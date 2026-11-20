# Đánh giá phản biện Stock Lakehouse AI — 19/11/2026

## 1. Phạm vi và kết luận

Đánh giá dựa trên mã nguồn, README, presentation.md, tài liệu giải trình toàn diện, tài liệu lakehouse, nghiên cứu walk-forward, báo cáo JSON và registry mô hình có trong workspace. Không có bản Word/PDF luận văn cuối cùng trong những tệp đã tìm thấy; nhận xét hình thức học thuật dưới đây áp dụng cho tài liệu hiện có, không mặc nhiên áp dụng cho một bản nộp nằm ngoài dự án.

**Kết luận: nền tảng kỹ thuật có chiều sâu và đủ chất liệu cho một khóa luận tốt; hiện chưa nên chốt là hoàn chỉnh vì còn lỗi ảnh hưởng trực tiếp đến tính hợp lệ của đánh giá mô hình và bằng chứng kiểm chứng dự báo.** Việc cần ưu tiên là sửa phương pháp, đồng bộ bằng chứng và viết lại lập luận; thêm mô hình hoặc công nghệ sẽ không giải quyết các vấn đề này.

Các điểm đáng giữ:

- Pipeline Bronze–Silver–Gold, kiểm tra dữ liệu, truy vết nguồn và xử lý sai lệch giữa các tầng.
- Chia train/validation/test theo thời gian; scaler của LSTM được fit trên đầu vào train trong chế độ đánh giá thông thường.
- Backtest có phí, trượt giá, thực thi ở bar kế tiếp và đối chứng mua và giữ.
- Đã mở rộng đánh giá chiến lược sang nhiều mã, báo cáo cả kết quả không vượt đối chứng.
- Có vòng xuất bản dự báo, nhận giá thật và chấm điểm; hệ thống có nhiều kiểm thử hồi quy cho lỗi nghiệp vụ thực tế.

Không nên đồng nhất những điểm này với một thuật toán mới. Với khóa luận xây dựng hệ thống, đóng góp có thể là thiết kế, triển khai, kiểm chứng và kết quả thực nghiệm có thể tái lập.

## 2. Kết quả kiểm tra trong lần đánh giá này

| Kiểm tra | Kết quả |
|---|---|
| Backend: `.venv/Scripts/python.exe -m pytest` | **583 passed, 20 skipped, 4 warnings**, 117,61 giây |
| Frontend: `npm.cmd run build` | **Thành công**, TypeScript và Vite build qua |
| Kiểm chứng bổ sung bằng dữ liệu tổng hợp cô lập | Tái hiện lỗi full-fit/hold-out, nhãn vượt cutoff, regime nhìn tương lai, chỉ báo đệ quy và cập nhật dự báo đã chấm |
| Kiểm tra phân loại sàn | Hàm hiện tại trả sai cho `.AX`, `.MI`, `.SA` |
| Kiểm tra registry cục bộ | 1.118 record: 1.092 không ghi fit_mode, 25 holdout_split, 1 full |
| Kiểm tra trực tiếp MySQL/MinIO đang chạy | Chưa xác nhận lại trong lần đánh giá này |

Dữ liệu tổng hợp chỉ phục vụ kiểm chứng logic, không đưa vào dữ liệu thị trường hoặc sổ dự báo thật. Phép kiểm tra huấn luyện dùng Gold giả lập trong bộ nhớ và thư mục mô hình tạm; kiểm tra sổ dự báo dùng SQLite trong bộ nhớ. Các số trong kiểm chứng dưới đây không phải kết quả dự báo thị trường.

**Bộ test xanh không chứng minh toàn bộ phương pháp đúng.** Các phép kiểm chứng bổ sung tìm được lỗi nằm ngoài các điều kiện mà test hiện có bao phủ. Không được viết lại thành “603/603 pass”: có 20 bài bị bỏ qua.

## 3. Những lỗi phải sửa trước khi dùng kết quả làm bằng chứng chính

