# Kiểm chứng dữ liệu (Data Verification)

Tài liệu này trả lời một câu hỏi duy nhất:

> **Dữ liệu trong MinIO và trên web có thật không?**

---

## 1. Nguyên tắc: so với với nguồn độc lập, không so với với chính mình

Một `diff` giữa Bronze và Silver chỉ chứng minh hai layer đồng ý với nhau. Nó
**không** chứng minh chúng đúng với thực tế.

Cách kiểm chứng đúng là **re-fetch trực tiếp từ provider** (một HTTP call mới
hoàn toàn, độc lập với lakehouse) rồi so với:

```
    Yahoo Finance (live HTTP)        <- nguồn sự thật
            |
            |  so sánh
            v
    Bronze   (raw, ngay khi ingest)
    Silver   (đã clean / canonicalize)
    Gold     (đã thêm feature)
    API      (thứ browser thực sự vẽ)
```

Nếu giá trị lưu trữ khác giá trị provider đang trả **ngay lúc này**, thì giá
trữ trữ đó sai (hoặc cũ, hoặc sai instrument) — và script sẽ báo.

---

## 2. Công cụ

### `scripts/verify_against_source.py` — kiểm chứng

```bash
cd backend

# Vài symbol mặc định
python scripts/verify_against_source.py

# Symbol cụ thể
python scripts/verify_against_source.py --symbols AAPL VNM VCB

# Toàn bộ universe trong Bronze
python scripts/verify_against_source.py --symbols all --max-symbols 130 --window 25

# Chỉ kiểm tra tầng Gold + API
python scripts/verify_against_source.py --symbols all --layer gold
```

| Tham số | Ý nghĩa |
|---|---|
| `--symbols` | Danh sách symbol, hoặc `all` (lấy từ Bronze) |
| `--layer` | `bronze` / `silver` / `gold` (mặc định cả 3) |
| `--window` | Số phiên gần nhất để so sánh (mặc định 60) |
| `--tolerance` | Sai số giá tương đối coi như là do làm tròn (mặc định `1e-6`) |
| `--api-url` | Base URL của API đang chạy (mặc định `http://127.0.0.1:8000/api/v1`) |
| `--provider` | Provider dùng để re-fetch (mặc định `yahoo_http`) |

**Exit code:** `0` = pass, `1` = có mismatch thật, `2` = không chạy được.

### `scripts/reingest_window.py` — sửa

Khi provider đã **sửa lại** bar cũ của nó (restatement), script verify báo
`RESTATED`. Script này fetch lại đúng cửa sổ đó, append vào Bronze (dedupe
giữ row mới), rebuild Silver + Gold, và invalidate cache của API:

```bash
# xem trước, không ghi
python scripts/reingest_window.py --symbols AAL 005930.KS --days 45 --dry-run

# ghi thật
python scripts/reingest_window.py --symbols AAL 005930.KS --days 45

# lấy danh sách symbol từ output của verify
python scripts/verify_against_source.py --symbols all > verify.txt
python scripts/reingest_window.py --symbols-from verify.txt --days 45
```

### `scripts/verify_layers.py` — kiểm tra tồn tại (nhanh)

```bash
python scripts/verify_layers.py --symbols AAPL MSFT VNM
```

Báo số object / symbol / byte mỗi layer. Dùng để trả lời "symbol này đã
 được ingest chưa", **không** chứng minh giá đúng.

---

## 3. Bốn loại kết quả, và nguyên nhân của từng loại

Script phân biệt 4 loại — vì chúng có **nguyên nhân hoàn toàn khác nhau**:

| Kết quả | Ý nghĩa | Nguyên nhân |
|---|---|---|
| `EXACT` | Khớp chính xác tới xu cuối | Dữ liệu đúng |
| `TOLERANT` | Lệch dưới `--tolerance` | Làm tròn float |
| `STALE` | Bar đúng, nhưng provider đã có session mới hơn | Bar đang forming, hoặc bar bị re-stamp |
| `RESTATED` | Provider đã **sửa lại** bar này sau khi mình ingest | Yahoo tự hiệu chỉnh lịch sử |
| `MISMATCH` | Giá trị lưu trữ **sai** | Bug thật — cần điều tra |

