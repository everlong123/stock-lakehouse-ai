# NGHIÊN CỨU ĐA MÃ: WALK-FORWARD + ĐƯỜNG CƠ SỞ MUA & GIỮ

> **Cập nhật 19/11/2026:** kết quả mới có **102 mã / 14 nhóm thị trường / 3.724 cửa sổ cặp**, sau khi sửa phân nhóm. Xem mục 8.7 của [tài liệu chính](HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md) và [báo cáo sửa lỗi](audits/KET_QUA_SUA_LOI_2026-11-19.md). Phần 101 mã/13 sàn bên dưới là snapshot 11/11, giữ để tra cứu lịch sử, không dùng làm kết quả hiện tại.

> **Tài liệu này dành cho bạn — người mới.**
> Mỗi khái niệm kỹ thuật đều được giải thích bằng **đời thường trước**, rồi mới nêu **tên thuật ngữ** sau.

---

# PHẦN 0 — ĐỌC TÀI LIỆU NÀY THẾ NÀO

## 0.1. Quy tắc của tài liệu (bảng 3 phần)

| Tầng | Tên mục | Nội dung | Bạn cần đọc tới đâu? |
|---|---|---|---|
| ① | **Hiểu đơn giản** | Giải thích đời thường, ví dụ như kể chuyện | Chỉ cần hiểu hệ thống thì dừng ở đây |
| ② | **Thuật ngữ** | Bảng tra cứu | Khi gặp từ lạ |
| ③ | **Chi tiết kỹ thuật** | Code, số đo, đường dẫn file | Khi thầy hỏi sâu |

## 0.2. Bảng tra thuật ngữ

### 0.2.1. Thuật ngữ về ĐÁNH GIÁ CHIẾN LƯỢC

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Đo trên đoạn chưa từng thấy** | **Out-of-sample** | Đo kết quả trên dữ liệu mà mô hình chưa từng được huấn luyện | `backtesting/walk_forward.py` |
| **Cửa sổ trượt** | **Sliding window** | Hai đoạn liên tiếp: đoạn học rồi đoạn kiểm tra, cả hai cùng trượt về phía trước | `backtesting/walk_forward.py` |
| **Đường cơ sở** | **Baseline / Buy-and-Hold** | Mua từ đầu kỳ và giữ đến cuối kỳ — cách đơn giản nhất | `backtesting/benchmark.py` |
| **Chênh lệch so với đường cơ sở** | **Excess return** | Lợi nhuận của chiến lược trừ lợi nhuận của đường cơ sở trên cùng kỳ | `backtesting/walk_forward.py` |
| **So sánh cặp** | **Paired comparison** | So sánh hai bên trên đúng những phiên giống nhau, rồi lấy hiệu | `backtesting/walk_forward.py` |
| **Giá trị trung vị** | **Median** | Giá trị ở giữa khi xếp hết các số lại — không bị số lớn kéo lệch | `scripts/run_multi_symbol_walkforward.py` |
| **Số phần trăm mã có lãi** | **Hit rate / % profitable** | Trong 100 mã, bao nhiêu mã sinh lời ngoài mẫu | `scripts/run_multi_symbol_walkforward.py` |
| **Lợi nhuận trên mỗi đơn vị rủi ro** | **Sharpe Ratio** | Đổi 1 đơn vị rủi ro thì được bao nhiêu lợi nhuận | `backtesting/metrics.py` |
| **Mức lỗ tệ nhất** | **Maximum Drawdown** | Từ đỉnh cao nhất xuống đáy thấp nhất, mức lỗ lớn nhất | `backtesting/metrics.py` |
| **Quá khớp tham số** | **Overfitting** | Mô hình khớp đoạn học quá đẹp, nhưng hỏng trên đoạn chưa thấy | `backtesting/walk_forward.py` |
| **Số mã trong mẫu** | **Universe size** | Tổng số mã có dữ liệu thật trong lakehouse | `app/lakehouse/bronze.py` |

### 0.2.2. Thuật ngữ về HẠ TẦNG ĐO

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Chạy sẵn ngoài, lưu ra file** | **Offline batch job** | Tính một lần rồi ghi kết quả ra file, không tính lại mỗi lần mở web | `scripts/run_multi_symbol_walkforward.py` |
| **Đọc từ file báo cáo** | **Report endpoint** | API chỉ đọc file đã sinh, không chạy lại phép tính nặng | `api/v1/endpoints/backtesting.py` |
| **Lấy mã theo tầng** | **Stratified sampling** | Mỗi sàn lấy một số mã bằng nhau, thay vì để sàn đông nuốt hết mẫu | `scripts/run_multi_symbol_walkforward.py` |

## 0.3. Tóm tắt câu hỏi lớn

