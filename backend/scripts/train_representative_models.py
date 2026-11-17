"""Train the three model families on a REPRESENTATIVE sample of the universe.

WHY THIS SCRIPT EXISTS
-----------------------
The universe-wide nightly model is LINEAR REGRESSION, because it is the
only family whose cost is compatible with "every symbol, every night"
(~0.9 s per symbol end to end). ARIMA costs ~7.8 s and LSTM ~7 s, so
training either of them for all 1,002 symbols would take hours every
night.

That is fine for the nightly forecast. It is NOT fine for the thesis.
The claim "three model families were compared" is only credible with a
sample that spans several exchanges: a comparison on US tickers alone
does not show that the system works on the HK, KS or VN markets it
actually claims to serve.

    10|So this script picks a REPRESENTATIVE sample - a handful of liquid,
well-known tickers from every exchange in the Gold layer - and trains
all three families on each of them.

WHAT IT PRODUCES
----------------
Three trained models per sampled symbol, each with its own registry
entry holding the metrics measured on that model's hold-out split. Those
registries are what the forecasting page reads to show the per-model
comparison, and what the nightly batch uses to publish one forecast per
model for the same session.

HOW IT PICKS THE SYMBOLS
------------------------
The sample is chosen by EXCHANGE, from a shortlist of well-known
liquid tickers, and it is verified against the Gold layer before
training. A ticker that has no Gold history is skipped rather than
trained on nothing.

    python scripts/train_representative_models.py --per-exchange 5
    python scripts/train_representative_models.py --models arima,lstm --workers 4
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)


#: A shortlist of liquid, well-known tickers per exchange.
#:
#: WHY A SHORTLIST AND NOT A RANDOM SAMPLE: a random sample of the Gold
#: layer would be dominated by thinly-traded names whose hold-out split
#: is dominated by noise. These are the names a reader recognises, and
#: they are the ones a reviewer would want to see in the comparison
#: table. The list is a CHOICE, and it is recorded in the output so the
#: selection is reproducible and visible - it is not a silent filter.
#:
#: The suffixes follow Yahoo Finance's convention:
#:   .HK  Hong Kong      .KS  Korea      .T  Tokyo      .TW  Taiwan
#:   .AX  Australia     .L   London     .DE  Germany    .PA  Paris
#:   .TO  Toronto       .MI  Milan      .MC  Madrid     .AS  Amsterdam
#:   .SW  Switzerland
SHORTLIST: dict[str, list[str]] = {
    "US": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "AMD"],
    "HK": ["0700.HK", "9988.HK", "0005.HK", "1299.HK", "3690.HK", "9618.HK"],
    "KS": ["005930.KS", "000660.KS", "035420.KS", "005380.KS", "051910.KS"],
    "T": ["7203.T", "6758.T", "9984.T", "8306.T", "6861.T"],
    "TW": ["2330.TW", "2317.TW", "2454.TW", "2881.TW", "2308.TW"],
    "AX": ["BHP.AX", "CBA.AX", "WES.AX", "ANZ.AX", "FMG.AX"],
    "L": ["HSBA.L", "SHEL.L", "AZN.L", "BP.L", "VOD.L"],
    "DE": ["SAP.DE", "SIE.DE", "ALV.DE", "BMW.DE", "DTE.DE"],
    "PA": ["MC.PA", "OR.PA", "TTE.PA", "AIR.PA", "BNP.PA"],
    "TO": ["SHOP.TO", "RY.TO", "TD.TO", "BCE.TO", "CNQ.TO"],
    "LSE": ["VOD.L"],
    "MI": ["ENEL.MI", "ISP.MI", "BNP.MI", "ENI.MI"],
    "MC": ["SAN.MC", "IBE.MC", "BBVA.MC"],
    "AS": ["ASML.AS", "INGA.AS", "PHIA.AS"],
    "SW": ["NESN.SW", "NOVN.SW", "ROG.SW"],
}


def _exchange_of(symbol: str) -> str:
    """The exchange a symbol belongs to, by its suffix.

    A symbol with no suffix is treated as US - Yahoo Finance's own
    convention for the American exchanges.
    """
    if "." not in symbol:
        return "US"
    suffix = symbol.rsplit(".", 1)[1].upper()
    # Yahoo's `.L` suffix is the London exchange. The shortlist uses
    # `L` for it.
    return suffix


def pick_symbols(per_exchange: int) -> list[str]:
    """Pick up to ``per_exchange`` symbols from each exchange.

    The order inside each exchange follows the shortlist, so the result
    is deterministic: the same command picks the same symbols, and the
    comparison table can be reproduced.
    """
    chosen: list[str] = []
    for exchange, tickers in SHORTLIST.items():
        for ticker in tickers[:per_exchange]:
            chosen.append(ticker)
    return chosen


def _train_one(symbol: str, model_name: str) -> tuple[str, str, bool, str]:
    """Train one model. Returns (symbol, model, ok, detail).

    This runs in a worker process, so it returns a plain tuple rather
    than sharing objects with the parent.
    """
    try:
        from app.forecasting.trainer import train_model

        result = train_model(symbol, model_name, horizon=1)
        mae = result.get("metrics", {}).get("mae")
        return symbol, model_name, True, f"MAE={mae}"
    except Exception as exc:  # noqa: BLE001
        return symbol, model_name, False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="arima,lstm",
        help="Comma-separated model families to train.",
    )
    parser.add_argument(
        "--per-exchange",
        type=int,
        default=5,
        help="How many symbols to take from each exchange.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="How many symbols to train at the same time.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only the first N symbols overall.",
    )
    args = parser.parse_args()

    setup_logging()
    models = [name.strip().lower() for name in args.models.split(",") if name.strip()]

    # Only the symbols that actually have Gold history are worth training.
    from app.forecasting.universe_training import list_gold_symbols

    available = {symbol.upper() for symbol in list_gold_symbols()}
    wanted = [s for s in pick_symbols(args.per_exchange) if s.upper() in available]
    missing = [s for s in pick_symbols(args.per_exchange) if s.upper() not in available]
    if args.limit:
        wanted = wanted[: args.limit]

    print(
        f"[representative-training] {len(wanted)} symbols x {len(models)} models "
        f"= {len(wanted) * len(models)} training runs, {args.workers} workers",
        flush=True,
    )
    if missing:
        print(
            f"[representative-training] skipped (no Gold history): {', '.join(missing)}",
            flush=True,
        )

    jobs = [(symbol, model) for symbol in wanted for model in models]
    started = time.perf_counter()
    done = 0
    ok_count = 0
    failures: list[tuple[str, str, str]] = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_train_one, symbol, model): (symbol, model)
            for symbol, model in jobs
        }
        for future in as_completed(futures):
            symbol, model = futures[future]
            done += 1
            try:
                _, _, ok, detail = future.result()
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, str(exc)
            if ok:
                ok_count += 1
            else:
                failures.append((symbol, model, detail))
            elapsed = time.perf_counter() - started
            rate = done / elapsed if elapsed else 0
            eta = (len(jobs) - done) / rate if rate else 0
            print(
                f"[representative-training] {done}/{len(jobs)} {symbol}/{model} "
                f"{'OK' if ok else 'FAIL: ' + detail} "
                f"elapsed={elapsed:.0f}s eta={eta:.0f}s",
                flush=True,
            )

    print(
        f"[representative-training] done: {ok_count}/{len(jobs)} succeeded "
        f"in {time.perf_counter() - started:.0f}s",
        flush=True,
    )
    if failures:
        print(f"[representative-training] {len(failures)} failures:", flush=True)
        for symbol, model, detail in failures[:20]:
            print(f"  {symbol}/{model}: {detail}", flush=True)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
