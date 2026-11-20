# Sửa lỗi và kiểm chứng bổ sung ngày 19/11/2026

Đây là lượt kiểm tra tiếp theo sau [báo cáo sửa lỗi trước](KET_QUA_SUA_LOI_2026-11-19.md), tập trung vào dự báo, dữ liệu đầu vào, lịch sử công bố và toàn bộ danh sách cổ phiếu. Các thay đổi đã có trong workspace được giữ nguyên.

## Các lỗi xác nhận và đã sửa

### Tính toàn vẹn của sổ dự báo

- Chỉ nhận các trường dự báo cho phép; không thể đưa điểm thực tế, ID hoặc thời gian công bố tùy ý vào thao tác lưu dự báo.
- Chuẩn hóa mã cổ phiếu, ngày phiên và múi giờ UTC trước khi so sánh thời điểm.
- Gửi lại cùng một dự báo không làm thay đổi thời gian công bố ban đầu.
- Bản dự báo đã được chấm không thể bị sửa giá hoặc thông tin nguồn gốc. Thay đổi nguồn gốc của bản chưa chấm được lưu thành revision, kể cả khi giá không đổi.
- Khóa bản ghi hiện hữu trong giao dịch khi sửa hoặc chấm, giảm nguy cơ hai thao tác ghi đè nhau. Đây không phải cam kết loại bỏ mọi tranh chấp đồng thời khi tạo bản ghi mới.
- Không để backfill ghi đè bản công bố thật; chặn cập nhật khi thời điểm mở phiên đích đã qua.

### Dữ liệu và căn chỉnh dự báo

- Không âm thầm dùng một hàng đặc trưng cũ nếu hàng mới nhất bị thiếu hoặc không hữu hạn.
- Dự báo t+1 gắn với phiên ngay tiếp theo trên trục thời gian gốc; không nhảy qua khoảng thiếu đặc trưng. Cửa sổ LSTM không nối qua các khoảng này.
- Chỉ tính lịch sử ngoài tập huấn luyện; nếu khoảng đánh giá nằm hoàn toàn sau dữ liệu thì trả rỗng.
- Dự báo nhiều bước giữ đủ lịch sử để tính lại chỉ báo. Lỗi tính chỉ báo hoặc cập nhật trạng thái ARIMA được báo rõ, không dùng trạng thái cũ làm kết quả mới.
- LSTM nhận đúng số hàng trong cửa sổ suy luận.

### Chấm điểm và hiển thị

- Chặn giá thực tế NaN, vô cực, bằng hoặc nhỏ hơn 0.
- Chọn giá đóng cửa theo timestamp đã sắp xếp và bỏ quan sát giá không hợp lệ.
- Độ chính xác chiều tăng/giảm dùng đúng giá tham chiếu của từng điểm, bao gồm điểm đầu tiên; loại bộ dữ liệu không hữu hạn khỏi phép tính.
- Median khi có số mẫu chẵn lấy trung bình hai phần tử giữa.
- API lịch sử lấy N bản mới nhất, sau đó sắp theo thời gian tăng dần; trước đó giới hạn truy vấn làm lấy nhầm các bản cũ nhất.

### Biên đầu vào và hiệu năng

- Kiểm tra mã và tên họ mô hình trước khi tạo đường dẫn; thao tác đọc không tự tạo thư mục.
- Kiểm tra tỷ lệ giá cực nhỏ/cực lớn không còn lỗi chia cho 0 do underflow.
- Khắc phục đường tính lịch sử LSTM gây vượt thời gian chờ: chỉ tính các cửa sổ đóng góp vào vùng biểu đồ yêu cầu, đồng thời suy luận theo lô. Kiểm thử đối chiếu với suy luận từng cửa sổ và toàn bộ lịch sử để bảo vệ giá trị, thứ tự và căn chỉnh kết quả.

## Kiểm thử

- Toàn bộ backend sau bản sửa cuối: **652 passed, 22 skipped, 4 warnings**, 125,64 giây. Các trường hợp bỏ qua được pytest ghi rõ: môi trường sandbox không truy cập được một số tài nguyên MySQL/Gold hoặc không có điểm tương lai đủ điều kiện. Bốn cảnh báo là deprecation của thư viện phụ thuộc.
- Frontend: `npm.cmd run build` thành công, gồm kiểm tra TypeScript và build Vite.
- Ruff kiểm tra tên chưa khai báo (`F821,F822,F823`) thành công; `git diff --check` thành công.
- Các kiểm thử tính toàn vẹn dùng SQLite riêng; kiểm thử mô hình dùng dữ liệu tổng hợp riêng. Không tạo dữ liệu giả cho ứng dụng đang chạy.
- Số liệu của lượt kiểm tra trực tiếp MySQL/MinIO được ghi riêng, không cộng với lượt toàn bộ backend vì có kiểm thử trùng nhau.
- Kiểm tra trực tiếp MySQL/MinIO sau bản sửa cuối: **10 passed, 9 skipped**, 27,55 giây. Hai trường hợp chưa có mẫu đã chấm với bằng chứng công bố trước phiên; bảy trường hợp không có điểm tương lai hợp lệ do dữ liệu trễ. Không coi các trường hợp này là đã kiểm thử thành công.

## Kiểm chứng dịch vụ thật

