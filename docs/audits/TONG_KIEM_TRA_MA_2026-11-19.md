# Kiểm tra toàn bộ mã ngày 19/11/2026

**Chưa đủ cơ sở kết luận tất cả mã đều hoạt động ổn ở mọi chức năng.** Giá và lịch sử có thể đọc được trong khi dữ liệu đã cũ, thiếu mô hình, thiếu số phiên cho backtest hoặc chưa được xác minh với nhà cung cấp.

Các số đo dưới đây có mốc thời gian và phạm vi riêng. Không cộng số lần chạy thành số mã duy nhất. Lượt kiểm tra này giữ nguyên các thay đổi đã có trong workspace.

## Dự báo và độ mới dữ liệu

Lượt quét GET toàn bộ API lúc **16:28–16:41 ngày 19/11/2026, giờ Việt Nam**, trước lần khởi động lại backend và lượt refresh tiếp theo:

| Hạng mục | Kết quả |
| --- | --- |
| Mã lịch sử duy nhất API liệt kê | 1.002 |
| Giá gần nhất đọc được từ Gold | 1.002/1.002 |
| Yêu cầu HTTP kiểm tra | 2.151; không lỗi HTTP hoặc kết nối trong lượt này |
| Linear Regression | 871 khả dụng; 131 chưa khả dụng |
| ARIMA | 47 khả dụng; 27 chưa khả dụng trong 74 mã có registry |
| LSTM | 45 khả dụng; 28 chưa khả dụng trong 73 mã có registry |
| Thời gian đáp ứng | Trung vị 0,500 giây; p95 3,563 giây |

ARIMA/LSTM không có model trên toàn bộ 1.002 mã. “Khả dụng” nghĩa có thể trả điểm dự báo tương lai qua kiểm tra hiện tại; không chứng minh độ chính xác hoặc khả năng sinh lời.

131 trường hợp LR chưa khả dụng gồm **99 đầu vào trễ phiên, 28 thiếu model, 4 bị chặn bởi kiểm tra chất lượng**. Bốn mã cần điều tra gián đoạn thang giá là **MRNA, PARA, ACH, EMBJ**. Chưa xác minh nguyên nhân là chia/tách cổ phiếu, đổi đơn vị của nguồn hay biến động thật; giữ nguyên bộ chặn và không sửa giá để làm dự báo chạy.

28 mã thiếu LR: `AVB EA EQR AKRO ALXN ATSG BK BLUE CCRN CHK CMA CPRX CTRA DAWN DENN EXPR FOLD HAB HOLX IPG KLG LTHM PEAK PGRE PLL TCO TGNA WBA`.

Ngày quan sát mới nhất phân bố: 770 mã ngày 18/11, 195 mã ngày 19/11, 37 mã cũ hơn. Cần đối chiếu lịch giao dịch của từng thị trường; không thể suy ra mọi hàng ngày 18/11 đều trễ hoặc mọi hàng ngày 19/11 đều đã đóng phiên.

Chi tiết: [toàn bộ phản hồi dự báo](universe_current_2026-11-19.json), [các khoảng trống theo mã và model](current_forecast_gaps_2026-11-19.json).

## Lịch sử, backtest và agent trên dữ liệu thật

Lượt quét đã hoàn tất **1.002/1.002 mã**. Kết quả ở [symbol_capabilities_2026-11-19.json](symbol_capabilities_2026-11-19.json):

| Hạng mục | Kết quả |
| --- | --- |
| Lịch sử đọc được, đạt kiểm tra cấu trúc OHLCV/timestamp/symbol | 1.002/1.002 |
| Lịch sử bị cắt bởi giới hạn API 5.000 hàng | 0 |
| MA Crossover chạy được, đạt kiểm tra nhất quán kết quả | 996/1.002 |
| RSI chạy được, đạt kiểm tra nhất quán kết quả | 996/1.002 |
| Agent offline gọi công cụ kỹ thuật đúng mã, không lỗi tool | 1.002/1.002; không yêu cầu mọi chỉ báo đều có giá trị |
| Agent offline chạy backtest MA/RSI | 996/1.002 cho mỗi chiến lược |
| Định tuyến năm dạng câu hỏi/mã | Không ghi nhận sai mã |

[Bảng CSV theo từng mã](symbol_status_matrix_2026-11-19.csv) ghép kết quả dự báo và lịch sử/backtest với các mốc quét khác nhau nêu trong báo cáo.

Script đọc lịch sử thực tế của mỗi mã qua API, kiểm tra OHLC dương/hữu hạn và quan hệ high/low, volume hợp lệ, timestamp hợp lệ/sắp xếp/không trùng, và đúng symbol. Sau đó chạy engine MA Crossover và RSI, kiểm tra tính hữu hạn và nhất quán của vốn/equity/metrics.

