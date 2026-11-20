# Lakehouse

> **Cập nhật 10/11/2026:** Apache Iceberg và Apache Kafka đã bị **gỡ khỏi dự án**.
> Tài liệu này mô tả trạng thái **sau khi gỡ**. Xem mục "Vì sao gỡ" bên dưới.

## Table Format

### Apache Parquet (định dạng đang dùng)

Toàn bộ lakehouse lưu bằng **file Parquet** trên MinIO (hoặc filesystem local), tổ chức theo
quy ước đường dẫn kiểu Hive: `symbol=AAPL/year=2016/month=10/part-000.parquet`.

```
STORAGE_BACKEND=minio   # hoặc "local"
```

**Vì sao gỡ Apache Iceberg (ngày 10/11/2026):**

| Lý do | Giải thích đời thường |
|---|---|
| **Giảm thành phần vận hành** | Bản prototype hiện dùng Parquet trực tiếp, chấp nhận thiếu giao dịch bảng và snapshot. Metadata/manifest của Iceberg không phải bản sao toàn bộ dữ liệu; đó là phần cung cấp các bảo đảm mà triển khai hiện tại chưa có. |
| **Ít một JVM phải vận hành** | `iceberg-rest` là một container Java. Mỗi JVM là một thứ phải giám sát, phải cấp RAM, phải khởi động lại khi chết. Bỏ nó đi là bỏ một nguồn lỗi. |
| **Phạm vi prototype** | Bronze có merge/dedupe và cập nhật khi provider sửa dữ liệu; Silver/Gold được dựng lại. Các file partition có thể bị ghi đè, nên triển khai hiện tại không phải kho raw bất biến có đầy đủ phiên bản. |
| **Quy ước đường dẫn là đủ** | `symbol=.../year=.../month=...` + `_lineage.json` + `_quality.json` đã trả lời được câu hỏi "dữ liệu này ở đâu, đến từ đâu, đã loại rác bao nhiêu". |

**Cái bị mất:** đọc lại một phiên bản dữ liệu cũ theo mốc thời gian (time travel) và
thêm cột mà không phải viết lại dữ liệu (schema evolution).
**Cái được lại:** hệ thống chạy với 2 container hạ tầng thay vì 4, không cần client
PyIceberg, không cần catalog đồng bộ.

> `_lineage.json` giúp truy vết nguồn và thời điểm nạp, nhưng không khôi phục được giá trị cũ đã bị ghi đè. Chạy lại Silver/Gold từ Bronze hiện tại chỉ tái tạo được kết quả từ đầu vào hiện tại. Muốn tái lập đúng một thí nghiệm cũ phải giữ snapshot đầu vào, phiên bản mã và cấu hình tương ứng.

**Container đã bị gỡ khỏi `docker-compose.yml`:**

```bash
# Trước 10/11/2026 (KHÔNG còn dùng):
# docker compose up -d iceberg-rest  # REST API ở http://localhost:8181
#
# Hiện tại chỉ còn 2 dịch vụ hạ tầng:
docker compose up -d mysql minio
```

**Code — đã gỡ, chỉ giữ lại để thấy được trước đây dùng thế nào:**

> **KHÔNG CÒN DÙNG ĐƯỢC.** File `backend/app/lakehouse/iceberg_manager.py` đã bị xoá
> ngày 10/11/2026. Đoạn code dưới đây là **bản ghi lịch sử**, không chạy được nữa.

```python
# ĐÃ XOÁ 10/11/2026 — không còn module app.lakehouse.iceberg_manager
from app.lakehouse.iceberg_manager import get_iceberg_manager

manager = get_iceberg_manager()
manager.create_all_tables()

# Write data
manager.write_bronze(df, symbol="AAPL")

# Time travel - đọc dữ liệu từ 3 ngày trước
df_old = manager.read_bronze(symbol="AAPL", as_of_timestamp="3d")
```

**Cách làm tương đương hiện nay (không cần catalog):**

