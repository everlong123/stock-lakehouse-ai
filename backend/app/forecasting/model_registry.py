"""Filesystem model registry used even when MySQL is unavailable."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.forecasting.arima import ARIMAForecastModel
from app.forecasting.base import BaseForecastModel
from app.forecasting.linear_regression import LinearRegressionForecastModel

MODEL_CLASSES: dict[str, type[BaseForecastModel]] = {
    "linear_regression": LinearRegressionForecastModel,
    "arima": ARIMAForecastModel,
}

def _lazy_load_lstm():
    """Lazy load LSTM model to avoid PyTorch DLL issues on Windows."""
    try:
        from app.forecasting.lstm import LSTMForecastModel
        return LSTMForecastModel
    except OSError:
        return None


def model_directory(symbol: str, model_name: str) -> Path:
    # Query parameters must never become filesystem traversal paths, and
    # reading a missing model must not create empty registry directories.
    symbol = str(symbol).strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,31}", symbol):
        raise NotFoundError(f"Invalid stock symbol: {symbol!r}")
    if model_name not in ("linear_regression", "arima", "lstm"):
        raise NotFoundError(f"Unknown model: {model_name}")
    return settings.model_dir_path / symbol / model_name


def save_registry_record(symbol: str, model_name: str, record: dict[str, Any]) -> Path:
    directory = model_directory(symbol, model_name)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "registry.json"
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path


def load_registry_record(symbol: str, model_name: str) -> dict[str, Any]:
    path = model_directory(symbol, model_name) / "registry.json"
    if not path.exists():
        raise NotFoundError(f"No trained model found for {symbol} / {model_name}. Please train the model first.")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("status") == "blocked":
        for metric in ("mae", "rmse", "mape", "directional_accuracy"):
            record[metric] = None
        record["metrics_source"] = "unavailable_blocked_model"
    if record.get("fit_mode") == "full" and not record.get("evaluation_model_path"):
        for metric in ("mae", "rmse", "mape", "directional_accuracy"):
            record[metric] = None
        record["metrics_source"] = "unavailable_legacy_full_fit"
    return record


def load_model(symbol: str, model_name: str) -> BaseForecastModel:
    record = load_registry_record(symbol, model_name)
    if record.get("status") == "blocked":
        raise NotFoundError(record.get("blocked_reason") or "The model is blocked pending a data-quality review.")
    if model_name == "lstm":
        lstm_cls = _lazy_load_lstm()
        if lstm_cls is None:
            raise NotFoundError("LSTM model unavailable due to PyTorch initialization error on Windows.")
        MODEL_CLASSES["lstm"] = lstm_cls
    if model_name not in MODEL_CLASSES:
        raise NotFoundError(f"Unknown model: {model_name}")
    directory = model_directory(symbol, model_name)
    marker = directory / "registry.json"
    if not marker.exists():
        raise NotFoundError(f"No trained model found for {symbol} / {model_name}. Please train the model first.")
    return MODEL_CLASSES[model_name].load(directory)


def load_evaluation_model(symbol: str, model_name: str) -> BaseForecastModel:
    """Load the model scored out of sample, never a refit on those targets."""
    record = load_registry_record(symbol, model_name)
    if record.get("status") == "blocked":
        raise NotFoundError(record.get("blocked_reason") or "The model is blocked pending a data-quality review.")
    if model_name == "lstm":
        cls = _lazy_load_lstm()
        if cls is None:
            raise NotFoundError("LSTM evaluation model is unavailable.")
        MODEL_CLASSES[model_name] = cls
    if model_name not in MODEL_CLASSES:
        raise NotFoundError(f"Unknown model: {model_name}")
    directory = model_directory(symbol, model_name) / "evaluation"
    if record.get("evaluation_model_path") and directory.is_dir():
        return MODEL_CLASSES[model_name].load(directory)
    if record.get("fit_mode") == "full":
        raise NotFoundError("This legacy full-fit model has no independent evaluation model. Retrain before historical evaluation.")
    return load_model(symbol, model_name)


def list_trained_models(symbol: str) -> list[dict[str, Any]]:
    root = model_directory(symbol, "linear_regression").parent
    if not root.exists():
        return []
    records = []
    for child in root.iterdir():
        registry = child / "registry.json"
        if registry.exists():
            try:
                records.append(load_registry_record(symbol, child.name))
            except Exception:
                pass
    return records