MySQL và MinIO đã hoạt động trở lại trên Docker Engine trong WSL; kiểm tra kết nối MySQL thành công, bảng dự báo có **47.631 bản ghi**, MinIO health trả HTTP 200. Backend được khởi động lại bằng mã đã sửa; API health trả HTTP 200. Dịch vụ tự cập nhật bật với **976 mã cấu hình**, đã ghi nhận đọc dữ liệu nguồn và dựng lại Silver/Gold. Con số cấu hình này khác danh sách 1.002 mã lịch sử mà API liệt kê.

Tại lần kiểm tra trạng thái cuối, dịch vụ cập nhật vẫn đang chạy: **976/976 mã đã qua bước fetch, 1 Silver và 1 Gold đã dựng lại**. Đây là tiến độ, chưa phải kết quả hoàn tất toàn bộ lượt cập nhật. Việc fetch một mã cũng có thể chỉ nhận lại dữ liệu cũ từ nguồn; không đồng nghĩa mã đó đã có giá phiên mới.

Lượt quét toàn bộ API diễn ra **13:49–13:58 ngày 19/11/2026, giờ Việt Nam**, trước lần khởi động lại nạp tối ưu hiệu năng LSTM cuối cùng:

| Hạng mục | Kết quả |
| --- | --- |
| Mã duy nhất được liệt kê và kiểm tra | 1.002 |
| Giá gần nhất đọc được từ Gold | 1.002/1.002 |
| LR khả dụng / chưa khả dụng | 764 / 238 |
| ARIMA khả dụng / chưa khả dụng, trong số mã có registry | 42 / 32 |
| LSTM khả dụng / chưa khả dụng, trong số mã có registry | 43 / 30 |
| Tổng yêu cầu GET đã kiểm tra | 2.151 |
| Lỗi HTTP hoặc lỗi kết nối trong lượt quét | 0 |
| Giá dự báo khả dụng không dương/không hữu hạn | 0 |
| Độ trễ p50 / p95 | 0,406 / 2,797 giây |

Phân loại **238 LR chưa khả dụng**: **28 thiếu mô hình, 206 trễ dữ liệu theo phiên đích, 4 bị chặn kiểm tra chất lượng** (MRNA, PARA, ACH, EMBJ). Toàn bộ 32 ARIMA và 30 LSTM chưa khả dụng đều báo trễ dữ liệu.

Đây là ảnh chụp khả dụng tại thời điểm nêu trên. Không thay thế bằng số 959 LR khả dụng của lượt kiểm tra cũ: thời điểm thị trường, phiên đích và dữ liệu đang lưu đã khác. Có 960 mã có timestamp gần nhất ngày 18/11, nhưng ngày đó không đồng nghĩa tất cả đều đủ mới cho phiên đích mà API đang yêu cầu. Đặc biệt khi thị trường đang giao dịch, không được gọi giá phiên trước là giá đóng cửa của phiên hiện tại.

Sau khi nạp mã cuối, smoke API cho kết quả:

| Yêu cầu dự báo 5 phiên | HTTP | Điểm tương lai | Thời gian |
| --- | --- | --- | --- |
| AAPL / LR | 200 | 5, giá dương và hữu hạn | 0,781 giây |
| MSFT / ARIMA | 200 | 5, giá dương và hữu hạn | 2,031 giây |
| AAPL / LSTM | 200 | 5, giá dương và hữu hạn | 0,297 giây |
| SOXS / LR | 200 | 5, giá dương và hữu hạn | 0,578 giây |
| FPT / LSTM | 200 | 0, chặn vì trễ 1 phiên; 120 điểm lịch sử | 1,016 giây |

FPT/LSTM trước tối ưu đã vượt timeout 60 giây. Sau sửa, cùng loại yêu cầu trả trong khoảng một giây và giữ thông báo không đủ điều kiện dự báo. Các phép đo này là smoke local, không phải benchmark có kiểm soát về tải và cache.

API accuracy/AAPL, compare/AAPL, giá gần nhất AAPL và trường hợp chặn PARA đều HTTP 200. Không xuất bản lại hàng loạt hoặc huấn luyện thêm chỉ để làm thay đổi các số đo.

Artifact để kiểm tra lại:

- [Toàn bộ lượt quét 1.002 mã](live_universe_supplemental_2026-11-19.json).
- [Phân loại từng mã chưa khả dụng](supplemental_findings_2026-11-19.json).
- [Smoke API sau khi nạp mã cuối](supplemental_smoke_2026-11-19.json).
- [Tiến độ cập nhật dữ liệu tại lần kiểm tra cuối](supplemental_refresh_status_2026-11-19.json).

## Phạm vi và giới hạn

Quét API chỉ đọc dữ liệu đang lưu và thử mô hình đã huấn luyện. Nó không chứng minh mọi giá đang lưu đã được đối chiếu với nhà cung cấp trong cùng thời điểm, cũng không đo độ chính xác tương lai.

Một mã có thể đọc được dữ liệu nhưng chưa đủ điều kiện dự báo vì thiếu mô hình, dữ liệu trễ phiên hoặc mô hình bị chặn do kiểm tra chất lượng. Không tạo giá hay mô hình giả để đạt tỷ lệ khả dụng 100%.

Các bản công bố cũ thiếu bằng chứng thời điểm được giữ riêng với các bản đã xác minh công bố trước phiên. Cần chờ giá thực tế của phiên đích để đánh giá các dự báo mới.

Đây là kết quả sửa các lỗi đã xác nhận và kiểm chứng trong phạm vi nêu trên, không phải chứng nhận phần mềm không còn lỗi hoặc xác nhận bản luận văn cuối cùng đã hoàn chỉnh về học thuật.