Phân biệt `RESTATED` với `MISMATCH` là điểm mấu chốt:

* **RESTATED** — `open` và `low` vẫn khớp provider, chỉ `close`/`high`/`volume`
  đổi, và mọi field dịch chuyển cùng chiều. Provider đang sửa lại lịch sử của
  chính nó. Lakehouse giữ giá trị **cũ** — tức là giá trị provider đã phục vụ
  đúng vào ngày ingest. Cách sửa: re-ingest cửa sổ đó.
* **MISMATCH** — lệch kiểu không giải thích được bằng việc provider sửa lại.
  Đây là bug.

---

## 4. Vì sao `RESTATED` xảy ra, và tại sao refresh không tự sửa

Refresh pass chỉ fetch lại một cửa sổ nhỏ:

```481:482:backend/app/services/auto_refresh.py
            overlap_days = _env_int("AUTO_REFRESH_OVERLAP_DAYS", 5)
            start = latest_ts.to_pydatetime() - timedelta(days=overlap_days)
```

Nghĩa là nó **không bao giờ chạm tới** một session cũ hơn 5 ngày. Nếu Yahoo
sửa lại một session từ 2 tuần trước, giá trị cũ nằm trong Bronze mãi mãi —
và vì Silver/Gold/API đều dựng từ Bronze, nó cũng nằm trong đó.

Đó chính xác là lý do `reingest_window.py` tồn tại: nó là thao tác *"đi lấy lại
cửa sổ đó"*, điều mà refresh tăng dần không bao giờ làm.

Kết quả đo được ngày 2026-11-03: 15 symbol có bar bị restate
(`000660.KS`, `005380.KS`, `005930.KS`, `009150.KS`, `032830.KS`, `033780.KS`,
`034730.KS`, `051910.KS`, `066570.KS`, `096770.KS`, `AAL`, `ABBN.SW`, `AD.AS`,
`ADS.DE`, `AIR.PA`). Sau khi re-ingest: **0 mismatch, 0 restated**.

---

## 5. Cache của API: cần invalidate sau khi ghi từ ngoài

`MarketService` cache frame của mỗi symbol trong 15 phút, để việc duyệt
nhiều symbol không phải tải lại toàn bộ lakehouse mỗi lần. Nhưng đó là
**rủi ro đúng-sai** cho bất kỳ thứ gì ghi vào lakehouse từ process khác.

Cụ thể: sau khi re-ingest sửa `AIR.PA`, API vẫn trả giá cũ cho `2026-10-19`
(vì cache còn hiệu lực), và một lần verify ngay sau đó báo mismatch **không
tồn tại trong storage**. Đã thêm endpoint để xử lý:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/auto-refresh/cache/invalidate?symbols=AIR.PA"
curl -X POST "http://127.0.0.1:8000/api/v1/admin/auto-refresh/cache/invalidate"   # xoá hết
```

`reingest_window.py` tự gọi endpoint này sau mỗi symbol.

---

## 6. Kiểm tra bổ sung trong script

### Đối chiếu chéo các nguồn trong cùng một symbol

Một symbol có thể được ingest từ nhiều provider (`source` column). Script so
giá của các source đó trên cùng một session:

```
note: cross-source gap 83.6270% between 'yahoo_http' and 'finnhub_ws' on 1 session(s), e.g. 2026-10-07
```

Khoảng cách lớn ở đây là **dữ liệu intraday của `finnhub_ws`**, không phải
lỗi — session đó không có daily bar nào từ `yahoo_http` để đối chiếu, và
script sẽ báo nếu một session **có** daily bar mà hai source vẫn lệch nhau.

Điều đáng lưu ý: `TSLA 2026-10-07` có giá ~210 từ `finnhub_ws` trong khi giá
thật ~377. May mắn là Silver **luôn chọn daily bar** (`yahoo_http`) làm
survivor, nên dữ liệu phục vụ vẫn đúng. Đây là lý do
`app/lakehouse/session.py` phải ưu tiên daily bar — nếu nó chọn row intraday,
giá trên web sẽ sai.

### Số bar mỗi session

Script báo cáo số session và số row của mỗi tầng. Bronze có thể giữ nhiều
row cho một session (intraday tick, bar bị re-stamp) — đó là hợp lệ. Silver và
Gold phải có **đúng 1 row mỗi session**. Nếu không, mọi rolling indicator
(RSI, MACD, Aroon) đều bị lệch.

---

## 7. Quy trình kiểm chứng định kỳ

```bash
cd backend

