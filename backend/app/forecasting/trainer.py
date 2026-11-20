"""High-level training orchestrator used by the API and scripts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import shutil
from uuid import uuid4
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
from app.forecasting.evaluator import evaluate_forecast
from app.features.target_features import add_target_features
from app.lakehouse.gold import GoldLayer
from app.lakehouse.scale_repair import detect_scale_span, is_scale_contaminated

logger = get_logger(__name__)


def _reject_contaminated_history(symbol: str, gold: pd.DataFrame) -> None:
    """Refuse to train a model on a history that mixes price scales.

    WHY THIS EXISTS
    ---------------
    A reverse split changes a symbol's price scale: the provider publishes
    the pre-split price for the old sessions and the post-split price for
    the new ones, and the lakehouse stores both. The stored history is
    still REAL data - every row is a price the exchange printed - but a
    price-LEVEL model fitted across the break learns nothing, and its
    extrapolation can land anywhere, including below zero.

    The measured case (18/11/2026): ``SOXS`` - a leveraged inverse ETF -
    was published with a forecast of **-277.289.577** against a reference
    close of 58,77. Its stored history spans **7.193x** (the pre-split
    sessions carry prices around 191.160.000). The write path REFUSED to
    store that forecast, which is why no negative price reached the ledger,
    but the model was still trained, still sat in the registry, and would
    keep producing the same nonsense on every refit.

    The detector already exists - ``app.lakehouse.scale_repair`` - and it
    already classifies these symbols correctly (SOXS 7.193x, UVXY 1.376x,
    SQQQ 256x, while the healthy AAPL is 5,19x and NVDA 30,66x). What was
    missing is the CALL to it: nothing in the training path asked whether
    the history sits on one scale.

    WHY THE THRESHOLD IS THE SPAN, NOT THE LOCAL JUMP
    -----------------------------------------------
    ``is_scale_contaminated`` combines two checks: a local jump between
    neighbouring sessions, and the GLOBAL span between the early level and
    the late level. SOXS, SQQQ and SPXU have **zero** local jumps - their
    breaks are spread over years - so the span check is the one that
    catches them.

    WHY THE MODEL IS REFUSED RATHER THAN THE DATA BEING FIXED
    ----------------------------------------------------------
    Rescaling the stored history would publish prices the provider never
    printed, and this project stores only prices that can be traced back
    to a real exchange feed. So the fix is to refuse the model and say
    why, not to invent a repaired series.
    """
    span = detect_scale_span(gold, symbol=symbol)
    if not is_scale_contaminated(gold, symbol=symbol):
        return

    raise ModelTrainingError(
        f"{symbol.upper()} cannot be trained on this window: suspected scale discontinuity "
        f"(span {span:.2f}x; the detector also checks local jumps). A reverse split, "
        f"a provider unit change or an actual market jump requires investigation. "
        f"Verify the source, re-ingest inconsistent data, or explicitly select a "
        f"recent stable training window. No prices were altered."
    )


def _prepare_supervised(frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    # Dedupe while preserving order — `close` already lives inside
    # `feature_cols` for Linear/LSTM, so appending it again would create
    # duplicate columns that blow up narwhals/polars validation later.
    needed: list[str] = []
    for col in feature_cols + ["target_close_next", "target_timestamp_next", "timestamp", "close"]:
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

    * ``False`` (default) — the model is fitted on the configured train slice
      and its chronological hold-out is scored. This is the
      evaluation mode: the reported metrics describe a model that has
      never seen the hold-out.
    * ``True`` — the model is fitted on **100%** of the history up to
      ``end_date``, AFTER a separate evaluation model has been scored on
      the hold-out. This is the production mode: the model that goes into the
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

    history_sessions = extra_params.get("history_sessions")
    if history_sessions is not None:
        history_sessions = int(history_sessions)
        if history_sessions < 100:
            raise ModelTrainingError("history_sessions must be at least 100.")
        gold = gold.sort_values("timestamp").tail(history_sessions).copy()

    # Targets must be derived AFTER truncation: an existing last-row target
    # can otherwise contain the close of a session beyond end_date.
    gold = gold.sort_values("timestamp").reset_index(drop=True)
    gold = add_target_features(gold)
    gold["target_timestamp_next"] = gold["timestamp"].shift(-1)

    # A history that mixes price scales cannot train a price-level model.
    # The check runs BEFORE any fit, so a contaminated symbol never reaches
    # the registry and never produces a forecast.
    _reject_contaminated_history(symbol, gold)

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
        model.fit(split.train, split.train["close"])
        # Advance the state with the validation observations before the first
        # test forecast, keeping fitted parameters independent of the test.
        model.extend(split.validation["close"].to_numpy(dtype=float))
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
        model.fit(split.train[feature_cols], split.train["target_close_next"], split.validation[feature_cols], split.validation["target_close_next"])
        metrics = model.evaluate(split.test[feature_cols], split.test["target_close_next"])
        predicted = model.predict(split.test[feature_cols])
        actual = split.test["target_close_next"].to_numpy()[model.sequence_length - 1 :]
        timestamps = split.test["target_timestamp_next"].to_numpy()[model.sequence_length - 1 :]
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
        model.fit(split.train[feature_cols], split.train["target_close_next"])
        metrics = model.evaluate(split.test[feature_cols], split.test["target_close_next"])
        predicted = model.predict(split.test[feature_cols])
        comparison = pd.DataFrame(
            {
                "timestamp": split.test["target_timestamp_next"].tolist(),
                "actual": split.test["target_close_next"].tolist(),
                "predicted": predicted.tolist(),
            }
        )

    directory = model_directory(symbol, model_name)
    if (directory / "registry.json").is_file():
        archive = settings.data_root_path / "model_versions" / symbol.upper() / model_name / uuid4().hex
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(directory, archive)
    # Keep the independently evaluated model for historical charts/backfill.
    # The production refit must never be replayed as if it were out of sample.
    evaluation_directory = directory / "evaluation"
    model.save(evaluation_directory)
    fitted_through = split.validation["timestamp"].max() if model_name == "arima" else split.train["timestamp"].max()
    if full_fit:
        if model_name == "arima":
            model = ARIMAForecastModel(order=tuple(extra_params.get("order", settings.arima_order_tuple)))
            model.fit(clean, clean["close"])
        elif model_name == "lstm":
            evaluation_epochs = int(model.metadata.get("epochs_ran", settings.lstm_epochs))
            model = LSTMForecastModel(
                sequence_length=int(extra_params.get("sequence_length", settings.lstm_sequence_length)),
                hidden_size=int(extra_params.get("hidden_size", settings.lstm_hidden_size)),
                num_layers=int(extra_params.get("num_layers", settings.lstm_num_layers)),
                epochs=evaluation_epochs,
            )
            model.fit(clean[feature_cols], clean["target_close_next"])
        else:
            model = LinearRegressionForecastModel()
            model.fit(clean[feature_cols], clean["target_close_next"])
        fitted_through = clean["timestamp"].max()
    model.save(directory)
    comparison_path = directory / "predictions.parquet"
    comparison.to_parquet(comparison_path, index=False)
    reference_by_target = gold.set_index("timestamp")["close"].shift(1)
    naive_reference = reference_by_target.reindex(pd.to_datetime(comparison["timestamp"], utc=True)).to_numpy(dtype=float)
    naive_metrics = evaluate_forecast(comparison["actual"].to_numpy(dtype=float), naive_reference, naive_reference)

    record = {
        "symbol": symbol.upper(),
        "model_name": model_name,
        "model_version": uuid4().hex,
        "data_sha256": hashlib.sha256(pd.util.hash_pandas_object(clean, index=False).values.tobytes()).hexdigest(),
        "train_start": split.train["timestamp"].min(),
        "train_end": split.train["timestamp"].max(),
        "validation_start": split.validation["timestamp"].min(),
        "validation_end": split.validation["timestamp"].max(),
        "test_start": split.test["timestamp"].min(),
        "test_end": split.test["timestamp"].max(),
        "features": feature_cols,
        "parameters": {**model.metadata, "horizon": horizon, **extra_params},
        "fit_mode": "full" if full_fit else "holdout_split",
        "fitted_through": fitted_through,
        "training_data_end": gold["timestamp"].max(),
        "evaluation_model_path": str(evaluation_directory),
        "evaluation_fitted_through": split.validation["timestamp"].max() if model_name == "arima" else split.train["timestamp"].max(),
        "metrics_source": "independent_chronological_holdout",
        "test_target_start": comparison["timestamp"].min(),
        "test_target_end": comparison["timestamp"].max(),
        "test_points": len(comparison),
        "naive_baseline": naive_metrics,
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
