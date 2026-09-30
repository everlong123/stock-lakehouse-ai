"""Comprehensive system health audit - all layers, providers, APIs, streaming.

Run this to confirm every component works end-to-end.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

results: list[tuple[str, str, str]] = []  # (category, status, detail)


def check(category: str, status: str, detail: str) -> None:
    results.append((category, status, detail))
    icon = {"PASS": "+", "WARN": "!", "FAIL": "-"}[status]
    print(f"[{icon}] {category:<28s} {status:<5s} {detail}")


# ============================================================
# 1. STORAGE BACKEND
# ============================================================
print("=" * 70)
print("STORAGE BACKEND")
print("=" * 70)
from app.lakehouse.storage_factory import get_storage_backend
storage = get_storage_backend()
check(
    "Storage backend",
    "PASS" if storage.backend_name in {"minio", "local"} else "FAIL",
    f"backend={storage.backend_name} class={type(storage).__name__}",
)
health = storage.health() if hasattr(storage, "health") else {"available": True}
if not health.get("available"):
    check("Storage health", "FAIL", str(health.get("error", "")))
else:
    check("Storage health", "PASS", str(health))

# ============================================================
# 2. LAKEHOUSE LAYERS
# ============================================================
print()
print("=" * 70)
print("LAKEHOUSE LAYERS")
print("=" * 70)
from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer

for layer_name, layer in [("Bronze", BronzeLayer()), ("Silver", SilverLayer()), ("Gold", GoldLayer())]:
    try:
        df = layer.storage.read_prefix(layer.layer_name, "")
        if df.empty:
            check(f"{layer_name} layer", "FAIL", "empty")
            continue
        symbols = df["symbol"].nunique()
        rows = len(df)
        check(
            f"{layer_name} layer",
            "PASS",
            f"symbols={symbols} rows={rows} columns={len(df.columns)}",
        )
    except Exception as exc:
        check(f"{layer_name} layer", "FAIL", str(exc))

# ============================================================
# 3. DATA PROVIDERS
# ============================================================
print()
print("=" * 70)
print("DATA PROVIDERS")
print("=" * 70)
from app.data_sources.factory import get_data_provider

for provider_name in ["yfinance", "ssi_vn", "multi_source"]:
    try:
        provider = get_data_provider(provider_name)
        check(
            f"Provider {provider_name}",
            "PASS",
            f"class={type(provider).__name__} source_name={provider.source_name}",
        )
    except Exception as exc:
        check(f"Provider {provider_name}", "FAIL", str(exc)[:120])

# ============================================================
# 4. INDICATORS / FORECASTING / BACKTEST
# ============================================================
print()
print("=" * 70)
print("ML/ANALYTICS LAYER")
print("=" * 70)
from app.indicators.service import add_indicators, IndicatorConfig
from app.lakehouse.silver import SilverLayer

silver = SilverLayer()
vcb_silver = silver.read("VCB")
if not vcb_silver.empty:
    config = IndicatorConfig(sma_windows=(5, 10, 20), ema_windows=(12, 26))
    enriched = add_indicators(vcb_silver, config=config)
    expected_cols = {"sma_5", "sma_10", "sma_20", "ema_12", "ema_26"}
    if expected_cols.issubset(set(enriched.columns)):
        check("Indicator service", "PASS", f"VCB enriched with {len(enriched.columns)} cols")
    else:
        check("Indicator service", "WARN", f"missing columns: {expected_cols - set(enriched.columns)}")
else:
    check("Indicator service", "FAIL", "no Silver data for VCB")

from app.forecasting.trainer import train_model
try:
    result = train_model(symbol="VCB", model_name="linear_regression")
    mae = result.get("mae", 0)
    rmse = result.get("rmse", 0)
    mape = result.get("mape", 0)
    check(
        "Forecasting (LR)",
        "PASS",
        f"MAE={mae:.2f} RMSE={rmse:.2f} MAPE={mape:.2f}%",
    )
except Exception as exc:
    check("Forecasting (LR)", "FAIL", str(exc)[:120])

from app.backtesting.engine import BacktestEngine
engine = BacktestEngine()
try:
    bt = engine.run(symbol="VCB", strategy_name="ma_crossover", initial_capital=100_000_000)
    check(
        "Backtesting (MA)",
        "PASS",
        f"trades={bt['number_of_trades']} return={bt['total_return']*100:.2f}% "
        f"sharpe={bt['sharpe_ratio']:.3f}",
    )
except Exception as exc:
    check("Backtesting (MA)", "FAIL", str(exc)[:120])

# ============================================================
# 5. API ENDPOINTS
# ============================================================
print()
print("=" * 70)
print("REST API")
print("=" * 70)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
endpoints = [
    ("GET",  "/api/v1/health",                              None),
    ("GET",  "/api/v1/stocks/symbols",                      None),
    ("GET",  "/api/v1/stocks/VCB?interval=1d",              None),
    ("GET",  "/api/v1/stocks/FPT/latest?interval=1d",       None),
    ("GET",  "/api/v1/stocks/VCB/indicators",               None),
    ("GET",  "/api/v1/data/stocks/supported",               None),
    ("POST", "/api/v1/backtests/run",                       {"symbol": "VCB", "strategy": "ma_crossover",
                                                            "initial_capital": 100_000_000,
                                                            "transaction_fee": 0.001, "slippage": 0.0005}),
    ("POST", "/api/v1/forecast/train",                      {"symbol": "VCB", "model_name": "linear_regression"}),
    ("POST", "/api/v1/forecast/predict",                    {"symbol": "VCB", "model_name": "linear_regression", "horizon": 5}),
]

for method, path, payload in endpoints:
    try:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json=payload)
        status = "PASS" if resp.status_code == 200 else "WARN"
        if resp.status_code >= 500:
            status = "FAIL"
        body_preview = ""
        if resp.status_code == 200:
            try:
                data = resp.json()
                if "data" in data and isinstance(data["data"], dict):
                    body_preview = f"keys={list(data['data'].keys())[:3]}"
                else:
                    body_preview = f"len={len(str(data))}"
            except Exception:
                body_preview = ""
        check(f"{method} {path}", status, f"{resp.status_code} {body_preview[:60]}")
    except Exception as exc:
        check(f"{method} {path}", "FAIL", str(exc)[:120])

# ============================================================
# 6. STREAMING (Kafka roundtrip)
# ============================================================
print()
print("=" * 70)
print("STREAMING (Kafka)")
print("=" * 70)
from app.streaming.kafka_producer import StockKafkaProducer
import pandas as pd

producer = StockKafkaProducer(bootstrap_servers="localhost:9094", linger_ms=0)
df = pd.DataFrame([{
    "symbol": "VCB",
    "timestamp": pd.Timestamp("2026-10-01T12:00:00+00:00"),
    "open": 58400.0,
    "high": 58500.0,
    "low": 58000.0,
    "close": 58450.0,
    "adj_close": 58450.0,
    "volume": 1234567,
    "source": "health_audit",
}])
try:
    sent = producer.send_ohlcv("VCB", df, topic="stock-ohlcv-health-audit")
    producer.close()
    check("Kafka producer", "PASS", f"sent {sent} message(s)")
except Exception as exc:
    check("Kafka producer", "FAIL", str(exc)[:120])

# Manual consumer inspect (avoids slow group rebalance)
from kafka import KafkaConsumer, TopicPartition
ins = KafkaConsumer(
    bootstrap_servers="localhost:9094",
    auto_offset_reset="latest",
    enable_auto_commit=False,
    api_version=(2, 5, 0),
    group_id=None,
    consumer_timeout_ms=5000,
)
tp = TopicPartition("stock-ohlcv-health-audit", 0)
ins.assign([tp])
ins.seek_to_beginning(tp)
count = 0
start = time.time()
while time.time() - start < 6:
    records = ins.poll(timeout_ms=1000)
    for _, messages in records.items():
        count += len(messages)
ins.close()
check("Kafka consumer (inspect)", "PASS" if count >= 1 else "FAIL", f"received {count} messages")

# ============================================================
# 7. INFRASTRUCTURE
# ============================================================
print()
print("=" * 70)
print("INFRASTRUCTURE")
print("=" * 70)
import subprocess
import socket


def tcp_check(host: str, port: int, name: str) -> None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((host, port))
        s.close()
        check(f"TCP {name}", "PASS", f"{host}:{port}")
    except Exception as exc:
        check(f"TCP {name}", "FAIL", f"{host}:{port} {exc}")


tcp_check("localhost", 9000, "MinIO API")
tcp_check("localhost", 9001, "MinIO Console")
tcp_check("localhost", 9092, "Kafka internal")
tcp_check("localhost", 9094, "Kafka external")
tcp_check("localhost", 8090, "Kafka UI")

try:
    out = subprocess.check_output(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=5,
    )
    running = [line.split("\t")[0] for line in out.strip().split("\n") if "stock-lakehouse" in line]
    check("Docker containers", "PASS", f"{len(running)} stock-lakehouse containers running")
except Exception as exc:
    check("Docker containers", "WARN", f"docker not available: {str(exc)[:60]}")

# ============================================================
# SUMMARY
# ============================================================
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for _, s, _ in results if s == "PASS")
warned = sum(1 for _, s, _ in results if s == "WARN")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"PASS={passed}  WARN={warned}  FAIL={failed}  TOTAL={len(results)}")
print("=" * 70)

# Write JSON report
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "summary": {"pass": passed, "warn": warned, "fail": failed, "total": len(results)},
    "checks": [{"category": c, "status": s, "detail": d} for c, s, d in results],
}
out_path = ROOT / "docs" / "system_health_report.json"
out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print(f"JSON report: {out_path}")

# Exit code reflects worst case
if failed > 0:
    sys.exit(2)
sys.exit(0)