### R01 — Chế độ full_fit chấm điểm trên dữ liệu đã dùng để học

**Mức độ: nghiêm trọng, đã tái hiện.**

Vị trí: [trainer.py](../backend/app/forecasting/trainer.py), các nhánh từ dòng 188, 221 và 242.

Khi `full_fit=True`, mã fit trên `clean`, bao gồm cả phần `split.test`, rồi gọi `evaluate(split.test, ...)` trên chính mô hình đó. Docstring lại nói metrics vẫn đến từ mô hình học trên split riêng. Hai hành vi không khớp nhau.

Bằng chứng cô lập: mô hình Linear Regression fit 219 hàng, evaluate 34 hàng; **cả 34 hàng đánh giá đều thuộc tập đã fit**. Không thể gọi các metrics này là kết quả hold-out độc lập.

Registry cục bộ còn có `AAPL/lstm/registry.json` ghi `fit_mode=full`, tạo ngày 17/11/2026. Vì vậy đây không chỉ là một nhánh tùy chọn chưa bao giờ được dùng. Tuy nhiên, chưa thể kết luận tất cả registry cũ hoặc bảng kết quả lịch sử đều bị lỗi: nhiều record không ghi chế độ fit.

**Cần sửa:** dùng một mô hình chỉ học train để đánh giá, lưu metrics và dự báo kiểm tra của nó; sau đó tạo một mô hình riêng để refit cho phục vụ thực tế. Registry phải phân biệt phiên bản đánh giá và phiên bản phục vụ, thời hạn dữ liệu thực sự đã học và nguồn của metrics. Đánh dấu rồi tính lại kết quả bị ảnh hưởng; không chỉ sửa câu chữ.

### R02 — Cắt lịch sử theo end_date nhưng vẫn giữ nhãn của ngày sau

**Mức độ: nghiêm trọng đối với mô phỏng refit theo thời gian, đã tái hiện.**

Vị trí: [trainer.py](../backend/app/forecasting/trainer.py), dòng 160; [target_features.py](../backend/app/features/target_features.py).

Gold đã có `target_close_next = close.shift(-1)` trước khi `_truncate_to()` lọc timestamp. Hàng cuối ở ngày cutoff có thể vẫn mang đáp án từ phiên sau cutoff.

Bằng chứng: cutoff `2024-08-13`, close ở cutoff = `113.77633199460374`; nhãn cuối được đưa vào full-fit = `113.98221939570173`, đúng bằng close của phiên kế tiếp. Tức mô hình tại cutoff đã nhận một giá chưa có tại cutoff.

**Cần sửa:** cắt OHLCV theo thời điểm thông tin khả dụng trước, rồi tính lại nhãn; hoặc lưu timestamp của target và chỉ giữ hàng có target không vượt cutoff. Với dự báo nhiều phiên phải áp dụng điều kiện cho toàn bộ khoảng nhãn. Không quy lỗi này cho mọi lần train mặc định: tác động phụ thuộc đường refit đang dùng.

### R03 — Sổ kiểm chứng có thể đổi dự báo nhưng giữ sai số của dự báo cũ

**Mức độ: nghiêm trọng, đã tái hiện.**

Vị trí: [prediction_repository.py](../backend/app/database/repositories/prediction_repository.py), dòng 47–129.

`upsert()` thay `predicted_close` và các thuộc tính dự báo của record tồn tại, đồng thời giữ các cột kết quả. Giữ `actual_close` là hợp lý; giữ nguyên `abs_error` hoặc `direction_correct` sau khi thay dự báo thì không còn bảo đảm đúng.

Bằng chứng trên SQLite cô lập:

| Trạng thái | Dự báo | Giá thật | Sai số lưu | Sai số đúng |
|---|---:|---:|---:|---:|
| Sau lần chấm đầu | 110 | 105 | 5 | 5 |
| Sau upsert đổi dự báo | 120 | 105 | **5** | **15** |

