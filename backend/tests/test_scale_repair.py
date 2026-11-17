"""Tests for the price-scale discontinuity detector."""

from __future__ import annotations

import pandas as pd
import pytest

from app.lakehouse.scale_repair import (
    DEFAULT_SPAN_FACTOR,
    contaminated_symbols,
    detect_scale_discontinuity,
    detect_scale_span,
    is_scale_contaminated,
)


def _series(close, start="2026-01-01"):
    n = len(close)
    timestamps = pd.date_range(start=start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"timestamp": timestamps, "close": close})


def test_a_continuous_history_reports_no_break() -> None:
    frame = _series([10.0 + i * 0.01 for i in range(200)])
    report = detect_scale_discontinuity(frame, symbol="AAA")
    assert report.continuous is True
    assert report.breaks == 0


def test_a_scale_break_is_detected_once_and_not_once_per_window() -> None:
    # 100 sessions at ~10, then a 1:10 reverse split -> the price becomes ~1.
    frame = _series([10.0] * 100 + [1.0] * 100)
    report = detect_scale_discontinuity(frame, symbol="BBB")
    assert report.breaks == 1
    break_info = report.discontinuities[0]
    assert break_info.factor == pytest.approx(10.0, rel=0.05)
    assert break_info.break_session == frame["timestamp"].iloc[100]


def test_a_real_market_move_within_the_threshold_is_not_a_break() -> None:
    # A 2x move is a real move, not a scale break.
    frame = _series([1.0] * 100 + [2.0] * 100)
    report = detect_scale_discontinuity(frame, symbol="CCC")
    assert report.continuous is True


def test_two_separate_breaks_are_both_found() -> None:
    frame = _series([10.0] * 100 + [1.0] * 100 + [0.1] * 100)
    report = detect_scale_discontinuity(frame, symbol="DDD")
    assert report.breaks == 2
    assert report.discontinuities[0].factor == pytest.approx(10.0, rel=0.05)
    assert report.discontinuities[1].factor == pytest.approx(10.0, rel=0.05)


def test_a_scale_that_returns_to_the_old_level_is_still_detected() -> None:
    # The shape PARA actually has: 0.42 scale, then a 4.1 scale, then back
    # to the 0.3 scale.
    frame = _series(
        [0.42] * 100 + [4.14] * 40 + [0.32] * 60,
    )
    report = detect_scale_discontinuity(frame, symbol="EEE")
    assert report.breaks >= 1


def test_contaminated_symbols_only_returns_the_broken_ones() -> None:
    frames = {
        "GOOD": _series([10.0] * 200),
        "BAD": _series([10.0] * 100 + [1.0] * 100),
    }
    reports = contaminated_symbols(frames)
    assert set(reports) == {"BAD"}


# ── The global span check ───────────────────────────────────────────────────
#
# WHY THIS TEST EXISTS
# --------------------
# The local-jump detector was run over all 1.002 symbols of the Gold layer
# on 15/11/2026. It flagged 46 symbols and a largest factor of 6,15x.
# ``PARA`` was NOT among them - yet PARA held 99,993% of the total
# absolute error of the verification ledger.
#
# The reason is that PARA's history does not break in ONE step: it spans
# from ~101.500 in 2021 to ~0,104 in November 2026 - a factor of a million
# - through a long series of steps, each of which looked ordinary.
#
# A detector that only looks one step at a time is blind to exactly the
# failure that hurt the most.


def test_the_span_of_a_healthy_history_is_one() -> None:
    frame = _series([10.0] * 200)
    assert detect_scale_span(frame, symbol="AAA") == pytest.approx(1.0, rel=0.05)


def test_the_span_of_a_slowly_growing_history_stays_small() -> None:
    # A stock that rose 13% over the window: normal, and far below the
    # 20x threshold.
    frame = _series([10.0 + i * 0.01 for i in range(200)])
    assert detect_scale_span(frame, symbol="GROW") < 2.0


def test_the_span_of_a_split_contaminated_history_is_huge() -> None:
    # The shape PARA actually has: 100.000 in 2021, 0,104 in 2026.
    frame = _series([100_000.0] * 100 + [0.104] * 100)
    span = detect_scale_span(frame, symbol="PARA")
    assert span > 100_000


def test_a_local_jump_alone_does_not_produce_a_huge_span() -> None:
    # A single 10x step still leaves the early and late levels close.
    frame = _series([10.0] * 100 + [100.0] * 100)
    assert detect_scale_span(frame, symbol="JUMP") < 20.0


def test_a_growing_stock_is_not_contaminated() -> None:
    # A healthy stock that is worth 30x more than it was: NVDA's measured
    # span on 15/11/2026 was 30,56x, with ZERO local breaks. The growth
    # is GRADUAL - a 30x jump in ONE session would be a corporate action,
    # not growth, and the local check is right to flag that.
    prices = [10.0 * (1.026 ** i) for i in range(200)]
    frame = _series(prices)
    span = detect_scale_span(frame, symbol="NVDA")
    assert 20.0 < span < 100.0, f"the synthetic span should be ~30x, got {span}"
    assert is_scale_contaminated(frame, symbol="NVDA") is False


def test_a_single_session_jump_of_thirty_times_is_a_local_break() -> None:
    # The same 30x span, but delivered in ONE session: that is a split,
    # and the local detector must catch it even though the span is under
    # the global threshold.
    frame = _series([10.0] * 100 + [300.0] * 100)
    assert is_scale_contaminated(frame, symbol="JUMP") is True


def test_a_split_contaminated_history_is_contaminated() -> None:
    # PARA's measured span was 3.503x.
    frame = _series([100_000.0] * 100 + [0.104] * 100)
    assert is_scale_contaminated(frame, symbol="PARA") is True


def test_the_span_threshold_is_documented_and_stable() -> None:
    # At 20x the check would flag NVDA (30,56x) and CELH (31,78x), which
    # are healthy symbols that simply grew. A false accusation is as bad
    # as a missed one.
    assert DEFAULT_SPAN_FACTOR == 100.0
