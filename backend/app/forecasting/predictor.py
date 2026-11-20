"""Prediction helper that loads a saved model and forecasts the next close."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.constants import LINEAR_REGRESSION_FEATURES, LSTM_FEATURE_COLUMNS
from app.core.exceptions import PredictionError
from app.core.logging_config import get_logger
from app.forecasting import light_forecast
from app.forecasting.model_registry import load_model, load_evaluation_model, load_registry_record, model_directory
from app.forecasting.multistep import holdout_history
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)


FORECAST_DISCLAIMER = """
CANH BAO QUAN TRONG - CHI Mang Tinh Tham Khao

1. DU BAO GIA CO PHIEU CO DO KHONG CHAC CHAN CAO
   - Ket qua du bao chi phan anh xu huong qua khu, khong phai du doan chan chan ve gia tuong lai.
   - Thi truong chung khoan bi anh huong boi nhieu yeu to khong the du doan (tin tuc, tam ly nha dau tu, bien dong vi mo).

2. KHONG PHAI KHUYEN NGHI DAU TU
   - He thong nay duoc xay dung cho muc dich NGHIEN CUU HOC THUAT.
   - Tuyet doi KHONG su dung ket qua du bao de quyet dinh mua/ban thuc te.

3. VE DO CHINH XAC CUA MO HINH
   - MAE/RMSE/MAPE chi do loi tren du lieu LICH SU, khong phan anh hieu suat tuong lai.
   - Cac mo hinh don gian (Linear Regression, ARIMA) co gioi han trong viec nam bat dong thai thi truong phuc tap.
   - LSTM cung chi la mo hinh thong ke, khong co "tri tue" ve thi truong.

4. BACKTEST KHONG DAM BAO LOI NHUAN THUC
   - Hieu suat qua khu trong backtest KHONG dam bao loi nhuan trong tuong lai.
   - Backtest khong tinh den chi phi giao dich thuc te, slippage, va dieu kien thi truong khac nhau.

5. NGUON GOC DU LIEU
   - Du lieu duoc lay tu cac nguon cong khai, co the co do tre hoac sai sot.
   - Khong co bao dam ve tinh chinh xac hoan toan cua du lieu.

Nguoi dung tu chiu trach nhiem ve moi quyet dinh dau tu cua minh.
"""


RISK_ASSESSMENT_DISCLAIMER = """
DANH GIA RUI RO - CHI Mang Tinh Tham Khao

Chi bao rui ro (VaR, drawdown, Sharpe ratio) duoc tinh toan tu du lieu lich su
voi cac gia dinh ve phan phoi loi nhuan. Trong thuc te:
- Phan phoi loi nhuan thi truong thuong co "duoi beo" (fat tails), dan den danh gia rui ro thap hon thuc te.
- Su kien "thien nga den" co the gay ra ton that lon hon nhieu so voi du doan.
- Correlation giua cac tai san thay doi trong thoi ky khu hoang.

Day la cong cu phan tich, khong phai tu van tai chinh chuyen nghiep.
"""


GENERAL_DISCLAIMER = """
MUC DICH SU DUNG

StockVision AI ho tro:
- Tra cuu du lieu va phan tich thi truong chung khoan
- Du bao gia bang cac mo hinh thong ke va hoc may
- Danh gia chien luoc tren du lieu lich su