# 1. Kiểm chứng toàn bộ universe (mất vài phút cho ~130 symbol)
python scripts/verify_against_source.py --symbols all --max-symbols 130 --window 25

# 2. Nếu có RESTATED, lấy danh sách symbol và sửa
python scripts/verify_against_source.py --symbols all --max-symbols 130 --window 25 > verify.txt
python scripts/reingest_window.py --symbols-from verify.txt --days 45

# 3. Verify lại để chắc chắn
python scripts/verify_against_source.py --symbols all --max-symbols 130 --window 25
```

Kết quả sau khi chạy trên 130 symbol ngày 2026-11-03:

```
  symbols checked : 130
  exact matches   : 12870
  tolerant        : 0
  stale/explained : 130   (bar mới nhất đang forming)
  restated        : 0
  MISMATCHES      : 0
  errors          : 0

VERDICT: PASSED - every checked bar matches the live provider.
```

---

## 8. Nguồn ô nhiễm đã tìm thấy và đã xoá (2026-11-04)

Kiểm chứng bằng cách so với provider là **điều kiện cần**, nhưng nó không đủ:
một symbol có thể khớp provider ở mọi session *được kiểm tra* mà vẫn chứa dữ
liệu bịa ở những session **không** ai kiểm tra. Vì vậy cần một lớp kiểm tra
thứ hai: **quét toàn bộ Bronze tìm row không khớp bất kỳ provider nào**.

Kết quả quét ngày 2026-11-04 trên 1.002 symbol / 2.3 triệu row:

| Nguồn row | Số symbol | Số row | Bản chất |
|---|---|---|---|
| `yahoo_http` | 981 | 2.316.846 | daily bar thật |
| `finnhub_ws` | 9 | 17.348 | **tick của instrument KHÁC** |
| `ssi_vn` | 9 | 17.335 | daily bar thật (nhưng bị gán nhãn sai) |
| `vn_rest` | 12 | 5.527 | tick 1 phút thật |
| `yfinance_python` | — | 2.513 | daily bar thật |
| `alpha_vantage` | — | 2.131 | daily bar thật |
| `manual` | 3 | 18 | **giá gõ tay** |

### 8.1 `finnhub_ws` — gán nhầm instrument

WebSocket của Finnhub đã gán trade của **mã khác** vào symbol. Chuỗi giá bên
trong *liên tục* (975 → 962 → 952 → 971), nên đây là trade thật của một mã
khác, không phải nhiễu. Đo ngày 2026-10-07:

| symbol | khoảng giá đã lưu | giá thật ngày đó |
|---|---|---|
| NVDA | 855 – 1938 | **237.47** |
| TSLA | 68 – 283 | **377.81** |
| WMT | 55 – 103 | **108.16** |
| COIN | 72 – 125 | **178.45** |
| BTC-USD | 48072 – 97762 | **83275.93** |

Symbol nào **có** daily bar thì không sao (daily bar thắng, tick bị loại khi
canonicalize). Symbol nào **không** có daily bar thì chart hiện giá sai. Và
đó đúng là ba symbol mà auto-refresh không bao giờ quét tới — vì
`CRYPTO_SYMBOLS` không nằm trong universe refresh.

### 8.2 `manual` — giá gõ tay từ nút "demo"

Trang Live Stream có một panel "demo" đẩy 3 bar gõ tay mỗi mã (AAPL ~332.5,
MSFT ~415.2, NVDA ~510.0) qua `POST /api/v1/stream/ingest` → Kafka → Bronze.
18 row đó tới được Bronze với `source = "manual"` và **không có gì phân biệt
được chúng với một print thật**.

### 8.3 `ssi_vn` — nguồn thật nhưng bị phân loại sai

SSI iBoard trả **một bar cả ngày**, nhưng `ssi_vn` không có trong
`DAILY_BAR_SOURCES`, nên hệ thống tưởng đó là tick intraday. Hậu quả: Gold
chứa 2.497 row cho `PVB`, 2.497 cho `VCS`, 2.487 cho `HNG` — trong khi mỗi
symbol chỉ có ~1 bar/ngày.

### 8.4 `vn_rest` — tick thật, nhưng không thuộc tầng daily

5.527 row tick 1 phút từ SSI REST. Giá đúng, nhưng lakehouse chỉ phục vụ daily
bar, và daily provider cung cấp đúng các session đó.

### 8.5 Cách sửa

```bash
cd backend