| # | Câu hỏi | Trả lời ngắn | Xem ở chương |
|---|---|---|---|
| 1 | **Vì sao một mã cổ phiếu không đủ?** | Một mã trong một thập kỷ đo phần lớn "cổ phiếu đó tăng", không phải "chiến lược đúng". | Phần 1 |
| 2 | **Đường cơ sở mua & giữ là gì?** | Mua đầu kỳ giữ cuối kỳ, cùng phí, cùng cách khớp lệnh. | Phần 2 |
| 3 | **Kết quả đa mã ra sao?** | Cả 2 chiến lược **không** vượt được đường cơ sở trên phần lớn mã. | Phần 4 |
| 4 | **Phân bố theo sàn thì sao?** | Kết luận giống nhau trên 13 sàn: không sàn nào chiến lược thắng rõ. | Phần 5 |

---

# PHẦN 1 — HIỂU ĐƠN GIẢN: VÌ SAO MỘT MÃ CỔ PHIẾU KHÔNG ĐỦ

## 1.1. Hiểu đơn giản

**Bối cảnh vấn đề:**

Bài luận văn trước đây chỉ chạy chiến lược trên **một mã**: AAPL. Kết quả rất đẹp — lợi nhuận +308% trong 10 năm.

**Hậu quả nếu không xử lý:**

Có một câu hỏi mà bất kỳ thầy tài chính nào cũng sẽ hỏi: *"AAPL tăng 300%, ai cũng mua AAPL thắng. Chiến lược của em khác gì so với cứ nắm giữ?"*

Câu hỏi đó là **chí mạng**, vì câu trả lời là: trong giai đoạn 2016–2026, AAPL tăng rất mạnh. Nếu ta thay chiến lược bằng hành động "mua AAPL và không bao giờ bán", ta gần như chắc chắn cũng kiếm được con số tương tự. Nhưng chỉ vì AAPL tăng — không phải vì chiến lược có khả năng.

**Cách hệ thống xử lý:**

Hệ thống giờ chạy **cùng một cơ chế walk-forward** trên **101 mã** thuộc **13 sàn** khác nhau, rồi báo cáo **phân phối** kết quả thay vì một con số đơn. Và quan trọng nhất: mỗi cửa sổ kiểm tra được đo **cả hai** — chiến lược **và** đường cơ sở mua & giữ — trên **đúng những phiên đó**.

**Phép so sánh đời thường:**

> Giống như so sánh tài xế xe đua với việc **đi bộ cùng đường**. Nếu đường bộ lên dốc thì cả hai đều tới đích, và ta chưa biết ai giỏi hơn. Chỉ khi đường bằng phẳng thì mới thấy ai thực sự lái giỏi.

Đó là lý do đường cơ sở phải được đo **trên cùng các phiên**, **cùng bộ chi phí**, **cùng cách khớp lệnh**. Không thì so sánh trở nên vô nghĩa.

## 1.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Universe** | Toàn bộ tập mã có dữ liệu thật trong lakehouse. Đo ngày 11/11/2026: **1.002 mã**. |
| **Stratified sampling** | Cách chọn mẫu: mỗi sàn lấy một số mã **bằng nhau**, để sàn đông không nuốt hết mẫu. |
| **Distribution** | Cách báo cáo **phân phối** kết quả (trung vị, tỉ lệ thắng) thay vì một số trung bình duy nhất. |
| **Baseline** | Đường cơ sở để so sánh. Ở đây là mua & giữ. |

## 1.3. Chi tiết kỹ thuật

### ① Hình vẽ

```
┌──────────────────────────────────────────────────────────────┐
│                    TRƯỚC: MỘT MÃ                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────┐                                               │
│   │   AAPL   │──▶ [MA Crossover] ──▶ +308%  + đẹp            │
│   └──────────┘                                               │
│                                                              │
│   Không ai hỏi: "nếu không có chiến lược thì sao?"           │
│   Câu hỏi đó chưa từng được trả lời.                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                   SAU: 101 MÃ, 13 SÀN                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────┐                                               │
│   │ 101 mã   │──▶ [Walk-forward] ──┬──▶ [Chiến lược]         │
│   │ 13 sàn   │                     │                         │
│   └──────────┘                     └──▶ [Mua & giữ]          │
│                                              │               │
│                                              ▼               │
│                                    ┌─────────────────┐       │
│                                    │ So sánh CẶP     │       │
│                                    │ trên cùng phiên │       │
│                                    └─────────────────┘       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### ② Đọc hình vẽ bằng lời đời thường

Hình trên cho thấy sự thay đổi. Trước đây, một mã cổ phiếu đi thẳng vào máy chạy chiến lược và ra một con số đẹp — không có gì để so sánh, nên không ai biết con số đó là công trình của chiến lược hay của thị trường.

Sau đó, 101 mã từ 13 sàn cùng đi qua máy. Mỗi mã được tách thành hai nhánh: một nhánh chạy chiến lược, một nhánh chạy hành động đơn giản "mua và giữ". Hai nhánh đó được so với nhau **trên cùng những phiên giống nhau**, nên kết quả cuối cùng trả lời được câu hỏi: chiến lược có tạo thêm giá trị hay không.

### ③ Chi tiết kỹ thuật

Mẫu được chọn bằng `select_symbols()` trong `backend/scripts/run_multi_symbol_walkforward.py`:

```python
def select_symbols(limit: int = 0, per_exchange: int = 0) -> list[str]:
    """Pick the symbols to test.

    Two modes:

    * ``per_exchange > 0`` - take up to N symbols from EVERY exchange.
      This is the mode used for the headline report, because a sample
      that is 70% US names would make the "by exchange" breakdown
      meaningless for the smaller markets.
    * ``limit > 0`` - take an evenly spread sample of the whole universe.
      Used for quick runs.
    """
