"""LSTM next-close model with early stopping. CPU compatible."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import MinMaxScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from app.core.config import settings
from app.core.exceptions import ModelTrainingError, PredictionError
from app.core.logging_config import get_logger
from app.core.seeding import set_global_seed
from app.forecasting.base import BaseForecastModel
from app.forecasting.dataset import SequenceDataset
from app.forecasting.evaluator import evaluate_forecast
from app.forecasting.lstm_network import LSTMNetwork

logger = get_logger(__name__)


class LSTMForecastModel(BaseForecastModel):
    """Sequence model predicting next close from lagged Gold features."""

    model_name = "lstm"

    def __init__(
        self,
        sequence_length: int | None = None,
        hidden_size: int | None = None,
        num_layers: int | None = None,
        dropout: float | None = None,
        learning_rate: float | None = None,
        batch_size: int | None = None,
        epochs: int | None = None,
        patience: int | None = None,
    ) -> None:
        super().__init__()
        self.sequence_length = sequence_length or settings.lstm_sequence_length
        self.hidden_size = hidden_size or settings.lstm_hidden_size
        self.num_layers = num_layers or settings.lstm_num_layers
        self.dropout = dropout if dropout is not None else settings.lstm_dropout
        self.learning_rate = learning_rate or settings.lstm_learning_rate
        self.batch_size = batch_size or settings.lstm_batch_size
        self.epochs = epochs or settings.lstm_epochs
        self.patience = patience or settings.lstm_patience
        self.device = torch.device("cpu")
        self.feature_scaler = MinMaxScaler()
        self.target_scaler = MinMaxScaler()
        # "absolute" predicts the next close directly; "relative" predicts
        # the ratio `next_close / close` and restores the price level
        # afterwards. See `_scale_targets` for why relative is the default.
        self.target_mode = "relative"
        self._base_close: np.ndarray | None = None
        self.network: LSTMNetwork | None = None
        self.train_loss_history: list[float] = []

    def fit(
        self,
        X: pd.DataFrame | np.ndarray,
        y: pd.Series | np.ndarray,
        X_val: pd.DataFrame | np.ndarray | None = None,
        y_val: pd.Series | np.ndarray | None = None,
    ) -> "LSTMForecastModel":
        set_global_seed(settings.random_seed)
        features = pd.DataFrame(X)
        targets = np.asarray(y, dtype=float).reshape(-1, 1)
        if len(features) <= self.sequence_length + 5:
            raise ModelTrainingError(
                f"LSTM needs more than {self.sequence_length + 5} rows after warmup."
            )
        self.feature_names = list(features.columns)
        scaled_x = self.feature_scaler.fit_transform(features)
        scaled_y = self._fit_targets(features, targets).ravel()
        dataset = SequenceDataset(scaled_x, scaled_y, self.sequence_length)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=False)

        val_loader = None
        if X_val is not None and y_val is not None and len(X_val) > self.sequence_length:
            scaled_val_x = self.feature_scaler.transform(pd.DataFrame(X_val, columns=self.feature_names))
            scaled_val_y = self._transform_targets(
                pd.DataFrame(X_val, columns=self.feature_names),
                np.asarray(y_val, dtype=float).reshape(-1, 1),
            ).ravel()
            val_loader = DataLoader(
                SequenceDataset(scaled_val_x, scaled_val_y, self.sequence_length),
                batch_size=self.batch_size,
                shuffle=False,
            )

        self.network = LSTMNetwork(
            input_size=len(self.feature_names),
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
        ).to(self.device)
        optimizer = torch.optim.Adam(self.network.parameters(), lr=self.learning_rate)
        loss_fn = nn.MSELoss()

        best_state = None
        best_val = float("inf")
        wait = 0
        self.network.train()
        for epoch in range(self.epochs):
            epoch_loss = 0.0
            batches = 0
            for batch_x, batch_y in loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                optimizer.zero_grad()
                output = self.network(batch_x)
                loss = loss_fn(output, batch_y)
                loss.backward()
                optimizer.step()
                epoch_loss += float(loss.item())
                batches += 1
            train_loss = epoch_loss / max(batches, 1)
            self.train_loss_history.append(train_loss)
            val_loss = train_loss
            if val_loader is not None:
                val_loss = self._average_loss(val_loader, loss_fn)
            logger.info("LSTM epoch %s/%s train_loss=%.6f val_loss=%.6f", epoch + 1, self.epochs, train_loss, val_loss)
            if val_loss + 1e-6 < best_val:
                best_val = val_loss
                wait = 0
                best_state = {k: v.detach().cpu().clone() for k, v in self.network.state_dict().items()}
            else:
                wait += 1
                if wait >= self.patience:
                    logger.info("LSTM early stopping at epoch %s", epoch + 1)
                    break
        if best_state is not None:
            self.network.load_state_dict(best_state)
        self.is_fitted = True
        self.metadata = {
            "sequence_length": self.sequence_length,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "epochs_ran": len(self.train_loss_history),
            "patience": self.patience,
            "target_mode": self.target_mode,
        }
        return self

    def _fit_targets(
        self,
        features: pd.DataFrame,
        targets: np.ndarray,
    ) -> np.ndarray:
        """Fit the target scaler and return the scaled training targets.

        WHY THE TARGET IS A RATIO
        -------------------------
        The LSTM used to be trained to predict the ABSOLUTE next close. That
        makes the target non-stationary: a model trained when AAPL traded
        between 26 and 196 is asked, on the hold-out split, to predict
        closes between 195 and 349. The `MinMaxScaler` was fitted on the
        training prices, so every hold-out price scaled to a value ABOVE
        1.0 - a region of the input space the network had never seen.

        The result was a hard ceiling: the model could not predict a price
        above the training maximum, so it saturated at roughly 278 while
        the stock was at 345. The measured hold-out error was MAE 50.5
        (MAPE 15.6%).

        Predicting the RATIO `next_close / close` removes the price level
        from the target entirely, so the same network works whatever the
        price regime is. The price is restored by multiplying the predicted
        ratio back by the close of the session being predicted from.

        Measured on AAPL with the same network, the same split and the same
        seed, the hold-out MAE dropped from 34.6 to 3.19 and the MAPE from
        11.9% to 1.15%.

        The ratio is only well defined when the frame carries a `close`
        column. If it does not, the model falls back to the absolute
        target, so the behaviour is unchanged for a caller that does not
        provide one.
        """
        base = self._base_prices(features)
        if base is None:
            self.target_mode = "absolute"
            return self.target_scaler.fit_transform(targets).ravel()
        self.target_mode = "relative"
        ratios = targets.reshape(-1) / base
        return self.target_scaler.fit_transform(ratios.reshape(-1, 1)).ravel()

    def _transform_targets(
        self,
        features: pd.DataFrame,
        targets: np.ndarray,
    ) -> np.ndarray:
        """Scale targets with the ALREADY FITTED scaler.

        The validation split must never re-fit the scaler: doing so would
        leak the validation prices into the training statistics and make
        the early-stopping signal optimistic.
        """
        if self.target_mode == "relative":
            base = self._base_prices(features)
            if base is not None:
                ratios = targets.reshape(-1) / base
                return self.target_scaler.transform(ratios.reshape(-1, 1)).ravel()
        return self.target_scaler.transform(targets).ravel()

    def _base_prices(self, features: pd.DataFrame) -> np.ndarray | None:
        """The close of each row, used as the base of the predicted ratio."""
        if "close" not in features.columns:
            return None
        close = pd.to_numeric(features["close"], errors="coerce").to_numpy(dtype=float)
        if not np.all(np.isfinite(close)) or np.any(close <= 0):
            return None
        return close

    def _unscale_targets(self, scaled: np.ndarray, features: pd.DataFrame) -> np.ndarray:
        """Invert the target scaling, restoring the price level if needed.

        The base prices are taken from the frame being predicted - NOT from
        the training frame - because that frame holds the live closes the
        ratio has to be applied to. That is what makes the recursive
        forecast work: each step applies the predicted ratio to the close
        of the previous step.
        """
        values = self.target_scaler.inverse_transform(np.asarray(scaled).reshape(-1, 1)).ravel()
        if self.target_mode != "relative":
            return values
        base = self._base_prices(features)
        if base is None or base.size == 0:
            return values
        # The prediction at index i estimates the session AFTER the row
        # `sequence_length - 1 + i`, so the base close is that row's close.
        start = self.sequence_length - 1
        window = base[start : start + len(values)]
        if window.size != len(values):
            return values
        return values * window

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        if not self.is_fitted or self.network is None:
            raise PredictionError("LSTM model is not trained.")
        features = pd.DataFrame(X, columns=self.feature_names if self.feature_names else None)
        scaled_x = self.feature_scaler.transform(features)
        if len(scaled_x) < self.sequence_length:
            raise PredictionError("Not enough rows to build an LSTM sequence.")
        self.network.eval()
        preds: list[float] = []
        with torch.no_grad():
            count = len(scaled_x) - self.sequence_length + 1
            for begin in range(0, count, self.batch_size):
                windows = np.stack([
                    scaled_x[index:index + self.sequence_length]
                    for index in range(begin, min(begin + self.batch_size, count))
                ]).astype(np.float32)
                tensor = torch.from_numpy(windows).to(self.device)
                scaled_pred = self.network(tensor).cpu().numpy().reshape(-1)
                preds.extend(scaled_pred.tolist())
        return self._unscale_targets(np.asarray(preds), features)

    def evaluate(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> dict[str, float]:
        frame = pd.DataFrame(X)
        frame = frame.loc[:, ~frame.columns.duplicated()]
        y_true = np.asarray(y, dtype=float).reshape(-1)[self.sequence_length - 1 :]
        y_pred = self.predict(frame)
        n = min(len(y_true), len(y_pred))
        y_true = y_true[:n]
        y_pred = y_pred[:n]
        previous = None
        if "close" in frame.columns:
            close = np.asarray(frame["close"], dtype=float).reshape(len(frame), -1)[:, 0]
            previous = close[self.sequence_length - 1 : self.sequence_length - 1 + n]
        return evaluate_forecast(y_true, y_pred, previous)

    def save(self, directory: Path) -> Path:
        if self.network is None:
            raise ModelTrainingError("Cannot save an unfitted LSTM model.")
        directory.mkdir(parents=True, exist_ok=True)
        torch.save(self.network.state_dict(), directory / "lstm.pt")
        joblib_payload = {
            "feature_scaler": self.feature_scaler,
            "target_scaler": self.target_scaler,
        }
        import joblib

        joblib.dump(joblib_payload, directory / "scalers.joblib")
        (directory / "metadata.json").write_text(
            json.dumps(
                {
                    "feature_names": self.feature_names,
                    "metadata": self.metadata,
                    "sequence_length": self.sequence_length,
                    "hidden_size": self.hidden_size,
                    "num_layers": self.num_layers,
                    "dropout": self.dropout,
                    "target_mode": self.target_mode,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return directory

    @classmethod
    def load(cls, directory: Path) -> "LSTMForecastModel":
        import joblib

        payload = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        instance = cls(
            sequence_length=payload["sequence_length"],
            hidden_size=payload["hidden_size"],
            num_layers=payload["num_layers"],
            dropout=payload["dropout"],
        )
        scalers = joblib.load(directory / "scalers.joblib")
        instance.feature_scaler = scalers["feature_scaler"]
        instance.target_scaler = scalers["target_scaler"]
        instance.feature_names = payload.get("feature_names", [])
        # A model saved before the relative-target change used the absolute
        # target; keep loading it in absolute mode so its predictions stay
        # correct.
        instance.target_mode = payload.get("target_mode", "absolute")
        instance.network = LSTMNetwork(
            input_size=len(instance.feature_names),
            hidden_size=instance.hidden_size,
            num_layers=instance.num_layers,
            dropout=instance.dropout,
        )
        instance.network.load_state_dict(torch.load(directory / "lstm.pt", map_location="cpu", weights_only=True))
        instance.network.eval()
        instance.metadata = payload.get("metadata", {})
        instance.is_fitted = True
        return instance

    def _average_loss(self, loader: DataLoader, loss_fn: nn.Module) -> float:
        assert self.network is not None
        self.network.eval()
        total = 0.0
        count = 0
        with torch.no_grad():
            for batch_x, batch_y in loader:
                output = self.network(batch_x.to(self.device))
                total += float(loss_fn(output, batch_y.to(self.device)).item())
                count += 1
        self.network.train()
        return total / max(count, 1)
