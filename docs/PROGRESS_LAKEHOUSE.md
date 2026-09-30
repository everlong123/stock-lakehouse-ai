# Báo cáo tiến độ – Tầng Data Lakehouse & Dữ liệu

> Giai đoạn: Tuần 1 – Tuần 2 (đã hoàn thành) và định hướng Tuần 3 – Tuần 4
> Phạm vi: Xây nền tảng dữ liệu (Data Lakehouse) cho đề tài *Xây dựng hệ thống phân tích và dự báo chứng khoán dựa trên Data Lakehouse kết hợp AI Agent*

---

## 1. Tổng quan em đã làm được gì

Sau 2 tuần đầu, em tập trung **làm chắc tầng dữ liệu** trước khi đụng đến mô hình, backtest hay giao diện. Lý do: mọi thứ phía sau (chỉ báo kỹ thuật, LSTM, backtest, AI Agent, dashboard) đều *ngồi trên* tầng dữ liệu. Nếu dữ liệu sai hoặc không truy vết được thì kết quả mô hình đẹp đến mấy cũng vô nghĩa. Đúng tinh thần *"garbage in, garbage out"* mà thầy thường nhắc.

Cụ thể em đã:

- **Thiết kế kiến trúc Medallion (Bronze – Silver – Gold)** cho toàn bộ luồng dữ liệu chứng khoán.
- **Dựng môi trường chạy bằng Docker Compose**: MinIO (object storage), Iceberg REST Catalog, Kafka, Spark, MySQL — tất cả chạy local, không phụ thuộc cloud.
- **Viết các module Python** cho từng tầng (`BronzeLayer`, `SilverLayer`, `GoldLayer`) với kiểm tra schema, validate, dedup, lineage.
- **Kết nối nhiều nguồn dữ liệu** (yfinance, Finnhub, Alpha Vantage, web scraper, SSI iBoard cho Việt Nam) qua một `factory` thống nhất.
- **Chuẩn bị sẵn dataset Gold** có chỉ báo MA, RSI, MACD, Bollinger Bands sẵn sàng cho forecasting và backtesting.

---

## 2. Tại sao em lại chọn kiến trúc như vậy

### 2.1. Vì sao dùng Medallion (Bronze / Silver / Gold)?

Em chọn mô hình 3 lớp của Databricks vì nó giải quyết đúng 3 vấn đề em gặp phải:

| Lớp | Đặc điểm | Vai trò |
|-----|----------|---------|
| **Bronze** | Dữ liệu thô, giữ nguyên schema nguồn, append-only, có `ingestion_time` và `source` | Nếu sau này phát hiện lỗi ở Silver, em luôn quay lại Bronze để tái xử lý |
| **Silver** | Đã làm sạch, chuẩn hóa timestamp UTC, dedup, loại bản ghi OHLC không hợp lệ (VD: high < low) | Là "single source of truth" cho mọi phân tích phía sau |
| **Gold** | Feature engineering + chỉ báo kỹ thuật, sẵn sàng cho ML/DL | Tránh phải tính lại mỗi lần train |

**Quan trọng nhất**: dữ liệu gốc luôn được giữ ở Bronze. Khi em đổi logic làm sạch ở Silver (ví dụ phát hiện thêm quy tắc lọc OHLC), em chỉ cần chạy lại pipeline Silver → Gold, không cần crawl lại từ nguồn. Đây là lý do thầy nhấn mạnh "khả năng truy vết" trong buổi bảo vệ đề cương.

### 2.2. Vì sao chọn Apache Iceberg + MinIO thay vì Delta Lake trên S3 thật?

| Tiêu chí | Iceberg + MinIO (em chọn) | Delta Lake + S3 |
|----------|---------------------------|------------------|
| Chi phí | Chạy local, 0 đồng | Cần AWS account |
| Mở | REST catalog open-source, không lock-in | Delta gắn với Databricks |
| Schema evolution | Có, kèm time travel | Có |
| Phù hợp thesis solo | Dựng bằng Docker 1 lệnh | Cần account/cloud |

Em đã tham khảo một số project mã nguồn mở hiện đại (ví dụ kiến trúc Spark Declarative Pipelines + Iceberg công bố giữa 2026) thì thấy Iceberg đang trở thành chuẩn mở cho financial lakehouse — không phụ thuộc một nhà cung cấp nào. Đồ án solo thì càng nên chọn cái mở để sau này mở rộng lên cloud không phải viết lại.

