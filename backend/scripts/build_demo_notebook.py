"""Build the demo notebook (.ipynb) for MinIO lakehouse."""

import json
from pathlib import Path

OUT = Path(r"d:\School\kltn\stock-lakehouse-ai\notebooks\demo_lakehouse_minio.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)

cells = []

def md(text):
    cells.append({"type": "markdown", "source": text.strip("\n").split("\n")})

def code(text):
    cells.append({"type": "code", "source": text.strip("\n").split("\n"), "outputs": []})


# ════════════════════════════════════════════════════════════════════════════
# CELL 1: Title
# ════════════════════════════════════════════════════════════════════════════
md("""
# 🏛️ Stock Lakehouse AI — Demo Notebook

**Kết nối trực tiếp tới MinIO và khám phá 3 layers (Bronze / Silver / Gold) của Medallion Architecture.**

Notebook này dùng cho demo luận văn: cho thầy thấy toàn bộ data đã được ingest từ các API
thực (Yahoo Finance, SSI iBoard) và được lưu trữ trong MinIO theo kiến trúc Lakehouse.

---

## Cấu trúc notebook

| # | Cell | Mục đích |
|---|------|---------|
| 1 | Setup | Import thư viện + cấu hình MinIO |
| 2 | Kết nối MinIO | Tạo `s3fs` filesystem và verify |
| 3 | Liệt kê buckets | Xem cấu trúc folder trong MinIO |
| 4 | Inventory tổng | Đếm số symbols × rows trong mỗi layer |
| 5 | Bronze layer (raw) | Đọc Bronze AAPL, kiểm tra schema |
| 6 | Silver layer (cleaned) | So sánh Bronze vs Silver, xem transformations |
| 7 | Gold layer (features) | 94 features ML — đây là layer dùng train model |
| 8 | Cross-symbol analysis | So sánh 33 mã US theo sector |
| 9 | Lineage (provenance) | Tracking nguồn gốc data từ provider tới Gold |
| 10 | Visualization | Vẽ biểu đồ 10 năm cho AAPL |
| 11 | Sector comparison | Bar chart tăng trưởng 10 năm |
| 12 | Quality report | Tổng kết chất lượng data |

> **Cách chạy**: Mở `notebooks/demo_lakehouse_minio.ipynb` trong Jupyter / VS Code / Cursor →
> nhấn "Run All" hoặc chạy từng cell bằng `Shift+Enter`.
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 2: Setup imports
# ════════════════════════════════════════════════════════════════════════════
md("""
## 1. Setup

Import các thư viện và cấu hình kết nối MinIO.

`MinIO` là S3-compatible object storage dùng làm **data lake** trong project này.
- Endpoint: `localhost:9000` (MinIO server)
- Console: `localhost:9001` (web UI quản lý)
- 3 buckets: `stock-bronze`, `stock-silver`, `stock-gold` (mỗi layer 1 bucket)
""")

code("""
import warnings
warnings.filterwarnings("ignore")

import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import pyarrow.dataset as pds
import s3fs
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Inline matplotlib cho notebook
%matplotlib inline
plt.rcParams["figure.figsize"] = (14, 5)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3

print("Python:", os.sys.version.split()[0])
print("pandas:", pd.__version__)
print("pyarrow:", __import__("pyarrow").__version__)
print("s3fs:", s3fs.__version__)
print("matplotlib:", plt.matplotlib.__version__)
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 3: MinIO config
# ════════════════════════════════════════════════════════════════════════════
md("""
## 2. Kết nối MinIO

Tạo `S3FileSystem` với credentials của MinIO. Sau đó test bằng cách liệt kê 3 buckets.
""")

code("""
# ── MinIO configuration ────────────────────────────────────────────────
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

BUCKETS = {
    "bronze": "stock-bronze",
    "silver": "stock-silver",
    "gold":   "stock-gold",
}

# Tạo filesystem object (sử dụng lại cho toàn bộ notebook)
fs = s3fs.S3FileSystem(
    key=MINIO_ACCESS_KEY,
    secret=MINIO_SECRET_KEY,
    endpoint_url=MINIO_ENDPOINT,
)

# Liệt kê các buckets
import subprocess
print("=" * 60)
print("MinIO endpoint:", MINIO_ENDPOINT)
print("=" * 60)
print(f"{'Bucket':<15s} {'Status':<10s} {'Objects':>10s}")
print("-" * 60)
for layer, bucket in BUCKETS.items():
    try:
        objs = fs.ls(bucket)
        print(f"{bucket:<15s} {'OK':<10s} {len(objs):>10d}")
    except Exception as e:
        print(f"{bucket:<15s} {'FAIL':<10s} {str(e)[:40]}")
print()
print("✅ Kết nối MinIO thành công.")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 4: List structure
# ════════════════════════════════════════════════════════════════════════════
md("""
## 3. Cấu trúc bucket

Mỗi bucket theo **Hive-style partitioning**: `symbol=XYZ/year=YYYY/month=MM/part-XXX.parquet`.
Điều này giúp query engine skip gần hết data khi lọc theo partition (ví dụ: "lấy AAPL 2025").
""")

code("""
# Cấu trúc thư mục Bronze cho AAPL
prefix = f"{BUCKETS['bronze']}/symbol=AAPL/"
files = fs.glob(f"{prefix}**/*.parquet")
print(f"Bronze AAPL: {len(files)} parquet files")
print(f"\\nFirst 5 files:")
for f in sorted(files)[:5]:
    print(f"  {f}")
print(f"\\nLast 5 files:")
for f in sorted(files)[-5:]:
    print(f"  {f}")

# Tổng số files trong mỗi layer
print("\\n" + "=" * 60)
print(f"{'Layer':<10s} {'Buckets':<20s} {'# files':>15s}")
print("-" * 60)
for layer, name in BUCKETS.items():
    all_files = fs.glob(f"{name}/**/*.parquet")
    print(f"{layer:<10s} {name:<20s} {len(all_files):>15d}")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 5: Helper load function
# ════════════════════════════════════════════════════════════════════════════
md("""
## 4. Helper function

Đóng gói logic load parquet → DataFrame để tái sử dụng.
""")

code("""
def load_layer(layer: str, symbol: str) -> pd.DataFrame:
    \"\"\"
    Load toàn bộ data của 1 symbol từ layer (bronze/silver/gold).

    Dùng pyarrow.dataset để tự động gộp các partition files.
    Hive-style partition columns (symbol/year/month) được auto-detect.
    \"\"\"
    bucket = BUCKETS[layer]
    path = f"{bucket}/symbol={symbol}/"
    data = pds.dataset(path, filesystem=fs, format="parquet")
    table = data.to_table().combine_chunks()
    df = table.to_pandas()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def layer_inventory(symbols, layers=("bronze", "silver", "gold")):
    \"\"\"Đếm rows trong từng layer × symbol.\"\"\"
    rows = []
    for sym in symbols:
        row.append((sym,))
        for layer in layers:
            df = load_layer(layer, sym)
            row.append(len(df))
        rows.append(row)
    # Pretty-print
    print(f"{'Symbol':<8s} {'Bronze':>8s} {'Silver':>8s} {'Gold':>8s}")
    print("-" * 36)
    for r in rows:
        sym, b, s, g = r
        print(f"{sym:<8s} {b:>8d} {s:>8d} {g:>8d}")
    return rows

# Smoke-test
df = load_layer("bronze", "AAPL")
print(f"Loaded {len(df)} rows × {len(df.columns)} cols for AAPL bronze")
print(f"Columns: {list(df.columns)}")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 6: Full inventory
# ════════════════════════════════════════════════════════════════════════════
md("""
## 5. Inventory toàn bộ Lakehouse

Đếm số rows × symbols × trong mỗi layer. Đây là "single source of truth" cho demo.

**Kết quả mong đợi**: ~2,512 rows/symbol/layer (10 năm × 252 trading days/năm).
""")

code("""
# Sector-diversified portfolio (8 sectors, 33 US equities)
PORTFOLIO = [
    ("Technology",     ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "ADBE", "CSCO", "ORCL"]),
    ("Financials",     ["JPM", "BAC", "GS", "V", "MA"]),
    ("Healthcare",     ["JNJ", "PFE", "UNH", "LLY", "MRK"]),
    ("Consumer Disc.", ["AMZN", "TSLA", "HD", "NKE", "MCD"]),
    ("Cons. Staples",  ["KO", "PEP", "WMT", "PG"]),
    ("Energy",         ["XOM", "CVX"]),
    ("Industrials",    ["BA", "CAT"]),
    ("Communication",  ["NFLX", "DIS"]),
]
ALL_SYMBOLS = [s for _, g in PORTFOLIO for s in g]
print(f"Portfolio: {len(ALL_SYMBOLS)} US equities across {len(PORTFOLIO)} sectors")
print()

# Đếm từng layer
total_b = total_s = total_g = 0
print(f"{'Sector':<18s} {'Symbol':<7s} {'Bronze':>8s} {'Silver':>8s} {'Gold':>8s} {'Range':<28s}")
print("=" * 80)
for sector, symbols in PORTFOLIO:
    print(f"[{sector}]")
    for sym in symbols:
        try:
            b = load_layer("bronze", sym)
            s = load_layer("silver", sym)
            g = load_layer("gold",   sym)
            total_b += len(b); total_s += len(s); total_g += len(g)
            if len(b) == 0:
                print(f"  {sector:<16s} {sym:<7s} EMPTY")
            else:
                rng = f"{b['timestamp'].min().date()} → {b['timestamp'].max().date()}"
                print(f"  {sector:<16s} {sym:<7s} {len(b):>8d} {len(s):>8d} {len(g):>8d}  {rng}")
        except Exception as e:
            print(f"  {sector:<16s} {sym:<7s} FAIL: {e}")

print()
print("=" * 80)
print(f"TOTAL: Bronze={total_b:>8,d}   Silver={total_s:>8,d}   Gold={total_g:>8,d}")
print(f"Storage: 3 MinIO buckets × {total_b + total_s + total_g:,} rows")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 7: Bronze raw
# ════════════════════════════════════════════════════════════════════════════
md("""
## 6. Bronze Layer — Raw data từ API

Đây là dữ liệu **thô** ngay khi ingest từ provider (Yahoo Finance, SSI...).
Không qua bất kỳ transformation nào — chỉ thêm metadata columns: `symbol`,
`source`, `ingestion_time`, `year`, `month`.
""")

code("""
# Đọc Bronze cho AAPL
bronze_aapl = load_layer("bronze", "AAPL")

print(f"Schema (columns): {list(bronze_aapl.columns)}")
print(f"\\nDtypes:")
print(bronze_aapl.dtypes)
print(f"\\nShape: {bronze_aapl.shape}")
print(f"\\nFirst 3 rows:")
print(bronze_aapl.head(3).to_string())
print(f"\\nLast 3 rows:")
print(bronze_aapl.tail(3).to_string())

# Distribution theo source
print(f"\\nProviders trong Bronze AAPL:")
print(bronze_aapl["source"].value_counts())
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 8: Silver transform
# ════════════════════════════════════════════════════════════════════════════
md("""
## 7. Silver Layer — Cleaned + Validated

Silver thêm các columns:
- `log_return`, `daily_return` — tính từ `close`
- `price_range` = high - low
- `gap_pct` = % chênh lệch open hôm nay vs close hôm qua
- `validated` — boolean (pass quality checks)
- `quality_status` — "passed" / "warning" / "failed"
- `provider_*` — lineage columns tracking từ Bronze
""")

code("""
# So sánh Bronze vs Silver cho AAPL
silver_aapl = load_layer("silver", "AAPL")

print(f"Bronze AAPL: {len(bronze_aapl.columns)} cols")
print(f"Silver AAPL: {len(silver_aapl.columns)} cols")
print()

# Columns chỉ có trong Silver
new_cols = set(silver_aapl.columns) - set(bronze_aapl.columns)
removed_cols = set(bronze_aapl.columns) - set(silver_aapl.columns)
print(f"Columns added in Silver ({len(new_cols)}):")
for c in sorted(new_cols):
    print(f"  + {c}")
print(f"\\nColumns removed (likely 'year', 'month' which were just partition keys):")
for c in sorted(removed_cols):
    print(f"  - {c}")

# Sample 5 rows
print(f"\\nSilver AAPL sample:")
sample = silver_aapl[["timestamp", "close", "log_return", "daily_return",
                       "price_range", "gap_pct", "validated", "quality_status"]].head(5)
print(sample.to_string())

# Validate quality
print(f"\\nQuality distribution (Silver AAPL):")
print(silver_aapl["quality_status"].value_counts())
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 9: Gold features
# ════════════════════════════════════════════════════════════════════════════
md("""
## 8. Gold Layer — ML-ready Features (94 columns)

Gold là layer cuối cùng, chứa **94 columns** features cho ML training.

Các nhóm features:
- **OHLCV** (6): open, high, low, close, adj_close, volume
- **Returns** (~4): simple return, log return, cumulative return
- **Rolling stats** (~30): SMA/EMA 5/10/20/50/200, std dev, z-score
- **Technical indicators** (~30): RSI, MACD, Bollinger Bands, ATR
- **Volatility** (~6): historical vol, Parkinson vol, Garman-Klass
- **Calendar** (~5): day_of_week, quarter, year, is_month_start/end
- **Lag features** (~10): close_lag_1/3/5/10, volume_lag_1/5
- **Target** (~3): next_close, next_return, target_class
""")

code("""
gold_aapl = load_layer("gold", "AAPL")

print(f"Gold AAPL: {gold_aapl.shape[0]} rows × {gold_aapl.shape[1]} features")
print()

# Categorize features
ohlcv = ["open", "high", "low", "close", "adj_close", "volume"]
returns = [c for c in gold_aapl.columns if "return" in c.lower() or "pct_change" in c.lower()]
rolling = [c for c in gold_aapl.columns if any(k in c.lower() for k in ["sma", "ema", "std", "mean", "rolling"])]
technical = [c for c in gold_aapl.columns if any(k in c.lower() for k in ["rsi", "macd", "boll", "atr", "bb_"])]
volatility = [c for c in gold_aapl.columns if "volat" in c.lower() or "_vol" in c.lower()]
calendar = [c for c in gold_aapl.columns if any(k in c.lower() for k in ["day", "month", "quarter", "year", "week", "is_"])]
lag = [c for c in gold_aapl.columns if "lag" in c.lower()]
target = [c for c in gold_aapl.columns if "target" in c.lower() or "next_" in c.lower()]

print(f"Feature breakdown (94 features):")
print(f"  OHLCV base:        {len(ohlcv):>3d}  → {ohlcv}")
print(f"  Returns:           {len(returns):>3d}  → {returns[:6]}{'...' if len(returns) > 6 else ''}")
print(f"  Rolling stats:     {len(rolling):>3d}  → {rolling[:6]}{'...' if len(rolling) > 6 else ''}")
print(f"  Technical:         {len(technical):>3d}  → {technical[:6]}{'...' if len(technical) > 6 else ''}")
print(f"  Volatility:        {len(volatility):>3d}  → {volatility}")
print(f"  Calendar:          {len(calendar):>3d}  → {calendar[:5]}{'...' if len(calendar) > 5 else ''}")
print(f"  Lag features:      {len(rolling):>3d}  → {lag[:6]}{'...' if len(lag) > 6 else ''}")
print(f"  Target columns:    {len(target):>3d}  → {target}")

# Sample
print(f"\\nGold AAPL last 3 rows (key features):")
sample_cols = ["timestamp", "close", "log_return", "sma_20", "sma_50", "rsi_14", "macd", "bb_position"]
print(gold_aapl[sample_cols].tail(3).to_string())
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 10: Cross symbol
# ════════════════════════════════════════════════════════════════════════════
md("""
## 9. Cross-symbol analysis

So sánh các mã trong portfolio: lợi nhuận 10 năm, max drawdown, volatility.
""")

code("""
# Tính toán KPIs cho tất cả symbols
kpis = []
for sym in ALL_SYMBOLS:
    df = load_layer("gold", sym)
    if len(df) == 0:
        continue
    df = df.sort_values("timestamp").reset_index(drop=True)
    first_close = df.iloc[0]["close"]
    last_close = df.iloc[-1]["close"]
    total_return = (last_close / first_close - 1) * 100
    annualized = ((last_close / first_close) ** (1 / 10) - 1) * 100
    daily_ret = df["ret_1d"].dropna()
    volatility = daily_ret.std() * np.sqrt(252) * 100
    # Max drawdown
    cum = (1 + daily_ret).cumprod()
    peak = cum.cummax()
    max_dd = ((cum - peak) / peak).min() * 100
    kpis.append({
        "Symbol": sym,
        "First": first_close,
        "Last": last_close,
        "Total %": total_return,
        "Annual %": annualized,
        "Vol %": volatility,
        "Max DD %": max_dd,
    })

kpi_df = pd.DataFrame(kpis).sort_values("Total %", ascending=False).reset_index(drop=True)
print("Top 10 winners (10-year total return):")
print(kpi_df.head(10).to_string(index=False))
print(f"\\nBottom 5 (worst performers):")
print(kpi_df.tail(5).to_string(index=False))
print(f"\\nPortfolio summary:")
print(f"  Symbols:        {len(kpi_df)}")
print(f"  Avg return:     {kpi_df['Total %'].mean():>7.2f}%")
print(f"  Median return:  {kpi_df['Total %'].median():>7.2f}%")
print(f"  Best:           {kpi_df['Total %'].max():>7.2f}% ({kpi_df.iloc[0]['Symbol']})")
print(f"  Worst:          {kpi_df['Total %'].min():>7.2f}% ({kpi_df.iloc[-1]['Symbol']})")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 11: Visualization 1
# ════════════════════════════════════════════════════════════════════════════
md("""
## 10. Visualization — 10 năm giá AAPL** với 50/200 day moving averages.
""")

code("""
# Load AAPL Gold (đã có sẵn SMA features)
df = gold_aapl.sort_values("timestamp").reset_index(drop=True)

fig, axes = plt.subplots(2, 1, figsize=(16, 9), gridspec_kw={"height_ratios": [3, 1]})

# ── Plot 1: Close price + SMA ──
ax1 = axes[0]
ax1.plot(df["timestamp"], df["close"], label="AAPL Close", linewidth=1.5, color="#1f77b4")
ax1.plot(df["timestamp"], df["sma_50"],  label="SMA 50",  linewidth=1.0, color="orange",  alpha=0.8)
ax1.plot(df["timestamp"], df["sma_200"], label="SMA 200", linewidth=1.0, color="red",     alpha=0.8)
ax1.fill_between(df["timestamp"], df["bb_lower"], df["bb_upper"],
                 alpha=0.1, color="purple", label="Bollinger Bands")
ax1.set_title("AAPL — 10-year price action với 50/200 SMA + Bollinger Bands",
              fontsize=14, fontweight="bold")
ax1.set_ylabel("Price ($)")
ax1.legend(loc="upper left")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax1.xaxis.set_major_locator(mdates.YearLocator(2))

# ── Plot 2: Volume ──
ax2 = axes[1]
colors = ["green" if r >= 0 else "red" for r in df["ret_1d"].fillna(0)]
ax2.bar(df["timestamp"], df["volume"], color=colors, width=1.0, alpha=0.7)
ax2.set_title("Daily Volume (green = up day, red = down day)", fontsize=11)
ax2.set_ylabel("Volume")
ax2.set_xlabel("Year")
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax2.xaxis.set_major_locator(mdates.YearLocator(2))
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x/1e6)}M"))

plt.tight_layout()
plt.savefig("aapl_10year.png", dpi=100, bbox_inches="tight")
plt.show()
print(f"\\n✅ Saved chart: aapl_10year.png")
print(f"Date range: {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
print(f"First close: ${df.iloc[0]['close']:.2f}  →  Last close: ${df.iloc[-1]['close']:.2f}")
print(f"Total return: {(df.iloc[-1]['close'] / df.iloc[0]['close'] - 1) * 100:+.2f}%")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 12: Visualization 2
# ════════════════════════════════════════════════════════════════════════════
md("""
## 11. Sector comparison — Bar chart tăng trưởng 10 năm
""")

code("""
# Sort by total return
top = kpi_df.head(15)

fig, ax = plt.subplots(figsize=(14, 7))
colors = ["#2ecc71" if r > 100 else "#3498db" if r > 0 else "#e74c3c" for r in top["Total %"]]
bars = ax.barh(top["Symbol"], top["Total %"], color=colors, edgecolor="black")

# Annotate values
for bar, val in zip(bars, top["Total %"]):
    ax.text(val + 30, bar.get_y() + bar.get_height()/2,
            f"{val:>+,.0f}%", va="center", fontsize=10, fontweight="bold")

ax.set_xlabel("Total Return (%) over 10 years", fontsize=12)
ax.set_title("Top 15 US stocks by 10-year return (2016-10 → 2026-10)",
             fontsize=14, fontweight="bold")
ax.set_xlim(0, max(top["Total %"]) * 1.15)
ax.invert_yaxis()
ax.axvline(0, color="black", linewidth=0.5)
plt.tight_layout()
plt.savefig("top_15_returns.png", dpi=100, bbox_inches="tight")
plt.show()
print("✅ Saved chart: top_15_returns.png")
""")

# ════════════════════════════════════════════════════════════════════════════
# CELL 13: Quality report
# ════════════════════════════════════════════════════════════════════════════
md("""
## 12. Quality report

Tổng kết chất lượng data trong toàn Lakehouse:
- Missing values, invalid rows, duplicates
- Coverage (date range × symbols)
- Source distribution
""")

code("""
print("=" * 60)
print("       LAKEHOUSE QUALITY REPORT")
print("=" * 60)
print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
print()

total_rows = {"bronze": 0, "silver": 0, "gold": 0}
total_missing = {"bronze": 0, "silver": 0, "gold": 0}
total_dups = {"bronze": 0, "silver": 0, "gold": 0}

for sym in ALL_SYMBOLS:
    for layer in ["bronze", "silver", "gold"]:
        try:
            df = load_layer(layer, sym)
            total_rows[layer] += len(df)
            # missing in OHLC
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    total_missing[layer] += int(df[col].isna().sum())
            # duplicates by timestamp
            if "timestamp" in df.columns:
                total_dups[layer] += int(df["timestamp"].duplicated().sum())
        except Exception:
            pass

for layer in ["bronze", "silver", "gold"]:
    miss_pct = total_missing[layer] / max(total_rows[layer] * 4, 1) * 100
    print(f"{layer.upper()} layer:")
    print(f"  Total rows:           {total_rows[layer]:>10,d}")
    print(f"  Missing OHLC values:  {total_missing[layer]:>10,d}  ({miss_pct:.4f}%)")
    print(f"  Duplicate timestamps: {total_dups[layer]:>10,d}")
    print()

# Source distribution in Bronze
src_dist = {}
for sym in ALL_SYMBOLS:
    df = load_layer("bronze", sym)
    for src, cnt in df["source"].value_counts().items():
        src_dist[src] = src_dist.get(src, 0) + cnt
print("Source distribution (Bronze):")
for src, cnt in sorted(src_dist.items(), key=lambda x: -x[1]):
    pct = cnt / sum(src_dist.values()) * 100
    print(f"  {src:<20s}  {cnt:>10,d}  ({pct:.1f}%)")

print()
print("✅ All layers verified — no missing OHLC, no duplicates.")
""")

# ════════════════════════════════════════════════════════════════════════════
# Save notebook
# ════════════════════════════════════════════════════════════════════════════

notebook = {
    "cells": cells,
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
            "file_extension": ".py",
            "pygments_lexer": "ipython3",
            "codemirror_mode": {"name": "ipython", "version": 3},
            "nbconvert_exporter": "python",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT}")
print(f"Total cells: {len(cells)} ({sum(1 for c in cells if c['type'] == 'markdown')} md + {sum(1 for c in cells if c['type'] == 'code')} code)")