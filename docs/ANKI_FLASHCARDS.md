# BO BÀN HỌC ANKI (FLASHCARDS) CHO DỰ ÁN STOCK LAKEHOUSE

> **Tài liệu này dành cho bạn — người mới.**
> Mỗi khái niệm kỹ thuật đều được giải thích bằng **đời thường trước**, rồi mới nêu **tên thuật ngữ** sau.

---

# PHẦN 0 — ĐỌC TÀI LIỆU NÀY THẾ NÀO

## 0.1. Bộ thẻ này là gì

Bộ 12 file `.apkg` trong thư mục `anki/build/` là **12 bộ thẻ nhớ ôn (flashcard)**, mỗi bộ là một **lĩnh vực chuyên môn** của đồ án. Tổng cộng **285 thẻ**.

Bạn cài vào Anki (miễn phí, chạy offline), import file `.apkg`, rồi học như bình thường. Mỗi thẻ có mặt trước là **câu hỏi**, mặt sau là **câu trả lời kèm đường dẫn file thật trong dự án**.

## 0.2. Quy tắc của bộ thẻ

| Quy tắc | Vì sao |
|---|---|
| Mỗi thẻ trả lời **một câu hỏi cụ thể** | Thẻ chung chung thì không học được gì |
| Câu trả lời nói **tại sao**, không chỉ **cái gì** | Điểm mà thầy/cô hỏi luôn là "tại sao vậy" |
| Mỗi thẻ có trường `Code` trỏ tới **file thật** | Để bạn tự kiểm chứng, không phải tin lời thẻ |
| Thẻ nào cũng có **mốc thời gian** khi có con số | Số liệu không có ngày đo là số liệu không đáng tin |
| Kết quả **xấu cũng được ghi thẳng** | Giấu điểm yếu là rủi ro bảo vệ lớn nhất |

## 0.3. Bảng tra thuật ngữ

### 0.3.1. Thuật ngữ về ANKI

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Gói thẻ** | `.apkg` | File ZIP chứa cơ sở dữ liệu SQLite mà Anki đọc | `anki/build/*.apkg` |
| **Mẫu thẻ** | Note Model | Bố cục các ô: Term / Answer / Code / Tags | `anki/deck_builder.py:MODEL` |
| **Mặt trước / mặt sau** | Front / Back | Câu hỏi / câu trả lời | `anki/deck_builder.py:TEMPLATE` |
| **Mã định danh thẻ** | GUID | Con số định danh duy nhất, giúp Anki **cập nhật** thay vì tạo bản trùng | `anki/deck_builder.py:note_guid` |
| **Mã định danh bộ** | Deck ID | Con số định danh một bộ thẻ | `anki/deck_builder.py:DECKS` |
| **Nhãn** | Tag | Từ khoá để lọc và gom thẻ | Trường `Tags` |

### 0.3.2. Thuật ngữ về DỰ ÁN

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Kho dữ liệu 3 tầng** | Medallion Architecture | Chia dữ liệu thành 3 mức: gốc → đã rửa → đã phân tích | `backend/app/lakehouse/` |
| **Bảng dự báo** | Prediction Ledger | Bảng lưu mọi dự báo kèm kết quả thực tế để đối chiếu | `backend/app/database/models/prediction.py` |
| **Nhìn thấy tương lai** | Look-ahead bias | Dùng thông tin ngày mai để quyết định hôm nay | `backend/app/backtesting/walk_forward.py` |
| **Số trung vị** | Median | Giá trị ở giữa khi xếp hàng — ít bị vài số lỗi kéo lệch | `prediction_repository.py:median_error_pct` |
| **Tỉ lệ sai số có trọng số** | WAPE | Sai số chia cho tổng tiền, để so sánh được giữa các mã | `prediction_repository.py:accuracy_summary` |

## 0.4. Danh sách 12 bộ thẻ

