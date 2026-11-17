# BẢN ĐỒ MÃ NGUỒN — ĐỌC FILE NÀY TRƯỚC KHI MÒ FILE KHÁC

**Mục đích:** sau 30 giây đọc file này, bạn biết mỗi thư mục và mỗi file trong dự án làm gì, và
khi nào cần mở nó. Không phải mò từng file.

**Cập nhật:** 16/11/2026

---

## 0.1. Hiểu đơn giản

Dự án này là một **hệ thống kho dữ liệu tài chính** với 3 phần chính:

1. **`backend/`** — trái tim hệ thống. Nó tải giá thật từ sàn giao dịch, rửa sạch, lưu lại,
   rồi dự đoán giá ngày mai và kiểm thử chiến lược đầu tư trên lịch sử.
2. **`frontend/`** — giao diện web React mà bạn nhìn thấy trên trình duyệt.
3. **`docs/`** — tài liệu luận văn và hướng dẫn vận hành.

Có 4 món "đặc biệt" cần biết ngay:

| Món | Nghĩa là gì |
|---|---|
| `minio_data/` | **Dữ liệu thật đang nằm trên đĩa.** Đừng xoá, xoá là mất lịch sử giá. |
| `.venv/` | Môi trường Python đã cài sẵn thư viện. Xoá thì phải cài lại hết. |
| `node_modules/` | Thư viện JavaScript của frontend. Xoá thì phải cài lại hết. |
| `backend/data/` | Bản sao cục bộ của dữ liệu khi chạy ở chế độ `STORAGE_BACKEND=local`. **Hiện chỉ còn `models/` + `backtests/`** (đã xoá 9,03 GB bản sao bronze/silver/gold ngày 16/11/2026 — dữ liệu vẫn đầy đủ trong MinIO). |

---

## 0.2. Bảng tra thuật ngữ (đọc khi thấy từ lạ)

### 0.2.1. Thuật ngữ về CẤU TRÚC

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **3 tầng kho dữ liệu** | **Medallion Architecture** | Chia dữ liệu thành: giữ nguyên → rửa sạch → phân tích | `backend/app/lakehouse/` |
| **Tầng giữ nguyên** | **Bronze** | Giá tải thẳng từ sàn, chưa rửa, giữ để đối chiếu | `backend/app/lakehouse/bronze.py` |
| **Tầng đã rửa** | **Silver** | Đã loại dòng hỏng, chuẩn hoá múi giờ UTC | `backend/app/lakehouse/silver.py` |
| **Tầng phân tích** | **Gold** | Đã tính chỉ báo, đặc trưng, sẵn sàng dùng | `backend/app/lakehouse/gold.py` |
| **Kho đối tượng** | **Object storage / MinIO** | Nơi lưu file Parquet, giống ổ cứng mạng | `backend/app/lakehouse/minio_storage.py` |
| **Định dạng cột** | **Parquet** | Định dạng file nén, đọc nhanh bằng pandas | `backend/app/lakehouse/parquet_manager.py` |

### 0.2.2. Thuật ngữ về MÔ HÌNH

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Đường hồi quy tuyến tính** | **Linear Regression** | Dự báo giá mai bằng đường thẳng vẽ qua dữ liệu cũ | `backend/app/forecasting/linear_regression.py` |
| **Mô hình chuỗi thời gian** | **ARIMA** | Dự báo giá dựa trên mẫu hình lặp lại của chính nó | `backend/app/forecasting/arima.py` |
| **Mạng trí nhớ dài hạn** | **LSTM** | Mạng nơ-ron nhớ được chuỗi dài, dự báo giá bằng "trí nhớ" | `backend/app/forecasting/lstm.py` |
| **Chấm điểm ngược** | **Backtesting** | Chạy chiến lược trên lịch sử để xem nó có lời không | `backend/app/backtesting/` |
| **Đối chiếu từng cửa sổ** | **Walk-forward** | Lăn cửa sổ thời gian, huấn luyện rồi kiểm tra như ngoài đời | `backend/app/backtesting/walk_forward.py` |
| **Đường cơ sở** | **Benchmark** | Mua và giữ — chiến lược mà mọi chiến lược phải thắng | `backend/app/backtesting/benchmark.py` |
| **Nhìn thấy tương lai** | **Look-ahead bias** | Dùng thông tin ngày mai để quyết định hôm nay (sai!) | Cấm trong `backtesting/engine.py` |