```

**Đo ngày 11/11/2026 — phân bố sàn của toàn bộ universe (1.002 mã):**

| Sàn | Số mã trong universe |
|---|---|
| NYSE/NASDAQ | 697 |
| HOSE (Việt Nam) | 81 |
| TSE (Nhật) | 39 |
| Euronext | 31 |
| XETRA (Đức) | 29 |
| HKEX | 20 |
| KRX (Hàn Quốc) | 20 |
| TWSE (Đài Loan) | 20 |
| Nasdaq Nordic | 19 |
| TSX (Canada) | 17 |
| LSE (Anh) | 15 |
| SIX (Thụy Sĩ) | 5 |
| BME (Tây Ban Nha) | 4 |
| **Tổng** | **1.002** |

> Lưu ý: 697/1.002 mã là NYSE/NASDAQ (69,6%). Nếu lấy mẫu ngẫu nhiên, phần "phân phối theo sàn" sẽ gần như chỉ nói về thị trường Mỹ. Đó là lý do mẫu dùng `--per-exchange 8`.

---

# PHẦN 2 — HIỂU ĐƠN GIẢN: ĐƯỜNG CƠ SỞ MUA & GIỮ

## 2.1. Hiểu đơn giản

**Bối cảnh vấn đề:**

Một con số lợi nhuận mà không có gì để so sánh thì vô nghĩa. "+15% là tốt" — so với cái gì?

**Hậu quả nếu không xử lý:**

Một trang web backtest chỉ hiện đường lợi nhuận của chiến lược. Người đọc tự nhận định "con số này lớn, chắc là chiến lược giỏi". Đó là một suy luận sai, vì phần lớn lợi nhuận của một cổ phiếu trong một thập kỷ đến từ việc cổ phiếu đó tăng, không phải từ quy tắc mua bán.

**Cách hệ thống xử lý:**

Hệ thống dựng **một hành vi đối chứng**: mua từ phiên đầu tiên, giữ tới phiên cuối, không bao giờ bán. Nó được mô phỏng trên **đúng những phiên** mà chiến lược được đo, với **cùng mức phí giao dịch** và **cùng độ trượt giá**, và **cùng quy ước khớp lệnh** (mua ở giá mở cửa của phiên kế tiếp).

**Phép so sánh đời thường:**

> Nếu người chơi biểu diễn đi bộ qua đoạn đường mà xe đua đang chạy 300 km/h, cả hai đều "về đích". Muốn biết ai giỏi, phải có người chơi thứ hai đi **cùng bộ đồ** — cùng giày, cùng đường, cùng quãng đường. Đó chính là đường cơ sở.

## 2.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Buy-and-hold** | Mua đầu kỳ, giữ đến cuối kỳ, không bán. |
| **Fair comparison** | So sánh công bằng: cùng công cụ, cùng phí, cùng kỳ. |
| **Next-bar execution** | Tín hiệu hôm nay → khớp lệnh ở giá mở cửa **ngày mai**. Dùng chung cho cả hai bên. |
| **Forced close** | Cuối kỳ, mọi vị thế đang mở đều bị đóng lại, tính cả phí. |
| **Excess return** | Lợi nhuận chiến lược − lợi nhuận đường cơ sở, trên cùng một cửa sổ. |
| **Paired difference** | Chênh lệch tính **theo từng cửa sổ**, rồi mới lấy trung bình. |

## 2.3. Chi tiết kỹ thuật

### ① Hình vẽ

```
┌───────────────────────────────────────────────────────────────┐
│              HAI BÊN ĐO TRÊN CÙNG MỘT PHIÊN                   │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│   Phiên:  ... │ P1 │ P2 │ P3 │ P4 │ P5 │ P6 │ P7 │ ...        │
│               │    │    │    │    │    │    │    │            │
│   Chiến lược:  S  │ B  │ B  │ H  │ H  │ S  │ H  │ ...         │
│               │    │    │    │    │    │    │    │            │
│   Mua & giữ:  B  │ H  │ H  │ H  │ H  │ H  │ H  │ ...          │
│               │    │    │    │    │    │    │    │            │
│   Chênh lệch:   +  │ -  │ -  │ +  │ +  │ -  │ +  │ ...        │
│                                                               │
│   MỗI CỬA SỔ CHO 1 CHÊNH LỆCH. TỔNG SỐ CHÊNH LỆCH MỚI LÀ      │
│   CON SỐ "CHIẾN LƯỢC CÓ THẮNG ĐƯỜNG CƠ SỞ KHÔNG".             │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### ② Đọc hình vẽ bằng lời đời thường

Hình vẽ là hai dòng ghi chép "mua hay bán" trên cùng một lịch. Dòng trên là chiến lược: có lúc vào, có lúc ra. Dòng dưới là hành động đơn giản: mua một lần rồi giữ.

