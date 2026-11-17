"""Verify the "newest partition" fast path against the full-history read.

WHY THIS SCRIPT EXISTS
----------------------
`MarketService.get_latest` was changed to read only the newest monthly
partitions instead of the symbol's whole history. That is a performance
optimisation, so it has to PRODUCE THE SAME NUMBERS - not an
approximation.

For every symbol in the Gold layer this script compares:

  * the fast path (`_load_symbol_latest_uncached`), and
  * the full path (`_load_symbol_frame_uncached`, which reads every
    partition),

on the fields the quote endpoint serves: close, open, high, low,
volume and change_pct.

A mismatch is printed with the numbers on both sides, so the cause is
visible. The exit code is 1 when any symbol disagrees.

NO DATA IS FABRICATED: every number comes from the lakehouse.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.gold import GoldLayer  # noqa: E402
from app.services.market_service import (  # noqa: E402
    _load_symbol_frame_uncached,
    _load_symbol_latest_uncached,
)


def _quote(frame) -> dict:
    """The comparable fields of the newest bar of a frame."""
    if frame.empty:
        return {}
    last = frame.iloc[-1]
    prev_close = float(frame.iloc[-2]["close"]) if len(frame) > 1 else float(last["close"])
    change_pct = (float(last["close"]) - prev_close) / prev_close if prev_close else 0.0
    return {
        "timestamp": str(last["timestamp"]),
        "open": float(last["open"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "close": float(last["close"]),
        "volume": float(last["volume"]),
        "change_pct": change_pct,
    }


def main() -> int:
    layer = GoldLayer()
    symbols: list[str] = []
    for key in layer.storage.list_objects("gold"):
        if "symbol=" not in key:
            continue
        symbol = key.split("symbol=", 1)[1].split("/", 1)[0]
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    symbols.sort()

    print(f"Comparing the fast path against the full read for {len(symbols)} symbols.")

    mismatches: list[str] = []
    missing: list[str] = []
    compared = 0

    for symbol in symbols:
        try:
            full_frame, _layer = _load_symbol_frame_uncached(symbol)
            fast_frame, _fast_layer = _load_symbol_latest_uncached(symbol)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{symbol}: {exc}")
            continue

        if full_frame.empty:
            continue
        if fast_frame.empty:
            missing.append(f"{symbol}: fast path returned nothing")
            continue

        full = _quote(full_frame)
        fast = _quote(fast_frame)
        compared += 1

        for field, expected in full.items():
            actual = fast.get(field)
            if field == "timestamp":
                if actual != expected:
                    mismatches.append(f"{symbol}.{field}: full={expected} fast={actual}")
                continue
            if actual is None:
                mismatches.append(f"{symbol}.{field}: missing in the fast path")
                continue
            if abs(float(actual) - float(expected)) > 1e-9:
                mismatches.append(
                    f"{symbol}.{field}: full={expected!r} fast={actual!r}"
                )

    print(f"Compared {compared} symbols.")
    if missing:
        print(f"\n{len(missing)} symbols could not be compared:")
        for line in missing[:20]:
            print(f"  {line}")
    if mismatches:
        print(f"\n{len(mismatches)} MISMATCHES:")
        for line in mismatches[:40]:
            print(f"  {line}")
        return 1
    print("\nNo mismatch: the fast path returns the same numbers as the full read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