### 0.2.3. Thuật ngữ về KIỂM TRA CHẤT LƯỢNG

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Cổng chất lượng** | **Quality Gate** | Bộ kiểm tra tự động xem dữ liệu có sạch không | `backend/app/core/quality_gate.py` |
| **Bộ lọc giá vô lý** | **Plausibility guard** | Chặn giá không thể có (âm, hoặc lệch 100 lần) | `backend/app/lakehouse/plausibility.py` |
| **Ảnh chụp giữa phiên** | **Forming snapshot** | Bar lấy lúc 12:29, giá chưa chốt trong ngày | `backend/app/lakehouse/forming_bar.py` |
| **Ngày giao dịch** | **Trading session** | Phiên giao dịch theo múi giờ của sàn, không theo UTC | `backend/app/lakehouse/exchange_timezone.py` |
| **Gãy thang giá** | **Scale break** | Cổ phiếu chia tách làm giá nhân 50 lần | `backend/app/lakehouse/scale_repair.py` |
| **Trái cây** | **AI agent** | Trợ lý hỏi đáp bằng ngôn ngữ tự nhiên | `backend/app/agent/` |

---

## 0.3. Bản đồ thư mục lớn

```
stock-lakehouse-ai/
│
├── backend/                  Trái tim hệ thống (Python/FastAPI)
├── frontend/                 Giao diện web (React + Vite + TypeScript)
├── docs/                     Tài liệu luận văn + vận hành
├── scripts/                  Công cụ bảo trì (2 nhóm con)
├── minio/                    Dockerfile cho MinIO
├── minio_data/               DỮ LIỆU THẬT — KHÔNG XOÁ
├── logs/                     Log của tiến trình frontend
│
├── .cursor/rules/            Quy tắc làm việc cho AI assistant
├── .github/workflows/        CI tự động (daily-ingest)
│
├── docker-compose.yml        Bật MySQL + MinIO + backend
├── start-all.ps1 / .bat      Bật toàn hệ thống 1 lệnh
├── stop-all.ps1 / .bat       Tắt toàn hệ thống
├── Makefile / make.ps1       Lệnh tắt-gọn cho dev
├── README.md                 Hướng dẫn nhanh bắt đầu
├── LOCAL_DEV.md              Hướng dẫn chạy trên máy Windows
└── .env / .env.example       Cấu hình (biến môi trường)
```

---

## 0.4. Chi tiết: `backend/` — nơi cần đọc code

### 0.4.1. `backend/app/` — mã nguồn chính

| Thư mục / file | Tác dụng | Mở khi nào |
|---|---|---|
| `main.py` | Điểm khởi động FastAPI, cấu hình CORS, vòng đời app | Muốn hiểu app khởi động thế nào |
| `core/config.py` | Đọc **toàn bộ** cấu hình từ `.env` | Thêm/sửa biến cấu hình |
| `core/heavy_worker.py` | Chạy job nặng ở **tiến trình con** để không nghẽn API | Job nặng bị chậm |
| `core/request_gate.py` | Giới hạn số request đồng thời để không sập server | API trả lỗi 503 |
| `core/quality_gate.py` | **Bộ kiểm tra chất lượng dữ liệu** (7 lần kiểm tra) | Cần biết dữ liệu có sạch không |
| `core/data_integrity.py` | Quy tắc quyết định symbol nào là dữ liệu thật | Nghi ngờ có dữ liệu giả lọt vào |
| `core/exceptions.py` | Các lỗi nghiệp vụ dùng chung | Thêm loại lỗi mới |
| `core/logging_config.py` | Cấu hình logger | Đổi cách ghi log |
| `core/security.py` | Xác thực, hash mật khẩu | Làm việc với user/auth |
| `core/seeding.py` | Seed dữ liệu ban đầu cho DB | Tạo DB mới |

### 0.4.2. `backend/app/lakehouse/` — trái tim dữ liệu