Moi noi dung mang tinh THAM KHAO, KHONG phai loi khuyen dau tu.
"""


def _arima_history(
    model: Any,
    gold: pd.DataFrame,
    registry: dict[str, Any],
    limit: int = 120,
) -> list[dict[str, Any]]:
    """One-step-ahead predictions over the hold-out sessions, for the chart.

    The model is re-fitted on the training split and then walked forward
    over the hold-out sessions, so the curve shows the same quantity the
    MAE was measured on: what the model said BEFORE each session.

    This is expensive - the walk-forward updates the state-space model once
    per session - so it is capped at the most recent `limit` sessions.
    """
    test_start = _arima_test_start(registry)
    if test_start is None:
        return []
    fitted = registry.get("evaluation_fitted_through") or registry.get("train_end")
    if fitted:
        context = gold[(gold["timestamp"] > pd.to_datetime(fitted, utc=True)) & (gold["timestamp"] < test_start)]
        if not context.empty:
            model.extend(context["close"].to_numpy(dtype=float))
    holdout = gold[gold["timestamp"] >= test_start]
    if holdout.empty:
        return []
    # Cap the walk-forward to the most recent sessions.
    if len(holdout) > limit:
        context = holdout.iloc[:-limit]
        model.extend(context["close"].to_numpy(dtype=float))
        holdout = holdout.iloc[-limit:]

    try:
        predictions = model.walk_forward(holdout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build the ARIMA hold-out history: %s", exc)
        return []

    actual = pd.to_numeric(holdout["close"], errors="coerce").to_numpy(dtype=float)
    previous = pd.to_numeric(gold["close"], errors="coerce").shift(1).loc[holdout.index].to_numpy(dtype=float)
    timestamps = holdout["timestamp"].to_numpy()
    n = min(len(predictions), len(actual))
    points: list[dict[str, Any]] = []
    for i in range(n):
        if not np.isfinite(predictions[i]):
            continue
        points.append(
            {
                "timestamp": str(timestamps[i]),
                "actual": float(actual[i]),
                "predicted": float(predictions[i]),
                "reference_close": float(previous[i]),
            }
        )
    return points


def _arima_test_start(registry: dict[str, Any]) -> pd.Timestamp | None:
    """The first session of the hold-out split the model was scored on."""
    value = registry.get("test_target_start") or registry.get("test_start")
    if not value:
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
    except Exception:  # noqa: BLE001
        return None
    return None if pd.isna(ts) else ts


def _holdout_window(registry: dict[str, Any]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Read the train/test boundaries the trainer recorded.

    The registry stores them as ISO strings. They are returned as tz-aware
    timestamps so they can be compared against the Gold timestamps.
    """
    def _parse(value: Any) -> pd.Timestamp | None:
        if not value:
            return None
        try:
            ts = pd.to_datetime(value, utc=True)
        except Exception:  # noqa: BLE001
            return None
        return None if pd.isna(ts) else ts

    return (
        _parse(registry.get("test_target_start") or registry.get("test_start")),
        _parse(registry.get("test_target_end") or registry.get("test_end")),
    )


