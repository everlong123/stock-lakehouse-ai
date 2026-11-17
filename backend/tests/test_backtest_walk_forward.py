"""Walk-forward validation tests.

WHY THIS FILE EXISTS
--------------------
Walk-forward validation is the strictest evaluation the platform has: it
replays the strategy over many rolling windows and measures how it
behaves on data it was NOT fitted on. Three defects made the whole result
meaningless.

1. EVERY WINDOW REPORTED ZERO TRADES
   -----------------------------------
   The indicators a strategy needs need history: MA Crossover needs a
   50-session SMA. A test window of 30 calendar days holds only ~21
   sessions, so the long SMA was NaN for every row of the test window and
   the strategy never emitted a signal. The aggregate result was
   `avg_test_return = 0`, `total_test_trades = 0`, `return_consistency =
   0` - a wall of zeros that said nothing about the strategy.

   The fix: the test phase is given the tail of the training window as a
   warmup context, so the indicators are already defined on the first test
   session. The warmup rows are strictly in the past and are dropped
   before the simulation, so nothing leaks into the result.

2. THE TRAIN WINDOW GREW WITHOUT BOUND
   -------------------------------------
   The train window started at the first session of the history every
   time, so window 0 trained on 180 days and window 175 trained on ten
   years. The "overfitting ratio" divided a ten-year return by a
   one-month return, and came out at 790 - a number that does not mean
   anything. The train window is now fixed-length, so it slides forward
   with the test window.

3. THE RECENT WINDOWS CAME BACK AS FAILURES
   -----------------------------------------
   A window whose test period was shorter than the minimum was still
   emitted, and the run loop then marked it `passed = False` with the
   error "Insufficient bars in window". On AAPL 17 of the 176 windows
   were in that state - and they were the MOST RECENT ones, which are
   the ones a reader cares about most.
"""

from __future__ import annotations

import pandas as pd

from app.backtesting.walk_forward import WalkForwardValidator


def _frame(rows: int = 900) -> pd.DataFrame:
    """A deterministic series with a long history and clear swings."""
    import numpy as np

    rng = np.random.default_rng(11)
    steps = rng.normal(0.15, 1.0, rows).cumsum()
    close = 100.0 + steps
    timestamps = pd.date_range("2018-01-01", periods=rows, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": "TEST",
            "timestamp": timestamps,
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": 1_000_000.0,
        }
    )


def _validator(**kwargs) -> WalkForwardValidator:
    defaults = dict(
        train_period_days=180,
        test_period_days=30,
        step_days=20,
        min_train_bars=60,
        min_test_bars=20,
    )
    defaults.update(kwargs)
    return WalkForwardValidator(**defaults)


def test_a_short_test_window_still_produces_trades() -> None:
    """The warmup context must let the strategy trade on a short window."""
    frame = _frame()
    validator = _validator()
    windows = validator._generate_windows(frame)
    assert windows, "no windows were generated"

    with_trades = 0
    for window in windows[:25]:
        train = frame[
            (frame["timestamp"] >= window.train_start)
            & (frame["timestamp"] <= window.train_end)
        ].copy()
        test = frame[
            (frame["timestamp"] >= window.test_start)
            & (frame["timestamp"] <= window.test_end)
        ].copy()
        result = validator._test_on_window(
            test,
            "ma_crossover",
            10_000.0,
            0.001,
            0.0005,
            {"short_window": 20, "long_window": 50},
            warmup=train,
        )
        if result and result["number_of_trades"] > 0:
            with_trades += 1

    assert with_trades > 0, (
        "no window produced a single trade - the indicators never warm up"
    )


def test_the_test_window_alone_cannot_trade() -> None:
    """Without the warmup the strategy is blind - that is the bug itself."""
    frame = _frame()
    validator = _validator()
    windows = validator._generate_windows(frame)
    window = windows[len(windows) // 2]

    test = frame[
        (frame["timestamp"] >= window.test_start)
        & (frame["timestamp"] <= window.test_end)
    ].copy()

    without = validator._test_on_window(
        test, "ma_crossover", 10_000.0, 0.001, 0.0005,
        {"short_window": 20, "long_window": 50},
    )
    assert without is not None
    assert without["number_of_trades"] == 0, (
        "the isolated test window was expected to be too short for MA(50)"
    )


def test_the_train_window_has_a_fixed_length() -> None:
    """The train window must not grow from window to window."""
    frame = _frame()
    validator = _validator()
    windows = validator._generate_windows(frame)

    lengths = [
        int(((frame["timestamp"] >= w.train_start) & (frame["timestamp"] <= w.train_end)).sum())
        for w in windows
    ]
    assert lengths, "no windows"

    # The first and the last window must cover a comparable number of
    # sessions. With an expanding train window the last one would be
    # several times longer than the first.
    assert max(lengths) < min(lengths) * 2, (
        f"the train window is not fixed-length: {min(lengths)}..{max(lengths)}"
    )


def test_no_window_is_reported_as_a_failure_for_missing_bars() -> None:
    """A short test window must be skipped, never reported as a failure."""
    frame = _frame()
    validator = _validator()
    windows = validator._generate_windows(frame)

    for window in windows:
        test_bars = int(
            ((frame["timestamp"] >= window.test_start)
             & (frame["timestamp"] <= window.test_end)).sum()
        )
        assert test_bars >= validator.min_test_bars, (
            "a window that cannot be evaluated was emitted"
        )


def test_the_full_run_produces_no_failed_windows(monkeypatch) -> None:
    """The end-to-end run must not report failed windows."""
    frame = _frame()
    validator = _validator()
    monkeypatch.setattr(
        validator, "_load_data", lambda symbol, start_date, end_date: frame.copy()
    )
    result = validator.run("TEST", "ma_crossover", parameters={"short_window": 20, "long_window": 50})
    summary = result["summary"]

    assert summary["total_windows"] > 50, "too few windows to be meaningful"
    assert summary["failed_windows"] == 0, (
        f"{summary['failed_windows']} windows failed"
    )


def test_the_overfitting_ratio_is_readable(monkeypatch) -> None:
    """The ratio must be a sane magnitude, not a value like 790."""
    frame = _frame()
    validator = _validator()
    monkeypatch.setattr(
        validator, "_load_data", lambda symbol, start_date, end_date: frame.copy()
    )
    result = validator.run("TEST", "ma_crossover", parameters={"short_window": 20, "long_window": 50})
    summary = result["summary"]

    ratio = summary["overfitting_ratio"]
    if ratio is None:
        return  # a strategy that never trades has no ratio - also fine
    assert abs(ratio) < 100, (
        f"the overfitting ratio is {ratio}, which means the two sides are "
        "not measured over comparable periods"
    )
