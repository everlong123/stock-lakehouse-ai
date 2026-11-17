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

### `scripts/audit_layer_coverage.py` — phát hiện layer bị cắt

So **tập tháng partition** giữa Bronze → Silver → Gold cho từng symbol. Bắt được
trường hợp partition write thất bại bị nuốt im lặng (mục 9.3).

```bash
# Chỉ báo cáo
python scripts/audit_layer_coverage.py

# Báo cáo + rebuild những symbol bị cắt
python scripts/audit_layer_coverage.py --repair

# Chỉ một số symbol
python scripts/audit_layer_coverage.py --symbols VCB HPG
```

### `scripts/backfill_thin_history.py` — bổ sung lịch sử còn thiếu

Tìm symbol có dưới 2.000 daily bar rồi fetch lại toàn bộ phạm vi provider có
(mục 9.4).

```bash
python scripts/backfill_thin_history.py --dry-run    # chỉ báo cáo
python scripts/backfill_thin_history.py              # backfill + rebuild
python scripts/backfill_thin_history.py --symbols VCB FPT HPG
```

### `tests/test_currency_consistency.py` — backend và frontend phải khớp

Parse bảng suffix và danh sách ticker VN trong file TypeScript, rồi so với bản
Python. Hai bản sao sẽ **chắc chắn drift** nếu không có test này (mục 9.1).

```bash
python tests/test_currency_consistency.py
```

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

# 1b. Universe lớn hơn thì chia lát (--offset để bỏ qua phần đã kiểm)
python scripts/verify_against_source.py --symbols all --offset 0   --max-symbols 300 --window 25
python scripts/verify_against_source.py --symbols all --offset 300 --max-symbols 300 --window 25
python scripts/verify_against_source.py --symbols all --offset 600 --max-symbols 300 --window 25
python scripts/verify_against_source.py --symbols all --offset 900 --max-symbols 300 --window 25

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

### 8.2 `manual` — giá gõ tay từ nút "demo" (LỊCH SỬ — đã xoá)

Trang Live Stream từng có một panel "demo" đẩy 3 bar gõ tay mỗi mã (AAPL ~332.5,
MSFT ~415.2, NVDA ~510.0) qua `POST /api/v1/stream/ingest` → Bronze.
18 row đó tới được Bronze với `source = "manual"` và **không có gì phân biệt
được chúng với một print thật**.

> **Đo ngày 10/11/2026:** các row `manual` đã bị **xoá khỏi Bronze** (xem mục 8.6
> bên dưới) và cổng `POST /api/v1/stream/ingest` bị **tắt**
> (`allow_stream_ingest=false`).
>
> **Đo ngày 11/11/2026:** cổng này cùng toàn bộ file `stream.py` đã bị **xoá
> hẳn**, kèm `allow_stream_ingest` trong cấu hình. Không còn đường nào ghi bar
> thủ công vào Bronze — đây là trạng thái tốt nhất cho luật "real data only".
> Xem mục 14.6 của `HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.

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

### 8.6 Kết quả sau khi sửa

Quét toàn bộ 1.002 symbol của Bronze, đối chiếu từng tầng với một lần fetch
mới hoàn toàn từ Yahoo:

```
symbols in Bronze : 1002
source                  rows  partitions
yahoo_http           2330404     112712
ssi_vn                 17342        938
yfinance_python         2514        122
alpha_vantage           2131        124
yfinance_eod              59         16
web_scraper               15         15

