# Sửa lỗi và kiểm chứng lại — 19/11/2026

Lượt kiểm tra tiếp theo, các bản sửa bổ sung và số đo mới nhất được ghi riêng tại [Sửa lỗi bổ sung ngày 19/11/2026](SUA_LOI_BO_SUNG_2026-11-19.md). Các số liệu dưới đây thuộc lượt kiểm tra trước, không mặc nhiên đại diện thời điểm hiện tại.

## Phạm vi

Đã sửa các lỗi tái hiện từ bản phản biện và lượt quét toàn bộ mã: dữ liệu, dự báo, đánh giá ngoài mẫu, sổ kiểm chứng, nhóm thị trường, lịch batch và hiển thị. Backend đã được khởi động lại bằng mã mới; dữ liệu dẫn xuất và model đã được xử lý trên MinIO/MySQL thật.

Không khẳng định mọi mã đều dự báo được: mã chỉ còn lịch sử cũ, thiếu model hoặc chưa vượt kiểm tra chất lượng phải trả lý do không khả dụng. Không tạo giá thay thế để tăng tỉ lệ thành công.

## Những lỗi đã sửa

| Vấn đề | Hành vi sau sửa |
|---|---|
| Giá âm hoặc lệch nhiều bậc độ lớn vẫn báo dự báo thành công | Bộ kiểm tra giá dùng chung bảo vệ đường đọc và ghi; model bị chặn không tiếp tục phục vụ số sai |
| Biến `symbol` chưa định nghĩa trong kiểm tra watermark | Dùng đúng `sym`; kiểm thử chạy thật nhánh Gold chậm hơn Bronze dù provider không thêm hàng |
| Bộ đếm dự báo thiếu `nonlocal` | Đếm được dự báo đã lưu; không coi việc chỉ tính ra số là đã xuất bản thành công |
| Refresh chồng lấn, trạng thái trống khó phân biệt đang chạy hay chưa chạy | Khóa chống chạy trùng; API có `running`, tiến độ, thời điểm bắt đầu và kết quả cuối; lỗi rebuild được ghi trong summary |
| Dự báo đệ quy tính chỉ báo từ một hàng | Nối hàng mới rồi tính lại trên toàn bộ lịch sử; kiểm thử SMA và lag của bước thứ hai |
| LR dừng ở bước hai do NaN warmup; horizon dài bị cắt | LR chỉ nhận hàng cuối khi dự báo bước tiếp; không báo thành công một horizon chưa đủ điểm; lịch tìm đủ 60 phiên khi được yêu cầu |
| Batch giữ cả universe trong cache rồi phải đọc lại khi TTL hết | Xử lý nhóm tối đa 32 mã, giữ trực tiếp đầu vào của nhóm; commit theo dự báo và chỉ đọc giá cho các target đã đến hạn chấm |
| Regime dùng quantile của cả tương lai | Ngưỡng expanding chỉ lấy các quan sát trước hàng hiện tại; thay tương lai không làm đổi nhãn quá khứ |
| Full-fit vừa học vừa chấm cùng dữ liệu | Chấm mô hình đánh giá độc lập trước, lưu riêng, rồi refit một mô hình phục vụ; model cũ được sao lưu |
| Cutoff giữ target của phiên sau cutoff | Tính lại target sau khi cắt lịch sử; timestamp kết quả LR/LSTM là ngày đích, không phải ngày đầu vào |
| LSTM bỏ mất cửa sổ hợp lệ cuối | Số mẫu là `n - sequence_length + 1` |
| ARIMA bắt đầu chấm test với trạng thái thiếu validation | Cập nhật các quan sát validation trước test; biểu đồ cập nhật đủ ngữ cảnh trước khi cắt phần hiển thị |
| So lỗi trên các tập phiên khác nhau và thiếu naive | Khi đủ artifact mới, so mọi model trên giao các phiên đích; thêm baseline giữ nguyên giá; không gắn nhãn “Best MAE” khi chưa so được cùng phiên |
| Ngày đích có thể đã mở phiên; thị trường Australia lệch một ngày | Không nhắm timestamp phiên đã qua; .AX/.NZ dùng ngày tại sàn nhất quán giữa lịch dự báo, độ trễ và chấm giá thật |
| Upsert đổi dự báo đã chấm nhưng giữ sai số cũ | Giá của dự báo đã chấm là bất biến; phiên bản chưa chấm bị thay được lưu vào `prediction_revisions` |
| Backfill có thể thay dự báo đã phát hành | Giữ nguyên bản phát hành; điểm luôn tính từ dự báo đang lưu, không nhận sai số do caller tự tính |
| Chỉ dựa vào source để gọi là phát hành trước phiên | Lưu timestamp đích, mốc đầu vào, phiên bản model; chỉ tính bằng chứng trước phiên nếu thời điểm phát hành được xác minh |
| Giá và sai số mất độ chính xác khi lưu | Chuyển các cột số dự báo từ FLOAT sang DOUBLE; lưu bản sao trước khi sửa điểm không khớp |
| MAE/WAPE cộng chung đơn vị tiền khác nhau | Bỏ số tuyệt đối gộp toàn universe; dùng sai số tương đối, giữ MAE theo từng mã |
| Đếm 1.037 mục thành 1.037 mã | Loại mã trùng; danh sách có 1.002 mã duy nhất; lỗi liệt kê không được che bằng danh sách cấu hình |
| Phân nhóm .AX, .MI, .SA sai | Sửa ASX, Milan, B3; nhóm Việt Nam không bị mặc định là toàn HOSE |
| EOD Việt Nam đặt vào buổi sáng | Cron HOSE 08:30 UTC, universe forecast 09:30 UTC, quality gate 10:30 UTC; NYSE vẫn 21:30 UTC |
| Lịch sử pipeline luôn trả 501, nhầm file với bản ghi | Lưu/đọc kết quả run thật, mặc định theo backend lưu trữ đã cấu hình; đếm hàng tách khỏi số object |
| Agent lỗi biến khi trả dữ liệu tài chính, context nói có XGBoost | Sửa biến, cập nhật danh sách mô hình thật; thêm kiểm tra tên biến trong CI |
| Tài liệu còn mô tả Iceberg/time-travel đang chạy | README và tài liệu lakehouse nêu đúng Parquet/MinIO và giới hạn snapshot; không đồng nhất lineage với time-travel |

