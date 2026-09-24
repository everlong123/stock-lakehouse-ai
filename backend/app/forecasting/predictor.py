"""Prediction helper that loads a saved model and forecasts the next close."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import LINEAR_REGRESSION_FEATURES, LSTM_FEATURE_COLUMNS
from app.core.exceptions import PredictionError
from app.forecasting.model_registry import load_model, load_registry_record, model_directory
from app.lakehouse.gold import GoldLayer


def predict_symbol(symbol: str, model_name: str, horizon: int = 5) -> dict[str, Any]:
    """Generate a next-close prediction series from the latest trained model."""
    model = load_model(symbol, model_name)
    registry = load_registry_record(symbol, model_name)
    gold = GoldLayer().read(symbol)
    if gold.empty:
        raise PredictionError(f"No Gold data available for {symbol}.")
    gold = gold.sort_values("timestamp")

    if model_name == "arima":
        predicted = model.predict(list(range(horizon)))
        last_ts = pd.to_datetime(gold["timestamp"].iloc[-1])
        freq = pd.infer_freq(gold["timestamp"]) or "B"
        future_index = pd.date_range(last_ts, periods=horizon + 1, freq=freq)[1:]
        points = [
            {"timestamp": str(ts), "actual": None, "predicted": float(value)}
            for ts, value in zip(future_index, predicted)
        ]
    elif model_name == "lstm":
        cols = [col for col in LSTM_FEATURE_COLUMNS if col in gold.columns]
        frame = gold.dropna(subset=cols)
        predicted_all = model.predict(frame[cols])
        actual = frame["close"].to_numpy()[model.sequence_length - 1 :]  # type: ignore[attr-defined]
        timestamps = frame["timestamp"].to_numpy()[model.sequence_length - 1 :]
        n = min(len(predicted_all), len(actual), len(timestamps))
        points = [
            {
                "timestamp": str(timestamps[i]),
                "actual": float(actual[i]),
                "predicted": float(predicted_all[i]),
            }
            for i in range(max(0, n - 120), n)
        ]
    else:
        cols = [col for col in LINEAR_REGRESSION_FEATURES if col in gold.columns]
        frame = gold.dropna(subset=cols)
        predicted_all = model.predict(frame[cols])
        actual = frame["close"].to_numpy()
        timestamps = frame["timestamp"].to_numpy()
        n = min(len(predicted_all), len(actual))
        points = [
            {
                "timestamp": str(timestamps[i]),
                "actual": float(actual[i]),
                "predicted": float(predicted_all[i]),
            }
            for i in range(max(0, n - 120), n)
        ]

    directory = model_directory(symbol, model_name)
    stored = directory / "predictions.parquet"
    if stored.exists() and model_name != "arima":
        stored_frame = pd.read_parquet(stored)
        points = [
            {
                "timestamp": str(row.timestamp),
                "actual": float(row.actual) if pd.notna(row.actual) else None,
                "predicted": float(row.predicted),
            }
            for row in stored_frame.itertuples(index=False)
        ]

    return {
        "symbol": symbol.upper(),
        "model_name": model_name,
        "horizon": horizon,
        "metrics": {
            "mae": registry.get("mae"),
            "rmse": registry.get("rmse"),
            "mape": registry.get("mape"),
            "directional_accuracy": registry.get("directional_accuracy"),
        },
        "parameters": registry.get("parameters"),
        "predictions": points,
        "disclaimer": "Forecasts are experimental research outputs, not investment advice.",
    }
