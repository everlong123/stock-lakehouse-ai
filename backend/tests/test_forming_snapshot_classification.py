"""A mid-session snapshot is not a provider disagreement.

THE DEFECT THIS FILE PINS
--------------------------
On 18/11/2026 the quality gate reported ``failed`` with 14 offending
symbols. The measurement:

    CAR  2026-11-17  stored  close 126.42  high 126.87  low 123.11  vol  77,163
                     provider close 124.64  high 126.87  low 123.11  vol 314,700

Every one of the 14 symbols disagreed on exactly ONE session - the newest
one - and every other session matched the provider exactly. The stored bar
was a snapshot taken while its own session was still open: its volume was
lower, and the provider's settled bar had already superseded it.

Reporting that as ``failed`` named the WRONG cause. It said "the provider
and the lakehouse disagree about a settled price", which sends the reader
hunting for a provider bug that does not exist, and it made a healthy
lakehouse look broken on the System Status page.

WHAT THE FIX IS
---------------
``check_against_provider`` now keeps the WHOLE bar - high, low, volume -
instead of only the close, and applies the same containment relation that
``app.lakehouse.forming_bar`` applies inside Bronze. A disagreement whose
two bars overlap and whose volume proves the order is a SNAPSHOT, so it is
counted as ``stale``, not as a mismatch.

The relation is OVERLAP, not containment. The measured case: CPB 2026-11-17
had ``forming.high = 24.01`` and ``settled.high = 24.05`` - the session went
four cents higher after the snapshot, so the settled range does NOT contain
the forming one, but the two still describe the same session.

A disagreement on a SETTLED session - one that is not the newest - must
STILL fail. That is the defect this check exists for, and the tests below
make sure the fix did not silence it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.quality_gate import _is_forming_snapshot  # noqa: E402
from app.lakehouse.forming_bar import (  # noqa: E402
    find_forming_snapshots,
    forming_snapshot_reason,
)

# ---------------------------------------------------------------------------
# The relation itself
# ---------------------------------------------------------------------------


def _bar(close: float, high: float, low: float, volume: float) -> dict:
    return {"close": close, "high": high, "low": low, "volume": volume}


#: The measured CAR 2026-11-17 pair. The stored bar was taken at 14:30,
#: while the session was still open.
CAR_STORED = _bar(close=126.42, high=126.87, low=123.11, volume=77_163)
CAR_SETTLED = _bar(close=124.64, high=126.87, low=123.11, volume=314_700)

#: The measured CPB 2026-11-17 pair. The session reached a new high AFTER
#: the snapshot, so the settled range does NOT contain the forming one.
CPB_STORED = _bar(close=23.965, high=24.01, low=23.32, volume=1_948_316)
CPB_SETTLED = _bar(close=23.58, high=24.05, low=23.21, volume=6_245_600)

#: The measured CHTR 2026-11-17 pair. The two highs differ by 2e-4 on a
#: $142 price - pure float noise from two different fetches.
CHTR_STORED = _bar(close=142.22, high=142.60020446777344, low=136.51, volume=789_672)
CHTR_SETTLED = _bar(close=138.50, high=142.60000610351562, low=136.51, volume=2_747_900)


def test_a_snapshot_of_a_settled_bar_is_recognised() -> None:
    """The stored CAR bar is a mid-session snapshot of the provider's bar."""
    assert _is_forming_snapshot(CAR_STORED, CAR_SETTLED) is True


def test_overlap_is_enough_containment_is_not_required() -> None:
    """A snapshot taken before the session reached its extreme still counts."""
    # The settled high is ABOVE the stored high, so containment fails.
    assert CPB_STORED["high"] < CPB_SETTLED["high"]
    assert _is_forming_snapshot(CPB_STORED, CPB_SETTLED) is True


def test_float_noise_between_two_fetches_is_not_a_disagreement() -> None:
    """Two fetches of the same session differ by float noise, not by a price."""
    assert CHTR_STORED["high"] != CHTR_SETTLED["high"]
    assert _is_forming_snapshot(CHTR_STORED, CHTR_SETTLED) is True


def test_a_settled_disagreement_is_not_a_snapshot() -> None:
    """Two bars of the same session with the same volume are not a snapshot."""
    settled = _bar(close=130.00, high=135.00, low=120.00, volume=1_000_000)
    other = _bar(close=140.00, high=145.00, low=125.00, volume=1_000_000)
    # Equal volumes describe the same moment, so there is no stale row.
    assert _is_forming_snapshot(settled, other) is False


def test_two_different_sessions_are_not_a_snapshot() -> None:
    """Bars whose ranges do not overlap are two sessions, not two moments."""
    forming = _bar(close=100.0, high=101.0, low=99.0, volume=1_000)
    elsewhere = _bar(close=200.0, high=201.0, low=199.0, volume=9_000)
    assert _is_forming_snapshot(forming, elsewhere) is False


