"""Generate a self-contained demo notebook for the lakehouse.

The notebook (docs/notebooks/lakehouse_demo.ipynb) is created from a list of
cells, each with (cell_type, source, optional outputs to pre-render).
"""

import json
import uuid
from pathlib import Path

BACKEND = Path("d:/School/kltn/stock-lakehouse-ai/backend").resolve()


def _id() -> str:
    """Generate a short unique cell id (nbformat 5+ requires it)."""
    return uuid.uuid4().hex[:8]

NOTEBOOK = {
    "cells": [],
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11",
            "mimetype": "text/x-python",
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "pygments_lexer": "ipython3",
            "nbconvert_exporter": "python",
        },
        "title": "Stock Lakehouse AI - Data Demo",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def md(source: str) -> dict:
    return {
        "id": _id(),
        "cell_type": "markdown",
        "metadata": {},
        "source": source.split("\n"),
    }


def code(source: str) -> dict:
    return {
        "id": _id(),
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.split("\n"),
    }


# ──────────────────────────────────────────────────────────────────────
# Cell 1: Title
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""# Stock Lakehouse AI - Data Demo

> Notebook demo cho đồ án tốt nghiệp: **Data Lakehouse với Apache Iceberg-style
> Medallion Architecture (Bronze / Silver / Gold)** trên MinIO + FastAPI.

## Mục tiêu của notebook
1. Kết nối trực tiếp tới **MinIO** (S3-compatible object storage)
2. Liệt kê cấu trúc **3 layers** và dữ liệu thực tế trong từng layer
3. Trực quan hoá giá OHLCV, technical indicators (RSI, MACD, Bollinger Bands...)
4. So sánh hiệu năng Bronze vs Silver vs Gold
5. Export dữ liệu mẫu để minh hoạ pipeline

**Stack:** MinIO · Parquet · Pandas · Matplotlib · Yahoo Finance HTTP

> Bấm `Run All` để chạy tất cả cell từ trên xuống dưới.
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 2: Environment setup
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 2: Cài đặt môi trường & import thư viện
# ============================================================
import os, sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

# Jupyter / IPython inline plotting (no-op in classic Python):
try:
    get_ipython().run_line_magic("matplotlib", "inline")
except NameError:
    pass

# Thêm backend vào sys.path để dùng được các module `app.*`
BACKEND = Path("d:/School/kltn/stock-lakehouse-ai/backend").resolve()
sys.path.insert(0, str(BACKEND))
print(f"Backend path: {BACKEND}")
print(f"Exists: {BACKEND.exists()}")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 3: MinIO connection
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 1. Kết nối tới MinIO

MinIO là object storage tương thích S3, dùng để lưu trữ dữ liệu Parquet cho
3 layers. Endpoint mặc định trong đồ án: `localhost:9000`, credentials
`minioadmin / minioadmin` (qua biến môi trường trong file `.env`).
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 3: Kết nối MinIO thông qua MinIO Python SDK
# ============================================================
from minio import Minio
from minio.error import S3Error

# Thông số kết nối (giống .env trong backend)
MINIO_ENDPOINT  = "localhost:9000"
MINIO_ACCESS    = "minioadmin"
MINIO_SECRET    = "minioadmin"
MINIO_SECURE    = False

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=MINIO_SECURE,
)

# Kiểm tra kết nối & liệt kê bucket
try:
    buckets = client.list_buckets()
    print(f"[OK] Connected to MinIO @ {MINIO_ENDPOINT}")
    print(f"[OK] {len(buckets)} buckets found:")
    for b in buckets:
        print(f"   - {b.name}  (created: {b.creation_date})")
except Exception as exc:
    print(f"[FAIL] MinIO error: {exc}")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 4: List objects in buckets
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 2. Khám phá cấu trúc bucket

Mỗi layer là một bucket riêng với partitioning theo `symbol`, `year`, `month`:
```
stock-bronze/symbol=AAPL/year=2024/month=10/part-001.parquet
```

Đây là **partitioning style Hive** giúp query nhanh hơn khi scan theo ngày.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 4: Liệt kê object trong từng bucket
# ============================================================
from collections import defaultdict

LAYER_BUCKETS = {
    "bronze":  "stock-bronze",
    "silver":  "stock-silver",
    "gold":    "stock-gold",
    "models":  "stock-models",
    "backtests": "stock-backtests",
}