| Việc | Trước đây (Iceberg) | Hiện nay (Parquet + quy ước) |
|---|---|---|
| Tạo bảng | `manager.create_all_tables()` | `backend/app/lakehouse/pipeline.py` tự tạo partition khi ghi |
| Ghi dữ liệu | `manager.write_bronze(df, symbol="AAPL")` | `backend/app/lakehouse/bronze.py` → `BronzeLayer.append()` |
| Đọc dữ liệu | `manager.read_bronze(symbol="AAPL")` | Đọc Parquet theo đường dẫn `symbol=AAPL/year=.../month=...` |
| Xem phiên bản dữ liệu cũ | `as_of_timestamp="3d"` (time travel) | Chưa có; lineage chỉ ghi provenance, không thay thế snapshot |

### Apache Parquet (Fallback)

```
STORAGE_BACKEND=local   # đường dự phòng khi MinIO không chạy
```

```
data/bronze/symbol=AAPL/year=2026/month=10/part-001.parquet
```

Engine đọc/ghi Parquet là **Pandas** (in-process). Dữ liệu hiện tại ~1.1M rows trên 884 symbols, Pandas xử lý thoải mái.

---

## Bảng bucket / tầng lưu trữ

| Tầng | `layer_name` | Bucket MinIO | Bố cục partition | Bất biến? | Ghi bởi |
|---|---|---|---|---|---|
| **Bronze giá** | `bronze` | `stock-bronze` | `symbol=X/year=YYYY/month=MM/part-NNN.parquet` | Có (append-only) | `backend/app/lakehouse/bronze.py` |
| **Silver giá** | `silver` | `stock-silver` | `symbol=X/year=YYYY/month=MM/part-NNN.parquet` | Không (dựng lại) | `backend/app/lakehouse/silver.py` |
| **Gold giá** | `gold` | `stock-gold` | `symbol=X/year=YYYY/month=MM/part-NNN.parquet` | Không (dựng lại) | `backend/app/lakehouse/gold.py` |
| **Mô hình đã train** | — | `stock-models` | `symbol=X/model=Y/...` | Không | `backend/app/forecasting/model_registry.py` |
| **Kết quả backtest** | — | `stock-backtests` | theo lần chạy | Không | `backend/app/backtesting/` |

