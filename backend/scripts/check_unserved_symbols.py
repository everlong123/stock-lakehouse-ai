"""Inspect the lakehouse rows for symbols the provider no longer serves.

WHY THIS EXISTS
---------------
The verification pass cannot compare a symbol the provider has dropped: a
404 or an empty response means there is nothing to compare against. That is
reported as `[NOPV]` / an error, not as a mismatch.

But "the provider stopped serving it" must NOT be allowed to mean "the
lakehouse holds garbage". These symbols still hold real history that was
fetched while the provider did serve them, and the web still renders it. So
this script checks that the stored rows are still INTERNALLY consistent and
plausible:

* the OHLC relationships hold (low <= open/close <= high),
* the volume is non-negative,
* there are no duplicate sessions,
* the series is monotonic in time,
* and the newest bar is not absurdly far from the median close.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/check_unserved_symbols.py CMA TCO WBA
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.bronze import BronzeLayer  # noqa: E402
from app.lakehouse.gold import GoldLayer  # noqa: E402
from app.lakehouse.silver import SilverLayer  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


def inspect(symbol: str) -> None:
    print(f"--- {symbol}")
    bronze = BronzeLayer().read(symbol)
    silver = SilverLayer().read(symbol)
    gold = GoldLayer().read(symbol)

    check("bronze has rows", not bronze.empty)
    check("silver has rows", not silver.empty)
    check("gold has rows", not gold.empty)
    if bronze.empty:
        return

    frame = silver if not silver.empty else bronze
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp")

    check("timestamps are unique", not frame["timestamp"].duplicated().any())
    check("timestamps are monotonic", frame["timestamp"].is_monotonic_increasing)

    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    check("no missing OHLC values", not frame[["open", "high", "low", "close"]].isna().any().any())
    check(
        "high >= open and high >= close",
        bool((frame["high"] >= frame["open"] - 1e-9).all() and (frame["high"] >= frame["close"] - 1e-9).all()),
    )
    check(
        "low <= open and low <= close",
        bool((frame["low"] <= frame["open"] + 1e-9).all() and (frame["low"] <= frame["close"] + 1e-9).all()),
    )
    check("volume is non-negative", bool((pd.to_numeric(frame["volume"], errors="coerce").fillna(0) >= 0).all()))
    check("all prices are positive", bool((frame["close"] > 0).all()))

    # The newest bar must not be an outlier against the series. A provider
    # that stopped serving a symbol often did so because of a corporate event,
    # so a big move at the end is EXPECTED - but a 100x jump means a unit
    # error, which is a defect we introduced.
    closes = frame["close"]
    median = float(closes.median())
    newest = float(closes.iloc[-1])
    ratio = newest / median if median else 0.0
    check(
        f"newest close {newest:.4f} is within 100x of the median {median:.4f}",
        0.01 < ratio < 100.0,
    )

    print(
        f"        rows={len(frame)}  {frame['timestamp'].iloc[0].date()} .. "
        f"{frame['timestamp'].iloc[-1].date()}  "
        f"close {closes.iloc[0]:.4f} -> {newest:.4f}"
    )
    # The three layers must agree on the newest close.
    newest_bronze = float(BronzeLayer().read(symbol)["close"].iloc[-1])
    if not silver.empty and not gold.empty:
        newest_silver = float(silver.sort_values("timestamp")["close"].iloc[-1])
        newest_gold = float(gold.sort_values("timestamp")["close"].iloc[-1])
        check(
            "bronze/silver/gold agree on the newest close",
            abs(newest_bronze - newest_silver) / max(newest_bronze, 1e-9) < 1e-6
            and abs(newest_bronze - newest_gold) / max(newest_bronze, 1e-9) < 1e-6,
        )


def main(argv: list[str]) -> int:
    symbols = [s.strip().upper() for s in argv if s.strip()]
    if not symbols:
        print("usage: check_unserved_symbols.py SYMBOL [SYMBOL ...]")
        return 2

    print(f"inspecting {len(symbols)} symbol(s) the provider no longer serves")
    for symbol in symbols:
        inspect(symbol)
        print()

    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed - the stored history is internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
