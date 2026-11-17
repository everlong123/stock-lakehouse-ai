"""Tests for the mid-session snapshot detector.

The failure this covers was measured on 15/11/2026: the quality gate's
``check_source_agreement`` failed on AMD and INTC because two providers
appeared to report different closes for 2026-10-28.

    AMD 2026-10-28  yfinance_eod  close 567.00  vol  7,367,032
                    yahoo_http    close 578.44  vol 18,848,600

The ``yfinance_eod`` row was written at 16:29 UTC - 3.5 hours BEFORE the
NYSE close - so its close is the last trade price at that moment and its
volume is the volume traded so far. It is a mid-session snapshot frozen
into a daily bar, and the provider's real settled close is 578.44.

The rule under test is the CONTAINMENT relation: a session's high and low
can only expand as the session runs and its volume can only grow, so the
settled bar always contains the forming one.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.lakehouse.forming_bar import (
    SCALE_BREAK_RATIO,
    find_forming_snapshots,
    forming_snapshot_reason,
)


def _bar(
    high: float,
    low: float,
    close: float,
    volume: float,
    source: str = "yahoo_http",
    timestamp: str = "2026-10-28 13:30:00",
) -> pd.Series:
    return pd.Series(
        {
            "open": low,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "source": source,
            "timestamp": pd.Timestamp(timestamp, tz="UTC"),
        }
    )


# ── The measured case ──────────────────────────────────────────────────────


def test_the_measured_amd_pair_is_detected() -> None:
    """AMD 2026-10-28: the yfinance_eod row is the frozen mid-session one."""
    forming = _bar(573.96, 560.52, 567.00, 7_367_032, source="yfinance_eod",
                   timestamp="2026-10-28 04:00:00")
    settled = _bar(579.18, 560.52, 578.44, 18_848_600)

    assert forming_snapshot_reason(forming, settled) is True
    # The reverse direction must NOT fire: the settled bar is not contained
    # in the forming one, and its volume is larger.
    assert forming_snapshot_reason(settled, forming) is False


# ── The structural rule ───────────────────────────────────────────────────


def test_a_wider_range_with_larger_volume_is_the_settled_bar() -> None:
    """Containment plus a larger volume identifies the settled copy."""
    forming = _bar(10.5, 9.8, 10.0, 1_000)
    settled = _bar(11.0, 9.5, 10.8, 4_000)

    assert forming_snapshot_reason(forming, settled) is True
    assert forming_snapshot_reason(settled, forming) is False


def test_an_identical_bar_is_not_reported() -> None:
    """Two providers reporting the same bar agree; nothing is stale."""
    a = _bar(10.5, 9.8, 10.0, 1_000)
    b = _bar(10.5, 9.8, 10.0, 1_000)

    assert forming_snapshot_reason(a, b) is False


def test_equal_volume_means_the_same_moment() -> None:
    """A session's volume only grows, so equal volume is not a snapshot."""
    forming = _bar(10.5, 9.8, 10.0, 1_000)
    settled = _bar(11.0, 9.5, 10.8, 1_000)

    assert forming_snapshot_reason(forming, settled) is False


def test_a_narrower_range_with_a_larger_volume_is_not_a_snapshot() -> None:
    """Containment is required in BOTH directions, not just the volume."""
    forming = _bar(11.0, 9.5, 10.8, 1_000)
    settled = _bar(10.5, 9.8, 10.0, 4_000)

    assert forming_snapshot_reason(forming, settled) is False


def test_a_tiny_price_difference_is_not_reported() -> None:
    """Float noise between two providers is not a stale snapshot."""
    forming = _bar(10.5, 9.8, 10.0, 1_000)
    settled = _bar(11.0, 9.5, 10.0000001, 4_000)

    assert forming_snapshot_reason(forming, settled) is False


# ── The exclusion that keeps this rule out of the scale-break case ────────


def test_a_split_inside_the_session_is_not_a_snapshot() -> None:
    """CMG split 50:1 in October 2026 - that is a scale break, not a snapshot."""
    forming = _bar(19_900.0, 19_500.0, 19_750.0, 100_000)
    settled = _bar(28.0, 27.0, 27.52, 400_000)

    assert forming_snapshot_reason(forming, settled) is False


def test_the_scale_break_ratio_is_documented() -> None:
    """The threshold that separates a snapshot from a split."""
    assert SCALE_BREAK_RATIO == 10.0


# ── Robustness ────────────────────────────────────────────────────────────


def test_a_missing_value_does_not_raise() -> None:
    """A row with a NaN price must be ignored, not crash the screen."""
    forming = _bar(10.5, 9.8, float("nan"), 1_000)
    settled = _bar(11.0, 9.5, 10.8, 4_000)

    assert forming_snapshot_reason(forming, settled) is False


def test_a_non_numeric_volume_does_not_raise() -> None:
    forming = _bar(10.5, 9.8, 10.0, 1_000)
    settled = _bar(11.0, 9.5, 10.8, "not-a-number")

    assert forming_snapshot_reason(forming, settled) is False


def test_find_forming_snapshots_reports_the_pair() -> None:
    frame = pd.DataFrame(
        [
            _bar(573.96, 560.52, 567.00, 7_367_032, source="yfinance_eod",
                 timestamp="2026-10-28 04:00:00"),
            _bar(579.18, 560.52, 578.44, 18_848_600),
        ]
    )

    pairs = find_forming_snapshots(frame)

    assert len(pairs) == 1
    stale, settled = pairs[0]
    assert stale["close"] == 567.00
    assert settled["close"] == 578.44


def test_find_forming_snapshots_on_a_single_row_frame() -> None:
    frame = pd.DataFrame([_bar(10.5, 9.8, 10.0, 1_000)])

    assert find_forming_snapshots(frame) == []


def test_find_forming_snapshots_on_an_empty_frame() -> None:
    assert find_forming_snapshots(pd.DataFrame()) == []


@pytest.mark.parametrize(
    "forming_high,forming_low,forming_close,forming_volume,"
    "settled_high,settled_low,settled_close,settled_volume,expected",
    [
        # The measured AMD case.
        (573.96, 560.52, 567.00, 7_367_032, 579.18, 560.52, 578.44, 18_848_600, True),
        # Same range, same close - two providers agreeing.
        (579.18, 560.52, 578.44, 18_848_600, 579.18, 560.52, 578.44, 18_848_600, False),
        # The forming bar's range EXCEEDS the settled one - impossible.
        (600.0, 560.52, 567.00, 7_367_032, 579.18, 560.52, 578.44, 18_848_600, False),
        # The settled bar has LESS volume - not a snapshot.
        (573.96, 560.52, 567.00, 7_367_032, 579.18, 560.52, 578.44, 1_000_000, False),
    ],
)
def test_the_rule_behaves_as_documented(
    forming_high, forming_low, forming_close, forming_volume,
    settled_high, settled_low, settled_close, settled_volume, expected,
) -> None:
    forming = _bar(forming_high, forming_low, forming_close, forming_volume)
    settled = _bar(settled_high, settled_low, settled_close, settled_volume)

    assert forming_snapshot_reason(forming, settled) is expected