def test_a_reverse_split_is_not_a_snapshot() -> None:
    """A price-scale break is a corporate action, not a frozen snapshot."""
    forming = _bar(close=19_700.0, high=19_900.0, low=19_600.0, volume=1_000)
    settled = _bar(close=27.52, high=27.90, low=27.10, volume=9_000)
    assert _is_forming_snapshot(forming, settled) is False


def test_a_bar_without_volume_is_not_a_snapshot() -> None:
    """Without volume there is nothing to order the two bars by."""
    forming = _bar(close=100.0, high=101.0, low=99.0, volume=float("nan"))
    settled = _bar(close=101.0, high=102.0, low=99.5, volume=9_000)
    assert _is_forming_snapshot(forming, settled) is False


# ---------------------------------------------------------------------------
# The relation inside Bronze is unchanged
# ---------------------------------------------------------------------------


def test_find_forming_snapshots_still_finds_the_pair_inside_bronze() -> None:
    """The Bronze-side detector keeps working after the range test changed."""
    frame = pd.DataFrame(
        [
            {
                "high": CAR_STORED["high"],
                "low": CAR_STORED["low"],
                "close": CAR_STORED["close"],
                "volume": CAR_STORED["volume"],
            },
            {
                "high": CAR_SETTLED["high"],
                "low": CAR_SETTLED["low"],
                "close": CAR_SETTLED["close"],
                "volume": CAR_SETTLED["volume"],
            },
        ]
    )
    pairs = find_forming_snapshots(frame)
    assert len(pairs) == 1
    stale, settled = pairs[0]
    assert stale["volume"] == CAR_STORED["volume"]
    assert settled["volume"] == CAR_SETTLED["volume"]


def test_forming_snapshot_reason_rejects_a_malformed_bar() -> None:
    """A bar missing its columns is not a snapshot, and does not raise."""
    malformed = pd.Series({"close": 100.0})
    well_formed = pd.Series(
        {"close": 101.0, "high": 102.0, "low": 99.0, "volume": 5_000}
    )
    assert forming_snapshot_reason(malformed, well_formed) is False


# ---------------------------------------------------------------------------
# The gate's own bookkeeping
# ---------------------------------------------------------------------------


def test_the_provider_check_reports_a_snapshot_as_stale_not_as_a_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider check must not call a mid-session snapshot a mismatch.

    The provider is stubbed here - it is a TEST DOUBLE for the network call,
    not a source of market numbers. The two bars it returns are the MEASURED
    CAR 2026-11-17 pair, so the assertion is about the gate's classification
    of a real situation, not about an invented price.
    """
    from app.core import quality_gate

    measured_frame = pd.DataFrame(
        [
            {
                "symbol": "CAR",
                "timestamp": pd.Timestamp("2026-11-17T14:30:00Z"),
                "open": 126.0,
                "high": CAR_SETTLED["high"],
                "low": CAR_SETTLED["low"],
                "close": CAR_SETTLED["close"],
                "volume": CAR_SETTLED["volume"],
            }
        ]
    )

    class _StubProvider:
        def get_historical_data(self, symbol: str, interval: str = "1d"):
            return measured_frame.copy()

    monkeypatch.setattr(
        "app.data_sources.factory.get_data_provider", lambda name: _StubProvider()
    )
    monkeypatch.setattr(
        quality_gate,
        "_stored_bars",
        lambda symbol, storage=None, days=30, indexes=None: {"2026-11-17": CAR_STORED},
        raising=False,
    )

    result, _ = quality_gate.check_against_provider(
        ["CAR"], batch_size=1, window=5, storage=object()
    )

    assert result.failed == 0
    assert result.status in {"passed", "warning"}
    assert result.details["stale_sessions"] == 1
    assert result.details["exact_sessions"] == 0


def test_a_disagreement_on_a_settled_session_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fix must not silence the defect this check exists to catch.

    The provider returns a bar with the SAME volume as the stored one, so
    there is no snapshot: the two bars describe the same moment and their
    closes differ. That is a real disagreement and it must still fail.
    """
    from app.core import quality_gate

    settled_frame = pd.DataFrame(
        [
            {
                "symbol": "CAR",
                "timestamp": pd.Timestamp("2026-11-17T14:30:00Z"),
                "open": 126.0,
                "high": 126.87,
                "low": 123.11,
                "close": 130.00,
                "volume": 77_163,
            }
        ]
    )

    class _StubProvider:
        def get_historical_data(self, symbol: str, interval: str = "1d"):
            return settled_frame.copy()

    monkeypatch.setattr(
        "app.data_sources.factory.get_data_provider", lambda name: _StubProvider()
    )
    monkeypatch.setattr(
        quality_gate,
        "_stored_bars",
        lambda symbol, storage=None, days=30, indexes=None: {"2026-11-17": CAR_STORED},
        raising=False,
    )

    result, _ = quality_gate.check_against_provider(
        ["CAR"], batch_size=1, window=5, storage=object()
    )

    assert result.failed == 1
    assert result.status == "failed"
    assert result.offenders == ["CAR"]
