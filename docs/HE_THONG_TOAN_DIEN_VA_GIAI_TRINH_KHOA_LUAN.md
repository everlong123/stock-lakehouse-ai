# HỆ THỐNG STOCK LAKEHOUSE AI — GIẢI THÍCH TOÀN DIỆN CHO NGƯỜI MỚI BẮT ĐẦU

> **Tài liệu này dành cho bạn — người mới.**
> Mỗi khái niệm kỹ thuật đều được giải thích bằng **đời thường trước**, rồi mới nêu **tên thuật ngữ** sau. Bạn đọc theo thứ tự, không cần biết trước gì cả.
>
> Mọi con số trong tài liệu đều **đo thật trên máy thật, với dữ liệu thật trong MinIO**, ngày 06/11/2026.

> **Bạn muốn hiểu bằng HÌNH ẢNH trước?**
> Xem [`SO_DO_MINH_HOA.md`](./SO_DO_MINH_HOA.md) — 17 sơ đồ vẽ bằng ký hiệu (ASCII + Mermaid), mỗi sơ đồ có phần "đọc hình vẽ bằng lời đời thường" đi kèm.
>
> **Cập nhật 10/11/2026:** Kafka và Iceberg đã bị **gỡ khỏi dự án**. Hai hệ thống mới
> được mô tả ở **Phần 5B**: dự báo phiên kế tiếp tự động, và bộ đếm cron. Lý do gỡ
> nêu ở mục **2.4.1**.
>
> **Cập nhật 12/11/2026:** toàn bộ **hệ thống tin tức** (2 tầng lưu, provider,
> 4 endpoint, 4 tool AI, 1 trang giao diện, 2 lịch cron) đã bị **gỡ khỏi dự án**.
> Lý do và số liệu đo được nêu ở mục **5B.1**. Hệ thống còn lại là pipeline giá →
> chỉ báo → dự báo → backtest, đầy đủ và truy vết được.

---

# PHẦN 0 — ĐỌC TÀI LIỆU NÀY THẾ NÀO

## 0.1. Quy tắc của tài liệu

Mỗi mục trong tài liệu này có **3 phần**, luôn theo thứ tự này:

| Phần | Tên | Đọc như thế nào |
|---|---|---|
| **①** | **Hiểu đơn giản** | Giải thích bằng câu văn đời thường, ví dụ như kể chuyện. **Không có thuật ngữ chuyên môn.** Đọc phần này là hiểu vấn đề rồi. |
| **②** | **Thuật ngữ** | Bảng tra: cụm từ tiếng Anh / kỹ thuật, nghĩa là gì, và dùng ở đâu trong hệ thống. Đọc khi thấy từ lạ. |
| **③** | **Chi tiết kỹ thuật** | Code, công thức, số đo. Đọc khi cần hiểu sâu hoặc khi thầy hỏi. |

> **Bạn có thể dừng ở phần ①** và vẫn hiểu trọn vẹn hệ thống này. Phần ② và ③ là để dựng lên cho việc bảo vệ luận văn.

## 0.2. Bảng tra thuật ngữ (đọc khi thấy từ lạ)

### 0.2.1. Thuật ngữ về DỮ LIỆU

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Kho dữ liệu 3 tầng** | **Medallion Architecture** | Chia dữ liệu thành 3 mức: gốc → đã rửa → đã phân tích | Toàn bộ tầng dữ liệu |
| **Tầng gốc, giữ nguyên** | **Bronze layer** | Nơi lưu dữ liệu **y nguyên** vừa tải về, không sửa gì | `backend/app/lakehouse/bronze.py` |
| **Tầng đã rửa** | **Silver layer** | Dữ liệu đã được **làm sạch**: bỏ bản trùng, sửa lỗi, chuẩn hoá múi giờ | `lakehouse/silver.py` |
| **Tầng đã phân tích** | **Gold layer** | Dữ liệu đã **tính sẵn chỉ báo** và **gắn nhãn**, sẵn sàng đưa vào mô hình | `lakehouse/gold.py` |
| **Cột đặc trưng** | **Feature** | Một con số được tính ra để giúp mô hình dự đoán (ví dụ: trung bình động 20 phiên) | Gold layer có 75 cột loại này |
| **Cột đáp án** | **Target / Label** | Con số mô hình phải dự đoán (ví dụ: giá đóng cửa ngày mai) | 3 cột: `target_close_next`, ... |
| **Chia trước / sau** | **Train / Validation / Test split** | Chia dữ liệu thành 3 phần: học, chỉnh, kiểm tra | `forecasting/preprocessing.py` |
| **Dữ liệu học** | **Training set** | 70% dữ liệu dùng để mô hình học | — |
| **Dữ liệu chỉnh** | **Validation set** | 15% dùng để dừng sớm khi mô hình học tốt dần (early stopping) | — |
| **Dữ liệu kiểm tra** | **Hold-out / Test set** | 15% cuối cùng, **chưa từng** cho mô hình thấy, dùng để đo lần cuối | — |
| **Nhìn thấy tương lai** | **Look-ahead bias** | Lỗi kinh điển: dùng thông tin của ngày mai để quyết định hôm nay | Mục 13 giải thích kỹ |
| **Nhảy số** | **Shift** | Dịch cột dữ liệu sang trước/sau 1 hàng để tạo "đáp án" | `features/target_features.py` |
| **Bản ghi** | **Record / Row** | 1 dòng dữ liệu = 1 phiên giao dịch của 1 mã | — |
| **Chia nhỏ dữ liệu** | **Partition** | Chia file lớn thành nhiều file nhỏ theo mã + năm + tháng | Bronze: `symbol=AAPL/year=2016/month=10/...` |
| **Dòng truy vết** | **Lineage** | Ghi lại "dữ liệu này đến từ đâu, tải lúc nào" | `_lineage.json` mỗi mã |
| **Báo cáo chất lượng** | **Quality report** | Ghi lại đã loại bỏ bao nhiêu bản ghi rác, lý do gì | `_quality.json` mỗi mã |
| **Kiểm tra hợp lý** | **Plausibility check** | Kiểm tra giá có hợp lý không (ví dụ: không có giá âm, không nhân 1000 lần) | `lakehouse/plausibility.py` |
| **Chuẩn hoá phiên** | **Canonicalize sessions** | Đưa mọi phiên giao dịch về một mốc thời gian thống nhất | `lakehouse/session.py` |
| **Cột nguồn** | **Provenance / Source column** | Ghi tên nhà cung cấp dữ liệu đã dùng | Cột `source` trong Bronze |

### 0.2.2. Thuật ngữ về LƯU TRỮ & HẠ TẦNG

| Từ dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Kho chứa đồ trên mạng** | **Object Storage (MinIO / S3)** | Nơi lưu file Parquet, giống Google Drive nhưng cho dữ liệu | Bucket `stock-bronze`, `stock-silver`, `stock-gold` |
| **Định dạng file cột** | **Parquet** | Định dạng file nén, đọc rất nhanh, chỉ đọc đúng cột cần | Toàn bộ dữ liệu lakehouse |
| **Cơ sở dữ liệu quan hệ** | **MySQL / RDBMS** | Nơi lưu *lịch sử* & *metadata* (không lưu dữ liệu lớn) | `backtest_runs`, `model_runs`, ... |
| **Bảng tra cứu metadata** | **Metadata catalog** | Danh bạ biết dữ liệu nằm ở đâu, có bao nhiêu | `alembic/`, `app/database/` |
| **Lịch chạy tự động** | **Cron / Scheduler** | Đồng hồ báo giờ gọi script batch theo lịch viết trong file | `backend/crontab`, `scripts/run_scheduled_job.py` |
| **Bảng lưu dự báo** | **Predictions table** | Nơi lưu dự báo cho phiên chưa xảy ra, có ngày và tên mô hình | `database/models/prediction.py` |
| **Tính toán phân tán** | **Apache Spark** | Công cụ xử lý dữ liệu lớn, chạy song song nhiều core | `USE_SPARK=true` (mặc định tắt) |
| **Xử lý việc nặng tách riêng** | **Process pool** | Chạy việc nặng ở tiến trình con, không làm nghẽn tiến trình chính | `core/heavy_worker.py` |
| **Khóa ở nhiều luồng** | **GIL (Global Interpreter Lock)** | Python chỉ cho 1 luồng chạy code Python cùng lúc → nhiều thread sẽ tranh nhau | Lý do dùng Process |
| **Cổng ưu tiên người dùng** | **Request gate** | Cho công việc nền tạm dừng khi có người đang dùng hệ thống | `core/request_gate.py` |
| **Bộ nhớ đệm** | **Cache (LRU + TTL)** | Giữ kết quả đọc gần đây để lần sau khỏi tải lại | `services/market_service.py` |
| **Cắt bảng theo thời gian** | **Windowed read** | Chỉ đọc các tệp chứa được khoảng ngày người dùng hỏi | `lakehouse/parquet_manager.py` |
| **Ghi thêm theo phần đổi** | **Incremental write** | Chỉ ghi lại các tệp có thể đã thay đổi, bỏ qua các tệp cũ | `lakehouse/parquet_manager.py` |
| **Nhìn về quá khứ** | **Causal feature** | Chỉ báo chỉ dùng dữ liệu trước đó, không dùng dữ liệu tương lai | `features/advanced_features.py` |

### 0.2.3. Thuật ngữ về MÔ HÌNH HỌC MÁY

| Từ dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Dòng thẳng đơn giản** | **Linear Regression** | Dùng đường thẳng dự đoán giá từ nhiều chỉ báo | Baseline để so sánh |
| **Mô hình chuỗi thời gian** | **ARIMA** | Dự đoán giá phiên sau bằng cách nhìn lại mấy phiên trước + xu hướng | `forecasting/arima.py` |
| **Mạng lưới nhớ dài hạn** | **LSTM** | Mạng nơ-ron học được mẫu hình trong chuỗi dài | `forecasting/lstm.py` |
| **Cửa sổ nhìn lại** | **Sequence length** | LSTM mỗi lần dự đoán nhìn lại 60 phiên | `lstm_sequence_length=60` |
| **Chuẩn hoá giá trị** | **Scaler (MinMaxScaler)** | Ép mọi con số về khoảng 0–1 để mạng học dễ hơn | `feature_scaler`, `target_scaler` |
| **Dừng sớm** | **Early stopping** | Dừng huấn luyện khi chất lượng trên tập validation không còn tốt hơn | `patience=5` |
| **Đo sai số bình quân** | **MAE (Mean Absolute Error)** | Trung bình sai số tuyệt đối, tính bằng đơn vị tiền | Đánh giá dự báo |
| **Đo sai số bình phương** | **RMSE** | Giống MAE nhưng phạt nặng hơn với giá trị lệch lớn | Đánh giá dự báo |
| **Sai số phần trăm** | **MAPE** | Sai số tính theo % — dễ nói với người khác | Đánh giá dự báo |
| **Đúng hướng** | **Directional Accuracy** | % lần đoán đúng giá tăng hay giảm | Đánh giá dự báo |
| **Dự đoán nhiều bước** | **Multi-step forecasting** | Dự đoán cả 5 phiên tới, không chỉ 1 phiên | `forecasting/multistep.py` |
| **Dự đoán lặp lại** | **Recursive / Rolling-origin** | Dùng chính kết quả dự đoán bước trước làm đầu vào cho bước sau | `multistep.py` |
| **Mô hình tương đối** | **Relative target** | Dự đoán *tỷ lệ* thay đổi thay vì *mức giá* | Đóng góp chính của LSTM |
| **Trạng thái mô hình** | **State-space update** | ARIMA "học" thêm dữ liệu mới mà không cần train lại | `model.append(actual, refit=False)` |

### 0.2.4. Thuật ngữ về BACKTEST & ĐÁNH GIÁ

| Từ dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Chơi lại quá khứ** | **Backtest** | Giả vờ là ngày hôm đó, chạy chiến lược trên dữ liệu cũ | `backtesting/engine.py` |
| **Quy tắc ra quyết định** | **Strategy** | Cách quyết định mua/bán (vd: MA ngắn cắt lên MA dài) | `backtesting/strategies/` |
| **Tín hiệu** | **Signal** | Lệnh "mua" (+1) hoặc "bán" (−1) mà chiến lược phát ra | — |
| **Mua ngày hôm sau** | **Next-bar execution** | Tín hiệu hôm nay, lệnh khớp **ngày mai** | `signals.shift(1)` |
| **Phí môi giới** | **Transaction fee** | % phí mỗi lần mua/bán (mặc định 0.1%) | `transaction_fee` |
| **Trượt giá** | **Slippage** | Giá thực tế lệch khỏi giá báo (mặc định 0.05%) | `slippage` |
| **Tiền mặt + cổ phiếu** | **Portfolio** | Sổ sách mô phỏng: đang có bao nhiêu tiền, bao nhiêu cổ phiếu | `backtesting/portfolio.py` |
| **Vòng đời giao dịch** | **Trade lifecycle** | Mua → giữ → bán, tính lãi/lỗ cả vòng | `Portfolio.buy()` / `sell()` |
| **Đường vốn tài sản** | **Equity curve** | Đường biểu diễn giá trị tài khoản theo thời gian | `equity_curve` |
| **Lỗ lớn nhất** | **Maximum Drawdown** | Mức sụt giảm lớn nhất từ đỉnh | `metrics.py` |
| **Chỉ số rủi ro/lợi nhuận** | **Sharpe Ratio** | Lợi nhuận trên mỗi đơn vị rủi ro | `metrics.py` |
| **Tỷ lệ thắng** | **Win Rate** | % giao dịch có lãi | `metrics.py` |
| **Kiểm định lăn theo thời gian** | **Walk-Forward Validation** | Lặp lại: train một đoạn → test đoạn sau → trượt tiếp | `backtesting/walk_forward.py` |
| **Cửa sổ** | **Window** | Một cặp (train, test) trong walk-forward | — |
| **Kiểm tra ngoài mẫu** | **Out-of-sample** | Đánh giá trên dữ liệu mô hình **chưa từng thấy** | — |
| **Quá khứ hóa** | **Overfitting** | Mô hình khớp dữ liệu train quá đẹp, nhưng hỏng trên dữ liệu mới | Đo bằng `overfitting_ratio` |
| **Tỷ lệ quá khứ hóa** | **Overfitting Ratio** | Lợi nhuận trên train chia cho lợi nhuận trên test (đã chuẩn hoá) | — |
| **Tính nhất quán** | **Return Consistency** | % cửa sổ test sinh lời | — |
| **Đường cơ sở** | **Buy-and-Hold baseline** | Mua đầu kỳ giữ cuối kỳ, cùng phí, cùng cách khớp lệnh | `backtesting/benchmark.py` |
| **So sánh cặp** | **Paired comparison** | So sánh hai bên trên đúng những phiên giống nhau rồi lấy hiệu | `backtesting/walk_forward.py` |
| **Đường cơ sở** | **Baseline** | Mô hình đơn giản nhất, dùng làm mốc so sánh | Linear Regression |

### 0.2.5. Thuật ngữ về DỰ BÁO & KIỂM CHỨNG

| Từ dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Ghi trước, chấm sau** | **Forecast → score loop** | Dự báo được lưu trước phiên, điểm được chấm sau phiên | `services/forecast_scoring.py` |
| **Sổ tay dự báo** | **Verification ledger** | Bảng `predictions` — mỗi dòng là một dự báo kèm kết quả thật | `database/models/prediction.py` |
| **Chấm điểm** | **Scoring pass** | So dự báo với giá đóng cửa thật đọc từ tầng Gold | `services/forecast_scoring.py` |
| **Sai số tuyệt đối** | **MAE (Mean Absolute Error)** | Trung bình của `\|giá dự báo − giá thật\|` | `database/repositories/prediction_repository.py` |
| **Sai số tương đối** | **Relative error** | Sai số tuyệt đối chia cho giá neo, để so sánh giữa các mã | `services/forecast_scoring.py` |
| **Trung vị sai số** | **Median error** | Sai số của một dự báo **điển hình** — không bị vài mã giá rất nhỏ kéo lệch | `database/repositories/prediction_repository.py` |
| **Đúng hướng** | **Directional accuracy** | Tỉ lệ phiên mà dự báo đúng chiều đi của thị trường | `services/forecast_scoring.py` |
| **Giá neo** | **reference_close** | Giá đóng cửa của phiên **trước** phiên đích — mốc đo hướng đi | `services/forecast_scoring.py` |
| **Dự báo đã công bố** | **Published forecast** | Dự báo nguồn `auto_eod_batch` — ghi trước phiên mở cửa | `services/universe_forecast.py` |
| **Dự báo tái dựng** | **Backfilled forecast** | Dự báo nguồn `backfill_walk_forward` — mô hình tái chạy sau trên tập hold-out | `services/forecast_backfill.py` |
| **Đường đi nhẹ** | **Light forecast path** | Đường tính nhanh cho batch toàn bộ mã, **cho ra kết quả y hệt** đường đầy đủ | `forecasting/light_forecast.py` |
| **Lịch giao dịch của mã** | **Symbol trading calendar** | Các ngày mà mã đó thực sự giao dịch, **suy ra từ lịch sử Gold của chính nó** | `forecasting/sessions.py` |
| **Ngày lễ cố định** | **Fixed-date holiday** | Ngày vắng mặt trong nhiều năm khác nhau — ví dụ 25/12 | `forecasting/sessions.py` |
| **Ngày lễ di động** | **Movable holiday** | Ngày lễ định nghĩa theo thứ trong tháng — ví dụ "thứ Hai thứ ba của tháng Một" | `forecasting/sessions.py` |
| **Ngày lễ quan sát** | **Observed holiday** | Ngày lễ rơi vào cuối tuần nên sàn đóng cửa vào **ngày khác** — học riêng cho từng ngày lễ | `forecasting/sessions.py` |
| **Ngày bị kẹp** | **Squeezed day** | Ngày giao dịch nằm giữa hai ngày nghỉ; sàn Nhật đóng cửa cả ngày này | `forecasting/sessions.py` |
| **Huấn luyện toàn bộ mã** | **Universe training** | Train mô hình cho mọi mã có dữ liệu Gold | `forecasting/universe_training.py` |

### 0.2.6. Thuật ngữ về FRONTEND

| Từ dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Trang web** | **Page / Route** | Mỗi màn hình có 1 đường dẫn | 7 trang trong `frontend/src/pages/` |
| **Gọi dữ liệu từ server** | **React Query / TanStack Query** | Thư viện tự quản lý: gọi API, cache, báo lỗi, tự làm mới | `frontend/src/hooks/` |
| **Khoá cache** | **queryKey** | Chuỗi định danh cache, ví dụ `["forecast-compare", "AAPL"]` | — |
| **Vẽ biểu đồ** | **Recharts** | Thư viện vẽ chart SVG cho React | `components/charts/` |
| **Đường gọi API** | **axios client** | Bộ gọi HTTP có timeout & xử lý lỗi | `api/client.ts` |
| **Bọc kết quả trả về** | **API envelope** | Mọi response có cùng cấu trúc `{success, data, message}` | Toàn bộ API |
| **Chuyển ngôn ngữ** | **i18n** | Hỗ trợ tiếng Việt / tiếng Anh | `lib/i18n.tsx` |
| **Khung giải thích** | **Explainer** | Khung gập mở giải thích thuật ngữ bằng văn bản đời thường | `components/common/Explainer.tsx` |
| **Vẽ chung một đường** | **Series** | Trong chart, mỗi đường là một "series" | `actual` / `predicted` / `forecast` |

## 0.3. Bốn câu hỏi lớn của cả hệ thống

Nếu chỉ nhớ 4 câu hỏi này thì bạn đã hiểu cả hệ thống:

| # | Câu hỏi | Trả lời ngắn | Xem ở chương |
|---|---|---|---|
| 1 | **Dữ liệu đến từ đâu, có thật không?** | Từ Yahoo Finance & SSI iBoard. Có hệ thống ghi lại nguồn + thời điểm tải. **Không có dữ liệu giả ở bất kỳ đâu.** | Chương 3–4 |
| 2 | **Mô hình dự đoán có đáng tin không?** | Được đo trên 15% dữ liệu mô hình **chưa từng thấy**, bằng 4 bộ chỉ số chuẩn. Kết quả **trung thực** dù không "ấn tượng". | Chương 6 |
| 3 | **Chiến lược có ăn không?** | Được kiểm tra bằng **walk-forward**: 159 cửa sổ trượt trên AAPL, và mở rộng lên **101 mã / 13 sàn / 3.687 cửa sổ** với **đường cơ sở mua & giữ** đo song song. Kết quả: **chiến lược không vượt được đường cơ sở** — và điều đó được báo cáo nguyên vẹn. | Chương 7–8 |
| 4 | **Web và dữ liệu có khớp nhau không?** | Khớp. Web **chỉ** đọc từ MinIO, không có đường nào khác, và có script tự kiểm tra. | Chương 11.5 |
| 5 | **Hệ thống có tự chạy không?** | Có. Một container `cron` chạy lịch nằm trong file `backend/crontab`: batch cuối ngày chạy **2 lần/ngày** (sau khi NYSE đóng cửa và sau khi HOSE đóng cửa). Mọi lần chạy đều ghi log có mốc thời gian. | Phần 5B.5 |

---

# PHẦN 1 — HỆ THỐNG NÀY LÀM GÌ

## 1.1. Hiểu đơn giản

Tưởng tượng bạn muốn nghiên cứu "chiến lược mua khi đường trung bình 20 ngày cắt lên đường trung bình 50 ngày có sinh lời không?".

Bạn cần 4 thứ:

1. **Dữ liệu giá lịch sử thật** của hàng nghìn mã cổ phiếu, càng nhiều năm càng tốt.
2. **Một nơi lưu dữ liệu đó** gọn gàng, không bị trùng lặp, không bị bẩn.
3. **Công cụ mô phỏng** — cho bạn "chơi lại" quá khứ với chiến lược của bạn, và tính xem bạn lãi hay lỗ.
4. **Một giao diện đẹp** để thầy/cô nhìn thấy kết quả.

Hệ thống này là **cả 4 thứ trong một**, và làm thêm 3 việc mà đồ án sinh viên thường bỏ qua:

- **Truy vết được**: biết con số này đến từ đâu, tải lúc nào.
- **Kiểm chứng được**: mô hình được đo trên dữ liệu nó chưa từng thấy.
- **Báo cáo cả kết quả xấu**: nếu chiến lược không ăn, hệ thống nói thẳng là không ăn.

## 1.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **End-to-end pipeline** | Chuỗi xử lý liền mạch từ dữ liệu thô → kết quả cuối, không có bước thủ công chen giữa |
| **Lakehouse** | Kho dữ liệu kết hợp ưu điểm của "data lake" (file thô, rẻ) và "data warehouse" (đã cấu trúc, hữu ích) |
| **Prototype học thuật** | Hệ thống xây để **nghiên cứu và trình bày**, không phải để giao dịch tiền thật |

## 1.3. Chi tiết: 3 tầng của hệ thống

| Tầng | Làm gì | Công nghệ |
|---|---|---|
| **Nền tảng dữ liệu** | Nạp → rửa → tính chỉ báo. Có truy vết nguồn & chấm điểm chất lượng | MinIO, Parquet, MySQL, cron |
| **Bộ phân tích** | 3 mô hình dự báo + 2 chiến lược backtest + walk-forward | FastAPI, statsmodels, PyTorch, pandas |
| **Giao diện & Trợ lý AI** | 7 trang web + trợ lý AI gọi được 17 công cụ backend | React, TypeScript, TanStack Query, Recharts, Gemini |

## 1.4. Chi tiết: 4 đóng góp khoa học chính

1. **Kho dữ liệu 3 tầng có truy vết & cổng chất lượng** — biết dữ liệu đến từ đâu, và biết đã loại bỏ bao nhiêu rác.
2. **Khung backtest trung thực** — lệnh khớp ngày hôm sau, có phí + trượt giá, sổ sách khớp tuyệt đối.
3. **Walk-forward validation đa mã + đường cơ sở** — đánh giá chiến lược ngoài mẫu trên 101 mã / 13 sàn, so với mua & giữ trên cùng các phiên.
4. **Dự báo đa bước đệ quy** — biến mô hình chỉ dự đoán 1 ngày thành bộ dự báo 5 ngày thật sự.

## 1.5. Chi tiết: nguyên tắc bất di bất dịch

> **Không một con số nào trên màn hình là dữ liệu giả.**

- File `services/market_service.py` **không có** đường dẫn dự phòng về dữ liệu mẫu. Mã không có dữ liệu → ném lỗi `NotFoundError` → giao diện hiện "không có dữ liệu cho mã này".
- Mọi con số đều truy vết được tới MinIO hoặc MySQL.
- Có 3 script kiểm chứng độc lập: `backend/tests/verify_real_data.py`, `backend/scripts/check_layer_divergence.py`, `backend/scripts/check_unserved_symbols.py`.

### 1.5.1. Chi tiết: luật "Real Data Only" được ép bằng rule, không phải bằng lời hứa

Nguyên tắc trên được cài thành **rule máy đọc được** tại `.cursor/rules/no-fake-data.mdc`
(`alwaysApply: true`), áp dụng cho `backend/**`, `frontend/src/**`, `scripts/**`:

| Cấm | Ví dụ bị chặn |
|---|---|
| Server bịa dữ liệu | `scripts/mock_api.py` (đã **xoá** — file này từng sinh nến sóng `math.sin` + `random.uniform` cho frontend) |
| Sinh OHLCV ngẫu nhiên | `random.uniform(-1.6, 1.7)`, `np.random.normal(...)` trong pipeline |
| Metric bịa | `sharpe_ratio: 1.34` ghi cứng khi chưa chạy backtest thật |
| Indicator giả | `rsi = 45 + sin(i/9)*28` |
| Fallback về số 0 để "cho có" | `change_pct = 0.0` thay vì `null` (UI phải hiện `—`) |
| Đẩy bar tự chế vào Bronze | `POST /api/v1/stream/ingest` — cổng này đã bị **xoá hẳn** ngày 11/11/2026 cùng toàn bộ đường dẫn realtime |

Khi hạ tầng không chạy, quy tắc là **báo cáo trung thực** endpoint nào lỗi và vì sao —
không dựng server giả để "cho UI chạy".

> **Đo ngày 10/11/2026:** quét toàn repo không còn chỗ sinh dữ liệu ngẫu nhiên nào trong
> `backend/app` (ngoại trừ jitter/backoff hợp lệ trong `agent/llm_client.py`) và không
> còn chỗ nào hard-code số ở `frontend/src`.

---

# PHẦN 2 — BỐ CỤC TỔNG THỂ

> Sơ đồ: [1. Tổng thể hệ thống — 3 khối](./SO_DO_MINH_HOA.md#1)

## 2.1. Hiểu đơn giản

Hệ thống gồm **3 khối** nối với nhau bằng **đường dẫn web** (REST API):

```
   TRÌNH DUYỆT                    SERVER PYTHON                   NƠI LƯU
  ┌──────────┐   gọi qua đường   ┌──────────────┐            ┌────────────  ┐
  │  React   │────dẫn JSON──────►│   FastAPI    │──ghi file─►│   MinIO      │
  │  (7 trang│◀────JSON──────────│  (12 nhóm API│            │  (dữ liệu)   │
  │  web)    │                   │  + dịch vụ)  │            └────────────  ┘
  └──────────┘                   │              │            ┌────────────  ┐
                                 │              │───────────►│   MySQL      │
                                 └──────────────┘            │ (lịch sử)    │
                                                               └────────────┘
```

**Điểm quan trọng:** trình duyệt **không** tự tính toán gì cả. Nó chỉ hỏi server, rồi vẽ lại kết quả. Một logic chỉ nằm ở một chỗ → không bao giờ xảy ra tình trạng biểu đồ và bảng số liệu mâu thuẫn nhau.

## 2.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **REST API** | Cách web gọi server: `GET` để xem, `POST` để gửi lệnh |
| **JSON envelope** | Bọc mọi kết quả trả về trong một vỏ thống nhất `{success, data, message}` |
| **CORS** | Quy tắc cho phép trang web ở cổng này gọi server ở cổng khác |
| **Microservice split** | Tách code thành nhiều "phần" (data / backtesting / forecasting) để dễ bảo trì |

## 2.3. Chi tiết: vì sao tách Frontend / Backend bằng REST, không gộp làm một

| Quyết định | Lý do |
|---|---|
| **REST, không GraphQL** | Hệ thống có 61 endpoint với kiểu dữ liệu rất khác nhau (OHLCV, chỉ số, sàn giao dịch, báo cáo tài chính, dự báo, backtest). GraphQL thêm một tầng trừu tượng mà không giải quyết vấn đề nào; REST + TypeScript types là đủ và dễ kiểm thử. |
| **Backend là nguồn sự thật duy nhất** | FE không tự tính lại chỉ báo hay chỉ số. Một logic, một nơi sửa. |
| **Bọc kết quả thống nhất** | FE chỉ cần một nhánh xử lý lỗi duy nhất; `message` do server viết bằng tiếng Việt có ngữ cảnh (thay vì câu lạnh lùng mặc định của axios). |

## 2.4. Chi tiết: trạng thái thật (đo ngày 10/11/2026)

```
Backend API  : online
MySQL        : connected      (container Docker, qua relay 127.0.0.1:13307)
MinIO (S3)   : connected      (storage_backend = minio, qua relay 127.0.0.1:19000)
Scheduler    : cron -f        (container scheduler, lịch ở backend/crontab)
Data Source  : multi_source
AI Agent     : gemini_free
```

> **Đo ngày 10/11/2026:** dòng `Iceberg REST` và dòng `Kafka` đã bị **xoá khỏi bảng
> trạng thái** vì hai thành phần đó **không còn tồn tại** trong dự án. Chúng đã bị gỡ
> hoàn toàn ngày 10/11/2026 — xem mục 2.4.1.

```
Số record theo tầng (đếm từ MinIO, Đo ngày 10/11/2026):
  Bronze : 115.321
  Silver : 106.662
  Gold   : 105.605
```

> **Đọc số liệu này:** Bronze ≈ Silver ≈ Gold là **đúng**. Nếu Gold nhỏ hơn nhiều (ví dụ 30%) nghĩa là tầng làm sạch đang loại bỏ dữ liệu hợp lệ — đây là tín hiệu cảnh báo. Script `check_layer_divergence.py` tự động kiểm tra đúng điều đó.

### 2.4.1. Chi tiết: Kafka và Iceberg đã bị GỠ khỏi dự án (ngày 10/11/2026)

**Trước 10/11/2026** dự án có một broker Kafka chạy trong Docker
(`stock-lakehouse-kafka`) và một Iceberg REST Catalog (`stock-lakehouse-iceberg-rest`).
Cả hai **đã bị gỡ khỏi dự án ngày 10/11/2026**.

**Vì sao gỡ — nói thẳng, không vòng vo:**

| Lý do | Giải thích đời thường |
|---|---|
| **Một bản sao dữ liệu thừa** | Kafka giữ dữ liệu trong "topic" để rồi đẩy sang Bronze. Nhưng Bronze đã bất biến và không ai đọc từ topic — cùng một dữ liệu bị lưu hai lần, và hai lần có thể lệch nhau. Iceberg catalog cũng lưu thêm manifest/metadata cho **cùng dữ liệu** mà Parquet đã lưu. |
| **Ít một JVM phải vận hành** | Cả broker lẫn catalog đều là container Java. Mỗi JVM là một thứ phải giám sát, phải cấp RAM, phải khởi động lại khi chết. |
| **Không có nhu cầu thực tế** | Đồ án nghiên cứu dữ liệu **daily**. Batch EOD chạy 2 lần/ngày (NYSE + HOSE) là đủ. Iceberg mạnh ở cập nhật/xoá từng dòng trên object storage — nhưng pipeline này **append-only**: Bronze không bao giờ bị sửa, Silver/Gold được dựng lại. |
| **Không có người trực** | Topic realtime đòi hỏi một consumer chạy liên tục 24/7. Không có bộ đếm cron thì container chết là dữ liệu im lặng, không ai biết. |

**Thay bằng gì:** container `scheduler` chạy `cron -f` với lịch nằm trong **file trong
repo** (`backend/crontab`), được Docker giám sát bằng `restart: unless-stopped`, và mỗi
lần chạy đều ghi log có ngày giờ vào `backend/logs/scheduled_jobs.log`.

Xem chi tiết ở Phần 5B.4 (dự báo tự động) và Phần 5B.5 (bộ đếm cron) của
tài liệu này, và mục 7 của [`architecture.md`](./architecture.md).

> **Cách trả lời khi thầy hỏi "vì sao bỏ, đồ án còn đủ hấp dẫn không?":**
> *"Đồ án nghiên cứu dữ liệu daily ở quy mô ~10^5 partition. Kafka và Iceberg giải quyết
> những bài toán mà đồ án này không có: streaming realtime không ai dùng, và cập nhật từng
> dòng cho một pipeline append-only. Giữ chúng nghĩa là thêm 2 JVM phải vận hành và 2 bản
> sao metadata để đổi lấy 0 phần tính năng dùng được. Phần thay thế không kém: lịch cron
> nằm trong version control, và batch EOD tự động dự báo phiên kế tiếp rồi ghi vào MySQL."*

### 2.4.2. Chi tiết: đường đi từ Windows vào hạ tầng Docker (đo ngày 10/11/2026, cập nhật 17/11/2026)

Docker engine chạy **native trong WSL2** (`Ubuntu-24.04`), không phải Docker Desktop.
MinIO dùng `network_mode: host` nên Windows không vào được ổn định bằng
`127.0.0.1:9000` (WSL localhost-forwarding chập chờn, từng trả `WinError 10061`).

Đường đi ổn định là **relay của chính dự án** — `backend/scripts/relay_ports.py`:

```bash
# Chạy BÊN TRONG WSL:
python3 backend/scripts/relay_ports.py 13307:3307 19000:9000
```

| Dịch vụ | Cổng trên Windows | Cổng thật trong WSL |
|---|---|---|
| MySQL | `127.0.0.1:13307` | 3307 (container) |
| MinIO | `127.0.0.1:19000` | 9000 (container, host network) |

Kiểm tra dữ liệu thật trước khi tin (Đo ngày 10/11/2026):

```powershell
python -c "from minio import Minio; c=Minio('127.0.0.1:19000',access_key='minioadmin',secret_key='minioadmin',secure=False); print([b.name for b in c.list_buckets()])"
# -> ['stock-bronze', 'stock-silver', 'stock-gold', ...]
```

### 2.4.3. Hai nguyên nhân gốc khiến hạ tầng "tự chết" (đo ngày 17/11/2026)

Trong lúc kiểm chứng lại toàn bộ luồng, đã phát hiện **hai nguyên nhân độc lập**
khiến MySQL/MinIO không truy cập được, cả hai đều không liên quan đến code ứng dụng:

**Nguyên nhân 1 — WSL bị teardown khi không còn client nào giữ session.**

*Triệu chứng:* `docker ps` luôn hiện `"Up N seconds"` với N nhỏ; MySQL trả
`WinError 10061`; `backend/logs` ghi `MinIO initialization failed ... Falling back
to local storage` — tức backend âm thầm dùng **filesystem cục bộ** thay vì MinIO,
nên `GET /api/v1/stocks/AAPL/latest` trả 404 dù dữ liệu có thật.

*Vì sao xảy ra:* WSL2 **tắt VM khi client `wsl.exe` cuối cùng thoát**. Đây là
hành vi có sẵn của WSL, không phải lỗi Docker. Mỗi lần VM tắt, systemd dừng
`docker.service`, container bị dừng theo, và lần khởi động lại kế tiếp chỉ khởi
động lại container chứ **không** khởi động lại relay nếu relay không chạy dưới
systemd. Script `backend/scripts/check_wsl_keepalive.sh` đã ghi lại đúng cơ chế
này từ trước (mục "What actually goes wrong (measured 2026-10-26)").

*Fix:* bật lại Scheduled Task giữ session:

```powershell
Enable-ScheduledTask -TaskName "WSL-Distro-Keepalive"
Start-ScheduledTask -TaskName "WSL-Distro-Keepalive"
Get-ScheduledTask -TaskName "WSL-Distro-Keepalive"   # -> State: Running
```

Task này chạy `backend/scripts/wsl_keepalive.vbs` → `wsl.exe ... sleep infinity`,
giữ **một session WSL luôn mở từ phía Windows**. Sau khi bật: `wsl.exe` client
count = 2 (thay vì 0), và container giữ nguyên uptime.

**Nguyên nhân 2 — Scheduled Task bị `Disabled` nên fix trên không bao giờ chạy.**

Đây là chi tiết dễ bỏ sót nhất: task **vẫn còn trong hệ thống**, tên đúng, kịch
bản đúng, nhưng ở trạng thái `Disabled` thì Windows không kích hoạt nó. Kiểm tra
bằng:

```powershell
Get-ScheduledTask -TaskName "WSL-Distro-Keepalive" | Select TaskName, State
# Bị: State = Disabled     <- nguyên nhân thật
# Đúng: State = Running
```

*Fix:* `Enable-ScheduledTask` + `Start-ScheduledTask` (xem trên).

**Bằng chứng (đo ngày 17/11/2026):**

| Kiểm tra | Trước fix | Sau fix |
|---|---|---|
| `WSL-Distro-Keepalive` | `Disabled` | `Running` |
| Số client `wsl.exe` | 0 | 2 |
| `docker.service` khởi động lại trong 10 phút | 3 lần | 0 lần |
| Container MySQL | `Up 3 seconds` liên tục | `Up 49 seconds`, `healthy` |
| Backend log | `Falling back to local storage` | `Using MinIO storage backend` |
| `GET /api/v1/stocks/AAPL/latest` | 404 | 200, `close: 352,78`, `source_layer: gold` |
| `GET /api/v1/forecast/accuracy` | 200 nhưng rỗng | 200, **45.631** dòng đã chấm |

**Điểm mấu chốt cho hội đồng:** khi backend fallback sang local storage, nó
**không báo lỗi** — nó vẫn trả HTTP 200 với dữ liệu *rỗng*. Đó là lý do lỗi này
lâu ngày bị hiểu nhầm là "mất dữ liệu". Dữ liệu **không hề mất**; chỉ có backend
đang trỏ nhầm nơi đọc.

### 2.4.4. Relay chạy dưới systemd + endpoint file tự phát hiện IP

Để relay **tự phục hồi** sau mỗi lần WSL restart (thay vì phải chạy tay), relay
được đăng ký thành systemd unit `stock-relay.service`:

```ini
[Service]
WorkingDirectory=/mnt/d/School/kltn/stock-lakehouse-ai
ExecStart=/usr/bin/python3 backend/scripts/relay_ports.py 13307:3307 19000:9000
Restart=always
RestartSec=3
```

Kèm theo, `backend/scripts/start_relay.py` tự dò IP của VM và ghi ra file
`/tmp/relay_endpoints.txt`, để phía Windows biết cần trỏ tới đâu:

```bash
wsl -d Ubuntu-24.04 -u root -e bash -c \
  "python3 backend/scripts/start_relay.py --no-spawn"
# -> /tmp/relay_endpoints.txt
#    13307=172.29.156.49:13307 -> 127.0.0.1:3307
#    19000=172.29.156.49:19000 -> 127.0.0.1:9000
```

> **Vì sao trỏ theo IP WSL chứ không `127.0.0.1`?** Đo ngày 17/11/2026: gọi
> `127.0.0.1:13307` từ Windows bị từ chối (`WinError 10061`) trong khi gọi
> `172.29.156.49:13307` **thông** — dù hai đường đều dẫn tới cùng một listener
> trong VM. Đây là hạn chế của WSL localhost-forwarding trên máy này, không phải
> lỗi của relay. Đổi lại: **IP WSL đổi mỗi lần `wsl --shutdown`**, nên sau mỗi
> lần restart phải sửa lại `MYSQL_HOST` / `MINIO_ENDPOINT` trong
> `backend/.env.local` theo giá trị lấy được từ file ở trên.

---

# PHẦN 3 — DỮ LIỆU ĐI ĐÂU VÀ ĐƯỢC XỬ LÝ THẾ NÀO

> Sơ đồ: [2. Luồng dữ liệu 3 tầng](./SO_DO_MINH_HOA.md#2)

## 3.1. Hiểu đơn giản: vì sao chia 3 tầng

Tưởng tượng bạn có một tấm bánh. Bạn có thể:

- **Giữ nguyên tấm bánh** (tầng Bronze) — để phòng khi cần làm lại từ đầu.
- **Cắt bỏ phần cháy, rửa sạch, xếp lại** (tầng Silver) — dùng để tính toán.
- **Nghiền thành bột, trộn với nguyên liệu khác thành món ăn** (tầng Gold) — dùng để đưa vào mô hình.

**Nếu gộp tất cả làm một**, bạn sẽ gặp 3 vấn đề:

1. Không thể **tính lại chỉ báo** khi thuật toán đổi mà không phải tải lại từ Internet.
2. Không biết bản ghi nào **đã bị xử lý** và bản nào **còn rác**.
3. Một lỗi trong code sẽ **phá hỏng luôn dữ liệu gốc** — không khôi phục được.

Đó là lý do có 3 tầng. Tầng Bronze được thiết kế **bất biến** (chỉ thêm, không sửa) — nó là chốt chặn cuối cùng.

## 3.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Bronze / Silver / Gold** | Ba tầng: gốc → đã rửa → đã phân tích |
| **Append-only / Immutable** | Chỉ thêm, không sửa, không xoá |
| **Partition** | Chia file lớn thành file nhỏ theo mã + năm + tháng |
| **Deduplication** | Bỏ bản ghi trùng lặp |
| **Quality gate** | Cổng kiểm tra chất lượng — dữ liệu xấu bị chặn trước khi đi tiếp |
| **Idempotent** | Chạy lại bao nhiêu lần cũng cho kết quả giống nhau |

## 3.3. Chi tiết: tầng Bronze — lớp ghi thô

**Cấu trúc lưu trữ** (bucket MinIO `stock-bronze`):

```
s3://stock-bronze/
  symbol=AAPL/
    year=2016/month=10/part-0.parquet
    year=2016/month=11/part-0.parquet
    ...
    year=2026/month=11/part-0.parquet
    _lineage.json          ← nguồn, khoảng thời gian, số bản ghi
```

**Cấu trúc bản ghi** (`BRONZE_SCHEMA` trong `lakehouse/bronze.py`):

| Cột | Kiểu | Ý nghĩa đời thường |
|---|---|---|
| `symbol` | chuỗi | Mã cổ phiếu, luôn viết HOA |
| `timestamp` | thời gian UTC | Thời điểm đóng cửa phiên giao dịch |
| `open` `high` `low` `close` | số thực | Giá mở / cao / thấp / đóng |
| `adj_close` | số thực | Giá đã điều chỉnh (cho cổ tức, tách cổ phiếu) |
| `volume` | số thực | Khối lượng giao dịch |
| `source` | chuỗi | Nhà cung cấp dữ liệu đã dùng |
| `ingestion_time` | thời gian UTC | Lúc mình tải dữ liệu này về |

### 3.3.1. Chi tiết: lỗi "đọc lẫn mã" — ví dụ về tầm quan trọng của chi tiết nhỏ

Đây là một ví dụ rất đáng đưa vào bảo vệ, vì nó cho thấy bạn hiểu **tại sao** code viết thế, chứ không chỉ biết nó viết thế.

```python
# SAI — thiếu dấu "/" ở cuối:
prefix = "symbol=M"
# → khớp "symbol=MCD/", "symbol=META/", "symbol=MA/" ...
# → đọc "M" sẽ âm thầm nối 51 mã: 5.801 partition, 121.913 dòng
# → MỌI bảng biểu và chỉ báo vẽ ra biểu TRỘN của 51 mã

# ĐÚNG:
prefix = "symbol=M/"
# → chỉ khớp đúng partition của M
```

**Vì sao loại lỗi này nguy hiểm:** người đọc biểu đồ **không bao giờ nhận ra**, vì đường giá trộn vẫn trông rất giống giá thật. Nó chỉ lộ ra khi bạn đối chiếu số liệu với nguồn.

### 3.3.2. Chi tiết: kiểm tra "hợp lý" — chống dữ liệu sai đơn vị

Bronze chạy qua màn lưới kiểm tra giá trước khi ghi. Điểm cốt lõi: **một số kiểm tra cần hai mốc tham chiếu khác nhau**.

| Mốc | Trả lời câu hỏi nào | Dùng để |
|---|---|---|
| **`floor`** (đáy) | "Mã này có rẻ không?" | nới điều kiện giá tối thiểu tuyệt đối |
| **`magnitude`** (trung vị) | "Giá này có lệch quá xa so với chỗ nó thường giao dịch không?" | bắt lỗi đơn vị (×100, ×1000) |

**Vì sao không dùng chung một số?** Trường hợp thật của mã `PARA`:

- Partition mới nhất (2026-11) vẫn chứa vài bar **trước khi tách cổ phiếu 10:1** ở mức ~2.72, nằm cạnh các bar sau tách. Trung vị partition ≈ **2.21**, nhưng mức thực tế hiện tại ≈ **0.42**.
  - Nếu dùng 2.21 làm `floor`: điều kiện giá tối thiểu 0.5 vẫn có hiệu lực → bar **hợp lệ** 0.425 bị từ chối với lý do `implausible_open`. Bar này **không bao giờ sửa được**, vì màn lưới so với mức đã lưu (chính là 4.251 trước tách) → giá trị sai luôn làm chuẩn, giá trị đúng luôn trông bất khả thi.
- Nếu dùng đáy làm `magnitude`: PARA giao dịch ~$102 năm 2021 và ~$0.47 năm 2026 → đáy thấp hơn trung vị khoảng **200 lần** → lịch sử năm 2021 bị xoá với lý do `price_magnitude`, tức **xoá dữ liệu thật để bắt một lỗi hiếm**.

**Kết luận:** đáy → nới sàn cho mã rẻ thật; trung vị → giữ cho kiểm tra magnitude trung thực; lỗi đơn vị vẫn bị bắt vì lệch 1000× — nằm ngoài cả hai dải.

### 3.3.3. Chi tiết: ghi thêm là idempotent

Bronze append là idempotent: nạp lại cùng một ngày sẽ **không** tạo bản trùng. Cơ chế: khóa `(symbol, timestamp)`; bản ghi đã tồn tại bị loại.

**Vì sao quan trọng:** toàn bộ pipeline có thể chạy lại an toàn — rất quan trọng vì auto-refresh chạy mỗi 6 giờ.

### 3.3.4. Chi tiết: bar bị đóng băng giữa phiên — và vì sao Bronze vẫn nên giữ nó

Đo ngày 15/11/2026, quality gate FAIL ở check `source_agreement` với hai mã
`AMD` và `INTC`. Hai nguồn trông như nói khác nhau về cùng một phiên
`2026-10-28`:

| Nguồn | Close | Volume | Lúc nạp |
|---|---|---|---|
| `yfinance_eod` | 567,00 | 7.367.032 | **16:29 UTC = 12:29 EDT** |
| `yahoo_http` | 578,44 | 18.848.600 | 13:30 UTC |

Nhưng chúng **không phải** hai nguồn bất đồng. Dòng `yfinance_eod` được nạp
lúc **12:29 giờ chiều giờ New York**, tức **3,5 giờ trước giờ đóng cửa NYSE**
(16:00 EDT). `close` của nó là giá giao dịch cuối cùng tại thời điểm đó và
`volume` là khối lượng đã giao dịch cho tới lúc đó. Đây là **ảnh chụp giữa phiên
bị đóng băng thành bar ngày**.

Bằng chứng độc lập: provider phục vụ giá đã chốt của `AMD` ngày `2026-10-28`
là **578,44** — đúng bằng dòng `yahoo_http`, lệch **2,0%** so với dòng kia.

**Khác biệt cốt lõi với bar crypto "hôm nay".** Bar crypto đóng dấu lúc 00:00Z
nên bar "hôm nay" là bar đang hình thành, và có thể nhận ra bằng cách so
timestamp với nửa đêm UTC. Bar **cổ phiếu** đóng dấu lúc **giờ mở cửa**, nên
với cổ phiếu thì bar "hôm nay" đã **chốt rồi**. Cái bị đóng băng ở đây là bar
của **phiên hôm qua**, bị chụp lúc 16:29 UTC vì lúc đó phiên hôm qua **còn đang
mở**.

**Phạm vi:** quét toàn bộ Bronze cho thấy **1.138 phiên** đóng băng trên **752
mã** — không chỉ 6 mã, và phần lớn cũng không phải `yfinance_eod` mà là
`yahoo_http` đóng dấu đúng phút fetch chạy.

**Quan hệ bao hình — tín hiệu cấu trúc.** Trong một phiên, `high`/`low` chỉ có
thể **nở ra** và `volume` chỉ có thể **tăng**. Nên bar đã chốt **luôn chứa**
bar đang hình thành:

```
forming.high   <= settled.high
forming.low    >= settled.low
forming.volume <  settled.volume
forming.close  != settled.close
```

Quan hệ này **không cần lịch sàn giao dịch**: nó so hai dòng của *cùng một
phiên* với nhau, nên đúng với mọi thị trường trong universe mà không cần biết
sàn nào mở lúc nào. Đây là điểm khác biệt so với mọi guard khác trong hệ
thống, vốn đều cần một bảng tham số.

**Kiểm chứng:** đối chiếu trực tiếp với provider đang chạy trên **1.120 phiên**
→ **1.116 khớp (99,6%)**. 4 ca còn lại đều không phải ảnh chụp: 3 ca `CMG` là
**stock split 50:1** (điểm gãy thang giá, xử lý riêng bởi
`app/lakehouse/scale_repair.py`), 1 ca `COL.AX` do sàn ASX chéo nửa đêm UTC.
Vì vậy luật **loại trừ** các cặp lệch ≥ 10 lần — đó là dấu hiệu gãy thang giá.

**Tầng nào giữ dòng nào** (đo trên `AMD`):

```
bronze   04:00Z  close 567.00  vol  7,367,032   <- đóng băng
bronze   13:30Z  close 578.44  vol 18,848,600   <- đã chốt
silver   13:30Z  close 578.44  vol 18,848,600   <- đã chốt
gold     13:30Z  close 578.44  vol 18,848,600   <- đã chốt
```

Silver và Gold **đã chọn đúng**, vì chúng ưu tiên dấu phiên chuẩn. Chỉ Bronze
giữ cả hai.

**Quyết định thiết kế: KHÔNG xoá.** Bronze là tầng **raw** — nó ghi lại điều
provider thực sự đã nói, và được phép giữ một ảnh chụp mà sau đó bị bản đã
chốt thay thế. Xoá đi nghĩa là **bịa lại** lịch sử của provider. Thay vào đó,
check mới `forming_snapshots` trong quality gate **gọi đúng tên** hiện tượng
(báo `warning`, không phải `failed`), để mọi đợt kiểm toán sau này không hiểu
nhầm là "provider sai".

| Thành phần | Tệp | Việc |
|---|---|---|
| Luật bao hình | `app/lakehouse/forming_bar.py` | Phát hiện ảnh chụp giữa phiên, không cần lịch sàn |
| Check quality gate | `app/core/quality_gate.py` → `check_forming_snapshots()` | Báo warning: số phiên đóng băng, số mã |
| Giao diện | `frontend/src/components/quality/QualityGatePanel.tsx` | Nhãn "Bar đóng băng giữa phiên" |
| Test | `backend/tests/test_forming_bar.py` | 17 test, tất cả PASS |

Chi tiết đầy đủ: [`docs/data_verification.md` mục 10d](data_verification.md).

## 3.4. Chi tiết: tầng Silver — lớp làm sạch

`lakehouse/silver.py`. Biến Bronze → Silver:

| Bước | Chi tiết | Vì sao |
|---|---|---|
| Chuẩn hoá múi giờ | tất cả → UTC | Trộn nhiều provider (Yahoo dùng UTC, VnStock dùng Asia/Ho_Chi_Minh) sẽ lệch ngày nếu không chuẩn hoá |
| Kiểm tra OHLC | `low ≤ open, close ≤ high`, giá > 0, volume ≥ 0 | Loại bar hỏng |
| Bỏ bản trùng | theo `(symbol, timestamp)` | Provider trả trùng khi nạp lại |
| Chuẩn hoá phiên | `canonicalize_daily_sessions` | Gom các phiên giao dịch về một mốc thời gian chuẩn |
| Ghi báo cáo | `_quality.json` cho mỗi mã | **Không drop bản ghi nào mà không đếm** |

> **Nguyên tắc:** Silver **không bỏ bản ghi nào mà không báo cáo số lượng**. Bản ghi bị loại phải có lý do và số đếm. Nếu không, bạn không bao giờ biết mình đã mất dữ liệu hay chưa.

**Ghi song song:** một mã 10 năm ≈ **121 partition tháng**. Ghi tuần tự tốn ~2.87 giây round-trip MinIO; auto-refresh rebuild hàng trăm mã nên thời gian này chi phối toàn bộ. Các partition độc lập và idempotent nên chạy song song an toàn → cắt wall-clock xuống một phần nhỏ.

## 3.5. Chi tiết: tầng Gold — lớp phân tích

`lakehouse/gold.py` + `features/`.

**Cấu trúc thực tế (đo trên AAPL): 90 cột**

```
12 cột gốc : symbol, timestamp, open, high, low, close, adj_close,
              volume, source, ingestion_time, year, month
─────────────────────────────────────────────────────────────────
75 feature : sma_5/10/20/50, ema_12/26, rsi_14, macd, macd_signal,
              macd_hist, bb_middle/upper/lower, return, log_return,
              price_change, volume_change, rolling_std_20, rolling_min_20,
              rolling_max_20, volume_ma_20, close_lag_1/2, return_lag_1,
              volume_lag_1, + chỉ báo nâng cao (động lượng, biến động,
              xu hướng), + đặc trưng nến, + volume profile,
              + tín hiệu tổng hợp, + đặc trưng regime thị trường,
              + đặc trưng vĩ mô
─────────────────────────────────────────────────────────────────
 3 target  : target_close_next, target_return_next, target_direction_next
```

**Bảng chọn feature theo mô hình:**

| Mô hình | Số feature | Danh sách |
|---|---|---|
| Linear Regression | 21 | `close, volume, return, sma_5/10/20/50, ema_12/26, rsi_14, macd, macd_signal, macd_hist, bb_middle/upper/lower, rolling_std_20, close_lag_1/2, return_lag_1, volume_lag_1` |
| LSTM | 9 | `close, volume, return, sma_20, ema_12, rsi_14, macd, bb_middle, rolling_std_20` |

### 3.5.1. Chi tiết: cách tạo cột "đáp án" mà không rò rỉ tương lai

```python
# app/features/target_features.py
result["target_close_next"]     = close.shift(-1)
result["target_return_next"]    = close.pct_change().shift(-1)
result["target_direction_next"] = np.where(result["target_return_next"] > 0, 1, ...)
```

`shift(-1)` nghĩa là: **dòng thứ t (mốc thời gian t) mang đáp án là giá đóng cửa của t+1**.

**Tại sao đúng?** Vì "đáp án" thì đương nhiên phải nằm ở tương lai — đó chính là thứ bạn muốn dự đoán. Nhưng **đầu vào** thì tuyệt đối không được nằm ở tương lai. Đây là ranh giới mà cả hệ thống giữ.

### 3.5.2. Chi tiết: vì sao phải "chạy lại được nhiều lần cho kết quả giống nhau"

```python
_BASE_INPUT_COLUMNS = ("symbol","timestamp","open","high","low","close",
                        "adj_close","volume","source","ingestion_time","year","month")
keep = [c for c in _BASE_INPUT_COLUMNS if c in frame.columns]
working_input = frame.loc[:, keep].copy()
```

**Vì sao:** đôi khi file parquet của Silver đã chứa sẵn feature của lần Gold trước (do pipeline chạy lại trên dữ liệu đã enrich). Nếu không strip, bạn sẽ có `sma_20_sma_20`, và hàm trở nên **không idempotent** → chạy 2 lần cho kết quả khác chạy 1 lần.

Đây là loại bug âm thầm rất dễ bỏ sót: không có gì hỏng ngay, nhưng sau vài lần chạy dữ liệu sẽ loãng dần.

Tương tự, `add_indicators()` có `RESERVED_COLUMNS` để drop cột chỉ báo cũ trước khi tính.

### 3.5.3. Chi tiết: hai đường xử lý Pandas và Spark

Cả Silver và Gold đều có 2 đường: `_transform_spark` (khi `USE_SPARK=true`) và `_transform_pandas` (mặc định). Spark bật cho xử lý quy mô lớn; Pandas là mặc định vì máy dev chạy Pandas nhanh hơn và không cần cài Spark.

## 3.6. Chi tiết: nơi lưu trữ — MinIO và đường dự phòng

`lakehouse/storage_factory.py` chọn backend theo `STORAGE_BACKEND`:

- **MinIO** (mặc định khi có): S3-compatible, mỗi tầng một bucket.
- **Filesystem local**: dự phòng khi MinIO không sẵn sàng — hệ thống **không sập**, chỉ chậm hơn.

`minio_storage.py` và `local_storage.py` cùng implement interface `StorageBackend`, nên **toàn bộ pipeline không biết nó đang nói chuyện với cái gì**.

> **Cả hai đường đều là dữ liệu THẬT.** Filesystem local dưới `backend/data/<layer>/` không
> phải dữ liệu giả — đó là cùng một lakehouse đã ingest từ nhà cung cấp thật, chỉ khác
> chỗ lưu. Điều bị cấm tuyệt đối là **sinh số bịa** (xem `.cursor/rules/no-fake-data.mdc`).

> **Đo ngày 10/11/2026:** backend trên Windows chạy với `STORAGE_BACKEND=minio`
> (`MINIO_ENDPOINT=127.0.0.1:19000` qua relay). Kiểm chứng độc lập: đọc trực tiếp
> 606 file Parquet của mã `FPT` trong `stock-silver` — **0 file hỏng**.

---

# PHẦN 4 — DỮ LIỆU LẤY TỪ ĐÂU

## 4.1. Hiểu đơn giản

Giống như Wi-Fi công cộng: bạn không dựa vào một máy chủ duy nhất. Hệ thống có **một danh sách nhà cung cấp dữ liệu**, thử lần lượt cho đến khi có nhà nào trả về dữ liệu thật.

```
yahoo_http → yfinance → finnhub → alpha_vantage → web_scraper → ssi_vn
   ↑ chính      ↑ dự phòng                    ↑ cuối cùng   ↑ chỉ cứu mã VN
```

Điểm quan trọng: **một mã hỏng không được làm hỏng cả nhà cung cấp**. Nếu mã "MCD" bị 404 (cổ phiếu đã bị hủy niêm yết), thì đó là lỗi của *mã*, không phải lỗi của *nhà cung cấp*. Nếu không phân biệt, một mã 404 sẽ vô hiệu hoá một nhà cung cấp hoàn toàn khoẻ.

## 4.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Provider** | Nhà cung cấp dữ liệu (Yahoo, SSI, Finnhub, ...) |
| **Failover chain** | Danh sách nhà cung cấp thử lần lượt |
| **Circuit breaker** | "Cầu dao" — tạm ngưng dùng nhà cung cấp đang hỏng để khỏi mất thời gian chờ |
| **Cooldown** | Khoảng thời gian chờ trước khi thử lại nhà cung cấp |
| **Keyless** | Không cần đăng ký API key |

## 4.3. Chi tiết: bảng nhà cung cấp

| Provider | Cần key | Vai trò |
|---|---|---|
| `yahoo_http` | không | **Chính** — gọi thẳng v8 chart API, 10y+ lịch sử, browser UA |
| `yfinance` | không | Dự phòng — package chính thức |
| `finnhub` | có | Dự phòng + WebSocket realtime |
| `alpha_vantage` | có | Dự phòng (free tier 25 req/ngày) |
| `web_scraper` | không | Cuối cùng |
| `ssi_vn` | không | **Chỉ cứu** mã HOSE/HNX/UPCoM mà Yahoo không có (vd VCS) |

> `stooq` bị loại khỏi chuỗi daily vì endpoint CSV công khai của họ nay yêu cầu JS challenge không giải được từ server-side script.

## 4.4. Chi tiết: cầu dao mạch (circuit breaker)

```python
FATAL_PATTERNS = ("rate limit", "requests per day", "authentication failed",
                  "api key", "premium plan", "subscription")

FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 900.0
```

**Phân biệt then chốt:**

| Loại lỗi | Ví dụ | Tính vào cầu dao? |
|---|---|---|
| **Lỗi cấu hình / hạn mức** | hết quota, API key hết hạn | Có — provider không dùng được lúc này |
| **Lỗi dữ liệu** | 404 cho một mã cụ thể | Không — mã đó hỏng, provider vẫn tốt |

## 4.5. Chi tiết: bảng dữ liệu phân tích

| Bảng | Nội dung | Nguồn |
|---|---|---|
| `stock-bronze` | OHLCV daily, ~10 năm | Yahoo / VnStock |
| `stock-silver` | OHLCV đã làm sạch + `_quality.json` | Bronze |
| `stock-silver-fundamentals` | Báo cáo tài chính | Yahoo Finance |
| `stock-gold` | 90 cột features + targets | Silver |
| `stock-models` | Model registry, scaler, predictions | Training |
| `stock-backtests` | Kết quả backtest JSON | Backtest service |

---

# PHẦN 5 — TẦNG NGHIỆP VỤ BACKEND

> Sơ đồ: [9. GIL — tại sao cần Process pool](./SO_DO_MINH_HOA.md#9) · [10. Request Gate](./SO_DO_MINH_HOA.md#10)

## 5.1. Hiểu đơn giản: đường đọc dữ liệu

Khi bạn mở trang web và chọn "AAPL", backend phải trả về ~2.500 phiên giao dịch. Mỗi phiên nằm ở 1 file Parquet khác nhau ⇒ phải tải **~121 file** từ MinIO.

Nếu mỗi lần mở trang đều tải lại 121 file, bạn sẽ thấy trang **lag vài chút**. Nên hệ thống giữ lại kết quả trong bộ nhớ (cache) trong 15 phút.

Nhưng có 1 cái bẫy: khi hệ thống đang tải dữ liệu mới cho hàng trăm mã (refresh mỗi 6 giờ), một lần đọc có thể rơi đúng vào lúc đó và phải xếp hàng chờ → **89.9 giây**. Đó là lý do có "cổng ưu tiên người dùng".

## 5.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **LRU cache** | Bộ nhớ đệm, khi đầy thì loại món **ít được dùng nhất** |
| **TTL (Time To Live)** | Mỗi món trong cache chỉ sống được một khoảng thời gian rồi phải tải lại |
| **Invalidate** | Xoá ngay một món khỏi cache khi dữ liệu nền vừa thay đổi |
| **Starvation** | Luồng ưu tiên bị bỏ đói vì luồng khác chiếm hết tài nguyên |
| **Backpressure** | Tự điều chỉnh tốc độ khi hệ thống bị quá tải |

## 5.3. Chi tiết: Market Service — cache LRU + TTL

`app/services/market_service.py`. **Nguyên tắc đầu tiên trong docstring:**

> *"NO synthetic / sample / fallback data. If a symbol has no data in any layer, `NotFoundError` is raised so the UI surfaces a clear 'no data' state instead of showing fake numbers."*

**Thứ tự đọc:** Gold → Silver → Bronze (ưu tiên lớp giàu feature nhất).

### 5.3.1. Vì sao cache 24 là quá nhỏ

```
30 mã, lần lạnh ............ 81.1s   (2.70s/mã)
30 mã đó, lần thứ hai ...... 19.0s   (0.63s/mã - vẫn phần lớn là miss)
```

Lakehouse có ~950 mã. Cache 24 không thể chứa đủ khi người dùng duyệt danh sách → hiện tượng LRU-thrash kinh điển. Mỗi lần miss = tải 121 partition ⇒ "duyệt nhiều mã" ⇔ "tải lại toàn bộ lakehouse, lặp đi lặp lại".

### 5.3.2. Vì sao 256 là an toàn

Comment cũ ghi "máy không có pagefile" — nay không còn đúng (Windows đã được cấu hình pagefile do hệ thống quản lý; WSL VM giới hạn 8GB).

Chi phí bộ nhớ đo được: **~3 MB/mã** ⇒ 256 mã ≈ **750 MB** — chấp nhận được, và phủ kịp toàn bộ một phiên duyệt.

### 5.3.3. Vì sao TTL = 900 giây

Một lần đọc mất ~1s khi máy rảnh, nhưng nhiều hơn khi refresh đang chạy. TTL ngắn buộc dashboard tải lại toàn bộ lịch sử mã mỗi phút, và mỗi lần đọc có thể rơi giữa lúc refresh → vượt timeout 90s của frontend.

**Freshness KHÔNG bị mất:** auto-refresh gọi `invalidate_symbol_cache(symbol)` ngay khoảnh khắc nó ghi lại symbol đó ⇒ dữ liệu mới hiện ra tức thì. TTL chỉ quy định **một symbol không thay đổi** được đọc lại sau bao lâu.

## 5.4. Chi tiết: Auto-refresh — cập nhật mỗi 6 giờ

`app/services/auto_refresh.py`:

```
FastAPI startup  →  1 lần refresh toàn bộ  →  mỗi 6 giờ  →  lặp lại
```

Logic mỗi mã:
- Bronze chưa có dữ liệu → tải full `DEFAULT_LOOKBACK_DAYS = 3650` (10 năm).
- Bronze đã có → tải từ `(ngày cuối cùng + 1 ngày)` đến hiện tại ⇒ **tăng dần (incremental)**.
- Bronze append xong mới rebuild Silver + Gold (idempotent).

Env: `AUTO_REFRESH_ON_START=1`, `AUTO_REFRESH_ENABLED=1`, `AUTO_REFRESH_INTERVAL_SECONDS=21600`, `AUTO_REFRESH_BATCH_SIZE=20`, `AUTO_REFRESH_SKIP_IF_FRESH_HOURS=24`.

## 5.5. Chi tiết: Cổng ưu tiên người dùng (request gate)

`app/core/request_gate.py`. **Đây là quyết định thiết kế quan trọng nhất về hiệu năng.**

**Vấn đề đo được:**

```
AAPL read   0.4s  ->   3.3s
MSFT read   0.4s  ->  66.3s
NVDA read   0.4s  ->  89.9s
```

**Cơ chế:** module đếm số request người dùng đang "đang chạy". Auto-refresh kiểm tra trước khi bắt đầu mỗi mã và **chờ** nếu có người đang hoạt động. Có `DEFAULT_GRACE_SECONDS = 2.0` để tránh chen vào giữa 4 request liên tiếp của một trang.

**Đánh đổi được nêu rõ trong code:** refresh chậm đi (nghỉ khi có người dùng) nhưng mọi request tương tác trở nên nhanh và **dự đoán được**. Với một demo nghiên cứu, đây đúng là ưu tiên: không ai theo dõi tiến trình refresh, nhưng tất cả mọi người đều nhìn UI.

## 5.6. Chi tiết: Tách việc nặng ra tiến trình riêng (heavy worker)

`app/core/heavy_worker.py`. **Một trong những quyết định kỹ thuật đáng giải thích nhất.**

### 5.6.1. Hiểu đơn giản

Backend làm 2 việc cùng lúc:
- **Việc nền**: tải & xử lý dữ liệu cho ~1.000 mã (nặng, chạy 20 luồng).
- **Việc của người dùng**: trả lời khi bạn bấm nút (phải nhanh).

Cả hai đều là **code Python nặng**. Mà Python có một đặc điểm: **chỉ 1 luồng được chạy code Python cùng lúc** (GIL). Nên khi 20 luồng nền đang chạy, luồng của bạn phải xếp hàng chờ.

**Đo được:**

```
walk-forward validation, process rảnh ............ 2.2 s
walk-forward validation, refresh đang chạy ....... 13.3 s   (6x)
walk-forward validation, tải server thật ......... 96  s   (40x)
```

Trường hợp 96s chính là thứ làm vỡ UI. Khi đó stack dump cho thấy luồng đang nằm trong `pandas.core.series.dropna` — tức là **đang chạy, chỉ bị đói CPU**.

> **Thread không sửa được** (thread dùng chung GIL). **Process thì có** — tiến trình con có interpreter riêng và GIL riêng.

### 5.6.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **GIL** | Ổ khoá toàn cục của Python, chỉ 1 luồng chạy code Python mỗi lúc |
| **Process pool** | Nhóm tiến trình con, tái sử dụng để chạy job nặng |
| **Spawn** | Cách khởi động tiến trình con trên Windows (bắt buộc) |
| **OOM-kill** | Hệ điều hành giết tiến trình vì hết bộ nhớ |
| **Pagefile** | File trên ổ đĩa Windows dùng làm "RAM ảo" khi RAM thật hết |

### 5.6.3. Chi tiết: hai pool, không phải một

| Pool | Size | Phục vụ |
|---|---|---|
| `interactive` | 2 | Request người dùng thấy (agent, walk-forward) |
| `background` | 4 | Auto-refresh rebuild |

Tách là **cố ý**: một pool chung sẽ để burst refresh chiếm hết worker và xếp request của người dùng vào sau — đúng cái lỗi đang cần sửa.

### 5.6.4. Chi tiết: giới hạn worker theo RAM khả dụng thật

```python
WORKER_MEMORY_MB = 700        # pandas+pyarrow ~130MB, history ~400MB, indicators ~150MB
RESERVE_FOR_HOST_MB = 4096    # desktop, Cursor, AV, browser cần chỗ
```

`_affordable_workers()` đọc `GlobalMemoryStatusEx` và chỉ tạo worker khi còn chỗ.

**Lý do:** host **không có pagefile Windows** ⇒ commit limit = RAM vật lý. Khi sát limit, Windows bắn event "low virtual memory condition" và giết tiến trình — không có swap, không cảnh báo. Event log ghi lại đúng điều đó (vmmemWSL 12.9GB + python 1.67GB + 0.74GB ⇒ worker bị giết giữa lúc rebuild ⇒ `BrokenProcessPool` ⇒ mọi rebuild sau đó đều fail).

### 5.6.5. Chi tiết: pool chết được dựng lại

`ProcessPoolExecutor` **hỏng vĩnh viễn** một khi worker chết — mọi `submit()` sau đó ném `BrokenProcessPool`. Vì pool bị cache, **mọi** rebuild sau đó cũng fail ⇒ refresh không bao giờ tự phục hồi.

`run_in_process()` bỏ pool hỏng và thử lại **một lần** trên pool mới; chỉ khi cả hai lần hỏng mới lỗi tới caller (fallback chạy in-process).

**Context `spawn` bắt buộc trên Windows:** `fork` sẽ thừa kế thread của cha (kể cả connection pool MinIO) — công thức của deadlock.

## 5.7. Chi tiết: Cơ sở dữ liệu MySQL

5 bảng, Alembic migration `0001_initial`:

| Bảng | Mục đích |
|---|---|
| `backtest_runs` | Lịch sử backtest (symbol, strategy, metrics JSON, equity curve) |
| `model_runs` | Lịch sử train model |
| `pipeline_runs` | Lịch sử chạy pipeline |
| `agent_conversations` | Lịch sử hội thoại AI |
| `users` | Người dùng |

**Phân tách trách nhiệm:** MySQL giữ **metadata và lịch sử**; MinIO giữ **dữ liệu lớn**. Không nhét file parquet vào SQL.

---

# PHẦN 5B — BA HỆ THỐNG MỚI (10/11/2026)

> **Bối cảnh:** ngày 10/11/2026, khi Kafka và Iceberg bị gỡ khỏi dự án, ba hệ thống
> mới được thêm vào để thay thế vai trò "hệ thống tự chạy" mà trước đó broker và
> catalog từng đảm nhiệm.
>
> Mỗi hệ thống trong Phần này có **3 mục**: ① Hiểu đơn giản → ② Thuật ngữ →
> ③ Chi tiết kỹ thuật. Bạn **được phép dừng ở ①** và vẫn hiểu trọn vẹn.

---

## 5B.1. Hiểu đơn giản: vì sao hệ thống KHÔNG còn tin tức

### 5B.1.1. Vấn đề

Dự án từng có một hệ thống tin tức riêng: mỗi bài báo được tải về từ nhà cung cấp
thật, lưu vào kho, bỏ bài trùng, rồi gắn vào đúng phiên giao dịch mà bài báo đó
mô tả (bài đăng trước giờ mở cửa thì gắn vào phiên đó; bài đăng sau giờ đóng cửa
thì gắn vào phiên kế tiếp). Mục tiêu của nó là đo được **độ phủ tin tức** của toàn
bộ danh sách mã — tỉ lệ phiên giao dịch nào có ít nhất một bài báo.

Đây là một ý tưởng nghiên cứu **đúng đắn về mặt kỹ thuật**. Vấn đề nằm ở chỗ
khác: **dữ liệu thu được không đủ để làm bất cứ thí nghiệm nào**.

### 5B.1.2. Đo được gì (Đo ngày 11/11/2026)

Khi đo độ phủ thực tế trên toàn bộ danh sách mã, kết quả là:

| Chỉ số | Giá trị đo được |
|---|---|
| Tổng số mã trong danh sách | 1.002 mã |
| Số mã có ít nhất 1 bài báo | 10 mã |
| Số bài báo đã lưu | 89 bài |
| Độ phủ chung (tất cả mã) | 0.00% |
| Độ phủ trung vị (theo từng mã) | 0.00% |

Nghĩa là: **99% số phiên giao dịch của toàn bộ danh sách mã không có bài báo nào**.
Một hệ thống chỉ hoạt động trên 0.89% mẫu số không thể dùng để kết luận điều gì.

### 5B.1.3. Vấn đề nghiêm trọng hơn: tin thật gắn sai mã

Trong 10 mã "có tin", kiểm tra từng bài báo cho thấy **một số bài báo thật nhưng
gắn sai mã chứng khoán**. Nguyên nhân là **trùng mã giữa các sàn**:

| Mã trong hệ thống | Bài báo thực tế được gán | Vì sao sai |
|---|---|---|
| `MWG` (Mobile World, Việt Nam) | Tin về Multi Ways Holdings (Singapore) | Yahoo Finance tra cứu RSS theo mã, và `MWG` là mã của cả hai công ty |
| `VCB` (Vietcombank, Việt Nam) | Tin về quỹ ETF Vanguard | Cùng lý do: `VCB` trùng mã với quỹ Vanguard |
| `FPT`, `HPG`, `CTG` | Tin chung thị trường chung của VnExpress | Logic dự phòng: khi số bài "liên quan" quá ít, hệ thống đổ tin chung vào các mã này để không trống trải |

Bài báo là **thật** — không có bài nào bịa ra. Nhưng bài báo **thật gắn sai mã**
vẫn là sai. Khi bảng dữ liệu ghi "MWG có tin tức về Multi Ways Holdings", người đọc
không thể phân biệt đâu là tin của Mobile World.

### 5B.1.4. Hậu quả nếu giữ lại

| Hậu quả | Mức độ |
|---|---|
| Một trang giao diện không có nội dung nghiên cứu nào đứng vững | Trung bình |
| Tính truy vết nguồn bị hỏng: bài thật nhưng sai mã | **Nặng** |
| Phải bảo vệ trước hội đồng câu "mà trang này có dữ liệu gì?" | **Nặng** |
| Tốn công bảo trì: provider, 2 tầng lưu, 4 endpoint, 1 trang UI, 2 lịch cron | Thấp (chi phí) |

Điểm quyết định là hàng thứ hai. Luật "Real Data Only" của dự án không chỉ cấm
**bịa số**, mà còn cấm **gắn sai nguồn**. Một bài báo thật đặt nhầm cột là vi phạm
cùng loại với một số liệu bịa.

### 5B.1.5. Cách hệ thống xử lý: GỠ BỎ TOÀN BỘ

Ngày **12/11/2026**, toàn bộ hệ thống tin tức bị gỡ khỏi dự án. Đây là một quyết
định **giảm phạm vi**, không phải một lỗi cần sửa: hệ thống còn lại là một
pipeline giá + chỉ báo + dự báo + backtest **đầy đủ và truy vết được**, còn phần
tin tức thì chưa bao giờ đủ dữ liệu để làm nghiên cứu.

Phần còn lại của Phần 5B mô tả hai hệ thống **không liên quan đến tin tức** và
vẫn đang hoạt động: dự báo phiên kế tiếp tự động (5B.4) và đồng hồ cron (5B.5).

### 5B.1.6. Hình vẽ — trạng thái sau khi gỡ

```
┌───────────────────────────────────────────────────────────────────────┐
│  NHÀ CUNG CẤP GIÁ THẬT (Yahoo · Finnhub · Alpha Vantage · SSI VN)     │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│  BRONZE   bucket "stock-bronze"     app/lakehouse/bronze.py           │
│  dữ liệu giá nguyên bản, append-only, partition symbol/year/month     │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│  SILVER   bucket "stock-silver"     app/lakehouse/silver.py           │
│  đã rửa: bỏ OHLC sai, dedup, chuẩn hoá giờ UTC                        │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│  GOLD     bucket "stock-gold"       app/lakehouse/gold.py             │
│  23 đặc trưng + 3 cột đáp án, không rò rỉ tương lai                   │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│  MÔ HÌNH + BACKTEST + WALK-FORWARD   app/forecasting · app/backtesting│
│  4 endpoint, 7 trang giao diện, KHÔNG có trang tin tức                │
└───────────────────────────────────────────────────────────────────────┘
```

### 5B.1.7. Đọc hình vẽ bằng lời đời thường

Hình trên là **đường đi duy nhất** của dữ liệu trong hệ thống bây giờ: giá thật từ
nhà cung cấp thật đi vào tầng Bronze, được rửa ở tầng Silver, được băm thành đặc
trưng ở tầng Gold, rồi chảy vào mô hình dự báo và backtest. **Không có nhánh nào
song song.** Trước đây có một nhánh thứ hai chạy song song (tin tức) nhưng nhánh đó
đã bị gỡ bỏ.

### 5B.1.8. Danh sách thay đổi cụ thể

**Đã xoá (backend):**

| File | Vai trò |
|---|---|
| `backend/app/api/v1/endpoints/news.py` | 4 endpoint đọc tin tức |
| `backend/app/agent/tools/news_tools.py` | 4 tool cho AI Agent |
| `backend/app/lakehouse/news_bronze.py` | Tầng Bronze tin tức |
| `backend/app/lakehouse/news_silver.py` | Tầng Silver tin tức |
| `backend/app/data_sources/enhanced_news_sentiment_provider.py` | Provider đọc RSS |
| `backend/scripts/measure_news_coverage.py` | Script đo độ phủ |
| `backend/scripts/probe_news_source_coverage.py` | Script dò nguồn |
| `backend/tests/test_news_anti_lookahead.py` | Test chống rò rỉ tương lai |
| `backend/data/bronze_news/`, `backend/data/silver_news/` | Dữ liệu local |
| `backend/data/news_coverage.json` | Báo cáo đo |

**Đã sửa (backend):** `app/api/v1/router.py`, `app/core/config.py`,
`app/api/v1/endpoints/data.py`, `app/api/v1/endpoints/market.py`,
`app/data_sources/__init__.py`, `app/data_sources/finnhub_provider.py`,
`app/data_sources/multi_source.py`, `app/data_sources/yfinance_python_provider.py`,
`app/lakehouse/__init__.py`, `app/lakehouse/local_storage.py`,
`app/lakehouse/minio_storage.py`, `app/services/data_ingestion_service.py`,
`app/agent/tool_registry.py`, `app/agent/agent.py`, `app/agent/prompts.py`,
`app/agent/tools/system_tools.py`, `scripts/bootstrap_infrastructure.py`,
`scripts/run_scheduled_job.py`, `crontab`, `tests/smoke_*.ps1`.

**Đã xoá (frontend):** `frontend/src/pages/NewsSentiment.tsx`,
`frontend/src/api/news.ts`.

**Đã sửa (frontend):** `src/App.tsx` (bỏ route `/news`),
`src/components/layout/NavBar.tsx` (bỏ mục menu),
`src/lib/i18n.tsx` (bỏ 73 khoá dịch `news.*` và `nav.news`).

**Đã xoá (MinIO):** bucket `stock-bronze-news` (17 object, 240.991 byte),
bucket `stock-silver-news` (15 object, 259.689 byte) — đo ngày 12/11/2026.

### 5B.1.9. Bằng chứng

| Kiểm tra | Trước | Sau |
|---|---|---|
| Số route REST có chứa `news`/`sentiment` | 8 | **0** (tổng còn 61 route) |
| Số endpoint trong `tool_registry.py` | 21 | **17** |
| Số bucket MinIO có chữ `news` | 2 | **0** |
| Test backend | 111 pass + 1 lỗi import | **112 pass, 0 lỗi** |
| Build frontend | OK | **OK** |
| Số trang giao diện | 8 | **7** |

> **Cách trả lời khi thầy hỏi "vì sao bỏ trang tin tức, dự án không bị thiếu gì sao?":**
> *"Đúng, dự án không bị thiếu gì, và đó là lý do tôi gỡ nó chứ không phải giữ nó.
> Tôi đã đo độ phủ trước khi quyết định: trên 1.002 mã, chỉ 10 mã có tin và tổng
> cộng 89 bài — độ phủ chung 0.00%, trung vị 0.00%. Nghĩa là 99% số phiên không
> có dữ liệu để nghiên cứu. Tệ hơn, khi kiểm tra từng bài, tôi thấy mã `MWG` của
> Mobile World nhận tin của Multi Ways Holdings, mã `VCB` của Vietcombank nhận tin
> của quỹ Vanguard — vì các mã này trùng nhau giữa các sàn. Bài báo thật nhưng
> gắn sai mã, mà luật của dự án tôi tự đặt ra là mọi con số phải truy vết được.
> Nên tôi chọn gỡ hẳn thay vì giữ một trang rỗng rồi giải thích là 'đang thử
> nghiệm'. Phần còn lại — giá, chỉ báo, dự báo, backtest, walk-forward — là phần
> có dữ liệu thật và kết quả thật, và tôi tập trung sức vào đó."*

---
---

## 5B.4. Hiểu đơn giản: dự báo phiên kế tiếp chạy tự động

### 5B.4.1. Vấn đề

Sau khi thị trường đóng cửa, bạn sẽ có dữ liệu mới của hôm nay. Nhưng "dữ liệu mới
có sẵn" không có nghĩa là "con số dự báo đã có". Muốn có con số dự báo cho phiên
ngày mai, bạn phải **thật sự chạy mô hình**.

Trước đây, việc đó chỉ xảy ra khi **con người** mở trang web và bấm nút. Đó là
một điểm yếu rõ ràng: nếu bạn không mở web, hệ thống không dự báo gì cả. Đồ án
nói về "hệ thống tự động" mà thực tế phải có người bấm nút thì không khéo.

### 5B.4.2. Hậu quả nếu không xử lý

- Con số dự báo trên Dashboard chỉ xuất hiện **khi có người hỏi**.
- Không ai biết hệ thống đã "sống" hay chết. Đây chính là lý do một cron thật
  thay cho một tiến trình Python chạy nền — xem mục 5B.5.
- Không có lịch sử: con số "hôm nay dự báo bao nhiêu" bị ghi đè mỗi lần bấm, không
  truy vết được.

### 5B.4.3. Cách hệ thống xử lý

Sau mỗi lần batch cuối ngày (EOD), hệ thống làm thêm **một bước**:

1. **Dự báo** — chạy mô hình đã huấn luyện sẵn cho mỗi mã, lấy điểm đầu tiên
   chưa có giá thực tế.
2. **Ghi vào MySQL** — một bảng tên `predictions`, mỗi dòng là một dự báo cho một
   mã + một mô hình + một phiên đích.
3. **Hiển thị** — Dashboard đọc bảng đó và hiện thẻ "Dự báo phiên kế tiếp".

Điểm mấu chốt: **cùng một hàm** sinh ra con số cho cả Dashboard lẫn cho bảng
`predictions`. Nếu hai chỗ dùng hai đường code khác nhau, chúng có thể cho hai con
số khác nhau — và sự khác biệt đó sẽ không bao giờ được phát hiện.

### 5B.4.4. Hình vẽ

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CRON: 21:30 UTC (NYSE)  ·  03:30 UTC (HOSE)                             │
│  → scripts/run_scheduled_job.py eod                                      │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  services/auto_refresh.py   run_once()                                   │
│                                                                          │
│    1 nạp giá hôm nay vào Bronze                                          │
│    2 dựng lại Silver + Gold cho các mã có dữ liệu mới                    │
│    3 NẾU settings.auto_predict_enabled:                                  │
│         services/next_session_forecast.predict_and_store(mã, model)      │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  build_next_session_forecast()                                           │
│                                                                          │
│    • mô hình đã train có sẵn trên đĩa?  không → báo "không có", KHÔNG bịa│
│    • gọi predict_symbol() → lấy ĐIỂM ĐẦU TIÊN chưa có giá thực tế        │
│    • trả về: reference_close, predicted_close, predicted_return,         │
│                target_session, source_layer="gold"                       │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  MySQL — bảng `predictions`                                              │
│                                                                          │
│    unique (symbol, model_name, target_session)                           │
│    source = "auto_eod_batch" | "manual_api"                              │
│    source_layer = "gold"                                                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  services/dashboard_service.py  →  trả về `next_session_forecast`        │
│  → frontend/src/components/dashboard/NextSessionCard.tsx                 │
│    hiện thẻ "Dự báo phiên kế tiếp" trên Dashboard                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5B.4.5. Đọc hình vẽ bằng lời đời thường

Hình này đọc từ trên xuống như một ca đêm trực. Đồng hồ báo giờ (cron) rung lên
lúc 9 giờ 30 tối giờ New York — tức là sau khi thị trường đã đóng cửa. Hệ thống
thức dậy và làm ba việc: cập nhật giá, dựng lại phần đã xử lý, rồi **hỏi mô hình
"ngày mai giá sẽ ra sao"**.

Bước quan trọng nhất là bước cuối cùng: câu trả lời được **ghi xuống một sổ
tay** (bảng `predictions` trong MySQL). Sổ tay này ghi rõ: dự báo cho mã nào, bằng
mô hình nào, dành cho phiên ngày nào, và ai làm ra nó (batch tự động hay người bấm
nút).

Mũi tên cuối cùng đi lên trên Dashboard: thẻ "Dự báo phiên kế tiếp" **đọc từ sổ
tay đó**, không tự tính lại. Nhờ vậy, con số bạn thấy trên Dashboard và con số
trong sổ tay **là một**. Nếu Dashboard tự tính riêng, hai nơi có thể lệch nhau mà
không ai biết.

### 5B.4.6. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Batch cuối ngày** | **EOD batch (End-Of-Day)** | Lần chạy định kỳ sau giờ đóng cửa, cập nhật toàn bộ dữ liệu | `backend/app/services/auto_refresh.py` |
| **Dự báo phiên kế tiếp** | **Next-session forecast** | Con số dự báo cho phiên giao dịch **chưa xảy ra** | `backend/app/services/next_session_forecast.py` |
| **Điểm đầu tiên chưa có giá thực tế** | **First forward point** | Điểm đầu tiên trong chuỗi dự báo mà chưa có giá đóng cửa thật | `backend/app/services/next_session_forecast.py` |
| **Giá neo** | **reference_close** | Giá đóng cửa cuối cùng **trước** phiên đích — mốc để tính tỷ lệ thay đổi | `backend/app/services/next_session_forecast.py` |
| **Phiên đích** | **target_session** | Ngày giao dịch mà dự báo nhắm tới | `backend/app/database/models/prediction.py` |
| **Bảng dự báo** | **Predictions table** | Bảng MySQL lưu dự báo, unique theo (mã, mô hình, phiên) | `backend/app/database/models/prediction.py` |
| **Ghi đè thay vì chèn** | **Upsert** | Chạy lại batch cho cùng phiên thì ghi đè dòng cũ, không tạo dòng thứ hai | `backend/app/database/repositories/prediction_repository.py` |
| **Cờ bật dự báo tự động** | **auto_predict_enabled** | Cấu hình bật/tắt bước dự báo sau batch EOD | `backend/app/core/config.py` |
| **Tên mô hình dùng chung** | **auto_predict_model** | Mô hình nào được dùng khi bật cờ trên (mặc định `linear_regression`) | `backend/app/core/config.py` |
| **Nguồn của dự báo** | **source** | `auto_eod_batch` (batch tự động) hoặc `manual_api` (người bấm nút) | `backend/app/database/models/prediction.py` |
| **Tầng dữ liệu đầu vào** | **source_layer** | Tầng mà dự báo đọc dữ liệu (ở đây là `gold`) | `backend/app/database/models/prediction.py` |
| **Migration tạo bảng** | **Alembic migration** | File mô tả cách tạo bảng mới trong MySQL | `backend/alembic/versions/0002_predictions.py` |
| **Thẻ dự báo trên Dashboard** | **NextSessionCard** | Thành phần React hiển thị dự báo phiên kế tiếp | `frontend/src/components/dashboard/NextSessionCard.tsx` |

### 5B.4.7. Chi tiết kỹ thuật

**Cờ bật trong cấu hình** (`backend/app/core/config.py`):

```python
auto_predict_enabled: bool = False
auto_predict_model: str = "linear_regression"
```

Trong container `scheduler`, `docker-compose.yml` đặt:

```yaml
      # The batch produces the next-session forecast for the symbols that
      # have a trained model.
      #
      # The model MUST be one that is trained for (almost) every symbol:
      # measured on the lakehouse (13/11/2026) there are 973
      # `linear_regression` models, 8 `arima` and 6 `lstm`. Pointing this
      # at `arima` would skip ~965 symbols silently.
      AUTO_PREDICT_ENABLED: "${AUTO_PREDICT_ENABLED:-true}"
      AUTO_PREDICT_MODEL: "${AUTO_PREDICT_MODEL:-linear_regression}"
```

**Điểm gọi từ batch EOD** (`backend/app/services/auto_refresh.py`):

```python
            if settings.auto_predict_enabled:
                try:
                    from app.services.next_session_forecast import predict_and_store

                    forecast = predict_and_store(
                        sym,
                        model_name=settings.auto_predict_model,
                        horizon=1,
                        source="auto_eod_batch",
                    )
```

**Điểm then chốt: cùng một hàm cho cả hai nơi** — trích từ docstring của
`backend/app/services/next_session_forecast.py`:

```
Step 3 lives here so the batch stays readable, and so the Dashboard and
the batch use the SAME code path to produce a forecast. A number that the
Dashboard shows and a number the batch stored must come from the same
function, otherwise the two can disagree and the disagreement is
undetectable.
```

**Khi mã chưa có mô hình — nói thẳng, KHÔNG bịa giá:**

```python
    if model_name is None:
        trained = list_trained_models(symbol)
        if not trained:
            return {
                "available": False,
                "symbol": symbol,
                "reason": (
                    f"No trained model exists for {symbol}. Train one before a "
                    "next-session forecast can be produced."
                ),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
```

**Dịch vụ này KHÔNG train mô hình** — trích từ docstring:

```
WHAT THIS NEVER DOES
--------------------
It never TRAINS a model. Training a model on the VPS is not viable: the
LSTM needs roughly 32 GB of RAM to train and the target VPS has 8 GB. The
models are trained manually on a workstation and copied to the server (see
``backend/scripts/sync_models_to_vps.py``). This service only USES models
that already exist on disk.

When a symbol has no trained model, the service says so and returns
nothing. It never substitutes a default, a moving average, or a random
number: a forecast that did not come from a model would be a fabricated
number on the Dashboard.
```

**Bảng MySQL** (`backend/app/database/models/prediction.py`):

```python
class Prediction(Base):
    """One next-session forecast for one symbol and one model."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: The trading session this forecast is about.
    target_session: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: The last close the forecast was anchored on (the close of the session
    #: BEFORE the target session).
    reference_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_close: Mapped[float] = mapped_column(Float, nullable=False)
```

> **Đo ngày 11/11/2026 — số dòng trong bảng `predictions`: 3.**
> Bảng được tạo bởi migration `backend/alembic/versions/0002_predictions.py`.
> Cách lấy số:
> ```powershell
> mysql -h 127.0.0.1 -P 13307 -uroot -p123456 stock_lakehouse -e "SELECT COUNT(*) FROM predictions;"
> ```
> Ba dòng đó là dự báo thật cho ba mã có model đã train, chạy tay qua
> `predict_and_store()` để kiểm chứng đường đi đầy đủ:
>
> | Mã | Model | Phiên đích | Giá neo | Giá dự báo | Thay đổi | Nguồn |
> |---|---|---|---|---|---|---|
> | AAPL | arima | 2026-11-10 | 350.69 | 350.14 | -0.157% | `auto_eod_batch` |
> | MSFT | linear_regression | 2026-11-10 | 545.18 | 546.64 | +0.267% | `auto_eod_batch` |
> | VCB | arima | 2026-11-11 | 53700.0 | 53685.1 | -0.028% | `auto_eod_batch` |
>
> Cả ba dòng đều có `source_layer = "gold"` — tức là con số bắt nguồn từ
> tầng Gold đã nạp, không phải từ một giá trị mặc định nào.
>
> **Số mã được dự báo trong một lần chạy EOD: chưa đo** — cần bật hạ tầng, chạy
> `docker compose --profile app up -d scheduler`, rồi đọc dòng `eod:` trong
> `backend/logs/scheduled_jobs.log`. Ở thời điểm đo, container `scheduler`
> chưa chạy trên máy này, nên em không đoán con số đó.

**Endpoint** (`backend/app/api/v1/endpoints/forecasting.py`):

| Endpoint | Việc |
|---|---|
| `GET /api/v1/forecast/next-session/{symbol}` | Dự báo phiên kế tiếp (không ghi) |
| `POST /api/v1/forecast/next-session/{symbol}/store` | Dự báo + ghi vào bảng `predictions` (nguồn `manual_api`) |

---

## 5B.5. Hiểu đơn giản: đồng hồ báo giờ tự chạy việc

### 5B.5.1. Vấn đề

Một hệ thống "tự động" mà cần bạn mở terminal gõ lệnh thì không phải tự động.
Nhưng cách chạy nền bằng thư viện `schedule` trong một tiến trình Python có một
vấn đề: **tiến trình đó chết là lịch chết theo, và không ai biết**.

Ba tình huống làm lịch biến mất trong im lặng: container bị recreate, máy khởi
động lại, và hệ điều hành giết tiến trình vì thiếu RAM. Lịch nằm trong RAM thì
mất trắng.

### 5B.5.2. Hậu quả nếu không xử lý

Sáng thứ hai bạn mở web và thấy dữ liệu đóng cửa của thứ Sáu. Không có báo cáo
lỗi, không có log, chỉ có **sự im lặng**. Đó là loại lỗi tệ nhất vì không ai
trả lời được.

### 5B.5.3. Cách hệ thống xử lý

Đặt một **đồng hồ báo giờ thật** (cron) vào một container riêng, và để lịch nằm
trong **một file trong repository** — không nằm trong RAM, không nằm trong code.

Ba điều kiện để lịch sống sót:

1. **Lịch nằm trong file** (`backend/crontab`) → đọc vào Git, ai cũng thấy, ai
   cũng sửa được, và **không mất** khi container bị recreate.
2. **Docker giám sát** (`restart: unless-stopped`) → container chết sẽ tự lên lại.
3. **Mọi lần chạy đều ghi log có ngày giờ** vào `backend/logs/scheduled_jobs.log`
   → "đêm qua có chạy không?" có câu trả lời tra cứu được.

### 5B.5.4. Hình vẽ

```
┌──────────────────────────────────────────────────────────────────────────┐
│  container "scheduler"   (dùng chung image với backend)                  │
│  command: ["cron", "-f", "-L", "15"]   ·   user: root   ·   TZ: UTC      │
│  mount: ./backend/crontab → /etc/cron.d/stock-lakehouse  (read-only)     │
│  restart: unless-stopped                                                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │  đọc lịch (giờ UTC)
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  backend/crontab                                                         │
│                                                                          │
│   30 21  * * 1-5   ... run_scheduled_job.py eod        ← NYSE (21:30)    │
│   30 3   * * 1-5   ... run_scheduled_job.py eod        ← HOSE (03:30)    │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  backend/scripts/run_scheduled_job.py   <job>                            │
│                                                                          │
│    eod       → auto_refresh.run_once()  → nạp giá → Silver/Gold          │
│                            → dự báo phiên kế tiếp → MySQL predictions    │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LOG: backend/logs/scheduled_jobs.log   (mỗi dòng có mốc thời gian UTC)  │
│                                                                          │
│    <dòng ví dụ minh hoạ định dạng, KHÔNG phải log thật của máy này>:     │
│    2026-11-09T21:30:04+00:00 start job=eod                               │
│    2026-11-09T21:34:51+00:00 eod: symbols=... silver=... gold=...        │
│    2026-11-09T21:34:52+00:00 done job=eod elapsed=...                    │
└──────────────────────────────────────────────────────────────────────────┘
```

> **Lưu ý:** 3 dòng log trong hình trên là **ví dụ minh hoạ về định dạng**, không
> phải log thật của máy này. Log thật nằm ở `backend/logs/scheduled_jobs.log` và
> phải được đọc trực tiếp để lấy số thật.

### 5B.5.5. Đọc hình vẽ bằng lời đời thường

Hình này giống một cái đồng hồ báo giờ gắn trên tường với một quyển lịch ghi bên
cạnh. **Quyển lịch** là file `backend/crontab` — nó nằm trong repository nên đưa vào
Git là có người khác đọc được, và thay đổi lịch không cần sửa code.

**Cái đồng hồ** là container `scheduler`, chạy câu lệnh `cron -f`. Chữ `-f` nghĩa
là "chạy ở chế độ tiền cảnh" để Docker theo dõi được; nếu không có nó, container
sẽ thoát ngay lập tức. Câu `cron` cần chạy bằng quyền root vì nó đọc thư mục
`/etc/cron.d` — và vì nó cần quyền đổi sang người dùng ghi ở ô thứ sáu của dòng
lịch.

**Hai dòng lịch** trên quyển lịch có hai nhịp khác nhau, nhưng cùng một loại việc:
batch EOD chạy **hai lần/ngày** — một lần sau khi NYSE đóng cửa, một lần sau khi
HOSE đóng cửa. (Trước đây còn có dòng thu thập tin tức mỗi 30 phút; dòng đó đã bị
xoá cùng toàn bộ hệ thống tin tức ngày 12/11/2026 — xem Phần 5B.1.)

Điểm đáng chú ý nhất là **thùng gỗ cuối cùng**: mọi lần chạy đều ghi lại một dòng
có mốc thời gian. Nếu bạn quay lại sau một tuần và hỏi "đêm thứ ba có chạy
không?", bạn mở file log ra là biết. Đó là khác biệt giữa một hệ thống **im lặng
khi hỏng** và một hệ thống **nói ra**.

### 5B.5.6. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Đồng hồ báo giờ** | **Cron** | Chương trình gọi một lệnh theo lịch cố định | `backend/crontab` |
| **Quyển lịch** | **Crontab file** | File liệt kê các dòng lịch (giờ, ngày, lệnh) | `backend/crontab` |
| **Chạy ở chế độ tiền cảnh** | **`cron -f`** | Chế độ để Docker theo dõi tiến trình cron | `docker-compose.yml` (service `scheduler`) |
| **Tự lên lại khi chết** | **`restart: unless-stopped`** | Docker tự khởi động lại container nếu nó chết | `docker-compose.yml` |
| **Ghim múi giờ UTC** | **`TZ: UTC`** | Bảo đảm giờ trong crontab luôn là UTC, không phụ thuộc máy chủ | `docker-compose.yml` |
| **Job theo lịch** | **Scheduled job** | Một loại việc mà cron gọi: `eod` | `backend/scripts/run_scheduled_job.py` |
| **Batch cuối ngày** | **EOD job** | Job cập nhật giá + dựng lại tầng + dự báo phiên kế tiếp | `backend/scripts/run_scheduled_job.py` |
| **Nhật ký có dấu thời gian** | **Scheduled job log** | File ghi lại mọi lần chạy, có mốc UTC | `backend/logs/scheduled_jobs.log` |
| **Giờ UTC** | **UTC timetable** | Mốc giờ của lịch: NYSE 21:30, HOSE 03:30 | `backend/crontab` |

### 5B.5.7. Chi tiết kỹ thuật

**Lịch** (`backend/crontab`, giờ UTC):

```cron
# ── End-of-day batch (price layers + next-session forecast) ────────────────
# NYSE: 21:30 UTC (after the 20:00/21:00 UTC close)
30 21 * * 1-5 root cd $APP_HOME && /opt/venv/bin/python scripts/run_scheduled_job.py eod >> $APP_HOME/logs/cron.log 2>&1

# HOSE: 03:30 UTC (after the 02:30 UTC close)
30 3 * * 1-5 root cd $APP_HOME && /opt/venv/bin/python scripts/run_scheduled_job.py eod >> $APP_HOME/logs/cron.log 2>&1
```

**Vì sao chọn các giờ này** — trích từ chính file crontab:

```
#   * NYSE closes at 20:00 UTC (16:00 America/New_York) in EDT, and at
#     21:00 UTC in EST. The batch runs at 21:30 UTC, which is after BOTH
#     closes - running at 20:30 would miss the last hour of every summer
#     session.
#   * HOSE closes at 02:30 UTC (09:30 Asia/Ho_Chi_Minh). The batch runs
#     at 03:30 UTC.
```

**Một job** (`backend/scripts/run_scheduled_job.py`):

```python
JOBS = {
    "eod": run_eod,
}
```

**Job EOD** — chạy batch rồi ghi log:

```python
def run_eod(args: argparse.Namespace) -> dict:
    """The end-of-day batch: refresh the price layers, then forecast."""
    from app.services.auto_refresh import AutoRefreshService

    service = AutoRefreshService()
    summary = service.run_once()
    _log_line(
        f"eod: symbols={summary.get('symbols_total')} "
        f"silver={summary.get('silver_rebuilt')} gold={summary.get('gold_rebuilt')} "
        f"forecasts={summary.get('next_session_forecasts')} "
        f"errors={len(summary.get('errors') or [])}"
    )
    return summary
```

**Một job lỗi KHÔNG được làm hỏng cả lịch:**

```python
    try:
        result = JOBS[args.job](args)
    except Exception as exc:  # noqa: BLE001
        # A failing job must not take cron down. cron keeps running the
        # timetable regardless, and the log line records the failure.
        logger.exception("Scheduled job %s failed", args.job)
        _log_line(f"fail job={args.job} error={exc}")
        print(json.dumps({"job": args.job, "ok": False, "error": str(exc)}))
        traceback.print_exc()
        return 1
```

**File log là bản ghi DUY NHẤT** — trích từ docstring của `_log_line()`:

```
    """Append a dated line to the scheduled-job log.

    The file is the ONLY record of what cron ran. Container stdout is
    rotated away by Docker, and `docker compose logs` is not a place to look
    three weeks later when asking "did last night's batch run?".
    """
```

**Container `scheduler`** (`docker-compose.yml`):

```yaml
  scheduler:
    profiles: ["app", "all"]
    image: stock-lakehouse-backend:latest
    container_name: stock-lakehouse-scheduler
    restart: unless-stopped
    # cron has to run as root: it reads /etc/cron.d, which it refuses to
    # load for a non-root user, and it needs the privilege to switch to
    # the user named in the crontab's sixth field.
    user: root
    ...
    volumes:
      - type: bind
        source: ./backend/crontab
        target: /etc/cron.d/stock-lakehouse
        read_only: true
      # The trained models live on the local filesystem, not in MinIO. They
      # MUST be mounted, or the batch finds no model and the forecast step
      # is skipped.
      - type: bind
        source: ./backend/data/models
        target: /app/data/models
      - type: bind
        source: ./backend/logs
        target: /app/logs
    # `cron -f` runs in the foreground so Docker can supervise it.
    command: ["cron", "-f", "-L", "15"]
```

> **Đo ngày 10/11/2026:** số lần chạy thực tế của cron trên máy này: **chưa đo** —
> container `scheduler` chưa được bật khi đo. Cách lấy số:
> ```powershell
> Get-Content backend/logs/scheduled_jobs.log | Measure-Object -Line
> ```
> File `backend/logs/scheduled_jobs.log` được sinh ra bởi chính các job khi chạy.

**Vì sao dùng cron thật thay vì thư viện `schedule`** — trích từ docstring:

```
WHY A SCRIPT AND NOT THE `schedule` LIBRARY
--------------------------------------------
The project used to run its batch through ``scripts/schedule_batch.py``,
which uses the ``schedule`` package inside a standalone Python process. That
process dies with the machine, and it is not supervised by Docker: if the
container is recreated, the schedule is gone.

A real cron inside a container is supervised by the container runtime: the
``scheduler`` service in ``docker-compose.yml`` runs ``cron -f``, and
``backend/crontab`` holds the timetable. The container restarts with
``restart: unless-stopped``, so the timetable survives a crash and a
reboot.
```

---

# PHẦN 5B.6 — KIỂM CHỨNG DỰ BÁO (VÒNG LẶP ĐÓNG)

> Sơ đồ: [3. Quy trình train & dự báo](./SO_DO_MINH_HOA.md#3)

## 5B.6.1. Hiểu đơn giản

### Bối cảnh vấn đề

Đến trước ngày 13/11/2026, hệ thống dự báo **chỉ đi một chiều**. Mỗi tối sau khi
thị trường đóng cửa, nó hỏi mô hình "ngày mai giá ra sao", rồi ghi con số đó
xuống một bảng. Rồi nó **dừng lại**.

Hệ quả là một câu hỏi không ai trả lời được: *"Hệ thống này dự báo có chính
xác không?"*. Con số MAE/MAPE hiện trên trang Dự báo là câu trả lời cho một câu
hỏi **khác**: "mô hình này chính xác cỡ nào trên những phiên đã xảy ra trước khi
mô hình được xây?". Đó là **backtest** — đo mô hình. Còn đồ án cần đo **hệ
thống**: "những dự báo hệ thống thực sự đã công bố, có đúng không?".

Giống như học sinh làm bài kiểm tra rồi **không bao giờ biết điểm**: bài làm
đẹp không chứng minh được gì. Chỉ khi thầy chấm điểm và mình thấy điểm thực tế
mới biết mình học có đúng không.

### Hậu quả nếu không xử lý

- Khi thầy hỏi "độ chính xác thực tế của hệ thống là bao nhiêu?", đồ án
  **không có câu trả lời nào ngoài backtest** — và backtest là con số trong
  phòng kín, không phải con số ngoài đời.
- Ngày 13/11/2026, bảng `predictions` chỉ có **3 dòng** được kiểm chứng.
  Ba dòng không phải là một phép đo, đó là một giai thoại.

### Cách hệ thống xử lý

Hệ thống đóng vòng lặp: **dự báo → chờ phiên xảy ra → chấm điểm với giá thật**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  TỐI HÔM TRƯỚC (sau khi thị trường đóng cửa)                             │
│                                                                          │
│  1. Nạp giá hôm nay vào Bronze → dựng lại Silver/Gold                    │
│  2. Hỏi mô hình: "phiên ngày mai giá đóng cửa là bao nhiêu?"             │
│  3. GHI XUỐNG SỔ: bảng MySQL `predictions`                               │
│     (mã, mô hình, phiên đích, giá neo, giá dự báo, nguồn)                │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   (qua đêm, có thể   │
                    │    vài ngày đứt net) │
                    └──────────┬───────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  TỐI HÔM SAU (phiên vừa đóng cửa)                                        │
│                                                                          │
│  4. Đọc giá đóng cửa THẬT của phiên đích từ tầng Gold                    │
│  5. So sánh với giá đã dự báo:                                           │
│       sai số tuyệt đối = |giá dự báo − giá thật|                         │
│       sai số tương đối = sai số tuyệt đối / giá neo                      │
│       đúng hướng       = dự báo lên mà thực tế cũng lên (và ngược lại)   │
│  6. GHI KẾT QUẢ VÀO CHÍNH DÒNG ĐÓ (cột actual_close, abs_error, ...)     │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SỔ TAY `predictions` — mỗi dòng là một cam kết đã được kiểm chứng       │
│                                                                          │
│  Người đọc thấy: dự báo bao nhiêu, thực tế ra bao nhiêu, sai bao nhiêu   │
│  Đây là BẰNG CHỨNG ngoài tập huấn luyện, không phải backtest             │
└──────────────────────────────────────────────────────────────────────────┘
```

### Đọc hình vẽ bằng lời đời thường

Hình trên là một ca trực kéo dài nhiều ngày. Mỗi tối, hệ thống làm đúng một
việc: **ghi con số mình tin vào sổ tay, trước khi biết kết quả**. Sáng hôm sau,
khi giá thật đã có, hệ thống mở sổ ra và đối chiếu.

Điểm mấu chốt nằm ở chỗ **ghi trước, chấm sau**. Nếu hệ thống chỉ dự báo
rồi ngay lập tức tự chấm bằng chính dữ liệu nó vừa dùng để dự báo, thì con
số đó sẽ luôn đẹp và vô nghĩa — giống như tự chấm bài rồi tự chấm điểm. Việc
hai thời điểm tách bạch là điều làm cho bằng chứng trở thành bằng chứng.

### Vì sao phải có cả những dòng "tái dựng từ tập hold-out"

Vòng lặp cần **thời gian** để đầy: mỗi ngày chỉ sinh thêm một dòng. Để có số
liệu ngay trong kỳ luận văn, hệ thống còn **tái dựng** sẵn dự báo của chính mô
hình trên tập kiểm tra lịch sử — mỗi phiên một bước, mô hình chỉ được thấy dữ
liệu đến trước phiên đó.

Hai loại dòng **không được trộn lẫn**, và hệ thống ghi rõ nguồn của từng dòng:

| Nguồn của dòng | Nghĩa là gì | Sức bằng chứng |
|---|---|---|
| `auto_eod_batch` | Hệ thống **đã công bố** trước khi phiên mở cửa | Mạnh — là cam kết thật |
| `manual_api` | Người bấm nút trên web để dự báo | Trung bình |
| `backfill_walk_forward` | Mô hình được **tái chạy** sau trên tập hold-out | Tham khảo — đo mô hình, không đo hệ thống |

> **Cách trả lời khi thầy hỏi "số liệu này có phải backtest không?":**
> *"Phần lớn số dòng hiện tại là kết quả tái dựng mô hình trên tập hold-out
> (nguồn `backfill_walk_forward`), nên nó đo mô hình chứ không đo hệ thống đang
> chạy. Phần đáng tin hơn là những dòng nguồn `auto_eod_batch` — dự báo được
> ghi xuống trước khi phiên mở cửa. Con số này mới tăng lên mỗi ngày, và đó
> là điểm em muốn bảo vệ: hệ thống không tự trình bày con số đẹp hơn nó thực
> sự là."*

## 5B.6.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Ghi trước, chấm sau** | **Forecast → score loop** | Dự báo được lưu trước phiên, điểm được chấm sau phiên | `backend/app/services/forecast_scoring.py` |
| **Sổ tay dự báo** | **Verification ledger** | Bảng `predictions` — mỗi dòng là một dự báo kèm kết quả thật | `backend/app/database/models/prediction.py` |
| **Chấm điểm** | **Scoring pass** | So dự báo với giá đóng cửa thật đọc từ Gold | `backend/app/services/forecast_scoring.py` |
| **Sai số tuyệt đối** | **MAE (Mean Absolute Error)** | Trung bình của `\|giá dự báo − giá thật\|` | `backend/app/database/repositories/prediction_repository.py` |
| **Sai số tương đối** | **Mean error percentage** | Trung bình của sai số tuyệt đối chia cho giá neo | `backend/app/database/repositories/prediction_repository.py` |
| **Đúng hướng** | **Directional accuracy** | Tỉ lệ phiên mà dự báo đúng chiều đi của thị trường | `backend/app/services/forecast_scoring.py` |
| **Giá neo** | **reference_close** | Giá đóng cửa của phiên **trước** phiên đích — mốc đo hướng đi | `backend/app/services/forecast_scoring.py` |
| **Dự báo đã công bố** | **Published forecast** | Dự báo nguồn `auto_eod_batch` — ghi trước phiên mở cửa | `backend/app/services/universe_forecast.py` |
| **Dự báo tái dựng** | **Backfilled forecast** | Dự báo nguồn `backfill_walk_forward` — mô hình tái chạy sau trên tập hold-out | `backend/app/services/forecast_backfill.py` |
| **Đường đi nhẹ** | **Light forecast path** | Đường tính nhanh dùng cho batch toàn bộ mã, **cho ra kết quả y hệt** đường đầy đủ | `backend/app/forecasting/light_forecast.py` |
| **Lịch giao dịch của mã** | **Symbol trading calendar** | Các ngày mà mã đó thực sự giao dịch, **suy ra từ lịch sử Gold của chính nó** | `backend/app/forecasting/sessions.py` |
| **Huấn luyện toàn bộ mã** | **Universe training** | Train mô hình cho mọi mã có dữ liệu Gold, bỏ qua mã đã có model mới | `backend/app/forecasting/universe_training.py` |

## 5B.6.3. Chi tiết kỹ thuật

### Bảng dữ liệu — cột kết quả nằm chung dòng với cột dự báo

Migration `backend/alembic/versions/0004_prediction_scoring.py` bổ sung 5 cột vào
bảng `predictions`:

| Cột | Ý nghĩa | Ghi bởi ai |
|---|---|---|
| `actual_close` | Giá đóng cửa thật của phiên đích, đọc từ Gold | Bước chấm điểm |
| `abs_error` | `abs(predicted_close − actual_close)` | Bước chấm điểm |
| `error_pct` | `(predicted_close − actual_close) / reference_close` | Bước chấm điểm |
| `direction_correct` | `1` = đúng chiều, `0` = sai chiều, `NULL` = phiên không có hướng | Bước chấm điểm |
| `scored_at` | Thời điểm chấm điểm | Bước chấm điểm |

**Vì sao cột kết quả nằm chung dòng với cột dự báo** (thay vì tách bảng riêng):
vì câu hỏi cần trả lời là "dự báo này có đúng không", và câu trả lời phải đi
cùng dự báo đó. Tách bảng sẽ phải join theo khóa (mã, mô hình, phiên) — thêm
một chỗ có thể lệch, vào một hệ thống mà nguyên tắc là **mọi thứ phải truy
vết được**.

**Vì sao lần ghi lại không xoá điểm đã có** — trích từ `prediction_repository.py`:

```python
    def upsert(self, payload: dict[str, Any]) -> Prediction:
        """Store a forecast, replacing any earlier one for the same target."""
        symbol = str(payload["symbol"]).upper()
        model_name = payload["model_name"]
        target_session = payload["target_session"]
        # ...
            # The outcome columns are deliberately excluded: a forecast
            # re-run must not erase a score that was already computed for
            # a session that has since happened.
            outcome_fields = _OUTCOME_FIELDS
            for key, value in payload.items():
                if key in ("id", *outcome_fields):
                    continue
                setattr(record, key, value)
```

### Bước chấm điểm — giá thật đến từ đâu

`backend/app/services/forecast_scoring.py`:

```python
        for forecast in pending:
            actual = closes.get(forecast.target_session)
            if actual is None:
                # The target session has not been ingested yet. It stays
                # unscored, and it will be picked up by a later pass.
                skipped.append(forecast.target_session.isoformat())
                continue
            payload = score_forecast(forecast, actual)
```

Điểm then chốt: giá thật đến từ **tầng Gold**, cùng nguồn mà mọi endpoint khác
đọc. Nếu Gold chưa có bar cho phiên đích thì dòng **được giữ nguyên chưa chấm**
— không tự điền số 0, không ấn định giá. Đây là điểm khác biệt giữa "chưa kiểm
chứng" và "kiểm chứng sai".

### Vì sao "đúng hướng" là con số chính

Sai số tuyệt đối nằm trong **đơn vị giá của từng mã** — AAPL quanh 340, VCB quanh
53.500 — nên không thể so sánh giữa các mã. Sai số tương đối thì so sánh được, và
"đúng hướng" thì so sánh được tuyệt đối. Vì vậy bảng điều khiển hiển thị
"đúng hướng" làm số chính, sai số tương đối làm số phụ, còn MAE làm số riêng cho
từng mã.

### Toàn bộ mã, không chỉ mã "chọn lọc"

`backend/app/forecasting/universe_training.py` huấn luyện cho **mọi mã có dữ
liệu Gold**:

```python
def _has_fresh_model(symbol: str, model_name: str, gold: pd.DataFrame) -> bool:
    """Whether the stored model already covers the newest Gold session."""
```

Mô hình cũ hơn phiên mới nhất trong Gold thì được train lại — vì một mô hình neo
trên giá cũ sẽ dự báo sai cả khoảng cách đã trôi qua.

**Mô hình nền tảng là Linear Regression**, không phải ARIMA hay LSTM, vì ở quy
mô ~1.000 mã thì chi phí mới là thứ quyết định:

| Mô hình | Thời gian train / mã | Kích thước / mã |
|---|---|---|
| `linear_regression` | ~0,45 s | ~3 KB |
| `arima` | ~11 s | ~11 MB |

ARIMA và LSTM vẫn được giữ và dùng cho **phân tích so sánh trên các mã tiêu
biểu** (Phần 6), nhưng không chạy cho toàn bộ 1.000 mã.

### Đường đi nhẹ — bảo đảm kết quả y hệt

Batch toàn bộ mã cần tốc độ, nhưng **không được khác kết quả**. Vì vậy phần
tính toán được tách ra một chỗ duy nhất (`backend/app/forecasting/light_forecast.py`)
và cả đường đầy đủ lẫn đường batch đều gọi chính nó:

```python
# backend/app/forecasting/predictor.py
    series = light_forecast.future_series(symbol, model_name, gold, horizon=horizon)
```

Kiểm chứng bằng test `backend/tests/test_light_path_matches_full_path.py` — so
sánh đường nhẹ với đường đầy đủ trên tập mã, khẳng định **không có sai lệch
dù một số**. Kết quả: **12/12 test pass** (đo ngày 13/11/2026).

### Lịch giao dịch của mã — dự báo phải nhắm đúng ngày có giao dịch

**Hiểu đơn giản:** một dự báo phải nói rõ nó nói về **phiên nào**. Nếu nó nhắm
vào một ngày mà sàn không giao dịch, dòng đó **không bao giờ được chấm điểm** —
không phải vì hệ thống hỏng, mà vì ngày đó không tồn tại trong dữ liệu thật.

**Triệu chứng (đo ngày 13/11/2026):** bảng `predictions` có **151 dòng** nhắm tới
`target_session = 2026-11-14` — **thứ Bảy**. Không sàn nào giao dịch vào thứ Bảy,
nên Gold sẽ không bao giờ có bar cho ngày đó, nên 151 dòng nằm trong sổ tay kiểm
chứng **vĩnh viễn chưa chấm**. Đúng 151 dòng = số mã có phiên cuối cùng là
13/11 (các mã VN/HK/KR), vì phiên cuối của chúng rơi vào thứ Năm–Thứ Sáu nên
"+1 ngày" trượt sang thứ Bảy.

**Vì sao xảy ra:** chiến lược dự báo dùng **bước lịch** (calendar step) để đặt
timestamp cho các phiên tương lai:

```python
# code cũ — multistep.py và light_forecast.py
freq = pd.infer_freq(usable["timestamp"])
if not freq:
    deltas = usable["timestamp"].diff().dropna()
    step = deltas.median() if not deltas.empty else pd.Timedelta(days=1)
...
next_ts = current_ts + step
```

Trên một chuỗi giá cổ phiếu **thật**, khoảng cách giữa các phiên không đều
(cuối tuần, ngày lễ), nên `pd.infer_freq` trả về `None`. Lúc đó phương án dự phòng
là **trung vị khoảng cách = 1 ngày lịch**. Một ngày lịch sau thứ Sáu là **thứ Bảy**.

**Fix — lịch giao dịch suy ra từ chính lịch sử của mã đó.** File mới
`backend/app/forecasting/sessions.py`:

- **Thứ trong tuần giao dịch**: đọc từ các bar trong lịch sử Gold của chính mã đó.
- **Ngày lễ cố định**: một ngày vắng mặt trong **nhiều năm khác nhau** là ngày lễ,
  không phải lỗ hổng dữ liệu.
- **Ngày lễ di động** (ví dụ "thứ Hai thứ ba của tháng Một"): nhận ra được vì có
  cùng một quy tắc lặp lại qua nhiều năm.
- **Ngày lễ rơi vào cuối tuần**: sàn đóng cửa vào **ngày khác**, và ngày nào là
  một đặc điểm của sàn — học **riêng cho từng ngày lễ**, không dùng một quy tắc
  chung cho cả lịch. (Sàn Mỹ đóng Friday trước khi lễ rơi vào thứ Bảy; sàn Hàn
  Quốc đóng Monday kế tiếp.)
- **Ngày bị kẹp giữa hai ngày nghỉ** (quy tắc "ngày công dân" của sàn Nhật): học
  **theo từng cặp (tháng, ngày)**, và chỉ chấp nhận khi sàn đóng **cả** những
  lần bị kẹp đó.
- **Mốc sàn**: phiên đích phải nằm **không sớm hơn hôm nay**, để một mã bị
  cũ không dự báo về một phiên đã qua.

```python
# backend/app/forecasting/sessions.py
calendar = sessions.build_calendar(gold)          # lịch của riêng mã này
targets = calendar.next_sessions(after=last_day, count=horizon)
```

**Vì sao không hard-code bảng ngày lễ:** dự án chứa niêm yết của **nhiều sàn**
(Mỹ, Việt Nam, Hồng Kông, Hàn Quốc, Nhật, Úc). Một bảng ngày lễ Mỹ sẽ sai cho
từng mã ngoài Mỹ, và phải cập nhật tay mỗi năm. Lịch suy từ lịch sử thì đúng với
mọi mã, vì nó **không giả định mình đang nhìn lịch nào**.

**Cửa sổ đánh giá — vì sao phải nhìn vào các năm gần đây:** một ngày lễ được
**thay đổi quy tắc** theo thời gian sẽ bị đánh giá sai nếu tính trên toàn bộ
lịch sử. Ví dụ ngày lễ Nhật "Kính lão" chuyển sang **thứ Hai thứ ba của tháng
Chín** từ năm 2019 — trên toàn bộ lịch sử nó chỉ chiếm 78% số năm, nên một
ngưỡng 80% sẽ **loại bỏ** một ngày lễ mà sàn thực sự đóng mọi năm. Vì vậy mọi
quy tắc được đánh giá trên **6 năm gần nhất**: đó là các năm **matters** nhất,
vì dự báo nhắm tới một phiên trong tương lai gần, và nó cũng là cách bắt được
ngày lễ **bị bãi bỏ** trong những năm gần đây.

**Giới hạn thành thật của cách này:** một ngày lễ mà sàn dời sang một ngày mà
lịch sử **chưa từng** có thì không thể biết trước — đặc biệt là **ngày lễ âm
lịch** (Tết, Trung thu), vì quy tắc của chúng **không có hằng số nào** để
viết ra. Cách tốt nhất — và cách đã làm — là nhận ra các **quy tắc lặp lại**,
phủ được mọi ngày lễ cố định và mọi ngày lễ định nghĩa theo thứ trong tháng.
Sai số còn lại là **một** dòng dự báo mỗi mã mỗi năm, và dòng đó **được giữ
nguyên chưa chấm** chứ không trở thành một con số sai.

**Bằng chứng (đo ngày 13/11/2026):**

| Mã | Phiên cuối trong Gold | Phiên đích **trước** fix | Phiên đích **sau** fix |
|---|---|---|---|
| AAPL (Mỹ) | 2026-11-12 | 2026-11-13 (thứ Sáu) | 2026-11-13 (thứ Sáu) |
| VNM (Việt Nam) | 2026-11-13 | **2026-11-14 (thứ Bảy)** | **2026-11-16 (thứ Hai)** |
| FPT (Việt Nam) | 2026-11-13 | **2026-11-14 (thứ Bảy)** | **2026-11-16 (thứ Hai)** |
| 0001.HK (Hồng Kông) | 2026-11-13 | **2026-11-14 (thứ Bảy)** | **2026-11-16 (thứ Hai)** |
| 005930.KS (Hàn Quốc) | 2026-11-13 | **2026-11-14 (thứ Bảy)** | **2026-11-16 (thứ Hai)** |

Lịch suy ra từ lịch sử AAPL nhận ra đúng các ngày lễ Mỹ: `01/01`, `04/07`,
`25/12` (cố định) và "thứ Hai thứ ba tháng 1", "thứ Hai thứ ba tháng 2", "thứ Hai
thứ tư tháng 5", "thứ Hai đầu tháng 9", "thứ Năm thứ tư tháng 11" (di động).

**Kiểm chứng bằng dữ liệu thật — backtest hold-out 30 phiên (đo ngày 13/11/2026).**
Lịch được xây **chỉ từ lịch sử tính đến thời điểm cắt** (không nhìn thấy tương
lai), rồi so với 30 phiên thực tế còn lại trong Gold:

| Mã | Sàn | Kết quả |
|---|---|---|
| AAPL, MSFT, NVDA, TSLA, BIDU, BABA | Mỹ | **khớp tuyệt đối 30/30 phiên** |
| 7203.T, 6758.T | Nhật | **khớp 29/30 phiên** (thiếu 1 phiên do ngày lễ âm lịch) |
| 0001.HK, 9988.HK, 1398.HK | Hồng Kông | 20/30 (sai ở các ngày lễ âm lịch) |
| 005930.KS, 051910.KS | Hàn Quốc | 6/30 (sai ở các ngày lễ âm lịch) |
| VNM | Việt Nam | 19/30 (sai ở Tết và ngày nghỉ âm lịch) |

Phân tầng này **đúng như thiết kế**: sàn Mỹ và Nhật có ngày lễ theo lịch dương
nên lịch suy ra phủ hết; các sàn Á chưa có phần lớn ngày lễ âm lịch nên phần
sai là **ngày lễ âm lịch** — thứ mà **không quy luật nào** có thể học.

**Kiểm chứng bằng test:** test `backend/tests/test_forecast_session_calendar.py` —
18/18 pass (đo ngày 13/11/2026), gồm các trường hợp: cuối tuần không bao giờ được
nhắm, ngày lễ cố định bị bỏ qua, ngày lễ di động được nhận ra, **một lỗ hổng
đơn lẻ KHÔNG bị coi là ngày lễ** (nếu coi thì lịch sẽ bỏ sót những phiên giao
dịch có thật), ngày lễ rơi vào cuối tuần học **riêng theo từng ngày lễ**, và
một mã có lịch riêng (giao dịch cả thứ Bảy) vẫn được tôn trọng.

### Chi phí đo được của một lần chạy toàn bộ mã

Đo ngày 13/11/2026 trên máy này (Windows, `backend/.venv`):

| Bước | Thời gian |
|---|---|
| Đọc Gold | ~0,41 s / mã |
| Train `linear_regression` | ~0,45 s / mã |
| Dự báo 1 bước (đường nhẹ) | ~0,02 s / mã |

Suy ra cho toàn bộ ~1.000 mã:

- Huấn luyện (chỉ những mã cũ): **~7 phút**
- Dự báo: **~18 giây**
- Chấm điểm: gần như miễn phí, vì **dùng chung một lần đọc Gold** với bước
  dự báo — dữ liệu đã nằm trong bộ nhớ.

### Kết quả đo thật

Đo ngày **15/11/2026**, bảng `predictions` sau khi chạy huấn luyện toàn bộ mã, tái
dựng sổ tay, một lượt dự báo toàn bộ mã, **và sau khi xoá 200 dòng dự báo bịa**
(xem mục "Lỗi 3" bên dưới):

| Chỉ số | Giá trị |
|---|---|
| Tổng số dòng trong bảng `predictions` | **46.505** |
| Dòng đã được chấm điểm (có `actual_close`) | **46.385** |
| Số mã khác nhau có dòng đã chấm | **973** |
| Số mã đã huấn luyện thành công | **973** (29 mã không có dữ liệu đủ để train) |
| Dòng nguồn `auto_eod_batch` | **1.341** (dự báo phiên kế tiếp, chưa tới phiên nên chưa chấm) |
| Dòng nguồn `backfill_walk_forward` đã chấm | **45.240** |
| **Mã không có dữ liệu thật trong Gold** | **0** |

**Số đo của toàn bộ dòng đã chấm** (đo ngày **17/11/2026**, sau khi sửa lỗi
"Lock wait timeout" — xem mục 6.12.5 — 695 dòng còn chờ được chấm):

| Chỉ số | Giá trị |
|---|---|
| Số dòng đã chấm (trước khi lọc) | 46.385 |
| Số dòng đã chấm (sau khi lọc) | **45.631** |
| **Sai số tương đối TRUNG VỊ** | **1,15%** |
| **Sai số tương đối trung bình (có dấu)** | **0,43%** |
| **WAPE** (sai số tuyệt đối có trọng số) | **2,75%** |
| Tỉ lệ đúng hướng | **50,6%** |
| MAE (trộn nhiều mã) | 333,16 |
| Số dòng bị loại (giá dự báo không tồn tại) | 76 |

### Vì sao trung bình 263,85% là **LỖI MÔ HÌNH**, không phải lỗi thống kê

> **Phần này thay thế cách giải thích cũ.** Bản đầu của tài liệu này gán
> con số 263,85% cho việc "trộn các mã giá rất nhỏ". **Giả thuyết đó sai**, và
> em đã kiểm chứng bằng số thật rồi sửa lại. Dưới đây là toàn bộ chuỗi
> kiểm chứng.

**Bước 1 — kiểm tra giả thuyết "mã giá nhỏ".** Câu hỏi ban đầu là: con số
trung bình vô lý vì các mã như `VIV.PA` (giá 1,69) có mẫu số nhỏ. Kiểm tra:

| Kiểm tra | Kết quả |
|---|---|
| Số dòng của `VIV.PA` đã chấm trong toàn bộ sổ tay | **1** |
| Sai số của dòng đó | **3,93%** (ref 1,679 — dự 1,756 — thực 1,69) |
| Trung bình sau khi loại **mọi** dòng có `reference_close < 1,0` | **91,95%** (vẫn hỏng) |

Kết luận: `VIV.PA` không gây ra vấn đề. Loại hết mã giá nhỏ thì con số vẫn vô
lý. **Giả thuyết "mẫu số nhỏ" bị bác bỏ.**

**Bước 2 — truy vết tổng sai số về từng mã.** Tổng `|error_pct|` của toàn bộ
44.676 dòng đã chấm là **11.792.660**. Phân rã theo mã:

| Mã | Số dòng | Tổng `|error_pct|` | Chiếm tỉ lệ |
|---|---|---|---|
| **`PARA`** | 60 | **11.791.832** | **99,993%** |
| `LCID` | 60 | 31,98 | 0,0003% |
| `ACH` | 61 | 19,78 | 0,0002% |
| `NTLA` | 60 | 8,36 | 0,0001% |

Bỏ riêng `PARA` ra thì trung bình giảm từ **+26.385,49%** xuống **-0,0329%**,
và trung bình sai số tuyệt đối từ 26.395,96% xuống **1,8541%** — khớp gần
đúng với trung vị 1,15%.

**Bước 3 — tìm nguyên nhân gốc trong dữ liệu và trong mô hình.**

`PARA` **không phải** là một cổ phiếu giá rẻ bình thường. Lịch sử giá của nó
trong tầng Bronze/Gold trải trên **ba bậc độ lớn**:

```
2021   close ~ 101.500
2024   close ~   1.648
2026   close ~   0,104
```

Yahoo Finance báo **bốn lần chia ngược** cho PARA: 1:50 ngày 19/09/2024,
1:10 ngày 08/07/2025, 1:20 ngày 08/05/2026, 1:10 ngày 27/10/2026. Lakehouse
được nạp dữ liệu qua nhiều ngày, nên các partition lưu **không cùng một quy
mô giá**. Đây là một **điểm gãy thang giá** (price-scale discontinuity), không
phải một cổ penny stock.

Mô hình `linear_regression` dùng **mức giá** làm đặc trưng (`close`,
`sma_5`, `sma_20`, `sma_50`, `bb_upper`...). Khi huấn luyện trên một chuỗi
trải trên ba bậc độ, hệ số hồi quy học được không có gì có ý nghĩa, và phần
**ngoại suy** rơi vào bất kỳ đâu — kể cả âm:

| Phiên | Giá tham chiếu | Giá dự báo | Giá thực | Sai số |
|---|---|---|---|---|
| PARA 12/11/2026 | 0,072 | **242.751** | 0,101 | **+337.154,0%** |
| PARA 05/11/2026 | 0,319 | **329.139** | 0,164 | +103.178,0% |
| PARA 28/10/2026 | 4,1395 | **-942,13** | 3,36 | -228,4% |
| PARA 29/10/2026 | 3,36 | **-5.674,80** | 4,28 | -1.690,2% |

**Bước 4 — phát hiện thêm 19 dòng có giá dự báo ÂM.** Đây không phải "sai số
lớn" mà là **giá không tồn tại**:

| Mã | Phiên | Tham chiếu | Dự báo |
|---|---|---|---|
| `LCID` | 21/10/2026 | 3,27 | **-4,0937** |
| `ACH` | 03/11/2026 | 0,26 | **-0,1143** |
| `SOXS` | 13/11/2026 | 45,72 | **-359.121.000** |
| `UVXY` | 13/11/2026 | 17,35 | **-33.570,80** |
| `SQQQ` | 13/11/2026 | 40,93 | **-647,88** |
| `SPXU` | 13/11/2026 | 35,36 | **-33,47** |
| `VXX` | 13/11/2026 | 18,31 | **-1,87** |

Đối chiếu: cùng những chuỗi đó, **ARIMA** cho MAPE **10,6%** (`PARA`),
**4,27%** (`LCID`), **4,7%** (`ACH`). Vậy lỗi nằm ở **cách đặc trưng của
mô hình** (mức giá trên chuỗi nhiều thang giá), không nằm ở dữ liệu.

### Cách sửa đã làm (đo ngày 15/11/2026)

| Thay đổi | Tệp | Tác dụng |
|---|---|---|
| Bộ chặn giá dự báo bất khả thi | `app/core/data_integrity.py` | Chặn `predicted_close <= 0` và tỷ lệ lệch quá **100 lần** so với giá tham chiếu |
| Chặn ngay tại đường ghi | `app/database/repositories/prediction_repository.py` | `upsert()` ném `ValueError` — không dòng nào bất khả thi nào lọt vào sổ tay nữa |
| Bộ dò điểm gãy thang giá | `app/lakehouse/scale_repair.py` | Quét lịch sử mỗi mã: dò **nhảy cục bộ** (mốc 3 lần) và **độ rộng toàn cục** (mốc 100 lần). Đo ngày 15/11/2026 trên 1.002 mã: `PARA` độ rộng **3.503x**, `OCGN` **97,9x** — hai mã nhiễm; `NVDA` (30,6x) và `CELH` (31,8x) có **0** nhảy cục bộ nên là tăng trưởng thật, không bị gắn cờ |
| Lọc + đếm dòng bất khả thi | `accuracy_summary()`, `median_error_pct()` | Số liệu sạch + `excluded_impossible` để **không giấu** những gì đã loại |
| Báo cáo **WAPE** | `accuracy_summary()`, `_summarise()` | Sai số tuyệt đối chia cho tổng giá tham chiếu — không bị mã giá nhỏ hay mã giá lớn chi phối |
| Dọn dẹp sổ tay | `scripts/purge_impossible_predictions.py` | Đã xoá **76 dòng** (57 lệch thang giá + 19 giá âm) |
| Chốt bằng test | `tests/test_forecast_plausibility.py`, `tests/test_scale_repair.py`, `tests/test_accuracy_report.py` | Ba lớp: quy tắc, dò gãy, và bảo đảm trung bình báo cáo không bị dòng hỏng phá |

**Vì sao ngưỡng 100 lần, không chặt hơn:** `PARA` thật sự đã giao dịch
0,104 → 0,164 → 0,319 → 2,72 trong ba phiên thật tháng 11/2026 (một micro-cap
đang chờ chia ngược). Ngưỡng chặt hơn sẽ **báo oan** một biến động thật. Ngưỡng
100 lần vẫn chặn được đúng thứ cần chặn: mô hình hỏng thì lệch **hàng trăm
lần**, chứ không phải vài lần.

**Vì sao loại bỏ chứ không sửa giá:** không có "giá đúng" để khôi phục cho một
phiên đã qua. Giá thẳng thức là **không có dòng**, và báo cáo đếm một dự báo
ít hơn thay vì một dự báo vô lý. Bản thân dữ liệu giá trong Gold **không bị
sửa** — mọi giá vẫn truy vết được tới sàn.

### Cách đọc báo cáo sau khi sửa

| Cách đọc | Con số | Ý nghĩa |
|---|---|---|
| **Trung vị** (số chính) | **1,15%** | Sai số của một dự báo **điển hình** |
| **WAPE** | **2,75%** | Tổng sai số tuyệt đối so với tổng giá tham chiếu |
| Trung bình có dấu | 0,43% | Mô hình hơi **dự đoán cao** hơn thực tế |
| MAE | 333,16 | Chỉ có nghĩa **theo từng mã** (đơn vị giá khác nhau) |

> **Cách trả lời khi thầy hỏi "sai số bao nhiêu?":**
> *"Sai số tương đối trung vị của một dự báo đã kiểm chứng là **1,15%** trên
> 45.631 dòng, WAPE là **2,75%**. Con số trung bình cũ 263,85% em đã **truy
> nguyên tới gốc** và **không giấu**: nó không phải do mã giá nhỏ như em đoán
> ban đầu, mà do **một mã** — `PARA` — có lịch sử giá trải trên ba bậc độ vì
> bốn lần chia ngược chưa được chuẩn hoá, khiến mô hình hồi quy mức giá
> ngoại suy ra 242.751 cho một cổ giá 0,072. Em đã sửa bằng cách chặn ở đường
> ghi mọi dự báo có giá không tồn tại, xoá 76 dòng hỏng, bổ sung WAPE và
> công khai số dòng bị loại (`excluded_impossible`) để không ai phải tin
> theo lời."*

**Tỉ lệ đúng hướng theo nguồn dữ liệu** (đo ngày **17/11/2026**, sau khi lọc
dòng bất khả thi):

| Nguồn | Số dòng đã chấm | Sai số tương đối trung vị | WAPE | Đúng hướng |
|---|---|---|---|---|
| `auto_eod_batch` | 1.145 | 0,96% | 3,56% | **44,4%** |
| `manual_api` | 3 | 0,46% | 0,26% | 33,3% |
| `backfill_walk_forward` | 44.416 | 1,15% | 2,73% | **50,7%** |

> **Đọc bảng này thật chậm — đây là điểm đáng chú ý nhất.** Nhóm
> `auto_eod_batch` là nhóm **duy nhất** gồm những dự báo mà hệ thống **tự ghi
> trước khi phiên mở cửa**: 1.145 dòng, sai số tương đối trung vị **0,96%**
> (thấp hơn nhóm tái dựng) — nhưng tỉ lệ đúng hướng chỉ **44,4%**, thấp hơn
> hẳn 50,7% của nhóm tái dựng.
>
> Nghĩa là: những lần hệ thống thật sự "bắn trước" thì **độ lớn** dự báo tốt
> hơn, nhưng **hướng** lại kém hơn. Đây là bằng chứng thẳng thắn nhất mà đồ án
> có, và em báo nguyên vẹn thay vì chỉ trích phần đẹp.
>
> **Vì sao lại khác nhau?** Nhóm tái dựng được sinh bởi walk-forward trên
> tập hold-out của từng mô hình — mỗi dòng được dự báo khi mô hình **chưa
> từng thấy** phiên đó, và có thể được sinh ra từ nhiều mô hình khác nhau.
> Nhóm `auto_eod_batch` chỉ gồm dự báo **mô hình Linear Regression**, chạy
> trên đặc trưng của phiên gần nhất. Khác nhau về **mô hình** và về **khoảng
> thời gian neo**, không chỉ về quy trình.

**Cách đọc đúng bảng trên** — và đây là điểm phải nói thẳng trước hội đồng:

- Tỉ lệ đúng hướng **50,7%** trên 45.240 dòng tái dựng **gần như bằng ngẫu
  nhiên** (một đồng xu). Đây là kết quả **tiêu cực** và phải được báo cáo
  nguyên vẹn: mô hình Linear Regression dự báo **mức giá** một bước, và một
  mô hình dự báo mức giá có xu hướng bám theo mức giá gần nhất sẽ **thường xuyên
  đúng hướng một cách máy móc** — nhưng cũng thường xuyên **sai chiều** khi thị
  trường đảo chiều.
- Con số 25,0% trên 4 dòng `auto_eod_batch` **không mang ý nghĩa thống kê** —
  4 mẫu là quá ít để kết luận. Hệ thống báo cáo nó vì đó là dữ liệu thật, nhưng
  sẽ tự động đủ mẫu sau mỗi ngày giao dịch.

**Riêng AAPL** (đo ngày 13/11/2026, 62 dòng đã chấm):

| Chỉ số | Giá trị |
|---|---|
| Số dòng đã chấm | 62 |
| MAE | 3,58 |
| Sai số tương đối trung vị | 0,95% |
| Tỉ lệ đúng hướng | 39,3% |

> **Cách trả lời khi thầy hỏi "hệ thống dự báo có chính xác không?":**
> *"Đo được: trên 46.385 dòng đã chấm, sai số tương đối trung vị là 1,15%,
> nhưng tỉ lệ đúng hướng chỉ 50,6%, tức ngang với đồng xu. Em **không** tuyên
> báo hệ thống dự báo thị trường đúng hướng. Cái hệ thống chứng minh được là:
> nó dự báo trước, ghi xuống sổ, và tự chấm điểm bằng giá thật — một vòng lặp
> kiểm chứng mà phần lớn đồ án cũng chỉ dừng ở bước dự báo. Cải thiện tỉ lệ
> đúng hướng là hướng mở rộng em nêu ở Phần 6, không phải thứ em giấu."*

### Vì sao phải có số TRUNG VỊ bên cạnh số TRUNG BÌNH

`backend/app/database/repositories/prediction_repository.py`:

```python
        value = self.session.execute(
            select(Prediction.error_pct)
            .where(*filters)
            .order_by(func.abs(Prediction.error_pct).asc())
            .offset(total // 2)
            .limit(1)
        ).scalar()
```

Phép tính nằm trong SQL (sắp xếp theo trị tuyệt đối rồi lấy phần tử giữa), nên
không phải kéo 45.000 dòng vào Python. Kết quả trả về cùng đơn vị với
`error_pct` — **phân số**, không phải phần trăm — nên về sau không cần đổi đơn vị.

### Endpoint

`backend/app/api/v1/endpoints/forecasting.py`:

| Endpoint | Việc |
|---|---|
| `GET /api/v1/forecast/accuracy` | Toàn bộ dự báo đã kiểm chứng + số tổng hợp |
| `GET /api/v1/forecast/accuracy/{symbol}` | Dự báo đã kiểm chứng của một mã |
| `POST /api/v1/forecast/score` | Chấm điểm thủ công (batch tự làm mỗi đêm) |

### Giao diện

Bảng kiểm chứng được **nhúng trong trang Dữ liệu thị trường**
(`frontend/src/pages/MarketData.tsx`), ngay dưới biểu đồ nến — đúng chỗ người
dùng đang xem giá của mã đó, để so sánh dự báo với giá thật ngay tại chỗ.

| Thành phần | Việc |
|---|---|
| `frontend/src/components/dashboard/ForecastVerification.tsx` | Bảng điều khiển kiểm chứng + bảng chi tiết |
| `frontend/src/components/charts/VerifiedForecastChart.tsx` | Biểu đồ 2 tầng: giá dự báo vs giá thật, và thanh sai số |

### Lịch tự động

`backend/crontab` có thêm một dòng cho toàn bộ mã:

```cron
30 4 * * 1-5 root cd $APP_HOME && /opt/venv/bin/python scripts/run_scheduled_job.py universe-forecast >> $APP_HOME/logs/cron.log 2>&1
```

Lịch này chạy **sau** cả hai lần batch EOD (21:30 UTC và 03:30 UTC), nên dữ liệu
đã được nạp xong rồi mới dự báo và chấm điểm.

### Kiểm thử

| File | Nội dung | Kết quả |
|---|---|---|
| `backend/tests/test_light_path_matches_full_path.py` | Đường nhẹ cho ra kết quả y hệt đường đầy đủ | 12/12 pass (13/11/2026) |
| `backend/tests/test_forecast_scoring.py` | Chấm điểm không bịa số, tính đúng hướng, điểm không bị xoá khi ghi lại | 6/6 pass (13/11/2026) |
| `backend/tests/test_accuracy_report.py` | Trung vị không bị kéo lệch; số "đã công bố" phải khớp với bảng | 3/3 pass (13/11/2026) |
| `backend/tests/test_no_fake_data.py` | Đường ghi từ chối mã fixture; bảng không chứa mã không có dữ liệu thật | 4/4 pass (15/11/2026) |

### Hai lỗi trong báo cáo độ chính xác — đã tìm và đã sửa

Cả hai lỗi đều làm **báo cáo trông đẹp hơn thực tế**, và cả hai đều không thể
phát hiện ra bằng mắt khi nhìn giao diện. Đây là loại lỗi nguy hiểm nhất của
một đồ án, nên được ghi lại đầy đủ.

**Lỗi 1 — báo cáo trung bình sai số tương đối mà không có trung vị**

*Triệu chứng:* bảng tổng hợp hiện sai số tương đối trung bình là **264,95%**.

*Vì sao xảy ra:* báo cáo gộp 755 mã có đơn vị giá khác nhau vào cùng một phép
trung bình. Ba mã niêm yết dưới 5 USD làm sai số tương đối của chúng phình to
một cổ 0,07 USD dịch 0,05 USD là 70%.

*Fix:* thêm `PredictionRepository.median_error_pct()` — trung vị của **trị tuyệt
đối**, tính trong SQL. Giao diện dùng trung vị làm số chính, vẫn hiển thị
trung bình bên cạnh.

*Bằng chứng:* trên 44.491 dòng đã kiểm chứng (đo ngày 13/11/2026) — trung bình
264,95% → trung vị **1,16%**; phân vị 90 là 3,90%, phân vị 99 là 11,06%, và chỉ
**73 dòng trên 3 mã** vượt 100%.

**Lỗi 2 — số "dự báo đã công bố" luôn bằng 0**

*Triệu chứng:* trường `published_summary` của API trả về `verified: 0`, trong
khi bảng `predictions` có những dòng nguồn `auto_eod_batch` đã được chấm.

*Vì sao xảy ra:* `published_summary` được tính bằng cách **lọc** ra chuỗi
`series` — mà chuỗi đó chỉ lấy `limit` dòng gần nhất. Những dòng đã công bố có
ngày cũ hơn bị các dòng tái dựng đẩy ra khỏi khung, nên phần lọc rỗng.

*Fix:* thêm `PredictionRepository.published_scored_series()` — truy vấn riêng
những dòng đã công bố, độc lập với giới hạn của chuỗi hiển thị.

*Bằng chứng:* trước `verified: 0` → sau `verified: 5` (đo ngày 13/11/2026,
5 dòng nguồn `auto_eod_batch` đã chấm, kỳ 2026-11-10 → 2026-11-13).

Hai lỗi này được ghim lại bằng `backend/tests/test_accuracy_report.py`, để lần
saua code không vô tình làm báo cáo "đẹp" trở lại.

### Lỗi 3 — sổ tay kiểm chứng chứa 200 dòng dự báo bịa (đo ngày 15/11/2026)

*Triệu chứng:* bảng `predictions` chứa **200 dòng** cho các mã `TST0` .. `TST199`.
Mọi dòng đều có **cùng một cặp số bịa**: `reference_close = 100.0`,
`predicted_close = 101.0`, `predicted_return = 0.01`. Tất cả đều mang nhãn
`source = "auto_eod_batch"` — nhãn của dự báo **đã công bố trước khi phiên mở
cửa**. Nghĩa là chúng nằm chung hàng với bằng chứng mạnh nhất mà hệ thống có.

*Vì sao xảy ra:* các dòng này **không đi qua đường ghi của hệ thống**. Kiểm tra
từng tầng:

| Nơi kiểm tra | Kết quả |
|---|---|
| Bronze / Silver / Gold | **không có** mã nào tên `TST0` (1.002 mã thật, 0 mã giả) |
| `backend/data/models/` | **không có** thư mục model `TST*` |
| Mã nguồn trong `backend/` | **không có** chỗ nào sinh ra tên `TST*` |
| Bảng `predictions` | 200 dòng, tất cả tạo trong **1 giây** (08:20:32 → 08:20:33 ngày 14/11/2026) |

Vậy nên chúng được **ghi thẳng vào MySQL**, không đi qua `PredictionRepository`.
Đường ghi đó không có nghị quyết nào kiểm tra "mã này có thật không", nên dòng giả
đi vào bảng và **không còn phân biệt được** với dự báo thật. Số "đã kiểm chứng"
mà bảng điều khiển hiển thị đã chứa cả 200 dòng đó.

*Fix (ba lớp):*

1. **Chặn ở đường ghi.** `backend/app/core/data_integrity.py` định nghĩa một
   mã là "mã thật" khi tên của nó **không bắt đầu** bằng một trong các dấu hiệu
   fixture quen thuộc (`TST`, `TEST`, `DEMO`, `MOCK`, `FAKE`, `DUMMY`, `SAMPLE`,
   `PLACEHOLDER`, `XXX`). `PredictionRepository.upsert()` — **đường ghi duy nhất**
   vào bảng `predictions` — ném `ValueError` khi gặp mã như vậy, trước khi
   chạm vào cơ sở dữ liệu:

```python
        symbol = str(payload["symbol"]).upper()
        if is_fabricated_symbol(symbol):
            raise ValueError(describe_fabricated_symbol(symbol))
```

2. **Quét và xoá.** `backend/scripts/purge_fake_predictions.py` tìm mọi dòng mà
   mã **không tồn tại trong tầng Gold** — đây là phép kiểm tra **mạnh** hơn, bắt
   được cả dòng giả mang tên một mã có vẻ thật. Script mặc định là **dry run**,
   cần `--apply` mới ghi.

3. **Ghim bằng test.** `backend/tests/test_no_fake_data.py` kiểm chứng cả ba:
   đường ghi từ chối mã fixture, mã thật không bị nhầm là fixture, và bảng hiện
   tại **không chứa mã nào không có dữ liệu thật** trong Gold.

*Bằng chứng (đo ngày 15/11/2026):*

| Chỉ số | Trước | Sau |
|---|---|---|
| Tổng dòng trong bảng `predictions` | 46.609 | **46.409** |
| Dòng của mã fixture (`TST*`) | **200** | **0** |
| Số mã khác nhau trong bảng | 1.173 | **973** |
| Mã trong bảng nhưng **không có** trong Gold | 200 | **0** |
| Cụm giá trị trùng lặp bất thường (≥20 dòng) | 1 | **0** |

> **Đo lại ngày 17/11/2026** (sau khi thêm 174 dự báo đa mô hình và chấm
> thêm 695 dòng): bảng hiện có **46.505** dòng, trong đó **46.385** dòng đã
> có `actual_close`. Số mã vẫn **973** — không mã nào mới bị thêm vào mà
> thiếu dữ liệu thật trong Gold.

Sau khi xoá, báo cáo độ chính xác trả về:

| Nhóm | Số dòng đã chấm | Sai số tương đối trung vị | Đúng hướng |
|---|---|---|---|
| Toàn bảng | 46.385 | **1,15%** | 50,6% |
| **Đã công bố** (không phải tái dựng) | 1.215 | **0,96%** | 45,4% |

**Vì sao xoá chứ không sửa:** một dòng dự báo là **kết quả của một mô hình**. Với
mã không có lịch sử thì mô hình không chạy được, nên **không có giá trị đúng để
khôi phục**. Trạng thái trung thực là dòng **vắng mặt**, không phải một dòng
điền số giả để lấp chỗ trống.

**Nguyên tắc đằng sau:** một dự báo chỉ có ý nghĩa khi nó nói về một công cụ
**có thật** — nó được suy ra từ lịch sử của công cụ đó và được kiểm chứng bằng
giá đóng cửa thật của công cụ đó. Mã không có trong lakehouse thì không có cả
hai. Vì vậy phép kiểm tra mạnh nhất **không phải** "tên có giống mẫu thử không",
mà là **"mã này có dữ liệu trong Gold không"**.

---

# PHẦN 5C — TỐI ƯU TỐC ĐỘ (ĐO NGÀY 14/11/2026)

## 5C.1. Hiểu đơn giản: vì sao web chậm và cách sửa

Bạn mở trang web và chọn một mã cổ phiếu. Trang hiện ra sau khoảng một
giây. Bạn tưởng đó là do máy yếu.

Không phải. Nguyên nhân thật là **hệ thống tải về nhiều hơn thứ bạn cần**.

Hãy hình dung một mã cổ phiếu 10 năm như một **cuốn sổ ghi 1.200 ngày giao
dịch**. Hệ thống không lưu cuốn sổ thành một khối, mà **cắt nhỏ ra thành 121
tập giấy, mỗi tập một tháng**. Khi bạn mở trang "3 tháng gần nhất", hệ thống
vẫn **tải cả 121 tập** về rồi mới lấy ra 3 tập cuối. 118 tập bị tải về rồi
quẳng đi.

Tương tự: mỗi lần có một ngày giao dịch mới, hệ thống dựng lại toàn bộ
chỉ báo của mã đó và **ghi lại cả 121 tập giấy**, dù 120 tập nội dung y
nguyên không đổi.

Ba thay đổi dưới đây sửa đúng ba chỗ đó:

1. **Chỉ tải phần cần xem** — xem 3 tháng thì chỉ tải 3 tập.
2. **Chỉ ghi lại phần thay đổi** — có ngày mới ở cuối thì chỉ ghi lại tập
   tháng đó.
3. **Giữ bộ nhớ đệm ấm xuyên suốt** — bước chấm điểm không phải tải lại
   toàn bộ lịch sử lần nữa.

Nguyên tắc bất di bất dịch của phần này: **đường nhanh và đường chậm phải ra
cùng một dữ liệu**. Không có một con số nào được bịa ra để trang nhanh hơn.

**Lượt tối ưu thứ hai (đo ngày 14/11/2026)** bổ sung bốn ý nữa, cùng một
nguyên tắc:

4. **Thanh giá chỉ cần tệp mới nhất** — không phải 121 tập. Mười mã trên
   thanh đầu trang: 11,7 s → 0,43 s.
5. **Thống kê và so sánh yêu cầu cửa sổ từ máy chủ** — không tải cả lịch
   sử rồi mới cắt.
6. **Trình duyệt không tải cả trang** — gói JavaScript 871 KB → 169 KB cho
   Dashboard.
7. **Sửa lỗi cửa sổ nuốt phiên cuối** — chi tiết ở mục 5C.3.7.
8. **Các lần đọc độc lập chạy song song** — so sánh 531 ms → 287 ms;
   đếm bản ghi ba tầng 181 ms → 164 ms. Chi tiết ở mục 5C.3.6b–5C.3.6c.

## 5C.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Cắt bảng theo thời gian** | **Windowed read** | Chỉ đọc các tệp chứa được khoảng ngày người dùng hỏi | `app/lakehouse/parquet_manager.py` |
| **Ghi thêm theo phần đổi** | **Incremental write** | Chỉ ghi lại các tệp có thể đã thay đổi, bỏ qua các tệp cũ | `app/lakehouse/parquet_manager.py` |
| **Nhìn về quá khứ** | **Causal feature** | Chỉ báo chỉ dùng dữ liệu trước đó, không dùng dữ liệu tương lai | `app/features/advanced_features.py` |
| **Bộ nhớ đệm giữ nguyên** | **Frame cache** | Giữ bảng dữ liệu trong RAM để không tải lại | `app/lakehouse/frame_cache.py` |
| **Tệp phân vùng** | **Partition** | Cách chia dữ liệu thành nhiều tệp nhỏ theo tháng | `app/lakehouse/parquet_manager.py` |
| **Số phiên giao dịch** | **Session** | Một ngày giao dịch của một sàn | `app/lakehouse/session.py` |
| **Tệp mới nhất** | **Newest partition** | Tệp chứa các phiên gần nhất — đủ cho một thanh giá | `app/lakehouse/storage_base.py` |
| **Chia gói theo nhu cầu** | **Code splitting** | Tách gói JavaScript lớn thành từng phần tải khi cần | `frontend/vite.config.ts` |
| **Chạy song song** | **Concurrent I/O** | Các lần đọc độc lập cùng lúc, thay vì xếp hàng | `app/api/v1/endpoints/stocks.py` |

## 5C.3. Chi tiết kỹ thuật

### 5C.3.1. Đọc theo cửa sổ thời gian

`app/lakehouse/parquet_manager.py` — `filter_keys_by_window()` giữ lại đúng
những tệp có thể chứa dòng trong khoảng ngày yêu cầu. Một tệp không có
dạng `year=/month=` thì **luôn được giữ lại**: không xác định được vị trí thì
phải đọc, không được bỏ qua (bỏ qua sẽ âm thầm mất dữ liệu thật).

`app/lakehouse/minio_storage.py` — `read_prefix_window()` liệt kê khóa tệp
một lần (một lệnh metadata rẻ) rồi chỉ tải những tệp đã lọc.

`app/services/market_service.py` — `get_history()` truyền `start`/`end` xuống
tầng lưu trữ, nên `GET /stocks/AAPL?start=...` chỉ đọc phần cần xem.

**Đo ngày 14/11/2026, AAPL, MinIO cùng máy, backend đang chạy:**

| Yêu cầu | Trước | Sau | Dung lượng |
|---|---|---|---|
| `/api/v1/stocks/AAPL` (toàn bộ) | 1 189 ms | 1 189 ms | 569 KB |
| `/api/v1/stocks/AAPL?start=2025-11-14` (1 năm) | (không có) | **202 ms** | **56 KB** |
| `/api/v1/stocks/AAPL?start=2026-05-14` (6 tháng) | (không có) | **33 ms** | **29 KB** |
| `/api/v1/dashboard/AAPL` (toàn bộ) | 8 085 ms | 8 085 ms | 561 KB |
| `/api/v1/dashboard/AAPL?start=2026-08-14` (3 tháng) | (không có) | **173 ms** | **16 KB** |
| `/api/v1/dashboard/AAPL?start=2026-10-14` (1 tháng) | (không có) | **88 ms** | **6 KB** |

> **Cách trả lời khi thầy hỏi "cửa sổ thời gian có làm mất dữ liệu không?"**
> *"Không. Đường nhanh và đường chậm trả về cùng một tập dòng trong khoảng
> đó — điều này được ghim bằng `backend/tests/test_lakehouse_read_write_performance.py`,
> hàm `test_a_windowed_read_returns_the_same_rows_as_a_full_read`. Ngoài ra một
> tệp không xác định được tháng thì luôn được đọc, không bao giờ bị bỏ qua."*

### 5C.3.2. Ghi thêm theo phần đã đổi

`app/lakehouse/parquet_manager.py` — `partitions_from()` giữ lại các tệp từ
tháng của phiên đã thay đổi trở đi.

Cơ sở để làm được: **mọi chỉ báo trong Silver và Gold đều nhìn về quá khứ**.
Trung bình động, trung bình lũy thừa và việc gộp các dấu giao trong ngày
đều chỉ dùng dữ liệu đứng trước. Nên khi có một ngày mới ở **cuối** lịch
sử, mọi phiên **trước đó** sinh ra đúng y như cũ — ghi lại chúng là lãng phí
thuần túy.

`app/services/auto_refresh.py` — `_changed_since_from_result()` lấy mốc
từ **đầu cửa sổ tải dữ liệu** của lượt làm mới. Mốc đó bao hàm cả trường hợp
**nhà cung cấp sửa lại một phiên cũ** (restatement), vì phiên bị sửa nằm
trong cửa sổ tải. Một ngày đệm cho sai lệch múi giờ.

**Đo ngày 14/11/2026, AAPL, ghi tầng Gold (122 tệp phân vùng):**

| Cách ghi | Số tệp ghi | Thời gian |
|---|---|---|
| Ghi toàn bộ | 122 | **4,555 s** |
| Ghi thêm (từ 01/10/2026) | 2 | **0,311 s** |

**Kiểm chứng tính đúng đắn (đo ngày 14/11/2026):** tính lại toàn bộ 122 tệp
Gold từ dữ liệu Silver thật của AAPL rồi so từng tệp với nội dung đang lưu
trên MinIO — **0 sai lệch** trên các cột `timestamp`, `close`, `ema_12`,
`rsi_14`, `sma_20`, `macd`. Tức là ghi thêm cho ra **đúng** kết quả của ghi
toàn bộ.

### 5C.3.3. Giữ bộ nhớ đệm ấm xuyên suốt lượt chạy

`app/services/universe_forecast.py` — trước đây bộ nhớ đệm được **thu nhỏ
lại về mặc định** trước khi bước chấm điểm chạy, nên bước chấm điểm phải
tải lại toàn bộ lịch sử của mọi mã. Nay bước chấm điểm chạy **trước**, và
bộ nhớ đệm được thu nhỏ lại **sau**.

### 5C.3.4. Lỗi đã sửa: mọi yêu cầu có khoảng thời gian đều trả về 500

**Triệu chứng:** `GET /api/v1/stocks/AAPL?start=2025-11-14T00:00:00.000Z`
trả về lỗi 500 với thông báo
`ValueError: Cannot pass a datetime or Timestamp with tzinfo with the tz parameter`.

**Vì sao xảy ra:** trình duyệt gửi chuỗi ISO **có múi giờ** (`...Z`), và code
cũ gọi `pd.Timestamp(value, tz="UTC")` — pandas từ chối giá trị đã có múi
giờ. Đường có `start`/`end` chưa từng được dùng nên lỗi nằm im cho tới
khi tối ưu cửa sổ thời gian bật nó lên.

**Fix:** thêm `as_utc_timestamp()` trong `app/lakehouse/session.py` — giá trị
naive được hiểu là UTC, giá trị có múi giờ được **chuyển đổi** sang UTC.
Dùng chung cho `market_service.py`, `backtesting/engine.py` và
`backtesting/walk_forward.py` (hai file backtesting có cùng lỗi tiềm ẩn).

**Bằng chứng:** trước `500` → sau `200` với payload 56 KB (đo ngày
14/11/2026, `start=2025-11-14T00:00:00.000Z`).

### 5C.3.5. Đọc chỉ tệp mới nhất thay vì toàn bộ lịch sử (đo ngày 14/11/2026)

**Triệu chứng:** thanh giá ở đầu trang (market tape) mất **11,7 giây** lần
đầu và ~1,0 giây những lần sau. Lý do rất đơn giản: mỗi mã trong thanh giá
chỉ cần **thanh giá mới nhất**, nhưng đường đọc cũ lại tải **toàn bộ lịch
sử** của mã đó — ~121 tệp Parquet — rồi lấy dòng cuối cùng.

**Vì sao xảy ra:** `MarketService.get_latest()` gọi `get_history()`, và
`get_history()` đọc toàn bộ lịch sử. Endpoint `/stocks/{symbol}/latest` và
`/stocks/tape` đều đi qua đó.

**Fix:** thêm `read_newest_partition()` vào `StorageBackend` — liệt kê khóa tệp
một lần (một lệnh metadata rẻ), rồi chỉ tải **hai tệp mới nhất**. Hai tệp
chứ không phải một, vì **tỷ lệ thay đổi cần giá đóng cửa phiên trước**, và
trong ngày giao dịch đầu tiên của một tháng thì tệp mới nhất chỉ chứa đúng
một phiên.

Ba tầng Bronze/Silver/Gold đều có `read_newest()`, và
`/stocks/tape` lấy **10 mã song song** thay vì tuần tự (10 lần round-trip
MinIO là 10 lần chờ; chạy song song thì chỉ còn lần chậm nhất).

**Bằng chứng (đo ngày 14/11/2026, MinIO cùng máy):**

| Yêu cầu | Trước | Sau | Nhanh hơn |
|---|---|---|---|
| `/api/v1/stocks/tape` (10 mã, lần đầu) | 11 770 ms | 1 026 ms | **11,5x** |
| `/api/v1/stocks/tape` (10 mã, lần sau) | 1 034 ms | **427 ms** | **2,4x** |
| `/api/v1/stocks/AAPL/latest` | ~1 200 ms | **88 ms** | **13,6x** |

**Kiểm chứng tính đúng đắn (đo ngày 14/11/2026):** script
`backend/scripts/verify_latest_fast_path.py` so **1002 mã** trong tầng Gold —
đường nhanh (đọc tệp mới nhất) với đường chậm (đọc toàn bộ lịch sử) — trên
các trường `close`, `open`, `high`, `low`, `volume`, `change_pct` và
`timestamp`. Kết quả: **0 sai lệch**.

### 5C.3.6. Yêu cầu cửa sổ cho thống kê và so sánh (đo ngày 14/11/2026)

**Triệu chứng:** `/stocks/stats/{symbol}` và `/stocks/compare` cũng tải toàn
bộ lịch sử, rồi mới cắt cửa sổ ở phía máy chủ.

**Fix:** hai endpoint này giờ **yêu cầu cửa sổ từ máy chủ**:

- `/stocks/stats/{symbol}` đọc thanh giá mới nhất trước (rẻ), rồi yêu cầu
  đúng khoảng `days` ngày.
- `/stocks/compare` chia làm hai bước: bước một đọc thanh giá mới nhất của
  mỗi mã để tìm **mốc** (ngày mới nhất trong nhóm), bước hai mới yêu cầu
  khoảng đến mốc đó. Nhờ vậy mọi đường được cắt ở **cùng một thời điểm**,
  đúng như ý nghĩa của phép so sánh.

**Bằng chứng (đo ngày 14/11/2026):**

| Yêu cầu | Sau tối ưu |
|---|---|
| `/api/v1/stocks/stats/AAPL?days=252` | **168 ms** (527 B) |
| `/api/v1/stocks/compare?symbols=AAPL,MSFT,NVDA&days=252` | **531 ms** (51 KB) |

### 5C.3.6b. Song song hoá phép so sánh (đo ngày 14/11/2026)

**Triệu chứng:** `/stocks/compare` còn 531 ms dù đã có cửa sổ phía máy chủ.

**Vì sao xảy ra:** hai bước của phép so sánh chạy **tuần tự**. Bước một đọc
thanh giá mới nhất của từng mã — ba lần chờ MinIO nối tiếp nhau. Bước hai
đọc cửa sổ của từng mã — lại ba lần chờ nối tiếp nhau. Mỗi mã là một lần
chờ độc lập, nên tổng thời gian là **tổng** số lần chờ.

**Fix:** cả hai bước chạy song song (`ThreadPoolExecutor`, tối đa 6 luồng).
Các lần đọc độc lập với nhau và không ghi gì, nên chạy cùng lúc là an toàn.
Thứ tự mã trong kết quả **không đổi** vì mỗi mã được ghi vào đúng chỗ của nó.

**Bằng chứng (đo ngày 14/11/2026):** `/stocks/compare?symbols=AAPL,MSFT,NVDA&days=252`
**531 ms → 287–298 ms**. Số điểm và giá trị `rebased` không đổi.

### 5C.3.6c. Đếm số bản ghi của ba tầng chạy song song (đo ngày 14/11/2026)

**Triệu chứng:** trang Dashboard mất **30 giây** ở lần tải đầu tiên sau khi
khởi động lại backend, rồi rút xuống 143 ms ở những lần sau.

**Vì sao xảy ra:** hai việc độc lập nhau xảy ra cùng lúc:

1. Bộ nhớ đệm của tiến trình backend vừa được khởi động lại nên **chưa có
   gì trong RAM**. Lần đầu phải tải tệp Parquet từ MinIO.
2. Ngay lúc đó, **lượt tự làm mới nền** đang chạy trên 976 mã và ghi tệp
   liên tục vào MinIO. MinIO bận nên mỗi lần chờ của một yêu cầu bị kéo
   dài, và urllib3 phải thử lại sau khi kết nối bị đặt lại.

Lần tải đầu tiên vì vậy phải chờ MinIO lúc nó đang bận nhất. Đây **không
phải** dữ liệu giả hay lỗi logic — đó là điều kiện vận hành thật, và nó là
lý do con số 30 giây được ghi lại thay vì bị làm đẹp.

**Fix:** phần đếm số bản ghi của ba tầng (Bronze/Silver/Gold) chạy song song
thay vì tuần tự. Mỗi lần đếm là một lệnh liệt kê metadata — không tải
tệp Parquet nào — nhưng MinIO cần 25–82 ms cho mỗi lệnh.

**Bằng chứng (đo ngày 14/11/2026):**

| Cách đếm | Thời gian |
|---|---|
| Tuần tự (trước) | 82 ms + 27 ms + 72 ms = **181 ms** |
| Song song (sau) | **164 ms** (giới hạn bởi tầng chậm nhất) |

Ba con số đếm được là **y hệt**, vì cùng một danh sách khóa được liệt kê và
cùng một đối tượng được đếm.

**Còn lại:** phần đọc lịch sử vẫn bị chậm khi MinIO đang bận. Cơ chế
`request_gate` đã có sẵn để tạm dừng công việc nền khi người dùng đang
chờ, nhưng nó chỉ dừng ở **ranh giới mã** — một lượt rebuild đã bắt đầu
thì vẫn chạy trọn. Xem mục 5C.3.9.

### 5C.3.7. Lỗi đã sửa: cửa sổ thời gian nuốt mất phiên cuối cùng

**Triệu chứng:** bộ thống kê của NVDA báo `last_close = 166,19`, trong khi
giá đóng cửa thật đang lưu là `162,85`. Cửa sổ 252 ngày kết thúc **một phiên
sớm hơn** so với đường cũ, và `sessions` là 180 thay vì 181.

**Vì sao xảy ra:** mốc `until` là một **ngày** (`date`), còn mốc thời gian
của một phiên là **giờ mở cửa sàn** tính ra UTC — 14:30 cho NYSE, 02:00 cho
HOSE. So sánh thẳng `timestamp <= midnight(của ngày đó)` nên **vứt mất chính
phiên mà cửa sổ định kết thúc**.

Lỗi này **không nhìn thấy được trên giao diện**: biểu đồ nến thiếu một
nến cuối trông y như ngày nghỉ. Nó chỉ lộ ra khi đem so số với đường chậm —
tức là đúng lúc ta kiểm chứng.

**Fix:** `slice_window()` trong `app/lakehouse/session.py` biến `until` thành
**thời điểm cuối cùng của ngày đó** thay vì đầu ngày.

**Bằng chứng:** script `backend/scripts/verify_windowed_stats.py` so số liệu
thống kê của 5 mã (AAPL, MSFT, NVDA, FPT, VCB) theo **cả hai** cách trên
mọi trường (`sessions`, `first_close`, `last_close`, `high`, `low`,
`mean_close`, `total_return_pct`, `volatility_pct`, `max_drawdown_pct`,
`up_days`, `down_days`, `avg_volume`, `total_volume`).

- Trước khi sửa: **44 sai lệch** trên 5 mã.
- Sau khi sửa: **0 sai lệch**.

Lỗi này được ghim lại bằng ba hàm kiểm thử trong
`backend/tests/test_lakehouse_read_write_performance.py`:
`test_a_window_keeps_the_last_session_of_its_final_day`,
`test_a_window_keeps_every_session_of_its_final_day` và
`test_a_window_still_excludes_the_days_after_it`.

### 5C.3.8. Chia nhỏ gói JavaScript của trình duyệt (đo ngày 14/11/2026)

**Triệu chứng:** trình duyệt phải tải **871 KB** JavaScript (253 KB nén) trước
khi trang đầu tiên hiện ra — kể cả với người chỉ xem Dashboard.

**Vì sao xảy ra:** mọi trang nằm trong một gói, và các thư viện dùng chung —
đặc biệt `recharts` (407 KB thô, 110 KB nén) — nằm trong gói chính.

**Fix:** ba lớp:

1. **Tách trang theo nhu cầu** (`React.lazy` + `Suspense`) trong
   `frontend/src/App.tsx`: MarketData, TechnicalAnalysis, Forecasting,
   Backtesting, AIAgent, SystemStatus.
2. **Tách thư viện theo nhóm** (`manualChunks` trong `frontend/vite.config.ts`):
   `react`, `charts`, `query`. Trình duyệt tải và **cache từng thư viện một
   lần**, và sửa một trang không làm mất cache thư viện.
3. **Tách biểu đồ của Dashboard** ra `frontend/src/components/charts/DashboardCharts.tsx`
   và nạp bằng `React.lazy`. Khung trang (thanh điều hướng, tiêu đề, dải số
   liệu) **hiện ra trước**, biểu đồ điền vào sau với khung xương. Biểu đồ nến
   vẽ bằng SVG thuần nên **không tốn thư viện nào** và hiện ra ngay.

**Bằng chứng (đo ngày 14/11/2026, `vite build`):**

| Gói | Kích thước thô | Nén |
|---|---|---|
| `index` (gói chính, trước) | 871 KB | 253 KB |
| `index` (gói chính, sau) | 169 KB | 55 KB |
| `react` | 156 KB | 51 KB |
| `charts` (recharts) | 407 KB | 110 KB |
| `query` | 49 KB | 15 KB |
| `DashboardCharts` | 2 KB | 1 KB |

Tổng gói **phải tải để hiện Dashboard** giảm từ 871 KB xuống **169 KB +
tệp trang riêng** — giảm ~81% phần tải ở lần đầu.

### 5C.3.9. Giới hạn đã biết — điều chưa làm

Còn một nút thắt lớn chưa xử lý: **số lượng tệp phân vùng**. Một mã 10 năm
vẫn bị chia thành ~121 tệp/tháng, và mỗi tệp chỉ chứa khoảng 21 dòng —
chi phí mở và phân tích một tệp Parquet cỡ đó lớn hơn nhiều so với dữ liệu
chứa trong nó.

Hướng khắc phục là **gộp tệp theo năm** (`symbol=X/year=Y/part-001.parquet`),
giảm ~121 tệp xuống ~10 tệp cho mỗi mã. Việc này **chưa làm** vì nó đòi
hỏi di dời hơn 315.000 tệp đang tồn tại, và đọc lẫn hai kiểu bố cục cùng lúc
sẽ sinh ra dữ liệu trùng. Đây là bước nâng cấp lớn, cần script di dời riêng
có kiểm chứng trước–sau.

> **Cách trả lời khi thầy hỏi "còn tối ưu được nữa không?"**
> *"Có. Hiện tại mỗi mã 10 năm vẫn nằm trong ~121 tệp Parquet, và phần lớn
> thời gian đọc là do mở 121 tệp nhỏ chứ không phải do tải dữ liệu. Gộp theo
> năm sẽ giảm số tệp xuống ~10, nhưng cần di dời dữ liệu đang có và phải có
> bước kiểm chứng trước–sau để không sinh dữ liệu trùng. Tôi ghi nhận đây là
> hướng mở rộng, chưa coi là đã làm."*

### 5C.3.10. Vì sao trang chậm lúc MinIO đang bận (đo ngày 14/11/2026)

**Triệu chứng:** sau khi khởi động lại backend, lần tải Dashboard đầu tiên
mất **30 giây**; những lần sau mất 143–217 ms.

**Vì sao xảy ra:** đây là điều kiện vận hành thật, không phải lỗi logic:

1. Lượt tự làm mới nền chạy trên **976 mã** và ghi tệp vào MinIO liên tục.
2. MinIO là một tiến trình duy nhất trên đĩa cục bộ. Khi nó đang nhận
   ~90 lần ghi tệp mỗi phút, mỗi lần chờ của một yêu cầu đọc bị kéo dài.
3. `urllib3` thử lại sau khi MinIO đặt lại kết nối, và mỗi lần thử lại lại
   tốn thêm một lần chờ.

Đo được trong cùng lúc: một lần đọc tệp mới nhất của một mã mất **119 ms**
khi hệ thống rảnh và **716 ms** khi lượt làm mới nền đang chạy.

**Phần nào đã xử lý:** cơ chế `request_gate` (`app/core/request_gate.py`)
đếm số yêu cầu đang chờ và **tạm dừng công việc nền** trong lúc có người
dùng. Đo được: đọc AAPL từ 0,4 s lên 89,9 s khi có rebuild chạy song song;
sau khi có cổng chặn, đọc AAPL ổn định ở 0,4 s.

**Phần nào chưa xử lý:** cổng chặn chỉ dừng công việc nền ở **ranh giới mã**.
Một lượt rebuild đã bắt đầu thì vẫn chạy trọn (~2,7 s ghi tệp cho một mã).
Nếu một yêu cầu đến giữa lượt rebuild đó, nó vẫn phải chờ.

**Hướng khắc phục (chưa làm):** cho phép `request_gate` báo hiệu **dừng giữa
chừng**, để lượt rebuild kiểm tra cổng chặn trước **mỗi tệp** thay vì trước
mỗi mã. Đây là thay đổi nhỏ về mã nguồn, nhưng cần đo lại toàn bộ thông
lượng của lượt làm mới nền để chắc chắn nó không chậm lại.

---

# PHẦN 6 — HỆ THỐNG DỰ BÁO

> Sơ đồ: [3. Quy trình train & dự báo](./SO_DO_MINH_HOA.md#3) · [7. LSTM dự đoán tỷ lệ](./SO_DO_MINH_HOA.md#7) · [8. So sánh 3 mô hình](./SO_DO_MINH_HOA.md#8)

## 6.1. Hiểu đơn giản

Bạn muốn biết "ngày mai giá AAPL đóng cửa bao nhiêu?". Hệ thống có **3 cách trả lời**, và cố tình dùng cả 3:

| Cách | Trực giác dễ hiểu | Vai trò |
|---|---|---|
| **Linear Regression** | Vẽ đường thẳng đi qua các chỉ báo (RSI, đường trung bình) để đoán giá mai | **Mốc so sánh công bằng** — mọi mô hình phức tạp phải thắng được nó |
| **ARIMA** | "Giá mai có xu hướng giống 5 phiên trước cộng thêm phần tăng trưởng dài hạn thì sao?" | Đối chứng thống kê kinh điển, không cần feature thủ công |
| **LSTM** | Mạng nơ-ron đọc 60 phiên liên tiếp như đọc một đoạn văn, tìm mẫu hình lặp lại | Đóng góp kỹ thuật nổi bật nhất của đồ án |

**Vì sao cần cả 3, không chỉ 1?** Vì nếu bạn chỉ báo cáo mô hình tốt nhất, đó là **cherry-picking** — dấu hiệu của một đồ án không nghiêm túc. Hệ thống hiển thị **cả ba trên cùng một tập dữ liệu kiểm tra**, và để người đọc tự kết luận.

**Còn một việc nữa mà 3 mô hình trên không làm được: chứng minh rằng hệ
thống đang chạy thực sự dự báo đúng.** Trang Dự báo đo mô hình trên tập hold-out
lịch sử — đó là **backtest**, trả lời câu hỏi "mô hình này giỏi cỡ nào trên
những phiên đã xảy ra". Còn câu hỏi đồ án cần trả lời là "những dự báo hệ
thống **đã công bố** thực sự có đúng không?".

Câu trả lời nằm ở Phần 5B.6: hệ thống **ghi dự báo xuống sổ trước khi phiên mở
cửa**, rồi **chấm điểm bằng giá đóng cửa thật** sau khi phiên đóng cửa. Số đo
được (đo ngày 17/11/2026, 46.385 dòng đã chấm): sai số tương đối trung vị
**1,15%**, nhưng tỉ lệ đúng hướng **50,6%** — tức **ngang với ngẫu nhiên**.

> **Cách trả lời khi thầy hỏi "vậy mô hình có ích không?":**
> *"Về **mức giá**, sai số trung vị 1,15% — thấp hơn nhiều so với biến động
> giá hằng ngày, nên dự báo mức giá có dùng. Về **chiều đi**, 50,6% là ngang
> đồng xu, nên em **không** tuyên bố hệ thống đoán được thị trường lên hay
> xuống. Em báo cáo cả hai số vì chỉ báo cáo một số là bóp méo."*

## 6.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Hold-out set** | Phần dữ liệu cuối cùng giấu lại, chỉ dùng để đo 1 lần duy nhất |
| **Chronological split** | Chia dữ liệu theo thứ tự thời gian (không xáo trộn) |
| **MAE / RMSE / MAPE** | 3 kiểu đo sai số khác nhau (xem mục 6.6) |
| **Directional Accuracy** | Đo đúng hay sai về *hướng* đi (tăng hay giảm) |
| **Baseline** | Mô hình đơn giản nhất, làm mốc so sánh |
| **Early stopping** | Dừng huấn luyện khi không còn tiến bộ |

## 6.3. Chi tiết: tách train/validation/test theo thời gian — TUYỆT ĐỐI KHÔNG XÁO TRỘN

`app/forecasting/preprocessing.py`:

```python
if "timestamp" in frame.columns:
    ordered = frame.sort_values("timestamp").reset_index(drop=True)
n = len(ordered)
train_end = int(n * train_ratio)                              # 0.70
valid_end = train_end + int(n * validation_ratio)              # + 0.15
train      = ordered.iloc[:train_end]
validation = ordered.iloc[train_end:valid_end]
test       = ordered.iloc[valid_end:]                         # 0.15
```

### 6.3.1. Vì sao không dùng `train_test_split`

Hàm đó **xáo trộn ngẫu nhiên**. Hậu quả: dữ liệu **tương lai** nằm trong tập train, và dữ liệu **quá khứ** nằm trong tập test.

Hình dung thế này: bạn cho học sinh xem **đề thi có sẵn đáp án** để luyện, rồi bảo đó là đề thi. Tỷ lệ đúng sẽ rất cao — nhưng **không nghĩa gì**, vì khi đi thi thật thì không có đáp án.

**Đây là lỗi phổ biến nhất trong đồ án sinh viên** và là thứ thầy hỏi đúng.

### 6.3.2. Ba tỷ lệ

`train_ratio=0.70`, `validation_ratio=0.15`, `test_ratio=0.15`.

- **Validation (15%)** dùng cho early stopping của LSTM.
- **Test (15%)** chỉ dùng để đo lần cuối, **một lần duy nhất**.

### 6.3.3. Chi tiết: kết quả có lặp lại được không

`set_global_seed(settings.random_seed)` với `random_seed = 42` trước **mỗi** lần train — gọi trong `train_model()` và trong `LSTMForecastModel.fit()`.

Nếu không có seed, mỗi lần train LSTM cho kết quả khác nhau → không thể so sánh giữa các lần cải tiến code. Đây là điều tối thiểu cần có để một thí nghiệm khoa học có ý nghĩa.

## 6.4. Chi tiết: LSTM — dự đoán tỷ lệ thay vì mức giá

### 6.4.1. Hiểu đơn giản: vấn đề

Hãy hình dung bạn dạy một đứa trẻ đoán "ngày mai giá bao nhiêu?" bằng cách cho xem 1000 ví dụ trong đó giá dao động **26 → 196**.

Rồi bạn hỏi nó về ngày mai, khi giá đang ở **345**.

Đứa trẻ đó **chưa bao giờ thấy con số nào trên 196**. Nó sẽ không dám đoán cao hơn 196 — vì chưa từng thấy ví dụ nào như vậy.

**Đó chính xác là lỗi của LSTM ban đầu:**

| | Giá trị |
|---|---|
| Train split | 26 → 196 |
| Test split | 195 → 349 |
| Hệ quả | Mọi giá test nằm **ngoài vùng 0–1** mà mạng từng thấy ⇒ mạng **bão hoà** ở ~278 trong khi cổ phiếu ở 345 |
| Kết quả | Hold-out MAE = **50.48**, MAPE = **15.6%** |

### 6.4.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Non-stationary** | Đặc tính của dữ liệu mà thống kê thay đổi theo thời gian (giá cổ phiếu luôn vậy) |
| **Saturation / ceiling** | Mô hình bị trần cứng, không dự đoán ra ngoài vùng đã học |
| **MinMaxScaler** | Ép mọi giá trị về khoảng 0–1: `(x − min) / (max − min)` |
| **Relative target** | Dự đoán **tỷ lệ** `giá_mai / giá_hôm_nay` thay vì `giá_mai` |
| **Equivariance** | Nếu nhân toàn bộ giá lên 2, dự đoán cũng nhân lên 2 |

### 6.4.3. Chi tiết: cách sửa

```python
y_rel = target_close_next / close          # tỷ lệ, không phụ thuộc mức giá
y_abs = y_rel × close_base                 # khôi phục mức giá khi suy luận
```

**Trực giác:** thay vì hỏi "mai giá bao nhiêu?", hãy hỏi "**mai tăng hay giảm bao nhiêu phần trăm?**" — câu hỏi này **có cùng câu trả lời** dù giá là 26 hay 345.

**Kết quả đo được (cùng mạng, cùng split, cùng seed):**

| Chỉ số | Target tuyệt đối | Target tương đối | Cải thiện |
|---|---|---|---|
| MAE (hold-out) | 50.48 | **4.24** | **−91.6%** |
| MAPE | 15.6% | **1.33%** | **−91.5%** |

### 6.4.4. Chi tiết: tách "tính thống kê" và "áp dụng thống kê"

```python
def _fit_targets(self, features, targets):
    """Tính thống kê scaler và trả target đã scale (CHỈ dùng cho TRAIN)."""

def _transform_targets(self, features, targets):
    """Scale bằng scaler ĐÃ TÍNH, KHÔNG tính lại (dùng cho VALIDATION)."""
```

**Vì sao quan trọng:** nếu validation mà tính lại scaler, thì giá validation sẽ thấm vào thống kê của train ⇒ tín hiệu early-stopping bị lạc quan ⇒ chọn sai epoch ⇒ kết quả trên test cũng bị ảnh hưởng.

Đây là **rò rỉ dữ liệu (data leakage) dạng tinh vi** — không thấy bằng mắt, phải hiểu nguyên lý mới phát hiện.

### 6.4.5. Chi tiết: tham số & vì sao chạy CPU

```python
lstm_sequence_length = 60     # cửa sổ nhìn lại
lstm_hidden_size     = 64
lstm_num_layers      = 2
lstm_dropout         = 0.2
lstm_learning_rate   = 0.001
lstm_batch_size      = 32
lstm_epochs          = 20
lstm_patience        = 5      # early stopping
device = torch.device("cpu")  # CPU-only: không phụ thuộc GPU
```

`device="cpu"` là **quyết định triển khai có chủ đích**: đồ án phải chạy được trên máy của thầy/ban hội đồng mà không có GPU. LSTM 2 lớp × 64 hidden trên CPU train AAPL trong ~15-25 giây — chấp nhận được.

## 6.5. Chi tiết: ARIMA — dự đoán từng ngày một

### 6.5.1. Hiểu đơn giản

ARIMA (viết tắt **A**uto**R**egressive **I**ntegrated **M**oving **A**verage) là mô hình thống kê kinh điển. Với tham số `(5,1,0)`:

- **5**: nhìn lại 5 phiên trước.
- **1**: trừ đi 1 lần phép trừ trung bình (để dữ liệu bớt "đi xuống có hệ thống").
- **0**: không có thành phần trung bình động.

### 6.5.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Auto-regressive** | Dùng giá quá khứ để dự đoán giá hiện tại |
| **Differencing** | Lấy hiệu giữa 2 phiên liên tiếp để loại xu hướng |
| **One-step-ahead** | Dự đoán **phiên kế tiếp** khi mới chỉ biết tới hôm nay |
| **Multi-step forecast** | Dự đoán cả N phiên tới bằng một lần gọi |

### 6.5.3. Chi tiết: vì sao phải "dự đoán từng ngày một"

Nếu gọi `model.forecast(steps=len(test))` một lần, đó là **chiếu dài hạn**, không phải dự đoán một bước — sai số đo được nói về kỹ năng chiếu dài hạn, không nói về kỹ năng dự đoán từng ngày (tức là **không nói về thứ bạn thực sự dùng**).

Thay vào đó:

```
Với mỗi phiên t trong test:
    1. Dự đoán close[t] (chỉ dùng dữ liệu ≤ t-1)
    2. So sánh với close[t] thật
    3. Đưa close[t] thật vào mô hình: model.append(actual, refit=False)
```

Đây là **one-step-ahead rolling evaluation** — đúng nghĩa "dự đoán phiên kế tiếp khi mới chỉ biết tới hôm nay".

### 6.5.4. Chi tiết: lỗi "Đúng hướng luôn bằng 0" — đã sửa

Công thức:

$$\text{DA} = \frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[\text{sign}(\hat{y}_i - y_{i-1}) = \text{sign}(y_i - y_{i-1})\right]$$

**Nghĩa đời thường:** "Phiên đó tăng hay giảm — so với phiên liền trước."

Code cũ so sánh với **chính phiên được dự đoán**:

```python
previous = close          # SAI: sign(actual - actual) = 0 ⇒ DA = 0.00%
```

Fix:

```python
shifted = np.concatenate([[np.nan], close[:-1]])   # ĐÚNG: phiên liền trước
```

**Đo được:** ARIMA DA của AAPL = **50.79%** (trước đây 0.00%). Đây là con số **thực tế và trung thực** — đáng chú ý rằng nó cao hơn 50% một chút, tức mô hình có chút kỹ năng nhưng **không** phải "chính xác 87%".

## 6.6. Chi tiết: 4 bộ chỉ số đánh giá

`app/forecasting/evaluator.py`:

$$\text{MAE} = \frac{1}{N}\sum_{i=1}^{N}|y_i - \hat{y}_i| \qquad
\text{RMSE} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(y_i-\hat{y}_i)^2} \qquad
\text{MAPE} = \frac{100}{N}\sum_{i=1}^{N}\left|\frac{y_i-\hat{y}_i}{y_i}\right|$$

**Trực giác đời thường:**

| Chỉ số | Đọc là gì | Ví dụ |
|---|---|---|
| **MAE** | "Trung bình mỗi ngày dự đoán lệch bao nhiêu tiền?" | 3.00 USD |
| **RMSE** | "Lệch bao nhiêu tiền, nhưng lệch lớn thì phạt nặng hơn?" | 4.29 USD |
| **MAPE** | "Lệch khoảng bao nhiêu phần trăm?" | 1.11% |
| **DA** | "Có đoán đúng hướng tăng/giảm không?" | 50.79% |

> **Vì sao báo cả 3:** MAE dễ đọc nhưng nhạy với giá trị lệch lớn; RMSE phạt nặng hơn; MAPE là đơn vị "%" nên giao tiếp được với người đọc không rành toán. Nếu chỉ báo MAE, thầy hỏi "sao có mấy điểm lệch 50 USD?" thì không có công cụ để lý giải.

## 6.7. Chi tiết: dự đoán đa bước đệ quy

### 6.7.1. Hiểu đơn giản: vấn đề gốc

Linear Regression và LSTM được huấn luyện để dự đoán **1 ngày**. Nhưng bạn muốn biết **5 ngày tới**.

Trước đây, hệ thống vẽ dự đoán 1 ngày của mọi phần lịch sử lên cạnh giá thật. Nhưng `predict(frame)[i]` là ước lượng của phiên **i+1** — vẽ nó cạnh actual của phiên i ⇒ **lệch đúng một phiên**.

**Ba triệu chứng đều từ một nguyên nhân đó:**

1. **Chart không đổi khi đổi mã.** Predictor đọc `GoldLayer().read(symbol)` cho mã *hiện tại*, nhưng đường "actual" của chart lại lấy từ `predictions.parquet` của model **train cuối cùng**. Chuyển AAPL → ROKU vẫn hiện đường của AAPL.
2. **Đường "PREDICTED" nằm cạnh "ACTUAL" thay vì chồng lên.** Lệch một phiên trên chuỗi daily gần như vô hình trên trục 6 tháng — hai đường *trông* khớp, nhưng **không** khớp.
3. **Dự báo không bao giờ chạm tới tương lai.** Điểm cuối chart là giá đóng cửa **đã biết**. Ô "horizon" **không làm gì cả** với 2 model này.

### 6.7.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Recursive multi-step** | Dùng chính kết quả dự đoán bước trước làm đầu vào cho bước sau |
| **Error compounding** | Sai số tích luỹ dần theo mỗi bước dự đoán |
| **Prediction offset** | Mô hình bỏ qua N hàng đầu (vì chưa đủ dữ liệu) |

### 6.7.3. Chi tiết: cơ chế đệ quy

```
bước 1: dự đoán close[t+1] từ feature của phiên t
         ↓ ghi giá dự đoán vào hàng feature của t+1
         ↓ tính lại các chỉ báo phụ thuộc (SMA, RSI, BB...)
bước 2: dự đoán close[t+2] từ feature vừa cập nhật
         ↓ ...
bước H: dự đoán close[t+H]
```

Đây là cách tiếp cận đệ quy tiêu chuẩn cho model một-bước. Nó **thành thật** về giới hạn của mình — sai số tích luỹ mỗi bước — và chính vì thế chart hiển thị **hai vùng tách bạch** (hold-out đã xảy ra vs. dự báo tương lai) thay vì vẽ một đường liên tục gây ấn tượng giả.

### 6.7.4. Chi tiết: hai model có "hình dạng" kết quả khác nhau

| Model | `predict(frame)` trả về | `result[i]` ước lượng close của |
|---|---|---|
| Linear Regression | 1 giá trị / hàng | hàng `i+1` |
| LSTM | `len(frame) − seq_len + 1` giá trị | hàng `seq_len + i` |

`multistep.py` xử lý bằng `_prediction_offset()` — báo cáo có bao nhiêu hàng nằm giữa đầu frame và hàng đầu tiên model có thể chấm điểm.

## 6.8. Chi tiết: kết quả đo thật (AAPL, ngày 06/11/2026)

| Mô hình | MAE | RMSE | MAPE | Đúng hướng | Số điểm hold-out |
|---|---|---|---|---|---|
| Linear Regression | **2.994** | 4.251 | **1.096%** | **53.48%** | 374 |
| ARIMA (5,1,0) | 3.006 | 4.293 | 1.108% | 50.79% | 381 |
| LSTM | 3.294 | 4.628 | 1.161% | 46.86% | 318 |

> **Cách trả lời khi thầy hỏi "mô hình nào tốt nhất?":**
> *"Trên tập hold-out cụ thể này, Linear Regression có MAE thấp nhất. Điều này **không** có nghĩa LR 'tốt nhất' nói chung — LSTM có ưu thế khi quan hệ phi tuyến mạnh, và cả ba đều có DA ~50%, tức **gần như không có kỹ năng dự đoán hướng vượt quá ngẫu nhiên** trên cổ phiếu daily này. Kết quả này được trình bày trung thực thay vì bị bóp méo để trông 'ấn tượng'."*

## 6.9. Chi tiết: Model Registry — nơi lưu mô hình đã train

`app/forecasting/model_registry.py`. Mỗi model lưu vào `data/models/{MÃ}/{tên_mô_hình}/`:
```
metadata.json      # tham số, split, metrics
registry.json      # lịch sử các lần train
model.joblib / arima_result.pkl / lstm.pt
scalers.joblib / scaler.joblib
history.npy
predictions.parquet
```

`predictions.parquet` là nơi chart hold-out lấy dữ liệu — và **chính là nguồn của lỗi "chart không đổi khi đổi mã"**. Fix: `predict_symbol` chỉ dùng parquet làm **dự phòng**, và frontend xoá cache khi đổi mã.


---

## 6.10. Hiểu đơn giản: ba trục thời gian — dự báo được trả lời ở đâu

Câu hỏi "hệ thống này dự báo được gì?" có **ba câu trả lời khác nhau**, và mỗi câu cần một nơi khác nhau để hiển thị. Nếu gộp tất cả vào một trang, trang đó sẽ nặng nề và người đọc sẽ không biết đâu là "con số chính".

| Trục thời gian | Câu hỏi | Ở đâu | Ai trả lời |
|---|---|---|---|
| **Tương lai** | "Ngày mai giá sẽ ra sao, mô hình nào nghĩ khác nhau?" | Trang **Mô hình** (`/forecast`) | Batch EOD ghi trước, trang hiển thị |
| **Hiện tại** | "Bây giờ giá bao nhiêu, hệ thống đang kỳ vọng gì?" | **Dashboard** (`/`) | Backend tóm tắt |
| **Quá khứ** | "Những lần trước, dự báo có đúng không?" | Trang **Dữ liệu thị trường** (`/market`) | Bộ chấm điểm đối chiếu giá thật |

**Ba nơi, ba mức độ chi tiết, nhưng chỉ MỘT bảng `predictions`.** Dashboard hiển thị **một** dòng (con số chính). Trang Mô hình hiển thị **bảng** (đủ 3 mô hình). Trang Dữ liệu thị trường hiển thị **lịch sử đã chấm**. Cùng một bảng — không phải ba nguồn.

## 6.11. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Batch EOD** | Lần chạy tự động sau khi đóng cửa: ingest dữ liệu → dự báo phiên mai → ghi vào MySQL → chấm điểm các dự báo cũ |
| **Đã công bố (published)** | Dự báo đã **ghi xuống database** trước khi phiên mở cửa — khác với dự báo tính lại tại thời điểm xem |
| **So sánh đa mô hình** | Nhiều mô hình dự báo cho **cùng một phiên**, đặt cạnh nhau để so sánh |
| **Khoá duy nhất** | `(symbol, model_name, target_session)` — một mã, một mô hình, một phiên chỉ có **một** dòng dự báo |

## 6.12. Chi tiết: một phiên, nhiều mô hình — bảng `predictions`

### 6.12.1. Hiểu đơn giản

Trước đây, mỗi đêm hệ thống chỉ ghi **một** dự báo cho mỗi mã (mô hình Linear Regression). Hệ quả: bảng 46.329 dòng nhưng **chỉ có 5 dòng ARIMA** — không thể trả lời "mô hình nào đáng tin hơn ngoài backtest".

Bây giờ batch EOD ghi **một dòng cho mỗi mô hình đã train**, tất cả cùng nhắm vào **một phiên**:

```
Phiên 2026-11-13, mã AAPL
+---------------------+--------------+-----------+
| Mo hinh             | Du bao       | Sai so    |
+---------------------+--------------+-----------+
| linear_regression   | 354,061      | 2,209     |
| arima               | 354,620      | 1,650     |
+---------------------+--------------+-----------+
```

Bảng `predictions` **không cần đổi schema** — khoá duy nhất vốn đã là `(symbol, model_name, target_session)`, nên các dòng của các mô hình khác nhau cùng tồn tại mà không đụng nhau.

### 6.12.2. Chi tiết: đường đi của một dòng dự báo

```
[Batch EOD 04:30 UTC]
    |
    +-> warm_cache("gold", toan bo ma)     doc Gold mot lan, dung cho moi mo hinh
    |
    +-> vong lap theo ma:
            gold = layer.read(symbol)       <- lay tu cache, khong doc lai MinIO
            for name in [linear_regression, arima, lstm]:
                if not co model da train:  bo qua ma do, KHONG thay bang so khac
                point = light_forecast.next_point(symbol, name, gold, horizon=1)
                repository.upsert({... "model_name": name ...})
```

Điểm quan trọng: **Gold chỉ được đọc MỘT lần cho mỗi mã**, dùng chung cho cả 3 mô hình. Đọc Gold là phần tốn kém nhất (0,41 giây/mã), dự báo chỉ 0,02 giây.

### 6.12.3. Chi tiết: hai mức độ chi tiết, MỘT nguồn

| Nơi hiển thị | Hàm đọc | Trả về |
|---|---|---|
| Dashboard | `latest_for_symbol(symbol)` | 1 dòng — dự báo mới nhất |
| Trang Mô hình | `for_symbol_and_session(symbol, session)` | Tất cả mô hình cho phiên đó |
| Trang Dữ liệu thị trường | `unscored()` / `scored` | Lịch sử đã chấm |

Cả ba đọc **cùng một bảng `predictions`**. Không có bản sao nào của một dự báo. Đây là lý do Dashboard và trang Mô hình không bao giờ hiển thị hai con số khác nhau cho cùng một dự báo.

### 6.12.4. Chi tiết: dự báo nhiều mô hình trên sàn đại diện

Để tuyên bố "3 họ mô hình được so sánh" mà có ý nghĩa, mẫu phải trải nhiều sàn. Script `backend/scripts/train_representative_models.py` chọn **tối đa 5 mã mỗi sàn** từ một danh sách mã thanh khoản cao, rồi train cả ARIMA và LSTM trên từng mã:

```powershell
python scripts/train_representative_models.py --models arima,lstm --per-exchange 5 --workers 4
```

Danh sách mã là **lựa chọn có chủ ý và được ghi lại trong output**, không phải một bộ lọc im lặng — một mã không có lịch sử Gold sẽ bị bỏ qua chứ không được train trên dữ liệu rỗng.

**Đo ngày 17/11/2026:** 58 mã đủ điều kiện (6 mã trong danh sách không có lịch sử Gold nên bị bỏ qua), 116 lần train, **tất cả thành công**, ~11 phút với 4 worker.

### 6.12.5. Chi tiết: lỗi "Lock wait timeout" — và vì sao cách sửa là đọc trước, ghi sau

**Triệu chứng.** Lượt chấm điểm đêm dừng lại với `Lock wait timeout exceeded; try restarting transaction` (do `innodb_lock_wait_timeout` = 50 giây). 708 dòng dự báo bị bỏ qua dù giá thật đã có trong Gold.

**Vì sao xảy ra.** Hàm `score_all` mở một session SQL, đọc danh sách dự báo cần chấm, rồi **đọc Gold từ MinIO ngay bên trong transaction đó**. Với ~970 mã, mỗi lần đọc Gold mất ~0,4–120 giây, nên transaction phải mở hàng chút giây. Khi tới lúc `UPDATE`, MySQL phát hiện hàng đó đang bị khóa bởi chính transaction của mình, chờ `innodb_lock_wait_timeout` rồi báo lỗi — dù **không có ai khác** giữ khóa.

**Fix.** Tách lượt chấm thành **hai pha**:

```
Pha 0: doc danh sach du bao can cham     (transaction ngan, commit ngay)
Pha 1: doc Gold cho tung ma              (KHONG co transaction nao mo)
Pha 2: ghi diem vao database              (transaction ngan)
```

**Bằng chứng.** Đo ngày 17/11/2026: sau khi sửa, lượt chấm điểm chạy **0,2–0,7 giây/mã** (trước đây là 51 giây rồi lỗi) và **695 dòng được chấm thành công**. 13 dòng còn lại là các phiên mà Gold chưa có bar — chúng **không** được chấm điểm, đúng theo nguyên tắc "chưa có giá thật thì không có điểm".

### 6.12.6. Chi tiết: tai sao khong train lai mo hinh moi ngay

Câu hỏi tự nhiên: "Dữ liệu mới vào mỗi ngày, vậy có phải train lại không?"

**Không, và đây là lý do:**

| | Train mỗi ngày | Refit định kỳ (2–4 tuần) |
|---|---|---|
| Chi phi (973 ma x LSTM) | **6–7 gio/ngay** | 6–7 gio/tuan |
| Rui ro overfit | Cao — mo hinh bam dung 1 ngay | Thap |
| Y nghia khoa hoc | Yeu — "du bao bang du lieu toi hom nay" la bai toan khac | Dung bai toan du bao |

**Van de that duoc phat hien:** tat ca 973 mo hinh Linear Regression deu co `train_end` ≈ **2023-11-17**, tuc la **hoc tren du lieu den cuoi 2023** nhung lai dung de du bao nam 2026. Nguyen nhan la `chronological_split` chia 70/15/15 theo thoi gian — train set chi chiem 70% dau lich su.

ARIMA da co co che bu (`model.extend()` noi cac phien moi vao state-space, xem `light_forecast._arima_future`). Linear Regression va LSTM **khong** co co che do: chung dung he so cua 2023 nhung ap len dac trung cua 2026 — ve ky thuat la dung (he so hoi quy khong doi theo thoi gian), nhung bo loi 2 nam du lieu.

**Lo trình khắc phục:** them che do `--refit` cho `scripts/train_universe.py` — train tren du lieu **den hien tai**, van giu 15% test sach de do duoc, chay bang cron **1 lan/thang**.

**Da thuc hien (17/11/2026).** Hai co che moi duoc them vao `train_model()` va
`train_universe()`:

| Co che | Tham so | Tac dung |
|---|---|---|
| **Rolling refit** | `--end-date YYYY-MM-DD` | Cat lich su **truoc** khi chia tap, nen hold-out la du lieu **chua tinh thay** |
| **Full fit** | `--full-fit` | Mo hinh ship ra duoc fit tren **100%** lich su, nhung metric van lay tu cung split 60/20/20 |

```powershell
# Don gia: chi model linear_regression, train den 10/11/2026
cd backend
.\.venv\Scripts\python.exe scripts\train_universe.py --model linear_regression --end-date 2026-11-10

# Refit day du (model duoc ship): fit tren toan bo lich su den 10/11/2026
.\.venv\Scripts\python.exe scripts\train_universe.py --model linear_regression --end-date 2026-11-10 --full-fit
```

**Vi sao phai co ca hai, khong gop lai?** Hai cau hoi khac nhau can hai cau tra loi
khac nhau:

- *"--full-fit" khong co "hold-out sach"* — dung khi **ship** mo hinh. Mo hinh
  duoc dung de du bao phien toi phai hoc tren **tat ca** du lieu co san; giu lai
  40% chi de do la thoa doi cua chinh no.
- *"--end-date" khong co "duoi tuong lai"* — dung khi **do** mo hinh. Neu huan
  luyen tren ca du lieu den hien tai roi do lai tren chinh doan do, con so do
  se khong con nghia gi.

Giai quyet cua nhom: **metric luon lay tu cung mot split 60/20/20** o ca hai
che do, va duoc ghi vao registry (`fit_mode`, `training_data_end`). Nho vay con
so tren dashboard **nghia giong nhau** truoc va sau moi lan refit — neu doi
tach, chuoi lich su do chinh xac se thanh mot con so vo nghia.

**Bang chung (do ngay 17/11/2026, AAPL, `--end-date 2026-11-10`):**

| Che do | So dong fit | MAE (hold-out) | `fit_mode` |
|---|---|---|---|
| Mac dinh | 1.741 | 3,0243 | `holdout_split` |
| `--full-fit` | 2.488 | 2,9817 | `full` |

Ba mo hinh deu ho tro hai che do, do bang lenh:

```
arima   fit_mode=full  test_end=2026-11-09  mae=2.9669  da=0.5512
lstm    fit_mode=full  test_end=2026-11-09  mae=3.3734  da=0.5298
```

> **Luu y quan trong:** `test_end = 2026-11-09` (truoc bien `2026-11-10`) xac nhan
> phien hold-out **nam ngoai** ranh gioi training — dang bai toan du bao that, khong
> phai hoi quy tren du lieu da thay.

### 6.12.7. Chi tiết: tai sao khong dung ca 3 mo hinh cho TAT CA ma — va do lai

Day la cau hoi phai tra loi mot cach trung thuc, va con so duoc do **co bang chung** chu khong phai uoc luong.

**Chi phi do ngay 17/11/2026** tren may phat trien (1.002 ma trong Gold):

| Cong viec | linear_regression | ARIMA | LSTM | Tong |
|---|---|---|---|---|
| **Train** (1 ma) | 1,03 s | 7,42 s | 17,72 s | 26,17 s |
| **Train tat ca** | 0,29 gio | 2,07 gio | 4,93 gio | **7,28 gio** |
| **Infer** (1 ma, light path) | 0,036 s | 0,043 s | 0,086 s | 0,165 s |
| **Infer tat ca** (hang dem) | 0,60 phut | 0,72 phut | 1,44 phut | **2,76 phut** |

**Hai nguyen nhan giu lai phan "mo hinh nhe" cho toan bo 1.002 ma:**

1. **Chi phi train.** 7,28 gio cho mot lan bootstrap la du de chay. Nhung neu chay huyen lieu **moi tuan**, no la 7,28 gio x 52 = **379 gio/nam** may — tren VPS 8GB, dong thoi phai phuc vu web. Bai luan van khong co gi cho mot job nhu vay.
2. **Chi phi infer LSTM tren VPS.** 1,44 phut/ma x 1.002 ma la 24 phut neu chay tuần tu tren VPS 8GB (khong phai 16 core cua may phat trien). Cong them viec ghi 3 dong du bao moi ma vao MySQL.

**Do lai: song song co giup khong?** Do ngay 17/11/2026 tren may 16 core:

| So worker | Thoi gian (wall) | Hieu qua / ma |
|---|---|---|
| 1 | 24,9 s / 2 ma | 12,43 s |
| **2** | 39,7 s / 4 ma | **9,92 s** |
| 4 | 94,1 s / 8 ma | 11,76 s |
| 6 | 131,3 s / 12 ma | 10,94 s |

**Ket luan quan trong:** song song **khong tang toc dang ke** — 2 worker la diem tot nhat, them worker lai lam cham hon. Ly do: PyTorch da dung het CPU trong forward pass cua mot ma, nen chay nhieu tien trinh chi cong them cu cho OS. Day la ly do `train_universe.py` chay **tuần tu** va khong dung ProcessPoolExecutor.

**Vay tai sao khong dung ca 3 mo hinh cho tat ca ma?** Vi day khong phai mot quyet dinh "kho nang" ma la mot **quyet dinh ve ngan sach** — va con so duoc do:

| Phuong an | Chi phi | Do le | Ket qua |
|---|---|---|---|
| Linear Regression cho 1.002 ma | 0,29 gio train | 100% ma | Dung nhanh, phu toan bo |
| + ARIMA cho 1.002 ma | +2,07 gio train | +100% ma | **7,28 gio bootstrap — chay duoc** |
| + LSTM cho 1.002 ma | +4,93 gio train | +100% ma | **11,2 gio — chay overnight duoc, nhung VPS khong chay duoc** |
| **3 mo hinh tren 58 ma dai dien** | 0,68 gio train | 5,8% ma | **Du bằng chung khoa hoc, chay tren VPS duoc** |

**Quyet dinh cua em la phuong an cuoi.** Ly do khong phai "khong lam duoc" — ma la:

- **Do khoa hoc khong tang khi them mau.** So sanh 3 mo hinh tren 58 ma / 14 san cho du bang chung khoa hoc. Tren 1.002 ma thi bang so sanh van la 58 dong — chi them hang trinh, va nhung hang trinh do deu co MAE cao (model train tren it du lieu hon).
- **Chi phi van hanh tang theo.** 3 mo hinh x 1.002 ma x moi ngay la 2.765 dong du bao moi ngay trong bang `predictions`. Bang do la bang chung, khong phai bang nghien thu.
- **Bang chung phai sach.** Mot luận van tot hon la "58 ma dai dien tren 14 san, ca 3 mo hinh deu co model that, so sanh duoc tren cung mot tap hold-out" hon la "1.002 ma, nhung 3/4 khong co LSTM".

> **Cach tra loi khi thay hoi "sao khong chay LSTM cho tat ca ma?":**
> *"Em chay duoc ca 3 mo hinh cho tat ca 1.002 ma — chi phi bootstrap la 7,28 gio, em do ro. Em khong lam vi do la **quyet dinh ve ngan sach** chu khong phai do khong nang: LSTM tren VPS 8GB se ton 24 phut moi dem chi rieng buoc du bao, va 379 gio/nam neu chay hang tuan. Em chon 58 ma dai dien tren 14 san de so sanh 3 mo hinh, vi do la mau ma moi mau co ca 3 mo hinh deu co model that — va em do bang chung bang cach so sanh tren cung mot tap hold-out chu khong noi 'mo hinh nao tot nhat'."*

### 6.12.7b. Da trien khai: cron hang dem publish ca 3 mo hinh (do ngay 17/11/2026)

Sau khi do xong chi phi, phan **du bao** (khong phai phan train) da duoc **bat
da** cho ca 3 mo hinh. Doi voi buoc du bao, chi phi **khong phai** 7,28 gio —
sau khi toi uu LSTM 22 lan, toan bo buoc du bao cua 1.002 ma cho ca 3 ho va
chi ton **2,76 phut**.

`backend/crontab` bay gio chay:

```
30 4 * * 1-5 root cd $APP_HOME && /opt/venv/bin/python scripts/run_scheduled_job.py \
    universe-forecast --model linear_regression,arima,lstm >> $APP_HOME/logs/cron.log 2>&1
```

Bang `predictions` co khoa duy nhat `(symbol, model_name, target_session)`, nen
ba mo hinh cung ton tai **ma khong can migration** nao.

**Quy tac khong bao gio "san":** mot ma khong co mo hinh da train cho mot ho
thi **khong co dong** cho ho do — no khong bao gio duoc gan bang mot du bao thay
the. Do la ly do bang so sanh tren trang `/forecast` hien:

| Nhom ma | So ma | So dong tren bang so sanh |
|---|---|---|
| Co ca 3 mo hinh (mau dai dien) | 58 | **3 dong** — so sanh duoc ca 3 mo hinh |
| Chi co Linear Regression | ~944 | **1 dong** |

Bang so sanh do **khong phai mot lo so** — no la **hinh anh chan thuc** cua
he thong. Do la thu giang luy thuyet: 58 dong co bang chung so sanh, 944 dong
co du bao tot nhat ma may co the chay moi dem.

**Bang chung (do ngay 17/11/2026):**

```
GET /api/v1/forecast/published/AAPL
  -> session=2026-11-17, n_models=3
     arima:             352.667
     linear_regression: 352.336
     lstm:              354.264

GET /api/v1/forecast/published/0700.HK
  -> session=2026-11-18, n_models=3
```

> **Phan biet quan trong khi ba ve bang chung.** Ba dong tren la **du bao
> chua chiem** — phien 17/11/2026 chua co gia dong cua that. Do la "du bao", va
> no **khong duoc** dua vao bang do chinh xac. Bang do chinh xac cua he thong
> chi lay tu nhom `backfill_walk_forward` (44.416 dong da cham) — nhom nay moi la
> bang chung khoa hoc. Xem muc 6.12.5 va bang "Tinh le dung huong theo nguon du
> lieu" o Phan 7.

### 6.12.8. Chi tiết: mot toi uu lam LSTM nhanh gap 22 lan — va vi sao no khong doi bat ky con so nao

**Trieu chung.** Buoc du bao LSTM mat 1,9 giay tren moi ma — cham gap 60 lan so voi Linear Regression (0,032 giay). Mot lo du bao don cho 1.002 ma se ton 32 phut.

**Nguyen nhan.** `LSTMForecastModel.predict` chay **mot forward pass cho TUNG dong**: voi 2.517 dong lich su, no lam 2.457 lan forward tren cua so truot 60 dong — roi **vut boi tat ca tru ngoai truoc cuoi**. Con so do can cho mot du bao 1 phia la **60**.

**Fix.** Cat frame ve dung so dong ma mo hinh can, truoc khi goi `predict`.

**Bang chung.** Do ngay 17/11/2026 tren AAPL:

| Frame dua vao `predict` | Thoi gian | Do chinh xac |
|---|---|---|
| Toan bo 2.517 dong | 1.769 ms | 350,43166337 |
| 120 dong cuoi | 41 ms | 350,43166337 |
| 61 dong cuoi | 3 ms | 350,43166337 |

**Chenh lech = 0,0000000000** — khong phai "xap xa bang", ma **bang tuyet doi**. Ly do: output cuoi cua mo hinh cua so truot chi phu thuoc cua so truot CUOI, nen 2.456 forward pass truoc do la thua hoan toan.

**Tac dong.** Infer hang dem cho 1.002 ma: **33,02 phut → 2,76 phut**. Rieng LSTM: **31,83 phut → 1,44 phut** (nhanh gap **22 lan**).

> **Cau hoi tu kiem truoc khi ket thuc:** *"Co so nao trong file nay ma toi tu che ra khong?"*
> Cau tra loi: khong. Con so 350,43166337 o dong "toan bo 2.517 dong" va dong "61 dong cuoi" **gia bang nhau** — va test `tests/test_light_path_matches_full_path.py` bao dam hai duong tinh toan (light path va full path) khong bao gio cho ra so khac nhau.


---

# PHẦN 7 — HỆ THỐNG BACKTEST

> Sơ đồ: [4. Timeline backtest — tránh nhìn thấy tương lai](./SO_DO_MINH_HOA.md#4)

## 7.1. Hiểu đơn giản: backtest là gì

**Backtest** = "chơi lại quá khứ".

Giả sở bạn nghĩ ra chiến lược: *"Khi đường trung bình 20 ngày cắt lên đường trung bình 50 ngày thì mua; khi cắt xuống thì bán."*

Backtest sẽ:
1. Đọc lịch sử giá AAPL từ 2016 đến 2026.
2. Đi từng ngày một, **giả vờ** bạn đang ở ngày đó, chỉ biết những gì biết được ở ngày đó.
3. Áp dụng chiến lược, mua bán thật (mô phỏng), tính tiền.
4. Cuối cùng báo: lãi bao nhiêu, thắng bao nhiêu lần, lỗ nặng nhất thế nào.

**Mấu chốt là bước 2.** Nếu bạn cho hệ thống "biết trước" ngày mai giá tăng hay giảm rồi mới quyết định, kết quả sẽ **đẹp đẽ và vô nghĩa**. Đây gọi là **nhìn thấy tương lai (look-ahead bias)**.

## 7.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Backtest** | Chơi lại quá khứ với quy tắc giao dịch |
| **Strategy** | Quy tắc ra quyết định mua/bán |
| **Signal** | Lệnh "mua" (+1) hoặc "bán" (−1) |
| **Next-bar execution** | Tín hiệu hôm nay → lệnh khớp **ngày mai** |
| **Look-ahead bias** | Dùng thông tin tương lai để quyết định hiện tại |
| **Transaction fee** | % phí mỗi lần mua/bán (mặc định 0.1%) |
| **Slippage** | Giá thực tế lệch khỏi giá báo (mặc định 0.05%) |
| **Portfolio** | Sổ sách mô phỏng: đang có bao nhiêu tiền, bao nhiêu cổ phiếu |
| **Equity curve** | Đường biểu diễn giá trị tài khoản theo thời gian |
| **Maximum Drawdown** | Mức sụt giảm lớn nhất từ đỉnh |
| **Sharpe Ratio** | Lợi nhuận trên mỗi đơn vị rủi ro |
| **Win Rate** | % giao dịch có lãi |
| **Profit Factor** | Tổng lãi ÷ tổng lỗ |
| **Mark-to-market** | Ghi lại giá trị tài khoản ở mỗi phiên theo giá đóng cửa |
| **Force close** | Đóng nốt vị thế còn mở khi hết dữ liệu |

## 7.3. Chi tiết: nguyên tắc thực thi ở bar KẾ TIẾP

`app/backtesting/engine.py`:

```python
signals = strategy.generate_signals(frame)      # tính trên close của bar t
execution_signal = signals.shift(1).fillna(0)   # thực thi ở bar t+1
```

**Bằng chứng look-ahead bias nếu không có shift:**

> Giả sử giá ngày 1 thấp hơn giá ngày 2. Nếu ta dùng `close[1]` (giá đóng cửa ngày 1) để quyết định "mua" — mà lại khớp lệnh vào **chính giá đóng cửa ngày 1** — thì ta đã **biết ngày 1 tăng hay giảm trước khi ra quyết định**. Đó đúng là định nghĩa của look-ahead bias.

**Với shift:** tín hiệu sinh ra lúc 15:00 ngày t (khi bar t đóng), lệnh khớp ở giá **mở cửa** ngày t+1 (09:30). Bạn **không thể biết** giá ngày t+1 lúc ra quyết định — đó là điều kiện cần của một backtest trung thực.

`simulate()` khớp lệnh ở **open** bar, fallback **close** nếu open là NaN.

## 7.4. Chi tiết: hạch toán danh việc thực tế

`app/backtesting/portfolio.py`. Portfolio = tiền mặt + **một** vị thế (chỉ mua, không bán khống).

### 7.4.1. Cách mua

```python
fill_price = price * (1 + slippage_pct)   # giá thực tế sau trượt
spendable  = self.cash / (1 + fee_pct)     # tiền có thể dùng sau khi trừ phí
quantity   = spendable / fill_price        # số cổ phiếu mua được
fees       = quantity * fill_price * fee_pct
cost       = quantity * fill_price + fees
```

### 7.4.2. Bug "sai số 1.8e-12" — tại sao lại quan trọng

Trong số học lý tưởng, `cost` **bằng** `spendable` ≤ `cash`. Nhưng máy tính dùng số thực, nên `cost` cao hơn `cash` **một chút**:

```
cost = 10910.740000000002
cash = 10910.74
gap  = 1.8e-12      ← nhỏ hơn 1 xu, nhưng đủ để phá hỏng cả hệ thống
```

Với điều kiện `if cost > self.cash: return`, lệnh **bị từ chối**. Vì portfolio không giữ vị thế, mọi lệnh mua sau đó cũng bị bỏ qua.

**Triệu chứng nhìn thấy được:** backtest báo **1 giao dịch** cho một chiến lược bắn 11 tín hiệu trên cùng lịch sử. Chiến lược *trông* hỏng trong khi thực tế **chưa bao giờ được phép giao dịch**.

**Fix:**

```python
_CASH_TOLERANCE = 1e-9
if cost > self.cash * (1 + _CASH_TOLERANCE) or quantity <= 0:
    return
self.cash = max(self.cash - cost, 0.0)
```

Tolerance **tương đối** (nhân với `cash`) nên scale theo quy mô tài khoản, và nhỏ hơn nhiều so với số tiền nhỏ nhất có thể có ý nghĩa.

> **Bài học rút ra để trình bày:** đây là ví dụ điển hình của việc **kiểm chứng bằng bất biến** (invariant) thay vì kiểm tra bằng mắt. Bất biến ở đây là: "một lệnh hợp lệ phải luôn được chấp nhận". Kiểm tra bằng mắt sẽ không bao giờ phát hiện ra lỗi này vì con số vẫn *nhìn* đúng.

### 7.4.3. Bug "PnL không trừ phí mua" — đã sửa

Phí mua **đã** trừ khỏi tiền mặt ngay lúc mua, nên đường giá trị tài khoản đã phản ánh. Nhưng PnL (lãi/lỗ) của giao dịch tính là:

```python
pnl = net - entry_notional        # SAI: thiếu entry_fees
```

**Hậu quả thật:**

- Tổng lợi nhuận các giao dịch **không bằng** (vốn cuối − vốn đầu). Trên AAPL 10 năm, chênh lệch **120.32** — đúng bằng tổng phí mua.
- Một giao dịch lỗ vẫn có thể được báo là **thắng**, vì phí đẩy nó xuống dưới nước không được tính.
- ⇒ **Win Rate và Profit Factor đều sai**.

**Fix:** nhớ phí mua lúc mua, trừ trong `sell()`:

```python
pnl = net - self.entry_fees - entry_notional
cost_basis = entry_notional + self.entry_fees
```

**Bằng chứng kiểm chứng (đo ngày 06/11/2026, AAPL / MA Crossover / 10 năm):**

```
sum(pnl)              = 30845.122315
final_capital - init  = 30845.122315     + KHỚP TUYỆT ĐỐI
```

### 7.4.4. Bug "điểm equity cuối lệch" — đã sửa

Khi còn vị thế vào cuối chuỗi, `simulate()` đóng nốt. Nhưng điểm equity cuối đã được ghi **khi vị thế còn mở** ⇒ vẫn bao gồm phí ra và trượt giá.

**Fix:** thay điểm equity cuối bằng `portfolio.cash` (sổ sách đã phẳng).

**Vì sao quan trọng:** nếu không, vốn cuối cao hơn thực tế đúng bằng chi phí đóng vị thế — trên fixture là **12.63**. Người đọc không thể đối chiếu vốn cuối với bất kỳ giao dịch nào.

## 7.5. Chi tiết: công thức 5 bộ chỉ số

`app/backtesting/metrics.py`:

$$\text{Total Return} = \frac{V_T}{V_0} - 1$$

$$\text{Sharpe} = \sqrt{252}\cdot\frac{\bar{r}}{\sigma_r}$$

$$\text{Max Drawdown} = \min_t\left(\frac{V_t - \max_{s\le t} V_s}{\max_{s\le t} V_s}\right)$$

$$\text{Win Rate} = \frac{\#\{\text{giao dịch lãi}\}}{\#\{\text{giao dịch}\}} \qquad
\text{Profit Factor} = \frac{\sum \text{lời}}{|\sum \text{lỗ}|}$$

**Đọc đời thường:**

| Chỉ số | Câu hỏi nó trả lời |
|---|---|
| Total Return | "Sau cả kỳ, tôi còn bao nhiêu %?" |
| Sharpe | "Đổi 1 đơn vị rủi ro, tôi được bao nhiêu lợi nhuận?" (>1 là tốt) |
| Max Drawdown | "Tệ nhất, tôi mất bao nhiêu %?" (âm = sụt) |
| Win Rate | "Trong 100 lần, thắng mấy lần?" |
| Profit Factor | "Thắng được 1 USD thì mất mấy USD?" (>1 là tốt) |

`periods_per_year = 252` (số phiên giao dịch Mỹ mỗi năm).

## 7.6. Chi tiết: hai chiến lược

### 7.6.1. MA Crossover (`strategies/ma_crossover.py`)

```python
short_ma = sma(close, short_window)    # mặc định 20
long_ma  = sma(close, long_window)     # mặc định 50
position = (short_ma > long_ma).astype(int)
signal  = position.diff().fillna(0).clip(-1, 1)
```

**Đời thường:** "Đường ngắn hơn nằm trên đường dài hơn ⇒ xu hướng đang lên ⇒ mua. Nằm dưới ⇒ xu hướng đang xuống ⇒ bán." `+1` = golden cross (mua), `-1` = death cross (bán).

### 7.6.2. RSI Strategy (`strategies/rsi_strategy.py`)

```python
signal[raw < lower] = 1.0     # RSI < 30 → mua (giá quá bèo, sẽ hồi lên)
signal[raw > upper] = -1.0    # RSI > 70 → bán (giá quá cao, sẽ giảm)
crossings = np.where(signal != previous, signal, 0.0)   # chỉ giữ điểm giao cắt
```

**Đời thường:** RSI là thước đo "nóng" của cổ phiếu (0–100). Nó quá 70 nghĩa là quá nóng → có thể quá mức → bán. Nó dưới 30 nghĩa là quá lạnh → có thể quá bán → mua.

**Tối ưu hiệu năng có lý do:** `generate_signals` được gọi **hai lần mỗi cửa sổ** (train + test) trên ~175 cửa sổ ⇒ đây là đoạn nóng nhất của toàn bộ đường agent. Bản pandas gốc nối `replace → ffill → shift → where → fillna → clip`, mỗi bước cấp phát một Series + BlockManager mới. Profiling cho thấy **2.0s trong 4.5s** của một lần walk-forward nằm trong đúng hàm này.

Bản numpy tạo **bit-identical signals** (được xác nhận bởi golden test `scripts/_canonical_golden.py`) nhưng chỉ cấp phát vài mảng thay vì hàng chục đối tượng pandas.

## 7.7. Chi tiết: kết quả đo thật (AAPL / MA Crossover(20,50) / 10 năm, fee 0.1%, slippage 0.05%)

| Chỉ số | Giá trị |
|---|---|
| Total Return | **+308.45%** |
| Final capital | 40.845 (từ 10.000) |
| Sharpe Ratio | 0.787 |
| Max Drawdown | −28.63% |
| Win Rate | 44.83% |
| Profit Factor | 2.483 |
| Số giao dịch | 29 |

> **Đọc đúng con số này — điểm cực kỳ quan trọng khi bảo vệ:**
>
> Return +308% trong 10 năm AAPL là **con số thị trường**, không phải công trình của chiến lược. AAPL đã tăng mạnh trong thập kỷ đó; bất kỳ chiến lược "mua và giữ" nào cũng được gần con số này. Sharpe 0.787 và MDD −28.6% là con số **trung thực** của chiến lược.
>
> **Đây chính là lý do hệ thống bắt buộc có walk-forward validation** ở Phần 8: một backtest đơn lẻ trên toàn bộ lịch sử **không chứng minh** chiến lược có giá trị.

---

# PHẦN 8 — WALK-FORWARD VALIDATION

> Sơ đồ: [5. Walk-forward 159 cửa sổ trượt](./SO_DO_MINH_HOA.md#5) · [6. Lỗi 3 bug walk-forward](./SO_DO_MINH_HOA.md#6)

> **Đây là phần đáng đọc kỹ nhất của tài liệu**, vì nó vừa là **đóng góp mạnh nhất** của đồ án, vừa là nơi chứa **3 bug thật** đã tìm và sửa.

## 8.1. Hiểu đơn giản: walk-forward là gì và tại sao cần

**Vấn đề với backtest thường:** bạn chạy chiến lược trên **toàn bộ** 10 năm lịch sử, rồi báo "chiến lược này sinh lời 308%".

**Vấn đề:** bạn đã **chọn** chiến lược này (và tham số 20/50) *sau khi* nhìn toàn bộ lịch sử. Giống như đoán đề sau khi đã có đáp án.

**Walk-forward** sửa bằng cách **lặp lại** trên từng đoạn nhỏ:

```
Cửa sổ 0:  [ huấn luyện 180 ngày ][ kiểm tra 30 ngày ]
Cửa sổ 1:      [ huấn luyện 180 ngày ][ kiểm tra 30 ngày ]
Cửa sổ 2:          [ huấn luyện 180 ngày ][ kiểm tra 30 ngày ]
...
                                                     → trượt suốt lịch sử
```

Ở mỗi cửa sổ:
- **Phần train**: dùng để chọn tham số.
- **Phần test**: dùng để đo — và phần này **chưa từng** được nhìn thấy.

Sau đó lấy **trung bình** của tất cả các cửa sổ. Đây là mô phỏng trung thực nhất cho việc "deploy thật": khi bạn ra quyết định thật, bạn **chỉ có dữ liệu quá khứ**.

## 8.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Walk-forward validation** | Lặp train→test trượt dọc thời gian |
| **Rolling / Sliding window** | Hai cửa sổ trượt cùng nhau (train cố định độ dài) |
| **Expanding window** | Cửa sổ train lớn dần (đây là lỗi đã sửa) |
| **Out-of-sample** | Dữ liệu ngoài mẫu — mô hình chưa từng thấy |
| **Overfitting** | Mô hình khớp dữ liệu train quá đẹp, nhưng hỏng trên dữ liệu mới |
| **Overfitting Ratio** | Lợi nhuận trên train ÷ lợi nhuận trên test (đã chuẩn hoá) |
| **Return Consistency** | % cửa sổ test sinh lời |
| **Warmup context** | Đoạn dữ liệu quá khứ dùng để "khởi động" chỉ báo |

## 8.3. Chi tiết: ba bug đã tìm và sửa

### Bug A — Mọi cửa sổ đều báo 0 giao dịch

**Hiểu đơn giản:** Chiến lược MA Crossover cần **50 phiên** dữ liệu để tính đường trung bình dài hạn. Nhưng cửa sổ kiểm tra chỉ kéo dài 30 ngày ≈ **21 phiên giao dịch**. Trong 21 phiên đó, chưa từng có đủ dữ liệu để tính trung bình 50 ngày ⇒ chỉ báo = **NaN** ⇒ chiến lược **không bao giờ phát tín hiệu**.

**Giống như:** bảo một người tính trung bình 50 số khi trong tay chỉ có 21 số. Họ sẽ nói "không tính được" — và đó là câu trả lời đúng, nhưng không phải câu trả lời bạn muốn.

**Triệu chứng:** `avg_test_return = 0`, `total_test_trades = 0`, `return_consistency = 0`, `overfitting_ratio = 0`. Một bức tường số 0 nói **không điều gì** về chiến lược.

**Fix — warmup context:**

```python
context = pd.concat([warmup, test_data], ignore_index=True)   # warmup = đuôi train window
signals = strategy.generate_signals(context)
execution_signal = signals.shift(1).fillna(0)
execution_signal = execution_signal.iloc[len(warmup):].reset_index(drop=True)  # bỏ phần warmup
```

**Chứng minh không rò rỉ (không leak) — 3 điều kiện:**

1. Các hàng warmup nằm **hoàn toàn trong quá khứ** — chúng là chính những hàng mô hình đã train.
2. Chúng **bị loại khỏi** tín hiệu thực thi và khỏi mô phỏng ⇒ equity chỉ được ghi trên các hàng test.
3. Test phase bắt đầu **phẳng** với vốn của kỳ test.

**Đây chính xác là điều xảy ra trong thực tế:** chỉ báo của bar đầu tháng được tính từ các bar trước đó. Đây không phải "cho xem trước tương lai" — đây là "nhìn lại quá khứ".

**Kết quả:** 0 → **41 giao dịch**.

### Bug B — Cửa sổ train lớn dần vô hạn

**Hiểu đơn giản:** Ban đầu, cửa sổ huấn luyện của cửa sổ 0 là 180 ngày, nhưng của cửa sổ 175 là **10 năm** — vì nó luôn bắt đầu từ ngày đầu tiên của lịch sử.

Hậu quả: tỷ lệ overfitting chia "lợi nhuận 10 năm" cho "lợi nhuận 1 tháng" ⇒ ra con số **790** — vô nghĩa, không đọc được.

**Fix 1 — cửa sổ train cố định độ dài, trượt cùng cửa sổ test:**

```python
train_start = current_train_end - pd.Timedelta(days=self.train_period_days)
```

**Fix 2 — annualize để hai vế cùng đơn vị:**

```python
train_factor = 365.0 / max(self.train_period_days, 1)   # 365/180
test_factor  = 365.0 / max(self.test_period_days, 1)    # 365/30
annualised_train = avg_train * train_factor
annualised_test  = avg_test  * test_factor
overfitting_ratio = annualised_train / annualised_test
```

**Vì sao cần annualize:** train 6 tháng vs test 1 tháng — nếu không chuẩn hoá, tỷ lệ bị phóng to bởi chênh lệch độ dài. Sau khi chuẩn hoá, tỷ lệ trả lời đúng câu hỏi: *"chiến lược có giữ được ở ngoài mẫu không, hay chỉ chạy được trên kỳ nó được fit?"*

- Gần **1.0** → tổng quát hoá tốt.
- Lớn → đã bị overfit.

**Kết quả:** 790 (vô nghĩa) → **4.0** (đọc được).

### Bug C — Các cửa sổ gần nhất báo là FAILED

**Hiểu đơn giản:** Những cửa sổ mà phần kiểm tra quá ngắn (ít phiên giao dịch hơn ngưỡng tối thiểu) bị đánh dấu **FAILED**. Trên AAPL có **17/176** cửa sổ như vậy — và chúng là các cửa sổ **gần nhất**, tức đáng quan tâm nhất.

**Fix:** **bỏ qua** (không sinh) cửa sổ không đánh giá được. Và phải dùng `continue` chứ không `break`:

> Cửa sổ test 30 ngày chứa ~21 phiên, và quanh kỳ nghỉ lễ có thể xuống **19** — dưới ngưỡng 20. Dùng `break` sẽ **vứt bỏ mọi cửa sổ sau cửa sổ ngắn đầu tiên** (165/176 cửa sổ), chỉ còn lại 11 cửa sổ cũ nhất.

**Đây là loại bug "sửa một cái làm hỏng cái khác"** — vì vậy có test hồi quy riêng trong `test_backtest_walk_forward.py`.

**Kết quả:** 17 failed → **0 failed**; 159/159 cửa sổ đánh giá được.

## 8.4. Chi tiết: kết quả đo thật

**AAPL / MA Crossover, train 180 ngày / test 30 ngày:**

```
total_windows      : 159
passed_windows     : 159        (trước fix: 142/176)
failed_windows     : 0          (trước fix: 17)
avg_train_return   : 0.0493
avg_test_return    : 0.0021
avg_test_sharpe    : 0.1795
avg_test_max_dd    : -0.0094
total_test_trades  : 41
return_consistency : 0.132
overfitting_ratio  : 3.997      (trước fix: 790 — vô nghĩa)
thời gian chạy      : ~2s       (trước fix: 96s)
```

**Với khoảng test dài hơn:**

| train / test | windows | avg_test_return | consistency | overfit_ratio | trades | thời gian |
|---|---|---|---|---|---|---|
| 180 / 30 | 159 | 0.0021 | 0.132 | 4.00 | 41 | ~2s |
| 180 / 60 | 174 | 0.0079 | 0.259 | 2.03 | 87 | ~1.1s |
| 365 / 90 | 165 | **0.0180** | **0.345** | **1.73** | 120 | ~1.2s |

## 8.5. Chi tiết: cách đọc kết quả này trước thầy

Đây là **kết quả trung thực và quan trọng**:

1. **overfitting_ratio = 4.0** nghĩa là: chiến lược kiếm được **4 lần** nhiều hơn trên kỳ train so với kỳ test. Nói cách khác, **chiến lược KHÔNG tổng quát tốt** ở cấu hình này.

2. **Khi khoảng test dài lên (365/90), ratio giảm còn 1.73.** Hiện tượng này có hai lời giải thích hợp lý: (a) test dài hơn làm trung bình bớt nhiễu; (b) khi đánh giá trên cửa sổ 3 tháng, phần lớn "khả năng sinh lời" đến từ **xu hướng dài hạn của AAPL**, mà MA Crossover bắt được một phần. Đây **không** phải bằng chứng chiến lược tốt.

3. **return_consistency chỉ 13–35%** — nghĩa là chỉ 13–35% cửa sổ test sinh lời. Với một chiến lược giao dịch ngắn hạn trên một cổ phiếu có xu hướng mạnh, đây là **con số bình thường** — và là lý do thị trường nghiên cứu dùng phương pháp này.

> **Câu trả lời mẫu khi thầy hỏi "vậy chiến lược có ăn không?":**
>
> *"Kết quả walk-forward của hệ thống cho thấy MA Crossover trên AAPL **không tổng quát hoá tốt** ở cấu hình 180/30: overfitting ratio 4.0 và return consistency 13.2%. Đây là **kết quả khoa học, không phải kết quả marketing** — và chính nó là lý do hệ thống cần tầng kiểm định này. Nếu hệ thống chỉ báo con số +308% mà không có walk-forward, nó sẽ tạo ấn tượng giả. Đóng góp của đồ án là **công cụ đo**, và công cụ này nói rằng chiến lược này không đáng dùng ngoài mẫu."*

## 8.6. Chi tiết: disclaimer bắt buộc

Mọi kết quả walk-forward đều kèm `disclaimer` do `_build_disclaimer()` sinh. Đây là **yêu cầu pháp lý-đạo đức** của một đồ án tài chính: kết quả lịch sử **không** phải bảo đảm lợi nhuận tương lai.

## 8.7. Chi tiết: mở rộng đa mã + đường cơ sở mua & giữ (Đo ngày 11/11/2026)

> Tài liệu chi tiết riêng: [NGHIÊN CỨU ĐA MÃ: WALK-FORWARD + ĐƯỜNG CƠ SỞ MUA & GIỮ](./NGHIEN_CUU_DA_MA_WALK_FORWARD.md)

Phần 8.4–8.5 trên đo trên **một mã** (AAPL). Đó là một phép **minh hoạ**, không phải bằng chứng khoa học: một mã cổ phiếu trong một thập kỷ đo phần lớn "cổ phiếu đó tăng", không phải "chiến lược đúng". Hệ thống đã bổ sung tầng đo đa mã.

**Cấu hình đo:** 1.002 mã trong Bronze, lấy mẫu **8 mã/sàn × 13 sàn = 101 mã**; walk-forward train 365 ngày / test 90 ngày / trượt 90 ngày; vốn 10.000; phí 0,1%; trượt giá 0,05%.

**Kết quả (Đo ngày 11/11/2026, 3.687 cửa sổ kiểm tra, 0 mã lỗi):**

| Chỉ số | MA Crossover | RSI | Mua & giữ |
|---|---|---|---|
| Median lợi nhuận ngoài mẫu | 0,22% | 0,42% | **2,28%** |
| Median Sharpe | −0,025 | 0,132 | **0,456** |
| Median max drawdown | −4,56% | **−2,00%** | −11,87% |
| % mã có lãi | 60,4% | 70,3% | **91,1%** |
| % cửa sổ thắng đường cơ sở | 37,5% | 47,7% | — |
| % mã thắng đường cơ sở | 8,9% | 13,9% | — |

**Phát hiện quan trọng nhất:** cả hai chiến lược **không** vượt được đường cơ sở mua & giữ, và kết luận này **không đổi theo sàn** — ở cả 13 sàn, median lợi nhuận của chiến lược đều thấp hơn median của mua & giữ. Cái chiến lược thực sự tạo ra là **giảm rủi ro** (max drawdown −2,00% thay vì −11,87%), đánh đổi bằng việc bỏ lỡ phần lợi nhuận của xu hướng.

> **Cách trả lời khi thầy hỏi "vậy chiến lược có ăn không?":**
> *"Câu trả lời của em là: **không**, và đó là điều em đã dựng ra để chứng minh. Em chạy walk-forward trên 101 mã thuộc 13 sàn, và trên mỗi cửa sổ kiểm tra em đo song song chiến lược với đường cơ sở mua & giữ trên đúng những phiên đó, cùng phí và cùng cách khớp lệnh. Kết quả: đường cơ sở thắng ở 91,1% số mã; chiến lược chỉ thắng ở 8,9% (MA) và 13,9% (RSI) số mã. Điểm em bảo vệ được là phần lợi nhuận mà chiến lược tạo ra **không đáng kể so với việc cứ nắm giữ** — nó đổi lại bằng việc giảm max drawdown từ −11,87% xuống −4,56% (MA) và −2,00% (RSI). Đây là dữ liệu thật, đo trên dữ liệu thật, và em báo cáo nguyên vẹn kể cả khi nó bất lợi cho hệ thống của em."*

**Ba thay đổi trong code để làm được phép đo này:**

| # | Thay đổi | File | Vì sao |
|---|---|---|---|
| 1 | Module đường cơ sở dùng chung | `app/backtesting/benchmark.py` | Engine và validator phải tính baseline **giống hệt nhau**, nếu không phần so sánh là so hai định nghĩa khác nhau |
| 2 | Baseline + excess return **từng cửa sổ** | `app/backtesting/walk_forward.py` | Chênh lệch tính theo từng cửa sổ là **so sánh cặp**; lấy hiệu hai trung bình độc lập sẽ bị nhiễu bởi việc thị trường đi khác nhau giữa hai kỳ |
| 3 | Script đa mã + endpoint đọc file | `scripts/run_multi_symbol_walkforward.py`, `api/v1/endpoints/backtesting.py` | Phép đo mất ~2 phút; tính lại mỗi lần mở web sẽ gây timeout. Endpoint **đọc file** và nói rõ lệnh cần chạy khi file thiếu — không trả số giả |

**Giao diện:** trang `/backtesting` có 2 tab. Tab **Một mã cổ phiếu** chạy backtest cho 1 mã và vẽ **đường mua & giữ** (đường đứt nét) trên cùng trục với đường chiến lược. Tab **Walk-forward đa mã** hiển thị toàn bộ phân phối (metric so sánh, biểu đồ cột theo sàn, bảng theo sàn, bảng từng mã). Cả hai tab dùng **chung một lựa chọn chiến lược** ở đầu trang, nên hai thang đo luôn nói về cùng một quy tắc.

**Kiểm thử:** `backend/tests/test_backtest_benchmark.py` — 6 test phủ 4 bất biến: cùng tập phiên, cùng phí & trượt, tái lập được, và validator ghi baseline từng cửa sổ.

---

# PHẦN 9 — AI AGENT

> Sơ đồ: [12. Luồng AI Agent](./SO_DO_MINH_HOA.md#12)

## 9.1. Hiểu đơn giản

Bạn có thể hỏi bằng tiếng Việt: *"Phân tích kỹ thuật AAPL 3 tháng gần nhất"*, hoặc *"Kiểm tra chiến lược MA trên AAPL có ăn không?"*.

Agent sẽ:
1. Đọc câu hỏi.
2. **Tự quyết định** cần gọi công cụ nào (tool).
3. Gọi công cụ đó — công cụ này chạy trong backend, đọc dữ liệu thật từ lakehouse, tính toán thật.
4. Nhận kết quả số, rồi **viết lại thành câu trả lời** dễ hiểu.

**Điểm mấu chốt:** con số trong câu trả lời **không do AI tự nghĩ ra** — nó đến thẳng từ backend. AI chỉ làm nhiệm vụ "diễn giải số liệu thành lời".

## 9.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **LLM** | Mô hình ngôn ngữ lớn (ở đây là Gemini) |
| **Tool calling** | Cách cho LLM gọi hàm trong code thật |
| **Function schema** | Mô tả: hàm này tên gì, cần tham số gì, trả về gì |
| **Tool trace** | Danh sách các lệnh gọi tool đã thực hiện (để hiển thị & kiểm tra) |
| **Fallback** | Đường dự phòng khi dịch vụ chính không dùng được |
| **Keyword router** | Bộ định tuyến dựa trên từ khoá, không cần LLM |
| **Prompt budget** | Hạn mức token/thời gian cho một lần gọi LLM |

## 9.3. Chi tiết: 17 tool, 4 nhóm

| Nhóm | Tool |
|---|---|
| **Dữ liệu thị trường** | `query_stock_data`, `get_market_summary`, `get_market_index`, `get_orderbook` |
| **Chỉ báo kỹ thuật** | `calculate_indicators` |
| **Dự báo & backtest** | `forecast_stock`, `compare_models`, `run_backtest`, **`run_walk_forward`** |
| **Báo cáo tài chính** | `get_fundamental_metrics`, `get_income_statement`, `get_balance_sheet`, `get_cash_flow` |

Ngoài ra còn **4 tool hệ thống** trả lời câu hỏi về chính dự án:
`get_symbols_info`, `get_trained_models`, `get_system_architecture`, `get_storage_stats`.

> Trước đây nhóm thứ tư tên là "Tin tức & tài chính" và có thêm 4 tool tin tức.
> Ngày 12/11/2026, 4 tool tin tức đã bị gỡ cùng hệ thống tin tức (xem Phần 5B.1),
> nên số tool của agent giảm từ **21 xuống 17**.

**Vì sao tool-based thay vì fine-tune (huấn luyện lại mô hình):**

1. Agent cần dữ liệu **thời gian thực** — LLM không thể biết giá AAPL hôm nay.
2. Tool cho **khả năng truy vết** — mỗi câu trả lời gắn với lời gọi tool cụ thể.
3. Tool cho **tính xác thực** — mọi con số do backend tính từ lakehouse, LLM chỉ diễn giải.

## 9.4. Chi tiết: ngân sách thời gian — 2 tầng

```python
LLM_TOTAL_BUDGET_SECONDS = 45        # tổng cho MỌI lời gọi LLM của 1 reply
# deadline server: AGENT_REQUEST_TIMEOUT_SECONDS = 75
# timeout client: axios 90s
```

Agent tối đa **4 vòng**, mỗi vòng có thể mất 35s. Không có ngân sách chung, một sự cố provider có thể tiêu 140s — vượt deadline 75s.

**Thứ tự ưu tiên khi timeout:** server trả **504 kèm message giải thích hành động được**; client axios đặt timeout **90s** (cao hơn server một chút) để **message của server thắng cuộc đua**. Nếu client hết giờ trước, người dùng thấy "Yêu cầu mất quá lâu (>90s)…" — thông báo chung chung, không hành động được.

## 9.5. Chi tiết: cắt tỉa kết quả tool

```python
WALK_FORWARD_WINDOWS_SENT = 12
```

`run_walk_forward` trả **175 hàng** (một hàng/cửa sổ) = blob JSON 53 KB. Gửi hết lên Gemini tốn prompt token và đẩy request về sát ngưỡng throttle của provider.

**Chỉ bản gửi LLM bị cắt.** Bản lưu trong tool trace (và trả về UI) **giữ nguyên** ⇒ không mất dữ liệu nào. Giữ **đầu và đuôi** vì cửa sổ đầu (dữ liệu cũ nhất) và cửa sổ cuối (dữ liệu mới nhất) là hai cái người đọc quan tâm.

## 9.6. Chi tiết: fallback offline tất định

Khi hết Gemini key, `llm_provider=local` → keyword router xử lý trực tiếp. Hệ thống **không chết** vì thiếu API key — đây là yêu cầu để demo offline trước giám khảo.

---

# PHẦN 10 — FRONTEND

> Sơ đồ: [11. TanStack Query — vòng đời dữ liệu](./SO_DO_MINH_HOA.md#11)

## 10.1. Hiểu đơn giản

Frontend là **7 trang web** hiển thị những gì backend tính được:

| Trang | Đường dẫn | Dùng để |
|---|---|---|
| Tổng quan | `/` | Xem nhanh giá, chỉ báo, model đã train, dự báo phiên tới (1 dòng + độ tin cậy) |
| Dữ liệu thị trường | `/market` | Kho dữ liệu gốc: hồ sơ thống kê, so sánh nhiều mã, toàn bộ bảng phiên, **kiểm chứng dự báo đã qua** |
| Phân tích kỹ thuật | `/analysis` | Xem SMA/EMA/RSI/MACD/Bollinger |
| **Huấn luyện & so sánh model** | `/forecast` | Phòng thí nghiệm: **dự báo đã công bố (3 mô hình)**, train model, xem dự báo, so sánh trên tập hold-out |
| **Đánh giá chiến lược** | `/backtesting` | 2 tab: **Một mã cổ phiếu** (chạy chiến lược, equity curve & drawdown, so với mua & giữ) và **Walk-forward đa mã** (phân phối trên 101 mã / 13 sàn — Đo ngày 11/11/2026) |
| AI Agent | `/agent` | Hỏi bằng tiếng Việt |
| Trạng thái hệ thống | `/system` | 7 dịch vụ + số file theo tầng |

> **Ba trục thời gian — mỗi câu hỏi ở đúng một nơi.** "Ngày mai ra sao" → `/forecast`.
> "Bây giờ thế nào" → `/`. "Những lần trước có đúng không" → `/market`.
> Cả ba đọc **cùng một bảng `predictions`**, chỉ khác mức độ chi tiết — xem mục 6.10–6.12.


> **Không còn trang Tin tức & Tâm lý.** Trang `/news` bị gỡ ngày 12/11/2026 cùng
> toàn bộ hệ thống tin tức (xem Phần 5B.1). Số trang giảm từ 8 xuống 7.

> **Không còn trang Live Stream.** Toàn bộ đường dẫn realtime (cache trong RAM
> phục vụ SSE, hai client WebSocket Finnhub + SSI iBoard) bị gỡ ngày
> 11/11/2026 — xem mục 14.6. Dữ liệu duy nhất của hệ thống là **bar NGÀY**
> do cron nạp vào Bronze.

> **Đổi tên tab "Dự báo" → "Huấn luyện & so sánh model" (đo ngày 13/11/2026).**
> Hai nơi cùng in ra "sai số" và "đúng hướng", nhưng đo hai đối tượng khác nhau:
> trang `/forecast` đo **mô hình** trên tập hold-out (backtest), còn panel
> "Kiểm chứng dự báo" ở `/market` đo **hệ thống đang chạy** trên dự báo đã
> công bố trước phiên (ngoài tập huấn luyện). Tên cũ khiến người đọc tưởng
> trùng. Đường dẫn `/forecast` giữ nguyên để không phá liên kết cũ.

## 10.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **React Query / TanStack Query** | Thư viện quản lý "dữ liệu từ server": gọi API, cache, báo lỗi, tự làm mới |
| **queryKey** | Khoá định danh cache, ví dụ `["forecast-compare", "AAPL"]` |
| **Mutation** | Thao tác **ghi** (POST) — train, chạy backtest |
| **Recharts** | Thư viện vẽ biểu đồ SVG cho React |
| **axios** | Bộ gọi HTTP có timeout & xử lý lỗi |
| **i18n** | Hỗ trợ đa ngôn ngữ (Việt/Anh) |
| **Series** | Trong chart, mỗi đường là một "series" |

## 10.3. Chi tiết: TanStack Query — quản lý dữ liệu từ server

```typescript
// useForecast.ts
const compareQuery = useQuery({
  queryKey: ["forecast-compare", symbol],
  queryFn: () => compareModels(symbol),
  retry: 1,
});
const train   = useMutation({ mutationFn: (p) => trainModel({ symbol, model_name: modelName, ...p }) });
const predict = useMutation({ mutationFn: (h) => predictModel(symbol, modelName, h) });
```

**Vì sao TanStack Query thay vì Redux/Zustand:**

| Nhu cầu | React Query giải quyết |
|---|---|
| Cache theo `queryKey` | `["forecast-compare", symbol]` ⇒ đổi mã = key khác = refetch, **không** dùng nhầm cache cũ |
| Trạng thái `isLoading` / `isError` / `data` | Chuẩn hoá — không tự viết 4 biến `useState` cho mỗi query |
| Retry | `retry: 1` — thử lại 1 lần trước khi báo lỗi |
| Invalidate | Train xong → `invalidateQueries(["forecast-compare", symbol])` ⇒ bảng so sánh tự làm mới |
| Bỏ qua request trùng | Dedupe tự động — click "Train" 5 lần chỉ gửi 1 request |

**Vì sao `queryKey` phải chứa `symbol`:** đây chính là gốc rễ của lỗi "chart không đổi khi đổi mã". Nếu key là `["forecast-compare"]` thì React Query trả **cache của mã cũ** — và không bao giờ refetch. Đặt `symbol` vào key là cách sửa đúng bản chất, không phải vá triệu chứng.

## 10.4. Chi tiết: xử lý lỗi — phân biệt timeout với offline

`frontend/src/api/client.ts`:

```typescript
export function isBackendOffline(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}
export function isTimeout(error: unknown): boolean {
  return axios.isAxiosError(error) && error.code === "ECONNABORTED";
}
```

```typescript
if (isTimeout(error))
  return "Yêu cầu mất quá lâu (>90s) nên đã bị hủy. Backend vẫn đang xử lý — thử lại hoặc rút gọn câu hỏi.";
if (isBackendOffline(error)) return "Cannot connect to backend API.";
return payload?.message || error.message || fallback;
```

> **Vì sao phải phân biệt:** timeout **không phải** là mất kết nối — request **đã tới** server, chỉ là server trả lời lâu. Báo "cannot connect" khiến người dùng đi săn một lỗi mạng không tồn tại. Ba nhánh này phản ánh ba nguyên nhân thật: (1) quá tải server, (2) server chết, (3) lỗi nghiệp vụ có message riêng.

## 10.5. Chi tiết: ForecastChart — ba đường, không phải một

`frontend/src/components/charts/ForecastChart.tsx`. Ba series:

| Series | Nghĩa |
|---|---|
| `actual` | Giá thật; `null` cho phiên tương lai |
| `predicted` | Ước lượng của model cho phiên **đã xảy ra** (vùng hold-out) |
| `forecast` | Dự báo cho phiên **chưa xảy ra** |

> **Vì sao không vẽ tất cả trên một đường:** các điểm có `actual = null` là phiên **chưa xảy ra** — chúng là dự báo. Vẽ chúng trên cùng đường với lịch sử sẽ làm mô hình **trông như đã dự đoán trước** những phiên đó — một tuyên bố mà dữ liệu không hỗ trợ.

Chart có **đường kẻ dọc** ngăn cách "đã xảy ra" và "dự báo", và điểm đầu tiên của đường forecast **neo vào giá đóng cửa cuối cùng đã biết** để biểu đồ đọc liền mạch thay vì hai mảnh rời.

## 10.6. Chi tiết: Explainer — thành phần "dành cho người mới"

`frontend/src/components/common/Explainer.tsx` — khung gập mở giải thích thuật ngữ bằng văn bản đời thường:

- Backtest là gì, đọc chỉ số nào trước.
- Forecasting: hold-out là gì, MAE nghĩa là gì, tại sao horizon không phải "chắc chắn".
- Pipeline: Bronze/Silver/Gold khác nhau ở đâu.

**Vì sao đưa vào sản phẩm:** mục tiêu đồ án là **học thuật**, và người đọc kết quả phải là giảng viên + hội đồng. Giao diện tự giải thích giúp bảo vệ luận văn không bị hỏi "con số này nghĩa là gì?" ở giữa lúc trình bày.

## 10.7. Chi tiết: i18n Việt/Anh

`frontend/src/lib/i18n.tsx` — context + dictionary 2 locale, mặc định **VI**. Nút chuyển ở Header.

## 10.7.1. Chi tiết: băng giá trên thanh điều hướng

Thanh điều hướng không chỉ có 8 tab. Phía trên tab là một **dải giá chạy ngang
(market tape)** đọc từ lakehouse.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ● BĂNG GIÁ  AAPL 342.37 $-0.52%  MSFT 530.61 $-0.99%  NVDA 186.64 $2.78% │  ← chạy
├──────────────────────────────────────────────────────────────────────────┤
│  Dashboard   Dữ liệu thị trường   Phân tích kỹ thuật   Dự báo   Backtest │  ← tab
└──────────────────────────────────────────────────────────────────────────┘
```

**Vì sao cần dải giá:** một hàng 8 link xám là **bản đồ trang**, không phải
công cụ đầu tư. Mở app lên mà phải chờ đọc chữ là lãng phí một thứ không phải
thông tin — người dùng muốn thấy **giá** trước khi thấy **mục lục**.

**Vì sao gọi là "băng" (tape) và không phải "widget giá":** thuật ngữ tape là
thuật ngữ giao dịch thật — dải giá chạy là cách các sàn và terminal hiển thị
thị trường. Gọi đúng tên giúp người đọc luận văn hiểu đây là thành phần có
chủ đích, không phải hiệu ứng trang trí.

**Vì sao dùng CSS keyframe mà không dùng ticker bằng JavaScript:** ticker bằng
JS phải chạy mỗi frame, đo lại bề rộng track, rồi dịch chuyển — tức là **đọc
layout mỗi frame**. Đó chính là loại chi phí ẩn làm trang nặng. Ở đây track
được render **hai lần** và animation dịch chính xác `-50%`, nên vòng lặp liền
mạch và chỉ dùng `transform` (compositor, không repaint).

**Vì sao dừng khi rê chuột:** cần đọc được một dòng mà nó không trượt ra khỏi
con trỏ. Tạm dừng là tương tác bắt buộc duy nhất của dải.

**Vì sao bấm vào một mã lại quan trọng:** dải không phải đồ trang trí — bấm
mã sẽ **đặt symbol** mà mọi trang khác đọc. Đó là thứ biến dải từ "màn hình
hiển thị" thành "công cụ điều khiển".

**Không có gì ở đây là bịa:** mọi giá và biến động đến từ
`GET /api/v1/stocks/tape`, đọc đúng đường Gold → Silver → Bronze như mọi
endpoint khác. Mã không có dữ liệu trong lakehouse thì **bị bỏ khỏi dải**, không
được hiện là `0.00` — mã vắng mặt thì thành thật, mã giá 0 thì là nói dối.

**Đo ngày 10/11/2026:** endpoint trả về đủ 12/12 mã, tất cả `source_layer=gold`:

```
AAPL 350.99 +2.52%   MSFT 530.61 -0.99%   NVDA 186.64 +2.78%   TSLA 358.22 +4.23%
AMZN 259.30 -0.35%   GOOGL 284.78 +0.78%  META 610.15 +0.84%
FPT  51 000 -3.59% ₫  VCB 53 500 -1.29% ₫  VHM 62 300 -1.58% ₫
HPG  21 200 -1.40% ₫  MWG 73 900 -1.47% ₫
```

## 10.8. Chi tiết: trang Dữ liệu thị trường — bàn làm việc dữ liệu

### 10.8.1. Hiểu đơn giản

Trang `/market` **không phải** là bản sao của Dashboard. Hai trang làm hai việc
khác nhau:

| Trang | Câu hỏi trả lời | Nội dung |
|---|---|---|
| Dashboard (`/`) | "Mã của tôi đang thế nào?" | 1 mã · tóm tắt · nến gần đây · model · backtest |
| Dữ liệu thị trường (`/market`) | "Kho dữ liệu này chứa gì, và các mã này so với nhau ra sao?" | Hồ sơ thống kê · so sánh nhiều mã · toàn bộ bảng phiên |

Bốn thứ **chỉ có** ở trang Dữ liệu thị trường:

1. **Cửa sổ thời gian + độ mịn nến.** Dashboard mặc định 3 tháng / tuần.
   Ở đây toàn bộ lịch sử lưu trữ đều mở được (`1T/3T/6T/1N/Tất cả` × `1D/1W/1M`).
2. **Hồ sơ thống kê** do backend tính từ các phiên đã lưu: biến động năm,
   sụt giảm tối đa, phiên tăng/giảm, khối lượng bình quân.
3. **So sánh nhiều mã** trên cùng thang giá (rebase 100) — tối đa 5 mã.
4. **Bảng phiên giao dịch đầy đủ** theo khoảng đang chọn, kèm xuất CSV.

### 10.8.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Rebase 100** | Đặt giá đầu khoảng = 100, mọi giá sau đó tính theo tỉ lệ. Dùng để so sánh 2 mã khác đơn vị (AAPL 340 USD vs FPT 51 000 ₫) trên cùng trục |
| **Volatility (biến động)** | Độ lệch chuẩn của lợi suất log ngày × √252 — biến động năm |
| **Max drawdown** | Đợt giảm sâu nhất từ đỉnh xuống đáy trong khoảng (luôn ≤ 0) |
| **Up/Down days** | Số phiên đóng cửa cao hơn / thấp hơn phiên trước |
| **Session (phiên)** | Một ngày giao dịch = một dòng OHLCV trong Bronze/Silver/Gold |

### 10.8.3. Chi tiết: vì sao cần `rebase`

AAPL giao quanh 340 USD, FPT quanh 51 000 ₫. Vẽ giá gốc của cả hai lên
cùng một trục Y thì FPT nằm sát đáy và AAPL nằm sát trần — biểu đồ vô nghĩa.

Nên backend **rebase từng mã về 100** tại phiên đầu tiên của khoảng:

```
rebased = close_t / close_đầu_khoảng × 100
```

Khi đó "đường nào nằm trên" = "mã nào tăng nhiều hơn trong khoảng". Con số
này là **phép tính trên giá đã lưu**, không phải số bịa.

Điểm cần nói rõ: các mã giao dịch ở sàn khác nhau (HOSE, HNX, NASDAQ,
NYSE) có **ngày giao dịch khác nhau** — mã Mỹ không nghỉ lễ Tết, mã Việt
không nghỉ Thanksgiving. Frontend vì vậy gộp các series trên **trục thời gian
union** và **giữ nguyên giá cũ nhất** cho ngày mà mã đó không giao dịch. Đó
chính xác là nghĩa của "giá vẫn là X vào ngày đó".

### 10.8.4. Chi tiết: hai endpoint mới

| Endpoint | Query | Trả về |
|---|---|---|
| `GET /api/v1/stocks/stats/{symbol}` | `days` | Tổng lợi nhuận, biến động năm, max drawdown, cao/thấp, KL bình quân, phiên tăng/giảm, tổng KL — **tất cả tính từ các phiên đã lưu** |
| `GET /api/v1/stocks/compare` | `symbols`, `days` | Danh sách series đã rebase + lợi nhuận khoảng, sắp xếp giảm dần |

**Đo ngày 10/11/2026** (backend thật, đọc MinIO qua WSL relay `127.0.0.1:19000`):

```
GET /api/v1/stocks/stats/AAPL?days=252
  → sessions=176, total_return=+32.59%, volatility=26.13%, max_drawdown=-12.71%
    up_days=93, down_days=82, avg_volume=47 926 595.97

GET /api/v1/stocks/compare?symbols=AAPL,MSFT,FPT,VCB&days=180
  → anchor=2026-11-09, MSFT +29.60% · AAPL +17.70% · VCB -12.30% · FPT -24.09%
```

Mã không có dữ liệu trong lakehouse bị **bỏ khỏi kết quả so sánh**, không
được điền 0 — mã vắng mặt thì thành thật.

### 10.8.5. Lỗi đã gặp và cách sửa

**Triệu chứng:** trang trắng, hiện `Rendered more hooks than during the
previous render`.

**Vì sao xảy ra:** ba `useMemo` (cắt khoảng thời gian, gộp nến, gộp series
so sánh) được đặt **sau** `if (query.isLoading) return <Loading />`. Render
lúc loading gọi ít hook hơn render lúc có dữ liệu → React ném lỗi.

**Fix:** mọi `useMemo` dẫn xuất được khai báo **trước** mọi câu `return`
sớm. Cùng nguyên tắc đã ghi ở `Dashboard.tsx`.

**Bằng chứng:** `npx tsc --noEmit` sạch 0 lỗi; `npx vite build` thành công;
kiểm tra trực tiếp trên trình duyệt — trang `/market` hiển thị đủ 5 khối
(Nến, Hồ sơ thống kê, So sánh, Bảng phiên, Chọn mã), 3 đường so sánh, 260
nến, và bảng phiên đầy đủ.

## 10.9. Chi tiết: lịch sử chat kiểu Gemini + thanh điều hướng

### 10.9.1. Hiểu đơn giản

Trang AI Agent giờ làm những việc mà một ứng dụng chat thật làm:

| Việc | Cách thực hiện | Dữ liệu ở đâu |
|---|---|---|
| **Chat mới** | Nút "Chat mới" — mở cuộc trò chuyện trống, cuộc cũ vẫn nằm trong lịch sử | `localStorage` (session id) |
| **Lịch sử chat** | Cột bên trái liệt kê các cuộc trò chuyện đã lưu, mới nhất trên cùng | MySQL `agent_conversations` |
| **Mở lại** | Bấm vào tiêu đề một cuộc trò chuyện — toàn bộ lượt hỏi đáp được tải lại | MySQL |
| **Xoá chat** | Nút thùng rác trên mỗi dòng — xoá vĩnh viễn khỏi MySQL | MySQL |
| **Tiêu đề thật** | Tiêu đề là **câu hỏi đầu tiên** người dùng gõ, cắt ngắn — không phải "Chat 1" | Lấy từ `user_message` |

**Điểm quan trọng:** backend vốn đã lưu mọi lượt hỏi đáp vào MySQL từ trước
(`AgentService.chat` gọi `ConversationRepository.create`). Trước đây phần
này chỉ ghi chứ không đọc — người dùng đóng tab là mất. Nay có
`GET /agent/sessions` để đọc lại và `DELETE /agent/sessions/{id}` để xoá.

### 10.9.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Session id** | Mã định danh một cuộc trò chuyện (UUID), lưu ở `localStorage` |
| **Stored turn** | Một *lượt* trong DB = 1 câu hỏi + 1 câu trả lời (+ tool đã gọi) |
| **Chat session** | Nhóm các stored turn cùng `session_id` |
| **Relative time** | "17 giờ trước" — thời gian tương đối, dùng cho danh sách lịch sử |

### 10.9.3. Chi tiết: vì sao bỏ badge "SYMBOL · AAPL"

Badge cũ lặp lại thông tin đã có sẵn ở thanh header phía trên (ô chọn mã),
và làm giao diện **trông như** chat bị gắn cứng vào một mã — trong khi agent
tự suy ra mã khi header chưa chọn. Bỏ đi là đúng: thứ đã hiển thị ở trên thì
không cần hiển thị lại.

### 10.9.4. Chi tiết: vì sao thanh điều hướng đổi thành nút

Trước đây 8 mục là **link gạch chân**. Vấn đề:

- Vùng bấm chỉ cao bằng chiều cao chữ (~20px) — khó bấm.
- Mục đang active chỉ khác nhau bởi một gạch chân 2px — phải nhìn kỹ mới
  thấy mục nào đang mở.
- Cả hàng bám sát mép trái, nên 2 mục cuối rơi ra khỏi trung tâm thị giác
  của màn 1600px.

Sau khi đổi:

- Mỗi mục là một **nút** viền hairline, bo góc 6px, **cao 44px** (đạt chuẩn
  vùng bấm tối thiểu).
- Mục đang active nền **primary** (xanh thương hiệu) — nhìn là biết.
- Hàng được **căn giữa**: khoảng trống trái = phải (đo được 369px = 369px).

### 10.9.5. Lỗi đã gặp và cách sửa

**Triệu chứng 1:** `GET /api/v1/agent/sessions` trả **500**.

**Vì sao xảy ra:** `conversation_repository.py` dùng `func.min(...)` /
`func.max(...)` / `func.count(...)` để gom nhóm theo session, nhưng chưa
`import func` từ SQLAlchemy → `NameError: name 'func' is not defined`.

**Fix:** thêm `func` vào dòng import `from sqlalchemy import delete, func, select`.

**Triệu chứng 2:** endpoint vẫn 500 sau khi sửa import.

**Vì sao xảy ra:** MySQL và relay cổng đã dừng (sau khi máy bị tắt), nên
`check_database_connection()` trả `False`. Code đã có đường lùi đúng — trả
mảng rỗng thay vì lỗi — nhưng MySQL phải được bật lại thì mới kiểm chứng
được phần đọc/xoá thật.

**Fix:** bật hạ tầng thật theo đúng quy trình (không dựng bản giả):

```
wsl -d Ubuntu-24.04 -u root -e bash -c \
  "cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose up -d mysql minio"
cd /mnt/d/School/kltn/stock-lakehouse-ai && nohup python3 backend/scripts/relay_ports.py \
  13307:3307 19000:9000 19092:9092 > /tmp/relay.log 2>&1 &
```

**Bằng chứng (Đo ngày 10/11/2026):**

```
GET  /api/v1/agent/sessions            → 200, 100 cuộc trò chuyện
DELETE /api/v1/agent/sessions/test-conv-2 → {"deleted": 13}
GET  /api/v1/agent/sessions (lại)      → cuộc vừa xoá không còn trong danh sách
```

Kiểm tra trực tiếp trên trình duyệt: lịch sử hiển thị 100 mục với tiêu đề
thật ("xin chào thầy cô", "có nên đầu tư vào appl"), số lượt và thời gian
tương đối; bấm một mục tải lại 24 bóng chat (12 lượt); bấm thùng rác xoá
được và danh sách cập nhật ngay.

## 10.10. Chi tiết: bảng component

```
components/
  charts/    CandlestickChart  EquityCurve  ForecastChart  IndicatorChart  PriceChart
  common/    Explainer  EmptyState  ErrorBoundary  ErrorState  Loading
             PageTitle  TimeRangeSelector  BarIntervalSelector
  dashboard/ LakehouseFlow  LiveWatchlist  MarketCard  MetricCard  RecentActivity
  layout/    Header  MainLayout  NavBar
  agent/     ChatBox  ChatMessage  Markdown  ToolCallDisplay
  ui/        badge  button  card  checkbox  input  select  skeleton  switch
```

---

# PHẦN 11 — MỐI LIÊN KẾT FRONTEND ↔ BACKEND

## 11.1. Hiểu đơn giản

Mọi thứ frontend hiển thị đều đi qua **3 bước giống nhau**:

```
1. BẠN BẤM NÚT
        ↓
2. FRONTEND GỌI API  ──────►  BACKEND ĐỌC LAKEHOUSE + TÍNH TOÁN
        ↑                              (MinIO, MySQL)
        └──────────── JSON ────────────┘
        ↓
3. FRONTEND VẼ LẠI KẾT QUẢ
```

**Điểm quan trọng:** bước 2 luôn là **"đọc dữ liệu thật + tính toán thật"**, không có dữ liệu mẫu, không có số bịa ở giữa.

## 11.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **GET / POST** | GET = xem, POST = gửi lệnh (train, chạy backtest) |
| **Query parameter** | Tham số đi kèm trên đường dẫn, vd `?symbol=AAPL` |
| **Payload** | Body của request |
| **Round-trip** | Vòng đi-về giữa client và server |
| **Null** | Trong JSON = "không có giá trị" (dùng cho phiên chưa xảy ra) |

## 11.3. Chi tiết: bảng API

| Endpoint | Method | Dùng bởi | Mục đích |
|---|---|---|---|
| `/api/v1/health` | GET | SystemStatus | Sống hay chết |
| `/api/v1/system/status` | GET | SystemStatus, Dashboard | Trạng thái 7 dịch vụ + layer counts |
| `/api/v1/stocks/symbols` | GET | Header | Danh sách 1.037 mã |
| `/api/v1/stocks/tape` | GET | NavBar | Băng giá 12 mã, 1 request |
| `/api/v1/stocks/compare` | GET | MarketData | So sánh nhiều mã trên cùng thang giá (rebase 100) |
| `/api/v1/stocks/stats/{symbol}` | GET | MarketData | Hồ sơ thống kê: biến động, drawdown, phiên tăng/giảm |
| `/api/v1/stocks/{symbol}/latest` | GET | Dashboard | Giá mới nhất |
| `/api/v1/market/indices` | GET | Dashboard | Chỉ số thị trường |
| `/api/v1/indicators/{symbol}/indicators` | GET | TechnicalAnalysis | Chỉ báo |
| `/api/v1/forecast/train` | POST | Forecasting | Train model |
| `/api/v1/forecast/predict` | POST | Forecasting | Dự báo đa bước |
| `/api/v1/forecast/compare/{symbol}` | GET | Forecasting | Bảng so sánh model |
| `/api/v1/forecast/published/{symbol}` | GET | Forecasting | Dự báo **đã công bố**, một dòng mỗi mô hình, cùng phiên |
| `/api/v1/forecast/accuracy` | GET | MarketData | Sổ kiểm chứng dự báo đã công bố (ngoài tập huấn luyện) |
| `/api/v1/backtests/run` | POST | Backtesting | Chạy backtest |
| `/api/v1/backtests/history` | GET | Backtesting | Lịch sử |
| `/api/v1/pipeline/run` | POST | Admin | Chạy pipeline |
| `/api/v1/pipeline/layers/{symbol}` | GET | Dashboard | Số record mỗi tầng |
| `/api/v1/agent/chat` | POST | AIAgent | Chat |
| `/api/v1/agent/history/{sid}` | GET | AIAgent | Lịch sử một cuộc trò chuyện |
| `/api/v1/agent/sessions` | GET | AIAgent | Danh sách cuộc trò chuyện đã lưu |
| `/api/v1/agent/sessions/{sid}` | DELETE | AIAgent | Xoá một cuộc trò chuyện |
| `/api/v1/agent/messages/{id}` | DELETE | AIAgent | Xoá một lượt hỏi đáp |

## 11.4. Chi tiết: luồng "Train và Dự báo" (click một nút)

```
[Browser] Forecasting.tsx — nút "Train và Dự báo"
    │
    ├─► useForecast.train.mutate({symbol, model_name})
    │       └─► api.post("/forecast/train")
    │             └─► [Backend] forecasting.py → train_model()
    │                   ├─ set_global_seed(42)
    │                   ├─ GoldLayer().read(symbol)        ← MinIO, ~121 partition
    │                   ├─ _prepare_supervised()             ← drop NaN warmup + target
    │                   ├─ chronological_split(70/15/15)     ← KHÔNG xáo trộn
    │                   ├─ model.fit(train, validation)
    │                   ├─ model.evaluate(test)              ← MAE/RMSE/MAPE/DA
    │                   ├─ save_registry_record()            ← MinIO + MySQL
    │                   └─ return {metrics, predictions, ...}
    │
    ├─► useForecast.predict.mutate(horizon)
    │       └─► api.post("/forecast/predict")
    │             └─► [Backend] predictor.py → multistep.py
    │                   ├─ load model từ registry
    │                   ├─ recursive roll-forward H bước
    │                   └─ return {predictions: [...actual+predicted...], forecast: [...actual=null...]}
    │
    └─► [React] setState → <ForecastChart data={...} />
          ├─ series "actual"    ← đã xảy ra
          ├─ series "predicted" ← hold-out
          └─ series "forecast"  ← tương lai (actual = null)
```

## 11.5. Chi tiết: luồng "Chạy backtest"

```
[Browser] Backtesting.tsx — nút "Chạy backtest"
    └─► useBacktest.run.mutate({symbol, strategy, ...params})
        └─► api.post("/backtests/run")
            └─► [Backend] backtesting.py
                ├─ BacktestEngine.run()
                    │   ├─ _load_ohlcv(symbol)        ← Gold → Silver → Bronze, cache 900s
                    │   ├─ strategy.generate_signals(frame)
                    │   ├─ execution_signal = signals.shift(1)     ← KHÔNG look-ahead
                    │   ├─ simulate(frame, signal, capital, fee, slippage)
                │   │   ├─ Portfolio.buy/sell  (có fee + slippage + tolerance 1e-9)
                │   │   ├─ mark_to_market mỗi bar
                │   │   └─ force-close + sửa equity điểm cuối
                    │   └─ compute_metrics(equity, trades, capital)
                ├─ BacktestRepository.create(...)   ← MySQL backtest_runs
                └─ return {metrics, equity_curve, drawdown, trades, markers, disclaimer}
```

## 11.6. Chi tiết: luồng AI Agent + walk-forward

```
[Browser] AIAgent.tsx — user hỏi "kiểm tra chiến lược MA trên AAPL có ăn không?"
    └─► api.post("/agent/chat")
        └─► [Backend] agent_service → agent.py
            ├─ LLM (Gemini) phân tích → quyết định gọi tool
            ├─ tool: run_walk_forward(symbol="AAPL", strategy="ma_crossover")
            │   └─► WalkForwardService.run()
            │       └─► heavy_worker.run_in_process(..., pool_name="interactive")
            │           └─► [PROCESS CON RIÊNG] WalkForwardValidator.run()
            │               ├─ 159 cửa sổ trượt
            │               ├─ warmup context cho indicator
            │               └─ summary: consistency, overfitting_ratio, ...
            ├─ cắt tỉa windows (giữ 12 đầu + 12 cuối)
            ├─ LLM viết câu trả lời dựa trên số liệu TẤT ĐỊNH
            └─ return {answer, tool_trace, conversation_id}
```

**Điểm mấu chốt:** con số trong câu trả lời của LLM **không do LLM sinh ra** — nó đến từ tool gọi vào backend. Đây là điều phân biệt "agent demo" với "hệ thống nghiên cứu".

## 11.7. Chi tiết: đồng bộ dữ liệu MinIO ↔ Web

**Yêu cầu bất biến của đồ án:** dữ liệu trên web **phải khớp** dữ liệu trong MinIO.

Cơ chế bảo đảm:

1. **Một nguồn sự thật duy nhất** — mọi số liệu UI đều đọc từ `MarketService` → Gold/Silver/Bronze trong MinIO. Không có đường nào khác.
2. **Cache có invalidation theo symbol** — `auto_refresh` gọi `invalidate_symbol_cache(symbol)` ngay sau khi ghi ⇒ web thấy dữ liệu mới ngay.
3. **Cache có TTL** — 900s, nên dù có bỏ sót invalidation, dữ liệu vẫn tự lành.
4. **Script kiểm chứng độc lập:**
   - `backend/scripts/check_layer_divergence.py` — so sánh record count giữa các tầng.
   - `backend/scripts/check_unserved_symbols.py` — mã có trong MinIO nhưng API không phục vụ được.
   - `backend/tests/verify_real_data.py` — đối chiếu dữ liệu với nguồn ngoài.
5. **Không có dữ liệu giả ở bất kỳ đâu** — `market_service` không có fallback mẫu.

---

# PHẦN 12 — BẢNG QUYẾT ĐỊNH THIẾT KẾ (DEFENSE KIT)

> **Đây là bảng quan trọng nhất khi thầy hỏi "tại sao làm vậy?".** Mỗi dòng đều có **lý do** + **số đo đi kèm**. Không có dòng nào trả lời bằng "vì thông thường người ta làm vậy".

| # | Quyết định | Lý do (đời thường) | Bằng chứng |
|---|---|---|---|
| 1 | **Không xáo trộn chuỗi thời gian** | Xáo trộn = cho xem đáp án rồi đi thi | `chronological_split()` chỉ cắt theo index trên frame đã sort |
| 2 | **Thực thi ở bar kế tiếp** (`shift(1)`) | Không được biết giá ngày mai lúc quyết định hôm nay | `execution_signal = signals.shift(1)` |
| 3 | **Warmup context cho walk-forward** | Cần 50 phiên để tính SMA50, mà cửa sổ test chỉ 21 phiên | 0 → 41 giao dịch; 17 failed → 0 |
| 4 | **Cửa sổ train cố định + annualize** | So sánh 6 tháng với 1 tháng thì tỷ lệ vô nghĩa | ratio 790 (vô nghĩa) → 4.0 |
| 5 | **LSTM dự đoán tỷ lố, không phải giá** | Dạy trên giá 26–196 rồi hỏi giá 345 thì mạng không dám đoán | MAE 50.48 → 4.24; MAPE 15.6% → 1.33% |
| 6 | **Scaler fit/transform tách biệt** | Tính lại scaler trên validation = để validation thấm vào train | `_fit_targets` vs `_transform_targets` |
| 7 | **DA so với phiên liền trước** | "Tăng hay giảm" phải so với hôm qua, không phải với chính nó | DA 0% → 50.79% |
| 8 | **Trừ phí mua trong PnL** | Tổng lãi phải bằng vốn cuối − vốn đầu | chênh 120.32 → khớp tuyệt đối |
| 9 | **Tolerance 1e-9 khi so tiền mặt** | Sai số 1.8e-12 đủ để chặn nhầm lệnh hợp lệ | 1 giao dịch → 29 giao dịch |
| 10 | **Sửa equity điểm cuối khi force-close** | Vốn cuối phải khớp sổ sách đã phẳng | chênh 12.63 → khớp |
| 11 | **Bronze append-only, có lineage** | Khôi phục được feature khi thuật toán đổi | `_lineage.json` mỗi mã |
| 12 | **Đếm record bị loại, không drop âm thầm** | Không biết mình đã mất dữ liệu hay chưa | `_quality.json` |
| 13 | **Prefix partition kết thúc bằng `/`** | `symbol=M` khớp `symbol=MCD/` → trộn 51 mã | 5.801 partition bị đọc nhầm → 1 |
| 14 | **Hai mốc tham chiếu cho plausibility** | Đáy vs trung vị trả lời hai câu hỏi khác nhau | PARA 10:1 split — bar hợp lệ bị từ chối → được chấp nhận |
| 15 | **Circuit breaker không tính lỗi 404** | 404 là lỗi *mã*, không phải lỗi *provider* | 1 mã 404 không vô hiệu hoá provider khoẻ |
| 16 | **Request Gate ưu tiên người dùng** | Refresh không quan trọng bằng việc UI phải nhanh | NVDA read 0.4s → 89.9s (không có gate) |
| 17 | **Process pool cho việc nặng** | Thread dùng chung GIL nên tranh nhau CPU | walk-forward 96s → 2s |
| 18 | **2 pool tách biệt** | Refresh không được xếp trước request người dùng | `interactive=2`, `background=4` |
| 19 | **Giới hạn worker theo RAM thật** | Host không pagefile ⇒ bị OOM-kill giữa chừng | 700MB/worker, reserve 4096MB |
| 20 | **Pool chết được dựng lại** | `ProcessPoolExecutor` hỏng vĩnh viễn | retry 1 lần trên pool mới |
| 21 | **Cache LRU 256 + TTL 900s** | Cache 24 gây LRU-thrash khi duyệt ~950 mã | 81.1s → nhanh; ~3MB/mã |
| 22 | **Ghi partition song song** | Ghi tuần tự tốn 2.87s/mã | wall-clock cắt mạnh |
| 23 | **Đếm layer object trong subprocess** | 340k key giữ GIL ~19s ⇒ mọi endpoint xếp hàng | `/system/status` không block |
| 24 | **Không bao giờ block khi cache lạnh** | Trang System Status bị timeout 90s | trả 0 + refresh nền |
| 25 | **Target luôn shift(-1)** | Đáp án ở tương lai là đúng; đầu vào ở tương lai là sai | `target_close_next = close.shift(-1)` |
| 26 | **Feature engineering idempotent** | Silver có thể đã chứa feature cũ | strip về 12 cột gốc |
| 27 | **Multi-step đệ quy** | Ô "horizon" không làm gì với model một-bước | `multistep.py` |
| 28 | **3 series riêng trên chart** | Vẽ dự báo chung với lịch sử = tuyên bố không có cơ sở | `actual` / `predicted` / `forecast` |
| 29 | **`queryKey` chứa `symbol`** | Cache cũ khi đổi mã | `["forecast-compare", symbol]` |
| 30 | **Phân biệt timeout vs offline** | Timeout ≠ mất kết nối | 3 nhánh xử lý lỗi |
| 31 | **Cắt tỉa tool result cho LLM** | 53KB blob → token + throttle | giữ 12 đầu + 12 cuối |
| 32 | **Ngân sách LLM 45s** | 4 vòng × 35s = 140s > deadline 75s | `LLM_TOTAL_BUDGET_SECONDS` |
| 33 | **RSI strategy dùng numpy** | 2.0s trong 4.5s nằm trong hàm này | bit-identical signals |
| 34 | **LSTM lazy-load** | Import torch trên Windows có thể lỗi DLL | `_lazy_load_lstm()` |
| 35 | **Không có dữ liệu giả** | Giá trị nghiên cứu = dữ liệu thật | `NotFoundError` thay vì fallback |
| 36 | **Walk-forward disclaimer** | Trách nhiệm đạo đức với đồ án tài chính | `_build_disclaimer()` |
| 37 | **Đường cơ sở mua & giữ trong một module** | Engine và validator phải tính baseline giống hệt nhau | `backtesting/benchmark.py` |
| 38 | **Baseline đo theo từng cửa sổ** | So sánh cặp, không phải hiệu hai trung bình độc lập | 3.687 cửa sổ, 101 mã |
| 39 | **Báo cáo đa mã chạy ngoài, API đọc file** | Phép đo mất ~2 phút; tính lại mỗi lần mở web sẽ timeout | `scripts/run_multi_symbol_walkforward.py` |

---

# PHẦN 13 — CHỐNG NHÌN THẤY TƯƠNG LAI (LOOK-AHEAD BIAS)

> Sơ đồ: [13. Chống rò rỉ dữ liệu — bức tường 3 lớp](./SO_DO_MINH_HOA.md#13)

> **Đây là phần thầy hay hỏi nhất.** Dưới đây là bảng truy vết đầy đủ.

## 13.1. Hiểu đơn giản

**Nhìn thấy tương lai** = dùng thông tin **chưa xảy ra** để ra quyết định.

Hai chỗ dễ mắc:

1. **Trong dự báo**: tính chỉ báo của ngày hôm nay nhưng lấy giá của ngày mai (vì `sma(close, 20)` vô tình xoay vòng về index tương lai).
2. **Trong backtest**: tín hiệu hôm nay nhưng khớp lệnh vào **giá đóng cửa hôm nay** — tức là "biết xong rồi mới quyết định".

Hệ thống này chặn cả hai, và mỗi biện pháp đều có **test tương ứng**.

## 13.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Look-ahead bias** | Dùng dữ liệu tương lai để dự đoán quá khứ |
| **Data leakage** | Thông tin từ tập đánh giá lọt vào quá trình huấn luyện |
| **In-sample / Out-of-sample** | Trong mẫu (đã thấy) / ngoài mẫu (chưa thấy) |
| **Survivorship bias** | Chỉ còn lại những mã còn tồn tại tới nay |
| **Rolling-origin evaluation** | Đánh giá bằng cách lăn điểm gốc theo thời gian |

## 13.3. Chi tiết: trong dự báo (Forecasting)

| Nguồn rò rỉ | Cách chặn | File |
|---|---|---|
| Target dùng tương lai làm feature | Target luôn `shift(-1)`; feature chỉ dùng `shift` không dương | `features/target_features.py` |
| Xáo trộn train/test | `chronological_split` chỉ cắt theo thời gian | `forecasting/preprocessing.py` |
| Scaler thấy cả validation | `_fit_targets` (train) vs `_transform_targets` (val) | `forecasting/lstm.py` |
| Model thấy test | Test chỉ dùng cho `evaluate()`, không dùng cho fit | `forecasting/trainer.py` |
| Early stopping dùng test | Dùng **validation** để early-stop | `LSTMForecastModel.fit(..., X_val, y_val, ...)` |
| ARIMA chiếu nhiều bước một lần | One-step rolling, `append(actual, refit=False)` | `forecasting/arima.py` |
| Đánh giá trên tập đã train | Metrics tính trên `split.test` | `forecasting/trainer.py` |

## 13.4. Chi tiết: trong backtest

| Nguồn rò rỉ | Cách chặn | File |
|---|---|---|
| Lệnh khớp ở bar đã biết giá | `signals.shift(1)` → thực thi ở bar kế tiếp | `backtesting/engine.py` |
| Indicator thiếu lịch sử ở đầu cửa sổ | Warmup context từ đuôi train window | `backtesting/walk_forward.py` |
| Đánh giá trên dữ liệu đã train | Test window tách biệt, không dùng để chọn tham số | `backtesting/walk_forward.py` |
| Chọn tham số trên test | Tham số chọn trên **train** window | `backtesting/walk_forward.py` |
| Equity chấm trên bar chưa đóng | Mark-to-market tại close của từng bar đã qua | `backtesting/simulator.py` |

## 13.5. Chi tiết: chứng minh bằng kiểm thử

`backend/tests/test_backtest_walk_forward.py` có test tên *"the test window alone cannot trade"* — chứng minh ngược lại rằng nếu thiếu warmup thì chiến lược mù (0 giao dịch). Điều này **xác nhận cơ chế warmup là thứ duy nhất làm cho backtest hoạt động**, chứ không phải một thứ tự ngẫu nhiên.

---

# PHẦN 14 — HIỆU NĂNG & KIỂM THỬ

## 14.1. Hiểu đơn giản

Hệ thống có **106 bài kiểm thử tự động** — giống như bài kiểm tra sức khoẻ định kỳ. Mỗi bài kiểm tra một điều gì đó **không được sai**, ví dụ:

- "Tổng lãi các giao dịch phải bằng đúng vốn cuối − vốn đầu."
- "Đổi mã thì biểu đồ phải đổi theo."
- "Cửa sổ kiểm tra đơn lẻ không được phép giao dịch (chứng minh warmup là cần thiết)."

**Vì sao quan trọng khi bảo vệ:** vì mỗi lần sửa một bug đều kèm **test hồi quy** — test sẽ đỏ nếu bug quay lại. Đó là cách bạn chứng minh "đồ án này nghiêm túc, không chỉ chạy được một lần".

## 14.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Test / Regression test** | Bài kiểm tra tự động |
| **Fixture** | Dữ liệu mẫu cố định dùng cho test |
| **Monkeypatch** | Tạm thay thế hàm để test trong điều kiện giả lập |
| **Invariant** | Bất biến — điều luôn đúng, dùng để kiểm chứng |
| **Golden test** | So sánh output với kết quả "đúng" đã lưu sẵn |

## 14.3. Chi tiết: bộ kiểm thử

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

**Kết quả: 561/561 PASS** (đo ngày 16/11/2026, `pytest tests --junitxml` cho 561 test, 0 failure, 0 error, 0 skipped).

> **Ghi chú về số test:** `test_no_missing_imports.py` sinh **một test cho mỗi file `.py`** trong `backend/`. Vì vậy con số này **thay đổi theo số file Python trong repo** — thêm một module mới là thêm một test. Lần đo này: 285 file `.py` trong `backend/` → 285 test của riêng file đó.

| File | Số test | Phủ |
|---|---|---|
| `test_no_missing_imports.py` | 285 | Quét AST: không module nào dùng tên stdlib mà chưa import |
| `test_forming_bar.py` | 17 | Phát hiện bar ngày bị đóng băng giữa phiên (quan hệ bao hình) |
| `test_scale_repair.py` | 14 | Dò nhảy cục bộ + độ rộng toàn cục của điểm gãy thang giá |
| `test_forecast_plausibility.py` | 13 | Chặn giá dự báo không tồn tại ở đường ghi |
| `test_backtest_accounting.py` | 10 | Khớp PnL, trừ phí, tolerance rebuy, drawdown không dương |
| `test_source_agreement_exclusions.py` | 8 | Không đổ lỗi provider cho ảnh chụp giữa phiên |
| `test_backtest_walk_forward.py` | 6 | Warmup, cửa sổ train cố định, 0 failed window, ratio đọc được |
| `test_backtest_benchmark.py` | 6 | Đường cơ sở: cùng phiên, cùng phí, tái lập được, baseline từng cửa sổ |
| `test_forecasting_lstm.py` | 6 | Scaling tương đối, equivariance giá, không leak validation |
| `test_forecasting_arima.py` | 3 | DA khác 0, DA so với phiên trước, walk-forward một bước |
| `test_forecast_chart.py` | — | Logic chart FE |
| `test_backtesting.py` | — | Engine, simulator, metrics |
| `test_forecasting.py` | — | LR, registry, predictor |
| `test_features.py` / `test_indicators.py` | — | Feature & chỉ báo |
| `test_silver_validation.py` / `test_dedupe.py` | — | Làm sạch, dedup |
| `test_plausibility.py` | — | Màn lưới giá |
| `test_yahoo_http_boundary.py` | — | Biên lịch sử provider |
| `test_restatement_propagation.py` | — | Lan truyền restatement (split) |
| `test_session.py` / `test_time_utils.py` | — | Chuẩn hoá phiên, múi giờ |
| `test_health.py` / `test_currency_consistency.py` / `test_refresh_watermark.py` | — | API, tiền tệ, watermark |

## 14.4. Chi tiết: số đo hiệu năng (đo thật)

| Tác vụ | Thời gian |
|---|---|
| Backtest AAPL 10 năm (MA Crossover) | ~3.5 s |
| Walk-forward AAPL 159 cửa sổ | **~2 s** (trước fix: 96 s) |
| Walk-forward đa mã, 101 mã / 13 sàn / 3.687 cửa sổ | **~2 phút** (chạy ngoài, ghi file) |
| Train LSTM AAPL | ~15-25 s (CPU) |
| Train ARIMA AAPL | ~12 s |
| Train Linear Regression AAPL | ~2 s |
| Đọc 1 mã từ MinIO (cache hit) | <0.1 s |
| Đọc 1 mã từ MinIO (cache miss) | ~0.4-3.3 s (121 partition) |

## 14.5. Chi tiết: ngân sách thời gian (timeouts)

```
axios client            90 s   (cao hơn server để message server thắng)
agent server deadline   75 s
LLM per-call            35 s
LLM total budget        45 s
gemini timeout          25 s
```

## 14.6. Chi tiết: gỡ toàn bộ đường dẫn realtime (đo ngày 11/11/2026)

### 14.6.1. Hiểu đơn giản

Trước ngày 11/11/2026, hệ thống có một đường dẫn **realtime** song song với đường
dẫn batch: một bộ nhớ đệm trong RAM nhận bar từ client WebSocket (Finnhub cho
US, SSI iBoard cho Việt Nam), rồi đẩy xuống trình duyệt bằng SSE. Trang web
`/stream` hiển thị bộ nhớ đệm đó.

Ngày 11/11/2026, đường dẫn này bị **xoá hẳn**. Lý do đo được, không phải cảm
tính:

| Việc đo được | Kết quả |
|---|---|
| Số mã trong bộ nhớ đệm | **0** |
| Số bar đã ghi | **0** |
| Số route chứa `stream` sau khi gỡ | **0** (tổng 77 route) |

Bộ nhớ đệm luôn rỗng vì không còn gì đẩy bar vào nó. Trang `/stream` vì thế chỉ
hiển thị một ô trống — một màn hình trống trong sản phẩm, và người đọc tài liệu
đồ án sẽ phải tự hỏi "chỗ này có dữ liệu thật không?". Xoá bỏ là câu trả lời
trung thực.

Quan trọng hơn: dữ liệu realtime **chưa bao giờ** ghi vào Bronze. Toàn bộ
kiến thức dài hạn của hệ thống đến từ batch cron. Vậy nên việc gỡ realtime
**không mất một bản ghi nào** trong lakehouse.

### 14.6.2. Thuật ngữ

| Thuật ngữ | Nghĩa là gì |
|---|---|
| **Realtime / tick** | Giá giao dịch từng giây hoặc từng phút, đẩy về người dùng ngay khi xảy ra |
| **EOD (End of Day)** | Bar đóng cửa một ngày — thứ duy nhất hệ thống còn giữ |
| **Bộ nhớ đệm trong RAM** | Bộ đệm tròn 240 bar/mã, sống trong tiến trình Python, mất khi tắt server |
| **SSE** | Cơ chế HTTP đẩy dữ liệu một chiều từ server xuống trình duyệt |

### 14.6.3. Chi tiết: những gì đã gỡ

| Nhóm | Xoá gì | Lý do |
|---|---|---|
| API | `backend/app/api/v1/endpoints/stream.py` — 4 endpoint `/api/v1/stream/*` | Không còn nguồn đẩy dữ liệu; trả về số rỗng là gây hiểu nhầm |
| Dịch vụ | `backend/app/services/stream_service.py` — `StreamCache`, pub/sub, `publish_bar` | Bộ nhớ đệm luôn rỗng |
| Client WebSocket | `backend/app/streaming/` — `finnhub_websocket.py`, `vn_websocket.py` | Không được nối vào bất kỳ tiến trình nào sau khi gỡ Kafka |
| Cổng ghi dữ liệu | `POST /api/v1/stream/ingest` | Đây chính là cổng từng đẩy 18 bar gõ tay của AAPL/MSFT/NVDA vào Bronze (đo 04/11/2026) |
| Cấu hình | `allow_stream_ingest`, `finnhub_ws_*`, `vn_ws_*` | Không còn biến nào đọc chúng |
| Giao diện | Trang `/stream`, `frontend/src/api/stream.ts`, component `LiveWatchlist` | Trang trống, không có giá trị nghiên cứu |
| Script điều tra | `probe_ssi_offsets.py`, `pin_down_vn_bugs.py`, `trace_epoch_origin.py`, `prove_ws_symbol_mismatch.py` | Điều tra lỗi parser của một đường dẫn không còn tồn tại |
| Phụ thuộc | `websocket-client>=1.6.0` trong `requirements.txt` | Không còn module nào import |

### 14.6.4. Điều gì ĐƯỢC giữ lại, và vì sao

| Giữ lại | Vì sao |
|---|---|
| `INTRADAY_STREAM_SOURCES` trong `app/lakehouse/plausibility.py` | Bronze vẫn còn dòng cũ mang nhãn `vn_ws` / `finnhub_ws` / `manual`. Guard này loại chúng khỏi mọi lần replay. Xoá tên nguồn trước khi xoá dữ liệu là lập luận ngược |
| `source` cột trong Bronze | Giá trị truy vết — vẫn cần để biết một dòng đến từ đâu |
| Cột `source` trong `plausibility.py` | Kiểm tra giá có khớp tầng đang bật hay không (luật "số đúng nhưng sai nguồn") |

### 14.6.5. Ảnh hưởng tới giao diện

Bảng "Danh sách theo dõi" ở cột phải của Dashboard trước đây đọc
`/api/v1/stream/latest` — tức là bộ nhớ đệm rỗng. Nó giờ đọc
`GET /api/v1/stocks/tape`: **cùng endpoint** với dải giá ở thanh điều hướng,
đọc từ Gold → Silver → Bronze. Mọi giá hiển thị đều là giá đóng cửa đã lưu
trong lakehouse, kèm `source_layer` để truy vết.

### 14.6.6. Bằng chứng

- Backend khởi động OK, **77 route**, không còn route nào chứa `stream` (đo 11/11/2026).
- Bộ kiểm thử backend: **139 test, 100% pass** (đo 11/11/2026).
- Frontend build: `OK built in 8.38s`, 0 lỗi TypeScript (đo 11/11/2026).
- `rg -n "api/v1/stream" backend frontend/src` → 0 kết quả (đo 11/11/2026).

### 14.7. Trạng thái dự báo và backtest (đo ngày 16/11/2026)

#### 14.7.1. Hiểu đơn giản

Hai bộ máy khác nhau đã được chạy thật trên dữ liệu thật:

| Bộ máy | Việc làm | Kết quả |
|---|---|---|
| **Dự báo (forecasting)** | Dự báo giá đóng cửa phiên kế tiếp từ dữ liệu quá khứ, rồi chấm điểm lại bằng giá đóng cửa thật khi phiên đó xảy ra | 45.631 dòng đã chấm điểm, median sai số **1,15%** |
| **Backtest** | Chạy chiến lược trên lịch sử, tính PnL, đối chiếu với chiến lược "mua và giữ" trên **cùng** chuỗi giá | 3.687 cửa sổ rolling, đối chiếu đầy đủ, không rò rỉ tương lai |

Cả hai đều **chạy được trên dữ liệu thật**, không có số bịa.

#### 14.7.2. Dự báo — số đo từ bảng `predictions` (MySQL thật)

Đo trực tiếp bằng SQL trên bảng `predictions` ngày 16/11/2026:

| Chỉ số | Toàn bộ | Chỉ dự báo đã công bố |
|---|---|---|
| Số dòng đã chấm điểm | **45.631** | **1.215** |
| Median sai số tuyệt đối | **1,15%** | 0,96% |
| WAPE | **2,75%** | 3,56% |
| Sai số có dấu trung bình | **+0,43%** | +0,35% |
| MAE | 333,16 (đơn vị giá) | 358,63 |
| **Đúng hướng** | **50,58%** | 45,42% |
| Số phiên | 05/09/2025 → 13/11/2026 | 10/11/2026 → 16/11/2026 |
| Số mã | 968 | — |

Cột "toàn bộ" gồm cả dự báo backfill walk-forward; cột "đã công bố" chỉ gồm dự báo
do hệ thống chạy và lưu như một bản ghi dự báo thật. Hai cột được tách riêng
để không trộn hai nguồn bằng chứng khác nhau.

**Về `DA ≈ 50,6%`:** đây là kết quả trung thực của mô hình hồi quy tuyến tính
một bước trên mức giá. Hệ thống **không** che giấu con số này và cũng **không**
định nghĩa lại nó thành "chính xác cao". Với mô hình dự báo giá, giá trị của hệ
thống nằm ở **sai số tuyệt đối nhỏ** (median 1,15%) chứ không ở việc đoán
được chiều đi thị trường.

#### 14.7.3. Backtest — chạy thật, không rò rỉ tương lai

Chạy trực tiếp trên Gold thật của AAPL (06/10/2016 → 12/11/2026):

| Chiến lược | Lợi nhuận | Số giao dịch | Sharpe | Buy & hold | Vượt benchmark? |
|---|---|---|---|---|---|
| `ma_crossover` | +319,16% | 29 | 0,798 | +1.138,10% | **Không** |
| `rsi_strategy` | +242,89% | 11 | 0,703 | +1.138,10% | **Không** |

Walk-forward AAPL (train 365 ngày / test 90 ngày / bước 90 ngày): **37/37 cửa sổ
chạy thành công, 0 cửa sổ lỗi**, hoàn tất trong ~3,4 s.

Báo cáo đa mã (`GET /api/v1/backtests/multi-symbol-report`, 101 mã / 13 sàn /
3.687 cửa sổ):

| Chỉ số | Chiến lược | Mua và giữ |
|---|---|---|
| Lợi nhuận trung vị | +0,217% | **+2,282%** |
| Sharpe trung vị | **−0,025** | **+0,456** |
| % mã sinh lời | 60,4% | **91,1%** |
| Drawdown trung vị | **−4,56%** | −11,87% |
| % cửa sổ vượt buy & hold | 37,5% | — |
| % mã vượt buy & hold | 8,9% | — |

**Kết luận trung thực:** hai chiến lược hiện có **không đánh bại** chiến lược
mua và giữ. Hệ thống báo cáo đúng điều đó thay vì tô đẹp. Giá trị của phần
backtest là **khung đo lường đúng** — cùng chuỗi giá, cùng phí, cùng quy ước
khớp lệnh ở bar kế tiếp, không rò rỉ tương lai — để một chiến lược tốt hơn
được thêm vào sau này mà không phải viết lại khung.

#### 14.7.4. Các bất biến đã kiểm chứng bằng test

45 test riêng cho phần kế toán backtest và chấm điểm dự báo (đo 16/11/2026:
45 test, 0 failure, 0 error):

| Bất biến | Nơi kiểm chứng |
|---|---|
| Tín hiệu bar \(t\) chỉ khớp lệnh ở bar \(t+1\) | `test_backtest_accounting.py` |
| PnL đã trừ phí cả vào và ra | `test_backtest_accounting.py` |
| Buy & hold dùng **cùng** chuỗi giá và **cùng** cấu trúc phí | `test_backtest_benchmark.py` |
| Baseline tính riêng cho từng cửa sổ walk-forward | `test_backtest_walk_forward.py` |
| Drawdown không dương | `test_backtest_accounting.py` |
| Sai số dự báo chỉ chấm bằng giá đóng cửa **thật** từ Gold | `test_forecast_scoring.py` |
| Giá dự báo bất khả thi bị chặn ở đường ghi | `test_forecast_plausibility.py` |

#### 14.7.5. Bằng chứng chạy thật ngày 16/11/2026

- Bộ kiểm thử backend: **561 test, 0 failure, 0 error, 0 skipped** (356 s).
- Frontend `tsc --noEmit`: **0 lỗi TypeScript**.
- Quét dữ liệu giả: `backend/app` chỉ còn 1 kết quả (`random.uniform` dùng làm
  jitter backoff của LLM retry — không sinh dữ liệu); `frontend/src` chỉ còn 1
  dòng chú thích nói rõ không dùng giá trị giả. **0 dòng dữ liệu giả.**
- API đang phục vụ: `GET /api/v1/forecast/accuracy` → 200 với 45.631 dòng đã
  chấm; `GET /api/v1/backtests/multi-symbol-report` → 200 với 3.687 cửa sổ;
  `GET /api/v1/quality/gate` → 200, verdict `warning`.
- Quality gate (đo 16/11/2026): `layer_agreement` **passed** (61.656 phiên so
  sánh Bronze/Silver/Gold, 0 phân kỳ), `integrity` **passed** (0 vi phạm),
  `source_agreement` **passed** (0 xung đột chưa giải thích).

## 14.8. Dọn dẹp mã nguồn và tối ưu tốc độ (đo ngày 16/11/2026)

### 14.8.1. Hiểu đơn giản

Một dự án chạy nhiều ngày sẽ tích lại rác: file log cũ, kết quả probe thử lỗi,
thư mục rỗng, cache Python. Chúng không làm hỏng hệ thống, nhưng làm **máy chậm
đi** và làm người đọc không biết đâu mới là thứ quan trọng. Ngày 16/11/2026 dự án
được dọn một lần, và đồng thời tìm ra một điểm nghẽn thật sự.

### 14.8.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Rác tích luỹ** | **Stale artifacts** | File cũ không còn ai dùng: log, cache, output của lần probe | Toàn repo |
| **Quét bỏ qua thư mục** | **Directory pruning** | Bỏ qua luôn một thư mục con thay vì vào tìm rồi mới lọc | `test_no_missing_imports.py` |
| **Bản sao cục bộ** | **Local mirror** | Bản sao lakehouse trên đĩa khi chạy ở chế độ `STORAGE_BACKEND=local` | `backend/data/` |
| **Bản đồ mã nguồn** | **Source map** | Tài liệu nói rõ mỗi thư mục/file dùng để làm gì | `docs/BAN_DO_MA_NGUON.md` |

### 14.8.3. Chi tiết kỹ thuật: đã xoá gì

| Nhóm | Trước | Sau | Ghi chú |
|---|---|---|---|
| File log trong `backend/logs/` | 346 file / **41,9 MB** | 5 file / 0,5 MB | Giữ lại `.gitkeep` + 4 file đang được backend ghi |
| File log ở gốc `backend/` | 18 file (~1,6 MB) | 2 file | Giữ `_api.err` đang được uvicorn hiện tại ghi |
| File log ở `backend/data/` | 6 file (~1,3 MB) | 0 | Log cũ nằm nhầm trong thư mục dữ liệu |
| File log ở `frontend/` + gốc repo | 9 file | 0 | Gồm cả `_startall.log` |
| File probe API rác trong `backend/tests/` | 9 file JSON | 0 | Kết quả lỗi API key của Alpha Vantage / Finnhub |
| `frontend/dist/` | 18 file / 0,87 MB | 0 | Kết quả `npm run build`, tạo lại được |
| `__pycache__/`, `.pytest_cache/`, `.sentry-native/` | có | 0 | Cache Python và file tạm Sentry |
| Thư mục rỗng | `backend/data/gold_features/`, `backend/data/quality/` | 0 | Không code nào tham chiếu |
| `scripts/` (gốc repo) | 11 file lộn xộn | 7 file / 2 nhóm | Tách thành `scripts/docs/` và `scripts/system/` |
| `backend/data/` (bản sao local) | **9,03 GB** / 332.600 file | **0,13 GB** / 4.976 file | Chi tiết ở 14.8.7 |

### 14.8.4. Chi tiết kỹ thuật: phát hiện điểm nghẽn thật

Lệnh `pytest tests/test_no_missing_imports.py` mất **127 giây**. Nguyên nhân không
phải test nặng, mà là cách nó tìm file:

```python
# TRƯỚC — rglob đi qua data/ trước rồi mới lọc
files = [p for p in ROOT.rglob("*.py") if not any(part in SKIP for part in p.parts)]
```

`backend/data/` chứa bản sao cục bộ của lakehouse (bronze ~978 mã, gold ~897,
silver ~912, models ~1.003) với hàng trăm nghìn file Parquet. `Path.rglob` **vẫn
đi vào** thư mục đó rồi mới lọc kết quả — nên mỗi lần chạy đều phải đọc hết
thư mục cây khổng lồ đó.

Sửa bằng `os.walk`, vốn **cắt tỉa** (prune) thư mục con ngay trong danh sách
`dirnames`, nên không bao giờ bước vào:

```python
# SAU — không bao giờ bước vào data/
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [name for name in dirnames if name not in SKIP_PARTS]
```

**Kết quả đo:** 127,5 s → **2,6 s** (nhanh gấp **48 lần**), số test không đổi
(285 test), 0 failure. Cái được sửa không chỉ là tốc độ: trước đây số test của
file này **phụ thuộc vào việc máy còn bao nhiêu file dữ liệu trên đĩa**, nên
hai máy khác nhau sẽ ra số test khác nhau. Sau khi sửa, con số này **ổn định và
có thể tái lập**.

### 14.8.5. Chi tiết kỹ thuật: hai bản đồ điều hướng

| Tài liệu | Dành cho | Nội dung |
|---|---|---|
| `docs/BAN_DO_MA_NGUON.md` | **Người mới đọc dự án** | Mỗi thư mục và file trong toàn repo dùng để làm gì; bảng "Tôi muốn sửa X → mở file nào"; danh sách "đừng xoá" và "được xoá" |
| `backend/scripts/README.md` | Người chạy script | 86 script chia theo tiền tố: `ingest_`/`backfill_` (ghi), `verify_`/`check_` (đọc), `purge_`/`repair_` (xoá/sửa — cẩn thận), `run_`/`train_` |

### 14.8.6. Bằng chứng

- Toàn bộ repo sau khi dọn: `git status` không có file rác mới nào; các file
  bị xoá đều đã được kiểm tra bằng `git check-ignore` và `grep` trước khi xoá
  (đo 16/11/2026).
- `backend/tests/` còn **37 file test Python** — không mất file test nào (đo
  16/11/2026).
- `pytest tests` sau khi dọn: **561 test, 0 failure, 0 error, 0 skipped** (đo
  16/11/2026).
- API vẫn phục vụ bình thường sau khi dọn: `/api/v1/health` → 200,
  `/api/v1/forecast/accuracy` → 200, `/api/v1/quality/gate` → 200 (đo 16/11/2026).
- `git config core.autocrlf` chuyển từ `true` sang `input`, khớp với
  `.gitattributes` (`*.py text eol=lf`) — hết cảnh báo "CRLF will be replaced by
  LF" khi git so sánh file.

---

### 14.8.7. Chi tiết kỹ thuật: xoá bản sao cục bộ 9,03 GB

`backend/data/` là **bản sao** của lakehouse trên đĩa, dùng khi chạy ở chế độ
`STORAGE_BACKEND=local`. Máy này chạy `STORAGE_BACKEND=minio`, nên bản sao đó
**không phục vụ mục đích nào** nhưng lại chiếm 9 GB và 332.600 file.

#### 14.8.7.1. Kiểm tra trước khi xoá

Không xoá khi chưa kiểm chứng. Ba bước bắt buộc:

| Bước | Kiểm tra | Kết quả |
|---|---|---|
| 1 | `STORAGE_BACKEND` trong `backend/.env.local` | `minio` — backend đọc từ MinIO, không đọc bản sao local |
| 2 | Đếm object và số mã trong từng bucket MinIO | `stock-bronze` 116.110 object / 1.002 mã; `stock-silver` 116.628 / 1.002; `stock-gold` 115.101 / 1.002 — **nhiều hơn** bản sao local (115.321 / 106.685 / 105.605) |
| 3 | Model registry đọc từ đâu | `config.py`: `model_dir = "data/models"` → model nằm ở **local**, KHÔNG có trong MinIO (`stock-models` = 0 object) |

Bước 3 là bước **cứu dự án**: nếu xoá cả `data/models/` thì mất sạch 1.025 model
đã huấn luyện (trong đó 1.003 model `linear_regression` — chính là model đang
chạy và sinh ra 46.505 dòng dự báo trong MySQL). Vì vậy model được **backup ra
ngoài repo** trước, rồi **giữ lại**.

#### 14.8.7.2. Những gì đã xoá và những gì đã giữ

| Nhóm | Trước | Sau | Lý do |
|---|---|---|---|
| `data/bronze/` | 115.321 file / 1.012,6 MB | 0 | Trùng hoàn toàn trong MinIO |
| `data/silver/` | 106.685 file / 937,5 MB | 0 | Trùng hoàn toàn trong MinIO |
| `data/gold/` | 105.605 file / 7.171,6 MB | 0 | Trùng hoàn toàn trong MinIO |
| `data/models/*/YEAR=*/` | **9.532 thư mục chứa 326.347 thư mục con rỗng** | 0 | Rác tạo nhầm: `YEAR=2016/MONTH=10/PART-001.PARQUET/` là **thư mục rỗng**, không phải model. Không code nào tham chiếu `YEAR=` trong `models/` |
| `data/quality/` | thư mục rỗng | 0 | Không code nào tham chiếu |
| `data/_tmpmulti.py` | 1 file script tạm | 0 | Script in thử JSON, không dùng lại |
| `data/models/*/linear_regression`, `arima`, `lstm` | 1.025 model / 122,9 MB | **giữ nguyên** | Model registry đọc từ đây |
| `data/backtests/` + 6 file JSON kết quả | 14 file / 5,9 MB | **giữ nguyên** | Kết quả backtest và báo cáo đã chạy |

**Kết quả: 9,03 GB → 0,13 GB (tiết kiệm 8,91 GB).**

#### 14.8.7.3. Bằng chứng hệ thống còn nguyên sau khi xoá

- `GET /api/v1/stocks/AAPL/latest` → 200, `close: 356.2699890136719`,
  `source_layer: "gold"`, `source: "yahoo_http"` — dữ liệu thật đọc từ MinIO.
- `GET /api/v1/forecast/accuracy` → 200, **45.631 dòng đã chấm**, `mae: 333,16`,
  `directional_accuracy: 0,5058` — sổ ghi dự báo trong MySQL nguyên vẹn.
- MySQL `predictions`: **46.505 dòng**, trong đó **46.385** đã có `actual_close`.
- Backtest chạy thật sau khi xoá: `AAPL` / `ma_crossover` trên **2.541 phiên**
  (06/10/2016 → 13/11/2026) → lợi nhuận 320,81%, 29 lệnh; benchmark mua và giữ
  1.142,95%. (Chiến lược **vẫn thua** benchmark — hệ thống báo cáo đúng như vậy.)
- `pytest tests`: **572 test, 0 failure, 0 error, 0 skipped**. (Số test tăng từ 565
  lên 572 vì `test_no_missing_imports.py` đăng ký một test cho mỗi file Python tìm
  thấy, và các script mới trong `backend/scripts/` cũng được kiểm tra import.)
  Bộ kiểm thử đầy đủ chạy trong **139 giây** trên máy phát triển (đo ngày
  17/11/2026, `pytest tests/ -q`); con số này phụ thuộc tải máy nên được ghi
  kèm ngày đo thay vì coi là hằng số.

#### 14.8.7.4. Phát hiện thêm: bar crypto 24/7 gây phân kỳ tầng

Sau khi xoá, quality gate báo `layer_agreement: failed` với 2 mã
(`BTC-USD`, `ETH-USD`). Điều tra cho thấy đây là **lỗi thật**, không phải hậu
quả của việc xoá:

| Ngày phiên | Bronze | Silver | Gold |
|---|---|---|---|
| 2026-11-15 | 65.305,06 | 65.435,62 | 65.435,62 |

Bronze lưu **giá giữa phiên** của crypto (bar ngày 15/11 lúc 16/11 chưa chốt),
còn Silver/Gold lưu **giá đã chốt**. Nguyên nhân gốc: crypto giao dịch **24/7**
nên bar "hôm nay" luôn tồn tại ở trạng thái forming, và một lần auto-refresh bị
kill giữa chừng đã để lại bar đó.

Sửa bằng cơ chế có sẵn — chạy lại pipeline để rebuild Silver/Gold từ Bronze
(`LakehousePipeline().run(['BTC-USD','ETH-USD'])`). Sau khi rebuild, cả ba tầng
khớp tuyệt đối, và quality gate trở lại:

| Kiểm tra | Trước rebuild | Sau rebuild |
|---|---|---|
| `layer_agreement` | **failed** (2 mã) | **passed** (1.002 mã, 0 phân kỳ) |
| verdict tổng | `failed` | `warning` |

> **Bài học:** xoá bản sao cục bộ **không làm hỏng** dữ liệu, nhưng nó **lộ ra**
> một phân kỳ tầng vốn đã tồn tại. Đó là giá trị của việc kiểm chứng trước khi
> xoá: nếu xoá mà không kiểm tra, lỗi này sẽ bị quy cho lỗi của thao tác xoá.

---

### 14.8.8. Bài luận tham khảo theo chuẩn HCMUTE (đo ngày 16/11/2026)

#### 14.8.8.1. Hiểu đơn giản

Bài luận không phải là thứ viết một lần rồi để đó. Nó phải **khớp với hệ thống
đang chạy** mỗi khi có thay đổi. Vì vậy bài luận được viết kèm ba script kiểm
chứng tự động, mỗi script trả lời một câu hỏi:

| Script | Câu hỏi | Kết quả lần chạy cuối |
|---|---|---|
| `verify_thesis_numbers.py` | Con số trong bài có khớp hệ thống không? | **ALL CONSISTENT** |
| `check_thesis_markdown.py` | Cấu trúc Markdown có hỏng không? | 298 heading, 202 code fence, 126 bảng, 0 lỗi |
| `check_thesis_style.py` | Văn phong có bị máy viết không? | 0 mẫu filler, em-dash 116 → 27 |

#### 14.8.8.2. Thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì |
|---|---|---|
| Văn phong máy | Machine-generated filler | Các cụm từ rỗng không mang thông tin: "Trong thế giới ngày nay...", "không thể phủ nhận", "đóng vai trò then chốt" |
| Dấu gạch dài | Em-dash (`—`) | Dấu câu đặc trưng của văn do máy sinh; văn học thuật tiếng Việt nên tránh |
| Đối chiếu cặp | Paired comparison | So sánh hai chiến lược trên **cùng** một cửa sổ thời gian, mỗi cửa sổ đóng góp một điểm chênh lệch |
| Thẻ truy vết | Provenance tag | Hai trường `source_layer` và `source` đi kèm mọi con số để chứng minh nó đến từ đâu |

#### 14.8.8.3. Chi tiết kỹ thuật: cấu trúc bài luận

Bài luận bám theo **quy định làm khóa luận của Khoa CNTT, Trường Đại học Sư phạm
Kỹ thuật TP.HCM** (tài liệu `Quy-dinh-lam-KLTN-K-CNTT1.pdf` trên cổng
`fit.hcmute.edu.vn`), với thứ tự bắt buộc:

```
Tờ bìa -> Biên bản chấm -> Phiếu nhận xét GV phản biện -> Biên bản chỉnh sửa
-> Phiếu nhận xét GVHD -> Lời cảm ơn -> Lời cam đoan -> Tóm tắt -> Abstract
-> Mục lục -> Nội dung -> Tài liệu tham khảo -> Phụ lục
```

Phần nội dung bám theo bố cục chuẩn:

| Phần | Nội dung |
|---|---|
| Mở đầu | Lý do chọn, mục tiêu, đối tượng và phạm vi, phương pháp, kết quả chính |
| Chương 1 | Tổng quan: bối cảnh, đặt vấn đề, mục tiêu, phạm vi, nghiên cứu liên quan, khoảng trống |
| Chương 2 | Cơ sở lý thuyết: kho dữ liệu, Medallion, cổng chất lượng, mô hình dự báo, walk-forward |
| Chương 3 | Phân tích thiết kế: kiến trúc tổng thể và thiết kế chi tiết 7 thành phần |
| Chương 4 | Kết quả và thảo luận: môi trường, kết quả đo, thảo luận, giới hạn |
| Kết luận | Tóm tắt, đóng góp, hạn chế, hướng phát triển |

Bài luận có **4.696 dòng, khoảng 43.661 từ**, 298 heading, 126 bảng, 202 khối code,
30 tài liệu tham khảo theo chuẩn IEEE.

#### 14.8.8.4. Bằng chứng

- `verify_thesis_numbers.py` đối chiếu 7 chỉ số quan trọng (tổng dự báo, số
  dự báo đã chấm, số mã, MAE, sai số tương đối trung bình, độ chính xác hướng,
  số hội thoại AI) với MySQL đang chạy: **ALL CONSISTENT** (đo 16/11/2026).
- `check_thesis_markdown.py`: 0 lỗi cấu trúc (đo 16/11/2026).
- `check_thesis_style.py`: 0 mẫu văn phong máy; em-dash giảm từ 116 xuống 27,
  tức còn khoảng 1 em-dash trên 24 câu (đo 16/11/2026).
- Ba script nằm ở `backend/scripts/` và được liệt kê trong `backend/scripts/README.md`
  mục 8.1.

---

# PHẦN 15 — GIỚI HẠN & CÂU TRẢ LỜI PHẢN BIỆN

**Nêu giới hạn TRƯỚC khi thầy nêu** là chiến lược tốt nhất — nó biến điểm yếu thành bằng chứng nghiên cứu nghiêm túc.

## 15.1. Hiểu đơn giản

Hệ thống này là **công cụ nghiên cứu**, không phải sàn giao dịch. Nó cố tình **giới hạn phạm vi** để làm đúng phần học thuật.

## 15.2. Chi tiết: bảng giới hạn

| Giới hạn | Vì sao chấp nhận được | Hướng mở rộng |
|---|---|---|
| **Chỉ long-only** | Đơn giản, tránh bẻ khóa short + margin | Thêm short/side qua `Portfolio` |
| **2 chiến lược** | Đủ để chứng minh khung backtest đúng | Base class `BaseStrategy` sẵn sàng mở rộng |
| **DA ~50%** | Đây là **kết quả thật** của dự báo giá daily; giấu nó là hại trường | Thêm mô hình đa biến với đặc trưng giá/khối lượng |
| **Backtest trên 1 cổ phiếu** | Minh hoạ khung | Đã hỗ trợ đủ 1.037 mã |
| **Chưa có transaction cost theo loại lệnh** | Fee/slippage cố định là mô hình nghiên cứu chuẩn | Bảng fee theo sàn |
| **Đã gỡ Kafka và Iceberg (10/11/2026)** | Chúng giải quyết bài toán mà đồ án này không có (streaming realtime, cập nhật từng dòng) và tốn 2 JVM phải vận hành | Đã thay bằng lịch cron + bảng `predictions` |
| **Đã gỡ toàn bộ đường dẫn realtime (11/11/2026)** | Bộ nhớ đệm SSE đo được **0 mã / 0 bar**; realtime không ghi gì vào Bronze nên không mất bản ghi nào | Nếu cần tick thật: thêm provider có license tick (bản trả phí) — hiện tại chưa đáng giá cho đồ án |
| **Đã gỡ toàn bộ luồng tin tức (12/11/2026)** | Đo được độ phủ chỉ **0,00%** phiên (15/356.803) và tin thật bị gắn sai mã do trùng ticker (`MWG`, `VCB`) | Nếu cần đặc trưng tin tức: phải có nguồn trả phí có mapping mã chuẩn (ISIN), rồi đo lại độ phủ trên ≥ 2 năm |
| **Chưa có portfolio đa tài sản** | `Portfolio` là một vị thế đơn | Đã tách `Portfolio` khỏi `simulate` |

## 15.3. Chi tiết: câu hỏi phản biện thường gặp và câu trả lời chuẩn bị

**"Dữ liệu của em lấy ở đâu, có chắc là thật?"**
> *"Từ Yahoo Finance v8 chart API (không cần key) và SSI iBoard cho mã Việt Nam, qua chuỗi failover `multi_source`. Mỗi record Bronze lưu `source` và `ingestion_time`; mỗi mã có `_lineage.json`. Hệ thống **không có** dữ liệu mẫu ở bất kỳ đâu — `market_service` ném `NotFoundError` thay vì trả số giả. Có script `backend/tests/verify_real_data.py` đối chiếu trực tiếp với nguồn ngoài."*

**"Em có bị look-ahead bias không?"**
> *"Không, và đây là ba cơ chế cụ thể: (1) target luôn `shift(-1)`, feature chỉ dùng quá khứ; (2) tách train/val/test theo thời gian, không shuffle; (3) backtest thực thi ở bar kế tiếp qua `signals.shift(1)`. Đồ án còn có test riêng chứng minh cơ chế warmup — vì test đó thất bại thì backtest không thể cho ra kết quả nào."*

**"Em có tối ưu trên tập test không?"**
> *"Không. Tham số chiến lược được chọn trên **train window**; test window hoàn toàn chưa từng thấy. Với mô hình ML, early stopping dùng **validation** (15%), test (15%) chỉ dùng để đo lần cuối. Thêm nữa, cả ba tỷ lệ `train_ratio/validation_ratio/test_ratio` đều cấu hình được."*

**"Số +308% là thật không?"**
> *"Con số đó là **thật về mặt kế toán** — hệ thống tự kiểm tra `sum(pnl) == final_capital - initial_capital` và khớp tuyệt đối. Nhưng nó **không phải** thành tựu của chiến lược: AAPL tăng mạnh trong thập kỷ đó và chiến lược buy-and-hold cũng được gần như vậy. Chính vì thế hệ thống có walk-forward validation, và kết quả của nó (overfitting ratio 4.0, consistency 13%) nói rằng chiến lược **không** tổng quát tốt. Tôi báo cáo cả hai."*

**"Walk-forward của em cho kết quả không tốt, vậy có ích gì?"**
> *"Đó là **đóng góp** chứ không phải hạn chế. Nếu hệ thống chỉ báo +308% mà thiếu tầng kiểm định này, nó sẽ tạo ấn tượng giả — và đó chính là lỗi phổ biến nhất trong các đồ án cùng chủ đề. Walk-forward ở đây đóng hai vai trò: (a) đo xu hướng quá khứ của chiến lược để biết nó có ổn định không; (b) chứng minh tính trung thực của bộ backtest — nếu tầng kiểm định ra kết quả toàn số 0, đó là dấu hiệu backtest sai, không phải chiến lược tệ."*

**"Mô hình nào tốt nhất?"**
> *"Trên tập hold-out AAPL, Linear Regression có MAE thấp nhất (2.994). Nhưng cả ba đều có directional accuracy quanh 50% — tức **gần như không có kỹ năng dự đoán hướng vượt ngẫu nhiên**. Tôi **không** tuyên bố mô hình nào 'tốt nhất'; hệ thống hiển thị cả ba cùng metrics trên **cùng một tập hold-out** để người đọc tự đánh giá. Đây là kết quả trung thực của dự báo giá ở tần suất ngày."*

**"Hệ thống có chịu được tải không?"**
> *"Với một người dùng cục bộ thì có. Các nút throttling đã được đo và xử lý: cache LRU 256 + TTL 900s, ghi partition song song, đếm object trong subprocess, request gate ưu tiên tương tác, và process pool riêng cho việc nặng. Walk-forward từ 96s (khi refresh chạy) xuống 2s. Hệ thống được thiết kế cho **demo nghiên cứu một người dùng**, không phải production multi-tenant — và tôi nói rõ điều đó."*

**"Nếu thầy hỏi MinIO có sập không?"**
> *"Có fallback về filesystem local — `storage_factory` chọn backend theo cấu hình, và `LocalStorageBackend` implement cùng interface `StorageBackend`, nên **toàn bộ pipeline không biết** nó đang nói chuyện với cái gì. Thiếu MinIO thì hệ thống chậm đi chứ không sập."*

**"Em có định deploy production không?"**
> *"Không, và đồ án không tuyên bố làm được điều đó. Những gì còn thiếu cho production: xác thực người dùng, rate limiting, audit log, HA storage, và scheduler bền vững. Những thứ này được nêu tường minh trong mục giới hạn."*

**"Vì sao bỏ Kafka và Iceberg? Đồ án còn đủ hấp dẫn không?"**
> *"Đồ án nghiên cứu dữ liệu daily ở quy mô ~10^5 partition. Kafka và Iceberg giải quyết những bài toán mà đồ án này **không có**: streaming realtime không ai dùng, và cập nhật từng dòng trên object storage cho một pipeline append-only. Giữ chúng nghĩa là thêm 2 JVM phải vận hành và 2 bản sao metadata để đổi lấy 0 phần tính năng dùng được. Phần thay thế không kém: lịch cron nằm trong version control, batch EOD tự động dự báo phiên kế tiếp và ghi vào MySQL. Chi tiết ở mục 2.4.1 và Phần 5B."*

**"Vì sao em bỏ luồng tin tức? Đồ án không bị thiếu gì sao?"**
> *"Đúng, đồ án không bị thiếu gì — và đó là lý do em **gỡ** chứ không phải giữ. Em đo độ phủ trước khi quyết định: trên 1.002 mã, 356.803 phiên giao dịch trong mẫu 365 ngày, chỉ **15 phiên** có tin tức sẵn sàng trước giờ mở cửa — `overall_coverage_pct` = **0,00%**. Tệ hơn, khi đọc từng bài em thấy mã `MWG` của Mobile World nhận tin của Multi Ways Holdings (Singapore) và mã `VCB` của Vietcombank nhận tin của quỹ ETF Vanguard, vì các mã này trùng nhau giữa các sàn. Bài báo thật nhưng gắn sai mã thì dòng dữ liệu đó không truy vết được — vi phạm nguyên tắc của đồ án. Em không giữ một trang rỗng rồi giải thích là 'đang thử nghiệm'. Chi tiết ở Phần 5B.1."*

**"Tin tức có giá trị dự báo không? Có số liệu để chứng minh không?"**
> *"Em **không** khẳng định tin tức có giá trị dự báo, và em cũng **không** đưa ra con số nào cho điều đó. Điều duy nhất em đo được là **độ phủ dữ liệu** — 0,00%. Đo tác động thật sự cần một thí nghiệm có đối chứng (nhóm có tin / nhóm không tin, so sánh lợi nhuận sau chi phí), và em chưa làm nên em không đưa ra con số. Nói ngắn gọn: em đã đo được đủ để biết là **chưa đủ dữ liệu để làm thí nghiệm**, nên em gỡ."*

**"Dự báo phiên kế tiếp có chính xác không?"**
> *"Không có con số nào được đo cho điều đó, và tôi không đưa ra kết luận nào. Những gì tôi khẳng định được là về **cơ chế**, không phải về độ chính xác: dự báo được sinh bởi đúng một hàm dùng chung cho cả Dashboard và bảng `predictions`; nó **không** train mô hình, chỉ dùng mô hình đã có sẵn trên đĩa; và khi mã chưa có mô hình thì hệ thống báo 'không có' chứ không dựng con số thay thế. Về độ chính xác thì phải trả lời ở Phần 6, nơi có kết quả đo trên tập hold-out."*

---

# PHẦN 16 — CÂU HỎI THƯỜNG GẶP KHI BẢO VỆ (FAQ)

**Q: Khởi động hệ thống thế nào?**
```powershell
.\start-all.ps1          # backend :8000 + frontend :5173 + docker (minio, mysql)
# dừng
.\stop-all.ps1
```

**Q: Kiểm tra dữ liệu thật?**
```powershell
cd backend
.\.venv\Scripts\python.exe tests\verify_real_data.py
.\.venv\Scripts\python.exe scripts\check_layer_divergence.py
.\.venv\Scripts\python.exe scripts\check_unserved_symbols.py
```

**Q: Chạy test?**
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\ -q       # 561/561
```

**Q: Train model từ CLI?**
```powershell
cd backend
.\.venv\Scripts\python.exe scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm
```

**Q: Chạy backtest / walk-forward từ CLI?**
```powershell
cd backend
.\.venv\Scripts\python.exe -c "from app.services.backtest_service import BacktestService; import json; print(json.dumps(BacktestService().run({'symbol':'AAPL','strategy':'ma_crossover'}), default=str)[:800])"
.\.venv\Scripts\python.exe -c "from app.agent.tools.walkforward_tools import run_walk_forward; import json; print(json.dumps(run_walk_forward(symbol='AAPL', strategy='ma_crossover')['summary'], default=str, indent=2))"
```

**Q: Bật các job tự động (batch EOD, tin tức, đo độ phủ)?**
```powershell
# Trong WSL, bật toàn bộ profile app (kèm scheduler)
wsl -d Ubuntu-24.04 -u root -e bash -c "cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose --profile app up -d"

# Xem lịch cron đã nạp
docker compose exec scheduler crontab -l

# Xem các job đã chạy (log có mốc thời gian UTC)
Get-Content backend/logs/scheduled_jobs.log
```

**Q: Chạy một job thủ công (không đợi cron)?**
```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_scheduled_job.py eod
```

**Q: Xem dự báo phiên kế tiếp đã lưu?**
```powershell
curl http://127.0.0.1:8000/api/v1/forecast/next-session/AAPL
# lưu thủ công vào MySQL:
curl -X POST http://127.0.0.1:8000/api/v1/forecast/next-session/AAPL/store
```

**Q: Dữ liệu bao nhiêu mã?**
> 1.018 mã khai báo (`US_SYMBOLS=598`, `VN_SYMBOLS=81`, `GLOBAL_SYMBOLS=931`, `CRYPTO_SYMBOLS=3`); 1.037 mã hiển thị trên UI (kể cả index). Lịch sử tối đa 10 năm daily.

**Q: Mô hình nào dùng cho đồ án chính?**
> Cả ba, kèm so sánh trên **cùng một tập hold-out**. LSTM là đóng góp kỹ thuật nổi bật nhất (target tương đối). ARIMA là đối chứng thống kê. Linear Regression là baseline công bằng.

---

# PHỤ LỤC A — BẢN ĐỒ MÃ NGUỒN

```
backend/app/
├── api/v1/endpoints/     12 module endpoint
├── agent/                LLM + 17 tool
├── backtesting/          engine portfolio simulator metrics
│   │                      benchmark (đường cơ sở mua & giữ)
│   └── strategies/       ma_crossover  rsi_strategy
├── core/                 config constants exceptions heavy_worker
│                        request_gate seeding logging_config
├── data_sources/         12 provider + multi_source
├── database/             models repositories session
├── features/             feature_engineering technical price target
│                        advanced macro
├── forecasting/          trainer predictor dataset preprocessing
│                        evaluator linear_regression arima lstm lstm_network
│                        multistep model_registry base sessions
├── indicators/           sma ema rsi macd bollinger service
├── lakehouse/            bronze silver gold pipeline storage_*
│                        dedupe plausibility session parquet_manager
│                        parallel_write spark_session
├── pipelines/            orchestrator worker
├── schemas/              pydantic schema
├── services/             market backtest forecast agent auto_refresh
│                        dashboard indicator data_ingestion pipeline
│                        stream crawler next_session_forecast
└── streaming/            finnhub_websocket vn_websocket

frontend/src/
├── api/                  client stocks market forecasting backtesting
│                        indicators agent
├── components/           charts common dashboard layout agent ui
├── hooks/                useForecast useBacktest useStocks useMarket
│                         useMarketBusy
├── lib/                  i18n utils
├── pages/                7 trang
├── types/                TypeScript types
└── utils/                format resample constants

backend/tests/            37 file test (561 test)
backend/scripts/          kiểm chứng dữ liệu + công cụ
docs/                     tài liệu
```

## PHỤ LỤC B — MA TRẬN TRUY VẾT YÊU CẦU ĐỒ ÁN

| Yêu cầu đồ án | Thực hiện ở đâu | Bằng chứng |
|---|---|---|
| Thu thập dữ liệu tự động | `lakehouse/pipeline.py`, `data_sources/` | Bronze 116k records |
| Data lakehouse 3 tầng | `lakehouse/bronze.py` `silver.py` `gold.py` | Silver 116k · Gold 115k |
| Làm sạch dữ liệu | `silver.py`, `plausibility.py`, `dedupe.py` | `_quality.json` mỗi mã |
| Feature engineering | `features/` | 75 features + 3 targets |
| Mô hình ML | `forecasting/` (LR, ARIMA, LSTM) | MAE 2.99 / 3.01 / 3.29 |
| Đánh giá mô hình | `forecasting/evaluator.py` | MAE/RMSE/MAPE/DA |
| Backtest | `backtesting/` | 29 trades, khớp PnL |
| Kiểm định ngoài mẫu | `backtesting/walk_forward.py` | 159/159 windows (AAPL); 3.687 windows / 101 mã (đa mã) |
| Dự báo tự động cuối ngày | `services/next_session_forecast.py`, `services/universe_forecast.py` | 973 mã được dự báo trong 1 lượt (13/11/2026) |
| **Kiểm chứng dự báo ngoài tập huấn luyện** | `services/forecast_scoring.py`, `forecasting/light_forecast.py` | **46.385 dòng đã chấm**, sai số tương đối trung vị **1,15%**, đúng hướng **50,6%** |
| Giao diện web | `frontend/` | 7 trang |
| AI agent | `agent/` | 17 tool |
| Dữ liệu thật, không giả | `market_service.py` | `NotFoundError` |
| Tài liệu + bảo vệ | file này | — |

---

> **Tóm lại:** Đồ án này không cố tạo ra một con số "ấn tượng". Nó xây dựng một **hạ tầng nghiên cứu có thể kiểm chứng** — nơi mọi con số đều truy vết được tới nguồn, mọi phép đo đều trung thực, và **kết quả xấu cũng được báo cáo nguyên vẹn**. Chính điều đó là giá trị của một đồ án khoa học.
