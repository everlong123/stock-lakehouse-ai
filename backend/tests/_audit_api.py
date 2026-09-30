"""End-to-end API test using FastAPI TestClient."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# ============================ Health ============================
print("=" * 70)
print("HEALTH ENDPOINT")
print("=" * 70)
resp = client.get("/api/v1/health")
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:1500])

# ============================ Stocks ============================
print("\n" + "=" * 70)
print("STOCKS /symbols")
print("=" * 70)
resp = client.get("/api/v1/stocks/symbols")
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Total symbols: {len(data['data']['symbols'])}")

# ============================ Single stock ============================
print("\n" + "=" * 70)
print("STOCKS /VCB")
print("=" * 70)
resp = client.get("/api/v1/stocks/VCB?interval=1d")
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Rows: {data['data']['count']}")
print(f"Latest: {data['data']['latest']}")
print(f"Source: {data['data']['data_source']}")

# ============================ Latest ============================
print("\n" + "=" * 70)
print("STOCKS /FPT/latest")
print("=" * 70)
resp = client.get("/api/v1/stocks/FPT/latest?interval=1d")
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:800])

# ============================ Indicators ============================
print("\n" + "=" * 70)
print("INDICATORS /stocks/VCB/indicators")
print("=" * 70)
resp = client.get("/api/v1/stocks/VCB/indicators?rsi_period=14")
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:600])

# ============================ Backtest ============================
print("\n" + "=" * 70)
print("BACKTEST POST /run")
print("=" * 70)
payload = {
    "symbol": "VCB",
    "strategy": "ma_crossover",
    "initial_capital": 100000000,
    "transaction_fee": 0.001,
    "slippage": 0.0005,
    "parameters": {},
}
resp = client.post("/api/v1/backtests/run", json=payload)
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:800])

# ============================ Backtest history ============================
print("\n" + "=" * 70)
print("BACKTEST GET /history")
print("=" * 70)
resp = client.get("/api/v1/backtests/history?symbol=VCB")
print(f"Status: {resp.status_code}")
data = resp.json()
if data.get("data"):
    print(f"Records: {len(data['data']) if isinstance(data['data'], list) else 'dict'}")

# ============================ Forecasting ============================
print("\n" + "=" * 70)
print("FORECASTING /forecast/train")
print("=" * 70)
resp = client.post("/api/v1/forecast/train", json={"symbol": "VCB", "model_name": "linear_regression", "test_size": 0.2})
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:600])

print("\n" + "=" * 70)
print("FORECASTING /forecast/predict")
print("=" * 70)
resp = client.post("/api/v1/forecast/predict", json={"symbol": "VCB", "model_name": "linear_regression", "horizon": 5})
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:600])

# ============================ Data endpoint ============================
print("\n" + "=" * 70)
print("DATA /stocks/supported")
print("=" * 70)
resp = client.get("/api/v1/data/stocks/supported")
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2, default=str)[:600])