> **Ghi chú 12/11/2026:** trước đây còn hai tầng tin tức (`bronze_news` →
> bucket `stock-bronze-news`, `silver_news` → bucket `stock-silver-news`). Cả hai
> đã bị **xoá khỏi MinIO** cùng toàn bộ hệ thống tin tức. Lý do: độ phủ chỉ
> **0,00%** (10 mã / 1.002 mã, 89 bài) và một số bài báo thật bị **gắn sai mã**
> do trùng mã giữa các sàn (`MWG` của Mobile World nhận tin của Multi Ways
> Holdings; `VCB` của Vietcombank nhận tin của quỹ Vanguard). Chi tiết ở mục 5B.1
> của `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.
>
> Bảng tầng lưu trữ giờ còn **một nhánh duy nhất**: giá → Bronze → Silver → Gold.

Cách lấy lại số liệu bucket:

```powershell
python -c "from minio import Minio; c=Minio('127.0.0.1:19000',access_key='minioadmin',secret_key='minioadmin',secure=False); print([(b.name, len([o for o in c.list_objects(b.name, recursive=True) if o.object_name.endswith('.parquet')])) for b in c.list_buckets()])"
```

---

## Universe & Coverage (cập nhật 06/10/2026)

Project ingest **958 tickers** trên **GLOBAL_SYMBOLS** (US + EU + JP + HK + KR + TW + CN + IN + BR + CA + AU + VN), 5 năm daily history qua Yahoo Finance v8 chart API (không cần `yfinance` package).

| Khu vực | Số mã | Ví dụ |
|---------|-------|--------|
| US (S&P 500 / NASDAQ-100 / sector ETFs) | ~300 | AAPL, MSFT, NVDA, XLK |
| Europe (DE / FR / UK / NL / ES / IT / CH) | ~95 | SAP.DE, MC.PA, SHEL.L, ASML.AS |
| Japan (TSE Top 40) | ~40 | 7203.T, 6758.T, 9984.T |
| Hong Kong (Hang Seng) | ~20 | 0700.HK, 9988.HK, 3690.HK |
| China (ADRs) | ~22 | BABA, JD, PDD, NIO, XPEV |
| South Korea (KOSPI top) | ~20 | 005930.KS, 000660.KS, 035420.KS |
| Taiwan (TWSE top) | ~20 | 2330.TW, 2317.TW, 2454.TW |
| India (ADRs) | ~8 | INFY, IBN, HDB |
| Brazil / LatAm (ADRs) | ~10 | VALE, ITUB, PBR |
| Canada (TSX) | ~19 | SHOP, RY.TO, ENB.TO |
| Australia (ASX) | ~20 | BHP.AX, CBA.AX, CSL.AX |
| Vietnam (HOSE/HNX/UPCOM) | ~50 | VCB, FPT, HPG, VNM |
| Sector / Thematic ETFs (US) | ~85 | XLK, XLE, XLV, GLD, TLT, ARKK, SOXL |

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

## Bảng dữ liệu (Parquet + quy ước đường dẫn)

> **Đo ngày 10/11/2026:** Apache Iceberg đã bị gỡ khỏi dự án. Không còn
> `lakehouse.bronze_ohlcv` / `lakehouse.silver_ohlcv` / `lakehouse.gold_features`
> dưới dạng bảng Iceberg, và `backend/scripts/init_iceberg_tables.py` cũng đã bị xoá.

Bảng bây giờ là **tập file Parquet** trong bucket, được định danh bằng quy ước đường dẫn.

### Bảng Bronze (giá)

- **Tầng:** `bronze`
- **Bucket:** `stock-bronze`
- **Partition:** `symbol` (identity), `timestamp` → `year`/`month`
- **Schema:** Raw OHLCV + lineage (`_lineage.json` mỗi partition)

### Bảng Silver (giá)

- **Tầng:** `silver`
- **Bucket:** `stock-silver`
- **Partition:** `symbol` (identity), `timestamp` → `year`/`month`
- **Schema:** Cleaned OHLCV + quality status (`_quality.json` mỗi partition)

### Bảng Gold (giá)

- **Tầng:** `gold`
- **Bucket:** `stock-gold`
- **Partition:** `symbol` (identity), `timestamp` → `year`/`month`
- **Schema:** Features + technical indicators + ML targets

### Đọc theo cửa sổ thời gian và ghi thêm theo phần đổi (đo ngày 14/11/2026)

Vì một mã 10 năm nằm trong ~121 tệp Parquet (mỗi tệm khoảng 21 dòng), hai
cơ chế sau đã được thêm vào để giảm số lượng tệp phải đọc/ghi:

| Cơ chế | Ở đâu | Tác dụng |
|---|---|---|
| **Đọc theo cửa sổ** | `lakehouse/parquet_manager.py::filter_keys_by_window`, `minio_storage.py::read_prefix_window` | Chỉ tải các tệp có thể chứa dòng trong khoảng ngày yêu cầu. Tệp không xác định được tháng thì **luôn được đọc**, không bỏ qua |
| **Ghi thêm theo phần đổi** | `lakehouse/parquet_manager.py::partitions_from` | Chỉ ghi lại các tệp từ tháng của phiên đã thay đổi trở đi |

Cơ sở kỹ thuật của cơ chế ghi thêm: **mọi chỉ báo Silver và Gold đều nhìn
về quá khứ** (rolling mean, EMA, gộp phiên trong ngày), nên một ngày mới ở
cuối lịch sử không làm đổi giá trị của bất kỳ phiên nào trước đó.

**Đo ngày 14/11/2026, AAPL, ghi tầng Gold (122 tệp):**

| Cách ghi | Số tệp ghi | Thời gian |
|---|---|---|
| Ghi toàn bộ | 122 | 4,555 s |
| Ghi thêm (từ 01/10/2026) | 2 | 0,311 s |

**Kiểm chứng:** tính lại toàn bộ 122 tệp Gold từ dữ liệu Silver thật của AAPL
rồi so từng tệp với nội dung đang lưu trên MinIO → **0 sai lệch** trên
`timestamp`, `close`, `ema_12`, `rsi_14`, `sma_20`, `macd`. Ghi thêm cho ra
đúng kết quả của ghi toàn bộ.

**Đo ngày 14/11/2026, API (MinIO cùng máy):**

| Yêu cầu | Thời gian | Dung lượng |
|---|---|---|
| `GET /stocks/AAPL` (toàn bộ) | 1 189 ms | 569 KB |
| `GET /stocks/AAPL?start=2025-11-14` (1 năm) | 202 ms | 56 KB |
| `GET /stocks/AAPL?start=2026-05-14` (6 tháng) | 33 ms | 29 KB |
| `GET /dashboard/AAPL` (toàn bộ) | 8 085 ms | 561 KB |
| `GET /dashboard/AAPL?start=2026-08-14` (3 tháng) | 173 ms | 16 KB |

### Đọc tệp mới nhất thay vì toàn bộ lịch sử (đo ngày 14/11/2026)

Một mã 10 năm nằm trong ~121 tệp/tháng, nhưng nhiều nơi chỉ cần **thanh giá
mới nhất**. Trước đây các nơi đó vẫn tải toàn bộ lịch sử rồi lấy dòng cuối.

Cơ chế mới: `StorageBackend.read_newest_partition()` liệt kê khóa tệp một lần
(một lệnh metadata rẻ) rồi chỉ tải **hai tệp mới nhất**. Hai tệp chứ không
phải một, vì tỷ lệ thay đổi cần giá đóng cửa phiên trước — trong ngày giao
dịch đầu tiên của một tháng, tệp mới nhất chỉ chứa đúng một phiên.

Ba tầng đều có `read_newest()`:
`lakehouse/bronze.py`, `lakehouse/silver.py`, `lakehouse/gold.py`.

**Đo ngày 14/11/2026, API (MinIO cùng máy):**

| Yêu cầu | Trước | Sau |
|---|---|---|
| `GET /stocks/tape` (10 mã, lần đầu) | 11 770 ms | 1 026 ms |
| `GET /stocks/tape` (10 mã, lần sau) | 1 034 ms | 427 ms |
| `GET /stocks/AAPL/latest` | ~1 200 ms | 88 ms |

**Kiểm chứng:** `backend/scripts/verify_latest_fast_path.py` so đường nhanh với
đường chậm trên **1002 mã** của tầng Gold, trên các trường `close`, `open`,
`high`, `low`, `volume`, `change_pct`, `timestamp` → **0 sai lệch**.

### Lỗi đã sửa: cửa sổ thời gian nuốt mất phiên cuối cùng (đo ngày 14/11/2026)

`session.py::slice_window()` so `timestamp <= pd.Timestamp(until, tz="UTC")`.
Vì `until` là một **ngày** còn mốc thời gian của phiên là **giờ mở cửa sàn**
(14:30 UTC cho NYSE, 02:00 UTC cho HOSE), phép so sánh này loại bỏ chính phiên
mà cửa sổ định kết thúc.

Triệu chứng: bộ thống kê của NVDA báo `last_close = 166,19` trong khi giá
đóng cửa đang lưu là `162,85`; số phiên là 180 thay vì 181. Trên giao diện
lỗi này không thấy được (nến cuối thiếu trông y như ngày nghỉ) — nó chỉ lộ
ra khi so số với đường chậm.

Fix: `until` được đổi thành **thời điểm cuối cùng của ngày đó**.

**Kiểm chứng:** `backend/scripts/verify_windowed_stats.py` so số liệu thống kê
của 5 mã theo cả hai cách → trước khi sửa **44 sai lệch**, sau khi sửa
**0 sai lệch**. Lỗi được ghim bằng ba hàm kiểm thử trong
`backend/tests/test_lakehouse_read_write_performance.py`.

### Các lần đọc độc lập chạy song song (đo ngày 14/11/2026)

Ba nơi trong backend gọi nhiều lần đọc MinIO **tuần tự**, trong khi các lần
đọc đó độc lập với nhau và không ghi gì. Xếp hàng khiến tổng thời gian bằng
**tổng** số lần chờ thay vì lần chờ dài nhất.

| Nơi | Trước | Sau |
|---|---|---|
| `/stocks/compare` — bước tìm mốc | 3 lần chờ nối tiếp | 3 lần chờ chồng nhau |
| `/stocks/compare` — bước đọc cửa sổ | 3 lần chờ nối tiếp | 3 lần chờ chồng nhau |
| Đếm bản ghi 3 tầng của Dashboard | 82 + 27 + 72 = **181 ms** | **164 ms** |
| `/stocks/tape` — 10 mã | 10 lần chờ nối tiếp | 10 lần chờ chồng nhau |

**Đo ngày 14/11/2026:** `/stocks/compare?symbols=AAPL,MSFT,NVDA&days=252`
**531 ms → 287 ms**. Thứ tự mã và mọi giá trị `rebased` không đổi; ba con số
đếm bản ghi y hệt vì cùng một danh sách khóa được liệt kê.

**Còn lại:** lần tải đầu tiên sau khi khởi động lại backend vẫn chậm (30 s)
vì lượt tự làm mới nền đang ghi tệp vào MinIO cùng lúc. Chi tiết ở mục
5C.3.10 của `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.