Dòng cuối cùng là phép trừ. Mỗi cửa sổ cho một con số: ở cửa sổ này chiến lược thắng đường cơ sở bao nhiêu, thua bao nhiêu. Khi gom hết các chênh lệch đó lại, ta biết trung bình chiến lược nhanh hơn hay chậm hơn đường cơ sở — và thắng được bao nhiêu phần trăm số cửa sổ.

Đây gọi là **so sánh cặp** (paired comparison): hai bên luôn được đo trên cùng những phiên, nên phần chênh lệch không bị nhiễu bởi việc thị trường đi lên hay xuống giữa hai kỳ khác nhau.

### ③ Chi tiết kỹ thuật

Đường cơ sở được dựng trong **một module duy nhất** để engine và script không thể lệch nhau:
`backend/app/backtesting/benchmark.py`.

```python
def buy_and_hold_signal(frame: pd.DataFrame) -> pd.Series:
    """Signal series that buys on the first bar and sells on the last.

    The signal is shifted by one bar by the caller, so the entry happens
    on the SECOND bar's open and the exit on the bar after the last
    signal. The forced close at the end of the series is handled by
    ``simulate``, which closes any open position on the final close.
    """
    signals = pd.Series(0.0, index=frame.index, dtype=float)
    if len(frame) == 0:
        return signals
    signals.iloc[0] = 1.0
    if len(frame) > 1:
        signals.iloc[-1] = -1.0
    return signals
```

Bốn điều kiện để phép so sánh là **công bằng**, mỗi điều kiện đều có test riêng trong `backend/tests/test_backtest_benchmark.py`:

| # | Điều kiện | Test chứng minh |
|---|---|---|
| 1 | Cùng tập phiên với chiến lược | `test_the_engine_returns_the_benchmark_on_the_same_bars` — so timestamp đầu & cuối |
| 2 | Cùng mức phí và độ trượt | `test_the_benchmark_pays_the_same_costs_as_the_strategy` |
| 3 | Cùng quy ước khớp lệnh bar kế tiếp | `run_buy_and_hold()` dùng `signals.shift(1)` giống `engine.py` |
| 4 | Buộc đóng vị thế cuối kỳ | `simulate()` đóng vị thế còn mở ở bar cuối (đã có sẵn) |

---

# PHẦN 3 — HIỂU ĐƠN GIẢN: CÁCH ĐO ĐA MÃ

## 3.1. Hiểu đơn giản

**Bối cảnh vấn đề:**

Chạy 101 mã là tốn CPU. Nếu trang web tính lúc mở, người dùng phải chờ hơn một phút — và trang đó sẽ không bao giờ được mở.

**Hậu quả nếu không xử lý:**

Một tính năng đẹp về lý thuyết nhưng chậm đến mức không ai dùng thì không phải là tính năng.

**Cách hệ thống xử lý:**

Phép đo chạy **ngoài (offline)** bằng một script, kết quả ghi ra file JSON. Trang web chỉ **đọc file** đó. Nếu file chưa có, trang hiện đúng lệnh cần chạy — chứ không hiện con số bịa.

**Phép so sánh đời thường:**

> Giống như báo cáo tổng kết năm được lập một lần vào cuối năm, in ra thành bản. Ai cần xem thì mở bản ra đọc — không ai ngồi tính lại từng tháng mỗi lần mở file.

## 3.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Offline batch** | Tính một lần, lưu lại, không tính lại. |
| **Report endpoint** | API chỉ đọc file JSON đã sinh. |
| **Missing report** | File chưa có → trả về lý do + lệnh cần chạy, không trả về số giả. |

## 3.3. Chi tiết kỹ thuật

### ① Hình vẽ

```
┌────────────────┐   script    ┌──────────────────────┐
│  1.002 mã      │───────────▶│ run_multi_symbol_     │
│  trong Bronze  │             │ walkforward.py       │
└────────────────┘             └──────────┬───────────┘
                                            │ ~2 phút
                                            ▼
                                 ┌──────────────────────┐
                                 │ backend/data/        │
                                 │ multi_symbol_        │
                                 │ walkforward.json     │
                                 └──────────┬───────────┘
                                            │ đọc file
                                            ▼
┌────────────────┐   HTTP      ┌──────────────────────┐
│  Trình duyệt    │◀───────────│ GET /backtests/      │
│  /backtesting  │             │ multi-symbol-report  │
│  (tab đa mã)   │             └──────────────────────┘
└────────────────┘
```

### ② Đọc hình vẽ bằng lời đời thường

Hình vẽ cho thấy hai con đường tách biệt. Con đường trên là việc **tính toán nặng**: đọc 1.002 mã từ kho dữ liệu, chạy hàng nghìn cửa sổ kiểm tra, mất khoảng hai phút, và kết quả nằm lại trong một file.

Con đường dưới là việc **phục vụ người xem**: trình duyệt gọi API, API đọc file đó ra và trả về. Người xem nhận kết quả trong tích tắc.

Nếu file chưa tồn tại, API **không** bịa số. Nó trả về lý do kèm lệnh để tạo file — và trang web hiển thị đúng lệnh đó.