Thêm vào đó, khóa duy nhất `(symbol, model, target_session)` cùng hành vi ghi đè làm mất phiên bản dự báo trước. Backfill và dự báo xuất bản thật có thể đụng cùng khóa.

**Cần sửa:** lưu lịch sử phát hành bất biến với `issued_at`, `target_session`, phiên bản model và snapshot dữ liệu; cho phép tạo phiên bản mới thay vì viết đè bằng chứng cũ. Nếu duy trì một bảng “latest” cho giao diện, bảng đó cần tách khỏi lịch sử dùng đánh giá. Khi thay dự báo phải tính lại kết quả liên quan; dự báo phát hành sau thời hạn thông tin cho phép không được tính thành dự báo tương lai hợp lệ. Tách chỉ số backfill khỏi chỉ số xuất bản trước thực tế.

### R04 — Dự báo nhiều bước chưa cập nhật chỉ báo bằng đủ lịch sử

**Mức độ: cao, đã tái hiện.**

Vị trí: [multistep.py](../backend/app/forecasting/multistep.py), dòng 299–320.

Hàm dựng `next_row` có một hàng, gọi `_recompute_indicators(next_row, ...)`, rồi dùng chỉ báo cũ nếu kết quả NaN. SMA cần nhiều phiên nên bị giữ lại; EMA tính từ một hàng cũng không tương đương EMA tiếp tục từ lịch sử. Bình luận trong mã lại nói tính trên toàn bộ frame.

Bằng chứng: ở đầu vào bước 2, SMA20 nhận được = `97.33042345510218`; SMA20 tính từ 19 giá lịch sử cuối và giá dự báo bước 1 phải là `97.67478126548583`.

**Cần sửa:** nối hàng dự báo vào lịch sử, tính lại các đặc trưng từ lịch sử đó, rồi lấy cửa sổ cuối để dự báo tiếp. Ghi rõ giả định cho volume/OHLC chưa biết trong tương lai. Đánh giá riêng horizon 1, 3, 5; không dùng sai số một bước làm bằng chứng cho độ chính xác cả đường dự báo năm phiên.

### R05 — Báo cáo theo sàn đang phân nhóm sai

**Mức độ: cao, xác nhận bằng hàm đang chạy.**

Vị trí: [run_multi_symbol_walkforward.py](../backend/scripts/run_multi_symbol_walkforward.py), bảng suffix từ dòng 80.

| Ví dụ | Nhóm hiện tại | Nhóm cần dùng |
|---|---|---|
| `BHP.AX` | Nasdaq Nordic | ASX, Australia |
| `ENI.MI` | BME | Milan, Italy |
| `ABEV3.SA` | TADAWUL | São Paulo/B3, Brazil |

Hàm chọn mẫu cũng dùng chính phân nhóm này. Vì vậy lỗi có thể ảnh hưởng cả mẫu được chọn và kết luận theo sàn, không chỉ nhãn hiển thị. Danh sách VN hiện được gom là HOSE dù phần mô tả nhà cung cấp đề cập HOSE/HNX/UPCoM; cần đối chiếu metadata thực tế của từng mã.

**Cần sửa:** dùng bảng exchange/market thống nhất toàn dự án, kiểm tra danh sách thành viên, chạy lại cả hai báo cáo đa mã và cập nhật số lượng sàn/mã. Không giữ kết luận “13 sàn” như một con số đã xác nhận sau khi sửa mapping.

Hai JSON báo cáo hiện có sinh ngày 11/11/2026 với cấu hình 365/90/90 ngày, phí 0,1%, trượt giá 0,05%. Chúng cần được gắn với snapshot và phiên bản mã đã sinh ra kết quả.

### R06 — Lịch EOD Việt Nam được đặt vào buổi sáng

**Mức độ: cao về vận hành; xác nhận từ cấu hình.**

Vị trí: [crontab](../backend/crontab), dòng 33, 66 và 88; phần lịch trong tài liệu giải trình toàn diện.

