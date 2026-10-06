# Lakehouse

## Table Format

### Apache Iceberg (Primary - Modern)

Project dùng **Apache Iceberg** thay vì raw Parquet plain để có schema evolution, time-travel, ACID commit.

```
USE_ICEBERG=true
ICEBERG_CATALOG_URI=http://localhost:8181
```

**Lợi ích so với raw Parquet:**

| Tính năng | Raw Parquet | Apache Iceberg |
|------------|-------------|----------------|
| Time travel | Không | Query historical versions (`as_of_timestamp='3d'`) |
| Schema evolution | Manual | Safe, atomic |
| ACID writes | Partial | Full atomicity |
| Partition pruning | Manual filter | Automatic hidden partitions |
| Concurrent writes | Lock issues | Snapshot isolation |
| Metadata tracking | `_lineage.json` | Built-in history |

**Container:**

```bash
docker compose up -d iceberg-rest  # REST API ở http://localhost:8181
```

**Code:**

```python
from app.lakehouse.iceberg_manager import get_iceberg_manager

manager = get_iceberg_manager()
manager.create_all_tables()

# Write data
manager.write_bronze(df, symbol="AAPL")

# Time travel - đọc dữ liệu từ 3 ngày trước
df_old = manager.read_bronze(symbol="AAPL", as_of_timestamp="3d")
```

### Apache Parquet (Fallback)

```
USE_ICEBERG=false  # Default nếu chưa có Iceberg catalog
```

```
data/bronze/symbol=AAPL/year=2026/month=10/part-001.parquet
```

Engine đọc/ghi Parquet là **Pandas** (in-process). Dữ liệu hiện tại ~1.1M rows trên 884 symbols, Pandas xử lý thoải mái.

---

## Universe & Coverage (cập nhật 06/10/2026)

Project ingest **958 tickers** trên **GLOBAL_SYMBOLS** (US + EU + JP + HK + KR + TW + CN + IN + BR + CA + AU + VN), 5 năm daily history qua Yahoo Finance v8 chart API (không cần `yfinance` package).

| Khu vực | Số mã | Ví dụ |
|---------|-------|--------|
| 🇺🇸 US (S&P 500 / NASDAQ-100 / sector ETFs) | ~300 | AAPL, MSFT, NVDA, XLK |
| 🇪🇺 Europe (DE / FR / UK / NL / ES / IT / CH) | ~95 | SAP.DE, MC.PA, SHEL.L, ASML.AS |
| 🇯🇵 Japan (TSE Top 40) | ~40 | 7203.T, 6758.T, 9984.T |
| 🇭🇰 Hong Kong (Hang Seng) | ~20 | 0700.HK, 9988.HK, 3690.HK |
| 🇨🇳 China (ADRs) | ~22 | BABA, JD, PDD, NIO, XPEV |
| 🇰🇷 South Korea (KOSPI top) | ~20 | 005930.KS, 000660.KS, 035420.KS |
| 🇹🇼 Taiwan (TWSE top) | ~20 | 2330.TW, 2317.TW, 2454.TW |
| 🇮🇳 India (ADRs) | ~8 | INFY, IBN, HDB |
| 🇧🇷 Brazil / LatAm (ADRs) | ~10 | VALE, ITUB, PBR |
| 🇨🇦 Canada (TSX) | ~19 | SHOP, RY.TO, ENB.TO |
| 🇦🇺 Australia (ASX) | ~20 | BHP.AX, CBA.AX, CSL.AX |
| 🇻🇳 Vietnam (HOSE/HNX/UPCOM) | ~50 | VCB, FPT, HPG, VNM |
| 📊 Sector / Thematic ETFs (US) | ~85 | XLK, XLE, XLV, GLD, TLT, ARKK, SOXL |

**Tổng: 958 ticker trong `GLOBAL_SYMBOLS`. Hiện có 917 ticker với 5 năm daily history thật trong Bronze (còn ~40 ticker delisted/renamed không có data trên Yahoo). ~1.1M daily rows qua 3 tầng. API `/stocks/symbols` enumerate từ MinIO bucket (fallback `GLOBAL_SYMBOLS` nếu bucket trống).**

---

## Bronze schema

`symbol`, `timestamp`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `source`, `ingestion_time`.

- Append-only.
- Schema validation.
- Duplicate checking theo `(symbol, timestamp)`.
- Lineage tracking (`_lineage.json` cho mỗi partition).

---

## Silver rules

- `high >= open` và `high >= close`
- `low <= open` và `low <= close`
- `high >= low`
- `volume >= 0`
- Business key: `(symbol, timestamp)`
- Timezone: UTC

Bản ghi lỗi: log, count, ghi `silver/_errors/` (không silent drop).

---

## Gold features

- **Returns / price**: `return`, `log_return`, `price_change`, `volume_change`
- **Trend**: `sma_5/10/20/50`, `ema_12/26`
- **Momentum**: `rsi_14`, `macd`, `macd_signal`, `macd_hist`
- **Volatility**: `bb_middle/upper/lower`, `rolling_std_20`, `atr_14`
- **Volume**: `volume_ma_20`, `obv`, `vwap`
- **Strength**: `adx_14`, `supertrend`
- **Lags**: `close_lag_1/2/3/5`, `return_lag_1/2/3/5`, `volume_lag_1`
- **Macro**: `usd_vnd`, `gold_usd`, `oil_usd`, `regime` (bull/bear x high/low vol)
- **Composite**: buy/sell/hold scores, candlestick patterns

**Targets** (shift -1, không leakage):

- `target_close_next`
- `target_return_next`
- `target_direction_next`

Mỗi symbol có ~94 features Gold. Storage abstraction: `StorageBackend` -> `LocalStorageBackend` | `MinioStorageBackend`.

---

## Iceberg Tables

### Bronze Table

- **Table:** `lakehouse.bronze_ohlcv`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Raw OHLCV + lineage

### Silver Table

- **Table:** `lakehouse.silver_ohlcv`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Cleaned OHLCV + quality status

### Gold Table

- **Table:** `lakehouse.gold_features`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Features + technical indicators + ML targets

### Khởi tạo Iceberg tables

```powershell
cd backend
python scripts\init_iceberg_tables.py
```

Idempotent - chạy nhiều lần không lỗi.

---

## Synthetic Fallback (chỉ cho UI demo)

Khi Lakehouse trống (chưa ingest symbol nào), `MarketService._synthetic_history()` sinh deterministic OHLCV (252 bars) theo ticker để chart demo không bị trống. Cơ chế:

- `seed = sum(ord(c) for c in symbol.upper())` -> deterministic.
- Wave sin kết hợp random walk -> giá dao động quanh base price (95-155 cho US, 25-55 cho VN).
- Dùng `pd.Timestamp(now_utc).normalize()` để tránh lỗi `datetime.datetime has no attribute normalize`.

**Quan trọng:** Synthetic fallback **chỉ dùng cho view layer (chart UI)**. Không ghi vào Bronze/Silver/Gold. Khi đã ingest dữ liệu thật, fallback tự động tắt.
