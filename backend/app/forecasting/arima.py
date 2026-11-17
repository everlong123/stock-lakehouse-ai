"""ARIMA close-price forecast using statsmodels."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA, ARIMAResults

from app.core.config import settings
from app.core.exceptions import ModelTrainingError, PredictionError
from app.core.logging_config import get_logger
from app.forecasting.base import BaseForecastModel
from app.forecasting.evaluator import evaluate_forecast

logger = get_logger(__name__)


class ARIMAForecastModel(BaseForecastModel):
    """Univariate ARIMA on the close series. Order is configurable."""

    model_name = "arima"

    def __init__(self, order: tuple[int, int, int] | None = None) -> None:
        super().__init__()
        self.order = order or settings.arima_order_tuple
        self.result: ARIMAResults | None = None
        self.history: np.ndarray = np.array([])

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> "ARIMAForecastModel":
        target = np.asarray(y, dtype=float)
        if len(target) < 20:
            raise ModelTrainingError("ARIMA needs at least 20 close observations.")
        try:
            model = ARIMA(target, order=self.order)
            self.result = model.fit()
        except Exception as exc:
            raise ModelTrainingError(f"ARIMA fitting failed for order={self.order}: {exc}") from exc
        self.history = target
        self.is_fitted = True
        self.feature_names = ["close"]
        self.metadata = {"order": list(self.order), "n_samples": int(len(target))}
        logger.info("ARIMA fitted with order=%s on %s observations", self.order, len(target))
        return self

    def predict(self, X: pd.DataFrame | np.ndarray | int) -> np.ndarray:
        """Forecast the next `horizon` sessions from the model's current state.

        `X` may be an integer horizon, or the frame of sessions to score.

        THE FORECAST IS ANCHORED AT THE END OF THE FITTED SERIES. If the
        model was fitted on the training split but more sessions have been
        published since, call `extend()` first - otherwise the forecast
        starts from a stale price and every value is wrong by that gap.
        """
        if not self.is_fitted or self.result is None:
            raise PredictionError("ARIMA model is not trained.")
        horizon = len(X) if not isinstance(X, int) else int(X)
        forecast = self.result.forecast(steps=horizon)
        return np.asarray(forecast, dtype=float)

    def extend(self, observations: np.ndarray | list[float]) -> "ARIMAForecastModel":
        """Append new observations to the fitted series without refitting.

        The model keeps its fitted parameters but learns the new observations
        through the state-space update, which is how a live model would
        ingest the sessions published since it was trained.
        """
        if self.result is None:
            raise PredictionError("ARIMA model is not trained.")
        new_values = np.asarray(observations, dtype=float).reshape(-1)
        if new_values.size == 0:
            return self
        try:
            self.result = self.result.append(new_values, refit=False)
        except Exception as exc:  # noqa: BLE001
            raise ModelTrainingError(f"Could not extend the ARIMA series: {exc}") from exc
        self.history = np.concatenate([self.history, new_values])
        return self

    def walk_forward(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """One-step-ahead predictions for each session in `X`.

        The metric that matters for a forecaster is "what did it say BEFORE
        the session happened?", so each prediction is made from the model
        state that existed before that session, and the session's actual
        value is fed back in afterwards.

        The previous implementation called `result.forecast(steps=len(X))`
        once, which produces a MULTI-step forecast anchored at the end of
        the TRAINING data. Comparing that against the test sessions scored
        a long-range projection as if it were a one-step forecast, which
        made the error enormous and completely unrelated to the model's
        actual skill.
        """
        if self.result is None:
            raise PredictionError("ARIMA model is not trained.")
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        if "close" not in frame.columns:
            raise PredictionError("ARIMA walk-forward needs a close column.")

        actual = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
        state = self.result
        predictions: list[float] = []
        for value in actual:
            if not np.isfinite(value):
                predictions.append(np.nan)
                continue
            try:
                forecast = np.asarray(state.forecast(steps=1), dtype=float).reshape(-1)[0]
                state = state.append(np.array([value]), refit=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ARIMA walk-forward stopped early: %s", exc)
                break
            predictions.append(float(forecast))
        return np.asarray(predictions, dtype=float)

    def in_sample_predict(self) -> np.ndarray:
        if self.result is None:
            raise PredictionError("ARIMA model is not trained.")
        return np.asarray(self.result.fittedvalues, dtype=float)

    def evaluate(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> dict[str, float]:
        """Score the model one step ahead on the hold-out sessions."""
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        y_true = np.asarray(y, dtype=float).reshape(-1)
        y_pred = self.walk_forward(frame)
        n = min(len(y_true), len(y_pred))
        if n == 0:
            raise ModelTrainingError("ARIMA evaluation received no usable rows.")
        y_true = y_true[:n]
        y_pred = y_pred[:n]
        previous = None
        if "close" in frame.columns:
            close = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
            # The directional accuracy compares the direction of the
            # forecast with the direction of the ACTUAL move. The move is
            # measured against the close of the PREVIOUS session.
            #
            # WHY THIS MATTERS: this used to be `close[:n]`, the close of
            # the very session being predicted. The actual move from that
            # close to the actual value is then the target itself, so
            # `sign(actual - close)` was zero for every row - the metric
            # could only ever be 0, and the ARIMA row of the comparison
            # table showed a directional accuracy of exactly 0.00.
            #
            # The previous session's close is the close of the session
            # BEFORE the one being predicted, so it is `close` shifted by
            # one. The first row has no predecessor inside the hold-out
            # frame, so it is dropped.
            shifted = np.concatenate([[np.nan], close[:-1]])
            usable = np.isfinite(shifted[:n])
            if usable.sum() >= 2:
                previous = shifted[:n][usable]
                y_true = y_true[usable]
                y_pred = y_pred[usable]
        return evaluate_forecast(y_true, y_pred, previous)

    def save(self, directory: Path) -> Path:
        if self.result is None:
            raise ModelTrainingError("Cannot save an unfitted ARIMA model.")
        directory.mkdir(parents=True, exist_ok=True)
        self.result.save(str(directory / "arima_result.pkl"))
        np.save(directory / "history.npy", self.history)
        (directory / "metadata.json").write_text(
            json.dumps({"order": list(self.order), "metadata": self.metadata}, indent=2),
            encoding="utf-8",
        )
        return directory

    @classmethod
    def load(cls, directory: Path) -> "ARIMAForecastModel":
        payload = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        instance = cls(order=tuple(payload.get("order", [5, 1, 0])))
        instance.result = ARIMAResults.load(str(directory / "arima_result.pkl"))
        instance.history = np.load(directory / "history.npy")
        instance.metadata = payload.get("metadata", {})
        instance.is_fitted = True
        instance.feature_names = ["close"]
        return instance