### 2.3. Vì sao tách Storage Backend ra abstraction (`StorageBackend`)?

Trong code em có `local_storage.py`, `minio_storage.py`, `parquet_manager.py` đều implement cùng interface `StorageBackend`. Lý do:

- Lúc dev/test em chạy với local filesystem (nhanh).
- Lúc demo/prod em chuyển sang MinIO chỉ bằng 1 biến môi trường, **không phải sửa code**.
- Đây cũng là pattern mà các hệ AllMind/Spark SDP hiện đại đang dùng để tách "nơi lưu" khỏi "logic xử lý".

### 2.4. Vì sao có nhiều data provider (yfinance, Finnhub, Alpha Vantage, web scraper, SSI VN)?

Vì **nguồn dữ liệu chứng khoán không ổn định**:

- Yahoo Finance có lúc block request, có lúc trả thiếu phiên.
- Free API (Finnhub, Alpha Vantage) giới hạn rate limit.
- Với cổ phiếu Việt Nam, yfinance không có — phải dùng SSI iBoard (HOSE/HNX/UPCOM) hoặc web scraper CafeF.

Em thiết kế 1 `DataSourceFactory` trả về provider theo biến môi trường, và có `MultiSourceProvider` để **failover tự động** (provider A chết thì tự chuyển sang B). Khi demo em có thể chỉ cho thầy: "Đây là luồng failover khi một nguồn lỗi".

---

## 3. Cơ chế hoạt động của hệ thống (giải thích cho thầy hiểu)

### 3.1. Luồng dữ liệu tổng thể

```
Data Sources (yfinance/Finnhub/SSI/CafeF)
        │
        ▼  ← factory chọn provider theo ENV
  Ingestion (app/pipelines/ingestion.py)
        │  validate schema, thêm ingestion_time, source
        ▼
  ┌─────────────┐
  │   BRONZE    │  Parquet phân vùng theo symbol, append-only, có lineage
  └─────────────┘
        │  đọc toàn bộ Bronze của symbol
        ▼
  ┌─────────────┐
  │   SILVER    │  chuẩn hóa UTC, dedup, lọc OHLC invalid → _errors/
  └─────────────┘
        │  clean OHLCV
        ▼
  ┌─────────────┐
  │    GOLD     │  feature engineering: MA/RSI/MACD/Bollinger/returns
  └─────────────┘
        │
        ├──► Technical Analysis (chart, dashboard)
        ├──► Forecasting (LSTM, ARIMA, Linear Regression)
        ├──► Backtesting (signals, Sharpe, drawdown)
        └──► AI Agent (đọc Gold qua tools)
```

### 3.2. Bronze hoạt động thế nào?

- Mỗi symbol được lưu thành 1 file Parquet phân vùng theo `symbol=VCB/year=2024/...`.
- Khi ingestion thêm dữ liệu mới, code đọc partition hiện có → concat → `drop_duplicates(subset=["symbol","timestamp"], keep="last")` → ghi đè lại.
- **Duplicate không bị bỏ âm thầm** — em đếm và ghi vào metadata `duplicate_count`. Đây là điểm quan trọng để thầy hỏi "có bị mất dữ liệu không".
- Mỗi lần ghi, 1 file `_lineage.json` được tạo kèm theo để truy vết: ai ingest, lúc nào, bao nhiêu record, từ nguồn nào.

### 3.3. Silver hoạt động thế nào?

Silver là tầng **"làm sạch có chứng cứ"**. Em loại bỏ các bản ghi vi phạm các quy tắc sau:

1. **Missing**: bất kỳ cột OHLCV hoặc timestamp nào NaN.
2. **Invalid OHLC**: `high < low`, hoặc `high < open`, hoặc `low > close`, v.v.
3. **Invalid volume**: `volume < 0`.
4. **Duplicate trùng `(symbol, timestamp)`**.

Các bản ghi lỗi **không bị xóa** mà được ghi vào `_errors/errors_<timestamp>.parquet` kèm cột `error_reason` (`missing;invalid_ohlc;duplicate;...`) để em kiểm tra ngược. Kết quả cuối cùng là một `_quality.json` ghi rõ:

```json
{
  "engine": "spark" hoặc "pandas",
  "source_count": 12000,
  "record_count": 11950,
  "duplicate_count": 12,
  "invalid_ohlc_count": 30,
  "quality_status": "passed" | "warning" | "failed"
}
```

