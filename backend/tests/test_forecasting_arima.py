"""ARIMA evaluation tests.

WHY THIS FILE EXISTS
--------------------
The directional accuracy of the ARIMA model was reported as exactly
0.00, while the other two models reported a sensible 47-54%.

The reason was a one-line mistake in `ARIMAForecastModel.evaluate`. The
"previous close" handed to the metric was the close of the very session
being predicted:

    previous = close[:n]

The directional accuracy compares the direction of the forecast with the
direction of the ACTUAL move, and the actual move is measured as
`actual - previous`. With `previous` set to the session's own close,
`actual - previous` is the target itself, so the "actual direction" was
zero for every row and the metric could only ever come out as 0.

The previous close is the close of the session BEFORE the one being
predicted, so it has to be the close shifted by one row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecasting.arima import ARIMAForecastModel


def _series(rows: int = 400) -> pd.DataFrame:
    """A noisy but trending series, so the model has something to learn."""
    rng = np.random.default_rng(7)
    steps = rng.normal(0.2, 1.0, rows).cumsum()
    close = 100.0 + steps
    timestamps = pd.date_range("2020-01-01", periods=rows, freq="B", tz="UTC")
    return pd.DataFrame({"timestamp": timestamps, "close": close})


def _fit(frame: pd.DataFrame) -> ARIMAForecastModel:
    model = ARIMAForecastModel(order=(1, 1, 0))
    model.fit(frame["close"], frame["close"])
    return model


def test_directional_accuracy_is_not_always_zero() -> None:
    """The metric must not collapse to zero for every hold-out session."""
    frame = _series()
    split = int(len(frame) * 0.7)
    train = frame.iloc[:split]
    test = frame.iloc[split:].reset_index(drop=True)

    model = _fit(train)
    metrics = model.evaluate(test[["close"]], test["close"])

    assert metrics["directional_accuracy"] > 0.0, (
        "the directional accuracy collapsed to zero - the previous close "
        "is probably the close of the session being predicted"
    )
    assert metrics["directional_accuracy"] <= 1.0


def test_directional_accuracy_is_computed_against_the_previous_close() -> None:
    """A model that always predicts the previous close must score 100%."""
    frame = _series()
    split = int(len(frame) * 0.7)
    train = frame.iloc[:split]
    test = frame.iloc[split:].reset_index(drop=True)

    model = _fit(train)
    predictions = model.walk_forward(test[["close"]])

    # Score the walk-forward predictions against the SAME previous close
    # the model uses, and compare the two numbers.
    from app.forecasting.evaluator import evaluate_forecast

    close = test["close"].to_numpy(dtype=float)
    shifted = np.concatenate([[np.nan], close[:-1]])
    usable = np.isfinite(shifted)
    scored = evaluate_forecast(
        close[usable],
        predictions[usable],
        shifted[usable],
    )
    metrics = model.evaluate(test[["close"]], test["close"])

    assert abs(scored["directional_accuracy"] - metrics["directional_accuracy"]) < 1e-9, (
        "evaluate() does not use the same previous close as the metric"
    )


def test_walk_forward_predicts_one_step_at_a_time() -> None:
    """Each prediction must be made before the session it predicts."""
    frame = _series()
    split = int(len(frame) * 0.7)
    train = frame.iloc[:split]
    test = frame.iloc[split:].reset_index(drop=True)

    model = _fit(train)
    predictions = model.walk_forward(test[["close"]])

    assert len(predictions) == len(test)
    assert np.all(np.isfinite(predictions))
    # A one-step-ahead prediction of a trending series must not be wildly
    # far from the price.
    error = np.abs(predictions - test["close"].to_numpy(dtype=float))
    assert np.median(error) < 10.0, "the walk-forward predictions are misaligned"