Agent offline thực sự chạy công cụ kỹ thuật và hai đường backtest trên cùng các hàng API. Chỉ adapter đọc và lưu được thay trong tiến trình audit để không ghi hàng nghìn backtest vào ứng dụng. Kết quả backtest đã tính được tái sử dụng trong đường agent; đây không phải kiểm thử độc lập lần hai của engine. Kiểm tra định tuyến thêm năm dạng câu hỏi cho từng mã.

**Sáu mã thiếu tối thiểu 60 hàng để chạy hai chiến lược: AVB (1), EA (1), EQR (1), BK (5), KLG (4), PEAK (2)**. Công cụ kỹ thuật có thể trả thành công với chỉ báo `null`; không diễn giải điều này thành đủ lịch sử để phân tích kỹ thuật đầy đủ.

Các kiểm tra trên không chứng minh mọi câu hỏi tự nhiên hoặc mọi lần gọi LLM đều đúng. [Smoke test HTTP agent cuối](agent_live_smoke_final_2026-11-19.json) kiểm tra một số tình huống cụ thể bằng dịch vụ thật. Bài kiểm tra AVB đạt khi agent trả đúng lỗi thiếu lịch sử, không phải khi backtest thành công. [Lượt HTTP trước bản sửa cuối](agent_live_smoke_fixed_2026-11-19.json) được giữ để xem tình huống BK chưa gọi công cụ.

Lượt cuối chạy trên API kiểm thử cổng 8001 lúc **17:04–17:05**: **4/4 đạt**, gồm WBA (10,27 giây), BK (10,69 giây), lỗi backtest AVB (39,28 giây), walk-forward RSI AAPL (14,97 giây). Chỉ chứng nhận bốn yêu cầu này; không phải tải đồng thời hoặc toàn bộ câu hỏi LLM trên 1.002 mã.

## Chất lượng nguồn và hiệu quả chiến lược

Snapshot quality gate đang lưu được chạy lúc **18:35 ngày 18/11/2026**, kết luận `warning`. Không gọi snapshot này là xác minh nguồn mới của ngày 19/11:

- Integrity và so khớp layer: 1.002 mã đạt; so 66.038 phiên trong 30 ngày.
- Freshness: 34 mã bị cảnh báo theo ngưỡng cũ hơn 10 ngày so với phiên mới nhất của lakehouse.
- Bronze có 1.242 phiên từng chụp giữa phiên trên 782 mã; cần phân biệt ảnh chụp chưa đóng phiên với giá đóng cửa chính thức.
- Đối chiếu provider chỉ bao gồm 1.170 phiên: 1.167 khớp, 3 phiên cũ, 1 lỗi provider. Không xác minh độc lập đầy đủ mọi phiên của mọi mã.

Hai báo cáo walk-forward có sẵn bao phủ **102 mã, 14 nhóm thị trường**, mỗi chiến lược có 3.724 cửa sổ so cặp. Đây chưa phải walk-forward toàn bộ 1.002 mã. Tỷ lệ mã có lợi nhuận trung bình cao hơn buy-and-hold chỉ khoảng **9,80% với MA**, **14,71% với RSI** trong mẫu này. Không suy rộng thành chiến lược tốt cho mọi mã.

Nguồn: [snapshot chất lượng và walk-forward](symbol_system_snapshot_2026-11-19.json).

## Vấn đề định danh và các bản sửa

- Nhận diện đúng ticker bắt đầu bằng `^`, tránh lấy một phần của `BRK.B` hoặc `BTC-USD` làm mã khác.
- Cụm chiến lược “MA Crossover” không bị nhận thành Mastercard, làm đổi mã A/F/V được hỏi.
- Agent nhận diện thêm mã thực sự có trong lakehouse ngoài danh sách cấu hình, như WBA/BK; chúng có cùng ưu tiên với mã cấu hình khi so khớp.
- Công cụ market summary có schema symbol, và khi LLM bỏ symbol thì dùng mã được hỏi thay vì mã AAPL đang chọn trên UI. Không tự thêm symbol vào tool hệ thống không nhận tham số đó.
- Khi LLM không gọi công cụ cho câu hỏi tài chính, chuyển sang router công cụ để kiểm chứng dữ liệu; không tự kết luận mã lưu trữ là không tồn tại.
- Agent dự báo chỉ lấy điểm tương lai khi `forecast_available=true`; không dùng điểm fitted trong lịch sử như một dự báo mới.
- Agent giữ lỗi công cụ trong trace; backtest lỗi không bị diễn giải thành lợi nhuận 0%. Walk-forward offline gọi đúng bộ kiểm định.
- Số đếm mã cấu hình của agent loại trùng, phân biệt cấu hình với độ phủ dữ liệu/dự báo.
- Thêm `^GSPC`, `^DJI`, `^IXIC` vào refresh mặc định: **979 mã cấu hình duy nhất**, thay vì 976. Ba chỉ số vẫn trả **404 ở đường đọc lakehouse lúc kiểm tra khoảng 16:57**; sửa danh sách chưa chứng minh đã nạp dữ liệu.
- Sửa tiền tệ bare ticker **FRT/NET/DBC thành USD**, khớp công cụ Mỹ mà provider và dữ liệu đang phục vụ; HDB vẫn VND, `FRT.VN` vẫn VND ở hàm xác định tiền tệ. Việc nhận tiền tệ cho hậu tố không có nghĩa đã nạp công cụ đó.