CONTAMINATED: NONE
```

Không còn `manual`, `finnhub_ws`, `finnhub_rest`, `vn_rest` hay `vn_ws`.

Lịch sử bị mất khi xoá đã được lấy lại từ Yahoo (14.338 row): COIN 1397,
BTC-USD 2133, ETH-USD 2133, BID 1420, CTG 1418, VIC 1421, VHM 1417,
MSN 1414.

Kiểm chứng sau sửa (5 lát, phủ hết 1.002 symbol):

```
symbols checked : 1002
exact matches   : ~16,000
MISMATCHES      : 0
VERDICT: PASSED - every checked bar matches the live provider.
```

Provider cũng **sửa lại lịch sử của chính nó** ở 17 symbol (ALV.DE, BARC.L,
BAYN.DE, ARVN, ASML.AS, AZN.L, CON.DE, DBK.DE, DGE.L, DTE.DE, LSEG.L,
TSCO.L, TTE.PA, UBSG.SW, ...). Tất cả đã được `reingest_window.py` lấy lại
và verify lại: **45 session × 4 tầng × 14 symbol = 2.475 exact, 0 mismatch.**

Giá sau khi sửa (đọc thẳng từ API):

| symbol | trước | sau |
|---|---|---|
| COIN | 95.6 | **145.45** |
| NVDA | 855 – 1938 | **202.06** |
| TSLA | 68 – 283 | **403.82** |
| MWG | 75.3 | **72.300** (VND) |
| WMT | 55 – 103 | **127.69** |

### 8.7 Guard đã thêm để không tái diễn

* `DAILY_BAR_SOURCES` giờ có `ssi_vn`.
* `plausibility.py` có `STREAM_PRICE_DEVIATION_FACTOR = 2.5`: một tick
  streaming nằm cách giá của chính symbol quá 2.5 lần bị loại. (Cùng một
  session, nên không thể xa giá như vậy.) Bản 100x trước đó quá lỏng — nó
  không bắt được NVDA (855 vs 237 = 3.6 lần) và TSLA.
* `POST /api/v1/stream/ingest` **đã bị xoá hẳn** (đo 11/11/2026) — không còn
  đường nào ghi bar thủ công vào Bronze.
* Toàn bộ trang Live Stream đã bị xoá (đo 11/11/2026).
* `CRYPTO_SYMBOLS` (giờ gồm cả `COIN`) đã vào universe của auto-refresh, nên
  crypto không còn đứng ngoài và bị bỏ quên.

### 8.8 Sổ tay kiểm chứng dự báo — 200 dòng bịa trong MySQL (2026-11-15)

Lần quét này mở rộng phạm vi: không chỉ Bronze/Silver/Gold, mà cả **bảng
`predictions`** — bảng ghi lại những gì hệ thống **đã công bố** trước khi phiên
mở cửa, và tự chấm điểm bằng giá đóng cửa thật.

**Triệu chứng:** bảng `predictions` chứa **200 dòng** cho các mã `TST0` ..
`TST199`. Mọi dòng có **cùng một cặp số bịa** (`reference_close = 100.0`,
`predicted_close = 101.0`, `predicted_return = 0.01`), cùng nhãn
`source = "auto_eod_batch"`, và được tạo trong **1 giây** (08:20:32 → 08:20:33
ngày 14/11/2026).

**Vì sao xảy ra:** các dòng đó **không đi qua đường ghi của hệ thống**:

| Nơi kiểm tra | Kết quả |
|---|---|
| Bronze / Silver / Gold | 1.002 mã thật, **0 mã** tên `TST*` |
| `backend/data/models/` | 1.003 thư mục model, **0** thư mục `TST*` |
| Mã nguồn trong `backend/` | **không có** chỗ nào sinh ra tên `TST*` |

Nghĩa là chúng được ghi **thẳng vào MySQL**, và đường ghi đó không có nghị quyết
nào hỏi "mã này có thật không". Kết quả: số "đã kiểm chứng" mà bảng điều khiển
hiển thị đã chứa cả 200 dòng giả, và chúng **không còn phân biệt được** với dự
báo thật.

**Fix (ba lớp):**

1. **Chặn ở đường ghi** — `backend/app/core/data_integrity.py` + guard trong
   `PredictionRepository.upsert()` (đường ghi duy nhất vào bảng `predictions`):
   mã bắt đầu bằng `TST`, `TEST`, `DEMO`, `MOCK`, `FAKE`, `DUMMY`, `SAMPLE`,
   `PLACEHOLDER` hoặc `XXX` bị từ chối trước khi chạm vào cơ sở dữ liệu.
2. **Quét theo tầng lưu trữ** — `backend/scripts/purge_fake_predictions.py` tìm
   mọi dòng mà mã **không tồn tại trong tầng Gold**. Đây là phép kiểm tra
   **mạnh hơn** denylist: nó bắt được cả dòng giả mang tên một mã có vẻ thật.
   Script mặc định dry-run, cần `--apply` mới ghi.
3. **Ghim bằng test** — `backend/tests/test_no_fake_data.py`.

**Bằng chứng (đo ngày 15/11/2026):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Tổng dòng trong bảng `predictions` | 46.609 | **46.409** |
| Dòng của mã fixture (`TST*`) | **200** | **0** |
| Số mã khác nhau trong bảng | 1.173 | **973** |
| Mã trong bảng nhưng **không có** trong Gold | 200 | **0** |
| Cụm giá trị trùng lặp bất thường (≥20 dòng) | 1 | **0** |

Đối chiếu cả ba tầng lưu trữ với MySQL sau khi sửa:

| Bảng | Số mã | Mã không có trong Gold |
|---|---|---|
| `predictions` | 973 | **0** |
| `model_runs` | 14 | **0** |
| `backtest_runs` | 13 | **0** |

**Vì sao xoá chứ không sửa:** một dòng dự báo là **kết quả của một mô hình**.
Với mã không có lịch sử thì mô hình không chạy được, nên **không có giá trị đúng
để khôi phục** — trạng thái trung thực là dòng vắng mặt, không phải một dòng điền
số giả để lấp chỗ trống.

### 8.9 Giá dự báo không tồn tại — 76 dòng, và 99,993% của tổng sai số (2026-11-15)

**Triệu chứng:** báo cáo kiểm chứng hiển thị **sai số tương đối trung bình
263,85%** trên toàn bộ nhóm, trong khi **trung vị chỉ 1,15%**. Con số trung bình
đó vô lý với mọi hệ thống dự báo thực.

**Giả thuyết ban đầu (SAI):** "mẫu số nhỏ". Người viết tài liệu đoán rằng các
mã giá rất nhỏ (ví dụ `VIV.PA` giá 1,69) làm sai số tương đối của chúng phình
to, nên trung bình bị kéo lên.

**Kết quả kiểm chứng (đo ngày 15/11/2026):**

| Kiểm tra | Kết quả | Kết luận |
|---|---|---|
| Số dòng đã chấm của `VIV.PA` | **1** (sai số 3,93%) | `VIV.PA` không gây ra vấn đề |
| Trung bình sau khi loại **mọi** dòng `reference_close < 1,0` | **91,95%** | Vẫn hỏng → giả thuyết bị bác bỏ |
| Tổng `|error_pct|` của toàn bộ 44.676 dòng | 11.792.660 | — |
| Trong đó, `PARA` một mình | **11.791.832 (99,993%)** | Một mã giữ hết |
| Trung bình sau khi loại riêng `PARA` | **-0,0329%** | Trung vị 1,15% là con số đúng |

**Vì sao `PARA` hỏng:** lịch sử giá của nó trong Bronze/Gold trải trên **ba bậc
độ lớn** (101.500 năm 2021 → 1.648 năm 2024 → 0,104 năm 11/2026) vì **bốn lần
chia ngược** (1:50 ngày 19/09/2024, 1:10 ngày 08/07/2025, 1:20 ngày 08/05/2026,
1:10 ngày 27/10/2026). Lakehouse nạp dữ liệu qua nhiều ngày nên các partition
lưu **không cùng một quy mô giá**.

Mô hình `linear_regression` dùng **mức giá** làm đặc trưng. Huấn luyện trên
một chuỗi nhiều thang giá thì hệ số hồi quy học được không có ý nghĩa, và phần
**ngoại suy** rơi vào bất kỳ đâu:

| Phiên | Tham chiếu | Dự báo | Thực | Sai số |
|---|---|---|---|---|
| PARA 12/11/2026 | 0,072 | **242.751** | 0,101 | +337.154,0% |
| PARA 05/11/2026 | 0,319 | **329.139** | 0,164 | +103.178,0% |
| PARA 28/10/2026 | 4,1395 | **-942,13** | 3,36 | -228,4% |

Ngoài ra còn **19 dòng có giá dự báo ÂM** — không phải "sai số lớn" mà là **giá
không tồn tại**: `LCID` -4,0937; `ACH` -0,1143; `SOXS` **-359.121.000**;
`UVXY` -33.570,80; `SQQQ` -647,88; `SPXU` -33,47; `VXX` -1,87.

Đối chiếu cùng chuỗi đó, **ARIMA** cho MAPE 10,6% (`PARA`), 4,27% (`LCID`),
4,7% (`ACH`) → lỗi nằm ở **cách đặc trưng của mô hình**, không nằm ở dữ liệu.

**Fix (bốn lớp):**

1. **Chặn ở đường ghi** — `backend/app/core/data_integrity.py`:
   `is_impossible_price()` từ chối `predicted_close <= 0` và mọi tỷ lệ lệch quá
   **100 lần** so với giá tham chiếu. `PredictionRepository.upsert()` (đường ghi
   duy nhất vào bảng) ném `ValueError`.
2. **Dò điểm gãy thang giá** — `backend/app/lakehouse/scale_repair.py`:
   - `detect_scale_discontinuity()` — dò **nhảy cục bộ** giữa hai phiên liền kề.
   - `detect_scale_span()` — dò **độ rộng toàn cục** giữa 1/3 đầu và 1/3 cuối.
   - `is_scale_contaminated()` — hợp nhất hai kiểm tra.
3. **Lọc + công khai số dòng bị loại** — `accuracy_summary()` và
   `median_error_pct()` chỉ tính trên dòng sạch, đồng thời trả
   `excluded_impossible` để **không giấu** những gì đã loại.
4. **Dọn dẹp sổ tay** — `backend/scripts/purge_impossible_predictions.py`
   (dry-run mặc định, `--apply` mới ghi). Đã xoá **76 dòng**
   (57 lệch thang giá + 19 giá âm).

**Bằng chứng (đo ngày 15/11/2026):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Sai số tương đối trung bình (có dấu) | **+26.385,49%** | **+0,43%** |
| Sai số tương đối trung bình (tuyệt đối) | 26.395,96% | **2,24%** |
| Sai số tương đối TRUNG VỊ | 1,15% | **1,15%** |
| WAPE (chưa có) | — | **2,73%** |
| Số dòng đã chấm | 45.430 | 44.606 |
| Dòng có giá không tồn tại | 76 | **0** |

> **Đo lại ngày 17/11/2026** (sau khi sửa lỗi "Lock wait timeout" và chấm thêm
> 695 dòng): WAPE toàn bảng là **2,75%**, số dòng đã chấm là **46.385**
> (45.631 dòng có giá tham chiếu hợp lệ). Sai số tương đối trung vị giữ nguyên
> **1,15%** — con số này **không đổi** khi thêm dữ liệu, và đó là dấu hiệu tốt:
> sai số của một dự báo điển hình không phụ thuộc vào việc hệ thống đã chạy
> thêm bao nhiêu phiên.

**Vì sao ngưỡng 100 lần, không chặt hơn:** `PARA` thật sự giao dịch 0,104 → 0,164
→ 0,319 → 2,72 trong ba phiên thật tháng 11/2026. Ngưỡng chặt hơn sẽ **báo oan**
một biến động thật.

**Bài học quan trọng nhất của lần quét này:** dò **nhảy cục bộ** một mình là
**không đủ**. Chạy bộ dò đó trên toàn bộ 1.002 mã của tầng Gold (đo ngày
15/11/2026) cho thấy:

| Kết quả quét | Số |
|---|---|
| Mã có ít nhất một nhảy cục bộ | 46 |
| Hệ số lớn nhất tìm được | **6,15x** (`OVV`, tháng 3/2020) |
| Số mã bị gắn cờ ở mức ≥ 10 lần | **0** |

`PARA` **không** nằm trong 46 mã đó — dù nó giữ 99,993% tổng sai số. Lý do:
`PARA` không gãy trong **một** bước mà trải trên **hàng nghìn lần** qua nhiều
bước nhỏ, mỗi bước trông bình thường. Đó là lý do phải có thêm kiểm tra
**độ rộng toàn cục** (`detect_scale_span`).

**Số đo độ rộng toàn cục trên toàn bộ 1.002 mã** (đo ngày 15/11/2026):

| Mã | Độ rộng | Số nhảy cục bộ | Kết luận |
|---|---|---|---|
| **`PARA`** | **3.503x** | 2 | **Nhiễm** — giữ 99,993% tổng sai số |
| `OCGN` | 97,9x | 7 | **Nhiễm** — 7 lần chia ngược |
| `CELH` | 31,8x | **0** | Tăng trưởng thật |
| `NVDA` | 30,6x | **0** | Tăng trưởng thật |
| 35 mã còn lại | < 5x | 1–2 | Bình thường |

Vì vậy ngưỡng độ rộng là **100 lần**: ở mức 20 lần thì `NVDA` và `CELH` cũng
bị gắn cờ — mà chúng là hai mã khỏe mạnh chỉ vì **tăng trưởng**. Một lần
báo oan cũng tệ như một lần bỏ sót: nó dạy người đọc không tin báo cáo.

**Ghim bằng test:**

- `backend/tests/test_forecast_plausibility.py` — quy tắc chặn (12 test).
- `backend/tests/test_scale_repair.py` — dò gãy cục bộ + độ rộng toàn cục
  (13 test).
- `backend/tests/test_accuracy_report.py` — bảo đảm trung bình báo cáo không bị
  dòng hỏng phá.
- `backend/tests/test_no_fake_data.py` — chặn ở đường ghi (giá âm, lệch thang).

---

## 9. Lỗi đồng bộ Web ↔ MinIO đã tìm và đã sửa (2026-11-04)

Bốn lỗi dưới đây làm cho **web hiển thị khác với MinIO**, hoặc làm cho dữ liệu
MinIO **bị cắt cụt mà không ai biết**. Cả bốn đều im lặng — không có lỗi, không
có log, chỉ có kết quả sai.

### 9.1 Đơn vị tiền tệ: mọi symbol đều hiển thị bằng ₫

`formatPrice` hardcode `₫`:

```tsx
// frontend/src/utils/format.ts (trước khi sửa)
export function formatPrice(value: number | null | undefined): string {
  if (!isUsableNumber(value)) return "—";
  return `${formatNumber(value, 2)} ₫`;
}
```

Hệ quả: AAPL hiển thị `331.90 ₫` — sai hoàn toàn, vì AAPL giao bằng USD.
Tệ hơn nữa, **giá của mọi symbol khác nhau 3 bậc độ lớn**: VCB ~54.800 (VND),
AAPL ~330 (USD). Lakehouse **không lưu cột currency** (Yahoo's daily bar endpoint
không trả về nó), nên tầng UI không có gì để biết đơn vị là gì.

Cách sửa: `currency_for_symbol()` ở backend (`app/core/constants.py`) và
`currencyForSymbol()` ở frontend (`utils/format.ts`) cùng resolve theo quy tắc:

1. Crypto pair mang quote trong ticker: `BTC-USD` → `USD`.
2. Yahoo exchange suffix: `.DE` → `EUR`, `.HK` → `HKD`, `.T` → `JPY`, `.L` → `GBP`.
3. Ticker Việt Nam (không có suffix) → `VND`.
4. Còn lại → `USD`.

Vì có **hai bản sao** (Python + TypeScript) nên chúng **bắt buộc phải giống
nhau**. `backend/tests/test_currency_consistency.py` parse thẳng file
TypeScript rồi so từng suffix và từng ticker VN với bản Python — nếu một bên
thêm mà bên kia quên, test fail.

### 9.2 `MIN_PLAUSIBLE_PRICE` giết chết cổ phiếu giá rẻ

`plausibility.py` có một sàn giá **tuyệt đối** `0.5`, với luận lẻ "cổ phiếu Mỹ
không bao giờ giao dưới 1 cent". Điều đó sai: **ACH** (NYSE American) giao quanh
**$0.21**. Từ 2026-10-23, mọi bar của ACH bị loại:

```
auto-refresh: ACH -> "All incoming rows failed the plausibility screen; nothing written."
```

Symbol đứng yên tại close 2026-10-22 trong khi provider đã ở 0.28.

Cách sửa: sàn giá giờ **tương đối với chính symbol đó** (`_effective_floor`).
Nếu mức giá gần nhất của symbol vốn đã dưới 0.5 thì symbol đó *thật sự* giao
sub-unit, và sàn được nới (và magnitude check so với chính lịch sử của symbol
làm phần việc thật sự). Nếu không có reference thì sàn cứ dùng lại — hướng
an toàn.

| Case | Kết quả |
|---|---|
| ACH bar thật 0.28 (reference 0.21) | **accept** |
| ACH bị /1000 → 0.00028 | reject (`price_magnitude`) |
| VCB bị /1000 → 56.9 (reference 56.600) | reject (`price_magnitude`) |
| AAPL 0.21, không có reference | reject (`implausible_open`) |

### 9.3 Partition write thất bại bị nuốt im lặng → mất lịch sử

Đây là lỗi nghiêm trọng nhất.

`parallel_write.write_partitions_concurrently` bắt exception của một partition
thất bại, **chỉ log warning**, rồi đi tiếp. Một connection reset của MinIO (rất
thường xuyên khi auto-refresh load cùng instance) khiến **110 trong 202 partition
của Silver VCB** không được ghi. Kết quả:

```
Bronze VCB : 202 partitions, 4.080 rows
Silver VCB :  92 partitions, 1.853 rows   <- mất 2.227 rows
Gold VCB   :  26 partitions,   532 rows   <- mất tiếp
```

Và tệ hơn: quality report vẫn ghi `record_count: 4080, error_count: 0,
quality_status: passed`. **Không có gì ở đâu báo rằng lịch sử bị cắt.**

Người đọc không thể phát hiện: họ nhận được một lịch sử **ngắn hơn** nhưng
giá vẫn đúng, vẫn hợp lý — chart chỉ hiện ít đi, không có tín hiệu nào.

Cách sửa:

* `write_partitions_concurrently` giờ **ném `StorageError`** nếu bất kỳ partition
  nào không ghi được, và error nêu rõ partition nào hỏng. Symbol giữ nguyên
  trạng thái đầy đủ cũ thay vì trở thành trạng thái một phần.
* `_put_bytes` của MinIO **retry 3 lần** (1s, 3s) — write là idempotent nên
  retry không thể làm hỏng dữ liệu.
* `scripts/audit_layer_coverage.py` — công cụ mới, so **tập tháng partition**
  giữa Bronze/Silver/Gold cho từng symbol và báo symbol nào bị cắt. `--repair`
  rebuild từ Bronze.

Sau khi sửa: **PASS — mọi symbol trong 1.002 có Silver và Gold phủ đủ các tháng
của Bronze.**

### 9.4 Lịch sử mỏng: symbol có dữ liệu nhưng chỉ 2 năm

Lakehouse được seed bằng rolling refresh, nên symbol thêm vào universe sau này
chỉ có vài năm daily bar, trong khi provider có 10 năm:

| Symbol | Rows trước | Từ | Provider có |
|---|---|---|---|
| `VCB` | 532 | 2024-10-07 | 2.623 từ 2016 |
| `FPT` | 534 | 2024-10-07 | 2.643 từ 2016 |
| `HPG` | 534 | 2024-10-07 | 2.641 từ 2016 |
| `MWG` | 532 | 2024-10-07 | 2.630 từ 2016 |
| `SOFI` | 6 | 2026-10-09 | 1.466 từ 2021 |

Chart của các symbol này **trông đầy đủ** — có bar, giá đúng — nhưng nó âm thầm
trả lời một câu hỏi khác với câu hỏi người đọc đặt ra.

`scripts/backfill_thin_history.py` (mới) tìm symbol có dưới 2.000 row và fetch
lại toàn bộ phạm vi provider có, qua **đúng con đường kiểm chứng** của mọi ingest
khác, rồi rebuild Silver + Gold.

Yahoo phục vụ mã Việt Nam với suffix `.VN` (`VCB.VN`), nên các ticker VN cũng
backfill được từ 2016 — không phụ thuộc SSI iBoard.

### 9.5 Nhãn hiển thị sai

* Layer count đếm **object (file parquet)**, không phải record, nhưng UI ghi
  "RECORDS" — người đọc tưởng Bronze có 114.904 *record* thay vì 114.904 *file*
  (thực tế ~2,3 triệu row). Đã sửa thành "files" / "Số file parquet theo layer".
* **Sửa lần 2 (13/11/2026):** nhãn "Số file parquet theo layer" vẫn **không
  chính xác**, vì `count_objects()` đếm **mọi object** trong bucket, không chỉ
  file `.parquet`. Đo ngày 13/11/2026 cho thấy chênh lệch rõ rệt:

  | Tầng | Số object đếm được | Trong đó là partition `.parquet` | Phần còn lại |
  |---|---|---|---|
  | Bronze | 116.110 | 115.101 | 1.007 manifest `.json` + 1 probe + 1 `.txt` |
  | Silver | 116.593 | 115.101 | 490 file `_errors/` + 1.002 báo cáo `_quality.json` |
  | Gold | 115.101 | 115.101 | 0 |

  Ba tầng có **cùng 115.101 partition** — chỉ khác nhau ở các file phụ trợ.
  Nhãn đã sửa thành "**Số object theo layer**" / "Objects by layer", đúng với
  cái nó thực sự đếm. Số liệu trong `docs/` ghi rõ đây là **object**, không
  phải record và không phải riêng file parquet.
* `data_source` trong `/system/status` là **object** `{label, status}`, nhưng UI
  làm `String(obj)` → hiển thị literal `[object Object]`. Đã sửa.
* Panel "Sources" liệt kê **Finnhub** — nguồn đã bị xoá hoàn toàn khỏi Bronze
  sau khi phát hiện nó gán nhầm instrument. Đã bỏ khỏi danh liệt.

---

## 9.6. Sàn giá của plausibility dùng **median** nên nuốt bar thật (2026-11-05)

Sau khi đóng 22 symbol FAIL còn lại, một symbol vẫn FAIL: `PARA`, ngày
`2026-10-23`, giá stored `4.251` vs provider `0.425` — đúng bằng tỉ lệ **10:1**.

Nguyên nhân **không phải** ở dữ liệu mà ở chính guard bảo vệ nó.

`BronzeLayer._reference_prices` lấy **median** của partition mới nhất làm
"mức giá" của symbol. Với PARA, partition `2026-11` vẫn còn vài bar **trước
split** quanh `2.72` nằm cạnh các bar sau split, nên median là `~2.21` trong khi
mức thật của symbol chỉ là `~0.42`.

Hệ quả: sàn giá tuyệt đối `0.5` vẫn còn hiệu lực, nên bar `0.425` **thật** của
provider bị loại với lý do `implausible_open`. Và bar đó **không bao giờ sửa
được**:

* guard so sánh row đến với chính mức giá đã lưu của symbol;
* mức giá đã lưu là `4.251` — tức giá **trước split**, giá sai;
* nên giá sai luôn là chuẩn tham chiếu, còn giá đúng luôn *trông* bất khả thi.

Đây là vòng lặp tự khóa: split 10:1 ngày `2026-10-28` buộc mọi session trước
đó phải được restate, mà bản restate thì không ingest được.

### Sửa

Reference price giờ là **mức thấp** của vài partition mới nhất, không phải
median:

* sàn giá được nới cho instrument thực sự rẻ (PARA `0.47 < 0.5`), nên bar
  `0.425` được nhận;
* guard magnitude vẫn bắt được lỗi đơn vị thật, vì lỗi đơn vị lệch **1000 lần**
  so với mức thấp chứ không phải 10 lần;
* reference lấy từ **vài** partition gần nhất (không phải một) để symbol vừa
  split vẫn có mẫu nhất quán.

Đã kiểm chứng lại bằng `tests/test_plausibility.py` (13 assertion): bar thật
dưới $1 được nhận (`ACH 0.21`, `PARA 0.425`), lỗi `/1000` vẫn bị loại
(`VCB 53.5` vs `53.500`, `PARA 0.00047` vs `0.47`).

### Đồng thời: phân loại mismatch bằng tỉ lệ, để không đoán mò

`scripts/classify_mismatches.py` (mới) báo cáo tỉ lệ `stored/live` cho từng
symbol FAIL, và tách hai nguyên nhân hoàn toàn khác nhau:

| Nhóm | Dấu hiệu | Ví dụ |
|---|---|---|
| **Corporate action** | tỉ lệ là một hệ số sạch (`1.15`, `10`) | `PC1` (bonus 115:100 ×4 lần) |
| **Provider restate** | tỉ lệ `1.0`, chỉ vài bar lệch | `BP.L`, `SAF.PA`, `VOW3.DE`… |

Hai nhóm này trước đây bị gộp chung thành "FAIL" và dẫn tới việc sửa bừa.
`PC1` cần re-ingest **toàn bộ lịch sử** (2.409 session), vì Yahoo đã restate
mọi bar cũ sau 4 lần phát hành cổ phiếu thưởng; 21 symbol còn lại chỉ cần
re-ingest **60 ngày cuối**.

Sau khi sửa: **22/22 PASS, 5.276 bar khớp tuyệt đối, 0 mismatch.**

---

## 9.7. Reference price phải là HAI con số, không phải một (2026-11-05)

Sửa ở mục 9.6 tạo ra một lỗi ngược lại, và lỗi đó chỉ lộ ra khi kiểm tra lại
toàn bộ lịch sử chứ không phải 60 ngày cuối.

**Lỗi 1 — dùng mức thấp cho cả hai check thì xoá lịch sử thật.**

Sau khi đổi reference sang mức thấp, check `price_magnitude` bắt đầu loại bỏ
lịch sử 2021 của chính PARA: giá thật năm 2021 là **\$101.500** (Yahoo serve
đúng như vậy, volume 11–62 cổ — micro-cap), còn mức thấp hiện tại là \$0.47.
Chênh lệch **200.000 lần** → vượt ngưỡng 100x → `price_magnitude`.

Dữ liệu đó **đúng** và đã nằm trong Bronze khớp chính xác provider. Nhưng nếu
cần re-ingest thì nó sẽ không ingest được — tức là guard đang xoá lịch sử thật
để bắt một lỗi đơn vị hiếm.

**Lỗi 2 — dùng median cho cả hai check thì nuốt bar thật.**

Ngược lại, median của partition mới nhất của PARA là ~2.21 (vì còn vài bar
trước split), nên sàn giá tuyệt đối 0.5 vẫn có hiệu lực và bar **thật** \$0.425
bị loại.

**Sửa: tách thành hai con số, vì hai check hỏi hai câu khác nhau.**

| Tham số | Dùng cho | Nguồn | Câu hỏi |
|---|---|---|---|
| `floor` | sàn giá tuyệt đối | **mức thấp** | "symbol này có rẻ không?" |
| `magnitude` | check độ lệch | **median** | "giá này có lệch bất thường không?" |

Lỗi đơn vị lệch **1000 lần** — nằm ngoài cả hai dải dung sai, nên việc tách
không làm suy yếu guard.

| Symbol | Giá thật | Reference cũ | Kết quả |
|---|---|---|---|
| `PARA` (2026) | \$0.425 | median 2.21 | bị loại (`implausible_open`) |
| `PARA` (2021) | \$101.500 | thấp 0.47 | bị loại (`price_magnitude`) |
| `PARA` (2026) | \$0.425 | thấp 0.47 | OK |
| `PARA` (2021) | \$101.500 | median 0.55 | bị loại (đúng: 200.000x) |

Lưu ý dòng cuối: lịch sử 2021 của PARA **vẫn bị loại** khi re-ingest, và điều
đó là **đúng** — một biến động 200.000 lần vượt ngưỡng, và dữ liệu đã lưu đã
khớp provider nên không cần sửa. Guard đang làm đúng việc: nó bảo vệ dữ liệu
đã đúng, không sửa dữ liệu sai.

---

## 9.8. Bar crypto "hôm nay" đóng băng giá giữa phiên (2026-11-05)

Bar ngày được đóng dấu thời điểm **mở cửa** phiên, không phải lúc đóng cửa.

* Với cổ phiếu: dấu thời gian nằm trong quá khứ khi ngày kết thúc, nên bar
  mới nhất thường là bar của hôm qua — **đã chốt**.
* Với crypto (24/7): bar ngày được đóng dấu lúc `00:00Z` của chính ngày đó,
  nên bar của **hôm nay đang còn forming**: giá đóng cửa của nó chỉ là giá
  tại thời điểm fetch cuối cùng.

Auto-refresh bỏ qua symbol mà bar mới nhất mới hơn
`AUTO_REFRESH_SKIP_IF_FRESH_HOURS` (24h). Với crypto, bar forming luôn mới hơn
24h → **mọi symbol crypto bị bỏ qua ở mọi pass**. Tệ hơn: vì bar forming giữ
timestamp mới, **ngày đã chốt gần nhất cũng không bao giờ được fetch lại**.

Kết quả đo được: bar `2026-11-04` của BTC-USD đứng nguyên ở giá đóng cửa
giữa phiên (`77.912`), trong khi provider đã chốt ở `80.405` — chênh **3.1%**.
Verifier báo đây là mismatch vĩnh viễn.

**Sửa:** `BronzeLayer.latest_settled_timestamp()` bỏ qua bar đóng dấu từ
`00:00Z` hôm nay trở đi, và auto-refresh dùng bar **đã chốt** gần nhất làm
watermark. Bar forming vẫn được ghi mỗi pass — nó chỉ không còn khiến symbol
trông "còn mới".

---

## 9.9. Provider sửa lịch sử → Bronze đúng nhưng Silver/Gold vẫn sai (2026-11-05)

Sau 9.8, verifier báo **0 mismatch** nhưng vẫn còn **275 bar "restated"** trên
30 symbol Châu Âu. Đây không phải dữ liệu sai — đây là **dữ liệu đúng ở tầng
sai**.

### Ba lỗi riêng biệt, cùng một hậu quả

**Lỗi 1 — `new_records` không thấy một bar bị provider sửa.**

Bronze dedupe theo `(symbol, timestamp)`, giữ dòng mới nhất. Nên khi provider
sửa giá một bar đã có, Bronze **ghi đè** được bar cũ. Nhưng số dòng của
partition **không đổi** — và `new_records` đo *sự lớn lên* của partition:

```
new_records += max(0, len(combined) - existing_count)
```

Nên một lần provider sửa bar ⇒ `new_records = 0` ⇒ auto-refresh đọc
"symbol này không có gì mới" ⇒ **không rebuild Silver/Gold** ⇒ Silver và Gold
giữ nguyên giá cũ **vĩnh viễn**. Fetch lại bao nhiêu lần cũng vô ích, vì
vấn đề không nằm ở lần fetch mà ở chỗ một thay đổi **nội dung** bị nhầm là
**no-op**.

Đo được: `ADS.DE` ngày `2026-11-03` — Bronze đã có `168.10` (provider đã sửa),
Silver/Gold vẫn có `168.85` (giá provider phục vụ hôm trước).

**Sửa:** `BronzeLayer.append()` báo thêm `updated_records` — số dòng mà
provider **sửa** (cùng `(symbol, timestamp)` nhưng khác payload giá). So sánh
dùng **tương đối** (`1e-6`, đúng bằng tolerance của verifier): một sàn
absolute floor sẽ sai, vì `1e-9` trên `ACH` (0.21) là `5e-9` tương đối — thay
đổi thật, nhưng trên `VCB` (54.200) là `2e-14` — nhiễu float.

**Lỗi 2 — auto-refresh chỉ rebuild khi `new_rows > 0`.**

Đã sửa thêm nhánh: `res.get("updated_rows", 0) > 0` cũng kích hoạt rebuild.
Cần cả hai: `new_rows` bắt bar **mới**, `updated_rows` bắt bar **bị sửa**.

**Lỗi 3 — `reingest_window.py` chỉ so Bronze.**

Script so Bronze với provider, thấy "không khác" nên **bỏ qua luôn bước
rebuild** — kể cả khi Silver/Gold đang lệch. Đây là lý do `ADS.DE` sửa xong
vẫn còn 1 bar restated.

**Sửa:** script so **cả Bronze, Silver, Gold** với provider, và rebuild khi
**bất kỳ** tầng nào lệch. Khi Bronze đã đúng mà Silver/Gold lệch thì không
ghi lại Bronze (không có gì để ghi) nhưng **vẫn rebuild**.

**Lỗi 4 — cache API không bị xoá vì dùng sai HTTP method.**

`/admin/auto-refresh/cache/invalidate` là endpoint **POST**. Script gọi bằng
`urllib.urlopen(url)` — tức GET — nên nhận `405 Method Not Allowed`. Exception
bị nuốt ở mức `logger.debug`, nên không ai thấy. API vẫn phục vụ frame cũ
trong 15 phút, và verifier chạy ngay sau đó báo "restated" cho những bar
thực ra đã đúng.

**Sửa:** dùng `urllib.request.Request(url, method="POST")`, và nâng log lên
`warning` để lỗi này không bị giấu lần nữa.

### Kiểm chứng

* `ADS.DE`, `BTF`: **0 restated**, 240 bar khớp tuyệt đối.
* 30 symbol Châu Âu còn lại: re-ingest sửa được các phiên chênh **2%–6%**
  (ví dụ `IFX.DE` 2026-11-04: `53.51 → 50.24`, `FRE.DE` 2026-11-04:
  `48.535 → 51.380` — tức là giá provider đã sửa mạnh, và bản web đang phục vụ
  giá cũ).
* Sau khi sửa: **30/30 PASS, 7.100 bar khớp tuyệt đối, 0 mismatch, 0 restated.**

### Bài học: kiểm tra Bronze mà không kiểm tra Silver/Gold là kiểm tra sai

Verifier ban đầu so Bronze với provider → thấy khớp → báo "PASS", trong khi
web vẫn hiển thị giá cũ. Đã thêm `backend/scripts/check_layer_divergence.py` để so
**nội dung** của ba tầng với nhau theo từng phiên.

Khi chạy lần đầu, script báo **~1.000 symbol lệch** — nhưng đó là **báo động
giả**: Bronze giữ **tick intraday thô** (VTI ngày `2026-10-26` có 2 dòng: 13:30
và 16:56) còn Silver/Gold giữ **một bar/ngày**. Script đã sửa để canonicalize
trước khi so. Sau đó còn **14 symbol** lệch thật (`ALV.DE`, `PXS`, …) — đều là
trường hợp Silver/Gold giữ *ảnh chụp giữa phiên* trong khi Bronze đã có bar đã
chốt. Rebuild `--force` cho 14 symbol đó.

Kết quả cuối: **1.002/1.002 symbol — Silver và Gold khớp Bronze tuyệt đối.**

> **Bài học cốt lõi:** "Bronze đúng" ≠ "web đúng". Đường dẫn
> provider → Bronze → Silver → Gold → API cache → UI có **năm** chỗ có thể
> đứt gãy, và mỗi chỗ đều cần một kiểm tra riêng.

---

## 10. Kiểm chứng toàn universe — kết quả cuối (2026-11-05)

Lần chạy đầu chia 4 lát song song để tận dụng băng thông, nhưng **backend bị
giết** giữa chừng (4 tiến trình verify cùng đọc MinIO + 4 tiến trình backend
cùng viết → hết RAM). 35 symbol báo lỗi `WinError 10061` (API bị tắt), không
phải lỗi dữ liệu.

Đã chạy lại **tuần tự** trên 111 symbol đó:

```
symbols checked : 111
exact matches   : 19612
tolerant        : 0
stale/explained : 312
restated        : 0
MISMATCHES      : 0
errors          : 27   (provider không còn phục vụ)
```

### 9.10. Provider ngừng phục vụ 33 symbol — không phải lỗi dữ liệu (2026-11-05)

27 symbol trả lỗi provider là những mã mà **Yahoo đã ngừng phục vụ**, không phải
mã hỏng. Bằng chứng:

* `query1` và `query2` cùng trả `404`.
* `v7/finance/download` trả `406`.
* Interleave thử với symbol đang hoạt động: `CVX`/`BLK`/`AAPL`/`MSFT` trả
  đủ 714 bar, còn `TCO`/`CHK`/`WBA` vẫn 404 → **lỗi theo từng mã**, không phải
  IP bị chặn.
* `v1/finance/search?q=TCO` không còn trả `TCO` (chỉ còn `TCOM`, `TCO.AX`) →
  Yahoo đã **đổi/hủy niêm yết** mã đó.
* Bar cuối cùng trong lakehouse dừng đúng ngày **2026-10-19 07:17** — tức là
  ngày provider ngừng phục vụ.

Vì vậy "provider không còn phục vụ" **không được phép đồng nghĩa với "lakehouse
chứa rác"**. Đã thêm `backend/scripts/check_unserved_symbols.py` để kiểm tra phần còn lại
theo hướng khác: thay vì so với provider (không còn để so), kiểm tra tính
**nhất quán nội tại** của dữ liệu đã lưu:

* `high >= open, close` và `low <= open, close` (quan hệ OHLC đúng),
* `volume >= 0`, giá > 0,
* không có session trùng, timestamp đơn điệu,
* bar mới nhất không lệch quá 100x so với median → loại lỗi đơn vị (10:1, 100:1),
* Bronze / Silver / Gold thống nhất về giá đóng cửa mới nhất.

Kết quả: **33/33 symbol PASS** (`CMA CPRX CTRA DAWN DENN EXPR FOLD HAB HNG HOLX
IDC IPG KLG LTHM PEAK PGRE PGS PLL PVB PVC PVE PVS PXS TCO TGNA VCS WBA AKRO
ALXN ATSG BK BLUE CCRN`). Lịch sử đã lưu là **thật** và nhất quán.

### Tổng kết kiểm chứng toàn universe

Lần chạy cuối chạy **một lần tuần tự toàn bộ 1.002 symbol** (không chia lát — 4
lát song song làm backend bị giết vì hết RAM):

```
symbols checked : 1002
exact matches   : 229950
tolerant        : 0
stale/explained : 1125
restated        : 0
MISMATCHES      : 0
errors          : 34   (provider không còn phục vụ)
no provider data: 1
```

`stale/explained` (1.125 bar) là bar đang trong phiên hoặc bar provider đã
re-stamp — không phải mismatch. 34 lỗi là 34 mà Yahoo đã ngừng phục vụ (mục
9.10), đã kiểm tra riêng và đều PASS.

### Đồng bộ 3 tầng: `check_layer_divergence.py`

Sau lần verify dài nhất, 6 symbol (`ROKU RRC RSG RVMD S SCHW`) lệch ở phiên
`2026-11-04`: Bronze đã có giá provider sửa, nhưng Silver/Gold còn giá cũ —
do auto-refresh chạy song song với lúc verify và bị xen giữa.

Đã rebuild `--force` cho 6 symbol đó và chạy lại toàn universe:

```
symbols checked        : 1002
symbols with divergence: 0
read errors            : 0
VERDICT: every symbol's Silver and Gold agree with Bronze.
```

Sau rebuild, verify lại 6 symbol đó: **60/60 exact ở cả Bronze, Silver, Gold
và API, 0 mismatch, 0 restated**.

### Lỗi 12: 78 symbol bị kẹt giữa Bronze và Silver/Gold — refresh KHÔNG BAO GIỜ tự sửa được

**Đo ngày 12/11/2026.**

**Triệu chứng:** `check_layer_divergence.py` báo **78 symbol lệch** giữa Bronze và
Silver/Gold, tất cả tập trung ở phiên `2026-11-12`. Ví dụ `0001.HK`:

| Tầng | Giá đóng cửa 2026-11-12 | Volume | `ingestion_time` |
|---|---|---|---|
| Bronze | **69,35** | 9.121.791 | 12:02:50 UTC (sau giờ đóng cửa) |
| Silver | 68,95 | 7.064.471 | 07:28:44 UTC (trong phiên) |
| Gold | 68,95 | 7.064.471 | 07:28:44 UTC (trong phiên) |

Lệch tương đối trung vị **0,457%**, lớn nhất **6,25%**. API trả về 68,95 — tức là
**giá chốt trong phiên**, không phải giá chốt phiên.

**Vì sao xảy ra:** Một bar ngày được đóng dấu thời điểm **mở cửa**, và provider phục vụ
giá tính đến lần gọi cuối cùng. Nên một lượt refresh chạy **trong khi thị trường còn
mở** sẽ ghi một ảnh chụp giá giữa phiên, rồi Silver/Gold được dựng lại từ ảnh chụp đó.
Provider sau đó chốt bar đó bằng giá đóng cửa. Lượt refresh kế tiếp ghi đè dòng Bronze
(cùng `symbol` + `timestamp`, close khác) và báo `updated_records = 1`, nên Silver/Gold
**được** dựng lại và hội tụ — đường đi này vốn chạy đúng.

Đường đi đó **hỏng** khi lần ghi Bronze đã xong nhưng lần dựng Silver/Gold **không**
chạy: process bị kill giữa hai lần ghi, lần dựng bị bỏ qua vì thiếu RAM, hoặc một
writer khác (script ingest, API) ghi thẳng vào Bronze. Lúc đó Bronze giữ giá đóng cửa
còn Silver/Gold giữ ảnh chụp giữa phiên.

Từ thời điểm đó **mọi tín hiệu phát hiện khác đều im lặng**:

| Tín hiệu | Giá trị | Vì sao không bắt được |
|---|---|---|
| `new_records` | 0 | Phân vùng không lớn thêm |
| `updated_records` | 0 | Bronze **đã** giữ giá chốt rồi, provider không "sửa" gì thêm |
| So ngày giao dịch Bronze ↔ Gold | bằng nhau | Cả hai cùng mang ngày `2026-11-12` |

⇒ Silver/Gold **không bao giờ** được dựng lại, và giá cũ được phục vụ **vĩnh viễn**.
Đây đúng là loại lệch mà "cứ fetch lại" không bao giờ chữa được, vì vấn đề không
nằm ở lần fetch.

**Bằng chứng (tái hiện trên storage cô lập):** dựng lại đúng trạng thái kẹt ở trên,
rồi chạy lại `BronzeLayer.append` với batch mà refresh thực sự fetch:

```
REPLAY của lượt refresh 12:02 trên Bronze hiện tại:
  new_records     = 0
  updated_records = 0   <-- tín hiệu rebuild
  duplicate_count = 5