| File | Tác dụng |
|---|---|
| `bronze.py` | **Tầng 1**: ghi dữ liệu thô tải từ sàn. Giữ nguyên để đối chiếu. |
| `silver.py` | **Tầng 2**: rửa sạch, loại dòng hỏng, chuẩn hoá UTC, dedupe phiên. |
| `gold.py` | **Tầng 3**: tính chỉ báo + đặc trưng, sẵn sàng cho mô hình và UI. |
| `pipeline.py` | Chạy trọn Bronze → Silver → Gold cho 1 danh sách mã. |
| `plausibility.py` | **Bộ lọc chặn giá vô lý** trước khi ghi vào Bronze. |
| `dedupe.py` | Phát hiện trùng lặp cùng một bar trong Bronze. |
| `session.py` | Chuẩn hoá bar ngày về đúng phiên giao dịch (13:30 UTC cho NYSE). |
| `exchange_timezone.py` | Múi giờ của từng sàn + ngày giao dịch của từng mã. |
| `forming_bar.py` | Nhận biết bar chụp **giữa phiên** (chưa chốt) để không báo nhầm là xung đột. |
| `scale_repair.py` | Phát hiện và sửa lỗi chia tách làm giá nhân 50 lần. |
| `frame_cache.py` | Bộ nhớ đệm frame trong RAM để đọc nhanh (LRU + TTL). |
| `parquet_manager.py` | Đọc/ghi file Parquet theo partition `symbol=/year=/month=`. |
| `storage_base.py` | Giao diện chung cho mọi nơi lưu trữ. |
| `storage_factory.py` | Chọn MinIO hay local, tự fallback khi MinIO chết. |
| `minio_storage.py` | Backend lưu trữ MinIO (đang dùng). |
| `local_storage.py` | Backend lưu trữ local filesystem (dự phòng). |
| `parallel_write.py` | Ghi nhiều partition song song để nhanh hơn. |
| `fundamentals_silver.py` | Tầng Silver cho dữ liệu tài chính cơ bản. |
| `spark_session.py` | Tạo Spark session (tùy chọn, mặc định tắt). |

### 0.4.3. `backend/app/forecasting/` — dự đoán giá

| File | Tác dụng |
|---|---|
| `base.py` | Hợp đồng chung mọi mô hình dự báo phải tuân theo. |
| `linear_regression.py` | **Mô hình đang chạy chính** (45.357 dòng dự báo trong DB). |
| `arima.py` | Mô hình ARIMA (statsmodels). |
| `lstm.py` + `lstm_network.py` | Mạng LSTM (PyTorch), có early stopping. |
| `dataset.py` | Chia dữ liệu thành chuỗi cho LSTM học. |
| `preprocessing.py` | **Chia train/val/test theo thứ tự thời gian — không được xáo trộn.** |
| `trainer.py` | Điều phối huấn luyện (dùng bởi API và script). |
| `model_registry.py` | Sổ đăng ký mô hình trên đĩa (hoạt động cả khi MySQL chết). |
| `predictor.py` | Nạp mô hình đã huấn luyện → dự báo phiên kế tiếp. |
| `light_forecast.py` | **Đường nhanh**: dự báo không cần nạp mô hình đầy đủ. |
| `multistep.py` | Dự báo nhiều ngày tới bằng cách đệ quy. |
| `sessions.py` | Lịch giao dịch của từng mã, suy ra từ chính lịch sử của nó. |
| `universe_training.py` | Huấn luyện mô hình cho **toàn bộ** ~1.000 mã. |
| `evaluator.py` | Tính metric đánh giá dự báo. |

### 0.4.4. `backend/app/backtesting/` — kiểm thử chiến lược

