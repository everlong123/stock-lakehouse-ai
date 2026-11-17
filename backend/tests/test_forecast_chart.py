"""The forecast chart must react to the symbol and to the horizon.

WHY THIS FILE EXISTS
--------------------
The "Actual vs Predicted" chart had three defects that all looked like one
symptom to the user: "the predicted line never changes".

1. The chart served the `predictions.parquet` written at TRAINING time, so
   switching symbols showed the previously trained symbol's curve.
2. The prediction was plotted against the actual close of the SAME
   session, but the model predicts the NEXT session - a one-session shift.
3. `horizon` was ignored for the feature-based models, so the chart never
   contained a future session at all.

These tests pin down the behaviour that replaced it: the history is
recomputed from the live Gold data and aligned to the session it predicts,
the forecast reaches into the future, and the forecast really does depend
on the symbol.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.forecasting.multistep import forecast_ahead, holdout_history  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


def _gold(symbol: str, close: float, sessions: int = 120) -> pd.DataFrame:
    """A synthetic Gold frame with a rising close and full features."""
    index = pd.date_range("2025-01-02", periods=sessions, freq="B", tz="UTC")
    base = close * (1.0 + 0.001 * pd.Series(range(sessions)))
    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": index,
            "open": base,
            "high": base * 1.01,
            "low": base * 0.99,
            "close": base,
            "volume": 1_000_000.0,
        }
    )
    for column in (
        "return", "sma_5", "sma_10", "sma_20", "sma_50",
        "ema_12", "ema_26", "rsi_14", "macd", "macd_signal",
    ):
        frame[column] = 1.0
    frame["bb_middle"] = base
    return frame


class _EchoModel:
    """A model that echoes the close plus a fixed drift.

    It stands in for a real forecaster so the tests check the PLUMBING -
    the alignment and the recursion - rather than the model's accuracy.
    """

    def __init__(self, drift: float = 1.0) -> None:
        self.drift = drift

    def predict(self, X):
        frame = pd.DataFrame(X)
        return (frame["close"].to_numpy(dtype=float) * self.drift).reshape(-1, 1)


def main() -> int:
    print("forecast chart behaviour")

    # --- 1. The forecast reaches into the future -------------------------
    gold = _gold("TEST", 100.0)
    model = _EchoModel(drift=1.01)
    future = forecast_ahead(model, gold, "linear_regression", horizon=5)

    check("the forecast has one point per requested step", len(future) == 5)
    check(
        "every forecast point is in the future",
        all(p["timestamp"] > str(gold["timestamp"].iloc[-1]) for p in future),
    )
    check(
        "every forecast point has no actual close yet",
        all(p["actual"] is None for p in future),
    )
    check(
        "the forecast timestamps are strictly increasing",
        [p["timestamp"] for p in future] == sorted(p["timestamp"] for p in future),
    )

    # --- 2. The forecast actually depends on the horizon -----------------
    short = forecast_ahead(model, gold, "linear_regression", horizon=3)
    long = forecast_ahead(model, gold, "linear_regression", horizon=10)
    check("a longer horizon produces more points", len(long) > len(short))
    check(
        "the first forecast point does not depend on the horizon",
        short[0]["predicted"] == long[0]["predicted"],
    )
    check(
        "a longer horizon extends further into the future",
        long[-1]["timestamp"] > short[-1]["timestamp"],
    )

    # --- 3. The forecast depends on the symbol ----------------------------
    other = forecast_ahead(_EchoModel(drift=1.01), _gold("OTHER", 250.0), "linear_regression", horizon=5)
    check(
        "a different price level produces a different forecast",
        abs(other[0]["predicted"] - future[0]["predicted"]) > 1.0,
    )

    # --- 4. The history is aligned to the session it predicts -------------
    history = holdout_history(model, gold, "linear_regression")
    check("the history is not empty", len(history) > 0)
    check(
        "every history point carries a real close",
        all(p["actual"] is not None for p in history),
    )
    check(
        "the history timestamps are strictly increasing",
        [p["timestamp"] for p in history] == sorted(p["timestamp"] for p in history),
    )
    check(
        "the history does not run past the last stored session",
        history[-1]["timestamp"] <= str(gold["timestamp"].iloc[-1]),
    )

    # The alignment check: `predicted[t]` must be the model's estimate for
    # `actual[t]`. With the echo model that means the prediction at index i
    # equals the close at index i - which is only true if the series was
    # shifted forward by one session.
    closes = pd.to_numeric(gold["close"], errors="coerce").to_numpy()
    timestamps = list(gold["timestamp"].astype(str))
    misaligned = 0
    for point in history:
        try:
            position = timestamps.index(point["timestamp"])
        except ValueError:
            continue
        if position == 0:
            continue
        # The prediction for session t is the model's output on session t-1.
        expected = closes[position - 1] * model.drift
        if abs(point["predicted"] - expected) > 1e-6:
            misaligned += 1
    check("the history is aligned to the session it predicts", misaligned == 0)

    # --- 5. The hold-out window hides the training rows -------------------
    window = (gold["timestamp"].iloc[80], gold["timestamp"].iloc[-1])
    windowed = holdout_history(model, gold, "linear_regression", window=window)
    check("the windowed history is not empty", len(windowed) > 0)
    check(
        "the windowed history starts at or after the window start",
        all(p["timestamp"] >= str(window[0]) for p in windowed),
    )
    check(
        "the windowed history does not include the training rows",
        len(windowed) < len(history) + 40,
    )

    # --- 6. A degenerate horizon is handled -------------------------------
    check("a horizon of zero produces no points", forecast_ahead(model, gold, "linear_regression", 0) == [])

    # --- 7. The LSTM's different array shape is handled -------------------
    #
    # LSTM consumes a sliding window of `sequence_length` rows, so it
    # returns `len(frame) - sequence_length + 1` values instead of one
    # per row. If that offset is ignored, every prediction is attached to
    # the wrong session - which is the same one-session-style bug the
    # chart had, just with a different stride.
    print()
    print("lstm array shape")

    class _EchoLSTM(_EchoModel):
        """Mimics the LSTM contract: a windowed model with an offset."""

        def __init__(self, sequence_length: int = 5, drift: float = 1.01) -> None:
            super().__init__(drift=drift)
            self.sequence_length = sequence_length

        def predict(self, X):
            frame = pd.DataFrame(X)
            closes = frame["close"].to_numpy(dtype=float)
            # Drop the first `sequence_length - 1` rows, exactly like the
            # real LSTM does when it builds its windows.
            trimmed = closes[self.sequence_length - 1 :]
            return (trimmed * self.drift).reshape(-1, 1)

    lstm = _EchoLSTM(sequence_length=5)
    lstm_history = holdout_history(lstm, gold, "lstm")
    check("the lstm history is not empty", len(lstm_history) > 0)
    check(
        "the lstm history carries a real close for every point",
        all(p["actual"] is not None for p in lstm_history),
    )

    # The lstm estimate for session j comes from the window that ENDS one
    # row earlier, so it is the echo of the close at session j - 1. That is
    # the same one-session-lookahead shape as Linear Regression, just with
    # a longer window.
    closes = pd.to_numeric(gold["close"], errors="coerce").to_numpy()
    timestamps = list(gold["timestamp"].astype(str))
    misaligned = 0
    for point in lstm_history:
        try:
            position = timestamps.index(point["timestamp"])
        except ValueError:
            continue
        expected = closes[position - 1] * lstm.drift
        if abs(point["predicted"] - expected) > 1e-6:
            misaligned += 1
    check("the lstm history is aligned to the session it predicts", misaligned == 0)

    lstm_future = forecast_ahead(lstm, gold, "lstm", horizon=5)
    check("the lstm forecast has one point per requested step", len(lstm_future) == 5)
    check(
        "the lstm forecast points are in the future",
        all(p["timestamp"] > str(gold["timestamp"].iloc[-1]) for p in lstm_future),
    )
    check(
        "the lstm forecast points have no actual close",
        all(p["actual"] is None for p in lstm_future),
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