### ③ Chi tiết kỹ thuật

Endpoint: `backend/app/api/v1/endpoints/backtesting.py`

```python
# The multi-symbol walk-forward report is produced OFFLINE by
# ``backend/scripts/run_multi_symbol_walkforward.py`` and written to
# ``backend/data/multi_symbol_walkforward.json``.
#
# WHY it is not computed on demand: the run replays ~100 symbols over
# ~37 windows each, which takes ~90 seconds of CPU. Serving that from a
# request handler would tie up a worker for a minute and return a
# timeout to the browser - the exact failure mode the thesis defence
# cannot afford. The report is therefore a FILE that the endpoint
# reads, and the endpoint says plainly when the file is missing instead
# of inventing numbers.
_REPORT_DIR = Path(__file__).resolve().parents[4] / "data"
_REPORT_FILES = {
    "ma_crossover": "multi_symbol_walkforward.json",
    "rsi_strategy": "multi_symbol_walkforward_rsi.json",
}
```

Lệnh chạy lại phép đo:

```powershell
cd backend
.venv\Scripts\python.exe scripts\run_multi_symbol_walkforward.py --per-exchange 8 --strategy ma_crossover
.venv\Scripts\python.exe scripts\run_multi_symbol_walkforward.py --per-exchange 8 --strategy rsi_strategy
```

---

# PHẦN 4 — CHI TIẾT KỸ THUẬT: KẾT QUẢ ĐO THẬT

## 4.1. Điều kiện chạy

| Tham số | Giá trị |
|---|---|
| Ngày đo | **11/11/2026** |
| Tập mã | 1.002 mã trong Bronze; lấy mẫu **8 mã/sàn × 13 sàn = 101 mã** |
| Cấu hình walk-forward | train 365 ngày / test 90 ngày / trượt 90 ngày |
| Vốn ban đầu | 10.000 |
| Phí giao dịch | 0,1% mỗi lệnh (cả mua lẫn bán) |
| Độ trượt giá | 0,05% mỗi lệnh |
| Nguồn dữ liệu | Tầng Gold/Silver/Bronze trong MinIO — dữ liệu thật từ Yahoo Finance và SSI iBoard |
| Mã không đo được | **0** (không có lỗi đọc) |

## 4.2. Kết quả chiến lược MA Crossover (20, 50)

```
symbols tested              : 101
universe size               : 1002

STRATEGY (out of sample)
  median avg test return     :   0.22%
  median avg test Sharpe     :  -0.025
  median max drawdown        :  -4.56%
  % symbols profitable       :  60.4%
  median return consistency  :  29.7%

BUY AND HOLD (same windows, same costs)
  median avg return          :   2.28%
  median Sharpe              :  0.456
  median max drawdown        : -11.87%
  % symbols profitable       :  91.1%

HEAD TO HEAD (paired, per window)
  paired windows             : 3687
  % windows beating B&H      :  37.5%
  mean paired excess return  :  -2.09%
  median paired excess return:  -2.45%
  % symbols beating B&H      :   8.9%
  median symbol excess return:  -1.90%
```

## 4.3. Kết quả chiến lược RSI (14, 30/70)

```
STRATEGY (out of sample)
  median avg test return     :   0.42%
  median avg test Sharpe     :  0.132
  median max drawdown        :  -2.00%
  % symbols profitable       :  70.3%
  median return consistency  :  13.5%

BUY AND HOLD — dùng chung, y hệt bảng trên (cùng tập phiên)

HEAD TO HEAD (paired, per window)
  paired windows             : 3687
  % windows beating B&H      :  47.7%
  mean paired excess return  :  -2.12%
  median paired excess return:  -0.73%
  % symbols beating B&H      :  13.9%
  median symbol excess return:  -2.00%
```

## 4.4. So sánh hai chiến lược cùng đường cơ sở

| Chỉ số | MA Crossover | RSI | Mua & giữ |
|---|---|---|---|
| Median lợi nhuận ngoài mẫu | 0,22% | 0,42% | **2,28%** |
| Median Sharpe | −0,025 | 0,132 | **0,456** |
| Median max drawdown | −4,56% | **−2,00%** | −11,87% |
| % mã có lãi | 60,4% | 70,3% | **91,1%** |
| % cửa sổ thắng baseline | 37,5% | 47,7% | — |
| % mã thắng baseline | 8,9% | 13,9% | — |

## 4.5. Cách đọc kết quả này

**Đây là kết quả xấu, và nó là kết quả có giá trị.**

1. **Cả hai chiến lược đều KHÔNG vượt được đường cơ sở mua & giữ.**
   Trung vị chênh lệch theo cửa sổ là **−2,45%** (MA) và **−0,73%** (RSI). Chỉ **8,9%** (MA) và **13,9%** (RSI) số mã thắng được đường cơ sở.

2. **Đường cơ sở thắng ở phần lớn mã** (91,1% mã có lãi so với 60,4% và 70,3%). Lý do không phải may rủi: giai đoạn 2008–2026 là giai đoạn thị trường tăng dài hạn trên hầu hết các sàn trong mẫu.

