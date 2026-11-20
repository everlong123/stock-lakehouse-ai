"""The multi-symbol walk-forward report: the shared core.

WHY A SERVICE AND NOT A SCRIPT
-------------------------------
The report used to be produced by one script, ``scripts/run_multi_symbol_
walkforward.py``, and the API read a FILE that the script had written.
That worked, but it left two problems:

1. The file was written into the local filesystem of whoever ran the
   script. The ``scheduler`` container and the ``backend`` container do
   NOT share the ``data`` volume - they share MySQL and MinIO. So a
   report produced by cron could never be read by the API.
2. Nothing ran the script on a schedule, so the report was a SNAPSHOT
   from whenever somebody last remembered to run it. A thesis defence
   read numbers that were days or weeks old, and nothing on the page
   said so.

This module is the fix. It holds the whole computation, so the manual
script and the cron job run the SAME code and cannot drift apart, and it
persists the result into the lakehouse's ``backtests`` layer - which is
MinIO in production - so the API and the batch always read the same
object.

WHAT THE REPORT IS
------------------
A single-symbol backtest answers "what happened on this one stock".
That is a demonstration, not evidence: one stock over one decade mostly
measures whether that stock went up. This report answers the research
question - "does the strategy work ACROSS many stocks, and does it beat
simply holding them?" - by reporting the DISTRIBUTION of the outcomes:

- median / mean Sharpe across symbols
- percentage of symbols that were profitable out of sample
- the same numbers for a buy-and-hold baseline, so the strategy is
  measured against something, not against nothing
- a breakdown by exchange, because a result that only holds on one
  market is not a general finding

WHY BUY-AND-HOLD IS THE RIGHT BENCHMARK
---------------------------------------
It is the null hypothesis that every active strategy has to beat. It
also carries the SAME friction assumptions (one entry fee, one exit fee,
the same slippage) and the SAME execution convention (buy at the next
bar's open), so the comparison is not rigged by giving the baseline
better fills than the strategy.

THE COMPARISON IS PAIRED
------------------------
Both the strategy and the baseline are evaluated on the SAME test
windows, and the headline number is the mean of the per-window
differences. That is a paired comparison: the two numbers were measured
over identical periods on identical bars, so the difference is not
contaminated by the market moving differently between two separate
periods. Averaging the two sides separately and subtracting them would
be a weaker statistic and would hide the fact that a single symbol can
dominate the average.

WHAT IS NOT CLAIMED
-------------------
A backtest measures history. It does not measure the future. The
report says so explicitly, and every number in it is reproducible from
the lakehouse with the commands printed at the end.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: The lakehouse layer the report is persisted into.
#:
#: ``backtests`` maps to the ``stock-backtests`` bucket in MinIO and to
#: ``backend/data/backtests/`` on the local filesystem. It is the layer
#: that already holds the single-symbol backtest results, so the report
#: sits beside the results it summarises.
REPORT_LAYER = "backtests"

#: The object key template inside the layer.
#:
#: The key is namespaced under ``_walkforward/`` so it cannot collide
#: with the ``{symbol}_{strategy}_latest.json`` files the single-symbol
#: backtest writes into the same layer.
REPORT_KEY_TEMPLATE = "_walkforward/{strategy}.json"

#: The LOCAL file names, used as a fallback for a deployment that still
#: runs on the filesystem storage backend and has an old report on disk.
LOCAL_REPORT_FILES = {
    "ma_crossover": "multi_symbol_walkforward.json",
    "rsi_strategy": "multi_symbol_walkforward_rsi.json",
}

#: The strategies the report can be produced for.
STRATEGIES = tuple(LOCAL_REPORT_FILES)


# ── Exchange classification ────────────────────────────────────────────────

# The suffix Yahoo uses for a ticker names its exchange, so the suffix
# already carried in the symbol is the source of truth. A Vietnamese
# ticker has no suffix - it comes from SSI iBoard - so it is matched by
# name against the VN_SYMBOLS list.
_SUFFIX_TO_EXCHANGE: dict[str, str] = {
    "HK": "HKEX",
    "KS": "KRX",
    "T": "TSE",
    "SS": "SSE",
    "SZ": "SZSE",
    "TW": "TWSE",
    "DE": "XETRA",
    "AS": "Euronext",
    "PA": "Euronext",
    "MC": "BME",
    "MI": "Milan",
    "L": "LSE",
    "SW": "SIX",
    "TO": "TSX",
    "AX": "ASX",
    "ST": "Nasdaq Nordic",
    "HE": "Nasdaq Nordic",
    "OL": "Oslo",
    "CO": "CSE",
    "NS": "NSE",
    "BO": "BSE",
    "SI": "SGX",
    "KL": "Bursa",
    "JK": "IDX",
    "IS": "BIST",
    "TA": "TASE",
    "SA": "B3",
    "NZ": "NZX",
    "VI": "Vienna",
    "BR": "Euronext",
}


def classify_exchange(symbol: str) -> str:
    """Map a symbol to the exchange it trades on."""
    from app.core.constants import VN_SYMBOLS

    sym = (symbol or "").upper().strip()
    if not sym:
        return "UNKNOWN"
    if sym in VN_SYMBOLS:
        # Bare VN tickers span HOSE, HNX and UPCoM. Without verified listing
        # metadata this is a market group, not a claim that every name is HOSE.
        return "Vietnam"
    if "." not in sym:
        return "NYSE/NASDAQ"
    suffix = sym[sym.rindex(".") + 1:]
    return _SUFFIX_TO_EXCHANGE.get(suffix, f"OTHER({suffix})")


# ── Symbol selection ───────────────────────────────────────────────────────

def universe_symbols() -> list[str]:
    """Every symbol present in the Bronze bucket, i.e. with real history."""
    from app.lakehouse.bronze import BronzeLayer

    bronze = BronzeLayer()
    symbols: set[str] = set()
    for key in bronze.storage.list_objects("bronze", ""):
        if not key.startswith("symbol="):
            continue
        head = key.split("/", 1)[0]
        symbols.add(head.split("=", 1)[1])
    return sorted(symbols)


def select_symbols(limit: int = 0, per_exchange: int = 0) -> list[str]:
    """Pick the symbols to test.

    Two modes:

    * ``per_exchange > 0`` - take up to N symbols from EVERY exchange.
      This is the mode used for the headline report, because a sample
      that is 70% US names would make the "by exchange" breakdown
      meaningless for the smaller markets.
    * ``limit > 0`` - take an evenly spread sample of the whole universe.
      Used for quick runs.
    """
    universe = universe_symbols()
    if not universe:
        return []

    if per_exchange:
        buckets: dict[str, list[str]] = {}
        for sym in universe:
            buckets.setdefault(classify_exchange(sym), []).append(sym)
        picked: list[str] = []
        for exchange, group in sorted(buckets.items()):
            if per_exchange >= len(group):
                picked.extend(group)
                continue
            # Evenly spread inside the exchange, so the sample is not
            # concentrated in one corner of the ticker alphabet.
            step = len(group) / per_exchange
            picked.extend(group[int(i * step)] for i in range(per_exchange))
        return sorted(set(picked))

    if limit and limit < len(universe):
        step = len(universe) / limit
        return sorted({universe[int(i * step)] for i in range(limit)})

    return universe


# ── Aggregation helpers ───────────────────────────────────────────────────

def _median(values) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return float(pd.Series(clean, dtype=float).median())


def _mean(values) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return float(pd.Series(clean, dtype=float).mean())


def _pct_positive(values) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return float(sum(1 for v in clean if v > 0) / len(clean) * 100)


def _by_exchange(rows: list[dict]) -> dict:
    """Group the per-symbol rows by exchange."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["exchange"], []).append(row)

    summary: dict[str, dict] = {}
    for exchange, group in sorted(grouped.items()):
        strat_returns = [r["avg_test_return"] for r in group if r["avg_test_return"] is not None]
        strat_sharpes = [r["avg_test_sharpe"] for r in group if r["avg_test_sharpe"] is not None]
        bh_returns = [r["buy_hold_return"] for r in group if r["buy_hold_return"] is not None]
        bh_sharpes = [r["buy_hold_sharpe"] for r in group if r["buy_hold_sharpe"] is not None]
        excess = [r["paired_excess_return"] for r in group if r["paired_excess_return"] is not None]
        summary[exchange] = {
            "symbols": len(group),
            "strategy_median_return": _median(strat_returns),
            "strategy_median_sharpe": _median(strat_sharpes),
            "strategy_pct_profitable": _pct_positive(strat_returns),
            "buy_hold_median_return": _median(bh_returns),
            "buy_hold_median_sharpe": _median(bh_sharpes),
            "buy_hold_pct_profitable": _pct_positive(bh_returns),
            "median_paired_excess_return": _median(excess),
            "pct_symbols_beating_buy_hold": _pct_positive(excess),
        }
    return summary


