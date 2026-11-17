"""Multi-symbol walk-forward validation with a buy-and-hold benchmark.

WHY THIS SCRIPT EXISTS
----------------------
The walk-forward validator had only ever been run on ONE symbol (AAPL).
That is not enough to say anything about a trading strategy, because a
single stock over a single decade mostly measures whether that stock
went up. A thesis defence on "does this strategy work?" cannot be
answered with one symbol.

This script runs the SAME walk-forward machinery across a sample of the
universe and reports the DISTRIBUTION of the outcomes:

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

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py
    .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting.walk_forward import WalkForwardValidator  # noqa: E402
from app.core.constants import VN_SYMBOLS  # noqa: E402
from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "multi_symbol_walkforward.json"


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
    "MI": "BME",
    "L": "LSE",
    "SW": "SIX",
    "TO": "TSX",
    "AX": "Nasdaq Nordic",
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
    "SA": "TADAWUL",
    "NZ": "NZX",
    "VI": "BME",
    "BR": "BME",
}


def classify_exchange(symbol: str) -> str:
    """Map a symbol to the exchange it trades on."""
    sym = (symbol or "").upper().strip()
    if not sym:
        return "UNKNOWN"
    if sym in VN_SYMBOLS:
        return "HOSE"
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


# ── Aggregation helpers ────────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Sample N symbols from the whole universe")
    parser.add_argument(
        "--per-exchange",
        type=int,
        default=8,
        help="Take up to N symbols from EVERY exchange (0 = use --limit only)",
    )
    parser.add_argument("--strategy", type=str, default="ma_crossover", help="Strategy name")
    parser.add_argument("--train-days", type=int, default=365, help="Train window length in days")
    parser.add_argument("--test-days", type=int, default=90, help="Test window length in days")
    parser.add_argument("--step-days", type=int, default=90, help="How far each window slides")
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--transaction-fee", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0005)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    setup_logging()

    symbols = select_symbols(args.limit, args.per_exchange)
    universe_size = len(universe_symbols())
    print(f"Walk-forward across {len(symbols)} symbol(s) from a universe of {universe_size}")
    print(f"  strategy      : {args.strategy}")
    print(f"  train/test/step: {args.train_days}/{args.test_days}/{args.step_days} days")
    print()

    validator = WalkForwardValidator(
        train_period_days=args.train_days,
        test_period_days=args.test_days,
        step_days=args.step_days,
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
                strategy_name=args.strategy,
                initial_capital=args.initial_capital,
                transaction_fee=args.transaction_fee,
                slippage=args.slippage,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"symbol": symbol, "error": str(exc)})
            logger.warning("%s failed: %s", symbol, exc)
            continue

        summary = result.get("summary", {})
        windows = result.get("windows", [])

        # The validator now measures the buy-and-hold baseline on the
        # SAME test windows and records the paired difference per
        # window, so the baseline is not recomputed here. The script only
        # reads the numbers the validator already produced, which keeps
        # the API response and this report describing the same thing.
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
            print(
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
            "strategy": args.strategy,
            "train_period_days": args.train_days,
            "test_period_days": args.test_days,
            "step_days": args.step_days,
            "initial_capital": args.initial_capital,
            "transaction_fee": args.transaction_fee,
            "slippage": args.slippage,
            "symbols_tested": len(per_symbol),
            "universe_size": universe_size,
            "sampling": "per_exchange" if args.per_exchange else "even_spread",
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

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    _print_summary(payload, out_path)
    return 0


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


def _print_summary(payload: dict, out_path: Path) -> None:
    strat = payload["strategy_distribution"]
    bh = payload["buy_and_hold_distribution"]
    head = payload["head_to_head"]

    print()
    print("=" * 78)
    print("MULTI-SYMBOL WALK-FORWARD - DISTRIBUTION OF OUTCOMES")
    print("=" * 78)
    print(f"  symbols tested              : {payload['config']['symbols_tested']}")
    print(f"  universe size               : {payload['config']['universe_size']}")
    print()
    print("  STRATEGY (out of sample)")
    print(f"    median avg test return     : {_fmt(strat['median_avg_test_return'])}")
    print(f"    median avg test Sharpe     : {_fmt_sharpe(strat['median_avg_test_sharpe'])}")
    print(f"    median max drawdown        : {_fmt(strat['median_avg_test_max_drawdown'])}")
    print(f"    % symbols profitable       : {_fmt_pct(strat['pct_symbols_profitable'])}")
    # ``return_consistency`` is a RATIO in the validator (0..1), unlike the
    # other percentages in this report, which are already 0..100. It is
    # scaled here so the printed table is consistent.
    print(f"    median return consistency  : {_fmt_pct((strat['median_return_consistency'] or 0) * 100)}")
    print()
    print("  BUY AND HOLD (same windows, same costs)")
    print(f"    median avg return          : {_fmt(bh['median_avg_return'])}")
    print(f"    median Sharpe              : {_fmt_sharpe(bh['median_sharpe'])}")
    print(f"    median max drawdown        : {_fmt(bh['median_max_drawdown'])}")
    print(f"    % symbols profitable       : {_fmt_pct(bh['pct_symbols_profitable'])}")
    print()
    print("  HEAD TO HEAD (paired, per window)")
    print(f"    paired windows             : {head['paired_windows']}")
    print(f"    % windows beating B&H       : {_fmt_pct(head['pct_windows_beating_buy_hold'])}")
    print(f"    mean paired excess return  : {_fmt(head['mean_paired_excess_return'])}")
    print(f"    median paired excess return: {_fmt(head['median_paired_excess_return'])}")
    print(f"    % symbols beating B&H       : {_fmt_pct(head['pct_symbols_beating_buy_hold'])}")
    print(f"    median symbol excess return: {_fmt(head['median_symbol_excess_return'])}")
    print()
    print("  BY EXCHANGE")
    for exchange, row in payload["by_exchange"].items():
        print(
            f"    {exchange:14} n={row['symbols']:3} "
            f"strat_med={_fmt(row['strategy_median_return'])} "
            f"bh_med={_fmt(row['buy_hold_median_return'])} "
            f"beat_bh={_fmt_pct(row['pct_symbols_beating_buy_hold'])}"
        )
    print()
    print(f"  elapsed: {payload['elapsed_seconds']}s")
    print(f"  report : {out_path}")
    print("=" * 78)
    print()
    print("NOTE: this measures HISTORY. It does not predict the future.")
    print("=" * 78)


if __name__ == "__main__":
    raise SystemExit(main())