| # | File `.apkg` | Lĩnh vực | Số thẻ |
|---|---|---|---|
| 01 | `01-lakehouse-architecture.apkg` | Kiến trúc Lakehouse Medallion | 25 |
| 02 | `02-data-quality.apkg` | Chất lượng dữ liệu & Integrity | 23 |
| 03 | `03-forecasting-models.apkg` | Dự báo & mô hình ML/DL | 25 |
| 04 | `04-backtesting.apkg` | Backtest & Walk-forward validation | 20 |
| 05 | `05-technical-analysis.apkg` | Phân tích kỹ thuật & chỉ báo | 21 |
| 06 | `06-ai-agent.apkg` | AI Agent & Tool calling | 19 |
| 07 | `07-trading-calendar.apkg` | Lịch giao dịch & quản lý phiên | 19 |
| 08 | `08-operations.apkg` | Vận hành & hạ tầng | 21 |
| 09 | `09-data-sources-api.apkg` | Nguồn dữ liệu & API layer | 17 |
| 10 | `10-database-ledger.apkg` | Database, Alembic & Prediction ledger | 28 |
| 11 | `11-frontend.apkg` | Frontend, UI/UX & i18n | 27 |
| 12 | `12-fundamentals-macro.apkg` | Fundamental, Macro & Order book | 40 |
| | | **TỔNG** | **285** |

---

# PHẦN 1 — BỘ THẺ NÀY ĐƯỢC TẠO RA NHƯ THẾ NÀO

## 1.1. Hiểu đơn giản

Một file `.apkg` không phải là file văn bản — nó là một **file ZIP** bên trong chứa một **cơ sở dữ liệu SQLite** theo đúng khuôn mẫu của Anki. Nếu tự viết bằng tay, rất dễ sai một chi tiết nhỏ và Anki sẽ từ chối mở file.

Vì vậy dự án chia việc thành ba phần:

```
    ┌──────────────────────┐
    │ anki/content/*.json  │  Nội dung thẻ (viết tay, dễ sửa, dễ review)
    └──────────┬───────────┘
               │  đọc
               ▼
    ┌──────────────────────┐
    │ anki/deck_builder.py │  Mẫu thẻ + CSS + quy tắc định danh
    └──────────┬───────────┘
               │  đóng gói
               ▼
    ┌──────────────────────┐
    │ anki/build/*.apkg    │  12 file Anki sẵn sàng import
    └──────────────────────┘
```

Bạn muốn thêm một thẻ? Sửa file `.json`, chạy lại lệnh build, xong.

## 1.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì |
|---|---|---|
| **Khung mẫu thẻ** | Note Model | Bố cục các ô dùng chung cho mọi thẻ |
| **Mã định danh ổn định** | Stable GUID | Con số giống nhau mọi lần build, để Anki cập nhật thẻ cũ |
| **Tách bộ** | Code splitting | Tách thư viện dùng chung ra khỏi bundle chính |
| **Bao gói** | Package | Gói ZIP gồm `collection.anki2` + media |

## 1.3. Chi tiết kỹ thuật

### 1.3.1. Mẫu thẻ dùng chung

```python
MODEL_ID = 1607392319

MODEL = genanki.Model(
    MODEL_ID,
    "Stock Lakehouse - Concept (Term/Answer/Code)",
    fields=[
        {"name": "Term"},
        {"name": "Answer"},
        {"name": "Code"},
        {"name": "Tags"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": '<div class=front-term>{{Term}}</div>',
            "afmt": TEMPLATE,
        }
    ],
    css=CSS,
)
```

Nguồn: `anki/deck_builder.py`

### 1.3.2. Vì sao Mã định danh phải là hằng số

`note_guid()` tính GUID từ cặp `(slug của bộ, câu hỏi)`:

```python
def note_guid(deck_slug: str, term: str) -> int:
    digest = hashlib.sha256(f"{deck_slug}::{term}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
```