## Dữ liệu và mô hình đã xử lý

- Một lượt auto-refresh đã hoàn tất: **976 mã cấu hình**, Silver/Gold dựng lại **87 mã**, không ghi nhận lỗi trong summary của lượt đó. Đây không phải số mã mới nạp thêm.
- Dựng lại Gold từ Silver cho **toàn bộ 1.002 mã duy nhất**. Job cũ nhận 1.037 mục vì danh sách đầu vào còn trùng; báo cáo giữ nguyên sự thật đó. Lỗi đếm trùng đã được sửa trong API và script.
- Huấn luyện lại **920 model LR** trên lịch sử dài hợp lệ; với các trường hợp bị từ chối và WOLF, có thêm **44 model** huấn luyện thành công trên cửa sổ 252 phiên được ghi rõ trong registry. Một số model được ghi lại ở nhiều lượt; số model LR hiện có đánh giá độc lập là **964 mã**, không cộng các lượt thành số mã duy nhất.
- Năm mã từng có dự báo sai — SPXU, SQQQ, SOXS, UVXY, VXX — huấn luyện lại được trên cửa sổ gần nhất. Đây vẫn là mô hình có sai số, không phải bảo đảm dự báo chính xác.
- **MRNA, PARA, ACH, EMBJ** vẫn bị bộ kiểm tra từ chối ở cửa sổ 252 phiên. Đã lưu bản sao và chặn các model LR cũ tương ứng, không tiếp tục phục vụ chúng như model hợp lệ. Đây là phát hiện nghi ngờ gián đoạn cần đối chiếu, không tự chứng minh mọi biến động đều là lỗi dữ liệu.
- ARIMA và LSTM cho **AAPL, MSFT, FPT** đã huấn luyện lại; giữ riêng mô hình dùng đánh giá và mô hình refit để phục vụ.
- Registry lưu phiên bản, hash đầu vào và provenance đánh giá. Các thư mục model cũ nằm trong `backend/data/model_versions/`.

## Kiểm chứng và số đo

- Backend cuối cùng: **619 passed, 25 skipped**, 4 cảnh báo thư viện; không ghi 644/644 pass. Những bài cần môi trường/dữ liệu thật có thể bị bỏ qua trong sandbox.
- Frontend: TypeScript và Vite production build thành công.
- Ruff: không còn lỗi tên biến chưa định nghĩa/tham chiếu trước gán trong `app` và `scripts`.
- Các migration **0006–0008** đã được áp dụng vào MySQL: revision, provenance và độ chính xác số.
- Đã kiểm tra **46.487** dòng có giá thật; tính lại **32.574** dòng có trường không khớp, lưu bản sao trước sửa. Phần lớn là sai lệch làm tròn FLOAT: trung vị chênh lệch tuyệt đối khoảng **0,00019**; có **15** trường hợp cần điều chỉnh quyết định hướng. Không diễn giải 32.574 là số dự báo sai nghiêm trọng.
- API AAPL so ba mô hình và naive trên **320 phiên đích chung**. Kết quả không chứng minh LSTM hoặc LR luôn hơn naive; giữ nguyên cả kết quả kém đối chứng.
- Hai báo cáo MA/RSI đã sinh lại trên **102 mã / 14 nhóm thị trường / 3.724 cửa sổ cặp**. Đây là nhóm thị trường, không phải 14 sàn đơn lẻ đã xác minh đầy đủ metadata.
- Kết quả quét API sau sửa và lượt xuất bản/chấm thật được lưu trong các artifact bên dưới; thời gian quét được ghi trong JSON.