| File | Tác dụng |
|---|---|
| `strategy_base.py` | Giao diện chiến lược: **tín hiệu ở bar t, khớp lệnh ở bar t+1**. |
| `strategies/ma_crossover.py` | Chiến lược cắt chéo đường trung bình động. |
| `strategies/rsi_strategy.py` | Chiến lược RSI (mua khi quá bán, bán khi quá mua). |
| `engine.py` | **Engine backtest chính**: nạp dữ liệu, chạy chiến lược, tính metric. |
| `simulator.py` | Mô phỏng từng bar: khớp lệnh, trừ phí, cập nhật danh mục. |
| `benchmark.py` | **Đường cơ sở mua và giữ** — mọi chiến lược phải thắng cái này. |
| `walk_forward.py` | Kiểm thử lăn cửa sổ (train → test → lùi → lặp). |
| `metrics.py` | Tính lợi nhuận, Sharpe, drawdown, win rate, profit factor. |
| `portfolio.py` | Danh mục chỉ được mua (long-only). |
| `trade.py` | Cấu trúc một lệnh đã đóng (PnL đã trừ phí). |
| `worker.py` | Điểm vào cho tiến trình con (tránh nghẽn API). |

### 0.4.5. `backend/app/services/` — tầng nghiệp vụ

| File | Tác dụng |
|---|---|
| `market_service.py` | Đọc OHLCV **chỉ** từ lakehouse (Gold → Silver → Bronze). |
| `auto_refresh.py` | Quét nền: tải mã mới → Bronze → Silver → Gold. |
| `forecast_scoring.py` | **Chấm điểm dự báo bằng giá đóng cửa thật** từ Gold. |
| `next_session_forecast.py` | Dự báo phiên kế tiếp và **lưu** vào MySQL. |
| `universe_forecast.py` | Lượt dự báo toàn universe đêm. |
| `forecast_backfill.py` | Bổ sung lịch sử dự báo vào sổ ghi để đo độ chính xác. |
| `quality_gate_service.py` | Chạy quality gate và lưu kết quả để API đọc. |
| `dashboard_service.py` | Gom số liệu cho trang Dashboard. |
| `data_ingestion_service.py` | Điều phối việc tải dữ liệu từ các nguồn. |
| `pipeline_service.py` | Chạy pipeline qua API. |
| `forecasting_service.py` | Nghiệp vụ dự đoán (huấn luyện, dự báo). |
| `indicator_service.py` | Bọc các chỉ báo kỹ thuật. |
| `backtest_service.py` | Nghiệp vụ backtest + walk-forward. |
| `agent_service.py` | Nghiệp vụ trợ lý AI. |
| `crawler_service.py` | Trình thu thập dữ liệu liên tục (tùy chọn). |

### 0.4.6. `backend/app/agent/` — trợ lý AI

| File | Tác dụng |
|---|---|
| `agent.py` | Vòng lặp chính: nhận câu hỏi → gọi tool → trả lời. |
| `tool_registry.py` | **Danh mục tool** mà LLM được phép gọi. |
| `prompts.py` | System prompt + ngữ cảnh dự án cho LLM. |
| `llm_client.py` | Gọi Gemini Free API, có fallback offline. |
| `markdown_normalizer.py` | Chuẩn hoá markdown LLM trả về cho UI. |
| `tools/stock_tools.py` | Tool tra cứu giá cổ phiếu. |
| `tools/fundamental_tools.py` | Tool tra cứu số liệu tài chính. |
| `tools/system_tools.py` | Tool tra cứu trạng thái hệ thống/lakehouse. |
| `tools/walkforward_tools.py` | Tool chạy walk-forward từ trong chat. |

### 0.4.7. Các thư mục còn lại trong `backend/app/`

| Thư mục | Tác dụng |
|---|---|
| `api/v1/endpoints/` | **Mỗi file = một nhóm endpoint API.** Xem `router.py` để biết prefix. |
| `api/dependencies.py` | Dependency dùng chung (lấy DB session...). |
| `api/v1/router.py` | **File gom tất cả route vào app.** Đọc file này để biết API nào tồn tại. |
| `schemas/` | Model Pydantic mô tả dữ liệu vào/ra của API. |
| `data_sources/` | **11 nhà cung cấp dữ liệu thật.** Xem `factory.py` để biết chọn nhà cung cấp nào. |
| `database/models/` | Bảng MySQL (ORM). `prediction.py` = bảng dự báo. |
| `database/repositories/` | Truy vấn DB theo từng bảng. |
| `database/session.py` | Tạo kết nối MySQL. |
| `features/` | Tính đặc trưng cho mô hình (giá, kỹ thuật, macro, target). |
| `indicators/` | Chỉ báo kỹ thuật: SMA, EMA, RSI, MACD, Bollinger. |
| `pipelines/` | Orchestrator + worker cho pipeline nền. |