Nguồn: `anki/deck_builder.py:note_guid`

Nếu GUID đổi mỗi lần build, Anki sẽ coi mỗi lần build là **một bộ thẻ mới** — bạn mất toàn bộ lịch sử ôn tập. Vì vậy `MODEL_ID` và `deck_id` phải là **hằng số nằm trong source**, không được sinh ngẫu nhiên.

### 1.3.3. Cách chạy

```powershell
# Sửa file JSON hỏng (dấu nháy kép chưa escape)
.\backend\.venv\Scripts\python.exe anki\repair_json.py

# Đóng gói toàn bộ 12 bộ
.\backend\.venv\Scripts\python.exe anki\build_all.py

# Kiểm tra 12 file .apkg mở được và đủ số thẻ
.\backend\.venv\Scripts\python.exe anki\verify_build.py
```

**Đo ngày 19/11/2026:**

```
Built 12 decks, 285 cards total
Output: D:\School\kltn\stock-lakehouse-ai\anki\build

Verified 12 packages, 285 notes
```

### 1.3.4. Một sự cố đã gặp và cách sửa

**Triệu chứng:** build báo `TypeError: Deck .deck_id must be an integer, not 1740110001.`

**Vì sao xảy ra:** `deck_id` được viết dạng chuỗi `"1740110001"` trong khai báo, nhưng `genanki` yêu cầu kiểu `int`.

**Fix:** đổi sang số nguyên không dấu nháy trong `DECKS`.

**Bằng chứng:** `12/12 deck FAIL` → `Built 12 decks, 285 cards total`.

---

**Triệu chứng:** build báo `KeyError: 0` tại `note.py` dòng `self.fields[self.model.sort_field_index]`.

**Vì sao xảy ra:** `genanki.Note` **index theo vị trí** để tính sort field, nhưng `fields` được truyền vào dạng dict. Dict không index được bằng số nguyên.

**Fix:** truyền `fields` dưới dạng **list** đúng thứ tự model khai báo, và đặt `sort_field=term` tường minh.

**Bằng chứng:** `12/12 deck FAIL` → `Built 12 decks, 285 cards total`.

---

# PHẦN 2 — CÁCH THẺ PHẢN ÁNH ĐÚNG HỆ THỐNG

## 2.1. Hiểu đơn giản

Bộ thẻ này **không phải** là một bản tóm tắt kiến thức chung về tài chính. Nó là bản ghi lại **những gì hệ thống này thực sự làm**, kèm đường dẫn tới file thật.

Ví dụ, thay vì ghi "RSI là gì", bộ thẻ ghi:

> **Term:** Vì sao RSI dùng công thức Wilder chứ không dùng trung bình đơn giản?
> **Code:** `backend/app/indicators/service.py`

Câu hỏi đó chỉ có ý nghĩa nếu bạn đọc được code. Vì vậy mỗi thẻ đều có trường `Code`.

Điểm thứ hai quan trọng không kém: bộ thẻ **không giấu điểm yếu**. Có những thẻ ghi thẳng rằng một chỉ báo chưa được tối ưu, rằng một nguồn dữ liệu là HTML scrape, rằng frontend **chưa có test tự động**.

## 2.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì |
|---|---|---|
| **Có thể tự kiểm chứng** | Verifiable | Mọi khẳng định đều dẫn tới file thật trong repo |
| **Bằng chứng trước / sau** | Before / After evidence | Khi ghi một lỗi đã sửa, phải kèm số đo trước và sau |
| **Nói thẳng giới hạn** | State the limits | Nêu ra phần chưa làm, thay vì để thầy/cô hỏi mới phát hiện |

## 2.3. Chi tiết kỹ thuật

### 2.3.1. Ví dụ thẻ nói thẳng điểm yếu

Một số thẻ cố ý **không** đẹp:

- Thẻ *"Vì sao dự án không có test frontend?"* — nêu rõ đây là khoảng trống, chỉ ra các hàm thuần tuần dễ test nhất (`isUsableNumber`, `tradingDay`, `toFinite`) lại chưa được test.
- Thẻ *"Những điều gì CHƯA có trong dự án về fundamental và macro?"* — liệt kê cả 5 khoảng trống, gồm việc **chưa xử lý độ trễ công bố báo cáo tài chính** (publication lag), vốn là nguồn rò rỉ thời gian nếu đưa vào mô hình.
- Thẻ *"Vì sao `macro_normalized` nhân với 1000?"* — chỉ ra file có **hai hệ số khác nhau** (10.000 ở `fx_adjusted_close` và 1.000 ở `macro_normalized`) mà không có comment giải thích, và nói rõ đây là điểm cần kiểm chứng.

### 2.3.2. Ví dụ thẻ có bằng chứng trước / sau

Thẻ *"Vì sao dùng `GREATEST` mà không dùng `LEAST` khi tính tỉ lệ giữa forecast và reference?"* trích nguyên văn từ docstring trong `prediction_repository.py`:

> *"On 15/11/2026 the median was 1,15% - and one symbol (`PARA`) accounted for 99,993% of the total error mass on its own"*

Thẻ *"Vì sao báo cáo độ chính xác dùng median thay vì mean?"* có đủ số đo:

| Số đo (Đo ngày 15/11/2026) | Giá trị |
|---|---|
| Số dòng đã xác minh | 44.676 |
| Mean sai số tuyệt đối | 26,385% |
| Median sai số tuyệt đối | 1,15% |
| Tỷ trọng sai số của riêng mã `PARA` | 99,993% |

---

# PHẦN 3 — CÁCH MỞ RỘNG BỘ THẺ

## 3.1. Hiểu đơn giản

Bạn học xong 285 thẻ này rồi muốn thêm thẻ mới. Bạn **không cần** đụng vào code Python — chỉ cần thêm vào file `.json`.

Quy trình: mở file `.json` của bộ cần thêm → chép thêm một mẫu thẻ cũ → đổi nội dung → chạy `build_all.py`.

## 3.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì |
|---|---|---|
| **Slug** | Slug | Tên ngắn của bộ thẻ, ví dụ `10-database-ledger` |
| **Thẻ trùng nhau** | Duplicate term | Hai thẻ cùng một câu hỏi trong một bộ — builder **cố ý báo lỗi** |
| **Bộ mới** | New deck | Thêm slug mới vào `DECKS` trong `deck_builder.py` |

## 3.3. Chi tiết kỹ thuật

### 3.3.1. Cấu trúc một file nội dung

```json
{
  "deck": "10-database-ledger",
  "notes": [
    {
      "term": "Câu hỏi ở mặt trước",
      "answer": "Câu trả lời ở mặt sau, viết bằng Markdown rút gọn.",
      "code": "backend/app/database/session.py:get_db",
      "tags": "database transaction fastapi"
    }
  ]
}
```

### 3.3.2. Markdown rút gọn được renderer hỗ trợ

| Cú pháp | Kết quả |
|---|---|
| `**đậm**` | chữ đậm |
| `` `mã` `` | mã nguồn nổi |
| `- mục` | danh sách gạch đầu dòng |
| `1. mục` | danh sách đánh số |
| `> trích dẫn` | khối trích dẫn (dùng cho phần "tại sao") |
| `---` | đường kẻ ngang |
| dòng trống | ngắt đoạn |

**Không** hỗ trợ bảng markdown — một bảng trên điện thoại wrap rất xấu, và các sự thật trong dự án này viết bằng danh sách ngắn sẽ rõ hơn.

### 3.3.3. Thêm một bộ thẻ mới

Ba chỗ cần sửa:

**1.** Thêm file `anki/content/d13_<slug>.json`.

**2.** Thêm slug vào `DECKS` trong `anki/deck_builder.py`:

```python
    "13-my-new-deck": {
        "title": "Stock Lakehouse :: 13 - Ten bo the moi",
        "deck_id": 1740110013,
    },
```

**3.** Chạy lại `build_all.py` và `verify_build.py`.

> `deck_id` phải là **số nguyên** và phải **khác** các id đang có.

### 3.3.4. Quy tắc cho nội dung một thẻ

- Câu hỏi nên **hỏi về một cơ chế cụ thể**, không hỏi "tổng quan về X".
- Câu trả lời dài 150-400 từ là đủ. Câu trả lời quá dài thì mỗi lần ôn chỉ đọc một phần.
- Trường `Code` phải trỏ tới **file có thật**. Đường dẫn sai thì thẻ đó vô giá trị.
- Nếu có con số, ghi **ngày đo** trong chính câu trả lời.
- Không dùng emoji trong nội dung thẻ.

---

# PHẦN 4 — GIỚI HẠN ĐÃ BIẾT

## 4.1. Hiểu đơn giản

Bộ thẻ này **không phải** là toàn bộ kiến thức về đồ án. Nó là phần **dễ quên nhất**: các quy ước kỹ thuật, các con số đo được, các lỗi đã sửa và nguyên nhân gốc.

Những thứ nó **không** thay thế được: tài liệu `docs/`, trực tiếp đọc code, và việc hiểu **tại sao** hệ thống được thiết kế như hiện tại.

## 4.2. Chi tiết kỹ thuật

| Hạn chế | Mô tả |
|---|---|
| **Số lượng** | 285 thẻ trên tổng số hàng nghìn khái niệm trong dự án |
| **Không có hình minh hoạ** | Thẻ là văn bản thuần, không có sơ đồ ASCII như tài liệu `docs/` |
| **Không có câu hỏi trắc nghiệm** | Tất cả là hỏi-đáp tự luận |
| **Nội dung có thể lỗi thời** | Số đo trong thẻ là ảnh chụp tại ngày ghi; cần cập nhật khi code đổi |
| **Chỉ tiếng Việt** | Nội dung thẻ viết bằng tiếng Việt, giữ nguyên tên tiếng Anh của hàm/biến |

---

# PHỤ LỤC A — BẢN ĐỒ MÃ NGUỒN CỦA HỆ THỐNG ANKI

```
anki/
├── build_all.py         Đóng gói 12 bộ thẻ -> anki/build/
├── deck_builder.py      Mẫu thẻ, CSS, DECKS, note_guid(), render()
├── repair_json.py       Sửa dấu nháy kép chưa escape trong file .json
├── verify_build.py      Mở lại .apkg, đối chiếu số thẻ và tên bộ
├── content/             Nội dung 12 bộ (d01..d12), mỗi bộ 17-40 thẻ
└── build/               12 file .apkg sẵn sàng import vào Anki
```

# PHỤ LỤC B — MA TRẬN TRUY VẾT YÊU CẦU

| Yêu cầu | Thực hiện ở đâu | Bằng chứng |
|---|---|---|
| Tạo bộ thẻ học cho từng lĩnh vực chuyên môn | `anki/content/d01..d12` | 12 file JSON, 285 thẻ |
| Đóng gói thành file Anki | `anki/build_all.py` | 12 file `.apkg` trong `anki/build/` |
| Bảo đảm file mở được, đủ số thẻ | `anki/verify_build.py` | `Verified 12 packages, 285 notes` |
| Mỗi thẻ có đường dẫn file thật | Trường `Code` | Kiểm tra tự động trong `verify_build.py` |
| Không mất lịch sử ôn tập khi build lại | `note_guid()` + `MODEL_ID` hằng số | GUID tất định theo `(bộ, câu hỏi)` |
| Sửa file JSON hỏng | `anki/repair_json.py` | `repair_json.py` chạy qua cho cả 12 file |