**Giới hạn còn lại:** số lượng tệp phân vùng chưa được gộp. Mỗi tệp chỉ
chứa khoảng 21 dòng nên phần lớn thời gian đọc là do **mở tệp**, không phải
do tải dữ liệu. Gộp theo năm (`symbol=X/year=Y/part-001.parquet`) sẽ giảm
~121 tệp xuống ~10 tệp mỗi mã, nhưng cần script di dời hơn 315.000 tệp đang
tồn tại và phải kiểm chứng trước–sau để không sinh dữ liệu trùng. Xem mục
5C.3.9 của `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.

### Bảng Bronze (tin tức) — ĐÃ GỠ 12/11/2026

- **Tầng:** `bronze_news` (không còn tồn tại)
- **Bucket:** `stock-bronze-news` (đã xoá khỏi MinIO ngày 12/11/2026)
- **Lý do gỡ:** độ phủ 0,00% + tin thật gắn sai mã. Chi tiết ở mục 5B.1 của
  `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.

### Bảng Silver (tin tức) — ĐÃ GỠ 12/11/2026

- **Tầng:** `silver_news` (không còn tồn tại)
- **Bucket:** `stock-silver-news` (đã xoá khỏi MinIO ngày 12/11/2026)
- **Lý do gỡ:** như trên.