### 0.4.8. `backend/` — ngoài `app/`

| Đường dẫn | Tác dụng |
|---|---|
| `tests/` | **572 test.** Chạy: `pytest tests -q`. Xem bảng ở `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md` §14.3. |
| `scripts/` | **81 script vận hành/kiểm chứng.** Xem `backend/scripts/README.md`. |
| `alembic/` | Migration cấu trúc DB (`versions/0002..0004`). |
| `alembic.ini` | Cấu hình Alembic. |
| `crontab` | Lịch cron cho container backend. |
| `entrypoint.sh` | Script khởi động khi container chạy. |
| `Dockerfile` | Đóng gói backend thành image. |
| `requirements.txt` | Danh sách thư viện Python cần cài. |
| `pyproject.toml` | Cấu hình ruff/black/pytest. |
| `.env` / `.env.local` | Cấu hình thật của máy. **`.env.local` có mật khẩu — đừng commit.** |
| `.env.local.example` | Mẫu cấu hình để người khác sao chép. |
| `data/` | Dữ liệu cục bộ (chế độ `STORAGE_BACKEND=local`) + kết quả backtest. |
| `docs/vn_quality_reports/` | Báo cáo chất lượng dữ liệu cho 53 mã Việt Nam. |
| `logs/` | Log runtime. Xoá được, tự tạo lại. |
| `daily_refresh.py` | Script làm mới hằng ngày. |
| `migrate_to_minio.py` | Chuyển dữ liệu từ local sang MinIO. |

---

## 0.5. Chi tiết: `frontend/src/` — giao diện web

| Thư mục / file | Tác dụng | Mở khi nào |
|---|---|---|
| `main.tsx` | Điểm gắn React vào DOM. | Không bao giờ, trừ khi lỗi khởi động. |
| `App.tsx` | **Bộ khung app + định tuyến trang.** | Thêm trang mới. |
| `api/client.ts` | Hàm `fetch` gọi API backend (có timeout 90s). | Lỗi gọi API. |
| `api/*.ts` | Mỗi file = một nhóm API client (agent, stocks, forecasting, backtesting, quality...). | Thêm endpoint mới. |
| `hooks/` | React hooks dùng chung (`useForecast`, `useBacktest`, `useMarket`, `useStocks`). | Tái sử dụng logic fetch. |
| `pages/` | **Mỗi file = một trang.** `Dashboard`, `Forecasting`, `Backtesting`, `MarketData`, `AIAgent`, `SystemStatus`, `TechnicalAnalysis`. | Sửa nội dung trang. |
| `components/layout/` | Khung trang: `Header`, `NavBar`, `MainLayout`. | Đổi menu/điều hướng. |
| `components/dashboard/` | Thẻ Dashboard: metric, watchlist, dự báo, chất lượng dữ liệu. | Sửa trang chủ. |
| `components/charts/` | **Các biểu đồ**: `CandlestickChart`, `ForecastChart`, `VerifiedForecastChart`, `EquityCurve`, `PriceChart`, `IndicatorChart`, `DashboardCharts`. | Thêm loại biểu đồ. |
| `components/backtesting/` | `SingleSymbolBacktest`, `MultiSymbolWalkForward`. | Sửa trang backtest. |
| `components/quality/` | `QualityGatePanel` — hiển thị 7 lần kiểm tra chất lượng. | Sửa hiển thị quality gate. |
| `components/agent/` | Khung chat AI: `ChatBox`, `ChatMessage`, `Markdown`, `ToolCallDisplay`. | Sửa giao diện chat. |
| `components/common/` | Thành phần dùng chung: `EmptyState`, `ErrorState`, `Loading`, `PageTitle`, `Explainer`, bộ chọn khoảng thời gian. | Thêm UI tái sử dụng. |
| `components/ui/` | Nút, thẻ, input, select, badge, skeleton... (phong cách chung). | Chuẩn hoá giao diện. |
| `components/market/` | Chuyển đổi khoảng thời gian. | — |
| `lib/i18n.tsx` | Hệ thống đa ngôn ngữ (Việt/Anh). | Thêm chuỗi dịch. |
| `lib/utils.ts` | Hàm tiện ích chung (merge class CSS...). | — |
| `types/` | Kiểu TypeScript cho dữ liệu API. | Thêm trường mới. |
| `utils/format.ts` | Định dạng số, ngày, tiền tệ. | — |
| `utils/resample.ts` | Gom nến theo khoảng thời gian. | — |
| `utils/constants.ts` | Hằng số dùng chung. | — |