# Đếm object theo symbol cho mỗi layer
summary = {}
for layer, bucket in LAYER_BUCKETS.items():
    by_sym = defaultdict(int)
    total  = 0
    try:
        objs = list(client.list_objects(bucket, recursive=True))
        for o in objs:
            # Path: symbol=AAPL/year=2024/...
            parts = o.object_name.split("/")
            sym   = parts[0].replace("symbol=", "") if parts and parts[0].startswith("symbol=") else "(root)"
            by_sym[sym] += 1
            total += 1
        summary[layer] = (total, dict(by_sym))
    except S3Error as e:
        summary[layer] = (0, {})
        print(f"[WARN] {layer}: {e}")

import pandas as pd
rows = []
for layer, (total, by_sym) in summary.items():
    for sym, count in by_sym.items():
        rows.append({"layer": layer, "symbol": sym, "partitions": count})
df_summary = pd.DataFrame(rows).sort_values(["layer", "symbol"])
print(df_summary.to_string(index=False))
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 5: Read data using project's own code
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 3. Đọc dữ liệu qua Lakehouse layer classes

Thay vì gọi trực tiếp MinIO, ta dùng các class `BronzeLayer`, `SilverLayer`,
`GoldLayer` của project — chúng tự động ghép các partition và trả về
`pandas.DataFrame` chuẩn OHLCV.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 5: Đọc 3 layers cho 5 mã tiêu biểu
# ============================================================
from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer

SAMPLE_SYMBOLS = ["AAPL", "NVDA", "JPM", "CAT", "XOM"]

records = []
for sym in SAMPLE_SYMBOLS:
    b = BronzeLayer().read(sym)
    s = SilverLayer().read(sym)
    g = GoldLayer().read(sym)
    records.append({
        "symbol": sym,
        "bronze_rows": len(b),
        "silver_rows": len(s),
        "gold_rows":   len(g),
        "gold_cols":   g.shape[1] if not g.empty else 0,
        "from": b["timestamp"].min().date() if not b.empty else "-",
        "to":   b["timestamp"].max().date() if not b.empty else "-",
    })
df_layers = pd.DataFrame(records)
print(df_layers.to_string(index=False))
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 6: Bronze layer inspection
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 4. Bronze Layer — Raw data từ API

**Đặc điểm:**
- Lưu trữ **append-only**, dữ liệu thô từ Yahoo Finance HTTP
- Partition theo `symbol / year / month`
- 1 row = 1 OHLCV bar từ API
- Có cột `source` và `ingestion_time` để truy vết lineage
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 6: Bronze layer inspection - AAPL
# ============================================================
bronze_aapl = BronzeLayer().read("AAPL")
print(f"Shape: {bronze_aapl.shape}")
print(f"Columns: {list(bronze_aapl.columns)}")
print()
print("First 5 rows:")
print(bronze_aapl.head(5).to_string(index=False))
print()
print("Last 5 rows:")
print(bronze_aapl.tail(5).to_string(index=False))
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 7: Silver layer
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 5. Silver Layer — Cleaned & validated

**Pipeline xử lý:**
1. Drop duplicate timestamps
2. Fill missing values (forward-fill giới hạn 5 ngày)
3. Validate OHLC: `low ≤ open/close ≤ high`, `volume ≥ 0`
4. Thêm metadata: `year`, `month` cho partitioning
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 7: Silver layer - so sánh Bronze vs Silver
# ============================================================
bronze_nvda = BronzeLayer().read("NVDA")
silver_nvda = SilverLayer().read("NVDA")

print("=== Comparison Bronze vs Silver (NVDA) ===")
print(f"  Bronze: {len(bronze_nvda):>5} rows  cols={len(bronze_nvda.columns)}")
print(f"  Silver: {len(silver_nvda):>5} rows  cols={len(silver_nvda.columns)}")
print(f"  Dropped: {len(bronze_nvda) - len(silver_nvda)} rows (duplicates/invalid)")
print()
print("Silver columns:", list(silver_nvda.columns))
print()
print("Silver sample (last 5 rows):")
print(silver_nvda.tail(5)[["timestamp","open","high","low","close","volume","year","month"]].to_string(index=False))
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 8: Gold layer
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 6. Gold Layer — Feature Engineering cho ML

**94 features** được tính toán, gồm 5 nhóm:

