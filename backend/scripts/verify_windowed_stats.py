"""Compare the windowed `/compare` and `/stats` against the full-history read.

WHY THIS SCRIPT EXISTS
----------------------
`/stocks/compare` and `/stocks/stats/{symbol}` were changed to request
their window from the backend instead of reading the symbol's whole
history and discarding most of it.

That is a performance optimisation, so it has to produce THE SAME
NUMBERS. This script computes the statistics both ways - from the
full history (the old behaviour) and from the windowed read (the new
one) - and prints any difference.

NO DATA IS FABRICATED: every number comes from the lakehouse.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.market_service import MarketService  # noqa: E402

TOLERANCE = 1e-9


def _stats_from(frame: pd.DataFrame, days: int) -> dict:
    """The statistics the endpoint computes, from an arbitrary frame."""
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    end = ts.iloc[-1]
    start = end - pd.Timedelta(days=days)
    window = frame.loc[(ts >= start).values]

    closes = pd.to_numeric(window["close"], errors="coerce").dropna()
    volumes = pd.to_numeric(window["volume"], errors="coerce").dropna()

    log_returns = np.log(closes / closes.shift(1)).dropna()
    volatility = (
        float(log_returns.std(ddof=1) * np.sqrt(252) * 100) if len(log_returns) > 1 else None
    )
    running_max = closes.cummax()
    drawdown = (closes - running_max) / running_max

    return {
        "sessions": int(len(closes)),
        "first_close": float(closes.iloc[0]),
        "last_close": float(closes.iloc[-1]),
        "high": float(closes.max()),
        "low": float(closes.min()),
        "mean_close": float(closes.mean()),
        "total_return_pct": float((closes.iloc[-1] / closes.iloc[0] - 1) * 100),
        "volatility_pct": volatility,
        "max_drawdown_pct": float(drawdown.min() * 100),
        "up_days": int((closes.diff().dropna() > 0).sum()),
        "down_days": int((closes.diff().dropna() < 0).sum()),
        "avg_volume": float(volumes.mean()) if not volumes.empty else None,
        "total_volume": float(volumes.sum()) if not volumes.empty else None,
    }


def main() -> int:
    service = MarketService()
    symbols = ["AAPL", "MSFT", "NVDA", "FPT", "VCB"]
    days = 252

    mismatches: list[str] = []

    for symbol in symbols:
        # The old behaviour: the whole history, trimmed afterwards.
        full = service.get_history(symbol, interval="1d")
        expected = _stats_from(full, days)

        # The new behaviour: the window, asked for explicitly.
        latest = service.get_latest(symbol, interval="1d")
        end = pd.to_datetime(latest["timestamp"], utc=True)
        start = end - pd.Timedelta(days=days)
        windowed = service.get_history(
            symbol, start=start.to_pydatetime(), end=end.to_pydatetime(), interval="1d"
        )
        actual = _stats_from(windowed, days)

        print(f"\n{symbol}: full rows={len(full)} window rows={len(windowed)}")
        for field, want in expected.items():
            got = actual.get(field)
            if got is None or want is None:
                if got != want:
                    mismatches.append(f"{symbol}.{field}: full={want!r} window={got!r}")
                continue
            if abs(float(got) - float(want)) > TOLERANCE:
                mismatches.append(f"{symbol}.{field}: full={want!r} window={got!r}")

    if mismatches:
        print(f"\n{len(mismatches)} MISMATCHES:")
        for line in mismatches:
            print(f"  {line}")
        return 1
    print("\nNo mismatch: the windowed read returns the same statistics as the full read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