def predict_symbol(symbol: str, model_name: str, horizon: int = 5) -> dict[str, Any]:
    """Generate a next-close prediction series from the latest trained model.

    WHY THIS IS BUILT THE WAY IT IS
    --------------------------------
    The chart has two regions and they are built from different sources:

    * **History** - the model's own estimate of what it WOULD have said for
      sessions that already happened. This is recomputed from the current
      Gold data on every call, so it reflects any restatement the provider
      has published since the model was trained.
    * **Forecast** - `horizon` sessions in the FUTURE, produced by the
      recursive forecaster in `app.forecasting.multistep`.

    The previous implementation had three defects that made the chart look
    frozen:

    1. It plotted `model.predict(frame)` against the actual close of the
       SAME session, which is a one-session shift - the prediction is for
       session *t+1*, not *t*.
    2. It then REPLACED the whole series with the `predictions.parquet`
       written at training time. That file belongs to whichever symbol was
       trained last, so switching symbols left the old symbol's curve on
       screen. It also froze the history at training time, so a provider
       restatement never reached the chart.
    3. `horizon` was ignored for the feature-based models, so the chart
       never showed a future session at all.

    All three are fixed below: the history is recomputed and aligned, the
    forecast is generated for the future, and the stored parquet is used
    only as a fallback when the live Gold data cannot serve the request.
    """
    registry = load_registry_record(symbol, model_name)
    try:
        model = load_evaluation_model(symbol, model_name)
    except Exception as exc:
        logger.warning("No independent historical model for %s/%s: %s", symbol, model_name, exc)
        model = None
    gold = GoldLayer().read(symbol)
    if gold.empty:
        # Fallback: build Gold from MarketService when Bronze is empty
        from app.features.feature_engineering import build_gold_features
        from app.services.market_service import MarketService
        try:
            base = MarketService().get_history(symbol)
            gold = build_gold_features(base)
        except Exception as exc:
            raise PredictionError(f"No Gold data available for {symbol}. ({exc})")
    if gold.empty:
        raise PredictionError(f"No Gold data available for {symbol}.")
    gold = gold.sort_values("timestamp")

    if model_name == "arima":
        # ARIMA is natively multi-step, so it forecasts the future directly.
        #
        # BUT the model was fitted on the TRAINING split, which ends long
        # before the latest session. A forecast taken straight from that
        # state is anchored at the stale training price, so it has to be
        # extended with every session published since the model was
        # trained - otherwise the forecast is wrong by the whole gap.
        gold_sorted = gold.sort_values("timestamp").reset_index(drop=True)
        gold_sorted["timestamp"] = pd.to_datetime(gold_sorted["timestamp"], utc=True)

        # The hold-out history is computed FIRST, while the model is still
        # in the state it was trained in - the same state the trainer scored
        # it in. It has to be walked over the FULL hold-out split (the
        # state-space update is sequential), and only the most recent
        # sessions are kept for the chart.
        history = _arima_history(model, gold_sorted, registry) if model is not None else []

        # The forward projection is produced by the SHARED light path, so
        # the chart and the nightly batch cannot disagree about what the
        # model predicted. See `app/forecasting/light_forecast.py`.
        future = light_forecast.future_series(symbol, model_name, gold_sorted, horizon=horizon)
    else:
        # The feature-based models are one-step models, so the future needs
        # the recursive forecaster, and the history needs the one-session
        # alignment shift.
        #
        # The history is restricted to the SAME chronological hold-out split
        # the metrics were computed on, so the curve on the chart and the
        # MAE shown above it describe the same rows. The split boundaries
        # are read back from the registry record the trainer wrote.
        window = _holdout_window(registry)
        history = holdout_history(model, gold, model_name, window=window) if model is not None else []
        # The forward projection comes from the SAME shared routine the
        # nightly batch uses - one implementation, two callers, no chance
        # of the chart and the batch reporting different numbers.
        future = light_forecast.future_series(symbol, model_name, gold, horizon=horizon)

    forecast_reason = None
    if future:
        lag = light_forecast.staleness_days(gold, light_forecast.session_date(future[0]["timestamp"], symbol))
        if lag is not None and lag > 0:
            forecast_reason = f"Input data is {lag} trading session(s) behind. Refresh before forecasting."
            future = []
    points: list[dict[str, Any]] = [*history, *future]

    # Fallback: if the live path produced nothing (no usable Gold rows),
    # serve the parquet written at training time so the chart is not empty.
    if not points and model is not None:
        directory = model_directory(symbol, model_name)
        stored = directory / "predictions.parquet"
        if stored.exists():
            stored_frame = pd.read_parquet(stored)
            points = [
                {
                    "timestamp": str(row.timestamp),
                    "actual": float(row.actual) if pd.notna(row.actual) else None,
                    "predicted": float(row.predicted),
                }
                for row in stored_frame.itertuples(index=False)
            ]

    # The metrics must describe the curve the user is looking at.
    #
    # The registry holds the metrics measured at TRAINING time, on the
    # hold-out split as it was then. The chart now shows the hold-out
    # history PLUS every session published since, because those are
    # honest hold-out rows too - the model was fitted on rows that all
    # predate them.
    #
    # Reporting the training-time metrics next to a longer curve would
    # understate the error, so the metrics are recomputed over exactly the
    # history that is plotted. If that cannot be done, the registry values
    # are returned unchanged and the response says so.
    metrics: dict[str, Any] = {
        "mae": registry.get("mae"),
        "rmse": registry.get("rmse"),
        "mape": registry.get("mape"),
        "directional_accuracy": registry.get("directional_accuracy"),
    }
    metrics_source = "training_split"
    if model is None:
        metrics = {key: None for key in metrics}
        metrics_source = "unavailable_independent_evaluation"
    if history:
        recomputed = _score_history(history)
        if recomputed is not None:
            metrics = recomputed
            metrics_source = "chart_holdout"

    return {
        "symbol": symbol.upper(),
        "model_name": model_name,
        "horizon": horizon,
        "metrics": metrics,
        "metrics_source": metrics_source,
        "parameters": registry.get("parameters"),
        "forecast_available": bool(future),
        "forecast_reason": forecast_reason,
        "predictions": points,
        "disclaimer": FORECAST_DISCLAIMER,
    }


def _score_history(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Recompute the metric set over exactly the points that are plotted."""
    import numpy as np

    actual = np.array([p["actual"] for p in history if p.get("actual") is not None], dtype=float)
    predicted = np.array([p["predicted"] for p in history if p.get("actual") is not None], dtype=float)
    if actual.size < 2:
        return None
    try:
        from app.forecasting.evaluator import evaluate_forecast

        # The previous close is the close before the session being scored.
        observed = [p for p in history if p.get("actual") is not None]
        previous = np.array([
            p.get("reference_close", actual[i - 1] if i else np.nan)
            for i, p in enumerate(observed)
        ], dtype=float)
        scored = evaluate_forecast(actual, predicted, previous)
        return {
            "mae": scored["mae"],
            "rmse": scored["rmse"],
            "mape": scored["mape"],
            "directional_accuracy": scored["directional_accuracy"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not rescore the hold-out history: %s", exc)
        return None
