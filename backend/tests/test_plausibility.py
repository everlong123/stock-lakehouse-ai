"""The plausibility screen must never reject a REAL bar.

WHY THIS FILE EXISTS
--------------------
The screen has a price floor and a magnitude check, and both have rejected
real data before:

* ACH (NYSE American, ~$0.21) was frozen at 2026-10-22 because every later
  bar sat below the absolute floor of 0.5.
* PARA (a US micro-cap that fell from ~$4.90 to ~$0.42) could not accept the
  provider's genuine 0.425 bar, because the reference price was taken as the
  MEDIAN of the newest partition - and that partition still held pre-split
  bars around 2.72. The wrong stored value was the reference, so the right
  value always looked impossible.

A unit error is still caught: it is 1000x off, not 10x off.

Run from the backend directory:

    .venv/Scripts/python.exe tests/test_plausibility.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.lakehouse.plausibility import (  # noqa: E402
    MAX_PRICE_DEVIATION_FACTOR,
    MIN_PLAUSIBLE_PRICE,
    MIN_SUBUNIT_PRICE,
    screen_batch,
)

FAILURES: list[str] = []


def _row(symbol: str, close: float, **overrides) -> pd.Series:
    """A minimal daily bar."""
    row = {
        "symbol": symbol,
        "timestamp": pd.Timestamp("2026-10-23", tz="UTC"),
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1000.0,
        "source": "yahoo_http",
        "ingestion_time": pd.Timestamp("2026-10-23", tz="UTC"),
    }
    row.update(overrides)
    return pd.Series(row)


def _accepts(symbol: str, close: float, reference: float | None) -> bool:
    """Does the screen keep this bar?"""
    frame = pd.DataFrame([_row(symbol, close)])
    refs = {symbol: reference} if reference is not None else None
    kept, _ = screen_batch(frame, reference_prices=refs)
    return len(kept) == 1


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


def main() -> int:
    print("plausibility screen")

    # ── Sub-unit instruments must be ACCEPTED ────────────────────────────
    # ACH trades at ~$0.21. Its own level is sub-unit, so the floor relaxes
    # and the bar is kept. (This is the bar that was silently dropped.)
    check("ACH at $0.21 is accepted", _accepts("ACH", 0.21, 0.21))
    check("ACH at $0.28 is accepted", _accepts("ACH", 0.28, 0.21))

    # PARA at $0.425 with a $0.47 reference (the symbol's recent LOW).
    check("PARA at $0.425 is accepted", _accepts("PARA", 0.425, 0.47))

    # ── Sub-unit prices with NO reference must still be REJECTED ─────────
    # Without evidence about the symbol, the stricter check wins.
    check(
        "sub-0.5 price with no reference is rejected",
        not _accepts("UNKNOWN", 0.21, None),
    )
    check(
        "sub-0.5 price with a USD-scale reference is rejected",
        not _accepts("AAPL", 0.21, 331.0),
    )

    # ── Unit errors must still be REJECTED ───────────────────────────────
    # VCB true price ~53,500 VND; a /1000 error is 53.5.
    check(
        "VCB divided by 1000 is rejected",
        not _accepts("VCB", 53.5, 53500.0),
    )
    # PARA true level ~0.47; a /1000 error is 0.00047.
    check(
        "PARA divided by 1000 is rejected",
        not _accepts("PARA", 0.00047, 0.47),
    )
    # A 10x error is below MAX_PRICE_DEVIATION_FACTOR (100x), so it is kept
    # on purpose: a wrongly deleted real bar costs more than a bad row
    # surviving one pass, and a split produces exactly that magnitude.
    check(
        "a 10x deviation is within tolerance by design",
        _accepts("PARA", 4.7, 0.47),
    )

    # ── The reference must be the LOW end, not the median ────────────────
    # A symbol whose newest partition still holds pre-split bars: the median
    # says 2.21 but the real level is 0.42. The reference must be the low
    # end, otherwise the genuine bar is rejected.
    import inspect

    from app.lakehouse.bronze import BronzeLayer  # noqa: E402

    source = inspect.getsource(BronzeLayer._reference_prices)
    check(
        "Bronze reference price uses the low end of the recent range",
        "min(closes)" in source,
    )
    check(
        "Bronze reference price no longer uses the median",
        "closes.median()" not in source,
    )

    # ── Constants ────────────────────────────────────────────────────────
    check("MIN_PLAUSIBLE_PRICE is 0.5", MIN_PLAUSIBLE_PRICE == 0.5)
    check("MIN_SUBUNIT_PRICE is tiny", 0 < MIN_SUBUNIT_PRICE < 1e-3)
    check("deviation factor is 100x", MAX_PRICE_DEVIATION_FACTOR == 100.0)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s) failed")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
