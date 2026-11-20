# HIỂU ĐỒ ÁN NÀY TỪ ĐẦU

> File này dành cho người **chưa biết chứng khoán** và **chưa quen công nghệ**.
> Đọc từ trên xuống là được. Không cần biết trước bất cứ thứ gì.
>
> Bạn đọc xong file này sẽ trả lời được 5 câu hỏi:
> 1. Cổ phiếu là gì và hệ thống này làm gì với cổ phiếu?
> 2. Dữ liệu đi từ đâu đến, qua những bước nào?
> 3. Các thành phần trong hệ thống liên hệ với nhau thế nào?
> 4. Hệ thống dự báo bằng cách nào, và làm sao biết nó có đúng không?
> 5. Hệ thống này **không** làm gì?

---

## MỤC LỤC

| Phần | Nội dung | Nếu bạn chỉ có 5 phút |
|---|---|---|
| [1](#1) | Chứng khoán là gì (viết cho người chưa biết) | Đọc |
| [2](#2) | Đồ án này giải quyết vấn đề gì | Đọc |
| [3](#3) | Dữ liệu đi đường nào (nhà hàng 3 tầng) | Đọc |
| [4](#4) | Các thành phần trong hệ thống và mối quan hệ | Đọc |
| [5](#5) | Các khái niệm chứng khoán mà hệ thống dùng | Tự tra |
| [6](#6) | Mô hình dự báo hoạt động thế nào | Tự tra |
| [7](#7) | Backtest là gì và vì sao phải so với "mua và giữ" | Tự tra |
| [8](#8) | AI Agent trong hệ thống này | Tự tra |
| [9](#9) | Các ví dụ sử dụng thật (use case) | Tự tra |
| [10](#10) | Hệ thống KHÔNG làm gì (giới hạn trung thực) | **Đọc** |
| [11](#11) | Tự kiểm tra hiểu chưa | Tự làm |

---

<a id="1"></a>
## 1. Chứng khoán là gì

### 1.1 Cổ phiếu

Khi một công ty cần tiền, công ty bán "phiếu" cho bạn. Bạn mua phiếu đó với một mức giá, và trở thành **cổ đông** của công ty, tức là có quyền nhận một phần lợi nhuận (gọi là **cổ tức**) khi công ty làm ăn tốt.

Đổi lại, giá của phiếu đó có thể tăng hoặc giảm mỗi ngày, tùy vào việc người mua thấy công ty sẽ ra sao.

```
Công ty ABC cần 10 tỷ để xây nhà máy
        │
        ├── Chia ra 100.000.000 cổ phiếu
        ├── Bán ở giá 100.000đ/cổ phiếu
        │       (thu được 10.000 tỷ, có người mua nhiều hơn thì giá bán cao hơn)
        │
        └── Sau đó, phiếu đó có thể được giao dịch mua bán trên sàn
```

Hai khái niệm quan trọng nhất:

| Khái niệm | Nghĩa |
|---|---|
| **Mã cổ phiếu** | Tên viết tắt của phiếu trên sàn. `AAPL` = Apple, `VCB` = Vietcombank, `FPT` = FPT Corp. Trong hệ thống này, mã là khóa chính để tra cứu mọi thứ về phiếu đó. |
| **Phiên giao dịch** | Một ngày sàn mở cửa. Mỗi phiên sinh ra một "nến" (xem mục 1.2). Sàn Việt Nam giao dịch T2–T6; sàn Mỹ cũng vậy. |

### 1.2 Nến (candle) và OHLCV

Mỗi ngày giao dịch, sàn ghi lại 5 con số. Đó là dữ liệu thô nhất, cũng là dữ liệu duy nhất mà hệ thống này sử dụng.

| Ký hiệu | Tên | Ý nghĩa |
|---|---|---|
| **O**pen | Giá mở cửa | Giá khớp lệnh đầu tiên trong ngày |
| **H**igh | Giá cao nhất | Giá cao nhất chạm tới trong ngày |
| **L**ow | Giá thấp nhất | Giá thấp nhất chạm tới trong ngày |
| **C**lose | Giá đóng cửa | Giá khớp lệnh cuối cùng trong ngày |
| **V**olume | Khối lượng | Tổng số cổ phiếu giao dịch trong ngày |

**Ví dụ một phiên của VCB:**

```
        Giá
         ▲
   97.000│        ╷  high = 96.500
         │        │
   96.000│    ╷   │  close = 96.200
         │    │   ╷
   95.000│────╷───╷──── open = 95.300
         │         │
   94.000│         ╷  low = 94.800
         └─────────┴────────────────► Thời gian
              09:00        15:00
```

Đọc nến này: VCB mở cửa ở 95.300, trong ngày có lúc tăng lên 96.500, có lúc rớt xuống 94.800, và đóng cửa ở 96.200 với khối lượng 2.340.000 cổ phiếu.

**Quan hệ bắt buộc:** `high ≥ max(open, close)` và `low ≤ min(open, close)`. Nếu một dòng dữ liệu vi phạm điều này thì nó sai, và hệ thống loại bỏ (xem mục 3.2).

Hệ thống gọi 5 con số này là **OHLCV**, và mỗi phiên là một **bar** (bar = thanh). "Bar ngày" = một phiên giao dịch.

### 1.3 Ba tầng dữ liệu mà mọi người chứng khoán đều biết

Một ngày ở sàn có ba mức giá chính:

| Tên | Nghĩa |
|---|---|
| **Giá tham chiếu** | Giá đóng cửa của phiên trước. Sàn dùng nó làm mốc để tính biến động ±10% (HOSE) hoặc ±20% (NYSE) trong một phiên. |
| **Giá trần** | Giá tham chiếu × 1,10 (HOSE) hoặc × 1,20 (NYSE). |
| **Giá sàn** | Giá tham chiếu × 0,90 (HOSE) hoặc × 0,80 (NYSE). |

Hệ thống này **không** dùng trần/sàn để sinh dữ liệu, nhưng hiểu khái niệm này giúp bạn hiểu vì sao dữ liệu "nằn" (giá vọt quá xa) phải bị loại. Xem mục 3.2.

### 1.4 Điều chỉnh giá (adj_close)

Đôi khi công ty chia cổ tức (trả tiền cho cổ đông) hoặc tách cổ phiếu (chia 1 cổ thành 2). Khi đó giá giảm mạnh trên biểu đồ, nhưng **của cổ đông không mất gì**.

Ví dụ: giá AAPL là 500 USD, công ty chia cổ tức 5 USD/cổ phiếu. Ngày hôm sau giá mở cửa 495 USD. Biểu đồ vẽ lên sẽ thấy một cú giảm 1%, nhưng thực tế cổ đông vẫn có đúng 500 USD (495 + 5 cổ tức).

Vì vậy có hai loại giá đóng cửa:

| Cột | Dùng để làm gì |
|---|---|
| `close` | Giá giao dịch thật, đúng như sàn báo. Dùng để vẽ nến. |
| `adj_close` | Giá đã điều chỉnh cho cổ tức và tách cổ phiếu. Dùng để **tính toán lợi nhuận**, vì nếu không, mọi phép tính sẽ tính sai một cách âm thầm. |

Hệ thống giữ cả hai cột. Đây là ví dụ đầu tiên về nguyên tắc "giữ nguyên dữ liệu gốc, tính toán ở tầng trên".

---

<a id="2"></a>
## 2. Đồ án này giải quyết vấn đề gì

### 2.1 Vấn đề

Có rất nhiều người muốn dùng máy tính để dự báo giá cổ phiếu. Nhưng giữa "tôi muốn dự báo" và "tôi có một hệ thống đáng tin" có một khoảng cách rất xa. Khoảng cách đó gồm ba phần:

**Phần 1 — Dữ liệu bẩn.**
Người mới tải dữ liệu từ đâu cũng được, rồi phát hiện:
- Có dòng trùng lặp (tải 3 lần cùng một ngày).
- Có dòng thiếu giá (ngày lễ không giao dịch nhưng có dòng rỗng).
- Có dòng vô lý (giá cao nhất thấp hơn giá thấp nhất).
- Múi giờ lẫn lộn (một nguồn theo giờ New York, một nguồn theo giờ Tokyo).

**Phần 2 — Tự đánh giá sai.**
Đây là lỗi phổ biến nhất và nguy hiểm nhất. Ai cũng nghĩ mô hình của mình "đúng 70%", nhưng nếu cách đo sai thì con số đó chỉ là ảo.

> **Ví dụ kinh điển:** bạn dùng giá đóng cửa ngày hôm nay để quyết định "mua hay bán", rồi giả định lệnh khớp **ngay giá đóng cửa hôm nay**. Bạn đã biết trước kết quả của chính quyết định đó. Mô hình có thể đạt 90% độ chính xác, nhưng con số đó **không mang ý nghĩa gì**.

**Phần 3 — Không ai chịu báo cáo kết quả xấu.**
Có 3 mô hình, chọn cái nào có điểm cao nhất rồi báo cáo cái đó. Đây là **cherry-picking**, và thầy bảo chấm sẽ hỏi ngay lập tức: "Còn 2 mô hình kia thì sao?"

### 2.2 Đồ án này làm gì

> **Mục tiêu:** xây dựng một hệ thống có **dữ liệu thật, truy vết được**, **đo lường trung thực**, và **báo cáo cả kết quả xấu**.

Cụ thể là 5 việc:

| # | Việc | Cách làm |
|---|---|---|
| 1 | Thu thập dữ liệu giá từ nhiều nguồn, tự chọn nguồn còn hoạt động | `data_sources/` với cơ chế failover + circuit breaker |
| 2 | Làm sạch dữ liệu và **đếm được đã loại bỏ bao nhiêu, vì lý do gì** | Tầng Silver ghi `_quality.json` |
| 3 | Tính chỉ báo kỹ thuật và gắn nhãn đáp án | Tầng Gold, 90 cột |
| 4 | Dự báo giá phiên kế tiếp bằng 3 mô hình, đo trên tập **chưa từng thấy** | `forecasting/` |
| 5 | Kiểm chứng chiến lược bằng walk-forward, so với đường cơ sở "mua và giữ" | `backtesting/` |

### 2.3 Nguyên tắc bất di bất dịch của đồ án

Đây là quy tắc số 1 trong file `.cursor/rules/no-fake-data.mdc` của chính dự án:

> **Mọi con số trên màn hình phải truy vết được về một nguồn thật.**

Nghĩa là:
- Không có số bịa trong code.
- API lỗi thì trả lỗi thật kèm lý do, không trả `0.00%` cho có.
- Không có "dữ liệu mẫu" để demo khi dữ liệu thật chưa có.
- AI Agent **không** tự nghĩ ra con số, mà gọi tool để lấy số thật rồi diễn giải.

Đây không phải quy tắc kỹ thuật khô khan. Đây là lý do đồ án này còn giá trị: **một hệ thống dự báo sai thì vô dụng, nhưng một hệ thống dự báo sai mà báo cáo trung thực thì vẫn dùng được để học.**

---

<a id="3"></a>
## 3. Dữ liệu đi đường nào

### 3.1 Câu chuyện nhà hàng

Hãy hình dung một nhà hàng chuẩn bị món ăn cho khách:

```
   ═══════════════════════════════════════════════════════════════
   BƯỚC 1 — MUA NGUYÊN LIỆU
   ═══════════════════════════════════════════════════════════════

   Yahoo Finance ─┐
   Finnhub        ├─→  Mua ở nhiều chỗ, giữ nguyên như mua
   Alpha Vantage  │    (chợ, siêu thị, vườn)
   SSI iBoard (VN) ┘

   ═══════════════════════════════════════════════════════════════
   BƯỚC 2 — SƠ CHẾ
   ═══════════════════════════════════════════════════════════════

   Rau rửa sạch, cắt bỏ phần hỏng, đo lại trọng lượng
   → Ghi ra giấy: "đã loại 3 kg rau héo, 2 kg rau đen"

   ═══════════════════════════════════════════════════════════════
   BƯỚC 3 — NẤU
   ═══════════════════════════════════════════════════════════════

   Cắt thành món, nêm, trang trí, đóng hộp sẵn cho khách
   → Kèm nhãn: "món này dành cho khách thích ít cay"
   ═══════════════════════════════════════════════════════════════
```

Ba tầng trong hệ thống chính là ba bước này:

| Tầng | Tên trong code | Ví dụ nhà hàng | Trạng thái dữ liệu |
|---|---|---|---|
| **Bronze** | `lakehouse/bronze.py` | Nguyên liệu vừa mua | Giữ **nguyên yên**, không sửa, không xoá |
| **Silver** | `lakehouse/silver.py` | Rau đã rửa, đã cắt | Sạch, chuẩn hoá, **có báo cáo đã loại gì** |
| **Gold** | `lakehouse/gold.py` | Món nấu xong, đóng hộp | Có đặc trưng + **có nhãn đáp án** |

### 3.2 Tại sao không gộp thành một tầng?

Đây là câu hỏi thầy hay hỏi nhất. Câu trả lời nằm ở chữ **"vì sao"**:

> Giả sử bạn viết sai công thức tính RSI (chỉ báo sức mạnh giá).
> - Nếu chỉ có 1 tầng: bạn phải **tải lại toàn bộ dữ liệu từ Internet**. Với 1.002 mã × 10 năm, đó là hàng giờ.
> - Với 3 tầng: bạn chạy lại Silver + Gold từ Bronze. Mất vài phút. Bronze vẫn nguyên vẹn để dựng lại từ đầu.

Ngoài ra còn 4 lý do cụ thể:

**Lý do 1 — Truy vết nguồn gốc.**
Mỗi mã ở Bronze có một file `_lineage.json` ghi rõ: lấy từ nguồn nào, lúc nào, bao nhiêu bản ghi. Nếu sau này phát hiện nhà cung cấp X trả sai cho mã Y, bạn biết chính xác cần sửa ở đâu và phạm vi bao nhiêu mã.

**Lý do 2 — Không mất dữ liệu khi làm sạch.**
Ở Silver, dòng hỏng **không bị xoá âm thầm**. Nó được tách riêng và ghi vào `_errors/` kèm lý do (`invalid_ohlc`, `missing`, `duplicate`, `invalid_volume`). Bạn luôn có thể hỏi "các dòng bị loại có đáng bị loại không?"

**Lý do 3 — Tính toán lặp lại cho ra cùng kết quả.**
Gold tính chỉ báo từ Silver. Chạy lại Gold 10 lần thì 10 lần cho cùng kết quả, vì Gold chỉ dùng Silver (đã sạch) chứ không dùng Bronze (còn bẩn).

**Lý do 4 — Chia sẻ được.**
Silver là đầu vào chung cho nhiều mục đích: tính chỉ báo, vẽ biểu đồ, huấn luyện mô hình. Không cần mỗi nơi tự làm sạch riêng (mà sẽ ra kết quả khác nhau).

### 3.3 Cụ thể Silver loại những gì

| Loại lỗi | Cách phát hiện | Ví dụ |
|---|---|---|
| **Thiếu giá** (`missing`) | Bất kỳ cột OHLCV nào là rỗng | `close = NaN` |
| **Giá vô lý** (`invalid_ohlc`) | `high < low`, hoặc `high < open/close`, hoặc `low > open/close` | `high = 100`, `low = 105` |
| **Khối lượng âm** (`invalid_volume`) | `volume < 0` | `volume = -5000` |
| **Trùng lặp** (`duplicate`) | Trùng cặp `(symbol, timestamp)` | 2 dòng cùng VCB ngày 15/01 |

Ngoài ra Silver còn:
- **Chuẩn hoá múi giờ về UTC.** Mọi nguồn lưu cùng một thời điểm theo một đơn vị, nên so sánh được với nhau.
- **Chuẩn hoá phiên giao dịch.** Mỗi ngày phải còn **đúng một nến**. Nếu trong ngày có nhiều dòng (do nguồn trả về nến mở cửa + nến đóng cửa + tick nội phiên), chúng được **gộp** lại: `open` = tick đầu, `high` = max, `low` = min, `close` = tick cuối, `volume` = tổng.

### 3.4 Cụ thể Gold thêm gì

Gold bắt đầu từ 12 cột gốc và thêm vào:

| Nhóm | Ví dụ | Câu hỏi mà nó trả lời |
|---|---|---|
| **Chỉ báo xu hướng** | SMA 5/10/20/50, EMA 12/26 | Giá đang đi đâu? |
| **Chỉ báo động lượng** | RSI 14, MACD, Bollinger Bands | Đang quá mua hay quá bán? |
| **Chỉ báo biến động** | ATR, ADX | Thị trường đang yên hay sóng lớn? |
| **Đặc trưng giá** | `return_1d`, `return_5d`, `log_return` | Hôm nay tăng hay giảm bao nhiêu? |
| **Đặc trưng khối lượng** | `volume_sma_20`, `volume_ratio` | Hôm nay có ai quan tâm bất thường không? |
| **Nhãn đáp án** | `target_close_next`, `target_direction_next` | **Ngày mai giá sẽ là bao nhiêu?** |

Tổng cộng khoảng **90 cột**. Cột cuối cùng là điều quan trọng nhất:

```
target_close_next = close.shift(-1)
```

Nghĩa là: ở dòng hôm nay, cột "đáp án" chứa giá đóng cửa **của ngày mai**.

Đây là cách mô hình học được "mai giá bao nhiêu". Và **đây cũng là chỗ dễ sai nhất** — xem mục 6.4.

### 3.5 Dữ liệu nằm ở đâu trên đĩa

| Thứ | Nằm ở đâu | Vì sao |
|---|---|---|
| Dữ liệu 3 tầng | **MinIO** (bucket `stock-bronze`, `stock-silver`, `stock-gold`) | Dữ liệu lớn, cần truy cập nhanh và có thể mở rộng |
| Lịch sử dự báo, chat AI, log chạy | **MySQL** (bảng `predictions`, `agent_conversations`, ...) | Dữ liệu nhỏ, cần truy vấn và join |
| Model đã train | **`backend/data/models/`** (filesystem) | Đọc bằng `pickle`, không phải object storage |

MinIO là gì? Hãy hình dung **ổ cứng mạng** của Google Drive, nhưng chạy ngay trên máy của bạn và truy cập bằng code thay vì trình duyệt. Nó nói chung theo giao thức **S3** của Amazon, nên nếu sau này chuyển lên AWS S3 thì chỉ cần đổi địa chỉ, không phải viết lại code.

Dữ liệu được chia nhỏ theo đường dẫn như sau:

```
stock-bronze/
└── symbol=AAPL/
    ├── year=2016/
    │   └── month=01/
    │       └── part-000.parquet
    ├── year=2016/
    │   └── month=02/
    │       └── part-000.parquet
    └── _lineage.json          ← nguồn + thời điểm + số bản ghi
```

**Parquet** là gì? Giống `.csv` nhưng nén theo **cột** thay vì theo hàng. Nếu bạn chỉ cần cột `close` của 1.002 mã trong 10 năm, Parquet chỉ đọc cột đó, còn CSV phải đọc toàn bộ rồi mới lọc. Đây là lý do đọc được nhanh hơn nhiều lần.

**Partition** (`symbol=AAPL/year=2016/month=01`) là cách chia nhỏ. Muốn đọc AAPL tháng 1/2016 thì đi thẳng vào thư mục đó, không đụng tới 120 thư mục khác.

---

<a id="4"></a>
## 4. Các thành phần và mối quan hệ giữa chúng

### 4.1 Bức tranh tổng thể

```
┌──────────────────────────────────────────────────────────────────────┐
│                    TRÌNH DUYỆT (React + TypeScript)                  │
│                                                                      │
│   Tổng quan · Dữ liệu thị trường · Phân tích kỹ thuật                │
│   Dự báo · Backtest · AI Agent · Trạng thái hệ thống                 │
│                                                                      │
│         ⇅  HTTP GET/POST, trao đổi JSON                              │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                       BACKEND (FastAPI + Python)                     │
│                                                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐         │
│  │  ĐỌC DỮ   │ │  DỰ BÁO   │ │  BACKTEST  │ │  AI AGENT  │           │
│  │  LIỆU      │ │            │ │            │ │            │         │
│  │            │ │ LR/ARIMA/  │ │ MA Cross   │ │ Gemini     │         │
│  │ Market     │ │ LSTM       │ │ RSI        │ │ + 17 tool  │         │
│  │ Service    │ │            │ │ Walk-fwd   │ │            │         │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘         │
│        │              │              │              │                │
│        └──────────────┴──────┬───────┴──────────────┘                │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │  LỚP DỮ LIỆU       │                            │
│                    │  Bronze→Silver→Gold │                           │
│                    │  + Pipeline         │                           │
│                    └─────────┬──────────┘                            │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │  HEAVY WORKER       │                           │
│                    │  (tiến trình con)   │                           │
│                    └────────────────────┘                            │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌─────────────┐        ┌─────────────┐        ┌─────────────────┐
│   MINIO     │        │   MYSQL     │        │   SCHEDULER     │
│             │        │             │        │   (cron)        │
│ stock-bronze│        │ predictions │        │                 │
│ stock-silver│        │ agent_chat  │        │ 2 lần/ngày:     │
│ stock-gold  │        │ users       │        │ sau khi sàn đóng│
└─────────────┘        └─────────────┘        └─────────────────┘
```

### 4.2 Điểm mấu chốt: trình duyệt không tính toán gì

Đây là điều quan trọng nhất về kiến trúc, và là câu trả lời cho câu hỏi "tại sao biểu đồ và bảng số liệu không bao giờ mâu thuẫn nhau".

```
   Trình duyệt  ──gửi yêu cầu──►  Backend  ──►  tính toán thật  ──►  trả JSON
        ▲                                                              │
        └──────────────────  hiển thị con số đã có  ◄─────────────────┘
```

Nếu trình duyệt tự tính (ví dụ tự chia phần trăm thay đổi), sẽ có hai nơi tính cùng một thứ và chúng sẽ lệch. Ở đây **mọi con số** trên web đều do backend tính và gửi sang.

### 4.3 Vai trò từng thành phần

#### Scheduler (cron) — đồng hồ báo giờ

```
backend/crontab:
  30 21  * * 1-5   job eod     ← sau khi NYSE đóng cửa
  30 3   * * 1-5   job eod     ← sau khi HOSE đóng cửa
```

Mỗi lần chạy, nó làm đúng 3 việc:

```
1. Nạp giá mới vào Bronze
2. Dựng lại Silver + Gold cho các mã thay đổi
3. Hỏi mô hình: "phiên kế tiếp giá sẽ ra sao?" → ghi vào MySQL
```

Mọi lần chạy đều ghi 1 dòng log có mốc thời gian vào `backend/logs/scheduled_jobs.log`. Hỏi "đêm thứ ba có chạy không?" thì mở file log ra là biết.

#### MinIO — kho dữ liệu lớn

Chỉ chứa dữ liệu dạng bảng (Parquet). Không chứa lịch sử dự báo.

#### MySQL — sổ tay hệ thống

Bảng `predictions` là **sổ tay dự báo**. Mỗi dòng ghi:

| Cột | Ý nghĩa |
|---|---|
| `symbol` | Mã cổ phiếu |
| `model_name` | Mô hình nào đã dự báo |
| `target_session` | Dự báo cho phiên nào (ngày giao dịch cụ thể) |
| `reference_close` | Giá đóng cửa thực tế của phiên **trước** đó (mốc) |
| `predicted_close` | Giá dự báo cho phiên đó |
| `predicted_return` | Tỷ lệ tăng dự báo |
| `actual_close` | Giá thực tế của phiên đó — **điền vào sau khi phiên diễn ra** |
| `abs_error` | Sai số tuyệt đối |
| `error_pct` | Sai số phần trăm |
| `direction_correct` | Đoán đúng hướng tăng/giảm không (1/0) |
| `data_staleness_days` | Dữ liệu đầu vào bị trễ bao nhiêu phiên giao dịch. `0` = dữ liệu còn mới |

Nguyên tắc: `unique (symbol, model_name, target_session)`. Nghĩa là mỗi cặp (mã, mô hình, phiên) chỉ có một dự báo — chạy lại cũng không tạo bản trùng.

**Ý nghĩa quan trọng:** `actual_close` điền vào **sau khi phiên thật sự diễn ra**. Đó là cách hệ thống tự chấm điểm mình. Không có `actual_close` thì dòng đó chưa được chấm, không đưa vào thống kê.

**Cột `data_staleness_days` — vì sao cần?**

Đôi khi dữ liệu chưa kịp tải về: sàn đã giao dịch xong thứ Tư, mà hệ thống mới có dữ liệu tới thứ Hai. Lúc đó hệ thống dự báo cho thứ Sáu — tức phiên gần nhất chưa xảy ra — chứ không phải cho "ngày mai".

Dự báo đó vẫn hợp lệ, nhưng nó dựa trên lịch sử cũ hơn thị trường. Cột này ghi lại mức độ trễ đó:
- `0` — dữ liệu đầy đủ, dự báo bình thường
- `1`, `2`, `3`... — thiếu nhiều phiên, dữ liệu càng cũ
- Trống (`NULL`) — dòng ghi trước khi hệ thống biết đo cái này. Trống **không phải** "0": "chưa đo được" khác "đo ra 0".

Khi giá trị lớn hơn 0, thẻ "Dự báo phiên kế tiếp" trên Dashboard hiện dòng cảnh báo
**"Dữ liệu trễ N phiên giao dịch"** — để bạn biết con số đó được tính trên dữ liệu cũ hơn.

#### Heavy Worker — tiến trình con

Khi bạn bấm nút "chạy walk-forward" (mất vài giây) hoặc hệ thống tự refresh 1.002 mã (mất hàng phút), việc đó **không chạy trong server chính**.

Lý do: Python có **GIL** (Global Interpreter Lock) — chỉ một luồng chạy code Python tại một thời điểm. Nếu refresh đang chiếm CPU, các yêu cầu của bạn phải xếp hàng đợi và web bị treo.

Đo được trên chính hệ thống này:

| Tình huống | Thời gian walk-forward |
|---|---|
| Máy rảnh | 2,2 giây |
| Refresh đang chạy (cùng process) | 13,3 giây (chậm 6×) |
| Nhiều refresh chồng nhau | 96 giây (chậm 40×, web vỡ) |
| Tách sang tiến trình con | 2,2 giây (không đổi) |

Giải pháp: chạy việc nặng trong **tiến trình riêng** (`ProcessPoolExecutor`), mỗi tiến trình có ổ khoá riêng nên không chờ nhau.

Còn thêm **Request Gate**: nếu đang có người dùng thao tác, refresh tự nhường đường. Đánh đổi: refresh chậm đi, nhưng refresh là việc không ai nhìn thấy, còn yêu cầu tương tác là việc mọi người đều chờ.

### 4.4 Luồng AI Agent

Đây là phần dễ hiểu nhầm nhất, nên đọc kỹ.

```
Bạn hỏi (tiếng Việt):
"MA crossover trên AAPL có ăn không?"

   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend nhận câu hỏi                                       │
│                                                             │
│  ① LLM (Gemini) đọc câu hỏi, chọn tool cần dùng             │
│     → quyết định: cần gọi run_walk_forward(AAPL, ma_...)    │
│                          │                                  │
│  ② Tool chạy THẬT trong tiến trình con                      │
│     → đọc dữ liệu thật từ MinIO                             │
│     → chạy 159 cửa sổ walk-forward                          │
│     → trả về: consistency 13,2%, overfitting_ratio 4,0      │
│                          │                                  │
│  ③ LLM viết câu trả lời dựa trên SỐ vừa nhận                │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
        Câu trả lời + TOOL TRACE (danh sách lệnh đã gọi)
```

**Điểm mấu chốt: số trong câu trả lời không do AI sinh ra.**

Đây là ranh giới giữa "AI agent demo" (chatbot bịa đặt số, nghe rất thuyết phục nhưng vô giá trị) và "hệ thống nghiên cứu" (số có nguồn gốc, kiểm chứng được).

Nếu hết API key Gemini, hệ thống vẫn chạy: một bộ định tuyến cục bộ nhận diện từ khoá và gọi đúng tool, chỉ khác ở chỗ không có phần "diễn giải cho dễ hiểu".

### 4.5 Bảng quan hệ nhanh

| Thành phần | Đọc từ | Ghi vào | Được gọi bởi |
|---|---|---|---|
| Bronze | Internet (Yahoo, Finnhub, SSI...) | MinIO | Pipeline, cron |
| Silver | Bronze | MinIO | Pipeline |
| Gold | Silver | MinIO | Pipeline, dự báo, backtest |
| Dự báo | Gold + model đã train | MySQL (`predictions`) | Cron, nút bấm trên web |
| Backtest | Gold | MySQL (`backtest_runs`) | Nút bấm trên web |
| AI Agent | Gọi tool → đọc Gold | MySQL (`agent_conversations`) | Khung chat trên web |

---

<a id="5"></a>
## 5. Khái niệm chứng khoán mà hệ thống dùng

### 5.1 Chỉ báo kỹ thuật

Chỉ báo là công thức toán học trên dữ liệu giá, cho biết "xu hướng" hoặc "trạng thái" của cổ phiếu.

| Chỉ báo | Công thức thuần văn | Cách đọc |
|---|---|---|
| **SMA** (trung bình trượt) | Trung bình giá đóng cửa của N ngày gần nhất | SMA20 đang tăng = giá đang đi lên trung bình |
| **EMA** | Giống SMA nhưng ngày gần đó có trọng số cao hơn | EMA phản ứng nhanh hơn SMA |
| **RSI** | So sánh tổng phần tăng với tổng phần giảm trong 14 ngày, quy về 0–100 | >70 quá mua, <30 quá bán, ~50 trung tính |
| **MACD** | EMA12 − EMA26, và đường tín hiệu EMA9 của nó | MACD cắt lên đường tín hiệu = hướng tăng |
| **Bollinger Bands** | SMA20 ± 2 độ lệch chuẩn | Giá chạm dải trên = có thể quá mua; dải hẹp = sắp biến động mạnh |
| **ATR** | Trung bình biến động thật | Dùng để đặt mức cắt lỗ hợp lý |
| **ADX** | Độ mạnh của xu hướng (không phải hướng) | >25 = xu hướng mạnh |

**Hệ thống dùng chỉ báo để làm gì?**

1. **Làm đặc trưng cho mô hình.** Gold tính hàng chục chỉ báo, đưa vào mô hình như "input".
2. **Làm tín hiệu cho chiến lược.** Backtest dùng SMA để quyết định mua/bán.
3. **Hiển thị cho người dùng.** Trang "Phân tích kỹ thuật" vẽ các đường này.

### 5.2 Ba loại mô hình dự báo

Hệ thống chạy **3 mô hình** trên cùng một tập dữ liệu, rồi báo cáo cả 3.

| Mô hình | Ý tưởng | Ưu điểm | Nhược điểm |
|---|---|---|---|
| **Linear Regression** (hồi quy tuyến tính) | Dựa trên các đặc trưng, tìm đường thẳng khớp nhất với dữ liệu quá khứ | Nhanh, dễ hiểu, ít bị overfit | Chỉ nắm được quan hệ tuyến tính |
| **ARIMA** (mô hình tự hồi quy) | Dùng chính lịch sử giá để dự đoán bước tiếp theo, có tính đến "xu hướng" và "chu kỳ" | Nắm được quy luật thời gian | Cần nhiều dữ liệu, không dùng được chỉ báo ngoài giá |
| **LSTM** (mạng nơ-ron hồi quy) | Mạng nhớ các bước thời gian gần đây (60 phiên) rồi dự đoán bước sau | Học được mối quan hệ phức tạp | Rất dễ overfit, cần nhiều RAM để train, khó giải thích |

**Điểm quan trọng về LSTM trong đồ án này:** mô hình **không** dự báo mức giá tuyệt đối, mà dự báo **tỷ lệ thay đổi**.

```
Cách cũ (sai):  học "26 → 196", rồi hỏi "345 là bao nhiêu?"
                 → mạng chưa từng thấy con số nào > 196, nên không dám đoán cao hơn 196
                 → MAE = 50,48

Cách mới (đúng): hỏi "mai tăng hay giảm bao nhiêu phần trăm?"
                 → câu trả lời giống nhau dù giá là 26, 345 hay 1725
                 → 26 × 1,015 = 26,39
                 → 345 × 1,015 = 350,18
                 → 1725 × 1,015 = 1750,88
                 → MAE = 4,24  (giảm 91,6%)
```

Cùng một mạng, cùng một cách chia dữ liệu, cùng một seed — chỉ khác cách đặt câu hỏi cho nó.

### 5.3 Backtest — "chơi chứng khoán trên giấy"

**Backtest** là: đưa chiến lược vào dữ liệu lịch sử và xem nó sẽ kiếm được bao nhiêu.

```
Chiến lược: "Khi SMA20 cắt lên SMA50 thì MUA.
              Khi SMA20 cắt xuống SMA50 thì BÁN."

Chạy trên lịch sử VCB 2016–2026:
   → mua ở đây, bán ở đây, ...
   → tổng lợi nhuận: +12,4%
   → số lần thắng/thua: 18/11
   → mức lỗ tệ nhất (max drawdown): −8,2%
```

**Hai chiến lược có trong hệ thống:**

| Chiến lược | Quy tắc |
|---|---|
| **MA Crossover** | Mua khi SMA nhanh cắt lên SMA chậm, bán khi cắt xuống |
| **RSI Strategy** | Mua khi RSI dưới 30 (quá bán), bán khi RSI trên 70 (quá mua) |

### 5.4 Các chỉ số đo backtest

| Chỉ số | Nghĩa | Cách đọc |
|---|---|---|
| **Total Return** | Tổng lợi nhuận % | Lãi bao nhiêu |
| **Win Rate** | % lệnh thắng | 60% nghĩa là 6/10 lệnh thắng |
| **Sharpe Ratio** | Lợi nhuận chia cho độ biến động | Cao = kiếm nhiều mà ít dao động |
| **Max Drawdown** | Mức lỗ tệ nhất | −20% nghĩa là từng mất 20% vốn |
| **Profit Factor** | Tổng lời / tổng lỗ | >1 = tổng lãi lớn hơn tổng lỗ |

**Max Drawdown** là chỉ số quan trọng nhất với người mới, và là chỉ số mà đồ án này tìm được điều có giá trị nhất (xem mục 7.4).

### 5.5 Walk-forward validation — kiểm chứng như người thật

Đây là ý tưởng quan trọng nhất về mặt khoa học, và cũng là phần khó nhất.

**Vấn đề:** nếu bạn dùng toàn bộ dữ liệu 2016–2026 để chọn tham số tốt nhất, rồi báo cáo điểm trên chính dữ liệu đó, thì bạn đang tự đánh giá bài thi mà bạn đã nhìn đáp án trước.

**Cách kiểm chứnh đúng:** chia dữ liệu thành các cửa sổ trượt, mỗi cửa sổ học trước rồi thi sau, và trượt đi.

```
LỊCH SỬ GIÁ AAPL 2016 ────────────────────────────────────────► 2026

CỬA SỔ 0    [████ HỌC 180 ngày ████][░░ THI 30 ngày ░░]
CỬA SỔ 1         [████ HỌC 180 ngày ████][░░ THI 30 ngày ░░]
CỬA SỔ 2              [████ HỌC 180 ngày ████][░░ THI 30 ngày ░░]
...
CỬA SỔ 158                                                   [░░ THI 30 ngày ░░]

████ = dùng để học/chọn tham số
░░░ = CHƯA TỪNG THẤY, chỉ dùng để đo
```

Nó mô phỏng đúng việc dùng chiến lược ngoài đời: khi bạn ra quyết định, bạn chỉ có dữ liệu **tới hôm nay**.

**Hai lỗi kinh điển mà đồ án này đã tìm ra và sửa:**

**Lỗi 1 — Thiếu dữ liệu khởi động.**
Cửa sổ thi 30 ngày chỉ có ~21 phiên giao dịch. Nhưng MA Crossover cần SMA(50) = 50 phiên để tính. Không có đủ → không có tín hiệu → 0 giao dịch.

*Fix:* mượn 50 phiên cuối của đoạn học làm "khởi động" (warmup), tính chỉ báo trên [warmup + test], nhưng **loại warmup khỏi phần tính lợi nhuận**. Warmup nằm hoàn toàn trong quá khứ nên không rò rỉ tương lai.

*Bằng chứng:* 0 giao dịch → 41 giao dịch.

**Lỗi 2 — So sánh khác đơn vị.**
Cửa sổ 0 học 180 ngày. Cửa sổ 175 học 10 năm. Chia tỷ lệ lợi nhuận 10 năm ÷ 1 tháng ra 790 — con số vô nghĩa.

*Fix:* dùng cửa sổ học **cố định** 180 ngày, rồi chuẩn hoá cả hai vế về 1 năm.

*Bằng chứng:* 790 → 4,0.

### 5.6 Look-ahead bias — cái lỗi nguy hiểm nhất

**Look-ahead bias** = mô hình "nhìn thấy" tương lai khi đưa ra quyết định.

Hình dung bạn là người ghi lịch sử thị trường. Mỗi tối bạn nhìn giá đóng cửa hôm nay, rồi viết ra giá đóng cửa ngày mai. Kết quả: bản ghi của bạn **luôn luôn chính xác**, vì bạn đã nhìn ngày mai rồi.

Đó chính xác là look-ahead bias. Mô hình dự báo giống vậy thì điểm 99% nhưng vô nghĩa.

Đồ án này có **3 lớp bảo vệ**:

```
LỚP 1 — ĐẦU VÀO CHỈ NHÌN VỀ QUÁ KHỨ
   target_close_next = close.shift(-1)   ← đáp án ở tương lai: ĐƯỢC PHÉP
   feature thì không bao giờ dùng shift dương ← TUYỆT ĐỐI KHÔNG

LỚP 2 — CHIA DỮ LIỆU THEO THỜI GIAN, KHÔNG XÁO TRỘN
   TRAIN 70% (2016 → 2025) │ VALIDATION 15% │ TEST 15% (giữ kín)
   KHÔNG dùng train_test_split()  ← vì hàm đó xáo trộn ngẫu nhiên
   Scaler tính trên train, chỉ transform trên validation
   Early stopping dùng validation, KHÔNG dùng test

LỚP 3 — LỆNH KHỚP Ở BAR KẾ TIẾP
   Tín hiệu sinh lúc 15:00 ngày t
   Lệnh khớp lúc 9:30 ngày t+1 (giá mở cửa)
   → Lúc ra quyết định, bạn KHÔNG biết giá ngày t+1
```

**Cách tự kiểm tra:** nếu mô hình có nhìn thấy tương lai, chạy lại 2 lần trong cùng một ngày sẽ cho **khác nhau** (vì random state đổi). Hệ thống này cố định seed (`set_global_seed(42)`) và chia theo thời gian, nên kết quả **lặp lại được**.

---

<a id="6"></a>
## 6. Mô hình dự báo hoạt động thế nào

### 6.1 Quy trình đầy đủ

```
[BẠN BẤM NÚT "Train và Dự báo"]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 1 — NẠP DỮ LIỆU                                        │
│   GoldLayer().read("AAPL")                                  │
│   → đọc ~121 file parquet, 2.500 hàng × 90 cột              │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 2 — CHUẨN BỊ                                           │
│   drop dòng có target NaN   (dòng cuối chưa có "đáp án")    │
│   drop dòng có feature NaN  (chưa đủ 50 phiên cho SMA50)    │
│   set_global_seed(42)   ← để kết quả lặp lại được           │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 3 — CHIA THEO THỜI GIAN (KHÔNG XÁO TRỘN)               │
│                                                             │
│   ┌──────────────┬───────────────┬──────────────┐           │
│   │ TRAIN 70%    │ VALIDATION 15%│  TEST 15%    │           │
│   │ 1.750 phiên  │ 375 phiên     │ 375 phiên    │           │
│   │ mô hình HỌC  │ DỪNG SỚM      │ ĐO 1 LẦN    │            │
│   │              │               │ DUY NHẤT     │           │
│   └──────────────┴───────────────┴──────────────┘           │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 4 — TRAIN 3 MÔ HÌNH                                    │
│   Linear Regression  │  ARIMA (5,1,0)  │  LSTM (2 lớp)      │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 5 — ĐO TRÊN TẬP TEST                                   │
│   MAE  ·  RMSE  ·  MAPE  ·  ĐÚNG HƯỚNG (DA)                 │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ BƯỚC 6 — LƯU                                                │
│   MinIO: stock-models/AAPL/<model>/                         │
│   MySQL : model_runs                                        │
└──────────────────────────────────────────────��──────────────┘
```

### 6.2 Bốn chỉ số đánh giá

| Chỉ số | Công thức | Ý nghĩa |
|---|---|---|
| **MAE** | Trung bình \|dự báo − thực tế\| | Sai số trung bình, tính bằng đơn vị tiền |
| **RMSE** | √(trung bình bình phương sai số) | Giống MAE nhưng phạt nặng hơn lỗi lớn |
| **MAPE** | Trung bình % sai số | Sai số tương đối, so sánh được giữa các mã có giá khác nhau |
| **DA** (độ đúng hướng) | % lần đoán đúng tăng/giảm | Chỉ số quan trọng nhất về mặt nghiệp vụ |

**Về MAPE:** có một cái bẫy mà đồ án này đã gặp phải. `mean_error_pct` tính trên **toàn bộ** mã cho ra 263,85%, con số vô lý. Nguyên nhân: một số mã có giá rất nhỏ (ví dụ `VIV.PA` giá 1,69), nên sai số 4,5đ trên giá 1,69 là **266%**. Lỗi tuyệt đối nhỏ nhưng phần trăm lại khổng lồ.

Vì vậy hệ thống báo cáa **median** (trung vị) thay vì mean cho phần trăm sai số: median 1,15% là con số đáng tin. Phần trăm theo từng mã vẫn được giữ nguyên, chỉ là con số tổng hợp dùng trung vị.

### 6.3 Kết quả thật của hệ thống

Đo ngày 17/11/2026 trên toàn bộ sổ dự báo:

| Chỉ số | Giá trị | Đọc là gì |
|---|---|---|
| Tổng số dự báo | 46.505 | Mỗi dòng là một lần dự báo cho một phiên cụ thể |
| Đã chấm điểm | 46.385 | Đã biết giá thực tế của phiên đó |
| MAE | 335,58 | Sai số trung bình 336 đơn vị tiền |
| Median sai số % | 1,15% | Sai số của mã "điển hình" |
| WAPE | 2,75% | Sai số % có trọng số theo giá |
| **Độ đúng hướng** | **50,58%** | **Gần như ngẫu nhiên** |

> **Đo lại ngày 18/11/2026:** tổng số dự báo là **46.531**, trong đó **46.487**
> dòng đã chấm (tăng 102 dòng vì các phiên 17–18/11 đã đóng cửa và được chấm
> bằng giá thật). Median sai số vẫn **1,15%**, MAE **337,61**, WAPE **2,76%**,
> độ đúng hướng **50,60%**. Hệ thống bắt đầu đo **độ trễ của dữ liệu đầu vào**
> cho mọi dự báo mới — xem mục 6.2 ở trên.

Và đây là điểm quan trọng nhất của cả đồ án:

> **50,60% nghĩa là hệ thống gần như không có khả năng dự đoán hướng giá vượt quá ngẫu nhiên.**

Ba mô hình đều cho kết quả tương tự. Đây là kết quả **thật**, và đồ án báo cáo nguyên vẹn thay vì chỉ chọn mô hình đẹp nhất.

### 6.4 Vì sao dự báo giá lại khó đến vậy?

Người mới thường nghĩ: "có dữ liệu 10 năm, sao không dự báo được?"

Lý do:

1. **Thị trường đã phản ánh thông tin.** Giá cổ phiếu ngày nay đã chứa mọi tin tức công ty đã công bố. Để dự báo giá mai, bạn cần dự báo **tin tức mai** — mà tin tức tương lai thì không ai biết.

2. **Nhiễu lớn hơn tín hiệu.** Giá dao động hằng ngày vì hàng triệu lệnh nhỏ của người bán lẻ. Phần "nhiễu" này thường lớn hơn phần "xu hướng".

3. **Hiệu ứng hồi quy về trung bình.** Sau khi giá tăng mạnh, xác suất giá giảm trong ngày tiếp theo cao hơn — nhưng hiệu ứng này rất nhỏ.

4. **Chi phí giao dịch ăn hết lợi nhuận.** Một chiến lược cần thắng đủ lớn mới còn lãi sau phí 0,1% và trượt giá 0,05% mỗi lượt.

Đây không phải lý do để bỏ cuộc. Đây là lý do đồ án tập trung vào **đo lường trung thực** thay vì **hứa hẹn lợi nhuận**.

---

<a id="7"></a>
## 7. Backtest và đường cơ sở

### 7.1 Vấn đề: so với cái gì?

Nếu bạn nói "chiến lược MA Crossover kiếm được 320% trên AAPL", thầy sẽ hỏi: **"so với cái gì?"**

Nếu AAPL tăng 1.142% trong cùng khoảng thời gian, thì chiến lược của bạn đã **thua** một cách rất lớn. Chỉ cần mua và ngồi đó cũng tốt hơn.

Đó là lý do đồ án này xây dựng **đường cơ sở mua và giữ** (buy-and-hold).

### 7.2 So sánh công bằng

Đường cơ sở phải chơi theo **đúng luật** như chiến lược, nếu không thì so sánh là bất công:

| Điều khoản | Chiến lược | Mua và giữ |
|---|---|---|
| Cùng một mã cổ phiếu | OK | OK |
| Cùng bộ phiên giao dịch | OK | OK |
| Cùng mức phí (0,1%) | OK | OK |
| Cùng độ trượt giá (0,05%) | OK | OK |
| Lệnh khớp ở giá mở cửa bar kế tiếp | OK | OK |

**Vì sao chọn mua và giữ chứ không chọn chỉ số (S&P 500, VN-Index)?**

Vì chỉ số là **tài sản khác**: khác rủi ro, khác tiền tệ, khác thanh khoản. So sánh chiến lược của VCB với VN-Index là so sánh giữa hai thứ không cùng loại.

Mua và giữ **chính cổ phiếu đó** trên **chính những phiên đó** là so sánh chặt nhất có thể. Nó trả lời đúng câu hỏi mà chiến lược tuyên bố: *"chiến lược của tôi có tốt hơn việc cứ nắm giữ không?"*

### 7.3 Kết quả đo đa mã — phần trung thực nhất của đồ án

Đo ngày 11/11/2026: **101 mã, 13 sàn, 3.687 cửa sổ kiểm tra, 0 mã lỗi đọc.**

| Chỉ số | MA Crossover | RSI Strategy | Mua và giữ |
|---|---|---|---|
| Lợi nhuận ngoài mẫu (median) | 0,22% | 0,42% | **2,28%** |
| % mã có lãi | 60,4% | 70,3% | **91,1%** |
| % mã chiến lược thắng baseline | 8,9% | 13,9% | — |
| Mức lỗ tệ nhất (median max drawdown) | −4,56% | **−2,00%** | −11,87% |

**Kết luận không dễ chịu nhưng rất đáng giá:**

> Chiến lược **thua** đường cơ sở ở **cả 13 sàn**. Ở 91,1% số mã, hành động "mua một lần rồi giữ" tốt hơn chiến lược phức tạp.

**Nhưng có một điều chiến lược làm được:** nó **giảm rủi ro**. Mức lỗ tệ nhất giảm từ −11,87% (mua và giữ) xuống −2,00% (RSI). Đó là một đánh đổi có thật: **ít lợi nhuận hơn, nhưng ít đau hơn nhiều.**

### 7.4 Vì sao đây là kết quả tốt cho đồ án

Nghe có vẻ ngược, nhưng hãy nghĩ từ góc nhìn của người chấm:

| Nếu đồ án báo | Thầy nghĩ gì |
|---|---|
| "Chiến lược MA Crossover sinh lời 320%, vượt trội benchmark" | "Con số này nghe giống backtest sai. Thầy sẽ hỏi kỹ." |
| "Chiến lược thua mua và giữ ở 91% số mã, nhưng giảm max drawdown từ −11,87% xuống −2,00%" | "Em đo được sự thật và dám báo cáo. Đồ án đáng tin." |

Một đồ án báo cáo kết quả xấu kèm phương pháp đo chặt chẽ **chứng minh** phương pháp của em đúng. Một đồ án báo cáo kết quả tốt nhưng không bước vào chiến lược thua baseline thì chỉ chứng minh em chưa kiểm tra.

---

<a id="8"></a>
## 8. AI Agent trong hệ thống này

### 8.1 Nó làm gì

Bạn hỏi bằng tiếng Việt, hệ thống trả lời bằng tiếng Việt, kèm danh sách những lệnh nó đã chạy để lấy số.

**17 tool** chia làm 4 nhóm:

| Nhóm | Tool ví dụ | Dùng để |
|---|---|---|
| Dữ liệu thị trường | `query_stock_data`, `get_market_summary`, `get_orderbox` | Lấy giá, thống kê, sàn |
| Chỉ báo kỹ thuật | `calculate_indicators` | Tính RSI, MACD, SMA... |
| Dự báo & backtest | `forecast_stock`, `compare_models`, `run_backtest`, `run_walk_forward` | Chạy mô hình, kiểm chứng chiến lược |
| Báo cáo tài chính | `get_fundamental_metrics`, `get_income_statement`, `get_balance_sheet`, `get_cash_flow` | Số liệu doanh thu, lợi nhuận |

### 8.2 Ví dụ câu hỏi và cách nó xử lý

| Bạn hỏi | Nó gọi tool | Kết quả |
|---|---|---|
| "AAPL hôm nay giá bao nhiêu?" | `query_stock_data` | Giá thật từ Gold + source_layer |
| "RSI của VCB là bao nhiêu?" | `calculate_indicators` | RSI14 tính từ Gold |
| "MA crossover trên AAPL có ăn không?" | `run_walk_forward` | consistency, overfitting_ratio, số cửa sổ |
| "So sánh LR với LSTM cho MSFT" | `compare_models` | Bảng MAE/RMSE/MAPE/DA của cả hai |
| "Doanh thu quý gần nhất của FPT?" | `get_income_statement` | Số liệu từ nguồn |

### 8.3 Điểm mấu chốt: số không do AI bịa

```
┌─────────────────────────────────────────────────────────────┐
│  SỐ TRONG CÂU TRẢ LỜI  ←  KHÔNG  ←  LLM TỰ NGHĨ RA          │
│                                                             │
│  LLM chỉ làm 2 việc:                                        │
│    ① hiểu câu hỏi → chọn tool nào                           │
│    ② viết lại số liệu thành câu dễ hiểu                     │
│                                                             │
│  Mọi con số → từ tool → từ backend → từ dữ liệu thật        │
└─────────────────────────────────────────────────────────────┘
```

**Cách kiểm chứng:** mở phần **tool trace** trong giao diện chat. Bạn sẽ thấy chính xác lệnh nào được gọi, với tham số gì, và kết quả trả về ra sao. Đối chiếu lại với API là kiểm tra được.

---

<a id="9"></a>
## 9. Các ví dụ sử dụng thật

### 9.1 Use case 1 — Người nghiên cứu muốn biết mô hình nào đáng dùng

```
Bước 1: Vào trang "Dự báo" → tab "Huấn luyện & so sánh model"
Bước 2: Chọn mã AAPL → bấm "Train"
Bước 3: Đọc bảng so sánh 3 mô hình trên cùng tập test
Bước 4: Kết luận
```

Kết quả (đo ngày 06/11/2026, AAPL, tập hold-out 375 phiên):

| Mô hình | MAE | RMSE | MAPE | Đúng hướng |
|---|---|---|---|---|
| Linear Regression | 2,994 | 4,251 | 1,096% | 53,48% |
| ARIMA (5,1,0) | 3,006 | 4,293 | 1,108% | 50,79% |
| LSTM | 3,294 | 4,628 | 1,161% | 46,86% |

**Cách đọc đúng:** LR có MAE thấp nhất, nhưng cả 3 đều có độ đúng hướng quanh 50%, tức gần như không có kỹ năng dự báo hướng. LSTM thậm chí tệ hơn ngẫu nhiên.

**Cách đọc sai:** "LSTM tệ nhất, vậy bỏ LSTM đi."

Cách đọc sai thứ 2 là cherry-picking. Cách đọc đúng là báo cả 3 trên cùng một tập và để người đọc tự kết luận.

### 9.2 Use case 2 — Kiểm tra một chiến lược trước khi dùng

```
Bước 1: Trang "Backtest" → tab "Walk-forward đa mã"
Bước 2: Xem phân phối theo 13 sàn
Bước 3: So sánh với đường cơ sở mua và giữ
```

**Câu hỏi người dùng trả lời được:** "Chiến lược này có đáng dùng không?" → Câu trả lời trung thực: "Không thắng mua và giữ, nhưng giảm rủi ro."

### 9.3 Use case 3 — Theo dõi dự báo hằng đêm

```
Mỗi tối sau khi sàn đóng cửa:
  cron nạp giá mới → dựng Silver/Gold → dự báo phiên kế tiếp → ghi MySQL

Sáng hôm sau bạn mở web:
  thẻ "Dự báo phiên kế tiếp" trên Dashboard hiện dự báo của đêm qua
  khi phiên hôm nay đã diễn ra, actual_close được điền vào
  → hệ thống tự chấm điểm
  → trang "Kiểm chứng dự báo" hiện bảng đối chiếu dự báo vs thực tế
```

### 9.4 Use case 4 — Hỏi bằng tiếng Việt

```
Bạn: "RSI của BTC-USD hiện tại bao nhiêu và có nên mua không?"
Agent: gọi calculate_indicators("BTC-USD") → nhận RSI thật
       → viết câu trả lời + hiện tool trace
```

### 9.5 Use case 5 — Chất lượng dữ liệu có đủ dùng không?

```
Trang "Trạng thái hệ thống" → cổng chất lượng (quality gate)
```

Cổng này chạy 7 kiểm tra:

| Kiểm tra | Hỏi cái gì |
|---|---|
| `schema_valid` | Đủ 12 cột gốc chưa |
| `no_missing` | Có dòng thiếu giá không |
| `ohlc_valid` | Có giá vô lý không (high < low) |
| `volume_valid` | Có khối lượng âm không |
| `no_duplicates` | Có dòng trùng không |
| `timestamp_monotonic` | Thời gian có đi đúng thứ tự không |
| `layer_agreement` | Bronze, Silver, Gold có thống nhất không |

**Đặc biệt `layer_agreement`:** đây là kiểm tra bắt được loại lỗi nguy hiểm nhất. Nếu Bronze có giá mới nhưng Silver/Gold chưa được dựng lại, hệ thống sẽ dùng **hai nguồn khác nhau** cho cùng một ngày và so sánh chúng với nhau → phát hiện ra ngay.

Một ví dụ thật đã xảy ra: crypto (BTC-USD, ETH-USD) giao dịch 24/7. Giữa chừng phiên, Bronze có giá "đang forming" 65.305, còn Silver/Gold có giá đã chốt 65.435. Cổng chất lượng báo `layer_agreement: failed`. Cách sửa: chạy lại pipeline để dựng đồng bộ cả 3 tầng.

### 9.6 Use case 6 — Kiểm chứng số liệu trong báo cáo

Đồ án có sẵn 3 script kiểm chứng:

```powershell
cd backend

# 1. Đối chiếu mọi con số trong bài luận với hệ thống đang chạy
.\.venv\Scripts\python.exe scripts\verify_thesis_numbers.py

# 2. Kiểm tra cấu trúc markdown (bảng, heading, code fence)
.\.venv\Scripts\python.exe scripts\check_thesis_markdown.py

# 3. Kiểm tra văn phong có bị máy viết không
.\.venv\Scripts\python.exe scripts\check_thesis_style.py
```

Lần chạy cuối (16/11/2026): `ALL CONSISTENT` — 8 chỉ số khớp MySQL/MinIO, 0 lỗi cấu trúc, 0 mẫu văn phong máy.

---

<a id="10"></a>
## 10. Hệ thống này KHÔNG làm gì

Phần này quan trọng ngang với phần "làm gì". Đọc trước khi bảo người khác về hệ thống này.

| KHÔNG làm | Vì sao |
|---|---|
| **Không giao dịch thật** | Không có kết nối tới sàn để đặt lệnh. Không có tài khoản, không rủi ro mất tiền. |
| **Không cam kết lợi nhuận** | Kết quả đo được là 50,71% đúng hướng, tức gần như ngẫu nhiên. |
| **Không dùng dữ liệu giả** | Không có fallback tổng hợp, không có số bịa trong UI. Thiếu dữ liệu thì báo lỗi kèm lý do. |
| **Không dùng dữ liệu trong ngày** | Chỉ có bar **ngày**. Không trade được intraday. |
| **Không đặt mức cắt lỗ / quản trị danh mục thật** | Backtest chỉ giả lập. Không có logic sizing, risk limit, hay rebalancing thực tế. |
| **Không phải lời khuyên tài chính** | Đây là prototype nghiên cứu học thuật. |
| **Không có tin tức / sentiment** | Đã thử, đo được độ phủ 0,00% và tin bị gắn sai mã → đã **gỡ khỏi dự án** (12/11/2026). |
| **Không chạy realtime** | Đường dẫn realtime (WebSocket, Kafka) đã thử và **đã gỡ** (11/11/2026). Dữ liệu đến từ cron 2 lần/ngày. |
| **Không dùng Kafka / Iceberg** | Đã thử, không đáng giữ với khối lượng dữ liệu hiện tại → đã gỡ (10/11/2026). |

### 10.1 Về những thứ đã bị gỡ

Ba thứ đã được thử, đo, rồi bỏ:

| Đã thử | Kết quả đo | Quyết định |
|---|---|---|
| Kafka + Iceberg (10/11) | Một bản sao dữ liệu thừa, thêm 1 JVM phải vận hành, trong khi pipeline chỉ append | Gỡ. Parquet + quy ước đường dẫn là đủ. |
| Realtime streaming (11/11) | Bộ nhớ đệm SSE đo được **0 mã / 0 bar**. Chưa từng ghi vào Bronze. | Gỡ. Không mất bản ghi nào. |
| Tin tức + sentiment (12/11) | Độ phủ **0,00%** (10 mã / 1.002 mã, 89 bài). Tin thật bị **gắn sai mã** do trùng mã giữa các sàn. | Gỡ toàn bộ. |

**Đây là một trong những điểm mạnh của đồ án.** Nhiều đồ án giữ lại công nghệ cho "nhìn pro" dù nó không hoạt động. Đồ án này đo trước, rồi bỏ, và **ghi lại lý do kèm số liệu** để người sau không phải đo lại.

---

<a id="11"></a>
## 11. Tự kiểm tra hiểu chưa

### 11.1 10 câu hỏi, trả lời được nghĩa là hiểu

| # | Câu hỏi | Đáp án ngắn |
|---|---|---|
| 1 | OHLCV gồm những gì? | Giá mở, cao, thấp, đóng cửa và khối lượng của một phiên |
| 2 | Vì sao có cả `close` và `adj_close`? | `adj_close` đã điều chỉnh cổ tức/tách cổ, dùng để tính lợi nhuận cho đúng |
| 3 | Ba tầng là gì? | Bronze (giữ nguyên) → Silver (làm sạch + đếm rác) → Gold (tính chỉ báo + gắn nhãn) |
| 4 | Vì sao không gộp 3 tầng? | Để tính lại nhanh khi sửa công thức, không phải tải lại từ Internet; và giữ được dữ liệu gốc |
| 5 | Silver loại những gì? | Dòng thiếu giá, giá vô lý, khối lượng âm, dòng trùng |
| 6 | `target_close_next = close.shift(-1)` nghĩa là gì? | Cột đáp án ở dòng hôm nay chứa giá ngày mai |
| 7 | Look-ahead bias là gì? | Mô hình nhìn thấy tương lai khi quyết định → điểm cao giả |
| 8 | Vì sao phải so với mua và giữ? | Vì "lãi 320%" mà không có baseline nghĩa là vô nghĩa |
| 9 | Walk-forward là gì? | Chia dữ liệu thành các cửa sổ học-trước-thi-sau, lặp lại trượt dần |
| 10 | Vì sao báo cáo cả 3 mô hình? | Chọn mô hình đẹp nhất là cherry-picking, sẽ bị hỏi ngay |

### 11.2 Nếu bạn muốn đi sâu hơn, đọc theo thứ tự này

| Thứ tự | File | Dành cho |
|---|---|---|
| 1 | `docs/SO_DO_MINH_HOA.md` | 18 sơ đồ vẽ tay, mỗi sơ đồ có phần "đọc bằng lời đời thường" |
| 2 | `docs/CODE_EXPLAINED_FOR_BEGINNER.md` | Giải thích code từng dòng (giả định bạn biết Python) |
| 3 | `docs/lakehouse.md` | Chi tiết 3 tầng, cách đọc/ghi, hiệu năng |
| 4 | `docs/NGHIEN_CUU_DA_MA_WALK_FORWARD.md` | Nghiên cứu đa mã chi tiết |
| 5 | `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md` | Tài liệu tổng thể lớn nhất (3.561 dòng) |
| 6 | `docs/BAN_DO_MA_NGUON.md` | File nào làm gì |
| 7 | `docs/architecture.md` | Kiến trúc chi tiết |
| 8 | `docs/tech_stack_matrix.md` | Công nghệ nào nằm ở file nào |
| 9 | `LOCAL_DEV.md` | Cách chạy hệ thống trên máy |

### 11.3 Chạy thử để tự thấy

```powershell
# 1. Bật hạ tầng (cần WSL2 + Docker)
wsl -d Ubuntu-24.04 -u root -- systemctl start docker
wsl -d Ubuntu-24.04 -u root -e bash -c "cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose up -d mysql minio"

# 2. Chạy backend + frontend
.\start-all.bat

# 3. Mở http://127.0.0.1:5173
```

Trang nên xem trước: **Tổng quan** (Dashboard) → **Dự báo** → **Backtest** → **AI Agent**.

---

## GHI CHÚ CUỐI

Nếu bạn chỉ nhớ 4 điều từ file này, hãy nhớ:

1. **Dữ liệu đi một đường**: Internet → Bronze (giữ nguyên) → Silver (làm sạch) → Gold (tính chỉ báo) → mô hình → web. Không có đường cắt ngang.
2. **Mọi số đều truy vết được**, và hệ thống nói rõ khi không có dữ liệu thay vì bịa ra số.
3. **Đo lường trung thực quan trọng hơn kết quả đẹp**: chia theo thời gian, lệnh khớp bar kế tiếp, so với mua và giữ, và báo cả kết quả xấu.
4. **Kết quả thật của đồ án**: 50,71% đúng hướng, chiến lược thua mua và giữ ở 91% số mã, nhưng giảm mức lỗ tệ nhất từ −11,87% xuống −2,00%.