### Tạo lại các tầng từ dữ liệu thô

```powershell
cd backend
python scripts\ingest_historical.py      # nạp Bronze từ nhà cung cấp thật
python scripts\reingest_window.py        # nạp lại một khoảng thời gian
```

Mỗi script đều **idempotent** — chạy nhiều lần không sinh bản ghi trùng.

---

## Không còn synthetic fallback (đo ngày 10/11/2026)

Bản cũ của tài liệu này mô tả `MarketService._synthetic_history()` — hàm sinh OHLCV
ngẫu nhiên để chart UI không bị trống khi lakehouse chưa có dữ liệu.

**Hàm đó không còn tồn tại trong mã nguồn.** Docstring hiện tại của
`backend/app/services/market_service.py` nói rõ:

```python
"""Market data service — reads OHLCV strictly from the lakehouse (Gold → Silver → Bronze).

NO synthetic / sample / fallback data. If a symbol has no data in any layer,
`NotFoundError` is raised so the UI surfaces a clear "no data" state instead of
showing fake numbers.
"""
```

Lý do gỡ: luật "Real Data Only" (`.cursor/rules/no-fake-data.mdc`) cấm tuyệt đối mọi
giá trị không truy vết được về một nguồn thật. Khi không có dữ liệu, hệ thống
**báo lỗi thật** (`NotFoundError`) và giao diện hiện trạng thái "không có dữ liệu
cho mã này" — thay vì vẽ một đường giá bịa ra.

> **Đo ngày 10/11/2026:** đã xác nhận bằng cách đọc mã nguồn — không còn chỗ nào
> gọi `_synthetic_history` hay sinh OHLCV bằng hàm ngẫu nhiên trong
> `backend/app/services/`.