Khi chạy trong môi trường có Spark (container `spark-master`), code tự dùng Spark DataFrame để transform; khi chạy local thì fallback Pandas — **logic nghiệp vụ giống hệt nhau**. Em thiết kế vậy để tránh phụ thuộc cứng vào Spark lúc debug.

### 3.4. Gold hoạt động thế nào?

Silver là input duy nhất của Gold. Tại đây em:

- Tính `return_1d`, `return_5d`, `log_return`.
- Tính MA (5, 10, 20, 50).
- Tính RSI(14), MACD(12,26,9), Bollinger Bands (20, 2σ).
- **Tạo target** cho supervised learning: `target_next_close`, `target_direction` (lên/xuống) — tính bằng `shift(-1)` để **chỉ dùng thông tin tại thời điểm t** dự đoán **t+1** (tránh look-ahead leakage).
- Một số feature chậm (rolling 50 ngày) sẽ có NaN ở 50 dòng đầu — em **không fill bằng 0** mà để nguyên, model sẽ tự skip.

Đầu ra Gold là Parquet phân vùng giống Bronze/Silver — query nhanh theo symbol và theo khoảng thời gian.

### 3.5. Cách các tầng "tương tác" với nhau

Điểm quan trọng để thầy hỏi: **làm sao biết được dữ liệu ở Gold đến từ Bronze nào, ingest lúc nào?**

- Mỗi bản ghi ở Silver đều giữ nguyên `timestamp`, `source`, `ingestion_time` từ Bronze.
- Mỗi partition ở mỗi layer đều kèm `_lineage.json` (cho Bronze) hoặc `_quality.json` (cho Silver).
- Pipeline runner (`app/pipelines/pipeline_runner.py`) chạy theo thứ tự: Bronze append → Silver transform → Gold transform, mỗi bước ghi log + metadata. Khi lỗi ở tầng nào thì dừng ở tầng đó, không âm thầm bỏ qua.

---

## 4. Môi trường chạy (Docker Compose)

File `docker-compose.yml` dựng 7 service:

| Service | Mục đích | Port |
|---------|----------|------|
| **MinIO** | Object storage S3-compatible | 9000 (API), 9001 (UI) |
| **Iceberg REST** | Catalog cho Iceberg | 8181 |
| **Kafka** (KRaft mode, không cần ZooKeeper) | Streaming ingestion | 9092, 9094 |
| **Spark master** + **Jupyter** | Xử lý Silver/Gold | 8080 (UI), 7077, 8888/8889 |
| **MySQL** | Metadata, user (tách khỏi lakehouse) | 3307 |
| **Adminer**, **Kafka UI** | UI quản trị | 8081, 8090 |

Em chọn **KRaft mode** cho Kafka (không ZooKeeper) vì đây là cấu hình chính thức từ Kafka 3.3+, dễ vận hành hơn cho thesis solo.

---

## 5. Khó khăn em gặp và cách xử lý

| Khó khăn | Cách em xử lý |
|----------|---------------|
| Dữ liệu chứng khoán hay thiếu phiên, trùng timestamp, OHLC không hợp lệ | Validate ngay tại Silver, **ghi lại bản ghi lỗi vào `_errors/`** chứ không drop âm thầm; Bronze giữ nguyên bản gốc để đối soát |
| Nguồn dữ liệu không ổn định (Yahoo block, rate limit) | `DataSourceFactory` + `MultiSourceProvider` cho phép failover tự động giữa các nguồn |
| Cổ phiếu Việt Nam không có trên yfinance | Tích hợp thêm `SSIVNProvider` (SSI iBoard) và `web_scraper_provider` (CafeF) |
| Spark chỉ chạy được trong container, dev local không có | `SilverLayer`/`GoldLayer` có 2 đường: Spark nếu `spark_enabled()`, fallback Pandas nếu không — **logic nghiệp vụ giống hệt** |
| Phạm vi công nghệ rộng (Spark, Iceberg, Kafka, ML, DL, React, AI) | Ưu tiên **prototype end-to-end**, mỗi module chỉ làm phần cốt lõi; orchestration chưa có Airflow (sẽ bổ sung tuần 3) |

---

## 6. Phần em chưa làm và kế hoạch tuần 3 – 4