# ── The computation ───────────────────────────────────────────────────────

def run_report(
    strategy: str = "ma_crossover",
    per_exchange: int = 8,
    limit: int = 0,
    train_days: int = 365,
    test_days: int = 90,
    step_days: int = 90,
    initial_capital: float = 10_000.0,
    transaction_fee: float = 0.001,
    slippage: float = 0.0005,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the walk-forward validation across the sample and build the report.

    ``progress`` is an optional callback used for logging: the cron job
    passes a logger so a long run leaves a trail in the scheduled-job
    log, and the manual script passes a print so the operator sees it on
    the terminal.
    """
    from app.backtesting.walk_forward import WalkForwardValidator

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    symbols = select_symbols(limit, per_exchange)
    # The universe size is reported in the config block, so the reader can
    # see the sample size against the population. When the sample IS the
    # whole universe (no limit, no per-exchange cap) the two are the same
    # list, and listing Bronze a second time would double the storage
    # round-trips of the pass for no new information.
    if not per_exchange and not limit:
        universe_size = len(symbols)
    else:
        universe_size = len(universe_symbols())

    say(
        f"walk-forward strategy={strategy} symbols={len(symbols)} "
        f"universe={universe_size}"
    )

    validator = WalkForwardValidator(
        train_period_days=train_days,
        test_period_days=test_days,
        step_days=step_days,
    )

    per_symbol: list[dict] = []
    strategy_returns: list[float] = []
    strategy_sharpes: list[float] = []
    strategy_dds: list[float] = []
    strategy_consistencies: list[float] = []
    bh_returns: list[float] = []
    bh_sharpes: list[float] = []
    bh_dds: list[float] = []
    all_paired_diffs: list[float] = []
    errors: list[dict] = []
    started = time.time()

    for index, symbol in enumerate(symbols, start=1):
        try:
            result = validator.run(
                symbol=symbol,
                strategy_name=strategy,
                initial_capital=initial_capital,
                transaction_fee=transaction_fee,
                slippage=slippage,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"symbol": symbol, "error": str(exc)})
            logger.warning("%s failed: %s", symbol, exc)
            continue

        summary = result.get("summary", {})
        windows = result.get("windows", [])

        # The validator measures the buy-and-hold baseline on the SAME
        # test windows and records the paired difference per window, so
        # the baseline is not recomputed here. The script only reads the
        # numbers the validator already produced, which keeps the API
        # response and this report describing the same thing.
        baseline = None
        if summary.get("avg_benchmark_return") is not None:
            baseline = {
                "avg_return": summary.get("avg_benchmark_return"),
                "avg_sharpe": summary.get("avg_benchmark_sharpe"),
                "avg_max_drawdown": summary.get("avg_benchmark_max_drawdown"),
                "windows": summary.get("windows_compared", 0),
            }

        mean_diff = summary.get("avg_excess_return")
        median_diff = None
        diffs = [
            w["test_excess_return"]
            for w in windows
            if w.get("test_excess_return") is not None
        ]
        if diffs:
            median_diff = float(pd.Series(diffs, dtype=float).median())
        all_paired_diffs.extend(diffs)

        row = {
            "symbol": symbol,
            "exchange": classify_exchange(symbol),
            "total_windows": summary.get("total_windows"),
            "passed_windows": summary.get("passed_windows"),
            "failed_windows": summary.get("failed_windows"),
            "avg_train_return": summary.get("avg_train_return"),
            "avg_test_return": summary.get("avg_test_return"),
            "avg_test_sharpe": summary.get("avg_test_sharpe"),
            "avg_test_max_drawdown": summary.get("avg_test_max_drawdown"),
            "total_test_trades": summary.get("total_test_trades"),
            "return_consistency": summary.get("return_consistency"),
            "overfitting_ratio": summary.get("overfitting_ratio"),
            "buy_hold_return": baseline.get("avg_return") if baseline else None,
            "buy_hold_sharpe": baseline.get("avg_sharpe") if baseline else None,
            "buy_hold_max_drawdown": baseline.get("avg_max_drawdown") if baseline else None,
            "buy_hold_windows": baseline.get("windows") if baseline else 0,
            # The PAIRED difference: the mean over windows of
            # (strategy return - buy-and-hold return).
            "paired_excess_return": mean_diff,
            "paired_excess_median": median_diff,
            "beat_buy_hold": bool(mean_diff > 0) if mean_diff is not None else None,
        }

        if row["avg_test_return"] is not None:
            strategy_returns.append(row["avg_test_return"])
        if row["avg_test_sharpe"] is not None:
            strategy_sharpes.append(row["avg_test_sharpe"])
        if row["avg_test_max_drawdown"] is not None:
            strategy_dds.append(row["avg_test_max_drawdown"])
        if row["return_consistency"] is not None:
            strategy_consistencies.append(row["return_consistency"])
        if row["buy_hold_return"] is not None:
            bh_returns.append(row["buy_hold_return"])
        if row["buy_hold_sharpe"] is not None:
            bh_sharpes.append(row["buy_hold_sharpe"])
        if row["buy_hold_max_drawdown"] is not None:
            bh_dds.append(row["buy_hold_max_drawdown"])

        per_symbol.append(row)

        if index % 5 == 0 or index == len(symbols):
            elapsed = time.time() - started
            say(
                f"  [{index}/{len(symbols)}] {symbol:10} "
                f"strat={_fmt(row['avg_test_return'])} "
                f"bh={_fmt(row['buy_hold_return'])} "
                f"excess={_fmt(row['paired_excess_return'])} "
                f"({elapsed:.0f}s)"
            )

    elapsed = time.time() - started

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "strategy": strategy,
            "train_period_days": train_days,
            "test_period_days": test_days,
            "step_days": step_days,
            "initial_capital": initial_capital,
            "transaction_fee": transaction_fee,
            "slippage": slippage,
            "symbols_tested": len(per_symbol),
            "universe_size": universe_size,
            "sampling": "per_exchange" if per_exchange else "even_spread",
            "grouping_note": (
                "Groups follow ticker suffixes; NYSE/NASDAQ, Euronext, Nordic "
                "and Vietnam are market groups. Vietnamese exchange membership "
                "has not been independently verified."
            ),
        },
        "strategy_distribution": {
            "symbols_with_usable_windows": len(strategy_returns),
            "median_avg_test_return": _median(strategy_returns),
            "mean_avg_test_return": _mean(strategy_returns),
            "median_avg_test_sharpe": _median(strategy_sharpes),
            "mean_avg_test_sharpe": _mean(strategy_sharpes),
            "median_avg_test_max_drawdown": _median(strategy_dds),
            "pct_symbols_profitable": _pct_positive(strategy_returns),
            "median_return_consistency": _median(strategy_consistencies),
        },
        "buy_and_hold_distribution": {
            "symbols_with_usable_windows": len(bh_returns),
            "median_avg_return": _median(bh_returns),
            "mean_avg_return": _mean(bh_returns),
            "median_sharpe": _median(bh_sharpes),
            "mean_sharpe": _mean(bh_sharpes),
            "median_max_drawdown": _median(bh_dds),
            "pct_symbols_profitable": _pct_positive(bh_returns),
        },
        "head_to_head": {
            # The paired statistic: every window of every symbol, with
            # the strategy and the baseline measured over the same bars.
            "paired_windows": len(all_paired_diffs),
            "pct_windows_beating_buy_hold": _pct_positive(all_paired_diffs),
            "mean_paired_excess_return": _mean(all_paired_diffs),
            "median_paired_excess_return": _median(all_paired_diffs),
            # The per-symbol view of the same question.
            "symbols_compared": len(
                [r for r in per_symbol if r["paired_excess_return"] is not None]
            ),
            "pct_symbols_beating_buy_hold": _pct_positive(
                [r["paired_excess_return"] for r in per_symbol]
            ),
            "median_symbol_excess_return": _median(
                [r["paired_excess_return"] for r in per_symbol]
            ),
        },
        "by_exchange": _by_exchange(per_symbol),
        "per_symbol": sorted(
            per_symbol,
            key=lambda r: -(r["paired_excess_return"] if r["paired_excess_return"] is not None else -9e9),
        ),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "note": (
            "Historical measurement only. A backtest measures what happened, "
            "not what will happen. The buy-and-hold baseline is simulated on "
            "the SAME test windows with the SAME fees and slippage, and the "
            "head-to-head numbers are PAIRED: each window contributes one "
            "difference, so both sides were measured over identical bars."
        ),
    }
    return payload


# ── Persistence ────────────────────────────────────────────────────────────

def report_key(strategy: str) -> str:
    """The object key the report for a strategy lives under."""
    return REPORT_KEY_TEMPLATE.format(strategy=strategy)


def persist_report(strategy: str, payload: dict[str, Any]) -> str:
    """Write the report into the lakehouse's ``backtests`` layer.

    WHY THE LAKEHOUSE AND NOT THE LOCAL FILESYSTEM
    ----------------------------------------------
    The ``scheduler`` container and the ``backend`` container share MySQL
    and MinIO, but they do NOT share the ``data`` volume. A report written
    to the local filesystem of the scheduler is invisible to the API. The
    lakehouse layer is the one place both containers already agree on,
    and it is where the single-symbol backtest results live too.

    The local file is written as well, as a convenience for the
    filesystem storage backend and for the manual script.
    """
    from app.lakehouse.storage_factory import get_storage_backend

    key = report_key(strategy)
    try:
        get_storage_backend().write_json(REPORT_LAYER, key, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Walk-forward report could not be written to storage: %s", exc)

    filename = LOCAL_REPORT_FILES.get(strategy)
    if filename:
        try:
            from app.core.config import settings

            path = settings.data_root_path / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Walk-forward local report copy could not be written: %s", exc)

    return key


def read_report(strategy: str) -> dict[str, Any] | None:
    """Read the stored report for a strategy, or ``None`` when there is none.

    The lakehouse layer is read FIRST, because in production that is
    where the cron job's report lives. The local file is the fallback
    for a filesystem-backed deployment.

    A report that cannot be read is reported as ``None`` - "the report
    has not been produced", not "the report is empty". The API renders
    the two differently.
    """
    import json

    from app.lakehouse.storage_factory import get_storage_backend

    try:
        payload = get_storage_backend().read_json(REPORT_LAYER, report_key(strategy))
        if isinstance(payload, dict):
            payload.setdefault("source", "lakehouse")
            return payload
    except Exception:  # noqa: BLE001 - no report in the lakehouse yet
        pass

    filename = LOCAL_REPORT_FILES.get(strategy)
    if filename:
        try:
            from app.core.config import settings

            path = settings.data_root_path / filename
            if path.is_file():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    payload.setdefault("source", "local_file")
                    return payload
        except Exception:  # noqa: BLE001
            pass
    return None


# ── Human-readable summary ────────────────────────────────────────────────

def _fmt(value) -> str:
    if value is None:
        return "   n/a"
    return f"{value * 100:6.2f}%"


def _fmt_sharpe(value) -> str:
    if value is None:
        return "   n/a"
    return f"{value:6.3f}"


def _fmt_pct(value) -> str:
    if value is None:
        return "   n/a"
    return f"{value:6.1f}%"


def format_summary(payload: dict[str, Any]) -> str:
    """Render the report's headline numbers as text."""
    strat = payload["strategy_distribution"]
    bh = payload["buy_and_hold_distribution"]
    head = payload["head_to_head"]

    lines = [
        "=" * 78,
        "MULTI-SYMBOL WALK-FORWARD - DISTRIBUTION OF OUTCOMES",
        "=" * 78,
        f"  symbols tested              : {payload['config']['symbols_tested']}",
        f"  universe size               : {payload['config']['universe_size']}",
        "",
        "  STRATEGY (out of sample)",
        f"    median avg test return     : {_fmt(strat['median_avg_test_return'])}",
        f"    median avg test Sharpe     : {_fmt_sharpe(strat['median_avg_test_sharpe'])}",
        f"    median max drawdown        : {_fmt(strat['median_avg_test_max_drawdown'])}",
        f"    % symbols profitable       : {_fmt_pct(strat['pct_symbols_profitable'])}",
        # ``return_consistency`` is a RATIO in the validator (0..1), unlike
        # the other percentages in this report, which are already 0..100.
        # It is scaled here so the printed table is consistent.
        f"    median return consistency  : {_fmt_pct((strat['median_return_consistency'] or 0) * 100)}",
        "",
        "  BUY AND HOLD (same windows, same costs)",
        f"    median avg return          : {_fmt(bh['median_avg_return'])}",
        f"    median Sharpe              : {_fmt_sharpe(bh['median_sharpe'])}",
        f"    median max drawdown        : {_fmt(bh['median_max_drawdown'])}",
        f"    % symbols profitable       : {_fmt_pct(bh['pct_symbols_profitable'])}",
        "",
        "  HEAD TO HEAD (paired, per window)",
        f"    paired windows             : {head['paired_windows']}",
        f"    % windows beating B&H       : {_fmt_pct(head['pct_windows_beating_buy_hold'])}",
        f"    mean paired excess return  : {_fmt(head['mean_paired_excess_return'])}",
        f"    median paired excess return: {_fmt(head['median_paired_excess_return'])}",
        f"    % symbols beating B&H       : {_fmt_pct(head['pct_symbols_beating_buy_hold'])}",
        f"    median symbol excess return: {_fmt(head['median_symbol_excess_return'])}",
        "",
        "  BY EXCHANGE",
    ]
    for exchange, row in payload["by_exchange"].items():
        lines.append(
            f"    {exchange:14} n={row['symbols']:3} "
            f"strat_med={_fmt(row['strategy_median_return'])} "
            f"bh_med={_fmt(row['buy_hold_median_return'])} "
            f"beat_bh={_fmt_pct(row['pct_symbols_beating_buy_hold'])}"
        )
    lines.extend(
        [
            "",
            f"  elapsed: {payload['elapsed_seconds']}s",
            "",
            "NOTE: this measures HISTORY. It does not predict the future.",
            "=" * 78,
        ]
    )
    return "\n".join(lines)
