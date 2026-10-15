# 🎓 BÀI THUYẾT TRÌNH KHÓA LUẬN TỐT NGHIỆP
## "Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán ứng dụng học sâu và AI Agent"

---

> **Ghi chú cho em khi thuyết trình:** File này em viết theo tinh thần **"dạy một người chưa biết gì về công nghệ"**. Mọi thuật ngữ IT đều được giải thích bằng ví dụ đời thường. Em xưng "em", giọng văn trôi chảy nhưng chậm rãi, để thầy cô theo dõi được. Chương 2 là **"Từ điển cho người mới"** — em khuyến khích thầy cô đọc chương này trước khi vào phần kỹ thuật. Các chương sau sẽ tự nhiên hơn sau khi đã có nền.
>
> **Disclaimer:** Đây là prototype nghiên cứu học thuật. Em không giao dịch chứng khoán thật, không đặt lệnh mua bán, không cam kết lợi nhuận, không khẳng định LSTM là mô hình tốt nhất. Backtest chỉ đánh giá hiệu suất lịch sử giả định, không phải dự đoán tương lai.

---

# MỤC LỤC

1. [Lời mở đầu](#1-lời-mở-đầu--em-sẽ-trình-bày-gì)
2. **[🌟 Từ điển cho người mới — Đọc chương này trước nhé](#2--từ-điển-cho-người-mới--đọc-chương-này-trước-nhé)**
3. [Bối cảnh – Vì sao em chọn đề tài này?](#3-bối-cảnh--vì-sao-em-chọn-đề-tài-này)
4. [Mục tiêu & phạm vi đề tài](#4-mục-tiêu--phạm-vi-đề-tài)
5. [Em làm cái gì? – Bức tranh toàn cảnh bằng ví dụ "Tiệm phở của em"](#5-em-làm-cái-gì--bức-tranh-toàn-cảnh-bằng-ví-dụ-tiệm-phở-của-em)
6. [Tầng 1 – "Hạ tầng" giống như xây nhà bếp](#6-tầng-1--hạ-tầng-giống-như-xây-nhà-bếp)
7. [Tầng 2 – Dữ liệu chứng khoán được "nấu" qua 3 lớp như thế nào](#7-tầng-2--dữ-liệu-chứng-khoán-được-nấu-qua-3-lớp-như-thế-nào)
8. [Tầng 3 – Tính 94 chỉ báo kỹ thuật (giống xem sức khỏe của cổ phiếu)](#8-tầng-3--tính-94-chỉ-báo-kỹ-thuật-giống-xem-sức-khỏe-của-cổ-phiếu)
9. [Tầng 4 – Dự báo giá cổ phiếu bằng 3 cách](#9-tầng-4--dự-báo-giá-cổ-phiếu-bằng-3-cách)
10. [Tầng 5 – Backtesting – "Thử chơi chứng khoán trên giấy"](#10-tầng-5--backtesting--thử-chơi-chứng-khoán-trên-giấy)
11. [Tầng 6 – AI Agent – Trợ lý ảo trả lời "không bịa số"](#11-tầng-6--ai-agent--trợ-lý-ảo-trả-lời-không-bịa-số)
12. [Tầng 7 – Giao diện web cho người dùng](#12-tầng-7--giao-diện-web-cho-người-dùng)
13. [Demo luồng chạy thật](#13-demo-luồng-chạy-thật)
14. [Kết quả thực nghiệm – "Sức khỏe" của hệ thống](#14-kết-quả-thực-nghiệm--sức-khỏe-của-hệ-thống)
15. [Hạn chế & phạm vi giới hạn – Em thành thật với thầy cô](#15-hạn-chế--phạm-vi-giới-hạn--em-thành-thật-với-thầy-cô)
16. [Đóng góp mới & Hướng phát triển](#16-đóng-góp-mới--hướng-phát-triển)
17. **[🌟 25 câu hỏi hội đồng + câu trả lời của em](#17--25-câu-hỏi-hội-đồng--câu-trả-lời-của-em)**
18. [Lời cảm ơn & kết thúc](#18-lời-cảm-ơn--kết-thúc)

**Phụ lục:** Bảng lệnh thường dùng & URL truy cập nhanh.

---

# 1. LỜI MỞ ĐẦU – EM SẼ TRÌNH BÀY GÌ?

Kính thưa thầy cô, em xin tự giới thiệu. Em là sinh viên ngành Công nghệ thông tin, hôm nay em xin được bảo vệ khóa luận tốt nghiệp với đề tài:

> **"Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán ứng dụng học sâu và AI Agent."**

Trước khi thầy cô cảm thấy "trời ơi toàn từ lạ", em xin phép tóm tắt bằng một câu đời thường:

> **Em xây dựng một hệ thống giống như một "siêu thị dữ liệu chứng khoán" trên máy tính, nơi em có thể lưu trữ hàng chục năm lịch sử giá cổ phiếu của Việt Nam và thế giới, sau đó dùng máy học (học sâu) để dự đoán giá, kiểm tra chiến lược mua bán, và đặc biệt — em có một "trợ lý ảo AI" trả lời câu hỏi chứng khoán bằng tiếng Việt mà không bịa số.**

Để thầy cô hình dung rõ hơn, em xin nói 3 con số em tự hào nhất trong đồ án này:

1. **Hệ thống chạy được 28/28 bài kiểm tra tự động** (tính đến ngày 30/09/2026).
2. **Tổng cộng đã ingest được 917 mã chứng khoán** (từ Mỹ, Việt Nam, Nhật, Hàn, Đài Loan, Châu Âu...) với **~1,1 triệu dòng dữ liệu thật** mỗi ngày.
3. **Toàn bộ chạy miễn phí** trên một chiếc laptop thường — không cần server đắt tiền, không cần đăng ký dịch vụ trả phí.

Tuy nhiên, vì thầy cô có thể là người **chưa quen với công nghệ thông tin**, em xin phép dành riêng chương tiếp theo để giải thích tất cả các thuật ngữ em sẽ dùng xuyên suốt bài. Thầy cô đọc chương 2 trước rồi quay lại đọc các chương sau sẽ dễ hiểu hơn rất nhiều ạ.

Em xin mời thầy cô sang chương 2.

---

# 2. 🌟 TỪ ĐIỂN CHO NGƯỜI MỚI – ĐỌC CHƯƠNG NÀY TRƯỚC NHÉ

Kính thưa thầy cô, em biết đề tài có rất nhiều thuật ngữ IT. Em xin phép giải thích từng thuật ngữ bằng ví dụ đời thường trước khi đi vào chi tiết. Em sẽ giải thích theo thứ tự alphabet để thầy cô dễ tra cứu.

## A – API

**API** là viết tắt của "Application Programming Interface" – tạm dịch là "cổng giao tiếp giữa hai chương trình máy tính".

**Ví dụ đời thường:**
Hãy tưởng tượng thầy cô vào nhà hàng. Thầy cô không vào bếp lấy đồ ăn. Thầy cô gọi phục vụ (waiter). Phục vụ là **API**:
- Thầy cô: "Cho tôi phở" → gửi **request** qua API.
- Bếp nấu → trả về **response** qua API cho phục vụ.
- Phục vụ mang ra cho thầy cô.

Trong đồ án, **API** của em là các "URL" mà frontend (phần giao diện web) gọi đến backend (phần xử lý dữ liệu) để lấy thông tin. Ví dụ:
- `http://localhost:8000/api/v1/stocks/VCB` → API này trả về dữ liệu giá cổ phiếu VCB.

## B – Backend

**Backend** = "phần sau của hệ thống", tức là **bộ máy xử lý bên trong**, người dùng không nhìn thấy trực tiếp.

**Ví dụ đời thường:**
- Khi thầy cô gọi Grab, phần bạn thấy trên điện thoại (bản đồ, nút bấm) gọi là **frontend**.
- Phần bên trong Grab tính toán tài xế gần nhất, giá cước, đường đi — đó là **backend**.

Trong đồ án:
- **Backend của em** được viết bằng ngôn ngữ **Python** (một ngôn ngữ lập trình rất phổ biến).
- Backend là nơi em đọc dữ liệu chứng khoán, tính chỉ báo kỹ thuật, train (huấn luyện) mô hình dự báo.

## C – Chứng khoán

**Chứng khoán** là các "giấy tờ có giá" được mua bán trên sàn giao dịch. Ví dụ:
- **Cổ phiếu** (stock): giấy chứng nhận em sở hữu một phần nhỏ của một công ty (VD: mua cổ phiếu VCB nghĩa là em sở hữu một phần nhỏ ngân hàng Vietcombank).
- **Trái phiếu** (bond): giấy hứa cho vay, công ty/nhà nước vay tiền và trả lãi.
- **Quỹ ETF**: gói nhiều cổ phiếu gộp lại.

Trong đồ án em chỉ nghiên cứu **cổ phiếu** và **giá đóng cửa hàng ngày** của chúng.

## D – Database (Cơ sở dữ liệu)

**Database** = nơi lưu trữ dữ liệu, giống như một **tủ hồ sơ khổng lồ** trong máy tính.

**Ví dụ đời thường:**
Một công ty có tủ hồ sơ chứa hồ sơ nhân viên. Mỗi ngăn tủ là một **bảng** (table), mỗi hồ sơ là một **dòng** (row), mỗi mục trong hồ sơ (họ tên, ngày sinh...) là một **cột** (column).

Trong đồ án em dùng 2 loại database:
- **MySQL**: lưu "metadata" (dữ liệu về dữ liệu, kiểu "cuốn sổ ghi chép ai đã chạy gì").
- **MinIO**: lưu dữ liệu thô (file Excel/CSV dạng Parquet).

## E – ETL

**ETL** = Extract – Transform – Load, tạm dịch: **Rút – Biến đổi – Nạp**.

**Ví dụ đời thường:**
- **Extract (Rút)**: Đi chợ mua rau, thịt, cá.
- **Transform (Biến đổi)**: Rửa rau, cắt rau, phi lê cá.
- **Load (Nạp)**: Cho vào tủ lạnh / nồi nấu.

Trong đồ án em ETL dữ liệu chứng khoán:
- **Extract**: Tải giá cổ phiếu từ Yahoo Finance, SSI, Finnhub...
- **Transform**: Loại bỏ dữ liệu lỗi, tính toán các chỉ báo.
- **Load**: Lưu vào các tầng Bronze–Silver–Gold (em sẽ giải thích ở chương 7).

## F – Frontend

**Frontend** = "phần trước của hệ thống", tức là **giao diện mà người dùng nhìn thấy trên màn hình**.

**Ví dụ đời thường:**
- **Frontend** của Grab là cái app trên điện thoại thầy cô, với bản đồ, nút bấm.
- **Backend** của Grab là phần máy chủ xử lý.

Trong đồ án em có frontend là **trang web** viết bằng React, thầy cô sẽ thấy chart (biểu đồ) cổ phiếu, bảng số liệu, ô chat với AI...

## G – Git

**Git** = phần mềm để **theo dõi lịch sử thay đổi** của code. Giống như chức năng "track changes" trong Word, nhưng mạnh hơn nhiều.

**Ví dụ đời thường:**
Khi thầy cô soạn một văn bản dài, thầy cô Ctrl+Z để undo khi lỡ tay xóa. Git làm điều đó cho **toàn bộ project**, cho cả đội, qua nhiều năm. Em dùng Git để quản lý code đồ án.

## H – Học sâu (Deep Learning)

**Học sâu** là một nhánh của **Trí tuệ nhân tạo (AI)**, dùng **mạng nơ-ron nhân tạo** (neural network) mô phỏng cách não người hoạt động.

**Ví dụ đời thường:**
Khi thầy cô dạy một đứa trẻ nhận diện con mèo: chỉ cho nó xem 1000 ảnh mèo, sau đó nó tự học ra "mèo có tai nhọn, có ria mép". Học sâu cũng vậy — máy tính học từ rất nhiều ví dụ.

Trong đồ án em dùng **LSTM** (một loại mạng nơ-ron chuyên xử lý chuỗi thời gian) để dự báo giá cổ phiếu.

## I – Ingest (Nạp dữ liệu)

**Ingest** trong tiếng Anh nghĩa là "nạp vào". Trong xử lý dữ liệu, **ingest** nghĩa là **lấy dữ liệu từ nguồn bên ngoài và đưa vào hệ thống**.

**Ví dụ đời thường:**
Khi em đi chợ mua rau sáng, em "ingest" rau vào tủ lạnh nhà em.

Trong đồ án, em "ingest" = tải giá cổ phiếu từ Yahoo Finance về máy tính em.

## J – JSON

**JSON** = định dạng lưu dữ liệu kiểu "key-value" (khóa-giá trị), giống như một quyển từ điển.

**Ví dụ:**
```
{
    "tên": "Nguyễn Văn A",
    "tuổi": 22,
    "mã_cổ_phiếu": ["VCB", "FPT"]
}
```

Khi frontend hỏi backend "cho tôi thông tin cổ phiếu VCB", backend trả về một **JSON**. Thầy cô không cần đọc JSON — frontend sẽ hiển thị nó thành bảng đẹp.

## K – Kafka

**Apache Kafka** = một hệ thống giúp **truyền tin nhắn liên tục** giữa nhiều chương trình, theo thời gian thực.

**Ví dụ đời thường:**
Hãy tưởng tượng thầy cô mở một **nhóm chat trên Zalo** cho cả công ty. Mọi người gửi tin vào nhóm, ai cần thì đọc. Kafka giống vậy, nhưng dành cho máy tính.

Trong đồ án em dùng Kafka để truyền dữ liệu real-time (cập nhật giá liên tục) giữa các thành phần.

## L – Lakehouse

**Lakehouse** = một kiến trúc lưu trữ dữ liệu kết hợp ưu điểm của **Data Lake** (rẻ, chứa nhiều) và **Data Warehouse** (có cấu trúc, truy vấn nhanh).

**Ví dụ đời thường:**
- **Data Lake** giống **bãi đỗ xe rộng** — đỗ nhiều xe nhưng không biết xe nào của ai.
- **Data Warehouse** giống **nhà xe nhiều tầng** — biết chính xác xe nào ở tầng nào, chỗ nào, nhưng đắt tiền và chật.
- **Lakehouse** = **bãi đỗ xe vừa rộng vừa có camera AI nhận diện biển số**. Rẻ + có tổ chức.

## M – MinIO

**MinIO** = một phần mềm lưu trữ file (ảnh, video, data...) trên máy chủ, **tương thích với Amazon S3** (dịch vụ lưu trữ nổi tiếng của Amazon).

**Ví dụ đời thường:**
MinIO giống **Google Drive phiên bản nội bộ**. Thầy cô upload file lên, ai cũng có thể tải về. MinIO dành cho máy chủ, không cho người dùng cuối.

Trong đồ án, em lưu hàng triệu file dữ liệu chứng khoán lên MinIO.

## N – Notebook (Jupyter)

**Jupyter Notebook** = một phần mềm cho phép viết code theo từng ô nhỏ, kết hợp giữa **code + văn bản giải thích + biểu đồ**.

**Ví dụ đời thường:**
Giống như một cuốn sổ tay, mỗi trang có: phần giải thích (toàn chữ), phần tính toán (có số), phần biểu đồ (có hình). Em dùng Notebook khi cần thử nghiệm nhanh.

## O – Open source

**Open source** = mã nguồn mở, nghĩa là **ai cũng có thể xem, sửa, dùng miễn phí**. Ngược lại với phần mềm trả phí (như Windows, Photoshop).

Trong đồ án em dùng toàn phần mềm open source: Python, FastAPI, React, Apache Kafka, Apache Iceberg, PostgreSQL, MySQL, MinIO... Tất cả đều miễn phí.

## P – Pandas

**Pandas** = một **thư viện Python** (Python library) chuyên xử lý bảng dữ liệu.

**Ví dụ đời thường:**
Pandas giống như **Excel phiên bản lập trình** — em có thể đọc file, lọc, tính tổng, vẽ biểu đồ, nhưng tự động và xử lý được hàng triệu dòng.

Trong đồ án em dùng Pandas suốt ngày — nó là "cái kéo + cái dao" để cắt gọt dữ liệu.

## Q – Quant (Định lượng)

**Quantitative** = "dựa trên con số", ngược lại với "cảm tính". Trader/chuyên gia phân tích theo trường phái Quant thường dùng mô hình toán học thay vì trực giác.

Trong đồ án, em dùng phương pháp Quant — tất cả ra quyết định đều dựa trên con số, không "thấy thích" cổ phiếu nào rồi mua.

## R – REST

**REST** là một kiểu thiết kế API, viết tắt của "Representational State Transfer". Thầy cô chỉ cần nhớ: **REST API là cách phổ biến nhất để frontend gọi backend trên web**.

## S – Spark (Apache Spark)

**Spark** = một **engine** xử lý dữ liệu lớn cực nhanh, dùng trong các công ty lớn.

**Ví dụ đời thường:**
Pandas = cái **chảo nhỏ** trong bếp, nấu được vài phần cơm.
Spark = **hệ thống 100 bếp** chạy song song, nấu được cả ngàn phần.

Trong đồ án em **không dùng Spark** (vì data chưa đủ lớn), nhưng code có sẵn đường Spark để dùng khi cần.

## T – Time-travel (Du hành thời gian)

**Time-travel** = khả năng **truy vấn dữ liệu tại một thời điểm trong quá khứ**.

**Ví dụ đời thường:**
Trong Google Docs, thầy cô có thể xem lại version "từ tháng 3" dù hiện tại đã qua tháng 10. Apache Iceberg cho phép data cũng vậy — em hỏi "giá VCB ngày 15/03/2024", hệ thống trả về giá tại thời điểm đó.

## U – URL

**URL** = địa chỉ web (như `https://google.com` hoặc `http://localhost:8000`). Thầy cô thấy cái này hằng ngày rồi.

## V – Validation (Kiểm tra hợp lệ)

**Validation** = kiểm tra dữ liệu có hợp lệ không.

**Ví dụ đời thường:**
Thầy cô mua rau ngoài chợ, em phải kiểm tra: rau có héo không? có sâu không? có phun thuốc không? Validation dữ liệu tương tự: kiểm tra giá cổ phiếu có hợp lý không (giá cao phải ≥ giá thấp, khối lượng không âm).

## W – Walk-Forward Validation

**Walk-forward validation** = một **phương pháp kiểm tra mô hình** bằng cách chia dữ liệu thành nhiều **cửa sổ trượt** (giống cửa sổ kéo dọc bằng).

**Ví dụ đời thường:**
Thầy cô học tiếng Anh. Thay vì học cả năm rồi thi 1 lần, thầy cô học 6 tháng → kiểm tra 1 tháng → học tiếp 1 tháng → kiểm tra tiếp... Walk-forward validation cũng vậy: train mô hình 6 tháng dữ liệu, test 1 tháng, lặp lại nhiều lần.

## X – Xử lý dữ liệu (Data Processing)

Cụm từ chung để chỉ việc **đọc, lọc, tính toán, lưu trữ dữ liệu**. Em sẽ nói nhiều về cái này.

## Y – YAML

**YAML** là một dạng file cấu hình, đơn giản hơn JSON nhưng cùng mục đích. File `docker-compose.yml` của em là dạng YAML.

## Z – Z-index (chỉ để cho vui thôi ạ 😅)

Đây là thuật ngữ CSS dành cho lập trình viên frontend, chắc thầy cô không cần quan tâm.

---

## Thuật ngữ chuyên ngành tài chính em hay dùng

### OHLCV (5 chữ cái quan trọng nhất)

**OHLCV** là viết tắt của 5 con số mô tả **một phiên giao dịch**:

| Chữ | Tiếng Anh | Nghĩa | Ví dụ |
|---|---|---|---|
| **O** | Open | Giá **mở cửa** (đầu phiên) | 95.000đ |
| **H** | High | Giá **cao nhất** trong phiên | 96.500đ |
| **L** | Low | Giá **thấp nhất** trong phiên | 94.500đ |
| **C** | Close | Giá **đóng cửa** (cuối phiên) | 96.000đ |
| **V** | Volume | **Khối lượng** giao dịch (bao nhiêu cổ phiếu đã mua bán) | 1.000.000 cổ phiếu |

Mỗi ngày có 5 con số này. Lưu 10 năm thì có ~2500 phiên × 5 số = ~12.500 số cho mỗi mã. Vài trăm mã thì thành hàng triệu số — đó là lý do em cần Lakehouse!

### Các chỉ báo kỹ thuật em dùng (em sẽ giải thích kỹ ở chương 8)

- **SMA** (Simple Moving Average): Trung bình cộng giá N ngày gần nhất. N = 20 → SMA20.
- **EMA** (Exponential Moving Average): Trung bình có trọng số, giá gần hiện tại quan trọng hơn.
- **RSI** (Relative Strength Index): Bộ đo "quá mua / quá bán", 0–100.
- **MACD**: Phát hiện xu hướng tăng/giảm.
- **Bollinger Bands**: Dải bao quanh giá, đo biến động.
- **ATR**, **ADX**, **Ichimoku**, **MFI**, **VWAP**... — em sẽ giải thích chương 8.

### Các thuật ngữ ML em dùng (em sẽ giải thích chương 9)

- **Linear Regression**: Đường thẳng đi qua các điểm dữ liệu.
- **ARIMA**: Mô hình cổ điển cho chuỗi thời gian.
- **LSTM**: Mạng nơ-ron "nhớ" được pattern dài hạn.
- **Train (Huấn luyện)**: Cho máy học từ dữ liệu quá khứ.
- **Predict (Dự báo)**: Máy dựa vào kiến thức đã học để đoán tương lai.
- **Overfitting (Học vẹt)**: Mô hình học quá kỹ dữ liệu cũ, áp dụng sang dữ liệu mới thì sai.

---

**Kết thúc "Từ điển cho người mới" — giờ thầy cô có nền tảng để đọc các chương sau ạ.**

---

# 3. BỐI CẢNH – VÌ SAO EM CHỌN ĐỀ TÀI NÀY?

Kính thưa thầy cô, khi nghiên cứu thị trường dữ liệu chứng khoán hiện tại em nhận ra 3 vấn đề rất rõ ràng:

**Vấn đề 1 – Dữ liệu rải rác nhiều nơi.**
Nếu thầy cô muốn xem giá cổ phiếu 5 năm qua của 50 mã (Việt Nam + Mỹ + Nhật), thầy cô phải vào nhiều website khác nhau: Yahoo Finance cho Mỹ, SSI cho Việt Nam, Bloomberg cho Nhật... Mỗi chỗ có định dạng khác nhau, múi giờ khác nhau, ngày tháng khác nhau. Em phải tải về rồi ghép tay → cực kỳ mất thời gian.

**Vấn đề 2 – Lý thuyết và thực hành tách rời.**
Em đọc rất nhiều sách về phân tích kỹ thuật (RSI, MACD...), sách về dự báo giá, sách về backtest. Nhưng mỗi cuốn chỉ dạy một phần, không có cuốn nào chỉ em cách kết nối tất cả lại. Em muốn xây một hệ thống **tích hợp đủ cả phân tích + dự báo + backtest trong cùng một nền tảng**.

**Vấn đề 3 – Chatbot AI hay "bịa số".**
Em thử nhiều chatbot AI miễn phí: hỏi "RSI hiện tại của VCB là bao nhiêu?" → câu trả lời thường là một con số rất "tự tin" nhưng… không có cơ sở, vì AI không có dữ liệu real-time. Em quyết định: **em sẽ xây một AI Agent mà chỉ trả lời khi đã gọi tool (công cụ) lấy dữ liệu thật từ backend. Không có data thì thà nói "không biết" còn hơn đoán.**

Từ 3 vấn đề đó, em đặt câu hỏi nghiên cứu:

> *Có thể xây dựng một hệ thống end-to-end (từ A đến Z) cho dữ liệu chứng khoán vừa có tính ACID (đảm bảo không mất dữ liệu), vừa hỗ trợ time-travel (xem lại dữ liệu cũ), vừa cho phép tính chỉ báo kỹ thuật, dự báo bằng học sâu, kiểm tra chiến lược giao dịch, và cho phép người dùng hỏi đáp tự nhiên qua AI không?*

Em xin trình bày câu trả lời qua các chương sau ạ.

---

# 4. MỤC TIÊU & PHẠM VI ĐỀ TÀI

## 4.1. Mục tiêu cụ thể

| # | Mục tiêu | Đo lường thế nào |
|---|---|---|
| 1 | Xây pipeline dữ liệu chạy ổn định | 28/28 health check pass |
| 2 | Hỗ trợ nhiều nguồn dữ liệu | 6 providers (yfinance, Finnhub, Alpha Vantage, SSI, web scraper, multi-source failover) |
| 3 | Hỗ trợ đa quốc gia | 958 ticker định nghĩa, ~917 ticker ingest thật |
| 4 | Tính 94 chỉ báo kỹ thuật | Đếm cột trong Gold = 94 |
| 5 | Huấn luyện 3 mô hình dự báo | Linear Regression, ARIMA, LSTM cùng so sánh |
| 6 | Backtest engine tự viết | MA Crossover, RSI Strategy + Walk-Forward |
| 7 | AI Agent tool-calling | Gemini Free + Local fallback, không bịa số |
| 8 | Frontend React đẹp, dễ dùng | 7 trang: Dashboard, Indicators, Forecast, Backtest, Agent, ... |
| 9 | Chi phí 0 đồng | Tất cả phần mềm open source, dữ liệu free |

## 4.2. Phạm vi giới hạn (em xin nói rõ trước)

- Đây là **prototype nghiên cứu** — KHÔNG phải sản phẩm thương mại.
- Em **KHÔNG đặt lệnh mua bán thật**, **KHÔNG cam kết lợi nhuận**, **KHÔNG khẳng định LSTM là tốt nhất**.
- **Backtest chỉ đánh giá hiệu suất lịch sử**, không phải dự đoán tương lai.
- Tất cả dữ liệu là **daily OHLCV** (đóng cửa cuối ngày), chưa xử lý tick-level.

---

# 5. EM LÀM CÁI GÌ? – BỨC TRANH TOÀN CẢNH BẰNG VÍ DỤ "TIỆM PHỞ CỦA EM"

Kính thưa thầy cô, để thầy cô dễ hình dung, em xin phép ví von cả hệ thống phức tạp này là **"Tiệm phở của em"**. Mỗi tầng của đồ án là một khâu trong tiệm phở.

**Em có một tiệm phở bán phở "chứng khoán" — nghĩa là phở "nấu" từ dữ liệu chứng khoán:**

```
┌──────────────────────────────────────────────────────────────────┐
│ 🛒 CHỢ NGUYÊN LIỆU (Data Sources - 6 nguồn free)                 │
│   Yahoo Finance · Finnhub · Alpha Vantage · SSI iBoard · ...      │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼ Em đi chợ mua nguyên liệu
┌──────────────────────────────────────────────────────────────────┐
│ 🥬 KHO RAU THÔ (Bronze Layer)                                    │
│   Rau còn nguyên đất cát, chưa rửa                                │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 🥗 RAU ĐÃ SƠ CHẾ (Silver Layer)                                  │
│   Rửa sạch, cắt bỏ phần héo, phần sâu                            │
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 🍜 BÁT PHỞ HOÀN CHỈNH (Gold Layer)                              │
│   94 gia vị: SMA, RSI, MACD, Bollinger, ...                      │
│   Sẵn sàng dùng cho phân tích, dự báo, backtest                  │
└──────────┬──────────┬─────────────┬──────────────┬───────────────┘
           ▼          ▼             ▼              ▼
   📊 Phở "Phân     🔮 Phở "Dự   🧪 Phở "Backtest"  🤖 Phở "AI"
   tích kỹ thuật"    báo giá"     (Thử nấu mới)
   (SMA, RSI...)     (LSTM...)     (xem có ngon)
```

**Khi khách (người dùng) hỏi:**
- "Tôi muốn xem phở có ngon không?" → Em đưa **bát phở phân tích** (RSI, MACD...).
- "Tôi muốn đoán ngày mai có phở không?" → Em cho **phở dự báo** (mô hình LR/ARIMA/LSTM).
- "Tôi muốn thử nấu theo công thức mới" → Em **backtest** (thử nấu mới 1 công thức trên dữ liệu cũ).
- "Tôi muốn hỏi bằng tiếng Việt" → Em đưa **AI Agent** (trợ lý ảo thông minh).

Em xin trình bày chi tiết từng "khâu nấu phở" qua các chương sau ạ.

---

# 6. TẦNG 1 – "HẠ TẦNG" GIỐNG NHƯ XÂY NHÀ BẾP

## 6.1. Tại sao cần "hạ tầng"?

Kính thưa thầy cô, để nấu phở thì em cần **bếp, nồi, bếp gas, tủ lạnh**. Để em chạy hệ thống Lakehouse, em cũng cần **4 thứ tương tự**:

| Đồ để nấu phở | Đồ để chạy hệ thống | Em dùng cái gì? |
|---|---|---|
| Bếp gas | Máy chủ ảo | **Docker** |
| Nồi | Nơi lưu trữ dữ liệu | **MinIO** |
| Tủ lạnh | Cơ sở dữ liệu metadata | **MySQL** |
| Lò nướng | Truyền tin real-time | **Apache Kafka** |
| Mâm | Catalog quản lý bảng | **Apache Iceberg** |

Tất cả 4 cái này em đóng gói vào **Docker Compose** — gọi là "file cấu hình" để một lệnh duy nhất chạy được cả 4.

## 6.2. Docker là gì? (Giải thích cho người chưa biết)

**Docker** giống như một **chiếc hộp di động** chứa cả một phần mềm + mọi thứ nó cần để chạy.

**Ví dụ đời thường:**
Hồi xưa, khi cài phần mềm trên Windows, thầy cô hay gặp lỗi "phần mềm X cần cài .NET 4.5, phần mềm Y cần .NET 3.5, không chạy cùng nhau được". 

Docker giải quyết bằng cách: **mỗi phần mềm bỏ vào 1 chiếc hộp riêng**, các hộp độc lập nhau. Thầy cô có 10 hộp = 10 phần mềm, không xung đột.

**Compose** là chạy nhiều hộp cùng lúc theo 1 file cấu hình.

## 6.3. 4 "hộp" em dùng

### Hộp 1: **MySQL** (như cuốn sổ cái)
- **Tác dụng**: Ghi chép "ai đã chạy pipeline lúc nào, model nào đã train, backtest nào đã chạy".
- **Ví dụ đời thường**: Giống cuốn **sổ nhật ký** của tiệm phở — ghi ngày nào bán bao nhiêu tô, ai mua.
- **Port (cổng kết nối)**: `3307`.

### Hộp 2: **MinIO** (như nhà kho to)
- **Tác dụng**: Lưu trữ **toàn bộ dữ liệu chứng khoán** (hàng triệu file).
- **Ví dụ đời thường**: Giống **kho hàng** của tiệm phở — chứa tất cả gạo, bánh phở, thịt, rau khô.
- **Port**: `9000` (cho app truy cập), `9001` (cho admin xem giao diện web).
- **Đặc biệt**: Thầy cô có thể mở `http://localhost:9001` trên trình duyệt, đăng nhập `minioadmin` / `minioadmin` → thấy toàn bộ file em đã upload lên.

### Hộp 3: **Apache Iceberg REST** (như cuốn catalog)
- **Tác dụng**: Quản lý "bảng dữ liệu" (table) — biết bảng nào có cột gì, phiên bản nào, dữ liệu từ lúc nào.
- **Ví dụ đời thường**: Giống **bảng kê hàng hóa** trong kho — ghi rõ mỗi mặt hàng có bao nhiêu, phiên bản nào, ai nhập lúc nào.
- **Port**: `8181`.

### Hộp 4: **Apache Kafka** (như hệ thống loa phát thanh nội bộ)
- **Tác dụng**: Truyền **tin nhắn real-time** giữa các phần mềm.
- **Ví dụ đời thường**: Giống **hệ thống PA** trong tiệm — phát thông báo mới cho mọi người nghe.
- **Port**: `9092` và `9094`.

## 6.4. Tại sao em chọn Kafka KRaft (không cần ZooKeeper)?

Kafka cũ có một component phụ tên là **ZooKeeper** (quản lý cụm Kafka). Phi bản mới (≥ 3.3) cho phép **KRaft mode** — bỏ ZooKeeper, đơn giản hơn nhiều. Em chỉ chạy 1 broker Kafka (đồ án) nên KRaft là lựa chọn hợp lý.

## 6.5. Một vài câu hỏi em thường gặp

**❓ Tại sao không dùng Postgres mà dùng MySQL?**

Vì MySQL phổ biến trong doanh nghiệp Việt Nam và dễ cài. Quan trọng hơn: trong đồ án MySQL chỉ lưu "sổ cái", toàn bộ dữ liệu chứng khoán nằm ở MinIO. Đổi Postgres cũng OK.

**❓ Tại sao không dùng Apache Spark?**

Vì Spark cần thêm JVM, thêm memory tuning. Trong phạm vi 1,1 triệu rows, Pandas đủ xử lý mượt. Code của em có sẵn đường Spark, chỉ cần bật env.

---

# 7. TẦNG 2 – DỮ LIỆU CHỨNG KHOÁN ĐƯỢC "NẤU" QUA 3 LỚP NHƯ THẾ NÀO

## 7.1. Ý tưởng Medallion (3 lớp)

Medallion là **một pattern (khuôn mẫu)** thiết kế data lake do công ty Databricks phổ biến hóa. Chia thành 3 lớp:

| Lớp | Tiếng Anh | Vai trò | Ví dụ đời thường |
|---|---|---|---|
| 🥉 **Bronze** | Bronze = đồng | Dữ liệu **thô**, append-only | Kho rau vừa nhập về, còn nguyên đất cát |
| 🥈 **Silver** | Silver = bạc | Dữ liệu **đã sạch**, đã validate | Rau đã rửa, cắt bỏ phần héo |
| 🥇 **Gold** | Gold = vàng | Dữ liệu **business-ready**, đã tính feature | Bát phở hoàn chỉnh sẵn ăn |

## 7.2. Bronze – Kho rau thô

**Mục đích**: Lưu dữ liệu thô y nguyên từ nguồn.

**Cấu trúc (em sẽ giải thích từng cột):**

| Cột | Nghĩa | Ví dụ VCB ngày 15/03/2024 |
|---|---|---|
| `symbol` | Mã cổ phiếu | "VCB" |
| `timestamp` | Ngày giờ xảy ra | 2024-03-15 09:00:00+07:00 |
| `open` | Giá mở cửa | 95.000đ |
| `high` | Giá cao nhất | 96.500đ |
| `low` | Giá thấp nhất | 94.500đ |
| `close` | Giá đóng cửa | 96.000đ |
| `adj_close` | Giá điều chỉnh (sau cổ tức/split) | 96.000đ |
| `volume` | Khối lượng | 1.000.000 |
| `source` | Nguồn (yfinance / SSI / ...) | "ssi_vn" |
| `ingestion_time` | Lúc ghi vào Bronze | 2024-03-16 22:30:00 UTC |

**Đặc tính quan trọng:**

1. **Append-only** (chỉ thêm, không sửa): Khi có dữ liệu mới, em chỉ viết thêm file mới, không bao giờ xóa file cũ. Giống như kho hàng không được phép huỷ hàng — chỉ nhập thêm.

2. **Phân vùng theo `symbol/year/month`** (folder theo mã + năm + tháng):
   ```
   📁 stock-bronze/
       📁 symbol=VCB/
           📁 year=2024/
               📁 month=01/  (tháng 1)
                   📄 part-001.parquet
               📁 month=02/  (tháng 2)
   ```
   Khi em hỏi "giá VCB năm 2024", hệ thống chỉ cần mở 12 folder (12 tháng) thay vì cả triệu file. Nhanh hơn rất nhiều.

3. **Dedup (loại trùng) theo `(symbol, timestamp)`**: Em ingest 2 lần cùng ngày thì chỉ giữ bản mới nhất. Tránh dữ liệu rác.

4. **Lineage (ghi nguồn gốc)**: Mỗi partition có file `_lineage.json` chứa: ingest lúc nào, từ source nào, bao nhiêu record. Giúp truy vết khi có lỗi.

## 7.3. Silver – Rau đã sơ chế

**Mục đích**: Làm sạch dữ liệu, loại bỏ bản ghi lỗi, chuẩn hóa về UTC.

**4 loại lỗi Silver phát hiện:**

1. **Missing** – thiếu dữ liệu (vd: thiếu giá close).
2. **Duplicate** – trùng `(symbol, timestamp)`.
3. **Invalid OHLC** – vi phạm logic giá:
   - `high` phải ≥ `open` và `high` ≥ `close` (giá cao nhất phải cao hơn giá mở và giá đóng).
   - `low` phải ≤ `open` và `low` ≤ `close`.
   - `high` phải ≥ `low` (high cao hơn low là hiển nhiên, nhưng dữ liệu thật đôi khi sai!).
4. **Invalid volume** – `volume < 0` (khối lượng không thể âm).

Bản ghi lỗi không bị "im lặng xóa" — em ghi vào `silver/_errors/errors_{timestamp}.parquet` kèm lý do.

**Ví dụ cụ thể** để thầy cô hiểu:
- Yahoo Finance trả về một row: `{"symbol": "VCB", "open": 95.000, "high": 80.000, "low": 94.500, "close": 96.000}`. 
- Dòng này **vô lý**: `high = 80.000 < open = 95.000`. Giá cao nhất không thể thấp hơn giá mở!
- Silver sẽ **đánh dấu lỗi** và ghi vào `_errors/`. Không để dòng lỗi này đi tiếp sang Gold.

## 7.4. Gold – Bát phở hoàn chỉnh

**Mục đích**: Dữ liệu đã tính **94 chỉ báo kỹ thuật**, sẵn sàng cho phân tích, dự báo, backtest.

Em sẽ giải thích chi tiết các chỉ báo ở chương tiếp theo.

## 7.5. Tại sao cần 3 lớp, không gộp làm 1?

Thầy cô có thể thắc mắc "làm 1 lớp cho gọn". Em xin giải thích:

1. **Replay (chạy lại)**: Nếu phát hiện logic "validate OHLC" sai (vd: em đánh dấu nhầm dòng đúng thành sai), em chỉ rebuild Silver từ Bronze. Không phải ingest lại từ Yahoo/SSI — vừa tốn quota API vừa mất thời gian.

2. **Audit (truy vết)**: Thầy cô muốn xem "dòng OHLCV ngày X của VCB lấy từ nguồn nào, lúc nào" → em truy ngược Bronze dễ dàng.

3. **Schema evolution (thêm trường mới)**: Nếu sau này em thêm trường mới (vd: `spread = high - low`), em tính ở Silver/Gold mà không đụng Bronze.

---

# 8. TẦNG 3 – TÍNH 94 CHỈ BÁO KỸ THUẬT (GIỐNG XEM SỨC KHỎE CỦA CỔ PHIẾU)

Kính thưa thầy cô, chương này em xin giải thích từng chỉ báo kỹ thuật bằng ví dụ đời thường để thầy cô hình dung. **94 chỉ báo** này chia thành 6 nhóm:

## 8.1. Nhóm 1 – "Xu hướng" (Trend)

### SMA – Simple Moving Average (Trung bình động đơn giản)

**Ý tưởng**: Lấy trung bình cộng giá N ngày gần nhất.

**Ví dụ đời thường:**
Thầy cô muốn biết "trung bình cân nặng của em trai 7 tuổi" trong tháng vừa rồi. Thầy cô cân mỗi ngày, cộng 30 lần, chia 30.

SMA cũng vậy: cộng 30 giá đóng cửa liên tiếp, chia 30.

**Công thức**:
```
SMA(N) = (giá_1 + giá_2 + ... + giá_N) / N
```

**Tác dụng**: Làm mượt giá, dễ thấy xu hướng. Nếu giá hôm nay > SMA20 → xu hướng ngắn hạn đang tăng.

### EMA – Exponential Moving Average (Trung bình động có trọng số)

**Khác SMA chỗ nào?**
SMA coi tất cả 30 ngày **quan trọng như nhau**. EMA coi **ngày gần hiện tại quan trọng hơn** ngày cũ.

**Ví dụ đời thường:**
Thầy cô đánh giá "cân nặng em trai có tăng không?". Em sẽ quan tâm ngày gần nhất hơn ngày 30 ngày trước.

**Công thức**:
```
EMA_today = α × giá_today + (1 - α) × EMA_hôm_trước
α = 2 / (N + 1)
```

## 8.2. Nhóm 2 – "Sức mạnh" (Momentum)

### RSI – Relative Strength Index

**Ý tưởng**: Đo **độ mạnh** của trend gần đây. Đặc biệt hiệu quả phát hiện **quá mua / quá bán**.

**Ví dụ đời thường:**
Sau khi ăn no, thầy cô chỉ muốn uống nước, không ăn thêm → đó là "quá no". Thị trường cũng vậy: nếu cổ phiếu tăng 10 ngày liên tiếp → "quá mua", nhiều khả năng sẽ giảm trở lại.

**Quy tắc đọc RSI:**
- RSI > 70 → **quá mua** (overbought), giá có thể sắp giảm.
- RSI < 30 → **quá bán** (oversold), giá có thể sắp tăng.
- RSI ~50 → cân bằng.

**Công thức**:
```
RS = (trung bình tăng) / (trung bình giảm) trong 14 phiên
RSI = 100 - 100 / (1 + RS)
```

### MACD – Moving Average Convergence Divergence

**Ý tưởng**: Phát hiện **điểm giao** giữa hai đường EMA.

**Ví dụ đời thường:**
Thầy cô theo dõi cân nặng em trai hàng tuần. Nếu cân nặng trung bình 1 tuần (EMA ngắn) bắt đầu vượt trung bình 1 tháng (EMA dài) → xu hướng tăng cân đang rõ rệt.

**Tín hiệu giao dịch:**
- MACD cắt lên Signal → **mua** (golden cross).
- MACD cắt xuống Signal → **bán** (death cross).

## 8.3. Nhóm 3 – "Biến động" (Volatility)

### Bollinger Bands (Dải Bollinger)

**Ý tưởng**: Vẽ 3 đường bao quanh SMA20:
- **Đường giữa** = SMA(20)
- **Đường trên** = SMA(20) + 2 × độ lệch chuẩn
- **Đường dưới** = SMA(20) − 2 × độ lệch chuẩn

**Ví dụ đời thường:**
Khi thời tiết "bình thường", nhiệt độ dao động quanh 30°C ± 5°C. Đó là dải Bollinger. Nếu nhiệt đột ngột lên 50°C → "breakout" → thời tiết cực đoan.

**Tín hiệu:**
- Giá chạm dải trên → có thể quá mua.
- Giá chạm dải dưới → có thể quá bán.
- Giá đi ra ngoài dải → biến động cực mạnh.

### ATR – Average True Range

**Ý tưởng**: Đo **khoảng cách trung bình** giữa giá cao và giá thấy trong N phiên.

**Ví dụ đời thường:**
Nếu thầy cô theo dõi cân nặng em trai hàng ngày, có ngày em dao động 0.5kg, có ngày 2kg (bệnh). ATR đo mức "dao động".

**Tác dụng**: ATR càng cao → thị trường càng "gập ghềnh" → rủi ro càng lớn. ATR em dùng để **chỉnh position size** (lệnh càng nhỏ khi ATR càng cao).

## 8.4. Nhóm 4 – "Khối lượng" (Volume)

### OBV – On-Balance Volume

**Ý tưởng**: Cộng dồn volume theo hướng giá. Nếu giá tăng → +volume, giá giảm → −volume.

**Ví dụ đời thường:**
Thầy cô theo dõi lượng nước uống của em: ngày uống nhiều (tăng), ngày uống ít (giảm). OBV giúp thấy dòng tiền đang vào/ra cổ phiếu.

### VWAP – Volume-Weighted Average Price

**Ý tưởng**: Giá trung bình có trọng số theo khối lượng. Đây là "giá thật" mà trader tổ chức thường dùng.

## 8.5. Nhóm 5 – "Xu hướng nâng cao" (Advanced)

### ADX – Average Directional Index

**Ý tưởng**: Đo **độ mạnh** của trend (không phân biệt tăng/giảm).
- ADX > 25 → trend mạnh → chiến lược theo trend hiệu quả.
- ADX < 20 → không có trend (sideway) → chiến lược theo trend KHÔNG hiệu quả.

### Ichimoku (C mây)

**Ý tưởng**: Hệ thống 5 đường của Nhật, giúp xác định trend, hỗ trợ, kháng cự.

**Ví dụ đời thường:**
Giống bản đồ thời tiết với nhiều "đường": đường gió, đường mây, đường áp suất. Ichimoku như vậy — nhiều đường cho trader có cái nhìn toàn cảnh.

### Market Regime

**Ý tưởng**: Phân loại thị trường thành 6 trạng thái:
- **Bull** (tăng) × **Low Vol** (ít biến động)
- **Bull × High Vol**
- **Bear** (giảm) × Low Vol
- **Bear × High Vol**
- **Neutral × Low Vol**
- **Neutral × High Vol**

Em tính regime từ SMA(50) và ATR. Mục đích: cho mô hình ML biết "hiện tại thị trường đang ở regime nào" để dự đoán chính xác hơn.

## 8.6. Nhóm 6 – "Lag" (Đặt trễ) và "Target"

### Lag features
Là các giá trị ngày hôm qua, hôm kia, hôm kìa...
- `close_lag_1` = giá đóng hôm qua.
- `return_lag_1` = return (= % thay đổi) hôm qua.

**Tác dụng**: Cho mô hình ML biết "giá hôm qua thế nào" để dự đoán hôm nay.

### Target (mục tiêu)
- `target_close_next` = giá đóng **ngày mai**.
- `target_return_next` = return ngày mai.
- `target_direction_next` = 1 nếu ngày mai tăng, 0 nếu giảm.

**Quan trọng**: Target tính bằng `shift(-1)` — đẩy lùi 1 ngày. Nghĩa là **mô hình không được nhìn trộm tương lai**. Đây là **nguyên tắc vàng** trong ML tài chính.

## 8.7. Tổng kết 94 chỉ báo

| Nhóm | Số lượng | Ví dụ |
|---|---|---|
| Returns / Price | ~6 | return, log_return, price_change |
| Trend | ~6 | sma_5/10/20/50, ema_12/26 |
| Momentum | ~4 | rsi_14, macd, macd_signal, macd_hist |
| Volatility | ~5 | bb_upper/middle/lower, rolling_std, atr_14 |
| Volume | ~3 | volume_ma_20, obv, vwap |
| Strength | ~6 | adx, supertrend, ichimoku, stoch, mfi, cci, williams_r |
| Lags | ~10 | close_lag_1/2/3/5, return_lag..., volume_lag |
| Macro | ~4 | usd_vnd, gold_usd, oil_usd, regime |
| Composite | ~6 | buy_score, sell_score, candlestick patterns, regime one-hot |
| **Target** | 3 | target_close_next, target_return_next, target_direction_next |
| **Tổng** | **~94** | (lưu trữ ở 1 symbol thật, kiểm chứng được) |

---

# 9. TẦNG 4 – DỰ BÁO GIÁ CỔ PHIẾU BẰNG 3 CÁCH

Kính thưa thầy cô, sau khi có 94 chỉ báo ở Gold, em dùng 3 mô hình để **dự báo giá tương lai**. Em xin giải thích từng mô hình bằng ví dụ đời thường.

## 9.1. Tại sao 3 mô hình?

| Mô hình | Tính cách | Khi nào nên dùng |
|---|---|---|
| **Linear Regression** | Đơn giản, nhanh | Làm baseline (đường cơ sở) |
| **ARIMA** | Cổ điển, ổn định | Khi chuỗi có trend rõ ràng |
| **LSTM** | Phức tạp, mạnh | Khi có nhiều feature phi tuyến |

Em **không khẳng định LSTM tốt nhất** — thực tế ARIMA hoặc Linear Regression đôi khi còn tốt hơn cho dữ liệu ít.

## 9.2. Linear Regression – "Vẽ đường thẳng"

**Ý tưởng**: Tìm một đường thẳng đi qua các điểm dữ liệu, sao cho sai số nhỏ nhất.

**Ví dụ đời thường:**
Thầy cô mua tôm hàng tuần với giá:
- Tuần 1: 100.000đ/kg
- Tuần 2: 110.000đ/kg
- Tuần 3: 105.000đ/kg

Linear Regression sẽ tìm công thức `giá = a × tuần + b` để dự đoán tuần 4.

**Trong đồ án**: 94 features → giá = a₁ × SMA20 + a₂ × RSI + a₃ × MACD + ... + b.

**Công thức tổng quát**:
```
y = w₁ × x₁ + w₂ × x₂ + ... + wₙ × xₙ + b
```
Trong đó y = giá dự báo, x₁...xₙ = features, w₁...wₙ = trọng số, b = hằng số. Mô hình học w và b từ dữ liệu.

## 9.3. ARIMA – "Mô hình cổ điển cho chuỗi thời gian"

**ARIMA** = AutoRegressive Integrated Moving Average. Tên dài nhưng ý tưởng đơn giản:

**Ví dụ đời thường:**
Thầy cô dự đoán thu nhập tháng tới dựa trên:
- Xu hướng (AR = AutoRegressive): thu nhập tháng này thường giống tháng trước.
- Sai phân (I = Integrated): lấy "thu nhập tháng này trừ tháng trước" để chuỗi ổn định hơn.
- Trung bình trượt (MA = Moving Average): thu nhập tháng này chịu ảnh hưởng của các sai số ngẫu nhiên gần đây.

**Công thức (ARIMA(p,d,q))**:
- p = bậc auto-regressive (số lượng lag đầu vào, em dùng 1).
- d = bậc sai phân (em dùng 1).
- q = bậc moving average (em dùng 1).

Em dùng ARIMA(1,1,1) — đơn giản nhất, đủ cho baseline.

## 9.4. LSTM – "Mạng nơ-ron nhớ lâu"

**LSTM = Long Short-Term Memory** = một loại mạng nơ-ron nhân tạo, có khả năng **nhớ lâu**.

**Ví dụ đời thường:**
Thầy cô đọc tiểu thuyết dài 800 trang. Khi đọc đến trang 600, thầy cô vẫn nhớ được trang 50 (nội dung chương 1) → nhân vật chính sinh năm bao nhiêu. Đó là LSTM — **nhớ được context xa**.

Mạng nơ-ron thường (RNN) quên nhanh, LSTM có 3 "cổng" (gate) giúp:
- **Forget gate** (Cổng quên): Quên thông tin cũ không còn hữu ích.
- **Input gate** (Cổng thêm): Thêm thông tin mới.
- **Output gate** (Cổng xuất): Trả ra thông tin.

**Cấu trúc LSTM em dùng:**
```
Input (60 phiên × 94 features) 
   ↓
LSTM Layer 1 (64 units, học pattern ngắn hạn)
   ↓
LSTM Layer 2 (64 units, học pattern dài hạn)
   ↓
Fully Connected Layer
   ↓
Output (giá dự báo ngày mai)
```

**Tại sao có 2 layer?**
Một layer LSTM có thể học pattern "ngày hôm qua giá tăng → hôm nay tăng". Hai layer học được pattern phức tạp hơn: "5 ngày giảm liên tiếp → khả năng cao sẽ tăng".

## 9.5. Quy trình em train LSTM

Bước em làm (em sẽ giải thích đơn giản):

1. **Chuẩn bị data**: Lấy 80% đầu làm **tập train** (dữ liệu để máy học), 20% cuối làm **tập test** (dữ liệu để kiểm tra).
   - **Quan trọng**: chia theo **thứ tự thời gian**, không xáo trộn. Vì xáo trộn → máy "nhìn tương lai khi học quá khứ" → sai.

2. **Chuẩn hóa**: Đưa mọi số về [0, 1] (vì LSTM nhạy với scale lớn). Sau khi dự báo, em chuyển ngược về giá trị thật.

3. **Tạo "cửa sổ trượt"**: Mỗi 60 ngày liên tiếp là một "mẫu", đầu ra là giá ngày thứ 61.

   ```
   Ngày 1-60: input (60 features × 94 chỉ báo)
       ↓
   Ngày 61: output (giá dự báo)
   
   Rồi trượt: Ngày 2-61 input, Ngày 62 output
   Rồi trượt: Ngày 3-62 input, Ngày 63 output
   ...
   ```

4. **Train**: Cho LSTM học từ các mẫu này. Mỗi lần học em gọi là "**epoch**". Em train tối đa 50 epoch.

5. **Early stopping**: Khi LSTM học đến một epoch mà kết quả test không cải thiện nữa → dừng. Tránh "học vẹt".

6. **Lưu lại model tốt nhất**: Trong quá trình train, em theo dõi model tốt nhất (epoch có val_loss nhỏ nhất). Kết thúc train em lưu model đó.

**Kết quả là gì?**: 4 con số em báo cáo — **MAE** (sai số trung bình tuyệt đối), **RMSE** (sai số bình phương căn), **MAPE** (% sai số), **Directional Accuracy** (% lần đoán đúng hướng tăng/giảm).

**Trong 4 con số, con nào quan trọng nhất?**
- **Directional Accuracy** quan trọng nhất cho trading. Em đoán đúng hướng (lên/xuống) 60% → đã tốt hơn tung đồng xu 50%. Em đoán đúng số 99% nhưng sai hướng → vẫn thua lỗ khi vào lệnh.

## 9.6. Em chọn CPU, không dùng GPU

Em cố ý dùng CPU thay vì GPU vì:
- Dataset mỗi mã chỉ ~2500 dòng → CPU train 1 phút là xong.
- GPU cho sinh viên đắt tiền hoặc cần cloud GPU.

Code của em có sẵn cờ chuyển sang GPU: chỉ cần đổi `torch.device("cpu")` thành `torch.device("cuda")` nếu có GPU.

---

# 10. TẦNG 5 – BACKTESTING – "THỬ CHƠI CHỨNG KHOÁN TRÊN GIẤY"

Kính thưa thầy cô, "backtesting" là **chạy thử một chiến lược mua bán trên dữ liệu quá khứ** xem nó "kiếm được bao nhiêu". Em xin giải thích từng bước bằng ví dụ đời thường.

**Ví dụ đời thường:**
Thầy cô chơi cờ tướng. Trước khi đấu giải, thầy cô chơi thử 100 ván với máy tính. Nếu thắng 80%, thầy cô tự tin đấu thật. **Backtest = chơi thử với dữ liệu lịch sử.**

Trong đồ án, em backtest bằng cách giả lập: "Nếu từ 2018 em áp dụng chiến lược MA Crossover, mua/bán theo tín hiệu, có phí giao dịch 0.1%, trượt giá 0.05%, thì đến nay em có bao nhiêu tiền?"

## 10.1. Chiến lược MA Crossover – "Vàng và chết"

**Nguyên tắc**:
- Tính SMA(20) và SMA(50).
- **SMA20 cắt lên SMA50** → MUA (golden cross — "giao điểm vàng").
- **SMA20 cắt xuống SMA50** → BÁN (death cross — "giao điểm chết").

**Ví dụ đời thường:**
Thầy cô nuôi em trai. Thầy cô theo dõi cân nặng trung bình 1 tháng (SMA20) và 3 tháng (SMA50).
- Nếu em tăng cân nhiều trong tháng này (SMA20 cao hơn SMA50) → "em đang phát triển tốt" → giữ chế độ ăn này.
- Nếu em giảm cân → cần thay đổi chế độ ăn.

**Code em viết:**
```python
class MACrossoverStrategy:
    def generate_signals(self, frame):
        sma20 = frame["close"].rolling(20).mean()
        sma50 = frame["close"].rolling(50).mean()
        signal = pd.Series(0, index=frame.index)
        signal[sma20 > sma50] = 1   # long
        signal[sma20 < sma50] = -1  # short
        return signal
```

## 10.2. Chiến lược RSI – "Quá mua quá bán"

**Nguyên tắc**:
- RSI < 30 → quá bán → **mua**.
- RSI > 70 → quá mua → **bán**.

**Ví dụ đời thường:**
Sau Tết, mọi người ăn quá nhiều bánh chưng → "quá no" → 1 tháng sau ít ăn lại → cân bằng. RSI cũng vậy: thị trường tăng quá nhiều → sắp giảm để cân bằng.

## 10.3. Hai quy tắc "thật" em áp dụng

### Quy tắc 1: Next-bar execution (Đặt lệnh ở giá bar tiếp theo)

Thầy cô hỏi: "Tại sao không mua ngay giá đóng cửa hôm nay?"

**Trả lời**: Vì khi tín hiệu xuất hiện (ví dụ cuối giờ chiều), thầy cô không kịp mua giá đóng cửa. Thầy cô phải mua **giá mở cửa ngày mai**. Đây là quy tắc "fair" trong backtest.

**Code:**
```python
signals = strategy.generate_signals(frame)
execution_signal = signals.shift(1).fillna(0)  # ← dòng này cực quan trọng!
```

Dòng `.shift(1)` nghĩa là: tín hiệu hôm nay được thực thi vào **ngày mai**.

### Quy tắc 2: Phí giao dịch + trượt giá

```python
transaction_fee = 0.001   # 0.1% phí
slippage        = 0.0005  # 0.05% trượt giá
```

- **Phí 0.1%**: Khi mua hoặc bán, em trả 0.1% giá trị lệnh.
- **Trượt giá 0.05%**: Lệnh mua của em thực sự khớp ở giá cao hơn giá "kỳ vọng" một chút.

**Tại sao cần có?**
Bỏ qua phí và slippage → kết quả backtest đẹp một cách ảo. Em giữ phí thật để kết quả trung thực.

## 10.4. 6 chỉ số đánh giá backtest

| Chỉ số | Ý nghĩa | Ví dụ đời thường |
|---|---|---|
| **Total Return** | Tổng lãi/lỗ (%) | Sau 5 năm, 10 triệu thành 15 triệu → +50% |
| **Sharpe Ratio** | Lãi / rủi ro | Lãi nhiều nhưng rủi ro cũng nhiều → Sharpe thấp |
| **Max Drawdown** | Sụt giảm tối đa từ đỉnh | Từng mất 30% từ đỉnh → -30% |
| **Win Rate** | Tỷ lệ lệnh thắng | 100 lệnh, 60 thắng → 60% |
| **Profit Factor** | Tổng lãi / tổng lỗ | 1.5 = kiếm 1.5 lần số lỗ |
| **Number of Trades** | Số lệnh | Nhiều lệnh → phí nhiều |

## 10.5. Walk-Forward Validation – "Học từng phần, kiểm tra từng phần"

**Vấn đề của train/test một lần:**
- Chia 80/20 (train 2018–2022, test 2023). Nếu 2023 là downtrend mà 2018–2022 là uptrend → kết quả xấu. Nhưng chiến lược vẫn có thể tốt, em chỉ "xui" thôi.
- Kết quả là 1 con số duy nhất → không có ý nghĩa thống kê.

**Cách Walk-Forward giải quyết:**
```
Fold 1:   [==== Train 6 tháng ====][Test 1 tháng]
Fold 2:   [====== Train 7 tháng ======][Test 1 tháng]
Fold 3:   [======== Train 8 tháng ========][Test 1 tháng]
...
```

Với mỗi fold:
1. Train trên 6 tháng đầu.
2. Test trên 1 tháng tiếp theo.
3. Trượt cửa sổ đi (thêm 20 ngày vào train, test tháng tiếp).
4. Lặp đến hết dữ liệu.
5. **Trung bình** kết quả từ tất cả fold → 1 con số có ý nghĩa.

**Ví dụ đời thường:**
Thầy cô học lái xe. Thay vì học 6 tháng rồi thi 1 lần, thầy cô học 1 tuần → thi thử 1 tiếng → học tiếp 1 tuần → thi thử → ... Walk-Forward cho ra nhiều kết quả thi thử → em biết thầy cô có thật sự giỏi hay chỉ may mắn.

**3 chỉ số quan trọng em báo cáo:**

1. **avg_test_return**: Trung bình return trên các fold test. ≥ 0% là strategy không lỗ.
2. **return_consistency**: Bao nhiêu % fold có test_return > 0. > 70% là ổn định.
3. **overfitting_ratio**: (lãi train) / (lãi test). ≈ 1.0 là tốt, > 2.0 là nghi ngờ overfitting.

---

# 11. TẦNG 6 – AI AGENT – TRỢ LÝ ẢO TRẢ LỜI "KHÔNG BỊA SỐ"

## 11.1. Vấn đề cũ: Chatbot AI hay bịa

Kính thưa thầy cô, em thử hỏi ChatGPT miễn phí: "RSI hiện tại của VCB là bao nhiêu?" → câu trả lời thường là một con số rất "tự tin" nhưng thực ra **không có cơ sở**, vì AI không có dữ liệu real-time.

**Em muốn xây AI khác**: AI chỉ trả lời khi **đã gọi tool lấy data thật**, không bịa.

## 11.2. Ý tưởng "Tool Calling"

**Tool Calling** = AI không tự trả lời, mà **gọi tool** (công cụ) để lấy dữ liệu, rồi tổng hợp.

**Ví dụ đời thường:**
Thầy cô hỏi trợ lý ảo: "Thời tiết hôm nay thế nào?"
- ❌ **Cách cũ (không có tool)**: Trợ lý ảo "đoán": "Hôm nay nắng nhẹ, khoảng 30°C" — nhưng có khi sai.
- ✅ **Cách mới (có tool)**: Trợ lý ảo gọi **công cụ weather API** → lấy nhiệt độ thật từ trạm khí tượng → trả lời: "30.5°C, có mây" — chính xác.

## 11.3. Luồng hoạt động

```
User: "RSI của VCB hiện tại bao nhiêu?"
        ↓
[Agent] nhận câu hỏi
        ↓
[Gemini] phân tích: "Cần gọi tool calculate_indicators(symbol='VCB')"
        ↓
[Backend] Tool thực thi → Tính RSI từ 94 features trong Gold
        ↓
[Gemini] nhận kết quả {rsi: 62.4}
        ↓
[Gemini] tổng hợp: "RSI(VCB) hiện tại = 62.4, gần vùng quá mua, cần thận trọng."
```

## 11.4. 11 tool em đăng ký

| Tên tool | Tác dụng |
|---|---|
| `get_market_summary` | Tổng quan thị trường |
| `query_stock_data` | Lấy OHLCV lịch sử |
| `calculate_indicators` | Tính SMA/EMA/RSI/MACD/Bollinger |
| `forecast_stock` | Dự báo N-day bằng LR/ARIMA/LSTM |
| `compare_models` | So sánh 3 model |
| `run_backtest` | Chạy MA Cross/RSI Strategy |
| `walk_forward` | Walk-forward validation |
| `get_news` | Tin tức |
| `get_company_profile` | Thông tin công ty |
| `get_fundamental_metrics` | P/E, ROE... |
| `get_sentiment_summary` | Sentiment tổng hợp |

## 11.5. Local Router (khi không có Gemini API key)

Nếu không setup Gemini API key, Agent có **Local Router** dự phòng:

**Ví dụ:**
- User gõ: "RSI của VCB bao nhiêu?"
- Local Router quét keyword "rsi" → biết cần gọi tool `calculate_indicators` → gọi tool → trả kết quả.

Local Router vẫn **không bịa** — chỉ khác là không qua LLM sinh câu tự do.

**Tại sao cần Local Router?**
1. Không phải ai cũng có API key.
2. Gemini Free có giới hạn 60 req/phút → demo nhiều người dùng → hết quota.
3. Khi viết test, em cần deterministic (cùng input → cùng output).

## 11.6. Một vấn đề em "vấp" và rút kinh nghiệm

**Vấn đề**: Đôi khi LLM tự "nghĩ ra" mã cổ phiếu từ câu bình thường.

**Ví dụ**:
- User gõ: "Em có con AI này rất thông minh."
- LLM đoán: "AI = ticker AIG" → gọi tool với symbol không tồn tại → lỗi.

**Em sửa**:
- Validate: chỉ chấp nhận ticker thực sự có trong danh sách 917 mã.
- Nếu user không hỏi về tài chính → dùng default symbol từ UI.

## 11.7. Lưu lịch sử chat

Mỗi cuộc hội thoại với Agent được lưu vào MySQL (bảng `agent_conversations`):
- Session ID (UUID).
- User message.
- Assistant response.
- Tool nào đã gọi.
- Input/output của tool.

Thầy cô có thể query lại: "3 tháng trước, Agent trả lời RSI của VCB là bao nhiêu?" → em tra bảng này.

---

# 12. TẦNG 7 – GIAO DIỆN WEB CHO NGƯỜI DÙNG

## 12.1. Frontend là gì? (giải thích cho người mới)

Kính thưa thầy cô, **frontend** là **phần giao diện mà người dùng nhìn thấy trên màn hình**. Khi thầy cô vào Google, gõ chữ "thời tiết Hà Nội", thấy ô tìm kiếm + kết quả + biểu đồ — tất cả là frontend.

Trong đồ án, frontend là **trang web** để người dùng (em hoặc thầy cô) xem:
- Chart (biểu đồ) giá cổ phiếu.
- Bảng số liệu OHLCV.
- Tín hiệu mua/bán.
- Chat với AI Agent.

## 12.2. Stack frontend em dùng (giải thích đơn giản)

| Tên | Tác dụng | Ví dụ đời thường |
|---|---|---|
| **React** | Framework (khung) để xây web | Giống "bộ Lego" để xếp giao diện |
| **Vite** | Build tool (công cụ đóng gói) | Giống "máy đóng gói" thành sản phẩm hoàn chỉnh |
| **TypeScript** | Ngôn ngữ lập trình (mở rộng của JavaScript) | Ngôn ngữ để viết code React |
| **TailwindCSS** | Thư viện CSS (trang trí web) | Bộ "giấy dán" để trang trí đẹp |
| **Recharts** | Thư viện vẽ biểu đồ | Cung cấp biểu đồ đường, cột, tròn |
| **TanStack Query** | Quản lý data fetching | Tự động gọi API + cache + cập nhật |

## 12.3. 7 trang web em có

| Đường dẫn | Tên trang | Chức năng |
|---|---|---|
| `/` | Dashboard | Giá + chỉ báo + chart cho 1 mã |
| `/market` | Market Data | OHLCV chart + bảng |
| `/indicators` | Indicators | Phân tích kỹ thuật |
| `/forecasting` | Forecasting | Train + dự báo 3 model |
| `/backtesting` | Backtesting | MA/RSI strategy + kết quả |
| `/agent` | Agent | Chat với AI Agent |
| `/system` | System Status | Health check tổng |

## 12.4. Cách frontend gọi backend

**Ví dụ đời thường:**
Thầy cô ngồi ở nhà (frontend), muốn gọi điện cho bạn ở công ty (backend). Thầy cô quay số (URL) + nói (request) → backend xử lý → trả lời (response).

**Code:**
```javascript
// Frontend gọi API
fetch("http://localhost:8000/api/v1/stocks/VCB")
  .then(response => response.json())
  .then(data => console.log(data));
```

Câu lệnh này: "Lấy dữ liệu VCB từ backend" → trả về JSON → frontend hiển thị lên chart.

---

# 13. DEMO LUỒNG CHẠY THẬT

Em xin trình bày luồng em đã chạy thực tế.

## 13.1. Bước 1 – Khởi động "nhà bếp"
```powershell
docker compose up -d
docker compose ps
# 4 hộp: mysql, minio, iceberg-rest, kafka → chạy healthy
```

## 13.2. Bước 2 – Khởi tạo sổ cái (database)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\init_database.py
# Tạo database + chạy migrations
```

## 13.3. Bước 3 – Ingest dữ liệu thật
```powershell
python scripts\ingest_historical.py --source multi_source --years 10
# Ingest 917 mã × ~2500 bars = ~2.3M dòng OHLCV
```

## 13.4. Bước 4 – Huấn luyện + backtest
```powershell
python scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm
python scripts\run_backtest.py --symbol AAPL --strategy ma_crossover
python scripts\run_walk_forward.py --symbol AAPL --model lstm --folds 5
```

## 13.5. Bước 5 – Test AI Agent
```powershell
python scripts\run_agent.py --symbol VCB --question "RSI hiện tại bao nhiêu?"
# Agent gọi tool → tính → "RSI(VCB) = 62.4"
```

## 13.6. Bước 6 – Mở web
- Backend: http://127.0.0.1:8000/docs (Swagger UI — tài liệu API tự động).
- Frontend: http://127.0.0.1:5173 (giao diện React).
- MinIO Console: http://localhost:9001 (user/pass: `minioadmin`/`minioadmin`).

---

# 14. KẾT QUẢ THỰC NGHIỆM – "SỨC KHỎE" CỦA HỆ THỐNG

## 14.1. System Health Report

Em chạy file `tests/_system_audit.py` ngày 30/09/2026, kết quả:

| ✅ Pass | ⚠️ Warn | ❌ Fail | Tổng |
|---|---|---|---|
| **28** | 0 | 0 | **28** |

**Ý nghĩa**: 28/28 bài test tự động đều pass → hệ thống "khỏe mạnh".

Các bài test chia nhóm:
- **Storage** (4): MinIO khả dụng, 5 buckets tồn tại.
- **Lakehouse** (3): Bronze 219,958 rows, Silver 193,508 rows, Gold 192,618 rows × 94 columns.
- **Providers** (3): yfinance, SSI, multi-source đều hoạt động.
- **API** (10): Test 10 endpoint GET/POST trả 200 + đủ key.
- **Streaming** (2): Kafka producer gửi được, consumer nhận được.
- **TCP** (5): MinIO API/Console, Kafka internal/external, Kafka UI đều mở được.
- **Docker** (1): 8 container stock-lakehouse đang chạy.

## 14.2. Universe & Coverage (cập nhật 06/10/2026)

| Khu vực | Số mã | Ví dụ |
|---|---|---|
| 🇺🇸 Mỹ | ~300 | AAPL, MSFT, NVDA |
| 🇪🇺 Châu Âu | ~95 | SAP.DE, MC.PA, SHEL.L |
| 🇯🇵 Nhật | ~40 | 7203.T, 6758.T |
| 🇭🇰 Hồng Kông | ~20 | 0700.HK, 9988.HK |
| 🇨🇳 Trung Quốc (ADR) | ~22 | BABA, JD, PDD |
| 🇰🇷 Hàn Quốc | ~20 | 005930.KS |
| 🇹🇼 Đài Loan | ~20 | 2330.TW |
| 🇮🇳 Ấn Độ | ~8 | INFY, IBN |
| 🇧🇷 Brazil | ~10 | VALE, ITUB |
| 🇨🇦 Canada | ~19 | SHOP, RY.TO |
| 🇦🇺 Úc | ~20 | BHP.AX, CBA.AX |
| 🇻🇳 Việt Nam | ~50 | VCB, FPT, HPG |
| ETF (quỹ chỉ số) | ~85 | XLK, GLD, TLT |
| **Tổng** | **958** | trong đó 917 mã đã ingest thật |

**Tổng dữ liệu**: ~1,1 triệu dòng OHLCV × 3 tầng = ~3,3 triệu file Parquet trên MinIO.

---

# 15. HẠN CHẾ & PHẠM VI GIỚI HẠN – EM THÀNH THẬT VỚI THẦY CÔ

Kính thưa thầy cô, em xin nói thật các hạn chế em biết.

## 15.1. Hạn chế về dữ liệu

1. **Chỉ daily OHLCV** + một số intraday. Chưa xử lý tick-level. Nếu muốn high-frequency trading thì project này không phù hợp.

2. **5–10 năm lịch sử** chưa đủ cho regime dài hạn. Một số mã delisted hoặc rename trong 5–10 năm, em loại bỏ (~40 ticker).

3. **VN stocks**: dữ liệu thiếu một số ngày (gãy lịch). Em có báo cáo `vn_data_quality.md` ghi chi tiết.

## 15.2. Hạn chế về mô hình

1. **3 model chưa phải state-of-the-art.** So với Transformer (Informer, Autoformer), LSTM là baseline. Nhưng với dữ liệu ~2500 dòng/symbol, Transformer dễ overfit.

2. **Không có feature selection hay hyperparameter tuning tự động.** Em set tham số cố định. Nếu có thời gian em sẽ dùng Optuna.

3. **MA Cross và RSI là strategies cơ bản.** Không có position sizing, không có risk management nâng cao.

## 15.3. Hạn chế về hạ tầng

1. **Chạy 1 broker Kafka** – chưa phân tán nhiều node. Cho đồ án đủ, cho production thì chưa.

2. **Pandas thay vì Spark.** 1,1M rows OK nhưng nếu lên 100M rows thì cần Spark. Code đã có sẵn đường Spark.

3. **Single-node Docker** – không có Kubernetes, không auto-scaling.

## 15.4. Hạn chế về AI Agent

1. **Tool calling chỉ 11 tool.** Chưa pluggable (mỗi tool mới phải đăng ký thủ công).

2. **Gemini Free 60 req/phút** có thể hết quota khi demo liên tục. Đã có Local Router fallback.

3. **Chưa có eval benchmark chuẩn** cho Agent. Em đánh giá bằng test cases thủ công.

## 15.5. Em tự đánh giá

Nếu thầy cô hỏi "1–10 em cho đồ án mấy điểm", em sẽ nói:
- Về **kiến trúc & code**: 8/10 — clean, có test, có docs.
- Về **giá trị nghiên cứu**: 7/10 — pipeline thật, data thật, nhưng chưa phát hiện insight mới.
- Về **sản phẩm**: 6/10 — chạy ổn nhưng còn nhiều feature để thêm.

---

# 16. ĐÓNG GÓP MỚI & HƯỚNG PHÁT TRIỂN

## 16.1. 5 đóng góp mới của đồ án

Nếu thầy cô hỏi "đồ án này có gì mới so với các đồ án cũ?", em xin nêu 5 điểm:

1. **Lakehouse đa tầng cho chứng khoán thật**, không phải demo data.
2. **Storage abstraction** (MinIO + Local fallback) – không mất data khi MinIO chết.
3. **94 features** comprehensive, **không look-ahead** (không nhìn trộm tương lai).
4. **Walk-forward validation thật sự robust** – không chỉ train/test 1 lần.
5. **AI Agent với tool-calling** – không bịa số.

## 16.2. 9 hướng phát triển

1. Chuyển sang **Spark thật** khi data >10M rows.
2. Tách riêng **Feature Store** (kiểu Feast).
3. **Hyperparameter tuning** tự động với Optuna.
4. **Model Registry** tốt hơn (MLflow thay vì filesystem).
5. Thêm data source: **TCBS, vnstock, FRED** cho macro.
6. **Streaming real-time 24/7** qua Finnhub WebSocket.
7. **Risk management** (Kelly, VaR, stop-loss tự động).
8. **Multi-user auth** với JWT.
9. **Cloud deployment** (AWS, GCP).

---

# 17. 🌟 25 CÂU HỎI HỘI ĐỒNG + CÂU TRẢ LỜI CỦA EM

> Em tự đặt câu hỏi như thầy cô có thể hỏi rồi tự trả lời bằng ngôn ngữ đời thường nhất có thể ạ.

---

### Câu 1: "Lakehouse khác gì Data Warehouse?"

> Data Warehouse như ngăn tủ có nhãn — biết rõ hộp nào ở đâu, nhưng tốn tiền cho big data, không linh hoạt cho dữ liệu thô.
>
> Data Lake như bãi đỗ xe rộng — rẻ, chứa nhiều, nhưng dễ "đầm lầy hóa" (không biết xe nào của ai).
>
> Lakehouse = "bãi đỗ xe có camera AI nhận diện biển số". Rẻ + có tổ chức + ACID (đảm bảo không mất dữ liệu).

---

### Câu 2: "Sao không gộp 3 lớp Bronze–Silver–Gold làm 1?"

> Tách 3 lớp giúp em 3 điều:
> - **Replay** – sai logic ở Silver thì rebuild từ Bronze, không phải ingest lại (mất thời gian + quota API).
> - **Audit** – truy vết mọi dòng dữ liệu.
> - **Schema evolution** – thêm trường mới ở Gold, không đụng Bronze.

---

### Câu 3: "MinIO là gì, sao không dùng OneDrive?"

> MinIO giống **Google Drive phiên bản nội bộ dành cho máy chủ** — lưu file, ai cũng truy cập được qua API.
>
> OneDrive dành cho người dùng cuối, không tối ưu cho máy chủ truy cập 10 triệu file.
>
> MinIO miễn phí, chạy local, **tương thích 100% API Amazon S3** (nếu sau này em deploy lên cloud chỉ cần đổi endpoint).

---

### Câu 4: "Tại sao dùng Pandas thay vì Spark?"

> Pandas = cái chảo nhỏ trong bếp, nấu được vài phần cơm.
> Spark = hệ thống 100 bếp chạy song song.
>
> Em có 1,1 triệu rows → Pandas (1 chảo) nấu thoải mái. RAM 16GB dư sức.
>
> Nếu data lên 100M rows → em chuyển sang Spark. Code đã có sẵn đường `_transform_spark()`.

---

### Câu 5: "Docker có phải là ảo hóa không?"

> **Docker ≠ ảo hóa (virtual machine).**
>
> Ảo hóa chạy cả một OS riêng (1-2 GB RAM mỗi cái). Docker chạy process, chia sẻ kernel OS (vài MB).
>
> Docker nhẹ, khởi động trong 1 giây, dễ quản lý bằng Compose. Phù hợp đồ án sinh viên.

---

### Câu 6: "LSTM có thật sự tốt cho chứng khoán không?"

> **Em xin trả lời thật: không phải lúc nào cũng tốt.**
>
> Nghiên cứu gần đây cho thấy ARIMA, Random Forest đôi khi đánh bại LSTM trên dữ liệu tài chính, đặc biệt khi dữ liệu ít.
>
> Em giữ cả 3 model để so sánh công bằng. **Kết quả do data quyết định**, em không khẳng định trước LSTM là tốt nhất.

---

### Câu 7: "Walk-forward validation là gì, tại sao quan trọng?"

> **Ví dụ đời thường:**
>
> Thầy cô học tiếng Anh. Cách A: học 6 tháng → thi 1 lần cuối khóa.
> Cách B: học 1 tháng → kiểm tra 1 tiếng → học tiếp → kiểm tra... (lặp lại nhiều lần).
>
> Cách B cho kết quả đáng tin hơn vì có nhiều lần kiểm tra, tránh "may mắn" 1 lần.
>
> Walk-forward là "Cách B" cho mô hình ML: nhiều fold train/test → trung bình kết quả.

---

### Câu 8: "Tại sao AI Agent phải gọi tool thật thay vì dùng 'kiến thức' của nó?"

> LLM (Gemini, ChatGPT...) học từ dữ liệu tĩnh, không real-time. Hỏi "RSI hiện tại của VCB?" → LLM **đoán** → sai.
>
> Em bắt buộc AI gọi **tool** (API). Tool lấy data thật từ Gold layer. Câu trả lời cuối cùng là Gemini tổng hợp từ data thật, có error handling rõ ràng.

---

### Câu 9: "Nếu user prompt injection (ép AI nói RSI = 100) thì sao?"

> Prompt injection là vấn đề chung của LLM-based system, em chưa giải quyết triệt để.
>
> Em giảm thiểu bằng:
> 1. System prompt rõ ràng ("không bịa số").
> 2. Tool có schema cứng, LLM chỉ chọn trong đó.
> 3. Backend có ground truth ở Gold. Thầy cô có thể audit bằng cách so sánh câu Agent trả lời với `calculate_indicators(symbol).rsi` thật.

---

### Câu 10: "Cổ phiếu VN lấy từ SSI có đáng tin không?"

> SSI là công ty chứng khoán lớn nhất VN, iBoard là sản phẩm public data của họ. Dữ liệu gần như khớp với HOSE/HNX/UPCOM.
>
> Em đã kiểm tra chất lượng trong `vn_data_quality.md`: 53/53 mã có ≥ 5 năm daily. Một số mã mới niêm yết (VTP, TPB) chỉ 2–3 năm.

---

### Câu 11: "Phí giao dịch 0.1% và slippage 0.05% em lấy từ đâu?"

> **Phí 0.1%**: Phí tại VN là ~0.15-0.3% mỗi lệnh (mua+bán). Em chọn 0.1% mỗi chiều, 0.2% round-trip — gần với thực tế.
>
> **Slippage 0.05%**: Trượt giá do khớp lệnh xa giá kỳ vọng. Với daily bar + cổ phiếu thanh khoản cao (AAPL, VCB) → slippage < 0.05% là hợp lý.
>
> Em **cố ý giữ phí hơi cao** để backtest không over-estimate lợi nhuận.

---

### Câu 12: "Nếu cổ phiếu delisted/reverse-split thì sao?"

> Bronze giữ raw data → có thể audit.
>
> Silver validate OHLC: nếu sau reverse-split giá tăng gấp 10 lần, OHLC vẫn valid → không phát hiện được đây là split event.
>
> Đây là **hạn chế em biết**, em để dành phát triển tiếp (thêm bảng split events merge theo ex-date).

---

### Câu 13: "Gemini Free 60 req/phút có đủ không? Production thì sao?"

> Gemini Free đủ cho demo, không đủ cho production.
>
> Production nên:
> 1. **Cache** kết quả tool (cùng `(symbol, indicator)` không cần tính lại).
> 2. Dùng **Gemini Batch API** nếu có.
> 3. **Self-hosted LLM** (Llama, Mistral). Code em đã có interface `LLMClient`, chỉ cần implement.
>
> Em không dùng self-hosted vì laptop em không có GPU đủ mạnh.

---

### Câu 14: "Đồ án này mở rộng cho crypto được không?"

> **Được.** Hiện đã có BTC-USD, ETH-USD trong danh sách.
>
> Khác biệt:
> - Crypto trade 24/7 → daily bar tính theo UTC 00:00.
> - Crypto nhiều sàn → cần aggregate từ Binance, Coinbase, Kraken.
>
> Em để dành: tích hợp CCXT (thư viện hỗ trợ 100+ sàn) trong tương lai.

---

### Câu 15: "Có thể deploy lên cloud không?"

> **Có.** Code đã có Dockerfile multi-stage.
>
> - **AWS**: ECS Fargate (backend), S3 (thay MinIO), RDS (MySQL), MSK (Kafka).
> - **GCP**: Cloud Run, Cloud Storage.
> - **Local**: Docker Compose (như hiện tại, 0đ).
>
> Em chọn local dev vì đồ án sinh viên budget = 0, và reviewer có thể chạy lại trên máy mình (reproducible).

---

### Câu 16: "Sao em dùng batch mà không dùng Kafka?"

> Em dùng cả hai:
> - **Batch** (script) cho dữ liệu lịch sử 5-10 năm (chạy 1 lần, xong thì ổn định).
> - **Streaming** (Kafka + Finnhub WebSocket) cho dữ liệu real-time (dashboard cập nhật liên tục).
>
> Hai mode phục vụ hai mục đích khác nhau.

---

### Câu 17: "Em test code kiểu gì?"

> Em có pytest tests ở `backend/tests/`.
>
> - Test cho từng hàm indicator (RSI có tính đúng không, MACD có sign đúng không).
> - Test cho Iceberg manager.
> - Test cho backtest engine (kết quả có deterministic không).
>
> Chưa có 100% coverage, chỉ test các hàm quan trọng.

---

### Câu 18: "Restart giữa chừng có mất data không?"

> **Không.** Mọi data nằm ở MinIO, MySQL, Iceberg. Restart container chỉ stop process, data vẫn còn do **named volumes**.
>
> `docker compose down` KHÔNG xóa volume, chỉ `down -v` mới xóa (cẩn thận).

---

### Câu 19: "Tại sao partition theo symbol/year/month?"

> Vì 90% query là "lấy dữ liệu của 1 mã trong 1 khoảng thời gian".
>
> Partition `symbol=VCB/year=2024/*` → Iceberg/MinIO chỉ quét 12 folder (12 tháng) thay vì cả triệu file. Benchmark: nhanh gấp ~50 lần.

---

### Câu 20: "Em có so sánh 3 model không?"

> **Có.** Endpoint `GET /api/v1/forecast/compare/{symbol}` và tool `compare_models` trả về MAE/RMSE/MAPE/Directional Accuracy của cả 3 model. Tab "Compare" trên UI hiển thị kết quả.

---

### Câu 21: "Bootstrap chạy nhiều lần có lỗi không?"

> **Không.** Em thiết kế idempotent (chạy nhiều lần cho cùng kết quả):
> - Tạo bucket: check tồn tại trước khi tạo.
> - Kafka topic: Kafka tự ignore nếu topic đã có.
> - `init_database.py`: check DB tồn tại trước khi migrate.

---

### Câu 22: "Làm sao em đảm bảo code chạy trên Windows + Mac + Linux?"

> Python 3.11 portable. Docker Compose chạy được trên cả 3 OS.
>
> Em dùng `py -3.11` trong PowerShell (Windows), `python3.11` trên Mac/Linux. Path trong `.env` là relative, không hard-code `C:\` hay `/home/`.

---

### Câu 23: "Em mất bao lâu để hoàn thành?"

> Tổng cộng ~4 tháng:
> - Tháng 1: Học Lakehouse theory (Iceberg, Delta, Hudi).
> - Tháng 2: Docker, ingest, pipeline Bronze-Silver-Gold.
> - Tháng 3: ML models, backtest, walk-forward.
> - Tháng 4: AI Agent, frontend, viết docs, test.

---

### Câu 24: "Tài liệu tham khảo?"

> Chính:
> - Apache Iceberg documentation
> - Databricks Medallion Architecture whitepaper
> - yfinance, Finnhub, Alpha Vantage API docs
> - PyTorch LSTM tutorial, scikit-learn docs
> - Gemini function-calling guide
>
> Phụ:
> - "Advances in Financial Machine Learning" – Marcos López de Prado
> - "Evidence-Based Technical Analysis" – David Aronson
> - Paper về LSTM for stock prediction (Fischer & Krauss, 2018)

---

### Câu 25: "Em tâm đắc nhất điều gì?"

> **"Không bịa số"** – nghe đơn giản nhưng rất khó.
>
> Khi làm AI/tài chính, rất dễ mượn "kiến thức nền" của LLM để trả lời. Em muốn hệ thống mình xây **chỉ trả lời khi có data thật, hoặc thà nói "không biết"**.
>
> Khi em chạy `python scripts/run_agent.py --symbol VCB --question "RSI hiện tại bao nhiêu?"` → nhận được con số 62.4 từ tool `calculate_indicators` chạy qua 94 features ở Gold, đi qua Silver đã validate, đến Bronze từ SSI – **đó là cảm giác "đồ án mình chạy thật" mà em tự hào nhất**.

---

# 18. LỜI CẢM ƠN & KẾT THÚC

Kính thưa thầy cô, trên đây là toàn bộ bài thuyết trình khóa luận tốt nghiệp của em.

Em xin tóm tắt bằng một câu: **em đã xây dựng một nền tảng Data Lakehouse end-to-end cho dữ liệu chứng khoán, từ ingest đa nguồn → Medallion Bronze-Silver-Gold → 94 features không look-ahead → 3 mô hình forecast (LR/ARIMA/LSTM) → backtest engine tự viết với walk-forward validation → AI Agent tool-calling đảm bảo không bịa số, tất cả chạy trên Docker Compose với 0 đồng chi phí hạ tầng**.

Em xin nhấn mạnh lại: **đây là prototype nghiên cứu học thuật** – không giao dịch thật, không đặt lệnh, không cam kết lợi nhuận, không khẳng định LSTM là tốt nhất, backtest chỉ đánh giá hiệu suất lịch sử.

Em xin chân thành cảm ơn:
- **Thầy/cô hướng dẫn** đã chỉ bảo em suốt quá trình.
- **Hội đồng bảo vệ** đã dành thời gian đọc báo cáo và nghe em trình bày.
- **Các bạn cùng lớp** đã góp ý và review code.
- **Gia đình** đã hỗ trợ em trong suốt thời gian qua.

Em xin hết bài thuyết trình. Em sẵn sàng trả lời các câu hỏi của thầy cô ạ. 🙏

---

# PHỤ LỤC A – BẢNG LỆNH THƯỜNG DÙNG

| Mục đích | Lệnh |
|---|---|
| Khởi động hạ tầng | `docker compose up -d` |
| Khởi tạo database | `python scripts\init_database.py` |
| Bootstrap MinIO + Kafka | `python scripts\bootstrap_infrastructure.py` |
| Ingest 917 mã | `python scripts\ingest_historical.py --source multi_source --years 10` |
| Ingest cổ phiếu VN | `python scripts\ingest_vn.py --years 10` |
| Pipeline 1 mã | `python scripts\run_pipeline.py --symbol VCB` |
| Train 3 model | `python scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm` |
| Backtest MA Cross | `python scripts\run_backtest.py --symbol AAPL --strategy ma_crossover` |
| Walk-forward 5 folds | `python scripts\run_walk_forward.py --symbol AAPL --model lstm --folds 5` |
| Test Agent headless | `python scripts\run_agent.py --symbol VCB --question "RSI hiện tại bao nhiêu?"` |
| Chạy backend | `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` |
| Chạy frontend | `cd frontend && npm run dev` |

---

# PHỤ LỤC B – URL TRUY CẬP NHANH

| Dịch vụ | URL | Tài khoản |
|---|---|---|
| Frontend (web app) | http://127.0.0.1:5173 | - |
| Backend Swagger UI | http://127.0.0.1:8000/docs | - |
| Backend Health check | http://127.0.0.1:8000/api/v1/health | - |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Iceberg REST catalog | http://localhost:8181/v1/config | - |

---

> **Ghi chú cuối file:** Mọi con số trong bài em lấy từ `docs/system_health.md` (audit 30/09/2026) và `docs/lakehouse.md` (Universe 06/10/2026). Code Python em trích dẫn đã đọc từ repo `stock-lakehouse-ai`. Khi thuyết trình em sẽ không đọc từng câu mà nói tự nhiên, dùng slide song song để thầy cô theo dõi trực quan.