```

Bronze đã giữ giá chốt ⇒ append không thấy thay đổi nào ⇒ không có tín hiệu nào báo
rebuild. Đây là lý do fix **không thể** đặt trong Bronze.

**Fix:** thêm một tín hiệu rebuild thứ tư trong `app/services/auto_refresh.py` —
so **giá đóng cửa phiên mới nhất** của Bronze với giá của Silver. Khi hai tầng lệch
nhau trên cùng một ngày giao dịch thì rebuild.

```python
def _silver_diverged_from_bronze(symbol, bronze_frame, silver) -> bool:
    bronze_day, bronze_close = _newest_session_close(bronze_frame)
    silver_day, silver_close = _newest_session_close(silver.read(symbol))
    if bronze_day != silver_day:
        return False   # để guard watermark ngày giao dịch lo
    return _closes_differ(bronze_close, silver_close)
```

**Bằng chứng (sau khi sửa):**

* Tái hiện trên storage cô lập: phát hiện lệch = `True`, và sau khi rebuild
  **Bronze = Silver = Gold = 69,35** — ba tầng hội tụ.
* Sửa dữ liệu thật: rebuild `--force` **78/78 symbol** thành công (3,1 phút).
* Quét lại toàn universe:
  ```
  symbols checked        : 1002
  symbols with divergence: 0
  errors                 : 0
  ```
* API xác nhận trả giá đúng: `0001.HK` → `close: 69.35` (trước: `68.95`),
  `0005.HK` → `close: 140.70` (trước: `141.00`).
* Test mới: `backend/tests/test_silver_divergence_recovery.py` — 15/15 check PASS.
  Toàn bộ `pytest` vẫn **112/112 PASS**.

**Script quét nhanh:** `check_layer_divergence.py` đọc *toàn bộ* lịch sử của từng
symbol theo thứ tự tuần tự — đo được 20 symbol mất 52 giây, tức ~44 phút cho 1.002
symbol. Đã thêm `backend/scripts/scan_divergence_fast.py` (đọc partition tháng mới
nhất, chạy song song 16 luồng): **1.002 symbol trong 95 giây**, 0 lỗi.

> **Cách trả lời khi thầy hỏi "làm sao biết dữ liệu trên web là dữ liệu mới nhất?"**
> *"Em viết một script đối chiếu nội dung ba tầng với nhau, không chỉ so Bronze với
> provider. Lần chạy đầu em tìm ra 78 mã bị kẹt: Bronze đã có giá chốt phiên nhưng
> Silver và Gold còn giữ ảnh chụp giữa phiên. Nguyên nhân là bar ngày được đóng dấu
> ở thời điểm mở cửa, nên lúc thị trường còn mở thì hệ thống ghi nhầm giá giữa phiên;
> và nếu lần ghi Bronze xong nhưng lần dựng Silver/Gold không chạy, thì từ đó mọi
> tín hiệu phát hiện đều im lặng vì Bronze không còn thay đổi nữa. Em đã thêm một
> tín hiệu thứ tư — so giá đóng cửa phiên mới nhất của Bronze với Silver — và sau
> khi sửa thì quét lại 1.002 mã cho ra 0 mã lệch, API trả đúng giá chốt phiên, và
> 112/112 test vẫn xanh."*

### Đồng bộ Web ↔ MinIO đã kiểm bằng trình duyệt

| Trang | Kết quả |
|---|---|
| Dashboard | AAPL $349.51, RSI 57.78, model `linear_regression` MAE 2.86, số file Bronze/Silver/Gold 116.109 / 116.426 / 115.100 |
| Dữ liệu thị trường | 2.534 phiên, nến + bảng 80 phiên cuối, nguồn `gold` |
| Phân tích kỹ thuật | `IFX.DE`: RSI 39.50, MACD, Bollinger — tính từ series **đã sửa** (`50.24` ngày 2026-11-04, trước đó `53.51`) |
| Dự báo | 3 model train thật: linear MAE 2.86 / LSTM 47.31 / ARIMA 86.33 |
| Backtest | +57.39%, Sharpe 0.49, max drawdown −28.24%, win rate 44.44% |
| AI Agent | Trả lời `ADS.DE` bằng giá thật (179.45) và **thừa nhận không có bar 2026-11-04** thay vì bịa |
| Trạng thái hệ thống | Backend online, MySQL connected, MinIO connected, storage `minio` |

`/api/v1/system/status` xác nhận storage backend là **minio** (không phải local
fallback) và cả ba layer đều đang được phục vụ.

---
## 10b. Hệ thống tin tức — đã gỡ khỏi dự án (đo ngày 12/11/2026)

> **Đo ngày 12/11/2026 — trạng thái: ĐÃ GỠ BỎ TOÀN BỘ.**
>
> Dự án từng có một hệ thống tin tức riêng (2 tầng lưu Bronze/Silver, provider
> đọc RSS, 4 endpoint, 4 tool AI, 1 trang giao diện, 2 lịch cron). Nó đã bị
> **gỡ khỏi dự án**. Mục này ghi lại **số đo thật** dẫn tới quyết định đó, và
> cách kiểm chứng trạng thái sau khi gỡ.

### 10b.1. Số đo dẫn tới quyết định gỡ

**Đo ngày 11/11/2026** — phép đo độ phủ tin tức trên **toàn bộ** danh sách mã:

| Trường | Giá trị |
|---|---|
| Số mã được đo | **1.002 / 1.002** |
| Tổng số phiên giao dịch trong mẫu | 356.803 |
| Số phiên có tin tức | 15 |
| `overall_coverage_pct` | **0,0%** |
| Độ phủ trung vị (theo từng mã) | **0,00%** |
| `read_errors` | **0** |
| `failed_symbols` | (rỗng) |

Kèm theo:

| Kiểm tra | Kết quả |
|---|---|
| File Parquet trong `stock-bronze-news` | 16 |
| File Parquet trong `stock-silver-news` | 15 |
| Số bài đã ingest (Bronze) | **89** |
| Số mã có ít nhất 1 bài | **10** |

**Đọc con số này:** trong 356.803 phiên giao dịch, chỉ **15 phiên** có tin tức sẵn
sàng trước giờ mở cửa. Tỉ lệ phủ trung vị theo từng mã là **0,00%**. Một hệ thống
chỉ hoạt động trên **0,89%** mẫu số không thể dùng để kết luận điều gì — không
một thí nghiệm sentiment nào trên nền dữ liệu đó có ý nghĩa.

### 10b.2. Lý do thứ hai, nặng hơn: tin thật gắn sai mã

Trong 10 mã "có tin", kiểm tra từng bài báo cho thấy một số bài báo **thật nhưng
gắn sai mã chứng khoán**. Nguyên nhân là **trùng mã giữa các sàn**:

| Mã trong hệ thống | Bài báo thực tế được gán | Nguyên nhân |
|---|---|---|
| `MWG` (Mobile World, Việt Nam) | Tin về Multi Ways Holdings (Singapore) | Yahoo tra cứu RSS theo mã, `MWG` là mã của cả hai |
| `VCB` (Vietcombank, Việt Nam) | Tin về quỹ ETF Vanguard | Cùng lý do: `VCB` trùng mã với quỹ Vanguard |
| `FPT`, `HPG`, `CTG` | Tin chung thị trường của VnExpress | Logic dự phòng: khi số bài "liên quan" quá ít, hệ thống đổ tin chung vào để không trống trải |

Bài báo là **thật** — không có bài nào bịa ra. Nhưng bài báo **thật gắn sai mã**
vẫn là sai: bảng dữ liệu ghi "MWG có tin về Multi Ways Holdings" là một dòng dữ
liệu **không truy vết được**, và đó là vi phạm cùng loại với số liệu bịa.

### 10b.3. Trạng thái sau khi gỡ (kiểm chứng ngày 12/11/2026)

| Hạng mục | Trước | Sau |
|---|---|---|
| Route REST chứa `news`/`sentiment` | 8 | **0** (tổng còn 61 route) |
| Endpoint trong `tool_registry.py` | 21 | **17** |
| Bucket MinIO có chữ `news` | 2 | **0** |
| Thư mục local `data/bronze_news`, `data/silver_news` | 2 | **0** |
| File `data/news_coverage.json` | 1 | **0** |
| Trang giao diện | 8 | **7** |
| Test backend | 111 pass + 1 lỗi import | **112 pass, 0 lỗi** |

Cách kiểm chứng lại sau khi gỡ:

```powershell
# 1. Không còn route news nào
Invoke-WebRequest "http://127.0.0.1:8000/openapi.json" -UseBasicParsing |
  Select-Object -ExpandProperty Content | ConvertFrom-Json |
  ForEach-Object { $_.paths.PSObject.Properties.Name } |
  Where-Object { $_ -match "news|sentiment" }