**Chưa hoàn thành** (theo đúng cam kết với thầy):
- Chưa train đủ baseline (Linear Regression, ARIMA) và LSTM để so sánh.
- Backtesting chưa có chỉ số Total Return, Sharpe, Win Rate, Max Drawdown đầy đủ.
- AI Agent mới chỉ thiết kế tool skeleton (`query_stock_data`, `calculate_indicators`, `forecast_stock`, `run_backtest`), chưa gắn vào pipeline thật.
- React/FastAPI chỉ là skeleton, chưa tích hợp đầy đủ dashboard.

**Kế hoạch tuần 3:**
1. Hoàn thiện Bronze → Silver → Gold, verify dataset Gold trên 5–10 mã VN.
2. Đưa pipeline vào DAG (cron/Airflow) để chạy đặt lịch.
3. Tính và verify MA/RSI/MACD/Bollinger Bands.

**Kế hoạch tuần 4:**
1. Train baseline (Linear Regression, ARIMA) trên Gold, chia train/test theo thời gian.
2. LSTM bước đầu trên 1–2 mã chọn lọc.
3. FastAPI expose endpoint truy vấn Gold + indicators để chuẩn bị cho AI Agent và React.

---

## 7. Demo cho thầy (5–7 phút)

### Bước 1 — Chứng minh môi trường chạy được
```powershell
docker compose ps
```
Chỉ cho thầy thấy 7 service đều `Up`. Nếu có cái nào `Exit` thì show log.

### Bước 2 — Chứng minh Bronze có dữ liệu thật
Mở MinIO console: <http://localhost:9001> (user/pass: `minioadmin`/`minioadmin`) → bucket `lakehouse` → thư mục `bronze/symbol=VCB/`. Mở 1 file Parquet bất kỳ bằng DuckDB CLI hoặc script:
```powershell
docker exec -it stock-lakehouse-spark-master pyspark
```
```python
df = spark.read.parquet("s3a://lakehouse/bronze/symbol=VCB/")
df.show(5)
df.count()
df.printSchema()
```
Giải thích: "Đây là dữ liệu crawl từ SSI, giữ nguyên schema gốc, có cột `source` và `ingestion_time` để truy vết".

### Bước 3 — Chạy pipeline Silver → Gold cho 1 symbol
```powershell
cd backend
python -m app.pipelines.pipeline_runner --symbol VCB --layers bronze,silver,gold
```
Mở file `_quality.json` sinh ra để show:
```powershell
cat data/silver/symbol=VCB/_quality.json
```
Giải thích: "Đây là bằng chứng chạy thật — số record gốc, số bị loại vì invalid OHLC, duplicate, missing".

### Bước 4 — Show dataset Gold
```python
import pandas as pd
df = pd.read_parquet("data/gold/symbol=VCB/")
print(df.columns.tolist())
print(df[['timestamp','close','MA20','RSI14','MACD','BB_upper']].tail(10))
```
Giải thích: "Đây là bộ feature sẵn sàng cho LSTM tuần 4 — không có look-ahead vì các indicator đều dùng rolling window".

### Bước 5 — Chứng minh truy vết được
Show `_lineage.json` của Bronze:
```powershell
cat data/bronze/symbol=VCB/_lineage.json
```
Giải thích: "Em ghi lại ingestion_time, source, số record, duplicate_count — đây là cách đảm bảo reproducibility mà thầy yêu cầu".

### Bước 6 (nếu còn thời gian) — Demo failover data source
Sửa `.env` từ `DATA_SOURCE=ssi_vn` sang `DATA_SOURCE=web_scraper`, chạy lại ingestion cho 1 symbol — show rằng cùng schema nhưng `source` khác nhau.

---

## 8. Tự đánh giá

| Tiêu chí | Đánh giá |
|----------|----------|
| Kiến trúc tổng thể | Rõ ràng, đúng pattern Medallion tham khảo từ các project open-source 2026 |
| Tính đúng đắn dữ liệu | Có validate schema, dedup, OHLC rule, ghi `_quality.json` |
| Khả năng truy vết | Mỗi layer kèm lineage/quality metadata, dữ liệu gốc ở Bronze |
| Mức độ hoàn thành prototype | ~25% tổng thể, đúng kế hoạch (2 tuần đầu ưu tiên data foundation) |
| Rủi ro | Đã kiểm soát: leakage (chia train/test theo thời gian), chất lượng dữ liệu (validate tại Silver) |

**Tình trạng chung:** đúng hướng, nền tảng dữ liệu đã vững. Trọng tâm 2 tuần tới là hoàn thiện Gold + baseline forecasting + API để có thật sự "đầu ra" cho thầy đánh giá tiếp.