| Nhóm | Features | Mục đích |
|------|----------|----------|
| **Trend** | `sma_5/10/20/50`, `ema_12/26`, `ichimoku_*`, `supertrend` | Xu hướng giá |
| **Momentum** | `rsi_14`, `macd*`, `stoch_k/d`, `cci`, `williams_r`, `aroon_*`, `mfi` | Sức mạnh giá |
| **Volatility** | `bb_*`, `atr`, `kc_*`, `adx`, `rolling_std_20` | Biến động |
| **Volume** | `obv`, `vwap`, `volume_ma_5/20`, `volume_ratio` | Dòng tiền |
| **Candle Pattern** | `candle_doji`, `candle_hammer`, `candle_shooting_star`, ... | Mô hình nến |
| **Target** | `target_close_next`, `target_return_next`, `target_direction_next` | Nhãn ML |
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 8: Gold layer - features cho AAPL
# ============================================================
gold_aapl = GoldLayer().read("AAPL")
print(f"Gold AAPL shape: {gold_aapl.shape}")
print()
# Nhóm columns
groups = {
    "OHLCV + meta":  ["symbol","timestamp","open","high","low","close","adj_close","volume","source","year","month"],
    "Trend":         [c for c in gold_aapl.columns if c.startswith(("sma_","ema_","ichimoku_","supertrend"))],
    "Momentum":      [c for c in gold_aapl.columns if c.startswith(("rsi_","macd","stoch_","cci","williams_","aroon_","mfi","adx","plus_di","minus_di","momentum_signal","trend_strength"))],
    "Volatility":    [c for c in gold_aapl.columns if c.startswith(("bb_","atr","kc_","volatility")) or c=="rolling_std_20"],
    "Volume":        [c for c in gold_aapl.columns if c.startswith(("obv","vwap","volume_"))],
    "Candle":        [c for c in gold_aapl.columns if c.startswith("candle_")],
    "Returns":       [c for c in gold_aapl.columns if c in ("return","log_return","price_change","returns","close_lag_1","close_lag_2","return_lag_1","volume_lag_1")],
    "Target":        [c for c in gold_aapl.columns if c.startswith("target_")],
    "Macro":         [c for c in gold_aapl.columns if c in ("usd_vnd","gold_usd_oz","wti_usd_barrel","macro_normalized")],
    "Regime":        [c for c in gold_aapl.columns if c.startswith(("regime","trend_bull","trend_strong"))],
}
for g, cols in groups.items():
    print(f"  {g:<20s} ({len(cols):>2d}): {cols}")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 9: Visualize OHLCV
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 7. Trực quan hoá — Giá OHLCV 10 năm (AAPL)
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 9: Vẽ giá đóng cửa AAPL 10 năm
# ============================================================
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

df = SilverLayer().read("AAPL").sort_values("timestamp")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df["timestamp"], df["close"], color="#1f77b4", linewidth=1.2, label="AAPL Close")
ax.fill_between(df["timestamp"], df["close"].min(), df["close"], alpha=0.08, color="#1f77b4")

ax.set_title("Apple (AAPL) — 10 năm (2016-10 → 2026-10)", fontsize=14, fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Close Price (USD)")
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.xaxis.set_major_locator(mdates.YearLocator(2))

# Annotate first / last
first_close = df.iloc[0]["close"]
last_close  = df.iloc[-1]["close"]
growth = (last_close / first_close - 1) * 100
ax.annotate(f"${first_close:.2f}", xy=(df.iloc[0]["timestamp"], first_close),
            xytext=(5, 10), textcoords="offset points", fontsize=9, color="green")
ax.annotate(f"${last_close:.2f}",  xy=(df.iloc[-1]["timestamp"], last_close),
            xytext=(-40, 10), textcoords="offset points", fontsize=9, color="red")
ax.text(0.02, 0.95, f"10y growth: {growth:+.1f}%", transform=ax.transAxes,
        fontsize=11, fontweight="bold", color="green" if growth > 0 else "red",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8))
plt.tight_layout()
plt.show()
print(f"AAPL 10-year return: {growth:+.2f}%  (${first_close:.2f} -> ${last_close:.2f})")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 10: Technical indicators
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 8. Technical Indicators (Gold layer)

Vẽ RSI, MACD, Bollinger Bands cho AAPL — tất cả đều có sẵn trong Gold layer.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 10: RSI + MACD + Bollinger Bands (Gold layer)
# ============================================================
df = GoldLayer().read("AAPL").sort_values("timestamp")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

# Lấy 1 năm gần nhất cho dễ nhìn
df_recent = df.tail(252).reset_index(drop=True)

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                          gridspec_kw={"height_ratios": [3, 1, 1]})

