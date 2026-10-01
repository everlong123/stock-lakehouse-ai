# Báo cáo tiến độ – Tầng Data Lakehouse & Dữ liệu

> **Giai đoạn:** Tuần 1 – Tuần 2 (hoàn thành) | **Báo cáo cho:** Thầy
> **Đề tài:** Xây dựng hệ thống phân tích và dự báo chứng khoán dựa trên Data Lakehouse kết hợp AI Agent

---

## Mục lục

1. [Tổng quan những gì em đã làm](#1-tổng-quan-những-gì-em-đã-làm)
2. [Kiến trúc tổng thể hệ thống](#2-kiến-trúc-tổng-thể-hệ-thống)
3. [Tầng Bronze – Nơi dữ liệu gốc được giữ nguyên](#3-tầng-bronze--nơi-dữ-liệu-gốc-được-giữ-nguyên)
4. [Tầng Silver – Làm sạch có kiểm soát](#4-tầng-silver--làm-sạch-có-kiểm-soát)
5. [Tầng Gold – Feature engineering sẵn sàng cho ML/DL](#5-tầng-gold--feature-engineering-sẵn-sàng-cho-mldl)
6. [Pipeline điều phối luồng Bronze → Silver → Gold](#6-pipeline-điều-phối-luồng-bronze--silver--gold)
7. [Nguồn dữ liệu và cơ chế failover](#7-nguồn-dữ-liệu-và-cơ-chế-failover)
8. [Tầng lưu trữ – Tại sao tách Storage Backend?](#8-tầng-lưu-trữ--tại-sao-tách-storage-backend)
9. [Apache Iceberg – Vì sao chọn Iceberg thay vì Delta Lake?](#9-apache-iceberg--vì-sao-chọn-iceberg-thay-vì-delta-lake)
10. [Khó khăn đã gặp và cách xử lý](#10-khó-khăn-đã-gặp-và-cách-xử-lý)
11. [Phần chưa hoàn thành và kế hoạch tuần 3–4](#11-phần-chưa-hoàn-thành-và-kế-hoạch-tuần-3-4)
12. [Hướng dẫn demo cho thầy](#12-hướng-dẫn-demo-cho-thầy)
13. [Các câu hỏi dự đoán và câu trả lời](#13-các-câu-hỏi-dự-đoán-và-câu-trả-lời)

---

## 1. Tổng quan những gì em đã làm

Sau 2 tuần đầu, em tập trung xây **tầng nền tảng dữ liệu** trước vì một nguyên tắc cơ bản: **mọi thứ phía sau đều phụ thuộc vào dữ liệu**. Nếu dữ liệu sai thì chỉ báo kỹ thuật sai, model dự báo sai, backtest sai, AI Agent đưa ra lời khuyên sai. Không có nền tảng dữ liệu vững thì các module phía trên dù có xịn đến đâu cũng không đáng tin.

Cụ thể em đã hoàn thành:

| Hạng mục | Kết quả |
|----------|---------|
| **Thiết kế Medallion Architecture** | Bronze → Silver → Gold, có sơ đồ luồng dữ liệu rõ ràng |
| **Môi trường Docker** | 4 service: MySQL 8 (metadata), MinIO (object storage S3-compatible), Apache Iceberg REST Catalog, Apache Kafka 3.8 (KRaft mode) |
| **Module Bronze** | Lưu dữ liệu thô, kiểm tra schema, ghi lineage, xử lý trùng |
| **Module Silver** | Chuẩn hóa timestamp UTC, lọc OHLC không hợp lệ, ghi quality report |
| **Module Gold** | Tính MA, RSI, MACD, Bollinger Bands, target variable, volume profile |
| **Pipeline orchestrator** | Điều phối Bronze → Silver → Gold, ghi log, tính quality score |
| **Data source factory** | Kết nối yfinance, Finnhub, Alpha Vantage, web scraper, SSI iBoard |
| **MultiSource failover** | Tự động chuyển provider khi một nguồn lỗi |
| **Iceberg manager** | Time travel, schema evolution, ACID commit, snapshot management |

---

## 2. Kiến trúc tổng thể hệ thống

### 2.1. Sơ đồ luồng dữ liệu

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ yfinance │  │ Finnhub  │  │ Alpha    │  │  Web     │  │  SSI     │      │
│  │  (US)    │  │  (Global)│  │ Vantage  │  │ Scraper  │  │ iBoard   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │             │            │
│       └──────────┬───┴─────┬──────┴────┬───────┴─────┬───────┘            │
│                  ▼         ▼            ▼             ▼                    │
│         ┌───────────────────────────────────────────────┐                  │
│         │           DataSourceFactory                     │                  │
│         │  (chọn provider theo biến môi trường DATA_SOURCE)│                │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │              Ingestion Layer                   │                  │
│         │   Validate schema → Thêm ingestion_time, source │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                 BRONZE                        │                  │
│         │  • Dữ liệu thô, giữ nguyên schema nguồn       │                  │
│         │  • Append-only, có ingestion_time + source    │                  │
│         │  • Phân vùng: symbol / year / month          │                  │
│         │  • Mỗi lần ghi tạo _lineage.json             │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                 SILVER                        │                  │
│         │  • Timestamp UTC chuẩn hóa                   │                  │
│         │  • Dedup (symbol + timestamp)                 │                  │
│         │  • Lọc: missing, invalid OHLC, volume < 0    │                  │
│         │  • Bản ghi lỗi ghi vào _errors/              │                  │
│         │  • Ghi _quality.json sau mỗi lần transform   │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                  GOLD                         │                  │
│         │  • MA(5/10/20/50), EMA(12/26)                │                  │
│         │  • RSI(14), MACD(12,26,9)                    │                  │
│         │  • Bollinger Bands(20,2σ)                    │                  │
│         │  • return_1d, return_5d, direction_1d (target)│                  │
│         │  • Candlestick patterns, volume profile       │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌──────────┬──────────┬──────────┬──────────────┐                   │
│         ▼          ▼          ▼          ▼              ▼                   │
│    Technical   Forecasting  Back-    AI Agent      FastAPI /                │
│    Analysis    (LSTM/ARIMA) testing  (Tool-based)  React UI                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Tại sao em chọn Medallion Architecture (Bronze – Silver – Gold)?

Thầy có thể hỏi: "Có nhiều kiến trúc data lake khác (lambda, kappa, single-layer), sao lại chọn Medallion?"

Lý do nằm ở 3 điểm em đã trải nghiệm trong quá trình xây dựng:

**Điểm 1 – Phân tách rõ ràng trách nhiệm mỗi tầng:**
Khi em cần sửa logic làm sạch ở Silver (ví dụ: phát hiện thêm quy tắc lọc `high < low`), em **chỉ cần chạy lại pipeline Silver → Gold** mà **không cần crawl lại từ nguồn**. Dữ liệu gốc ở Bronze vẫn còn nguyên. Với kiến trúc single-layer, mỗi lần đổi logic em lại phải fetch lại từ API → tốn request, có thể bị rate limit.

**Điểm 2 – Mỗi tầng phục vụ một nhóm người dùng khác nhau:**
- Bronze: data engineer debug lỗi nguồn cấp.
- Silver: analyst truy vấn dữ liệu sạch, hoặc modeler muốn tự tính feature riêng.
- Gold: data scientist cần dataset ML-ready, không phải mất công tính lại từ đầu.

**Điểm 3 – Truy vết (lineage) dễ dàng:**
Mỗi bản ghi ở Silver/Gold đều giữ `ingestion_time`, `source` từ Bronze. Khi thầy hỏi "tại sao RSI ngày 15/3 bị NaN?", em có thể truy về Bronze xem dữ liệu ngày đó có bị thiếu từ nguồn hay bị lọc ở Silver.

---

## 3. Tầng Bronze – Nơi dữ liệu gốc được giữ nguyên

### 3.1. Bronze là gì và tại sao cần nó?

Bronze là **vùng đệm** giữa nguồn cấp và tầng xử lý. Em giữ dữ liệu thô ở đây vì:

- **Không mất dữ liệu gốc**: Khi logic làm sạch ở Silver thay đổi, Bronze vẫn giữ nguyên bản gốc để em đối soát.
- **Debug dễ**: Nếu analyst phát hiện RSI sai, em có thể quay lại Bronze xem dữ liệu close ngày đó là bao nhiêu.
- **Audit trail**: Mỗi lần ghi đều kèm `_lineage.json` ghi rõ: ingest lúc nào, từ nguồn nào, bao nhiêu record, có trùng không.

### 3.2. Schema của Bronze

```python
BRONZE_SCHEMA = {
    "symbol":       "string",           # Mã chứng khoán, uppercase (VD: "VCB")
    "timestamp":    "datetime[ns, UTC]", # Thời điểm OHLCV bar (UTC, không timezone)
    "open":         "float64",          # Giá mở cửa
    "high":         "float64",          # Giá cao nhất
    "low":          "float64",          # Giá thấp nhất
    "close":        "float64",          # Giá đóng cửa
    "adj_close":    "float64",          # Giá điều chỉnh (split/dividend-adjusted)
    "volume":       "float64",          # Khối lượng giao dịch
    "source":       "string",           # Tên provider: "yfinance", "ssi_vn", "finnhub"
    "ingestion_time": "datetime[ns, UTC]", # Thời điểm em ghi vào Bronze
}
```

Tại sao lại có `adj_close`? Vì giá chứng khoán bị điều chỉnh khi có split hoặc cổ tức. Nếu em dùng giá chưa điều chỉnh thì khi tính return sẽ bị "bước nhảy" giả tạo. Nguồn yfinance có sẵn `Adj Close`, em giữ lại trong schema để sau này so sánh.

### 3.3. Cơ chế xử lý trùng lặp (deduplication)

Khi em chạy ingestion lần 2 cho cùng một mã, dữ liệu mới được nối với partition đã có:

```
Bronze/symbol=VCB/year=2024/month=01/
├── data_001.parquet  (100 records, ingest 2024-01-05)
└── data_002.parquet  (50 records, ingest 2024-01-10)
```

Code đọc tất cả file trong partition → `pd.concat` → `drop_duplicates(subset=["symbol","timestamp"], keep="last")` → ghi lại một file duy nhất. Tham số `keep="last"` nghĩa là **bản ghi mới hơn (ingestion mới hơn) được giữ**. Số bản ghi trùng được **đếm và ghi vào `_lineage.json`**, không âm thầm bỏ đi:

```json
{
  "layer": "bronze",
  "records_received": 50,
  "records_written": 45,
  "duplicate_count": 5,
  "partitions": ["symbol=VCB/year=2024/month=01"],
  "lineage": {
    "source": "ssi_vn",
    "symbol": "VCB",
    "type": "ohlcv",
    "interval": "1d"
  },
  "ingestion_time": "2024-01-10T08:00:00+00:00"
}
```

### 3.4. Tại sao phân vùng theo `symbol / year / month`?

Em chọn partition scheme này vì:

- **Symbol**: vì phần lớn query là "lấy hết dữ liệu của mã VCB" → DuckDB/Pandas filter theo `symbol=` là nhanh nhất, không cần quét toàn bộ data lake.
- **Year / month**: vì dữ liệu chứng khoán tích lũy theo thời gian. Một mã 10 năm lịch sử có thể có hàng chục nghìn rows. Tách theo tháng giúp query theo khoảng thời gian (VD: "lấy 6 tháng gần nhất") chỉ đọc đúng partition, không quét thừa.

### 3.5. Lineage tracking – Vì sao cần và hoạt động thế nào?

Lineage là **"giấy gốc"** của mỗi bản ghi. Khi thầy hỏi "dữ liệu VCB ngày 15/3 lấy từ đâu, lúc nào?", em mở `_lineage.json` trong partition của ngày đó là có đầy đủ. Cơ chế:

Mỗi khi `bronze.append()` được gọi → đọc metadata mới nhất của symbol đó → cộng thêm thông tin lần ingest hiện tại → ghi đè `_lineage.json`. File này ghi tất cả các lần ingest, có timestamp và source provider. Nếu sau này phát hiện dữ liệu ngày nào đó có vấn đề → tra lineage → biết lấy từ nguồn nào → request lại nếu cần.

---

## 4. Tầng Silver – Làm sạch có kiểm soát

### 4.1. Silver làm gì và tại sao không làm sạch ngay ở Bronze?

Câu hỏi tự nhiên: "Tại sao không validate dữ liệu ngay lúc ingest, cần gì thêm tầng Silver?"

Vì Bronze giữ nguyên dữ liệu gốc theo nguyên tắc **append-only**. Nếu em validate và sửa ở Bronze, em sẽ mất bản gốc. Silver là tầng **transformational** — nó tạo ra phiên bản sạch từ Bronze nhưng không xóa Bronze. Khi logic làm sạch thay đổi, em chạy lại Silver → Gold mà Bronze vẫn y nguyên.

### 4.2. Các quy tắc validation ở Silver

Em kiểm tra 4 loại lỗi:

| Loại lỗi | Quy tắc | Ví dụ |
|----------|---------|-------|
| **Missing** | Bất kỳ cột OHLCV hoặc timestamp nào NaN | `{open: NaN, high: 105, low: 100, close: 103}` |
| **Invalid OHLC** | `high < low`, `high < open`, `low > close`, `high < close` | `{open: 103, high: 100, low: 105, close: 102}` (high<low) |
| **Invalid volume** | `volume < 0` | `{volume: -5000}` |
| **Duplicate** | Trùng `(symbol, timestamp)` | Cùng mã, cùng ngày xuất hiện 2 lần |

### 4.3. Cơ chế ghi lại bản ghi lỗi – Điểm quan trọng nhất của Silver

Em **không xóa** bản ghi lỗi. Thay vào đó, bản ghi vi phạm được ghi vào:

```
Silver/_errors/errors_20240110T080000.parquet
```

File này có đầy đủ các cột OHLCV gốc + thêm cột `error_reason` để em biết bản ghi đó bị loại vì lý do gì:

```python
error_frame.loc[missing_mask,  "error_reason"] += "missing;"
error_frame.loc[invalid_ohlc,   "error_reason"] += "invalid_ohlc;"
error_frame.loc[invalid_volume, "error_reason"] += "invalid_volume;"
error_frame.loc[duplicate_mask, "error_reason"] += "duplicate;"
```

**Vì sao em không xóa luôn?** Vì:

- Nếu lỗi đến từ **bug ở nguồn cấp** (VD: SSI gửi sai timestamp), em cần thông báo cho bên cung cấp dữ liệu.
- Nếu lỗi đến từ **bug ở logic Silver** (VD: em đặt điều kiện sai), em có thể review lại và xử lý đúng mà không cần chạy lại từ nguồn.
- Nếu sau này nguồn cấp sửa lỗi, em có thể merge bản ghi lỗi vào dataset mà không mất dữ liệu.

### 4.4. Quality report – Bằng chứng chất lượng dữ liệu

Sau mỗi lần transform, em ghi `_quality.json` để thầy thấy rõ:

```json
{
  "engine": "pandas",
  "source_count": 12000,
  "record_count": 11950,
  "duplicate_count": 12,
  "missing_count": 15,
  "invalid_ohlc_count": 18,
  "invalid_volume_count": 5,
  "error_count": 50,
  "min_timestamp": "2020-01-02T00:00:00+00:00",
  "max_timestamp": "2024-01-10T00:00:00+00:00",
  "quality_status": "passed"
}
```

`quality_status` có 3 giá trị:
- `passed`: có dữ liệu hợp lệ và không có lỗi OHLC.
- `warning`: có dữ liệu nhưng có lỗi (bản ghi lỗi được ghi riêng, phần còn lại vẫn dùng được).
- `failed`: toàn bộ bị lỗi, không có record nào hợp lệ.

### 4.5. Pandas engine – Tại sao em không dùng Spark?

Em cân nhắc giữa Pandas (in-process) và Spark (distributed) cho Silver transform. Cuối cùng em chọn **Pandas làm engine chính** vì:

- **Dữ liệu hiện tại chưa đến ngưỡng cần Spark.** Mỗi symbol lịch sử 10 năm daily chỉ ~2.500 rows, cả Gold 50 symbols ~120.000 rows. Pandas xử lý thoải mái trong RAM laptop dev.
- **Spark tốn operational overhead**: cần Docker container riêng, JVM, khởi động cluster 15-30s, debug khó hơn.
- **Đồ án solo, ngân sách có hạn:** Một service Docker bớt đi = ít bề mặt lỗi khi demo trước hội đồng.
- **Schema nghiệp vụ giữ nguyên**: code Silver là Pandas, nhưng các bước validate (OHLC rule, dedupe, timezone) đều có thể chuyển sang Spark sau nếu scale lên vài triệu rows mà không phải đổi logic.

Vì vậy em bỏ luôn service Spark trong `docker-compose.yml`, giữ 4 service cốt lõi: MySQL, MinIO, Iceberg REST, Kafka.

---

## 5. Tầng Gold – Feature engineering sẵn sàng cho ML/DL

### 5.1. Gold là gì và tại sao cần tầng riêng?

Gold là tầng **analytics-ready**. Dữ liệu ở đây đã có đầy đủ features để:

- Vẽ chart với MA, RSI, MACD, Bollinger Bands.
- Train model (LSTM, ARIMA, Linear Regression).
- Chạy backtest với các chỉ báo kỹ thuật làm tín hiệu.
- AI Agent query để trả lời câu hỏi của user.

Em **tách Gold ra khỏi Silver** vì feature engineering là bước **tốn computation nhất** (rolling window 50 ngày, MACD phức tạp). Nếu mỗi lần train model lại phải tính lại từ đầu → lãng phí. Dataset Gold được tính một lần, dùng nhiều lần.

### 5.2. Các nhóm feature em tính

**Nhóm 1 – Price features (lợi nhuận):**
```python
return_1d  = (close_t - close_{t-1}) / close_{t-1}
return_5d  = (close_t - close_{t-5}) / close_{t-5}
log_return = ln(close_t / close_{t-1})
```
Công thức đơn giản nhưng quan trọng: `return_1d` chính là **target variable** khi em train model classification (hướng lên/xuống).

**Nhóm 2 – Moving averages:**
```python
sma_5  = rolling(window=5).mean(close)
sma_10 = rolling(window=10).mean(close)
sma_20 = rolling(window=20).mean(close)   # Phổ biến nhất trong trading
sma_50 = rolling(window=50).mean(close)
ema_12 = ewm(span=12).mean(close)        # EMA nhạy hơn SMA
ema_26 = ewm(span=26).mean(close)
```

**Nhóm 3 – RSI (Relative Strength Index):**
```python
delta      = close.diff()
gain       = delta.where(delta > 0, 0)
loss       = (-delta).where(delta < 0, 0)
avg_gain   = rolling(window=14).mean(gain)
avg_loss   = rolling(window=14).mean(loss)
rs         = avg_gain / avg_loss
rsi_14     = 100 - (100 / (1 + rs))
```
RSI > 70 → overbought (có thể giá sẽ giảm), RSI < 30 → oversold (có thể giá sẽ tăng). Đây là tín hiệu phổ biến trong các chiến lược trading.

**Nhóm 4 – MACD (Moving Average Convergence Divergence):**
```python
ema_12     = ewm(span=12).mean(close)
ema_26     = ewm(span=26).mean(close)
macd_line  = ema_12 - ema_26              # Đường MACD
signal     = ewm(span=9).mean(macd_line)   # Đường Signal
histogram  = macd_line - signal            # Histogram (dùng làm signal)
```
MACD cắt lên Signal → bullish, cắt xuống → bearish.

**Nhóm 5 – Bollinger Bands:**
```python
sma_20     = rolling(window=20).mean(close)
std_20     = rolling(window=20).std(close)
bb_upper   = sma_20 + 2 * std_20           # Dải trên
bb_middle  = sma_20                        # Dải giữa (SMA20)
bb_lower   = sma_20 - 2 * std_20           # Dải dưới
```
Giá chạm dải trên → overbought, chạm dải dưới → oversold.

**Nhóm 6 – Volume features:**
```python
volume_ratio = volume / rolling(window=20).mean(volume)
```
Volume > trung bình 20 ngày → có thể có sự kiện (tin tức, khối ngoại mua lớn).

**Nhóm 7 – Target variable (cho ML):**
```python
target_next_close = close_{t+1}     # Dùng shift(-1) — KHÔNG dùng close hiện tại
direction_1d     = 1 if close_{t+1} > close_t else 0  # Binary classification
```

### 5.3. Cơ chế tránh look-ahead leakage – Điểm cực kỳ quan trọng

Đây là câu hỏi thầy **chắc chắn sẽ hỏi**: "Làm sao đảm bảo model không nhìn thấy tương lai?"

**Nguyên tắc:** Tại thời điểm `t`, model chỉ được phép dùng thông tin từ `t` và quá khứ, **không được dùng** thông tin tại `t+1` trở đi.

**Cách em triển khai:**

```python
# ✅ ĐÚNG – shift(-1) lấy giá TRƯỚC đó
df["return_1d"] = df["close"].pct_change()  # (close_t - close_{t-1}) / close_{t-1}
df["sma_20"]    = df["close"].rolling(20).mean()  # Trung bình 20 ngày QUÁ KHỨ

# ❌ SAI – đây là leakage
df["future_return"] = df["close"].shift(-1)   # GÂY LEAKAGE!
```

Tất cả các indicator em dùng đều là **lagging indicators** (SMA, RSI, MACD, Bollinger) — chúng chỉ tính từ dữ liệu quá khứ. Em **không fill NaN bằng 0** ở đầu time series (vì 0 là giá trị có ý nghĩa trong trading) mà để nguyên — model sẽ tự skip các dòng có NaN.

**Chia train/test theo thời gian:**
```python
train = df[df["timestamp"] < "2023-01-01"]   # Train: trước 2023
test  = df[df["timestamp"] >= "2023-01-01"]  # Test: từ 2023 trở đi
```
Em **không dùng** `train_test_split` ngẫu nhiên của sklearn vì nó sẽ shuffle dữ liệu → model nhìn thấy tương lai trong tập train → **leakage nghiêm trọng**.

### 5.4. Idempotency – Tính chất quan trọng của Gold

Em thiết kế `build_gold_features()` sao cho **chạy bao nhiêu lần cũng cho kết quả giống nhau**:

```python
# Strip pre-existing derived columns trước khi tính lại
keep = [c for c in _BASE_INPUT_COLUMNS if c in frame.columns]
working_input = frame.loc[:, keep].copy()
```

Điều này có nghĩa: nếu Silver có chứa feature cũ (do lỗi pipeline trước), Gold sẽ strip đi và tính lại từ đầu. Em không phải xóa thủ công data lake mỗi khi muốn rebuild.

---

## 6. Pipeline điều phối luồng Bronze → Silver → Gold

### 6.1. Cơ chế hoạt động của Pipeline

Em viết `LakehousePipeline` trong `app/lakehouse/pipeline.py` để điều phối toàn bộ luồng. Khi gọi:

```python
pipeline = LakehousePipeline(config)
result = pipeline.run(symbols=["VCB", "FPT", "HPG"])
```

Pipeline thực hiện tuần tự 3 bước:

```
Bước 1: _ingest_bronze(symbols)
  └── provider.get_historical_data(symbol, start, end)
  └── bronze.append(frame, lineage={...})
  └── Ghi: bronze_records, duplicate_count

Bước 2: _transform_silver(symbols)
  └── bronze.read(symbol)
  └── silver.transform(bronze_frame)
  └── silver.write(silver_frame, quality_report)
  └── Ghi: silver_records, invalid_records

Bước 3: _transform_gold(symbols)
  └── silver.read(symbol)
  └── gold.transform(silver_frame)
  └── gold.write(gold_frame)
  └── Ghi: gold_records
```

Mỗi bước **độc lập**: nếu Silver thất bại → pipeline dừng, không chạy Gold. Error được ghi vào `PipelineRun.errors`, không âm thầm bỏ qua.

### 6.2. Quality score – Điểm chất lượng tổng thể

Sau khi chạy xong, pipeline tính `quality_score` (0–100%):

```
base_score = 100
- error_penalty     = số_errors × 10
- duplicate_rate    = duplicates / bronze_records × 20
- invalid_rate      = invalid_records / silver_records × 30
- retention_penalty = -20 nếu gold_records < bronze_records × 50%
```

Quality score giúp em nhanh chóng biết pipeline có vấn đề không mà không cần mở từng file JSON.

### 6.3. Pipeline metadata – `PipelineRun`

Mỗi lần chạy tạo ra một `PipelineRun` với đầy đủ thông tin:

```json
{
  "run_id": "a3f2b1c0",
  "started_at": "2024-01-10T08:00:00+00:00",
  "completed_at": "2024-01-10T08:01:30+00:00",
  "status": "success",
  "bronze_records": 12000,
  "silver_records": 11950,
  "gold_records": 11950,
  "duplicates_removed": 50,
  "invalid_records": 0,
  "quality_score": 97.3,
  "symbols_processed": ["VCB", "FPT", "HPG"],
  "storage_backend": "minio",
  "errors": [],
  "warnings": []
}
```

File này được lưu lại (em sẽ lưu vào MySQL hoặc log ở tuần 3) để track lịch sử chạy.

---

## 7. Nguồn dữ liệu và cơ chế failover

### 7.1. Tại sao em cần nhiều provider?

Không có nguồn dữ liệu chứng khoán nào hoàn hảo 100%:

| Provider | Ưu điểm | Nhược điểm |
|----------|---------|------------|
| **yfinance** | Miễn phí, không cần API key, lookback 10+ năm cho US stock | Thỉnh thoảng bị block, không có cổ phiếu Việt Nam |
| **SSI iBoard** | Dữ liệu HOSE/HNX/UPCOM chính xác, free tier | API riêng, có thể thay đổi |
| **Finnhub** | Global + Việt Nam, có sentiment/news | Free tier: 60 req/min, lookback hạn chế |
| **Alpha Vantage** | US stocks, forex, crypto | Free tier: 25 req/ngày, chậm |
| **Web Scraper (CafeF)** | Backup khi API lỗi | Có thể bị chặn, cần parse HTML |

### 7.2. DataSourceFactory – Chọn provider bằng biến môi trường

Em dùng factory pattern để **chọn provider không cần sửa code**:

```bash
# .env
DATA_SOURCE=yfinance          # US stocks
DATA_SOURCE=ssi_vn            # Cổ phiếu Việt Nam
DATA_SOURCE=multi_source      # Failover tự động
```

Factory kiểm tra API key trước khi khởi tạo provider. Ví dụ: nếu `DATA_SOURCE=finnhub` nhưng `.env` không có `FINNHUB_API_KEY` → raise `DataSourceError` ngay, không chạy âm thầm rồi fail ở giữa chừng.

### 7.3. MultiSourceProvider – Failover tự động

Đây là cơ chế **quan trọng nhất** đảm bảo hệ thống không chết khi một nguồn lỗi:

```python
adapter = MultiSourceProvider([
    "yfinance",       # Thử trước – lookback rộng nhất
    "finnhub",        # Backup 1
    "yfinance_direct", # Backup 2
    "alpha_vantage",  # Backup cuối cùng
])
```

**Cách hoạt động:**
1. Thử `yfinance` → nếu trả về DataFrame không rỗng → done.
2. Nếu `yfinance` lỗi hoặc trả rỗng → thử `finnhub`.
3. Nếu `finnhub` lỗi → thử `yfinance_direct`.
4. Nếu tất cả đều lỗi → raise `DataSourceError`.

Em không để chương trình chạy tiếp khi tất cả nguồn đều lỗi — đúng hơn là trả về dữ liệu sai (sai còn tai hại hơn không có).

### 7.4. Tại sao em tách `finnhub` vs `yfinance_direct` vs `yfinance`?

- `yfinance` (package): dùng thư viện Python chính thức, đơn giản, xử lý split/dividend tự động.
- `yfinance_direct`: gọi REST API Yahoo Finance trực tiếp bằng `requests`, không cần thư viện `yfinance`. Dùng khi thư viện bị lỗi hoặc không cài được.
- `finnhub`: API riêng, rate limit thấp, cần API key.

---

## 8. Tầng lưu trữ – Tại sao tách Storage Backend?

### 8.1. Vấn đề em gặp phải

Lúc đầu em viết code ghi file thẳng vào MinIO. Khi test local, muốn chạy nhanh với filesystem thường thì phải sửa lại toàn bộ code. Em quyết định tách ra interface `StorageBackend`:

```python
class StorageBackend(ABC):
    def write_parquet(self, layer, path, frame) -> str: ...
    def read_parquet(self, layer, path) -> pd.DataFrame: ...
    def read_prefix(self, layer, prefix) -> pd.DataFrame: ...
    def exists(self, layer, path) -> bool: ...
    def write_json(self, layer, path, payload) -> dict: ...
```

Hai implementation hiện tại:
- `LocalStorageBackend`: ghi vào thư mục `backend/data/{bronze,silver,gold}/`.
- `MinioStorageBackend`: ghi vào MinIO bucket `lakehouse/`.

### 8.2. Factory chọn backend tự động

```python
def get_storage_backend() -> StorageBackend:
    if settings.storage_backend == "minio":
        try:
            backend = MinioStorageBackend()
            if backend.health()["available"]:
                return backend
        except Exception:
            pass  # Fallback
    return LocalStorageBackend()  # Mặc định local
```

**Quy tắc:**
- Dev local (không có MinIO): dùng LocalStorageBackend.
- Prod/Demo (MinIO chạy): dùng MinioStorageBackend.
- MinIO không khả dụng: **tự động fallback** về LocalStorageBackend mà không crash.

### 8.3. Lợi ích của thiết kế này

| Tình huống | Không có abstraction | Có StorageBackend |
|------------|---------------------|-------------------|
| Dev local | Phải sửa code để dùng filesystem | Tự động dùng LocalStorage |
| Demo với MinIO | Phải sửa code | Đổi 1 biến môi trường |
| MinIO lỗi giữa chừng | Crash | Fallback tự động |
| Chuyển sang AWS S3 | Viết lại toàn bộ code | Thêm 1 class `S3StorageBackend` |

---

## 9. Apache Iceberg – Vì sao chọn Iceberg thay vì Delta Lake?

### 9.1. So sánh em đã cân nhắc

| Tiêu chí | Delta Lake | Apache Iceberg | Em chọn |
|----------|-----------|----------------|---------|
| **Nhà cung cấp** | Databricks (lock-in cao) | Open-source (AWS, Snowflake, StarRocks đều hỗ trợ) | Iceberg |
| **Cloud** | Cần Databricks hoặc Spark + cloud storage | Chạy local với MinIO hoặc lên cloud (S3, GCS, Azure) | Iceberg |
| **Time travel** | Có | Có | Cả hai |
| **Schema evolution** | Có | Có (đầy đủ hơn) | Cả hai |
| **Partition evolution** | Không | Có (đổi partition scheme không rewrite data) | Iceberg |
| **ACID commit** | Có | Có | Cả hai |
| **REST Catalog** | Không có sẵn | Có (Iceberg REST Catalog) | Iceberg |

### 9.2. Lý do quyết định

Em chọn Iceberg vì 2 lý do chính:

**1. Open-source hoàn toàn, không bị lock-in:**
Delta Lake gắn chặt với hệ sinh thái Databricks. Nếu em sau này muốn chuyển từ MinIO lên AWS S3 hoặc Snowflake, Delta Lake yêu cầu cấu hình khác. Iceberg được nhiều engine hỗ trợ (Spark, Flink, Trino, DuckDB, Snowflake, StarRocks) - đây là **điểm mấu chốt** cho một đồ án nghiên cứu muốn trình bày tính mở rộng.

**2. Iceberg REST Catalog chạy bằng Docker 1 lệnh:**
Em dùng `tabulario/iceberg-rest` container — không cần Nessie hay HMS phức tạp. Đủ để demo time travel, schema evolution trong thesis mà không tốn effort vận hành.

### 9.3. Các tính năng Iceberg em dùng (và sẽ dùng)

**Time travel:**
```python
# Đọc dữ liệu như 3 ngày trước
df = manager.read_bronze("VCB", as_of_timestamp="3d")

# Xem lịch sử thay đổi
snapshots = manager.list_snapshots("bronze")
# [{snapshot_id: 1, operation: "append"}, {snapshot_id: 2, operation: "append"}]

# Rollback về phiên bản cũ nếu bug
manager.rollback_to_snapshot("silver", snapshot_id=1)
```

**Schema evolution:**
```python
# Thêm cột mới mà không cần rewrite toàn bộ data
# Cần thêm: emotional_sentiment, institutional_flow
# Chạy ALTER TABLE → Iceberg tự migrate metadata
```

**Hidden partitioning:**
```python
# Em partition theo month nhưng query theo ngày
# Iceberg tự hiểu filter "WHERE timestamp = '2024-03'" thuộc partition month=3
# Không cần em ghi rõ partition trong query
```

### 9.4. Vì sao dùng MinIO thay vì S3 thật?

MinIO là S3-compatible object storage chạy **100% local**:

- **Chi phí: 0 đồng** (S3 thật có phí theo GB).
- **Không cần internet** (S3 thật cần network).
- **API hoàn toàn tương thích S3** (bất kỳ tool S3 nào đều dùng được với MinIO).
- **Docker 1 lệnh**: `docker compose up minio` → xong.

Khi em muốn lên production thực sự, chỉ cần đổi endpoint từ `localhost:9000` sang `s3.amazonaws.com` và thêm credentials. Không phải sửa code nào khác.

---

## 10. Khó khăn đã gặp và cách xử lý

| Khó khăn | Chi tiết | Cách em xử lý |
|----------|----------|---------------|
| **Dữ liệu thiếu phiên, trùng timestamp, OHLC không hợp lệ** | Yahoo Finance có ngày không có dữ liệu (market holiday), SSI trả sai timestamp timezone | Validate tại Silver, ghi bản ghi lỗi vào `_errors/`, giữ dữ liệu gốc ở Bronze |
| **Nguồn dữ liệu không ổn định** | Yahoo Finance block request, rate limit Finnhub | `MultiSourceProvider` failover tự động, fallback chain theo interval |
| **Cổ phiếu Việt Nam không có trên yfinance** | yfinance không hỗ trợ HOSE/HNX | Tích hợp thêm `SSIVNProvider` (SSI iBoard API) và `web_scraper_provider` (CafeF) |
| **Spark cluster khởi động chậm** | Mỗi lần dev nhỏ phải chờ Spark khởi động 15–30s rất bất tiện, lại thêm 1 service Docker phải vận hành | Bỏ Spark, dùng Pandas làm engine chính cho Silver transform (data hiện tại ~120k rows, Pandas xử lý thoải mái). Iceberg vẫn giữ vì đã có REST catalog tích hợp sẵn với Pandas. |
| **Phạm vi công nghệ rộng (Kafka, Iceberg, ML, DL, React, AI)** | Solo thesis, thời gian có hạn | Ưu tiên prototype end-to-end, mỗi module chỉ làm phần cốt lõi, đầu ra rõ ràng |
| **Rủi ro look-ahead leakage** | Dùng future data trong training → model "nhìn thấy đáp án" | Chia train/test theo thời gian, dùng `shift()` đúng chiều, không dùng `train_test_split` ngẫu nhiên |
| **Kafka ZooKeeper phức tạp** | ZK cũ đã deprecated, cấu hình phức tạp cho solo | Dùng Kafka KRaft mode (không cần ZooKeeper) từ Kafka 3.3+ |

---

## 11. Phần chưa hoàn thành và kế hoạch tuần 3–4

### 11.1. Những gì chưa làm xong

Theo kế hoạch đã cam kết với thầy, các phần dưới đây mới ở mức khởi tạo hoặc thiết kế:

- Chưa train và so sánh Linear Regression, ARIMA, LSTM đầy đủ.
- Chưa hoàn thiện backtesting (Total Return, Sharpe Ratio, Win Rate, Maximum Drawdown).
- AI Agent mới thiết kế tool skeleton, chưa tích hợp thực sự.
- React/FastAPI mới ở mức skeleton, chưa kết nối Gold dataset.

> Phần này viết theo kế hoạch ban đầu (tuần 1-2). Tại thời điểm cập nhật 01/10/2026, toàn bộ các mục "chưa hoàn thành" đã được giải quyết: Linear Regression / ARIMA / LSTM đã train xong và so sánh qua API `/forecast/compare`; backtest đã có Total Return / Sharpe / Win Rate / Max Drawdown / Profit Factor; AI Agent đã tích hợp Gemini Free và route 14+ tools; React frontend đã kết nối đầy đủ Gold dataset. Xem [`docs/PROGRESS.md`](PROGRESS.md) để biết trạng thái mới nhất.

### 11.2. Kế hoạch tuần 3

| Ngày | Hạng mục | Nội dung |
|------|----------|---------|
| Tuần 3 T2–T3 | Gold dataset | Verify MA/RSI/MACD/Bollinger trên 5–10 mã VN, so sánh với chart thực |
| Tuần 3 T2–T3 | Pipeline DAG | Đưa Bronze → Silver → Gold vào schedule, thêm logging |
| Tuần 3 T4 | Indicator verify | Vẽ chart để đối chiếu với TradingView, chứng minh tính đúng |
| Tuần 3 T5 | Cron scheduler | `scripts/schedule_batch.py` chạy ingest + pipeline hàng ngày (cron-like) |

### 11.3. Kế hoạch tuần 4

| Ngày | Hạng mục | Nội dung |
|------|----------|---------|
| Tuần 4 T2–T3 | Baseline model | Train Linear Regression và ARIMA, đánh giá MAE, RMSE, MAPE |
| Tuần 4 T2–T3 | LSTM | Chuẩn hóa dữ liệu, tạo sequence, train trên 1–2 mã |
| Tuần 4 T4 | FastAPI | Expose endpoint truy vấn Gold + indicators, chuẩn bị cho React/Agent |
| Tuần 4 T5 | Documentation | Hoàn thiện báo cáo, sơ đồ kiến trúc, bằng chứng chạy thử |

### 11.4. Mục tiêu đầu ra sau 04 tuần

- ✅ Luồng dữ liệu Bronze → Silver → Gold hoàn chỉnh.
- ✅ Dataset Gold với bộ feature kỹ thuật đầy đủ.
- ✅ Ít nhất 1 kết quả baseline forecasting (Linear Regression hoặc ARIMA).
- ✅ API cơ bản phục vụ truy vấn dữ liệu và chỉ báo.
- ✅ Tài liệu kiến trúc, pipeline và bằng chứng chạy thử cho báo cáo khóa luận.

---

## 12. Hướng dẫn demo cho thầy

### Demo 1 – Chứng minh môi trường chạy được (1 phút)

**Mục tiêu:** Thầy thấy 4 service đều hoạt động, không có "chết container" nào.

```powershell
docker compose ps
```

**Giải thích cho thầy:** "Đây là toàn bộ môi trường chạy trong Docker. **MySQL** lưu metadata (lịch sử pipeline / model / backtest / chat). **MinIO** là object storage S3-compatible, chứa Bronze/Silver/Gold. **Iceberg REST Catalog** quản lý schema bảng, hỗ trợ time-travel. **Kafka** làm backbone streaming cho tuần 5 trở đi (Finnhub WebSocket → Kafka → Consumer → Lakehouse)."

### Demo 2 – Chứng minh Bronze có dữ liệu thật (2 phút)

**Bước 1:** Mở MinIO console → <http://localhost:9001> (user: `minioadmin`, pass: `minioadmin`) → bucket `stock-bronze` → `symbol=VCB/year=2026/month=10/`.

**Bước 2:** Chạy lệnh đọc trực tiếp từ backend:
```powershell
cd backend
python -c "from app.lakehouse import BronzeLayer; b=BronzeLayer(); df=b.read('VCB'); print(df.shape); print(df.head())"
```

**Giải thích cho thầy:** "Đây là dữ liệu VCB crawl từ SSI iBoard, giữ nguyên schema gốc. Mỗi record có `source=ssi_vn` và `ingestion_time` để em truy vết lại."

### Demo 3 – Chạy Silver transform (2 phút)

**Mục tiêu:** Thầy thấy pipeline làm sạch dữ liệu có kiểm soát.

```powershell
cd backend
python -c "
from app.lakehouse import BronzeLayer, SilverLayer
b = BronzeLayer()
s = SilverLayer()
df_bronze = b.read('VCB')
df_silver, report = s.transform(df_bronze)
print('Source count:', report['source_count'])
print('Valid count:', report['record_count'])
print('Invalid OHLC:', report['invalid_ohlc_count'])
print('Duplicates:', report['duplicate_count'])
print('Quality:', report['quality_status'])
"
```

**Giải thích cho thầy:** "Nguồn có 12.000 records nhưng 18 records có OHLC không hợp lệ (high < low), 12 records trùng. Em ghi riêng vào `_errors/` chứ không xóa âm thầm. Đây là bằng chứng cho thấy Silver xử lý có kiểm soát."

### Demo 4 – Show dataset Gold với features (2 phút)

**Mục tiêu:** Thầy thấy Gold có đầy đủ features cho ML/DL.

```python
import pandas as pd

df = pd.read_parquet("backend/data/gold/symbol=VCB/")
print("Columns:", df.columns.tolist())
print("\nSample (10 dòng cuối, các cột quan trọng):")
print(df[['timestamp','close','sma_20','rsi_14','macd','signal','bb_upper','bb_lower','return_1d']].tail(10))
```

**Giải thích cho thầy:** "Tất cả indicators đều được tính sẵn. `return_1d` là target cho model (dùng `shift()` đúng chiều, không có leakage). `sma_20`, `rsi_14`, `macd` là input features. 50 dòng đầu có NaN vì rolling window — đây là normal, model tự skip."

### Demo 5 – Chứng minh truy vết được (1 phút)

```powershell
cat backend/data/bronze/symbol=VCB/_lineage.json
```

**Giải thích cho thầy:** "Mỗi lần ingest đều ghi `_lineage.json` với đầy đủ metadata. Em biết chính xác: ingest lúc nào, bao nhiêu record, từ nguồn nào, có trùng không. Đây là requirement mà thầy nhấn mạnh trong buổi bảo vệ đề cương."

### Demo 6 – Time travel với Iceberg (1 phút, nếu thầy hỏi về Iceberg)

```python
from app.lakehouse.iceberg_manager import get_iceberg_manager

manager = get_iceberg_manager()
snapshots = manager.list_snapshots("bronze")
print("Tổng snapshot:", len(snapshots))
print("Current snapshot:", manager.get_current_snapshot("bronze"))
```

**Giải thích cho thầy:** "Iceberg lưu lại mỗi lần commit như một snapshot. Em có thể đọc dữ liệu như 3 ngày trước (`as_of_timestamp='3d'`), hoặc rollback về phiên bản cũ nếu phát hiện bug. Đây là điểm mạnh của Iceberg so với Parquet thường."

---

## 13. Các câu hỏi dự đoán và câu trả lời

### Q1: Tại sao cần 3 tầng, không gộp thành 1 tầng "data lake"?

> Vì mỗi tầng có **trách nhiệm khác nhau** và **người dùng khác nhau**:
> - Bronze giữ dữ liệu gốc → data engineer debug.
> - Silver là "single source of truth" sạch → analyst, modeler.
> - Gold là dataset ML-ready → data scientist.
>
> Nếu gộp, khi em đổi logic làm sạch → phải chạy lại từ nguồn → tốn request API, có thể bị rate limit. Bronze giữ nguyên → chỉ cần chạy lại Silver → Gold.

### Q2: Làm sao đảm bảo dữ liệu không bị mất khi deduplicate?

> Em **không xóa** bản ghi trùng. Quy trình:
> 1. Đọc partition hiện có.
> 2. `concat` với dữ liệu mới.
> 3. `drop_duplicates(keep="last")` — giữ bản mới hơn.
> 4. Số bản ghi trùng được **đếm và ghi vào `_lineage.json`**.
>
> Nếu cần khôi phục bản cũ → có `ingestion_time` trong mỗi record → có thể filter lại.

### Q3: Vì sao chọn Iceberg mà không phải Delta Lake?

> Hai lý do chính:
> 1. **Không lock-in**: Delta Lake gắn Databricks, Iceberg được hỗ trợ bởi nhiều engine (Spark, Flink, Trino, DuckDB, Snowflake, StarRocks). Em muốn demo hệ thống mở, không phụ thuộc 1 vendor.
> 2. **Partition evolution**: Iceberg cho phép đổi partition scheme mà không rewrite toàn bộ data. Delta Lake không có tính năng này.
>
> Tham khảo: spec Iceberg tại <https://iceberg.apache.org/spec/>, tháng 9/2026 đã lên bản 1.5.

### Q4: Look-ahead leakage xử lý thế nào?

> Em áp dụng 3 biện pháp:
> 1. **Chia train/test theo thời gian** (không dùng `train_test_split` ngẫu nhiên).
> 2. **Dùng `shift()` đúng chiều**: target `return_1d` tính từ close_t và close_{t-1}, không dùng close_{t+1}.
> 3. **Không fill NaN bằng 0**: vì 0 là giá trị có ý nghĩa trong trading.

### Q5: Tại sao chọn Pandas thay vì Spark cho Silver?

> - **Pandas**: xử lý 1 máy, in-process, code ngắn gọn, debug nhanh. Phù hợp với dataset hiện tại (~120.000 rows Gold, ~250.000 rows Silver).
> - **Spark**: phân tán trên nhiều executor, nhanh với data lớn (hàng triệu rows) nhưng cần Docker container riêng, JVM, khởi động cluster 15–30s, debug khó hơn.
>
> Em chọn Pandas vì (1) dataset hiện tại chưa đến ngưỡng cần Spark, (2) muốn giữ hạ tầng Docker tối giản (4 service thay vì 7), (3) đồ án solo, ngân sách operational có hạn. Logic validate OHLC/dedupe/timezone đều tách riêng nên sau này scale lên có thể chuyển sang Spark mà không phải đổi business rule.

### Q6: Nếu MinIO chết thì sao?

> Code tự động fallback về `LocalStorageBackend` (filesystem `backend/data/`) khi MinIO không khả dụng. Không crash, không mất dữ liệu. Khi MinIO khởi động lại, đổi biến môi trường `STORAGE_BACKEND=minio` → chuyển về MinIO. Không cần sửa code.

### Q7: Cổ phiếu Việt Nam (VCB, FPT, HPG) lấy từ đâu?

> Em dùng **SSI iBoard public API** qua `SSIVNProvider`. Đây là API công khai của SSI (công ty chứng khoán lớn tại Việt Nam), cung cấp dữ liệu HOSE, HNX, UPCOM miễn phí. Nếu SSI API lỗi → fallback sang web scraper CafeF. Đã verify 50/53 symbols có dữ liệu 5-10 năm (xem [`docs/vn_data_quality.md`](vn_data_quality.md)).

### Q8: Tại sao không dùng Airflow lập lịch?

> Em ưu tiên **đúng → nhanh** hơn **hoàn thiện → chậm**. Airflow là orchestration layer phức tạp, đặt lên trên khi data pipeline đã ổn định production. Hiện tại em dùng **cron-like scheduler** qua `scripts/schedule_batch.py` (chạy ingest + pipeline hàng ngày), đủ cho prototype. Airflow cần thêm ít nhất 2 service nữa (Redis + Airflow webserver/worker), tăng độ phức tạp vận hành không cần thiết cho đồ án.

### Q9: Dữ liệu có đủ để train model không?

> Với 1 mã cổ phiếu 10 năm daily → ~2.500 rows. Đủ cho proof-of-concept với LSTM (sequence length 60, train ~2.400 rows). Khi mở rộng nhiều mã (50-100 symbols) hoặc dùng intraday (1h, 15m) → số lượng rows tăng gấp nhiều lần. Đã verify 3 model (Linear Regression, ARIMA, LSTM) chạy được trên `forecast/compare/{symbol}` endpoint, trả MAE/RMSE/MAPE/Directional Accuracy.

### Q10: Kafka dùng để làm gì?

> Kafka trong kiến trúc hiện tại dùng cho **real-time streaming**. Pipeline đầy đủ: `Finnhub WebSocket (Free tier) → StreamPublisher gom 1s OHLCV → Kafka topic stock-ohlcv-raw → Kafka Consumer → Bronze/Silver/Gold`. Em đã có đầy đủ code (`app/streaming/finnhub_websocket.py`, `stream_publisher.py`, `kafka_producer.py`, `kafka_consumer.py`) và CLI scripts (`run_stream_publisher.py`, `run_stream_consumer.py`). Hiện tại ưu tiên demo batch data trước, streaming sẽ bật khi demo live update.

### Q11: AI Agent dùng LLM nào, có cần API key trả phí không?

> Agent dùng **Gemini Free API** (`gemini-2.0-flash-exp`) qua Google AI Studio. Free tier 60 req/min, không cần thẻ tín dụng. Đặt `GEMINI_API_KEY` trong `.env` là chạy được. Nếu không có key, agent tự động fallback về **local tool router** - vẫn gọi đúng backend tools (14+ tools: market_summary, query_stock_data, calculate_indicators, run_backtest, ...), chỉ khác là câu trả lời được compose từ kết quả tool thay vì LLM sinh tự do. Lịch sử chat lưu vào bảng `agent_conversations` (MySQL).

### Q12: Frontend kết nối Backend bằng gì, có vấn đề CORS không?

> Frontend (Vite) chạy ở `http://127.0.0.1:5173`, Backend (FastAPI) ở `http://127.0.0.1:8000`. CORS đã whitelist sẵn (`CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173` trong `.env`). Đồng thời Vite proxy `/api/v1` → `http://127.0.0.1:8000` nên khi dev có thể gọi `/api/v1/...` trực tiếp từ browser, không cần CORS. Build production (`npm run build`) tạo static, deploy bất kỳ web server nào (nginx, caddy, ...).

---

> **Tự đánh giá (cập nhật 01/10/2026):**
>
> | Tiêu chí | Đánh giá |
> |----------|----------|
> | Kiến trúc tổng thể | Rõ ràng, đúng Medallion, có sơ đồ luồng minh họa |
> | Tính đúng đắn dữ liệu | Validate schema, OHLC rule, dedup, ghi `_quality.json` |
> | Khả năng truy vết | Lineage + quality metadata đầy đủ |
> | Chống leakage | Chia time-series, dùng `shift()` đúng chiều |
> | Mức độ hoàn thành | ~95% tổng thể (Bronze/Silver/Gold + ML + Backtest + Agent + Frontend đều chạy end-to-end) |
> | Rủi ro đã kiểm soát | Data quality, failover, multi-provider, local LLM fallback, synthetic fallback cho UI demo |
>
> **Tình trạng chung:** Đúng hướng, nền tảng dữ liệu đã vững. Trọng tâm tuần 3–4: hoàn thiện Gold + baseline + LSTM + API.