---

## 0.6. Chi tiết: `docs/` — tài liệu

| File | Nội dung | Dành cho |
|---|---|---|
| `HUONG_DAN_NGUOI_MOI.md` | **Bắt đầu từ đây nếu chưa biết chứng khoán lẫn công nghệ.** Giải thích nghiệp vụ (cổ phiếu, OHLCV, backtest, walk-forward), luồng dữ liệu, quan hệ giữa các thành phần, ví dụ và use case. | Người mới |
| `HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md` | **Tài liệu luận văn chính** (~4.696 dòng). Toàn bộ kiến trúc, số đo, sẵn sàng bảo vệ. | Bảo vệ đồ án |
| `SO_DO_MINH_HOA.md` | Sơ đồ minh hoạ bằng ASCII từng phần hệ thống. | Bảo vệ đồ án |
| `CODE_EXPLAINED_FOR_BEGINNER.md` | Giải thích từng đoạn code (dành cho người đã biết Python). | Đọc code lần đầu |
| `NGHIEN_CUU_DA_MA_WALK_FORWARD.md` | Nghiên cứu chi tiết về walk-forward. | Bảo vệ phần backtest |
| `QA_KIEM_THU_CHUYEN_SAU.md` | Nhật ký QA từng lần sửa lỗi (triệu chứng → nguyên nhân → fix → bằng chứng). | Điều tra lỗi |
| `data_verification.md` | **Bằng chứng dữ liệu thật**: đối chiếu từng tầng, ảnh chụp màn hình, số đo. | Chứng minh không fake data |
| `lakehouse.md` | Cách tầng Bronze/Silver/Gold hoạt động. | Hiểu dữ liệu |
| `data_sources.md` | Từng nhà cung cấp dữ liệu, ưu/nhược điểm. | Hiểu nguồn dữ liệu |
| `architecture.md` | Kiến trúc tổng thể. | Hiểu hệ thống |
| `tech_stack_matrix.md` | Bảng công nghệ dùng ở đâu. | Bảo vệ đồ án |
| `ai_agent.md` | Cách trợ lý AI hoạt động, tool registry. | Hiểu AI agent |
| `database.md` | Cấu trúc DB, các bảng. | Hiểu DB |
| `daily-ingest-setup.md` | Cài lịch ingest hằng ngày. | Vận hành |
| `CI.md` | Định nghĩa CI. | Vận hành |
| `OPERATIONS_RAM.md` | Quản lý RAM (Windows không có pagefile). | Khi máy chậm |
| `exports/` | Mẫu CSV dữ liệu Gold thật (AAPL/JPM/NVDA). | Minh hoạ dữ liệu |
| `notebooks/` | Notebook demo lakehouse. | Thử nhanh |

---

## 0.7. Chi tiết: `scripts/` — công cụ bảo trì

| Thư mục / file | Tác dụng |
|---|---|
| `scripts/docs/remove_emoji.py` | Xoá emoji khỏi `docs/`, giữ khung ASCII thẳng. |
| `scripts/docs/align_ascii_diagrams.py` | Căn lại các hàng trong khung ASCII. |
| `scripts/docs/check_ascii_diagrams.py` | Báo cáo hàng lệch khung (chạy sau khi vẽ sơ đồ). |
| `scripts/docs/fix_mojibake.py` | Khôi phục file tiếng Việt bị lỗi mã hoá. |
| `scripts/system/check-running.ps1` | Xem process nào đang chạy (uvicorn, vite) và cổng nào đang mở. |
| `scripts/system/flush_standby_cache.py` | Đẩy cache RAM xuống standby list (cần Admin). |
| `scripts/system/purge_standby_list.py` | Xoá hẳn standby list khỏi RAM (cần Admin). |