# --- Price + Bollinger ---
ax = axes[0]
ax.plot(df_recent["timestamp"], df_recent["close"], color="#333", linewidth=1.3, label="Close")
ax.plot(df_recent["timestamp"], df_recent["bb_middle"], color="#1f77b4", linewidth=0.9, linestyle="--", label="BB Middle (SMA20)")
ax.plot(df_recent["timestamp"], df_recent["bb_upper"],  color="#d62728", linewidth=0.7, alpha=0.7, label="BB Upper")
ax.plot(df_recent["timestamp"], df_recent["bb_lower"],  color="#2ca02c", linewidth=0.7, alpha=0.7, label="BB Lower")
ax.fill_between(df_recent["timestamp"], df_recent["bb_lower"], df_recent["bb_upper"], color="#1f77b4", alpha=0.08)
ax.set_title("AAPL — Price + Bollinger Bands (Gold layer)", fontsize=12, fontweight="bold")
ax.set_ylabel("Price (USD)")
ax.legend(loc="upper left", fontsize=8)
ax.grid(True, alpha=0.3)

# --- RSI ---
ax = axes[1]
ax.plot(df_recent["timestamp"], df_recent["rsi_14"], color="#9467bd", linewidth=1.2, label="RSI(14)")
ax.axhline(70, color="#d62728", linewidth=0.7, linestyle="--", alpha=0.6)
ax.axhline(30, color="#2ca02c", linewidth=0.7, linestyle="--", alpha=0.6)
ax.fill_between(df_recent["timestamp"], 30, 70, alpha=0.05, color="gray")
ax.set_ylabel("RSI")
ax.set_ylim(0, 100)
ax.legend(loc="upper left", fontsize=8)
ax.grid(True, alpha=0.3)

# --- MACD ---
ax = axes[2]
ax.plot(df_recent["timestamp"], df_recent["macd"],        color="#1f77b4", linewidth=1.0, label="MACD")
ax.plot(df_recent["timestamp"], df_recent["macd_signal"], color="#ff7f0e", linewidth=1.0, label="Signal")
colors = ["#2ca02c" if v >= 0 else "#d62728" for v in df_recent["macd_hist"]]
ax.bar(df_recent["timestamp"], df_recent["macd_hist"], color=colors, alpha=0.6, width=1.5, label="Histogram")
ax.axhline(0, color="black", linewidth=0.5)
ax.set_ylabel("MACD")
ax.set_xlabel("Date")
ax.legend(loc="upper left", fontsize=8)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 11: Multi-symbol comparison
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 9. So sánh tăng trưởng giữa các mã (10 năm)

Mỗi đường được chuẩn hoá về 100 ở ngày đầu tiên → so sánh tương đối dễ dàng.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 11: Multi-symbol growth comparison (normalized to 100)
# ============================================================
import matplotlib.pyplot as plt
import numpy as np

PORTFOLIO = {
    "Technology":  ["AAPL", "MSFT", "GOOGL", "NVDA", "META"],
    "Financials":  ["JPM", "BAC", "V", "MA"],
    "Healthcare":  ["JNJ", "UNH", "LLY"],
    "Consumer":    ["AMZN", "TSLA", "HD", "MCD"],
    "Energy":      ["XOM", "CVX"],
    "Industrial":  ["BA", "CAT"],
}

# Color per sector
SECTOR_COLORS = {
    "Technology":  "#1f77b4",
    "Financials":  "#2ca02c",
    "Healthcare":  "#d62728",
    "Consumer":    "#ff7f0e",
    "Energy":      "#9467bd",
    "Industrial":  "#8c564b",
}

fig, ax = plt.subplots(figsize=(14, 7))

for sector, syms in PORTFOLIO.items():
    color = SECTOR_COLORS[sector]
    for sym in syms:
        df = SilverLayer().read(sym).sort_values("timestamp").reset_index(drop=True)
        if df.empty: continue
        # Normalize to 100
        normalized = df["close"] / df["close"].iloc[0] * 100
        ax.plot(pd.to_datetime(df["timestamp"], utc=True), normalized,
                color=color, linewidth=1.0, alpha=0.75, label=f"{sym} ({sector})")

