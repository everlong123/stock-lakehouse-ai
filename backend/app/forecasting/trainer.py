"""High-level training orchestrator used by the API and scripts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.constants import LINEAR_REGRESSION_FEATURES, LSTM_FEATURE_COLUMNS
from app.core.exceptions import ModelTrainingError
from app.core.logging_config import get_logger
from app.core.seeding import set_global_seed
from app.core.config import settings
from app.forecasting.arima import ARIMAForecastModel
from app.forecasting.linear_regression import LinearRegressionForecastModel
from app.forecasting.lstm import LSTMForecastModel
from app.forecasting.model_registry import MODEL_CLASSES, model_directory, save_registry_record
from app.forecasting.preprocessing import chronological_split
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)


def _prepare_supervised(frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    # Dedupe while preserving order — `close` already lives inside
    # `feature_cols` for Linear/LSTM, so appending it again would create
    # duplicate columns that blow up narwhals/polars validation later.
    needed: list[str] = []
    for col in feature_cols + ["target_close_next", "timestamp", "close"]:
        if col in frame.columns and col not in needed:
            needed.append(col)
    clean = frame[needed].dropna(subset=feature_cols + ["target_close_next"]).copy()
    if clean.empty:
        raise ModelTrainingError("No supervised rows remain after dropping indicator warmup and target NaNs.")
    return clean


def _truncate_to(frame: pd.DataFrame, end_date: Any) -> pd.DataFrame:
    """Return the rows of ``frame`` whose timestamp is at or before ``end_date``.

    The comparison is done on the timestamp column with everything
    timezone-naive, because Gold stores exchange-local session dates and
    mixing them with tz-aware boundaries would silently drop every row.
    """
    if "timestamp" not in frame.columns:
        raise ModelTrainingError("Cannot truncate: the frame has no 'timestamp' column.")

    stamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    if stamps.isna().all():
        raise ModelTrainingError("Cannot truncate: every 'timestamp' value is unparseable.")

    boundary = pd.to_datetime(end_date, errors="coerce", utc=True)
    if pd.isna(boundary):
        raise ModelTrainingError(f"Cannot truncate: {end_date!r} is not a valid date.")

    return frame.loc[stamps <= boundary]


def train_model(
    symbol: str,
    model_name: str,
    horizon: int = 1,
    extra_params: dict[str, Any] | None = None,
    end_date: Any | None = None,
    full_fit: bool = False,
) -> dict[str, Any]:
    """Train one model on Gold data using a chronological split.

    ``end_date`` truncates the training data to sessions at or before that
    timestamp. It is what makes a *rolling* (walk-forward) refit possible:
    a model trained on 2026-11-10 data and scored on the sessions after it
    is the honest way to measure a model that will be retrained every
    night, instead of training once on the whole history and scoring on a
    hold-out that the model has already seen the shape of.

    ``full_fit`` decides what the *shipped* model is trained on:

    * ``False`` (default) — the model is fitted on the 60% train slice of
      the chronological split, and the 20% hold-out is scored. This is the
      evaluation mode: the reported metrics describe a model that has
      never seen the hold-out.
    * ``True`` — the model is fitted on **100%** of the history up to
      ``end_date``, while the metrics still come from the same 60/20/20
      split. This is the production mode: the model that goes into the
      registry is the one that will actually forecast, and the metrics
      stay comparable across refits because they are always computed the
      same way.

    Keeping the metrics from the hold-out split in both modes is
    deliberate: the number on the dashboard has to mean the same thing
    before and after a refit, otherwise the historical accuracy series
    becomes meaningless.
    """
    set_global_seed(settings.random_seed)
    extra_params = extra_params or {}
    gold = GoldLayer().read(symbol)
    if gold.empty:
        raise ModelTrainingError(
            f"No Gold data for {symbol}. Run the lakehouse pipeline first "
            f"(POST /api/v1/pipeline/run or wait for auto-refresh on startup)."
        )

    if end_date is not None:
        gold = _truncate_to(gold, end_date)
        if gold.empty:
            raise ModelTrainingError(
                f"No Gold data for {symbol} at or before {end_date}."
            )

    model_name = model_name.lower()
    if model_name not in MODEL_CLASSES:
        # LSTM is lazy-loaded because importing torch on Windows sometimes
        # trips a DLL error (LoadLibrary failed). Lazy-load it here so the
        # /forecast/train endpoint works for LSTM too, matching load_model.
        if model_name == "lstm":
            from app.forecasting.model_registry import _lazy_load_lstm
            lstm_cls = _lazy_load_lstm()
            if lstm_cls is not None:
                MODEL_CLASSES["lstm"] = lstm_cls
    if model_name not in MODEL_CLASSES:
        raise ModelTrainingError(f"Unsupported model: {model_name}")

    if model_name == "arima":
        clean = gold.dropna(subset=["close"]).sort_values("timestamp")
        split = chronological_split(clean)
        model = ARIMAForecastModel(order=tuple(extra_params.get("order", settings.arima_order_tuple)))
        if full_fit:
            model.fit(clean, clean["close"])
        else:
            model.fit(split.train, split.train["close"])
        # The hold-out sessions are scored ONE STEP AHEAD: each prediction is
        # made before the session it predicts, and the session's actual value
        # is fed back in afterwards. A single multi-step forecast anchored at
        # the end of the training data would be a long-range projection, not
        # a one-step forecast, and the resulting error would say nothing
        # about the model's actual skill.
        metrics = model.evaluate(split.test, split.test["close"])
        feature_cols = ["close"]
        # The comparison frame holds the same one-step-ahead predictions the
        # metrics were computed on, so the chart and the MAE agree.
        aligned_pred = model.walk_forward(split.test)
        n = min(len(aligned_pred), len(split.test))
        comparison = pd.DataFrame(
            {
                "timestamp": split.test["timestamp"].tolist()[:n],
                "actual": split.test["close"].tolist()[:n],
                "predicted": aligned_pred.tolist()[:n],
            }
        )
    elif model_name == "lstm":
        feature_cols = [col for col in LSTM_FEATURE_COLUMNS if col in gold.columns]
        clean = _prepare_supervised(gold, feature_cols)
        split = chronological_split(clean)
        model = LSTMForecastModel(
            sequence_length=int(extra_params.get("sequence_length", settings.lstm_sequence_length)),
            hidden_size=int(extra_params.get("hidden_size", settings.lstm_hidden_size)),
            num_layers=int(extra_params.get("num_layers", settings.lstm_num_layers)),
            epochs=int(extra_params.get("epochs", settings.lstm_epochs)),
        )
        if full_fit:
            model.fit(clean[feature_cols], clean["target_close_next"])
        else:
            model.fit(split.train[feature_cols], split.train["target_close_next"], split.validation[feature_cols], split.validation["target_close_next"])
        metrics = model.evaluate(split.test[feature_cols], split.test["target_close_next"])
        predicted = model.predict(split.test[feature_cols])
        actual = split.test["target_close_next"].to_numpy()[model.sequence_length - 1 :]
        timestamps = split.test["timestamp"].to_numpy()[model.sequence_length - 1 :]
        n = min(len(predicted), len(actual), len(timestamps))
        comparison = pd.DataFrame(
            {
                "timestamp": list(timestamps[:n]),
                "actual": list(actual[:n]),
                "predicted": list(predicted[:n]),
            }
        )
    else:
        feature_cols = [col for col in LINEAR_REGRESSION_FEATURES if col in gold.columns]
        clean = _prepare_supervised(gold, feature_cols)
        split = chronological_split(clean)
        model = LinearRegressionForecastModel()
        if full_fit:
            model.fit(clean[feature_cols], clean["target_close_next"])
        else:
            model.fit(split.train[feature_cols], split.train["target_close_next"])
        metrics = model.evaluate(split.test[feature_cols], split.test["target_close_next"])
        predicted = model.predict(split.test[feature_cols])
        comparison = pd.DataFrame(
            {
                "timestamp": split.test["timestamp"].tolist(),
                "actual": split.test["target_close_next"].tolist(),
                "predicted": predicted.tolist(),
            }
        )

    directory = model_directory(symbol, model_name)
    model.save(directory)
    comparison_path = directory / "predictions.parquet"
    comparison.to_parquet(comparison_path, index=False)

    record = {
        "symbol": symbol.upper(),
        "model_name": model_name,
        "train_start": split.train["timestamp"].min(),
        "train_end": split.train["timestamp"].max(),
        "validation_start": split.validation["timestamp"].min(),
        "validation_end": split.validation["timestamp"].max(),
        "test_start": split.test["timestamp"].min(),
        "test_end": split.test["timestamp"].max(),
        "features": feature_cols,
        "parameters": {**model.metadata, "horizon": horizon, **extra_params},
        "fit_mode": "full" if full_fit else "holdout_split",
        "training_data_end": end_date.isoformat() if hasattr(end_date, "isoformat") else end_date,
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "mape": metrics["mape"],
        "directional_accuracy": metrics["directional_accuracy"],
        "model_path": str(directory),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Metrics are computed on a chronological hold-out split. They do not guarantee future performance.",
    }
    save_registry_record(symbol, model_name, record)
    logger.info("Trained %s for %s: %s", model_name, symbol, metrics)
    return {
        **record,
        "predictions": [
            {
                "timestamp": str(row.timestamp),
                "actual": float(row.actual),
                "predicted": float(row.predicted),
            }
            for row in comparison.itertuples(index=False)
        ],
    }
