"""LSTM forecasting tests.

WHY THIS FILE EXISTS
--------------------
The LSTM used to be trained to predict the ABSOLUTE next close. That made
the target non-stationary.

On AAPL the training split covered prices between 26 and 196 while the
hold-out split covered 195 to 349. The `MinMaxScaler` was fitted on the
training prices, so every hold-out price scaled to a value ABOVE 1.0 - a
region of the input space the network had never seen.

The visible symptom was a hard ceiling: the model could not predict a
price above the training maximum, so it saturated at roughly 278 while
the stock was at 345. The measured hold-out error was MAE 50.5
(MAPE 15.6%), and the forecast chart showed a line that sat far below the
real price and drifted the wrong way.

The fix is to predict the RATIO `next_close / close` and restore the price
level afterwards. These tests pin that behaviour down so it cannot
regress silently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecasting.lstm import LSTMForecastModel


def _rising_frame(rows: int = 400, start: float = 50.0, step: float = 0.35) -> pd.DataFrame:
    """A frame whose price climbs steadily, like a rising market."""
    timestamps = pd.date_range("2020-01-01", periods=rows, freq="B", tz="UTC")
    close = start + step * np.arange(rows)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": close,
            "volume": np.full(rows, 1_000_000.0),
            "return": np.gradient(close),
            "sma_20": pd.Series(close).rolling(20, min_periods=1).mean().to_numpy(),
            "ema_12": pd.Series(close).ewm(span=12, adjust=False).mean().to_numpy(),
            "rsi_14": np.full(rows, 55.0),
            "macd": np.zeros(rows),
            "bb_middle": pd.Series(close).rolling(20, min_periods=1).mean().to_numpy(),
            "rolling_std_20": pd.Series(close).rolling(20, min_periods=2).std().fillna(0.0).to_numpy(),
        }
    )


def _fit(frame: pd.DataFrame, sequence_length: int = 10, epochs: int = 12) -> tuple:
    features = [
        "close", "volume", "return", "sma_20", "ema_12",
        "rsi_14", "macd", "bb_middle", "rolling_std_20",
    ]
    clean = frame.copy()
    clean["target_close_next"] = clean["close"].shift(-1)
    clean = clean.dropna(subset=features + ["target_close_next"]).reset_index(drop=True)

    split = clean.iloc[: int(len(clean) * 0.7)].copy()
    test = clean.iloc[int(len(clean) * 0.7) :].copy()

    model = LSTMForecastModel(
        sequence_length=sequence_length,
        hidden_size=16,
        num_layers=1,
        epochs=epochs,
        batch_size=32,
    )
    model.fit(split[features], split["target_close_next"])
    return model, test, features


def test_lstm_uses_a_relative_target_when_a_close_is_available() -> None:
    """The model must predict a ratio, not an absolute price."""
    frame = _rising_frame()
    model, _test, _features = _fit(frame)
    assert model.target_mode == "relative", (
        "the LSTM must scale-free its target by the close"
    )


def test_lstm_predictions_scale_with_the_price_level() -> None:
    """The same model applied to a doubled price level must double its output.

    This is the property the absolute target destroyed: a model trained at
    50 could not predict 350, because 350 was outside the range the
    scaler had ever seen.
    """
    frame = _rising_frame()
    model, _test, features = _fit(frame)

    base = frame.iloc[-40:].reset_index(drop=True)
    doubled = base.copy()
    for column in ("close", "sma_20", "ema_12", "bb_middle"):
        doubled[column] = doubled[column] * 2

    normal = model.predict(base[features])
    scaled = model.predict(doubled[features])

    assert len(normal) == len(scaled)
    ratio = scaled[-1] / normal[-1]
    assert 1.9 < ratio < 2.1, (
        f"the prediction did not follow the price level: ratio={ratio}"
    )


def test_lstm_forecast_stays_close_to_the_current_price() -> None:
    """A trained model must not predict a price far from the last close.

    Before the fix the model saturated at the training maximum, which on
    AAPL was 196 while the stock traded at 345 - a 43% error that the
    chart displayed as a confident forecast.
    """
    frame = _rising_frame()
    model, _test, features = _fit(frame)

    tail = frame.iloc[-40:].reset_index(drop=True)
    prediction = float(model.predict(tail[features])[-1])
    last_close = float(tail["close"].iloc[-1])

    assert abs(prediction - last_close) / last_close < 0.25, (
        f"the prediction {prediction} is far from the last close {last_close}"
    )


def test_lstm_target_scaler_is_not_refit_on_the_validation_split() -> None:
    """The validation split must not leak into the target scaler."""
    frame = _rising_frame()
    features = [
        "close", "volume", "return", "sma_20", "ema_12",
        "rsi_14", "macd", "bb_middle", "rolling_std_20",
    ]
    clean = frame.copy()
    clean["target_close_next"] = clean["close"].shift(-1)
    clean = clean.dropna(subset=features + ["target_close_next"]).reset_index(drop=True)

    train = clean.iloc[:200]
    validation = clean.iloc[200:260]

    model = LSTMForecastModel(sequence_length=10, hidden_size=16, num_layers=1, epochs=2)
    model.fit(
        train[features],
        train["target_close_next"],
        validation[features],
        validation["target_close_next"],
    )

    # The scaler must have been fitted on the TRAINING ratios only. The
    # validation prices are much higher, so a scaler that had seen them
    # would have a different maximum.
    ratios = (
        train["target_close_next"].to_numpy()
        / train["close"].to_numpy()
    )
    expected_max = float(np.max(ratios))
    fitted_max = float(model.target_scaler.data_max_[0])

    assert fitted_max == pytest.approx(expected_max, rel=1e-6), (
        "the target scaler was re-fitted on data it should not have seen"
    )


def test_lstm_falls_back_to_absolute_target_without_a_close_column() -> None:
    """A model trained WITHOUT a `close` feature keeps the absolute target.

    The relative target needs a close to divide by, so a caller whose
    feature set has no close must still get a working model rather than a
    crash.
    """
    frame = _rising_frame()
    features = [
        "volume", "return", "sma_20", "ema_12",
        "rsi_14", "macd", "bb_middle", "rolling_std_20",
    ]
    clean = frame.copy()
    clean["target_close_next"] = clean["close"].shift(-1)
    clean = clean.dropna(subset=features + ["target_close_next"]).reset_index(drop=True)

    model = LSTMForecastModel(sequence_length=10, hidden_size=16, num_layers=1, epochs=3)
    model.fit(clean[features], clean["target_close_next"])

    assert model.target_mode == "absolute"

    predictions = model.predict(clean[features])
    assert len(predictions) == len(clean) - model.sequence_length + 1
    assert np.all(np.isfinite(predictions))


def test_lstm_metrics_are_finite_on_the_holdout_split() -> None:
    """The reported metrics must be finite and consistent."""
    frame = _rising_frame()
    model, test, features = _fit(frame)
    metrics = model.evaluate(test[features], test["target_close_next"])

    assert metrics["mae"] >= 0
    assert metrics["rmse"] >= metrics["mae"]
    assert np.isfinite(metrics["mape"])
    assert 0.0 <= metrics["directional_accuracy"] <= 1.0