File ghi HOSE đóng cửa `02:30 UTC = 09:30 Việt Nam`, rồi chạy EOD lúc `03:30 UTC = 10:30 Việt Nam`. Đây là thời gian trong buổi giao dịch, không phải sau đóng cửa. Universe forecast lúc `04:30 UTC = 11:30 Việt Nam` cũng chưa có giá đóng cửa ngày đó của HOSE.

**Cần sửa:** đối chiếu lịch giao dịch chính thức, chọn giờ sau khi phiên đóng và provider đã chốt dữ liệu; cho job forecast phụ thuộc trạng thái thành công của ingest, không chỉ giả định ingest sẽ xong sau một giờ. Với nhiều thị trường, dùng lịch theo exchange và kiểm tra phiên đã hoàn tất. Sửa cả cron, chú thích và bài viết. Việc có các đường refresh khác không làm cấu hình EOD này trở thành đúng.

### R07 — Đặc trưng market regime nhìn vào toàn bộ tương lai

**Mức độ: cao đối với tính nhân quả của Gold; phạm vi mô hình hiện tại cần phân biệt rõ.**

Vị trí: [macro_features.py](../backend/app/features/macro_features.py), dòng 94.

Ngưỡng `volatility_20d.quantile(0.75)` được tính trên toàn bộ chuỗi, rồi gán regime cho các ngày quá khứ. Thay phần tương lai có thể làm đổi đặc trưng quá khứ.

Bằng chứng: giữ nguyên 100 hàng đầu, chỉ thay close từ hàng 100 trở đi; **32 nhãn regime trong 100 hàng đầu thay đổi**.

**Giới hạn tác động:** danh sách đặc trưng LR/LSTM hiện tại không chứa `regime_numeric` hay `volatility_actual`, nên chưa có cơ sở nói các metrics LR/LSTM hiện có đã nhiễm qua đặc trưng này. Tuy vậy, khẳng định “mọi đặc trưng Gold đều causal” và giả định một số tối ưu ghi tăng dần đều cần xem lại.

**Cần sửa:** ngưỡng rolling/expanding chỉ dùng lịch sử có sẵn, hoặc fit ngưỡng trên train rồi cố định khi áp dụng; kiểm chứng rằng thêm tương lai không làm thay đổi các đặc trưng quá khứ không phải target.

## 4. Những phần phương pháp nghiên cứu còn thiếu hoặc cần sửa cách kết luận

### M01 — Chưa có đối chứng dự báo ngây thơ và so sánh chưa chung tập phiên

Trong phần dự báo đã đọc và mã evaluator/trainer, chưa thấy baseline giữ nguyên giá: `predicted_close[t+1] = close[t]`. Linear Regression là một đối chứng học máy, nhưng không thay thế baseline này.

Giá cổ phiếu giữa hai phiên thường gần nhau. MAPE khoảng 1% chưa chứng minh mô hình tạo thêm giá trị nếu chỉ giữ nguyên giá cũng đạt mức đó.

Bảng ở mục 6.8 của tài liệu chính dùng **374 điểm LR, 381 điểm ARIMA, 318 điểm LSTM**. Khác cỡ mẫu không chứng minh mọi phép so sánh đều sai, nhưng chưa đủ để khẳng định so sánh công bằng trên cùng phiên. Trainer còn lưu timestamp hàng đầu vào trong khi actual của LR/LSTM là target phiên tiếp theo; ARIMA lưu timestamp phiên được dự báo. Cần chuẩn hóa theo `target_session`, rồi lấy giao các phiên cả bốn mô hình đều dự báo được.

ARIMA hiện fit train rồi walk-forward trực tiếp trên test, không cập nhật các quan sát validation vào trạng thái trước test. Cần đưa mô hình về đúng thời điểm bắt đầu đánh giá để tránh bước đầu chấm với trạng thái quá cũ.

Nên báo cáo MAE, RMSE, MAPE hoặc sai số chuẩn hóa theo từng mã, mức cải thiện so với naive và DA so với baseline luôn tăng/đa số lớp. DA xấp xỉ 50% chưa tự nó chứng minh tương đương ngẫu nhiên nếu chưa xét tỉ lệ phiên tăng và độ bất định.