3. **Cái chiến lược mua được là giảm rủi ro, không phải tăng lợi nhuận.**
   Median max drawdown của MA là **−4,56%** và của RSI là **−2,00%**, trong khi mua & giữ là **−11,87%**. Đây là đánh đổi thật, không phải lỗi: chiến lược tránh được phần lớn biến động, và cái giá phải trả là bỏ lỡ phần lợi nhuận của xu hướng.

4. **Return consistency thấp** (29,7% MA; 13,5% RSI) nghĩa là phần lớn các cửa sổ kiểm tra không sinh lời. Điều này khớp với kết luận ở Phần 8 của tài liệu luận văn chính (chỉ trên AAPL).

> **Cách trả lời khi thầy hỏi "vậy chiến lược có ăn không?":**
>
> *"Câu trả lời của em là: **không**, và đó là điều em đã dựng ra để chứng minh. Em chạy walk-forward trên 101 mã thuộc 13 sàn, và trên mỗi cửa sổ kiểm tra em đo song song chiến lược với đường cơ sở mua & giữ trên đúng những phiên đó, cùng phí và cùng cách khớp lệnh. Kết quả: đường cơ sở thắng ở 91,1% số mã; chiến lược chỉ thắng ở 8,9% (MA) và 13,9% (RSI) số mã. Điểm em bảo vệ được là phần lợi nhuận mà chiến lược tạo ra **không đáng kể so với việc cứ nắm giữ** — nó đổi lại bằng việc giảm max drawdown từ −11,87% xuống −4,56% (MA) và −2,00% (RSI). Đây là dữ liệu thật, đo trên dữ liệu thật, và em báo cáo nguyên vẹn kể cả khi nó bất lợi cho hệ thống của em. Nếu em chỉ báo con số +308% của AAPL mà không có đường cơ sở, đó mới là con số bịa."*

## 4.6. Giới hạn của phép đo (nêu trước, không đợi thầy hỏi)

| Giới hạn | Vì sao có | Hướng mở rộng |
|---|---|---|
| Mẫu 101 mã, không phải toàn bộ 1.002 | Thời gian chạy ~2 phút/chiến lược | Chạy `--per-exchange 0 --limit 0` để dùng toàn bộ universe (khoảng 20 phút) |
| Chỉ 2 chiến lược (MA, RSI) | Chưa có bộ chiến lược lớn hơn | Thêm momentum, breakout, mean-reversion vào `STRATEGY_MAP` |
| Tham số chiến lược **cố định**, không tối ưu trên train | Bản hiện tại chỉ chọn tham số mặc định | Bổ sung bước chọn tham số tối ưu trên train window |
| Quy mô vốn cố định 10.000 | Cho phép so sánh đơn giản | Thử nhiều quy mô vốn, có tính phí tối thiểu theo sàn |
| Không tính thuế, không tính lãi vay vay margin | Phạm vi nghiên cứu học thuật | Mở rộng sang phí tổng thể (thuế + spread + phiên bản) |
| Mẫu chỉ gồm cổ phiếu, không có ETF hay chỉ số | Bản đồ án chỉ ingest cổ phiếu | Thêm chỉ số để có đường cơ sở "thị trường" thay vì chỉ "mã đó" |

---

# PHẦN 5 — CHI TIẾT KỸ THUẬT: PHÂN PHỐI THEO SÀN

## 5.1. Chi tiết: kết quả theo sàn (MA Crossover)

Đo ngày 11/11/2026, 101 mã, walk-forward 365/90/90:

| Sàn | Số mã | Median RR chiến lược | Median RR mua & giữ | Sharpe CL | Sharpe B&H | % mã thắng B&H |
|---|---|---|---|---|---|---|
| BME (Tây Ban Nha) | 8 | 0,23% | 2,52% | — | — | 12,5% |
| Euronext | 8 | 0,62% | 2,25% | — | — | 0,0% |
| HKEX | 8 | −0,10% | 0,46% | — | — | 25,0% |
| HOSE (Việt Nam) | 8 | 0,35% | 2,75% | — | — | 0,0% |
| KRX (Hàn Quốc) | 8 | 0,54% | 2,58% | — | — | 25,0% |
| LSE (Anh) | 8 | −0,02% | 1,66% | — | — | 0,0% |
| NYSE/NASDAQ | 8 | 0,38% | 2,65% | — | — | 0,0% |
| Nasdaq Nordic | 8 | −0,12% | 1,66% | — | — | 25,0% |
| SIX (Thụy Sĩ) | 5 | −0,15% | 1,80% | — | — | 0,0% |
| TSE (Nhật) | 8 | 0,45% | 3,07% | — | — | 12,5% |
| TSX (Canada) | 8 | 0,53% | 2,46% | — | — | 0,0% |
| TWSE (Đài Loan) | 8 | 0,93% | 4,66% | — | — | 0,0% |
| XETRA (Đức) | 8 | 0,09% | 2,48% | — | — | 12,5% |