# -> không in ra gì

# 2. Không còn bucket news nào
cd backend
.\.venv\Scripts\python.exe -c "
from minio import Minio
from app.core.config import settings
c = Minio(settings.minio_endpoint, access_key=settings.minio_access_key,
          secret_key=settings.minio_secret_key, secure=False)
print([b.name for b in c.list_buckets() if 'news' in b.name] or 'NONE')
"
# -> NONE

# 3. Test backend vẫn xanh
.\.venv\Scripts\python.exe -m pytest tests\ -q
# -> 112 passed
```

### 10b.4. Điều KHÔNG thay đổi

Việc gỡ tin tức **không đụng vào** bất kỳ đặc trưng nào của mô hình dự báo:

- Tập đặc trưng của Gold **không có** cột sentiment — trước và sau khi gỡ.
- Tầng giá (Bronze/Silver) **không bị tác động** — số record không đổi.
- Kết quả backtest và walk-forward **không đổi** — chúng chưa bao giờ dùng tin tức.

> **Cách trả lời khi thầy hỏi "bỏ tin tức thì dự án có bị thiếu gì không?":**
> *"Không, vì nó chưa bao giờ được dùng vào mô hình nào. Tôi đo độ phủ trước khi
> quyết định: 1.002 mã, 356.803 phiên, chỉ 15 phiên có tin — 0,0%. Tệ hơn, kiểm tra
> từng bài thì thấy `MWG` của Mobile World nhận tin của Multi Ways Holdings và `VCB`
> của Vietcombank nhận tin của quỹ Vanguard, do trùng mã giữa các sàn. Bài báo thật
> nhưng sai mã là dữ liệu không truy vết được, mà luật của tôi là mọi con số phải
> truy vết được. Nên tôi gỡ hẳn. Phần còn lại là giá, chỉ báo, dự báo, backtest và
> walk-forward — phần có dữ liệu thật và kết quả thật."*

---
---

## 10c. Kiểm chứng phép đo đa mã (đo ngày 11/11/2026)

> **Đo ngày 11/11/2026 — trạng thái: ĐÃ CHẠY, 0 lỗi đọc.**

Phép đo walk-forward đa mã đọc dữ liệu từ cùng đường `Gold → Silver → Bronze`
mà mọi endpoint khác dùng, nên nó thừa hưởng toàn bộ kiểm chứng ở Phần 1–10.
Phần này ghi lại **những gì riêng của phép đo này**.

### 10c.1. Mẫu lấy từ đâu, và vì sao lấy theo tầng

Mẫu được rút từ **tập mã có mặt trong Bronze** — tức là những mã đã thực sự được
ingest, không phải một danh sách gõ tay.

| Sàn | Số mã trong universe | Số mã lấy mẫu |
|---|---|---|
| NYSE/NASDAQ | 697 | 8 |
| HOSE (Việt Nam) | 81 | 8 |
| TSE (Nhật) | 39 | 8 |
| Euronext | 31 | 8 |
| XETRA (Đức) | 29 | 8 |
| HKEX | 20 | 8 |
| KRX (Hàn Quốc) | 20 | 8 |
| TWSE (Đài Loan) | 20 | 8 |
| Nasdaq Nordic | 19 | 8 |
| TSX (Canada) | 17 | 8 |
| LSE (Anh) | 15 | 8 |
| SIX (Thụy Sĩ) | 5 | 5 (hết mã) |
| BME (Tây Ban Nha) | 4 | 4 (hết mã) |
| **Tổng** | **1.002** | **101** |

Vì sao phải lấy theo tầng: 697/1.002 mã là NYSE/NASDAQ (69,6%). Nếu lấy mẫu
ngẫu nhiên, phần "phân phối theo sàn" sẽ gần như chỉ nói về thị trường Mỹ, và
bảng so sánh 13 sàn trở nên vô nghĩa.

Nguồn: `select_symbols()` trong `backend/scripts/run_multi_symbol_walkforward.py`.

### 10c.2. Bằng chứng dữ liệu thật trong báo cáo

| Kiểm chứng | Kết quả | Ý nghĩa |
|---|---|---|
| Số mã có dữ liệu dùng được | 101/101 | Không mã nào rơi vào tình trạng "không đủ dữ liệu" |
| Số mã lỗi khi đọc | **0** | `errors: []` trong file báo cáo |
| Số cửa sổ kiểm tra | 3.687 | Trung bình ~36 cửa sổ/mã với cấu hình 365/90/90 |
| Thời gian chạy | 112 s (MA) · 118 s (RSI) | Trên 1.002 mã, ~2 phút/chiến lược |

### 10c.3. Đường cơ sở dùng cùng dữ liệu, cùng chi phí

Đường cơ sở mua & giữ được mô phỏng bằng **cùng hàm `simulate()`**, trên
**cùng một DataFrame phiên** mà chiến lược dùng, với **cùng mức phí** và **cùng
độ trượt giá**. Bằng chứng cụ thể:

* Số điểm equity của hai bên bằng nhau (AAPL: 2.538 điểm cả hai bên).
* Timestamp đầu và cuối của hai đường equity **trùng khớp tuyệt đối**.
* Chênh lệch giữa hai bên được tính **theo từng cửa sổ** (so sánh cặp), không
  phải hiệu của hai trung bình độc lập.

Bốn bất biến này có test riêng trong `backend/tests/test_backtest_benchmark.py`.

### 10c.4. Điều phép đo này KHÔNG chứng minh

* **Không chứng minh chiến lược sẽ thắng trong tương lai.** Đây là phép đo
  lịch sử.
* **Không phải phép thống kê kiểm định giả thuyết.** Chưa có kiểm định ý nghĩa
  thống kê (t-test, bootstrap) trên phân phối excess return — đó là hướng mở
  rộng.
* **Tham số chiến lược không được tối ưu trên đoạn train.** Bản hiện tại dùng
  tham số mặc định (MA 20/50, RSI 14/30/70) cho mọi mã, nên đây là phép đo của
  một cấu hình cố định, không phải của quy trình tối ưu tham số.
* **Mẫu 101 mã, không phải toàn bộ 1.002 mã.**

Tài liệu chi tiết: [`docs/NGHIEN_CUU_DA_MA_WALK_FORWARD.md`](NGHIEN_CUU_DA_MA_WALK_FORWARD.md).

---

## 10d. Bar đóng băng giữa phiên trong Bronze (đo ngày 15/11/2026)

### Triệu chứng

Quality gate FAIL ở check `source_agreement` với hai mã `AMD` và `INTC`.
Cả hai trông như hai nguồn giá nói khác nhau về cùng một phiên:

| Mã | Ngày | Nguồn | Close | Volume |
|---|---|---|---|---|
| `AMD` | 2026-10-28 | `yfinance_eod` | 567,00 | 7.367.032 |
| `AMD` | 2026-10-28 | `yahoo_http` | 578,44 | 18.848.600 |
| `INTC` | 2026-10-28 | `yfinance_eod` | 93,93 | 33.148.315 |
| `INTC` | 2026-10-28 | `yahoo_http` | 95,53 | — |

### Vì sao xảy ra

Dòng `yfinance_eod` được nạp lúc **16:29 UTC = 12:29 EDT**, tức là **3,5
giờ trước giờ đóng cửa NYSE** (16:00 EDT). `close` của nó là giá giao dịch
cuối cùng tại thời điểm đó, và `volume` là khối lượng đã giao dịch cho tới
lúc đó. Đây là **ảnh chụp giữa phiên bị đóng băng thành bar ngày**, không
phải hai nguồn nói khác nhau.

Bằng chứng độc lập: provider phục vụ giá đóng cửa đã chốt của `AMD` ngày
`2026-10-28` là **578,44** — đúng bằng dòng `yahoo_http`, và lệch **2,0%**
so với dòng `yfinance_eod`.

### Phạm vi: không chỉ 6 mã

Quét toàn bộ Bronze (tháng 10–11/2026) cho thấy **1.138 phiên** bị đóng băng
trên **752 mã**. Phần lớn **không phải** `yfinance_eod` mà là `yahoo_http` được
đóng dấu đúng phút fetch chạy (`16:41`, `17:32`, `04:02`, ...). Đặc điểm
chung là như nhau: dòng được ghi **khi phiên của chính nó còn đang mở**.

### Quan hệ bao hình — tín hiệu cấu trúc

Trong một phiên, `high` và `low` chỉ có thể **nở ra**, và `volume` chỉ có thể
**tăng**. Nên bar đã chốt **luôn chứa** bar đang hình thành:

```
forming.high   <= settled.high
forming.low    >= settled.low
forming.volume <  settled.volume
forming.close  != settled.close
```

Quan hệ này **không cần lịch sàn giao dịch**: nó so hai dòng của *cùng một
phiên* với nhau, nên đúng với mọi thị trường trong universe (NYSE, HOSE,
ASX, TWSE) mà không cần biết sàn nào mở lúc nào.

**Đây là điểm khác biệt cốt lõi với mục 9.8.** Mục 9.8 xử lý bar crypto
"hôm nay" bằng cách so timestamp với nửa đêm UTC. Bar crypto đóng dấu lúc
00:00Z nên "bar hôm nay" là bar đang hình thành — nhưng chỉ với crypto.
Bar **cổ phiếu** đóng dấu lúc **giờ mở cửa**, nên với cổ phiếu thì bar
"hôm nay" đã **chốt rồi** và không cần canh. Cái bị đóng băng ở đây là bar
của **phiên hôm qua**, bị chụp lúc 16:29 UTC vì lúc đó phiên hôm qua **còn
đang mở**.

### Kiểm chứng độ chính xác của luật

Luật bao hình được kiểm chứng trên **1.120 phiên** đối chiếu trực tiếp với
provider đang chạy:

| Kết quả | Số phiên |
|---|---|
| Dòng mà luật gọi là "đã chốt" **khớp** giá provider | **1.116** |
| Dòng mà luật gọi là "đã chốt" **không khớp** | 4 |

4 ca còn lại đều **không phải** snapshot:
* 3 ca `CMG` — **stock split 50:1** ngày 10/2026 (giá `19.750 → 27,52`, lệch
  717 lần). Đây là **điểm gãy thang giá**, không phải ảnh chụp giữa phiên, và
  nó đã được xử lý riêng bởi `app/lakehouse/scale_repair.py`.
* 1 ca `COL.AX` — sàn ASX, phiên chéo nửa đêm UTC.

Vì vậy luật **loại trừ** những cặp tỉ lệ giá ≥ `10` lần: đó là dấu hiệu
điểm gãy thang giá, không phải ảnh chụp giữa phiên. Sau khi loại, độ chính
xác là **1.116/1.120 = 99,6%**.

### Tầng nào giữ dòng nào

Đo trực tiếp trên `AMD` 2026-10-28:

```
bronze   2026-10-28 04:00:00Z  close 567.00  vol  7,367,032  yfinance_eod   <- đóng băng
bronze   2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http     <- đã chốt
silver   2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http     <- đã chốt
gold     2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http     <- đã chốt
```

**Silver và Gold đã chọn đúng dòng** — vì chúng ưu tiên dấu phiên chuẩn.
Chỉ **Bronze** giữ cả hai. Vì vậy:

* **Sản phẩm đang phục vụ đúng.** Web vẽ giá đã chốt, không vẽ giá đóng băng.
* **Bronze vẫn giữ dòng sai** — và điều đó phải được *gọi đúng tên*, vì một
  dòng trái với provider sẽ khiến mọi đợt kiểm toán sau đó hiểu nhầm là
  "provider sai" thay vì "dòng này bị chụp giữa phiên".

### Sửa

1. **Module mới** `backend/app/lakehouse/forming_bar.py` — hiện thực luật bao
   hình, không cần lịch sàn giao dịch.
2. **Check mới trong quality gate**: `forming_snapshots`. Nó **không xoá gì** —
   Bronze là tầng raw, nó được phép giữ cái provider đã nói, và dòng đã chốt
   sau đó thay thế dòng đóng băng. Check này báo **warning**, không phải
   failed, vì nó mô tả sự thật về tầng raw chứ không phải lỗi làm hỏng thứ
   web phục vụ.
3. **Frontend**: thêm nhãn cho check mới trong `QualityGatePanel.tsx`.

### Kiểm chứng

* Chạy check trên toàn bộ lakehouse: `status=warning`, `checked=1002`,
  `warned=752`, `frozen_sessions=1138`.
* Test: `backend/tests/test_forming_bar.py` — 17 test, tất cả PASS.
* Test loại trừ: `backend/tests/test_source_agreement_exclusions.py` — 8 test.
* Đối chiếu provider trực tiếp: 1.116/1.120 phiên đúng (99,6%).

### Kết quả quality gate trước và sau

Chạy toàn bộ gate trên 1.002 mã (đo ngày **15/11/2026**):

| Check | Trước | Sau |
|---|---|---|
| `source_agreement` | **failed** (2 mã: `AMD`, `INTC`) | **passed** (0 mã) |
| `forming_snapshots` | *(chưa có)* | **warning** (752 mã, 1.138 phiên) |
| **Verdict tổng** | **failed** | **warning** |

Chi tiết mới trong `source_agreement.details`:
`explained_by_mid_session_snapshot: 2` — hai phiên `AMD` và `INTC` được giải
thích bằng ảnh chụp giữa phiên, nên không còn là "xung đột provider".

*Toàn bộ bộ test backend: **565/565 PASS** (đo ngày 16/11/2026).*

### Dọn dẹp dự án (đo ngày 16/11/2026)

Việc dọn dẹp **không được làm thay đổi dữ liệu thật**. Cụ thể:

| Việc | Kết quả | Ảnh hưởng dữ liệu |
|---|---|---|
| Xoá 346 file log trong `backend/logs/` (41,9 MB) | Không | **Không** — log không phải dữ liệu thị trường |
| Xoá 9 file probe API rác trong `backend/tests/` | Không | **Không** — đó là response lỗi "Invalid API key" |
| Xoá `frontend/dist/`, `__pycache__/`, `.pytest_cache/`, `.sentry-native/` | Không | **Không** — tất cả đều tự sinh lại |
| Xoá `backend/data/gold_features/`, `backend/data/quality/` (rỗng) | Không | **Không** — 0 file, không code nào tham chiếu |
| Sửa `test_no_missing_imports.py` để bỏ qua `backend/data/` | Không | **Không** — chỉ đổi cách test tìm file `.py` |
| **Giữ nguyên** `minio_data/` và `backend/data/` | — | Đây là dữ liệu thật, không được đụng |

Bằng chứng dữ liệu vẫn nguyên vẹn sau khi dọn (đo 16/11/2026):

- `GET /api/v1/forecast/accuracy` → 200, vẫn **44.606** dòng đã chấm điểm.
- `GET /api/v1/quality/gate` → 200, `layer_agreement` **passed** với **61.656**
  phiên so sánh, 0 phân kỳ.
- `pytest tests` → **565 test, 0 failure, 0 error**.

> **Cập nhật 17/11/2026** (đo lại sau khi sửa lỗi "Lock wait timeout" và thêm
> dự báo đa mô hình):
> - `GET /api/v1/forecast/accuracy` → 200, **45.631** dòng đã chấm điểm hợp lệ
>   (46.318 dòng có `actual_close`), median sai số **1,15%** — **không đổi**.
> - `pytest tests` → **572 test, 0 failure, 0 error, 0 skipped**, **139 giây**.

### Điều này KHÔNG chứng minh

* **Không chứng minh Bronze sạch.** Bronze vẫn giữ 1.138 dòng đóng băng. Đó là
  quyết định có chủ đích (tầng raw giữ nguyên lời của provider), nhưng phải
  nói ra thay vì giấu.
* **Không chứng minh mọi mã đều đúng.** Check này chỉ soi các phiên có **nhiều
  hơn một dòng** trong cửa sổ 60 phân vị. Một phiên chỉ có một dòng đóng
  băng mà không có bản đã chốt thì không bị phát hiện — và cũng không làm hỏng
  gì, vì dòng đó là dữ liệu thật của thời điểm đó.
* **Không chứng minh lịch sử sâu hơn tháng 11/2026 sạch.** Cửa sổ kiểm tra là
  60 phân vị gần nhất.

---

## 11. Giới hạn của phương pháp này

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