### M02 — “Walk-forward huấn luyện tham số” chưa đúng với triển khai

Trong [walk_forward.py](../backend/app/backtesting/walk_forward.py), `_train_on_window()` chỉ backtest bộ tham số truyền vào; `_test_on_window()` cũng dùng bộ tham số đó. Không thấy bước chọn/tối ưu tham số trên train rồi truyền tham số tối ưu sang test như bình luận mô tả.

Hai lựa chọn hợp lệ: mô tả đúng là đánh giá chiến lược tham số cố định trên các cửa sổ thời gian; hoặc triển khai chọn tham số chỉ trong train/validation. Không cần thêm tối ưu nếu mục tiêu chỉ là kiểm chứng khung.

`overfitting_ratio` là tỉ số lợi nhuận được quy đổi tuyến tính theo số ngày. Nó có thể bất ổn khi lợi nhuận test gần 0 hoặc âm; không phải bằng chứng độc lập rằng chiến lược bị overfit. Không nên dùng ngưỡng 1 hoặc 2 làm kết luận chắc chắn. Walk-forward của MA/RSI cũng không tự kiểm định khả năng dự báo của LSTM.

### M03 — Cần lượng hóa độ bất định và giới hạn chọn mẫu

Báo cáo hiện có là thống kê mô tả hữu ích. Để củng cố lập luận:

- Báo khoảng tin cậy của chênh lệch lỗi dự báo hoặc excess return; ưu tiên bootstrap theo khối thời gian, có xét sự phụ thuộc giữa mã cùng thị trường.
- Không coi 3.687 cửa sổ là 3.687 quan sát độc lập. Cửa sổ có thể phụ thuộc do chồng lấn, cùng mã hoặc cùng giai đoạn thị trường.
- Chạy vài seed LSTM nếu ngân sách cho phép, báo trung bình và độ lệch chuẩn; một seed giúp lặp lại nhưng không đo độ ổn định.
- Ghi rõ mẫu hiện tại là chọn có hệ thống theo thứ tự mã trong mỗi nhóm, không phải lấy mẫu ngẫu nhiên đại diện toàn thị trường.
- Thừa nhận survivorship bias của universe được chọn từ các mã hiện còn dữ liệu, các ngoại lệ bị loại và tác động đến kết luận.
- Nếu đã điều chỉnh thiết kế sau khi xem test, dành một khoảng thời gian chưa dùng để phát triển làm kiểm tra cuối, hoặc dùng đánh giá rolling có giao thức rõ ràng.

Không bắt buộc thực hiện mọi kiểm định thống kê nâng cao cho một khóa luận hệ thống; điều bắt buộc là không kết luận vượt quá bằng chứng thực có.

### M04 — Chính sách giá điều chỉnh và đơn vị đo cần rõ

Loại một mã có lịch sử sai thang giá là một biện pháp phòng thủ, chưa thay cho chính sách corporate actions. Cần định nghĩa close/adjusted close, split, cổ tức và sự khác biệt giữa provider. Dữ liệu điều chỉnh có công thức, nguồn sự kiện và provenance là dữ liệu dẫn xuất hợp lệ; không nên gọi chung mọi điều chỉnh giá là “bịa giá”. Giữ raw và adjusted ở các cột/layer riêng.

Không nên diễn giải MAE gộp USD, VND, JPY như một số có cùng đơn vị. WAPE hiện cộng `abs_error` và `reference_close` giữa các mã; nếu trộn tiền tệ, kết quả thay đổi chỉ vì đổi đơn vị niêm yết. Nên báo lỗi chuẩn hóa theo từng mã rồi tổng hợp, hoặc thống nhất tiền tệ với quy tắc chuyển đổi được mô tả.

Phần trăm lỗi lấy mẫu số là reference close trong sổ kiểm chứng khác MAPE lấy actual close trong evaluator. Cần đặt tên/công thức riêng, không gọi chúng là cùng một chỉ số.