### Kết quả API sau sửa

| Kiểm tra | Kết quả |
|---|---:|
| Giá đọc được từ Gold | **1.002/1.002 mã** |
| Số lượt GET trong quét toàn bộ | **2.151**, không có lỗi HTTP/timeout |
| LR trả dự báo hợp lệ | **959 mã** |
| LR không khả dụng | **43 mã**: 28 thiếu model, 11 đầu vào chậm phiên, 4 model bị chặn |
| ARIMA / LSTM trả dự báo hợp lệ trong số có model | **71/74**, **70/73**; mỗi họ có 3 mã đầu vào chậm phiên |
| Giá âm, không hữu hạn hoặc quá xa reference theo bộ kiểm tra | **0** trong các kết quả trả khả dụng |
| Độ trễ p50 / p95 trong quét | **0,516 / 2,828 giây** |
| Lượt xuất bản toàn universe | **1.100 tính được, 1.100 lưu thành công, 20 dự báo cũ được chấm** |
| Dự báo mới 5 phiên qua API | AAPL/LR, MSFT/ARIMA, FPT/LSTM, SOXS/LR đều **HTTP 200, đủ 5 điểm, giá dương** |

Batch xuất bản hoàn tất trong **545,77 giây**. 49 trường hợp không xuất bản tương ứng 43 LR và 3+3 ARIMA/LSTM không đủ điều kiện; không phải 49 giá trị sai đã được lưu.

Tại lần smoke cuối, AAPL đã có ba bản phát hành cho phiên **19/11/2026**, source `auto_eod_batch`. Các dự báo mới còn chờ giá thật của phiên đích, không tự gán kết quả để làm đầy báo cáo. **1.337** bản ghi công bố cũ đã có giá thật nhưng thiếu timestamp đích được báo `timing_unknown`; chưa được tính thành bằng chứng đã xác minh phát hành trước phiên.

## Giới hạn còn phải trình bày trung thực

- **28 mã** không có model LR; đa số chỉ còn lịch sử cũ. Ví dụ, lượt refresh gọi Yahoo vẫn chỉ nhận một hàng cũ cho AVB, EA, EQR; không có cơ sở tạo giá mới cho chúng hoặc tự khẳng định tất cả đã hủy niêm yết.
- **6 model LR cũ** còn thuộc các mã có lịch sử chưa cập nhật đầy đủ. Bộ kiểm tra đầu vào chặn việc gọi một dự báo một bước từ dữ liệu bị chậm phiên.
- Không hồi dựng giả `target_open_at`/phiên bản model cho các bản ghi cũ thiếu provenance. Chúng vẫn được lưu nhưng không mặc nhiên tính là bằng chứng phát hành trước phiên.
- Các dự báo .AX/.NZ cũ chưa ghi timestamp đích không được tự chấm theo một ngày phiên suy đoán.
- Chưa chạy Actions trên GitHub trong phiên này; workflow kiểm thử/build đã được bổ sung. Báo cáo kiểm thử ở trên là số đo local.
- Parquet/MinIO hiện không có table snapshot/ACID. Model version và hash giúp truy vết, nhưng không thay thế việc lưu snapshot dữ liệu đầu vào cho một thí nghiệm cần tái lập tuyệt đối.
- Bộ so sánh naive và sửa giao thức đánh giá không thay thế nghiên cứu liên quan, trích dẫn, khoảng tin cậy, đánh giá Agent và biên tập bản Word/PDF cuối cùng.

## Artifact để kiểm tra lại

- [Quét toàn bộ API sau sửa](live_universe_after_repair_2026-11-19.json).
- [Lượt xuất bản và chấm sau sửa](publication_after_repair_2026-11-19.json).
- [Phân loại các mã không khả dụng](live_after_repair_findings_2026-11-19.json).
- [Smoke API và sổ đã lưu](live_final_smoke_2026-11-19.json).
- [Dự báo nhiều bước qua API](multistep_after_repair_2026-11-19.json).
- [Dựng lại Gold](gold_repair_2026-11-19.json).
- [LR trên lịch sử dài](models_repair_2026-11-19.json).
- [LR trên cửa sổ 252 phiên](recent_retry_models_2026-11-19.json).
- [Sáu mã từng có giá sai](recent_window_models_2026-11-19.json).
- [Model bị chặn và bản sao](blocked_models_2026-11-19.json).
- [ARIMA](arima_repair_2026-11-19.json), [LSTM](lstm_repair_2026-11-19.json).
- [Điểm kiểm chứng trước/sau sửa](prediction_score_repair_2026-11-19.json).
- [MA walk-forward hiện tại](../../backend/data/multi_symbol_walkforward.json), [RSI hiện tại](../../backend/data/multi_symbol_walkforward_rsi.json).

Đây là kết quả sửa và kiểm chứng trong phạm vi các lỗi đã xác nhận; không phải chứng nhận hệ thống không thể còn lỗi.