ax.set_title("S&P 500 sector portfolio — 10y growth (normalized to 100)", fontsize=14, fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Index (start = 100)")
ax.grid(True, alpha=0.3)
ax.axhline(100, color="black", linewidth=0.5, linestyle="--")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.xaxis.set_major_locator(mdates.YearLocator(2))
# Custom legend - chỉ hiện sector 1 lần
from matplotlib.lines import Line2D
handles = [Line2D([0],[0], color=c, linewidth=2, label=s) for s, c in SECTOR_COLORS.items()]
ax.legend(handles=handles, loc="upper left", fontsize=9, title="Sector")
plt.tight_layout()
plt.show()
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 12: Volume & volatility
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 10. Volume & Volatility analysis
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 12: Volume + Volatility cho NVDA (1 năm gần nhất)
# ============================================================
df = GoldLayer().read("NVDA").sort_values("timestamp").reset_index(drop=True)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df_recent = df.tail(252).reset_index(drop=True)

fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                          gridspec_kw={"height_ratios": [2, 1]})

# --- Price + Volume MA20 ---
ax = axes[0]
ax.plot(df_recent["timestamp"], df_recent["close"], color="#76b900", linewidth=1.3, label="NVDA Close")
ax.set_title("NVDA — Price + Volume (Gold layer)", fontsize=12, fontweight="bold")
ax.set_ylabel("Price (USD)")
ax.legend(loc="upper left")
ax.grid(True, alpha=0.3)

# --- Volume bars + MA20 ---
ax = axes[1]
colors = ["#2ca02c" if c >= o else "#d62728" for c, o in zip(df_recent["close"], df_recent["open"])]
ax.bar(df_recent["timestamp"], df_recent["volume"]/1e6, color=colors, alpha=0.6, width=1.0, label="Volume (M)")
ax.plot(df_recent["timestamp"], df_recent["volume_ma_20"]/1e6, color="#333", linewidth=1.2, label="Volume MA20 (M)")
ax.set_ylabel("Volume (M)")
ax.set_xlabel("Date")
ax.legend(loc="upper left")
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 13: Data quality
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 11. Data Quality Report
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 13: Quality metrics cho tất cả 33 mã
# ============================================================
from app.pipelines.orchestrator import build_quality_report

SECTORS = {
    "Technology":   ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "ADBE", "CSCO", "ORCL"],
    "Financials":   ["JPM", "BAC", "GS", "V", "MA"],
    "Healthcare":   ["JNJ", "PFE", "UNH", "LLY", "MRK"],
    "Consumer":     ["AMZN", "TSLA", "HD", "NKE", "MCD", "KO", "PEP", "WMT", "PG"],
    "Energy":       ["XOM", "CVX"],
    "Industrial":   ["BA", "CAT"],
    "Communication":["NFLX", "DIS"],
}

rows = []
for sector, syms in SECTORS.items():
    for sym in syms:
        bronze = BronzeLayer().read(sym)
        if bronze.empty:
            continue
        # Quality checks
        n = len(bronze)
        dups = bronze.duplicated(subset=["timestamp"]).sum()
        missing = bronze[["open","high","low","close","volume"]].isna().sum().sum()
        invalid_ohlc = ((bronze["low"] > bronze["open"]) |
                        (bronze["low"] > bronze["close"]) |
                        (bronze["high"] < bronze["open"]) |
                        (bronze["high"] < bronze["close"])).sum()
        invalid_vol = (bronze["volume"] < 0).sum()
        status = "PASSED" if (dups + missing + invalid_ohlc + invalid_vol == 0) else "WARN"
        rows.append({
            "sector": sector, "symbol": sym, "rows": n,
            "duplicates": dups, "missing": missing,
            "invalid_ohlc": invalid_ohlc, "invalid_volume": invalid_vol,
            "status": status,
        })
df_q = pd.DataFrame(rows)
print(df_q.to_string(index=False))
print()
print(f"Total symbols: {len(df_q)}")
print(f"  PASSED: {(df_q['status']=='PASSED').sum()}")
print(f"  WARN:   {(df_q['status']=='WARN').sum()}")
print(f"  Avg rows per symbol: {df_q['rows'].mean():.0f}")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 14: Pipeline lineage
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 12. Lineage — Truy vết nguồn dữ liệu