---

## 0.8. Bảng tra nhanh: "Tôi muốn sửa X — mở file nào?"

| Tôi muốn... | Mở file |
|---|---|
| Thêm/sửa một API endpoint | `backend/app/api/v1/endpoints/<nhóm>.py` |
| Biết tất cả route đang có | `backend/app/api/v1/router.py` |
| Sửa cách tính chỉ báo | `backend/app/indicators/` |
| Sửa mô hình dự báo | `backend/app/forecasting/<model>.py` |
| Sửa logic khớp lệnh backtest | `backend/app/backtesting/simulator.py` |
| Sửa cách tính lợi nhuận | `backend/app/backtesting/metrics.py` |
| Sửa cách rửa dữ liệu | `backend/app/lakehouse/silver.py` |
| Sửa cách tính đặc trưng | `backend/app/features/` |
| Thêm nhà cung cấp dữ liệu | `backend/app/data_sources/` + `factory.py` |
| Sửa giao diện trang chủ | `frontend/src/pages/Dashboard.tsx` |
| Thêm trang mới | `frontend/src/pages/` + `frontend/src/App.tsx` |
| Sửa cách gọi API từ web | `frontend/src/api/client.ts` |
| Thêm tool cho trợ lý AI | `backend/app/agent/tools/` + `tool_registry.py` |
| Sửa đường dẫn dữ liệu | `backend/app/lakehouse/storage_factory.py` |
| Đổi cấu hình | `backend/.env.local` (máy) hoặc `backend/.env.local.example` (mẫu) |
| Thêm bước kiểm tra chất lượng | `backend/app/core/quality_gate.py` |
| Viết test | `backend/tests/test_<tên>.py` |
| Chạy pipeline nền | `backend/app/services/auto_refresh.py` + `backend/crontab` |

---

## 0.9. Quy tắc "đừng xoá"

| Đường dẫn | Lý do |
|---|---|
| `minio_data/` | Dữ liệu lịch sử giá **thật**. Xoá = mất toàn bộ lakehouse. |
| `backend/.env.local` | Cấu hình thật của máy (cổng relay, storage backend). |
| `backend/data/models/` | **Model đã huấn luyện** (1.025 model: 1.003 linear_regression, 16 arima, 6 lstm). Model registry đọc từ đây, KHÔNG có trong MinIO. **Đừng xoá.** |
| `backend/data/backtests/` | Kết quả backtest đã chạy. Đừng xoá nếu còn trích dẫn. |
| `backend/data/sample/` | Mẫu dữ liệu để test khi không có mạng. |
| `backend/docs/vn_quality_reports/` | 53 báo cáo chất lượng dữ liệu Việt Nam, tài liệu có trích dẫn. |
| `backend/tests/_system_audit.py` | `presentation.md` có trích dẫn. |
| `backend/tests/_build_health_md.py` | Sinh báo cáo `system_health.md` cho `_system_audit.py` (file sinh ra, không commit). |
| `backend/app/lakehouse/spark_session.py` | Đường dẫn dự phòng (tắt mặc định), xoá thì mất tính năng. |

## 0.10. Quy tắc "được xoá"

| Đường dẫn | Lý do |
|---|---|
| `backend/logs/*` (trừ `.gitkeep`) | Log runtime, tự tạo lại. Đã dọn 346 file / 42 MB ngày 16/11/2026. |
| `backend/data/*.log`, `*.err` | Log cũ nằm nhầm trong thư mục dữ liệu. |
| `*.log`, `*.err`, `*.out` ở gốc repo/backend/frontend | Log dev cũ. |
| `frontend/dist/` | Kết quả build, `npm run build` tạo lại. |
| `__pycache__/`, `.pytest_cache/` | Cache Python. |
| `scripts/__pycache__/` | Cache Python (chứa cả `.pyc` của script cũ). |
| `.sentry-native/` | File tạm của Sentry CLI. |
| `backend/tests/_av_test*.json`, `_fh_*.json` | Kết quả probe API tạm (lỗi API key) — dữ liệu rác. |
| `backend/data/gold_features/`, `backend/data/quality/` | Thư mục rỗng, không code nào tham chiếu. |
| `backend/data/bronze/`, `backend/data/silver/`, `backend/data/gold/` | Bản sao cục bộ — đã xoá 16/11/2026 (9,03 GB). Dữ liệu vẫn đầy đủ trong MinIO. |
| `backend/data/models/*/YEAR=*/` | Rác tạo nhầm — 9.532 thư mục chứa 326.347 thư mục con rỗng, 0 byte. Không code nào tham chiếu. |
| `backend/data/_tmpmulti.py` | Script in thử JSON, không dùng lại. |