Với backtest Việt Nam, phải nêu giả định về lô giao dịch, thanh khoản, biên độ giá, thuế/phí và khả năng bán theo chu kỳ thanh toán. Engine hiện dùng mô hình đơn giản thì được, nhưng kết luận chỉ trong mô hình đó. Nếu dữ liệu crypto còn được backtest, hệ số 252 phiên/năm mặc định cũng cần xem lại.

### M05 — AI Agent cần một thực nghiệm riêng

Gọi tool thật là nền tảng tốt, nhưng chưa bảo đảm mọi câu trả lời diễn giải đúng số, đơn vị hoặc nguồn. Cần một tập câu hỏi cố định với đáp án đối chiếu, gồm truy vấn giá, chỉ báo, so mô hình, đa vòng, thiếu dữ liệu, mã trùng và tool lỗi.

Đo ít nhất: tỉ lệ hoàn thành yêu cầu, chọn đúng tool, truyền đúng mã/tham số, số liệu/đơn vị khớp tool, trả lời thiếu căn cứ và thời gian phản hồi. Tách kết quả Gemini khỏi fallback theo từ khóa. Có thể dùng 50–100 câu với phạm vi cân đối; số lượng chỉ là đề xuất thiết kế, không phải kết quả đã đo.

[prompts.py](../backend/app/agent/prompts.py) còn nói có XGBoost và các số đặc trưng/quy mô khác tài liệu; registry lớp mô hình hiện chỉ có LR/ARIMA cùng LSTM nạp riêng. Context sai có thể khiến Agent mô tả sai năng lực hệ thống dù các tool dữ liệu đúng.

## 5. Kiến trúc lakehouse và hồ sơ học thuật cần chỉnh

### A01 — Chốt rõ nghĩa “Lakehouse” sau khi bỏ Iceberg

README vẫn mô tả Iceberg REST, time-travel và endpoint 8181; tài liệu khác xác nhận đã bỏ Iceberg. MinIO + Parquet + ba tầng là kiến trúc dữ liệu phân tầng hữu ích, nhưng riêng những thành phần đó chưa chứng minh có các bảo đảm thường gắn với một lakehouse như giao dịch bảng, snapshot nhất quán, quản trị schema và truy vấn phân tích trên bảng.

Quan trọng hơn, [lakehouse.md](lakehouse.md) mô tả `_lineage.json` như cách thay thế đọc lại dữ liệu cũ. Metadata nguồn không thể tái tạo các giá trị đã bị ghi đè. Bronze có logic merge, cập nhật dữ liệu restatement và ghi lại partition; do đó câu “Bronze bất biến, không bao giờ sửa” không mô tả đầy đủ hành vi hiện tại.

**Cần chọn phạm vi có thể bảo vệ:** nếu yêu cầu đề tài đòi hỏi đầy đủ đặc tính lakehouse, bổ sung lớp table/snapshot cho phạm vi cụ thể và chứng minh nó hoạt động. Nếu giữ triển khai gọn, nêu rõ prototype theo kiến trúc medallion và những bảo đảm còn thiếu. Không cần đưa Kafka trở lại nếu không có bài toán streaming thực tế.

Nên lưu raw theo phiên bản/batch bất biến và có manifest phiên bản đầu vào cho thực nghiệm. MySQL metadata không tự tạo giao dịch nguyên tử cho nhiều object Parquet.

### A02 — Tài liệu giải thích cho người mới chưa phải một luận văn hoàn chỉnh

Tài liệu hiện tại có nhiều kiến thức triển khai, lịch sử sửa lỗi và câu trả lời mẫu. Phần này rất hữu ích để học hệ thống và làm phụ lục, nhưng phần thân khóa luận cần mạch nghiên cứu rõ hơn:

1. Bài toán, đối tượng sử dụng, mục tiêu định lượng, phạm vi và câu hỏi nghiên cứu.
2. Nghiên cứu/công trình liên quan và bảng đối chiếu để xác định khoảng trống cụ thể.
3. Cơ sở lý thuyết có trích dẫn cho lakehouse, mô hình, giao thức đánh giá và agent.
4. Phân tích yêu cầu, use case, kiến trúc, mô hình dữ liệu, giao diện và lựa chọn thiết kế.
5. Thiết kế thực nghiệm: dữ liệu, phiên bản, chọn mẫu, split, baseline, tham số, tài nguyên, chỉ số.
6. Kết quả gắn với từng câu hỏi nghiên cứu, thảo luận, đe dọa tính hợp lệ và kết luận.
7. Tài liệu tham khảo và phụ lục tái lập.

Mục 14.8.8 nói đã có cấu trúc chương chuẩn và 30 tài liệu tham khảo, nhưng trong tài liệu chính hiện đọc không thấy phần danh mục 30 nguồn tương ứng. Không dùng tuyên bố đó làm bằng chứng rằng hồ sơ đã đủ. Cần kiểm tra bản nộp thực tế, nguồn trích và quy định chính thức của khoa, thay vì chỉ kiểm tra Markdown.

Các kỹ thuật chuẩn như medallion, LSTM, recursive forecasting và walk-forward không tự thành “bốn đóng góp khoa học mới”. Nên viết “đóng góp của khóa luận” và chỉ rõ phần tác giả thiết kế/triển khai/kiểm chứng, so với thành phần kế thừa thư viện và phương pháp có sẵn.

### A03 — Tách thuyết trình khỏi tài liệu hướng dẫn; chốt số liệu có thời điểm

`presentation.md` còn 28 test, 917 mã và câu “~1,1 triệu dòng dữ liệu thật mỗi ngày”. Nếu 1,1 triệu là tổng lịch sử lưu trữ thì câu này nhầm tồn lượng với dữ liệu tăng hàng ngày. Không thay bằng một số hiện tại chưa đo lại.

Không nên nói hội đồng “chưa quen công nghệ thông tin” hay yêu cầu đọc chương từ điển trước. Có thể giải thích ngắn gọn thuật ngữ quan trọng mà vẫn coi người nghe là chuyên gia. Chuyển ví dụ tiệm phở, hướng dẫn từng file và nhật ký bug sang phụ lục hoặc tài liệu sử dụng.

Mỗi bảng kết quả nên ghi ngày đo, khoảng dữ liệu, cấu hình, cỡ mẫu, mã phiên bản và đường dẫn artifact. Các con số cũ có thể giữ nếu được đánh dấu snapshot lịch sử rõ ràng; không cần đuổi theo số live mỗi ngày.

### A04 — Tính tái lập và triển khai cần bớt phụ thuộc laptop hiện tại

Compose đang phụ thuộc đường dẫn WSL, gateway cố định và cấu hình máy cụ thể. README dùng `docker compose up -d` trong khi các service được đặt profile; cần kiểm thử lại hướng dẫn khởi động trên cấu hình sạch.

Chưa thấy workflow chạy pytest/build tự động; workflow ingest hiện bị vô hiệu hóa. Nên có CI cho kiểm thử độc lập hạ tầng, còn integration test cần dịch vụ thì ghi điều kiện riêng.

Model registry hiện ghi đè theo thư mục mã/model; cần version model, feature schema và hash/snapshot dữ liệu cho kết quả được đưa vào luận văn. Freeze gói thí nghiệm thay vì chỉ dựa vào seed 42.

Compose còn chứa giá trị mặc định dạng khóa API trong trường cấu hình Gemini. Chuyển sang biến môi trường bắt buộc hoặc secret và kiểm tra lịch sử chia sẻ; nếu là khóa thật đã chia sẻ thì thay khóa. Không sao chép giá trị đó vào báo cáo hoặc slide.

## 6. Bộ thí nghiệm gọn nhưng đủ sức bảo vệ

