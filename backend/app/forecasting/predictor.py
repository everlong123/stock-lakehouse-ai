"""Prediction helper that loads a saved model and forecasts the next close."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.constants import LINEAR_REGRESSION_FEATURES, LSTM_FEATURE_COLUMNS
from app.core.exceptions import PredictionError
from app.forecasting.model_registry import load_model, load_registry_record, model_directory
from app.lakehouse.gold import GoldLayer


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

He thong Stock Lakehouse AI duoc phat trien cho muc dich:
- Nghien cuu hoc thuat ve tai chinh dinh luong
- Hoc tap ve xay dung he thong du lieu (Lakehouse architecture)
- Demo cac ky thuat ML/AI trong linh vuc chung khoan

Moi noi dung mang tinh THAM KHAO, KHONG phai loi khuyen dau tu.
"""


def predict_symbol(symbol: str, model_name: str, horizon: int = 5) -> dict[str, Any]:
    """Generate a next-close prediction series from the latest trained model."""
    model = load_model(symbol, model_name)
    registry = load_registry_record(symbol, model_name)
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
        "disclaimer": FORECAST_DISCLAIMER,
    }
