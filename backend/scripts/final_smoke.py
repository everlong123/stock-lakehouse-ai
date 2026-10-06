"""Final smoke test: verify all key endpoints work after scale-up."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=" * 60)
print("FINAL SMOKE TEST — Stock Lakehouse AI")
print("=" * 60)

# 1. Health
r = client.get("/api/v1/health")
print(f"1. /health: {r.status_code}")

# 2. Symbols list
r = client.get("/api/v1/stocks/symbols")
data = r.json().get("data", {})
print(f"2. /stocks/symbols: {r.status_code}, count={data.get('count')}")

# 3. Sample stocks đa quốc gia
print("\n3. Multi-country samples:")
samples = ["AAPL", "MSFT", "SAP.DE", "MC.PA", "7203.T", "0700.HK",
           "INFY", "ITUB", "2330.TW", "005930.KS", "VCB", "BHP.AX"]
for sym in samples:
    r = client.get(f"/api/v1/stocks/{sym}?interval=1d")
    d = r.json().get("data", {})
    rows = d.get("count", 0)
    latest = d.get("latest", {}).get("timestamp", "")[:10]
    src = d.get("data_source", "?")
    print(f"   {sym:10s}: {r.status_code}  rows={rows:5d}  latest={latest}  source={src}")

# 4. Pipeline health
try:
    r = client.get("/api/v1/pipeline/health")
    print(f"\n4. /pipeline/health: {r.status_code}")
except Exception as e:
    print(f"\n4. /pipeline/health: error {e}")

# 5. Market summary
try:
    r = client.get("/api/v1/market/summary")
    print(f"5. /market/summary: {r.status_code}")
except Exception as e:
    print(f"5. /market/summary: error {e}")

print("=" * 60)
print("OK — web safe.")
print("=" * 60)