| Câu hỏi | Thí nghiệm | Bằng chứng cần lưu |
|---|---|---|
| RQ1: Nền tảng có xử lý dữ liệu đúng, nhất quán không? | Kiểm tra trùng, OHLC sai, ngày giao dịch, restatement; chạy lại pipeline | Số nhận/loại/ghi, checksum đầu ra, danh sách ngoại lệ |
| RQ2: Mô hình có hơn giữ nguyên giá không? | Naive + LR + ARIMA + LSTM trên giao các target_session | Bảng theo mã/horizon, chỉ số lỗi, DA, độ bất định |
| RQ3: Chiến lược có hơn mua và giữ trong phạm vi khảo sát không? | MA/RSI và buy-and-hold, cùng phiên và chi phí | Lợi nhuận, drawdown, Sharpe, excess return, số mã/cửa sổ, giả định thực thi |
| RQ4: Agent hỗ trợ truy vấn đúng đến đâu? | Bộ câu hỏi cố định, chấm theo tool và dữ liệu gốc | Tỉ lệ hoàn thành, sai số liệu/đơn vị, trace, latency, lỗi còn lại |
| RQ5: Hệ thống đáp ứng quy mô mục tiêu thế nào? | Đọc dữ liệu khi nhàn/batch; cache nóng/lạnh; ingest tăng dần | p50/p95, lỗi/timeouts, CPU/RAM, I/O và môi trường đo |

Các RQ là đề xuất viết lại, không phải kết quả đã đạt. Chỉ giữ RQ nằm trong phạm vi thực sự triển khai và đo được.

## 7. Thứ tự sửa và tiêu chí chốt bài

**Đợt 1 — sửa tính đúng:** R01–R04 trước, tiếp đến mapping sàn, lịch EOD và causal regime. Mỗi lỗi có kiểm chứng hồi quy tập trung vào bất biến nghiệp vụ. Giữ bản sao bằng chứng cũ để biết bảng nào cần tính lại.

**Đợt 2 — tính lại kết quả:** snapshot dữ liệu và mã, so naive trên cùng target_session, sinh lại báo cáo đa mã, tách live/backfill, công bố ngoại lệ và phạm vi suy luận. Nếu chưa đủ thời gian cho một phép đo thì hạ mức kết luận, không thay bằng câu khẳng định.

**Đợt 3 — hoàn thiện bài viết:** chốt phạm vi lakehouse, mục tiêu/RQ, nghiên cứu liên quan và trích dẫn; chuyển giải thích mã và nhật ký sửa lỗi ra phụ lục; đồng bộ README, Agent context, slide và bảng kết quả.

**Đợt 4 — diễn tập:** chạy từ hướng dẫn sạch; demo pipeline, dự báo/kiểm chứng, backtest có đối chứng và Agent; chuẩn bị giải thích cả kết quả tốt, kết quả không hơn baseline và các kiểm thử chưa chạy.

Có thể chốt nộp khi:

- Metrics được gọi là ngoài mẫu thực sự không dùng dữ liệu đã học, và target không vượt thời điểm thông tin cho phép.
- Mọi dự báo đã chấm có sai số khớp giá trị lưu và có phiên bản phát hành truy vết được.
- Chỉ báo nhiều bước dùng đúng lịch sử; ngày đích và lịch batch đúng theo thị trường.
- Bảng so mô hình cùng phiên, có naive; bảng theo sàn sinh từ mapping đã xác nhận.
- Bài viết có đủ các phần học thuật và nguồn tham khảo thực, mọi kết luận khớp bằng chứng.
- Số liệu, hướng dẫn chạy và phạm vi lakehouse thống nhất giữa tài liệu, giao diện và triển khai.

**Nhận định cuối của bản phản biện:** nên giữ và hoàn thiện hướng đề tài này. Điểm yếu chính không phải thiếu số lượng chức năng; đó là một số lỗi trong đường đánh giá và khoảng cách giữa tài liệu giải thích hệ thống với một lập luận học thuật có thể kiểm chứng.
