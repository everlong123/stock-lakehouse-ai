"""The refresh watermark must ignore a bar that is still forming.

WHY THIS FILE EXISTS
--------------------
A daily bar is stamped at the session OPEN. For an equity the stamp is in the
past by the time the day ends, so the newest stored bar is usually yesterday's
- already settled.

For a 24/7 instrument it is not. Crypto's daily bar is stamped at 00:00Z of
the day it covers, so the bar stored for TODAY is still forming: its close is
whatever the price happened to be at the last fetch.

The auto-refresh skips any symbol whose newest bar is younger than
``AUTO_REFRESH_SKIP_IF_FRESH_HOURS``. Counting the forming bar made every
crypto symbol look up to date, so BTC-USD and ETH-USD were skipped on EVERY
pass - and because the forming bar kept a fresh timestamp, the last genuinely
settled day was never re-fetched either.

The measured result: BTC-USD's 2026-11-04 bar stayed frozen at the close it
had mid-session (77,912) while the provider had already settled it at
80,405. The verifier reported it as a permanent mismatch.

Run from the backend directory:

    .venv/Scripts/python.exe tests/test_refresh_watermark.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


class _FakeStorage:
    """A storage backend that serves one partition per symbol."""

    def __init__(self, partitions: dict[str, pd.DataFrame]) -> None:
        self._partitions = partitions

    def list_objects(self, layer: str, prefix: str) -> list[str]:
        return [k for k in self._partitions if k.startswith(prefix)]

    def read_parquet(self, layer: str, key: str) -> pd.DataFrame:
        return self._partitions.get(key, pd.DataFrame())


class _FakeBronze:
    """Just enough of BronzeLayer to exercise the watermark logic."""

    layer_name = "bronze"

    def __init__(self, storage) -> None:
        self.storage = storage

    # Reuse the real implementation.
    from app.lakehouse.bronze import BronzeLayer as _Bronze

    latest_settled_timestamp = _Bronze.latest_settled_timestamp


def _frame(stamps: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["X"] * len(stamps),
            "timestamp": pd.to_datetime(stamps, utc=True),
            "close": [1.0] * len(stamps),
        }
    )


def main() -> int:
    print("refresh watermark")

    now = pd.Timestamp("2026-11-05 14:00:00", tz="UTC")

    # ── Crypto: today's bar is forming, yesterday's is settled ───────────
    crypto = _FakeBronze(
        _FakeStorage(
            {
                "symbol=BTC-USD/year=2026/month=11/part-001.parquet": _frame(
                    [
                        "2026-11-03 00:00:00+00:00",
                        "2026-11-04 00:00:00+00:00",
                        "2026-11-05 00:00:00+00:00",
                    ]
                ),
            }
        )
    )
    settled = crypto.latest_settled_timestamp("BTC-USD", now=now)
    check(
        "crypto watermarks on the last SETTLED bar, not today's forming one",
        settled == pd.Timestamp("2026-11-04 00:00:00+00:00"),
    )
    check("the watermark is not today", settled < now.normalize())

    # The bug this fixes: with the forming bar counted, the watermark was
    # 2026-11-05 00:00Z, i.e. only 14h old, so the refresh skipped the symbol.
    forming = pd.Timestamp("2026-11-05 00:00:00+00:00")
    check(
        "the forming bar would have looked fresh (the original bug)",
        (now - forming).total_seconds() / 3600.0 < 24,
    )
    check(
        "the settled watermark is old enough to trigger a refresh",
        (now - settled).total_seconds() / 3600.0 > 24,
    )

    # ── Equity: the newest bar is stamped in the past, so it is settled ──
    equity = _FakeBronze(
        _FakeStorage(
            {
                "symbol=AAPL/year=2026/month=11/part-001.parquet": _frame(
                    [
                        "2026-11-03 13:30:00+00:00",
                        "2026-11-04 13:30:00+00:00",
                    ]
                ),
            }
        )
    )
    settled_equity = equity.latest_settled_timestamp("AAPL", now=now)
    check(
        "an equity watermarks on its newest bar",
        settled_equity == pd.Timestamp("2026-11-04 13:30:00+00:00"),
    )

    # ── A symbol whose only bar is today's forming bar ───────────────────
    only_forming = _FakeBronze(
        _FakeStorage(
            {
                "symbol=NEW/year=2026/month=11/part-001.parquet": _frame(
                    ["2026-11-05 00:00:00+00:00"]
                ),
            }
        )
    )
    check(
        "a symbol with only a forming bar has no settled watermark",
        only_forming.latest_settled_timestamp("NEW", now=now) is None,
    )

    # ── A symbol with no stored data at all ──────────────────────────────
    empty = _FakeBronze(_FakeStorage({}))
    check(
        "a symbol with no data has no watermark",
        empty.latest_settled_timestamp("NOPE", now=now) is None,
    )

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