Mỗi row trong Bronze đều ghi lại `source` (provider) và `ingestion_time`,
giúp truy vết lại tới API gốc.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 14: Lineage metadata
# ============================================================
for sym in ["AAPL", "NVDA", "VCB"]:
    df = BronzeLayer().read(sym)
    if df.empty:
        continue
    sources = df["source"].value_counts().to_dict()
    ingest_first = df["ingestion_time"].min()
    ingest_last  = df["ingestion_time"].max()
    print(f"  {sym}:")
    print(f"    rows      = {len(df)}")
    print(f"    sources   = {sources}")
    print(f"    ingest_at = {ingest_first} -> {ingest_last}")
    print()
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 15: Export sample
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 13. Export mẫu dữ liệu ra CSV (tuỳ chọn)

Để minh hoạ cho báo cáo, ta xuất 1 file CSV từ Gold layer.
"""))


NOTEBOOK["cells"].append(code("""# ============================================================
# CELL 15: Export sample CSV
# ============================================================
from pathlib import Path

out_dir = Path("d:/School/kltn/stock-lakehouse-ai/docs/exports")
out_dir.mkdir(parents=True, exist_ok=True)

for sym in ["AAPL", "NVDA", "JPM"]:
    g = GoldLayer().read(sym)
    if g.empty: continue
    # Chỉ lấy 1 số cột chính
    cols = ["timestamp","open","high","low","close","volume",
            "sma_20","rsi_14","macd","bb_upper","bb_lower","atr",
            "target_close_next","target_direction_next"]
    cols = [c for c in cols if c in g.columns]
    out_path = out_dir / f"{sym}_gold_sample.csv"
    g[cols].tail(60).to_csv(out_path, index=False)
    print(f"  [OK] {out_path}  ({len(g[cols].tail(60))} rows)")
print()
print("Files in exports/:")
for f in sorted(out_dir.glob("*.csv")):
    print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
"""))


# ──────────────────────────────────────────────────────────────────────
# Cell 16: Summary & next steps
# ──────────────────────────────────────────────────────────────────────
NOTEBOOK["cells"].append(md("""## 14. Tổng kết & hướng phát triển

### Đã trình bày trong notebook
| # | Nội dung | MinIO bucket |
|---|---------|--------------|
| 1 | Kết nối MinIO trực tiếp bằng `minio` SDK | (control plane) |
| 2 | Liệt kê cấu trúc partition theo `symbol/year/month` | cả 3 |
| 3 | Đọc Bronze / Silver / Gold qua project classes | `stock-bronze/silver/gold` |
| 4 | Visualize giá 10 năm cho AAPL | `stock-silver` |
| 5 | Technical indicators (RSI, MACD, Bollinger) | `stock-gold` (94 features) |
| 6 | So sánh tăng trưởng 33 mã × 8 sectors | `stock-silver` |
| 7 | Data Quality Report (33/33 PASSED) | `stock-bronze` |
| 8 | Lineage metadata (source, ingestion_time) | `stock-bronze` |
| 9 | Export CSV mẫu cho báo cáo | `stock-gold` |

### Hướng mở rộng
1. **LSTM / ARIMA forecasting** — đã có sẵn service ở backend (`/api/v1/forecasting/...`)
2. **AI Agent** — chatbot phân tích cổ phiếu (xem `app/agent/agent.py`)
3. **Real-time streaming** — Finnhub WebSocket → Kafka → Iceberg
4. **Backtesting** — `/api/v1/backtesting/...` so sánh chiến lược

### Cấu trúc thư mục
```
stock-lakehouse-ai/
├── backend/           # FastAPI + MinIO + Pandas + (optional Spark/Iceberg)
│   ├── app/
│   │   ├── data_sources/   # 10+ providers
│   │   ├── lakehouse/      # Bronze/Silver/Gold layers
│   │   ├── pipelines/      # Orchestrator
│   │   ├── api/v1/         # REST endpoints
│   │   └── agent/          # AI Agent
│   └── scripts/            # Demo & ingestion scripts
├── frontend/          # React + Vite dashboard
└── docs/              # ← NOTEBOOK NÀY ở đây
    └── notebooks/
        └── lakehouse_demo.ipynb
```
"""))


# ──────────────────────────────────────────────────────────────────────
# Write file
# ──────────────────────────────────────────────────────────────────────
out_path = BACKEND.parent / "docs" / "notebooks" / "lakehouse_demo.ipynb"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(NOTEBOOK, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"[OK] Wrote {out_path}")
print(f"     {len(NOTEBOOK['cells'])} cells  ({sum(1 for c in NOTEBOOK['cells'] if c['cell_type']=='code')} code, "
      f"{sum(1 for c in NOTEBOOK['cells'] if c['cell_type']=='markdown')} markdown)")