> Cột Sharpe để trống trong bảng này vì bảng gốc (`data/multi_symbol_walkforward.json`) lưu giá trị đó ở trường `strategy_median_sharpe` / `buy_hold_median_sharpe` — giá trị có thật, chỉ là bảng tóm tắt trong tài liệu này không liệt kê để tránh nhân đôi độ dài. Trang web (tab "Walk-forward đa mã" của `/backtesting`) hiển thị đầy đủ.

## 5.2. Cách đọc

**Kết luận quan trọng: kết luận KHÔNG đổi theo sàn.**

Ở **cả 13 sàn**, median lợi nhuận của chiến lược đều **thấp hơn** median lợi nhuận của mua & giữ. Không sàn nào chiến lược thắng rõ rệt — tỉ lệ mã thắng cao nhất là 25% (HKEX, KRX, Nasdaq Nordic), tức là trong 8 mã thì 2 mã thắng, vẫn là đa số thua.

Điều này có hai ý nghĩa:

1. **Phát hiện này không phải đặc sản của một thị trường.** Nếu chỉ thất bại ở Mỹ, ta có thể nói "thị trường Mỹ hiệu quả hơn, chiến lược kỹ thuật không có chỗ". Nhưng nó thất bại **đồng đều** ở HOSE, TSE, KRX, HKEX, TWSE — nghĩa là đây là **đặc tính của chính quy tắc mua bán theo chỉ báo kỹ thuật**, chứ không phải đặc thù của một sàn nào.

2. **Kết quả của bài luận văn trước đây không bị "lỗi vì AAPL".** AAPL chỉ là một trong 1.002 mã, và phát hiện trên AAPL vẫn đúng trên 101 mã.

> **Cách trả lời khi thầy hỏi "có sàn nào chiến lược này ăn không?":**
>
> *"Em đã kiểm tra cả 13 sàn trong mẫu và câu trả lời là không có sàn nào. Điểm em muốn nhấn mạnh là đây không phải hạn chế của phép đo — nếu chỉ thất bại ở một sàn, em sẽ không kết luận được gì. Thất bại đồng đều ở cả 13 sàn là bằng chứng cho thấy giới hạn nằm ở bản chất của quy tắc (mua bán theo chỉ báo, ra vào nhiều lần, tự cắt lợi nhuận xu hướng), chứ không phải ở một thị trường cụ thể. Cái mà chiến lược thực sự mang lại là giảm drawdown, và con số đó em báo cáo đầy đủ."*

---

# PHẦN 6 — CHI TIẾT KỸ THUẬT: CÁCH CHẠY LẠI

## 6.1. Lệnh

```powershell
cd backend

# MA Crossover — 8 mã/sàn
.venv\Scripts\python.exe scripts\run_multi_symbol_walkforward.py --per-exchange 8 --strategy ma_crossover

# RSI — 8 mã/sàn
.venv\Scripts\python.exe scripts\run_multi_symbol_walkforward.py --per-exchange 8 --strategy rsi_strategy

# Chạy thử nhanh trên 6 mã bất kỳ
.venv\Scripts\python.exe scripts\run_multi_symbol_walkforward.py --limit 6 --per-exchange 0
```

## 6.2. File sinh ra

| File | Nội dung |
|---|---|
| `backend/data/multi_symbol_walkforward.json` | Báo cáo MA Crossover |
| `backend/data/multi_symbol_walkforward_rsi.json` | Báo cáo RSI |

Cấu trúc JSON:

```json
{
  "generated_at": "2026-11-11T11:47:05.146566+00:00",
  "config": { "strategy": "ma_crossover", "train_period_days": 365, "...": "..." },
  "strategy_distribution": { "median_avg_test_sharpe": -0.0246, "...": "..." },
  "buy_and_hold_distribution": { "median_avg_return": 0.0228, "...": "..." },
  "head_to_head": { "paired_windows": 3687, "...": "..." },
  "by_exchange": { "HOSE": { "...": "..." }, "...": "..." },
  "per_symbol": [ { "symbol": "VCB", "...": "..." } ],
  "errors": []
}
```

## 6.3. Kiểm thử liên quan

| File test | Phủ |
|---|---|
| `backend/tests/test_backtest_benchmark.py` | 6 test: cùng phiên, cùng phí, tái lập được, drawdown, engine trả benchmark, walk-forward ghi baseline từng cửa sổ |
| `backend/tests/test_backtest_walk_forward.py` | 6 test: warmup, cửa sổ train cố định, không cửa sổ lỗi, overfitting ratio đọc được |
| `backend/tests/test_backtest_accounting.py` | 10 test: khớp PnL, trừ phí, drawdown không dương |

