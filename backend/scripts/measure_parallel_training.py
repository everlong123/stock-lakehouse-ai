"""Measure the parallel LSTM training throughput.

WHY THIS SCRIPT EXISTS
----------------------
The nightly forecast needs one trained model per symbol per model family.
The measured serial cost of training an LSTM is ~17.7 s per symbol, so
1,002 symbols would take ~4.9 hours in one process. The question this
script answers is simple and necessary: **does running several symbols
in parallel actually make it faster, and by how much?**

The answer decides whether "train LSTM for the whole universe" is a
realistic plan or an aspiration. On a memory-constrained machine the
answer is not obvious - PyTorch reserves memory per process, so more
workers can mean less total throughput.

WHAT IT REPORTS
---------------
For each worker count: the wall-clock time to train a fixed set of
symbols, and the effective seconds per symbol. The ratio between the
serial cost and the parallel cost is the speed-up.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _train_one(symbol: str) -> tuple[str, float, str | None]:
    """Train one symbol. Returns (symbol, seconds, error)."""
    import logging

    logging.disable(logging.WARNING)
    from app.forecasting.trainer import train_model

    started = time.perf_counter()
    try:
        train_model(symbol, "lstm", horizon=1)
        return symbol, time.perf_counter() - started, None
    except Exception as exc:  # noqa: BLE001
        return symbol, time.perf_counter() - started, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="lstm")
    parser.add_argument("--workers", default="1,2,4,6")
    parser.add_argument(
        "--symbols",
        default="AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AMD,JPM,V,WES.AX,7203.T",
    )
    args = parser.parse_args()

    from app.core.logging_config import setup_logging

    setup_logging()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    worker_counts = [int(w) for w in args.workers.split(",") if w.strip()]

    print(f"[parallel-train] model={args.model} symbols={len(symbols)}")
    print(f"[parallel-train] cpu_count={os.cpu_count()}")

    for workers in worker_counts:
        batch = symbols[: workers * 2] or symbols
        started = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_train_one, batch))
        wall = time.perf_counter() - started
        failures = [r for r in results if r[2]]
        per_symbol = wall / len(results)
        print(
            f"[parallel-train] workers={workers:2d}  "
            f"{len(results)} symbols  wall={wall:6.1f}s  "
            f"effective={per_symbol:5.2f}s/symbol  "
            f"failures={len(failures)}",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