> **Lưu ý:** mọi thư mục bị xoá đều đã được kiểm tra bằng `git check-ignore` hoặc
> `grep` để xác nhận không có code/tài liệu nào tham chiếu tới.

### 0.10.1. Một điểm nghẽn đã tìm ra và sửa (đo ngày 16/11/2026)

`pytest tests/test_no_missing_imports.py` mất **127 giây**. Nguyên nhân: file test
dùng `Path.rglob("*.py")` trên toàn bộ `backend/`, mà `rglob` **vẫn đi vào**
thư mục `backend/data/` (bản sao cục bộ của lakehouse — hàng trăm nghìn file
Parquet) rồi mới lọc kết quả.

Đã sửa bằng `os.walk` (cắt tỉa thư mục con ngay trong `dirnames`, không bao giờ
bước vào). Kết quả: **127,5 s → 2,6 s** (nhanh gấp 48 lần), 285 test, 0 failure.

Cái được sửa không chỉ là tốc độ: trước đây **số test phụ thuộc vào việc máy còn
bao nhiêu file dữ liệu trên đĩa**, nên hai máy khác nhau ra số test khác nhau.
Sau khi sửa, con số này ổn định và tái lập được.

Ngoài ra: `git config core.autocrlf` chuyển từ `true` → `input`, khớp với
`.gitattributes` (`*.py text eol=lf`) — hết cảnh báo "CRLF will be replaced by LF"
khi git so sánh file.

---

## 0.11. Lệnh kiểm tra nhanh

```powershell
# Chạy hết test
cd backend; .\.venv\Scripts\python.exe -m pytest tests -q

# Kiểm tra dữ liệu thật
cd backend
.\.venv\Scripts\python.exe tests\verify_real_data.py
.\.venv\Scripts\python.exe scripts\check_layer_divergence.py

# Chạy quality gate
curl http://127.0.0.1:8000/api/v1/quality/gate

# Xem API nào đang có
curl http://127.0.0.1:8000/openapi.json

# Quét dữ liệu giả (phải ra 0 kết quả)
rg -n "random\.(uniform|randint|choice)|np\.random\.(rand|normal|uniform)" backend/app
rg -n "mock|fake|dummy|synthetic|Math\.random" frontend/src
```

---

## 0.12. Bảng thay đổi tài liệu này

| Ngày | Thay đổi |
|---|---|
| 16/11/2026 | Tạo file lần đầu. Đồng thời dọn dẹp: 346 file log (42 MB), 9 file probe JSON, 2 thư mục rỗng, `.sentry-native`, `__pycache__`; tổ chức lại `scripts/` thành `docs/` và `system/`; sửa điểm nghẽn quét file trong `test_no_missing_imports.py` (127 s → 2,6 s); sửa 3 link chết trong `README.md` và 2 link chết trong `docs/`; đồng bộ `Makefile` với việc Kafka/Iceberg đã bị gỡ. |
| 16/11/2026 (lần 2) | Xoá bản sao cục bộ `backend/data/{bronze,silver,gold}` (**9,03 GB**) và 326k thư mục rỗng `models/*/YEAR=*/`; giữ lại 1.025 model đã huấn luyện (đã backup ra `D:\School\kltn\stock-lakehouse-models-backup`). Rebuild Silver/Gold cho `BTC-USD`/`ETH-USD` — `layer_agreement` trở lại `passed` (1.002 mã). |