Chạy:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests\test_backtest_benchmark.py tests\test_backtest_walk_forward.py tests\test_backtest_accounting.py -q
```

---

# PHẦN 7 — GIAO DIỆN NGƯỜI DÙNG

## 7.1. Hiểu đơn giản

Có **hai** chỗ trên web hiện đường cơ sở, và sau ngày 11/11/2026 chúng nằm trong **cùng một trang**, chia thành hai tab:

1. **Trang "Đánh giá chiến lược"** (`/backtesting`), tab **"Một mã cổ phiếu"** — khi chạy backtest cho một mã, response kèm thêm `benchmark` (metrics + equity curve + drawdown của mua & giữ) và `excess_return_vs_benchmark`. Biểu đồ equity vẽ **hai đường**: đường liền là chiến lược, đường đứt nét là mua & giữ.

2. **Cùng trang đó**, tab **"Walk-forward đa mã"** — hiển thị toàn bộ báo cáo phân phối: metric so sánh, biểu đồ cột theo sàn, bảng theo sàn, bảng chi tiết từng mã, và danh sách mã không đo được.

**Vì sao gộp chứ không tách hai trang?** Vì hai bên phải nói về **cùng một quy tắc**. Khi tách trang, mỗi trang mang lựa chọn chiến lược riêng, và người đọc có thể vô tình so một lần chạy MA với một báo cáo RSI mà không nhận ra. Ở đây lựa chọn chiến lược nằm ở **đầu trang**, dùng chung cho cả hai tab.

## 7.2. Chi tiết kỹ thuật

| Thành phần | File |
|---|---|
| Engine trả benchmark | `backend/app/backtesting/engine.py` |
| Validator ghi baseline từng cửa sổ | `backend/app/backtesting/walk_forward.py` |
| Module đường cơ sở dùng chung | `backend/app/backtesting/benchmark.py` |
| Endpoint đọc báo cáo | `backend/app/api/v1/endpoints/backtesting.py` |
| Script chạy phép đo | `backend/scripts/run_multi_symbol_walkforward.py` |
| Kiểu dữ liệu frontend | `frontend/src/types/backtesting.ts` |
| Biểu đồ 2 đường | `frontend/src/components/charts/EquityCurve.tsx` |
| Trang + tab strip | `frontend/src/pages/Backtesting.tsx` |
| Tab một mã | `frontend/src/components/backtesting/SingleSymbolBacktest.tsx` |
| Tab đa mã | `frontend/src/components/backtesting/MultiSymbolWalkForward.tsx` |
| Gọi API | `frontend/src/api/backtesting.ts` |
| Route | `frontend/src/App.tsx` → `/backtesting` |
| Menu | `frontend/src/components/layout/NavBar.tsx` |

---

# PHỤ LỤC A — BẢN ĐỒ MÃ NGUỒN (phần liên quan)

```
backend/
├── app/
│   ├── backtesting/
│   │   ├── benchmark.py          ← MỚI: đường cơ sở mua & giữ
│   │   ├── engine.py             ← trả benchmark trong response
│   │   ├── walk_forward.py       ← baseline từng cửa sổ + excess return
│   │   ├── metrics.py            ← Sharpe, drawdown, win rate
│   │   ├── simulator.py          ← khớp lệnh bar kế tiếp, đóng vị thế cuối
│   │   └── strategies/           ← ma_crossover, rsi_strategy
│   ├── api/v1/endpoints/
│   │   └── backtesting.py        ← endpoint đọc báo cáo đa mã
│   └── services/
│       └── backtest_service.py
├── scripts/
│   └── run_multi_symbol_walkforward.py   ← MỚI: chạy phép đo đa mã
├── tests/
│   └── test_backtest_benchmark.py        ← MỚI: 6 test
└── data/
    ├── multi_symbol_walkforward.json      ← báo cáo MA
    └── multi_symbol_walkforward_rsi.json  ← báo cáo RSI

frontend/src/
├── api/backtesting.ts          ← fetchMultiSymbolReport
├── types/backtesting.ts        ← BacktestBenchmark, MultiSymbolReport
├── components/charts/
│   └── EquityCurve.tsx         ← vẽ 2 đường
├── components/backtesting/
│   ├── SingleSymbolBacktest.tsx    ← tab 1: một mã
│   └── MultiSymbolWalkForward.tsx  ← tab 2: đa mã
└── pages/
    └── Backtesting.tsx         ← trang /backtesting, 2 tab
```

# PHỤ LỤC B — MA TRẬN TRUY VẾT YÊU CẦU ĐỒ ÁN

| Yêu cầu đồ án | Thực hiện ở đâu | Bằng chứng |
|---|---|---|
| Kiểm định chiến lược ngoài mẫu | `app/backtesting/walk_forward.py` | 3.687 cửa sổ kiểm tra trên 101 mã |
| Có đường cơ sở so sánh | `app/backtesting/benchmark.py` | 91,1% mã mua & giữ có lãi |
| Báo cáo phân phối, không phải một số | `scripts/run_multi_symbol_walkforward.py` | median Sharpe, % mã lãi, theo sàn |
| Phân phối theo sàn | `scripts/run_multi_symbol_walkforward.py` → `by_exchange` | 13 sàn |
| Thêm đường baseline vào cùng biểu đồ | `frontend/src/components/charts/EquityCurve.tsx` | 2 đường trên cùng trục |
| Không bịa số khi thiếu dữ liệu | `api/v1/endpoints/backtesting.py` | trả lý do + lệnh, không trả số giả |
| Có test cho từng bất biến | `backend/tests/test_backtest_benchmark.py` | 6 test |