# 1. Xoá row bịa / gán nhầm khỏi Bronze (dry-run trước)
python scripts/purge_fabricated_rows.py
python scripts/purge_fabricated_rows.py --apply

# 2. Dựng lại Silver + Gold từ Bronze đã sạch
python scripts/backfill_silver_gold.py --symbols AAPL BID BTC-USD COIN CTG \
    ETH-USD FPT HPG MSFT MSN MWG NVDA TSLA UNH V VCB VHM VIC VNM WMT XOM

# 3. Fetch lại các session bị xoá, từ provider thật
python scripts/reingest_window.py --symbols AAPL BID BTC-USD COIN CTG \
    ETH-USD FPT HPG MSFT MSN MWG NVDA TSLA UNH V VCB VHM VIC VNM WMT XOM --days 45
```

Bước 3 là bắt buộc: sau khi xoá, những session đó **trống** chứ không sai.
Một bar thiếu thì trung thực; một bar sai thì không.

### 8.6 Guard đã thêm để không tái diễn

* `DAILY_BAR_SOURCES` giờ có `ssi_vn`.
* `plausibility.py` có `STREAM_PRICE_DEVIATION_FACTOR = 2.5`: một tick
  streaming nằm cách giá của chính symbol quá 2.5 lần bị loại. (Cùng một
  session, nên không thể xa giá như vậy.) Bản 100x trước đó quá lỏng — nó
  không bắt được NVDA (855 vs 237 = 3.6 lần) và TSLA.
* `POST /api/v1/stream/ingest` **mặc định trả 403**. Nó chỉ mở khi
  `ALLOW_STREAM_INGEST=true`, và chỉ dành cho smoke test local.
* Panel "demo" đã bị xoá khỏi `LiveStream.tsx`.
* `CRYPTO_SYMBOLS` (giờ gồm cả `COIN`) đã vào universe của auto-refresh, nên
  crypto không còn đứng ngoài và bị bỏ quên.

---

## 9. Giới hạn của phương pháp này

Nói thẳng để không tạo cảm giác an toàn giả:

* **Chỉ kiểm tra được những gì provider vẫn phục vụ.** Yahoo giữ ~10 năm
  daily bars; lịch sử sâu hơn không re-fetch được. Tầng `STALE` cũng có thể do
  provider đã *xoá* session (delisting) chứ không phải do bar forming.
* **Provider có thể sai.** "Khớp với Yahoo" nghĩa là "khớp với Yahoo", không
  phải "đúng với thị trường". Với giá niêm yết, Yahoo là nguồn đáng tin độc
  lập — nhưng nó không phải sàn giao dịch.
* **Số so sánh là cửa sổ gần nhất** (`--window`). Lịch sử cũ hơn không được
  kiểm tra lại mỗi lần; nó được tin là đã đúng từ lần ingest.
* **Script kiểm tra giá và volume.** Không kiểm tra chỉ báo kỹ thuật — RSI/MACD
  tính từ đúng series đã được xác nhận là đúng.
* **`cross-source gap` không tự động là lỗi.** Nó là cảnh báo để con người
  nhìn; script không phán đoán.
* **Quét toàn bộ Bronze là việc tốn thời gian** (~10 phút cho 1.002 symbol vì
  phải tải từng partition). Nên nó là một lần kiểm tra định kỳ, không phải
  thứ chạy mỗi request.