**Giới hạn định danh còn tồn tại:** FRT/NET/DBC/HDB xuất hiện ở cả danh sách quốc tế và Việt Nam nhưng khóa bare ticker chỉ lưu được một công cụ. Cần chuẩn hóa khóa theo thị trường để theo dõi cả hai công cụ cùng tên; đổi nhãn tiền tệ không giải quyết đầy đủ vấn đề này. Lượt này không tự di chuyển lịch sử hoặc tạo model cho mã đã ngừng giao dịch/đổi tên.

26 mã API ngoài cấu hình: `AKRO ALXN ATSG BK BLUE CCRN CHK CMA CPRX CTRA DAWN DENN EXPR FOLD HOLX IPG KLG LTHM PEAK PGRE PLL SOFI TCO TGNA WBA WBD`. Các mã lịch sử này không tự động trở thành mã cần refresh như cổ phiếu đang niêm yết.

## Kiểm thử, vận hành và giới hạn

- Toàn bộ backend sau các sửa chính: **1.658 passed, 22 skipped, 4 cảnh báo thư viện**, 323,47 giây. Bộ hồi quy agent sau bản bổ sung cuối: **999 passed**, 46,94 giây. Hai lượt có bài trùng, không cộng chúng thành số bài độc lập.
- Frontend TypeScript/Vite production build thành công sau sửa tiền tệ.
- Ruff kiểm tra tên biến chưa khai báo/tham chiếu trước gán đạt. `git diff --check` đạt; không coi cảnh báo CRLF là lỗi kiểm tra.
- Trong lượt quét lịch sử có giai đoạn API 8000 không phản hồi; đã khởi động lại và retry các yêu cầu timeout. Chưa xác định nguyên nhân, chưa có cơ sở cam kết độ ổn định dài hạn.
- API kiểm thử sandbox không kết nối được MySQL/MinIO/LLM; các kết quả thất bại do môi trường được giữ riêng ở [artifact sandbox](agent_smoke_sandbox_blocked_2026-11-19.json). Không tính chúng là kiểm chứng đạt hoặc tự kết luận là lỗi dữ liệu.
- Lượt refresh mới chạy đồng thời có thể thay đổi kết quả sau snapshot dự báo 16:28–16:41. [Trạng thái refresh](refresh_current_2026-11-19.json) là tiến độ tại thời điểm chụp, không đồng nghĩa mọi mã đã có phiên mới.
- Sau khi quét đủ 1.002 mã, backend chính được khởi động lại để nạp bản sửa cuối; API kiểm thử cổng 8001 đã dừng. Lúc **17:10**, health trả 200, FRT/NET/DBC trả USD và HDB trả VND. Refresh khởi động lại với 979 mã, tiến độ 195, chưa hoàn tất; lượt trước dừng khi tiến độ fetch là 748, không ghi nhận nó là một lượt refresh hoàn thành. Bằng chứng ở [smoke backend cuối](backend_final_smoke_2026-11-19.json).
- Sau khởi động lại, câu hỏi HTTP `Price BK today` trên cổng 8000 trả 200 và gọi `get_market_summary` với đúng `symbol=BK`, không lỗi công cụ.
- Chưa kiểm thử hết báo cáo tài chính, orderbook, CSV, giao diện trình duyệt và mọi tính năng phụ trên từng mã. Không tuyên bố đã bao phủ “mọi thứ liên quan tới mã”.

## Việc còn cần làm để đạt đầy đủ độ phủ

1. Xác định công cụ nào đang hoạt động, đổi tên hoặc hủy niêm yết; chuẩn hóa mã theo thị trường để xử lý tên trùng.
2. Bổ sung lịch sử cho mã còn hoạt động nhưng thiếu phiên, hoàn tất refresh và kiểm tra chất lượng nguồn mới.
3. Chỉ train model còn thiếu sau khi dữ liệu đủ và vượt kiểm tra chất lượng; xác minh bốn trường hợp gián đoạn thang giá.
4. Nếu yêu cầu mọi mã có ARIMA/LSTM và walk-forward, cần chạy batch huấn luyện/đánh giá toàn bộ và đối chiếu naive/buy-and-hold. Không dùng số LR thay cho độ phủ cả ba model.
5. Tiếp tục kiểm chứng LLM và các tính năng phụ theo từng loại thị trường; theo dõi timeout và tính ổn định dưới tải.
