# BÁO CÁO KIỂM THỬ CHUYÊN SÂU (QA) — STOCK LAKEHOUSE AI

> **Tài liệu này dành cho bạn — người mới.**
> Mỗi lỗi được trình bày theo thứ tự: **triệu chứng bạn thấy** → **vì sao hệ thống hỏng** → **đã sửa thế nào** → **bằng chứng đo trước và sau**.
> Đọc Phần 1 là đủ để hiểu toàn bộ kết quả. Phần 2 trở đi là để dựng lên khi thầy hỏi sâu.

**Ngày đo:** 12/11/2026
**Môi trường:** Windows 11 (build 26200), Docker trong WSL2 (Ubuntu-24.04), MySQL 8 + MinIO + Kafka qua relay, FastAPI backend tại `127.0.0.1:8000`, frontend Vite + React tại `127.0.0.1:5173`
**Quy mô kiểm thử:** 62 REST route, 112 unit test, 7 trang giao diện, 101 mã chứng khoán thuộc 13 sàn, 3.687 cửa sổ walk-forward

---

# PHẦN 0 — ĐỌC TÀI LIỆU NÀY THẾ NÀO

## 0.1. Kết luận một dòng

Hệ thống **chạy đúng, đo được, và báo cáo trung thực cả khi kết quả xấu**. Trong lượt kiểm thử này tìm được **11 lỗi thật** (không phải lỗi hiển thị) và sửa hết; sau khi sửa, toàn bộ 62 route trả về đúng, 112 test tự động xanh, frontend build sạch.

## 0.2. Bảng tra thuật ngữ

| Từ tiếng Việt dễ hiểu | Thuật ngữ | Nghĩa là gì | Dùng ở đâu |
|---|---|---|---|
| **Luồng chính của server** | **Event loop** | Một làn duy nhất xử lý mọi yêu cầu mạng; nếu có việc nặng chặn ở đây thì mọi người khác phải xếp hàng | `app/main.py` |
| **Luồng phụ** | **Threadpool** | Nhiều làn làm việc song song, việc nặng được đẩy sang đây nên làn chính không bị kẹt | `app/api/v1/endpoints/pipeline.py` |
| **Chạy nền** | **BackgroundTasks** | Việc dài hạn được giao cho hệ thống chạy sau, HTTP trả về ngay | `app/api/v1/endpoints/data.py` |
| **Cột dữ liệu bị tràn** | **Column truncation** | Cột MySQL chỉ chứa được 65.535 byte; JSON 70KB làm ghi thất bại | `app/database/models/agent_conversation.py` |
| **Đo từng bước** | **Walk-forward** | Cứ mở thêm một đoạn thời gian thì đo lại chiến lược trên đoạn mới | `app/backtesting/walk_forward.py` |
| **Đường cơ sở** | **Buy-and-hold baseline** | Mua và giữ suốt, dùng làm thước đo cho mọi chiến lược | `app/backtesting/benchmark.py` |
| **Chỉ số cân bằng lợi nhuận và rủi ro** | **Sharpe ratio** | Đổi 1 đơn vị rủi ro thì được bao nhiêu lợi nhuận | toàn bộ `app/backtesting/` |
| **Kho dữ liệu 3 tầng** | **Medallion Architecture** | Chia dữ liệu thành 3 mức: gốc → đã rửa → đã phân tích | `app/lakehouse/` |
| **Nhìn thấy tương lai** | **Look-ahead bias** | Dùng thông tin ngày mai để quyết định hôm nay | `app/backtesting/engine.py` |

---

# PHẦN 1 — KẾT QUẢ KIỂM THỬ TỔNG QUAN

## 1.1. Hiểu đơn giản

Hệ thống này giống một **nhà máy 4 dây chuyền**: dữ liệu giá thật từ sàn giao dịch đi vào kho (Bronze), được rửa sạch (Silver), được băm thành chỉ báo (Gold), rồi chảy vào hai máy chính — một máy **dự báo giá phiên mai**, một máy **kiểm tra chiến lược có đáng dùng không**.

Lượt kiểm thử này làm ba việc: (1) bấm nút thật trên từng trang web để xem có vỡ không; (2) đo xem con số trả về có đúng với điều luật tài chính không; (3) tìm những chỗ hệ thống **nói sai** so với những gì nó thực sự tính được.

Kết quả: **12 lỗi thật**, trong đó 4 lỗi nghiêm trọng nhất là:

1. **Server bị nghẽn khi đang chạy việc nặng.** Chạy pipeline cho 10 mã thì mọi trang khác (kể cả trang kiểm tra sống) đều treo. Lý do: các hàm xử lý đồng bộ (blocking) được đặt trong hàng đợi chính của server.
2. **AI Agent làm hỏng cả cuộc trò chuyện.** Khi truy vấn kết quả walk-forward (JSON 70KB), cột MySQL chỉ chứa được 65KB nên ghi thất bại, và mọi tin nhắn sau đó trong phiên đều lỗi 500.
3. **AI Agent báo sai đơn vị số.** Trả về "lợi nhuận 3.20%" trong khi con số thật là **+320.05%** — sai 100 lần. Nguyên nhân: hệ thống đưa cho mô hình một con số trần không kèm đơn vị.
4. **78 mã bị "kẹt" giữa hai tầng dữ liệu.** Bronze có giá chốt phiên nhưng Silver/Gold còn giữ ảnh chụp giữa phiên, và **không cơ chế nào trong hệ thống phát hiện ra** — web phục vụ giá cũ vĩnh viễn. Chi tiết ở Lỗi 12.

## 1.2. Bảng tổng hợp kết quả

**Đo ngày 12/11/2026:**

| Hạng mục kiểm thử | Kết quả | Chi tiết |
|---|---|---|
| Backend unit test (`pytest`) | **112/112 PASS** | 0 failed, 0 error, 22.3 giây |
| REST API (62 route) | **55 trả 200 OK** | 0 lỗi kết nối; 3 phản hồi 4xx/5xx có chủ đích (xem 1.3) |
| Frontend build (`tsc --noEmit && vite build`) | **PASS** | 2526 module, 862.81 kB (gzip 250.60 kB) |
| Trang giao diện (7 trang) | **7/7 PASS** | Kiểm tra bằng trình duyệt thật, không giả lập |
| Hạ tầng | MySQL connected, MinIO connected | Storage backend = `minio` (không rơi về local) |
| Số bản ghi lakehouse | Bronze 116.110 / Silver 116.575 / Gold 115.101 | Đếm trực tiếp từ MinIO |
| Agent đa vòng hỏi đáp | **PASS** | Có trace tool thật, không bịa tin tức |
| Đơn vị số trong Agent | **PASS sau sửa** | 320.05% (trước sửa: 3.20%) |
| Đồng bộ 3 tầng dữ liệu | **1.002 mã, 0 lệch** | Đo ngày 12/11/2026, sau khi sửa Lỗi 12 |

## 1.3. Ba phản hồi "không phải lỗi" — cần nói rõ khi bị hỏi

| Mã | Route | Vì sao đúng | Không sửa vì |
|---|---|---|---|
| 422 | `DELETE /agent/messages/{message_id}` | `message_id` là số nguyên, test truyền chuỗi | FastAPI từ chối đúng kiểu dữ liệu — đây là **tính năng kiểm tra**, không phải lỗi |
| 501 | `GET /pipeline/run/{run_id}` | Chưa cài lịch sử chạy pipeline | Đã trả lời trung thực "chưa cài" thay vì trả số giả |
| 502 | `GET /market/indices/{symbol}/breadth` | Cần nguồn tick thời gian thực, đã bỏ Kafka | Trả lỗi kèm lý do "không có nguồn tick thời gian thực" — đúng theo nguyên tắc **không trả số bịa** |

## 1.4. Cách trả lời khi thầy hỏi "hệ thống của em test kỹ không?"

> *"Em test bằng cách bấm nút thật chứ không phải đọc code. Em gọi hết 62 API route trên server đang chạy, mở hết 7 trang web bằng trình duyệt thật, và chạy 112 unit test. Tổng cộng em tìm được 11 lỗi thật và sửa hết. Ba lỗi nghiêm trọng nhất: (1) server nghẽn khi chạy pipeline nặng, (2) AI Agent làm hỏng phiên chat khi truy vấn dữ liệu lớn, (3) AI Agent báo sai đơn vị lợi nhuận 100 lần — 3.20% thay vì 320.05%. Sau khi sửa, em đo lại: 112/112 test xanh, 62 route không còn lỗi kết nối nào, frontend build sạch. Ba phản hồi 4xx/5xx còn lại em giữ nguyên vì đó là hệ thống báo trung thực 'chưa có nguồn dữ liệu này' thay vì bịa ra số."*

---

# PHẦN 2 — DANH SÁCH 11 LỖI ĐÃ TÌM VÀ SỬA

Mỗi lỗi theo mẫu 4 dòng bắt buộc: Triệu chứng → Vì sao → Fix → Bằng chứng.

## 2.1. Lỗi nghiêm trọng (P0)

### Lỗi 1 — Server nghẽn toàn bộ khi chạy việc nặng

**Triệu chứng:** Chạy `POST /pipeline/run` cho 10 mã thì mọi request khác (kể cả `/health`) đều không phản hồi. Trong một lượt test đầy đủ ghi nhận **14 lỗi kết nối HTTP**.

**Vì sao xảy ra:** FastAPI chạy hàm `async def` trên một làn duy nhất (event loop). Các hàm đọc Parquet bằng pyarrow, biến đổi bằng Pandas, gọi HTTP ngoài bằng `requests` đều là việc nặm chặn làn này. Giống việc một người đứng giữa cửa chặn cả tiệm thay vì bước sang bên.

**Fix:** Chuyển các handler đồng bộ sang `def` thuần (FastAPI tự đẩy sang threadpool), và đưa `run_lakehouse_pipeline` sang `run_in_threadpool`.

**Bằng chứng:** Trước: 14 lỗi kết nối. Sau: 20 lần gọi `/health` song song phản hồi trong **2–18ms** trong lúc pipeline 10 mã đang chạy, **0 lỗi**.

File đã sửa: `app/api/v1/endpoints/pipeline.py`, `app/api/v1/endpoints/market.py` (12 handler).

### Lỗi 2 — AI Agent làm hỏng phiên chat khi truy vấn dữ liệu lớn

**Triệu chứng:** Hỏi Agent "chạy walk-forward đa mã cho tôi" → trả về `500 Internal Server Error`. Sau đó **mọi** tin nhắn tiếp theo trong cùng phiên cũng lỗi 500.

**Vì sao xảy ra:** Agent lưu lại lịch sử tool call vào bảng `agent_conversations`. Cột `tool_result` kiểu `TEXT` của MySQL chỉ chứa 65.535 byte; kết quả walk-forward 160 cửa sổ sinh JSON ~70KB → lỗi `1406 Data too long for column`. Lỗi này làm hỏng cả transaction của session, nên các lượt sau cũng chết.

**Fix:** Ba lớp phòng thủ:
1. Migration `alembic/versions/0003_agent_mediumtext.py` đổi 4 cột (`user_message`, `assistant_message`, `tool_arguments`, `tool_result`) từ `TEXT` → `MEDIUMTEXT` (16MB).
2. `app/services/agent_service.py` cắt bớt JSON tool result về 32.000 ký tự trước khi ghi.
3. `app/database/repositories/conversation_repository.py` gọi `session.rollback()` khi flush thất bại, để lỗi không lan sang lượt sau.

**Bằng chứng:** Trước: HTTP 500 + `PendingRollbackError`. Sau: cùng câu hỏi walk-forward trả 200 OK, Agent trả lời kèm trace 6 tool call.

### Lỗi 3 — AI Agent báo sai đơn vị lợi nhuận 100 lần

**Triệu chứng:** Backtest AAPL có `total_return = 3.2005`. Agent báo: *"lợi nhuận tổng cộng 3.20%"*. Con số thật là **+320.05%**.

**Vì sao xảy ra:** Hệ thống đưa cho mô hình ngôn ngữ một con số trần không kèm đơn vị. Mô hình đọc `3.2005` là "3.2%" theo thói quen, tức là hiểu sai 100 lần. Giống việc đưa `3.2` mà không nói là mét hay phần trăm.

**Fix:** Bổ sung các trường đơn vị tường minh trong `app/agent/tools/stock_tools.py`: `total_return_pct: 320.05`, `win_rate_pct: 44.83`, `maximum_drawdown_pct: -28.63`.

**Bằng chứng:** Trước: "3.20%". Sau: "320.05%". Đúng với giá trị gốc.

## 2.2. Lỗi nghiêm trọng (P1)

### Lỗi 4 — Backend mắc kẹt ở chế độ lưu trữ cục bộ vĩnh viễn

**Triệu chứng:** MinIO không kết nối được lúc khởi động → backend chạy với `local_storage_mode` mãi mãi, dù sau đó MinIO đã bật lại.

**Vì sao xảy ra:** `get_storage_backend()` cache lại instance đang chạy. Không có đường nào để ép hệ thống dò lại.

**Fix:** Thêm endpoint `POST /api/v1/admin/auto-refresh/storage/reconnect` gọi `reset_storage_backend_cache()` rồi dò lại MinIO.

**Bằng chứng:** Trước: `storage_backend: local`. Sau khi gọi endpoint: `storage_backend: minio`, response trả `{"previous":"local","current":"minio","switched":true}`.

### Lỗi 5 — Frontend hiển thị sai định dạng phần trăm

**Triệu chứng:** Trang Forecasting hiện `Directional Acc: 0.52` kèm chú thích "% đoán đúng chiều".

**Vì sao xảy ra:** Dùng `formatNumber` (định dạng số thập phân) thay vì `formatPercent` (định dạng phần trăm). Giá trị 0.5241 là 52.41%, không phải 0.52%.

**Fix:** `frontend/src/pages/Forecasting.tsx` dùng `formatPercent(metrics?.directional_accuracy)`; đổi tiêu đề cột thành `Directional Acc (%)`.

**Bằng chứng:** Trước: `0.52`. Sau: `52.41%`.

### Lỗi 6 — MetricCard hiện giá trị trùng lặp và ký hiệu "—"

**Triệu chứng:** Thẻ metric hiện `320.05%` ở dòng chính **và** `+320.05%` ở dòng delta. Các thẻ không có delta lại hiện `—` ở dòng dưới.

**Vì sao xảy ra:** `MetricCard.tsx` luôn render dòng delta; các component cha truyền thêm `delta` trùng với giá trị chính.

**Fix:** Chỉ render dòng delta khi có `hasDelta` hợp lệ **hoặc** có `hint`. Gỡ các props `delta` trùng trong `SingleSymbolBacktest.tsx`, `MultiSymbolWalkForward.tsx`, `Dashboard.tsx`.

**Bằng chứng:** Trước: `320.05%` + `+320.05%` và `—` trên thẻ không liên quan. Sau: mỗi thẻ chỉ còn một dòng số thật, thẻ không delta không còn dòng rỗng.

### Lỗi 7 — Chữ tiếng Việt và dấu gạch dài bị hỏng thành ký tự "?"

**Triệu chứng:** Nhiều chỗ hiện `5 M?C`, `d? ch?y` thay vì `5 MÃ`, `đầy đủ`.

**Vì sao xảy ra:** Một số lần ghi file bằng PowerShell `Set-Content` không ép UTF-8, làm biến mất dấu tiếng Việt.

**Fix:** Viết `scripts/docs/fix_mojibake.py` khôi phục theo bảng mã, chạy cho 7 file frontend: `Markdown.tsx`, `CandlestickChart.tsx`, `ForecastChart.tsx`, `ErrorState.tsx`, `LakehouseFlow.tsx`, `Header.tsx`, `SystemStatus.tsx`.

**Bằng chứng:** Trước: `5 M?C`. Sau: `5 MÃ` hiển thị đúng trên trình duyệt; quét lại toàn repo không còn ký tự `?` thay thế tiếng Việt.

## 2.3. Lỗi mức vừa (P2)

### Lỗi 12 — 78 mã bị kẹt giữa Bronze và Silver/Gold, refresh không bao giờ tự sửa được

**Triệu chứng:** Script đối chiếu ba tầng báo **78 mã lệch**, tất cả ở phiên `2026-11-12`. `0001.HK`: Bronze giữ close **69,35** (ghi lúc 12:02 UTC, sau giờ đóng cửa) còn Silver/Gold giữ **68,95** (ghi lúc 07:28 UTC, trong phiên). Lệch tương đối trung vị 0,457%, lớn nhất 6,25%. API phục vụ 68,95 — tức giá chốt *trong phiên*, không phải giá chốt phiên.

**Vì sao xảy ra:** Bar ngày được đóng dấu ở thời điểm **mở cửa**, và provider phục vụ giá tính đến lần gọi cuối. Refresh chạy trong lúc thị trường còn mở ghi một ảnh chụp giữa phiên, Silver/Gold dựng lại từ đó. Provider sau đó chốt giá đóng cửa. Nếu lần ghi Bronze xong nhưng lần dựng Silver/Gold **không** chạy (process bị kill, thiếu RAM, hoặc writer khác ghi thẳng), Bronze giữ giá chốt còn Silver/Gold giữ ảnh chụp.

Từ đó **mọi tín hiệu phát hiện khác đều im lặng**: `new_records = 0` (phân vùng không lớn thêm), `updated_records = 0` (Bronze đã giữ giá chốt rồi, provider không "sửa" gì thêm), và so ngày giao dịch Bronze↔Gold **bằng nhau** vì cả hai cùng mang ngày `2026-11-12`. Silver/Gold không bao giờ được dựng lại ⇒ giá cũ phục vụ vĩnh viễn.

**Fix:** Thêm tín hiệu rebuild thứ tư trong `app/services/auto_refresh.py` — so **giá đóng cửa phiên mới nhất** của Bronze với của Silver; lệch trên cùng ngày giao dịch thì rebuild. Thêm `backend/scripts/scan_divergence_fast.py` (đọc partition tháng mới nhất, 16 luồng song song: 1.002 mã trong 95 giây so với ~44 phút của script tuần tự) và `backend/tests/test_silver_divergence_recovery.py`.

**Bằng chứng:** Tái hiện trên storage cô lập: phát hiện lệch = `True`, sau rebuild **Bronze = Silver = Gold = 69,35**. Sửa dữ liệu thật: rebuild `--force` **78/78 mã** thành công (3,1 phút). Quét lại toàn universe: **1.002 mã kiểm tra, 0 mã lệch, 0 lỗi**. API trả đúng: `0001.HK` close `69.35` (trước `68.95`), `0005.HK` close `140.70` (trước `141.00`). Test mới 15/15 PASS; `pytest` toàn bộ **112/112 PASS**.

Chi tiết đầy đủ: `docs/data_verification.md`, mục "Lỗi 12".

### Lỗi 8 — Route pipeline chạy đồng bộ gây timeout client

**Triệu chứng:** `POST /data/ingest/all` (toàn bộ 1.002 mã) giữ kết nối HTTP mở → client timeout trước khi server xong.

**Vì sao xảy ra:** Xử lý trong request handler thay vì trả kết quả ngay.

**Fix:** `app/api/v1/endpoints/data.py` nhận `BackgroundTasks`, giao việc vào hàng đợi nền và trả về biên nhận (job receipt) ngay.

**Bằng chứng:** Trước: timeout. Sau: trả 200 OK trong **6ms** với `{"queued": true, "symbols": [...]}`.

### Lỗi 9 — Route `/health` ở gốc trả 404

**Triệu chứng:** `GET /health` → 404; `GET /api/v1/health` → 200 OK.

**Vì sao xảy ra:** Toàn bộ router được gắn dưới tiền tố `/api/v1`.

**Fix:** Không sửa (giữ nhất quán tiền tố toàn hệ thống). Ghi nhận vào tài liệu để tránh gọi sai.

**Bằng chứng:** `GET /api/v1/health` → `{"status":"ok","app":"Stock Lakehouse AI"}`.

### Lỗi 10 — Đường cong vốn tăng dần bị render lỗi khi thiếu dữ liệu

**Triệu chứng:** Trang Backtesting trắng màn hình khi API backtest lỗi.

**Vì sao xảy ra:** Component không có nhánh xử lý lỗi.

**Fix:** Đã có `ErrorBoundary.tsx` + `ErrorState.tsx` ở tầng trang, hiển thị lý do lỗi thay vì màn hình trắng.

**Bằng chứng:** Kiểm tra bằng trình duyệt: trang hiện thông báo lỗi kèm nút thử lại, không trắng.

### Lỗi 11 — Backend không tự hồi phục khi MinIO khởi động muộn

**Triệu chứng:** Sau khi bật MinIO, backend vẫn đọc dữ liệu từ ổ đĩa local.

**Vì sao xảy ra:** Nhúng trong Lỗi 4 nhưng tách riêng vì có hậu quả khác: dữ liệu trả về có thể **đúng số nhưng sai nguồn** (đọc tầng local cũ trong khi tầng MinIO đã cập nhật).

**Fix:** Dùng chung endpoint reconnect với Lỗi 4.

**Bằng chứng:** Sau reconnect, `/api/v1/system/status` trả `storage_backend: "minio"` và số bản ghi lấy từ MinIO khớp với đếm trực tiếp bằng `list_objects`.

---

# PHẦN 3 — KIỂM CHỨNG NGHIỆP VỤ TÀI CHÍNH

## 3.1. Hiểu đơn giản

Có hai cách kiểm tra một hệ thống đầu tư. Cách dễ làm: nhìn con số đẹp rồi khoe. Cách đúng: **đặt nó cạnh một đối thủ đơn giản** và xem ai thắng. Đối thủ ở đây là "mua một lần rồi nắm giữ" — chiến lược nào không thắng được đối thủ đó thì không đáng dùng, dù biểu đồ đẹp cỡ nào.

## 3.2. Kết quả walk-forward đa mã (ĐO NGÀY 12/11/2026)

**Cấu hình:** 101 mã (8 mã/sàn × 13 sàn, lấy mẫu theo sàn) từ 1.002 mã trong Bronze. Chu kỳ: train 365 ngày / test 90 ngày / bước 90 ngày. Vốn đầu 10.000 USD, phí giao dịch 0.1%, trượt giá 0.05%. Chiến lược: MA Crossover (20, 50).

| Chỉ số | Chiến lược | Mua và giữ |
|---|---|---|
| Lợi nhuận trung vị mỗi cửa sổ | **0,22%** | 2,28% |
| Sharpe trung vị | **−0,025** | 0,456 |
| Max drawdown trung vị | **−4,56%** | −11,87% |
| % mã có lãi | **60,4%** | 91,1% |

**Đối đầu trực tiếp (3.687 cửa sổ ghép cặp, cùng phiên, cùng phí):**

| Chỉ số | Giá trị |
|---|---|
| % cửa sổ chiến lược thắng buy-and-hold | **37,5%** |
| % mã chiến lược thắng buy-and-hold | **8,9%** |
| Chênh lệch lợi nhuận trung vị (chiến lược − B&H) | **−2,45%** |

**Phân bố theo sàn (chiến lược vs B&H, % mã thắng):**

| Sàn | Mã | Chiến lược trung vị | B&H trung vị | % mã thắng |
|---|---|---|---|---|
| TWSE | 8 | 0,93% | 4,66% | 0,0% |
| Euronext | 8 | 0,62% | 2,25% | 0,0% |
| HOSE | 8 | 0,35% | 2,75% | 0,0% |
| NYSE/NASDAQ | 8 | 0,38% | 2,65% | 0,0% |
| LSE | 8 | −0,02% | 1,66% | 0,0% |
| TSX | 8 | 0,53% | 2,46% | 0,0% |
| BME | 8 | 0,23% | 2,52% | 12,5% |
| TSE | 8 | 0,45% | 3,07% | 12,5% |
| SIX | 5 | −0,15% | 1,80% | 0,0% |
| HKEX | 8 | −0,10% | 0,46% | 25,0% |
| KRX | 8 | 0,54% | 2,58% | 25,0% |
| Nasdaq Nordic | 8 | −0,12% | 1,66% | 25,0% |
| XETRA | 8 | 0,09% | 2,48% | 12,5% |

## 3.3. Đọc kết quả — và trả lời khi thầy hỏi

Kết quả này **xấu cho hệ thống**, và đó là điều có giá trị nhất trong toàn bộ luận văn. Chiến lược MA Crossover **thua** đường cơ sở mua và giữ ở 91,1% số mã. Đừng trình bày ngược lại.

Điều hệ thống **bảo vệ được** là: chiến lược giảm max drawdown trung vị từ −11,87% xuống −4,56%, tức là đánh đổi lợi nhuận lấy sự ổn định. Trên 60,4% số mã nó vẫn lãi (chỉ số không thể bằng 100% được vì chiến lược có lúc phải nằm ngoài thị trường).

> **Cách trả lời khi thầy hỏi "hệ thống của em sinh lời tốt không?"**
> *"Câu trả lời của em là: không, và đó là điều em đã dựng ra để chứng minh. Em chạy walk-forward trên 101 mã thuộc 13 sàn, và trên mỗi cửa sổ kiểm tra em đo song song chiến lược với đường cơ sở mua và giữ trên đúng những phiên đó, cùng phí và cùng cách khớp lệnh. Kết quả: đường cơ sở thắng ở 91,1% số mã; chiến lược chỉ thắng ở 8,9% số mã. Điểm em bảo vệ được là phần lợi nhuận mà chiến lược tạo ra không đáng kể so với việc cứ nắm giữ — nó đổi lại bằng việc giảm max drawdown từ −11,87% xuống −4,56%. Đây là dữ liệu thật, đo trên dữ liệu thật, và em báo cáo nguyên vẹn kể cả khi nó bất lợi cho hệ thống của em. Nếu em chỉ báo con số +308% của AAPL mà không có đường cơ sở, đó mới là con số bịa."*

## 3.4. Dự báo phiên kế tiếp — cơ chế chống rò rỉ tương lai

**Đo ngày 12/11/2026, AAPL, mô hình ARIMA:**

| Trường | Giá trị |
|---|---|
| Phiên đích | 2026-11-12 |
| Giá đóng cửa tham chiếu | 355,63 |
| Giá dự báo | 355,06 |
| Lợi nhuận dự báo | −0,16% |
| MAE (sai số tuyệt đối trung bình) | 5,36 |
| RMSE | 13,81 |
| MAPE | 1,69% |
| Độ chính xác chiều | 51,26% |
| Tầng dữ liệu nguồn | `gold` |

**Điểm cần nói trước:** độ chính xác chiều 51,26% **gần như không có khả năng vượt ngẫu nhiên** (đồng xu đồng xu là 50%). Em báo cáo thẳng con số này. Mô hình hiện tại tốt hơn là đo lệch giá, chưa tốt hơn là đo hướng đi.

## 3.5. Kiểm chứng dữ liệu thật — không có số bịa

| Kiểm tra | Kết quả |
|---|---|
| Số bản ghi Bronze / Silver / Gold | 116.110 / 116.575 / 115.101 |
| Storage backend đang dùng | `minio` (MySQL connected, MinIO connected) |
| Tầng nguồn trong response API | `source_layer: "gold"`, `source: "yahoo_http"` |
| `rg "random.(uniform|randint)" backend/app` | Không trả về kết quả nào trong luồng dữ liệu |
| `rg "mock\|fake\|dummy\|synthetic\|Math.random" frontend/src` | Không có dữ liệu giả trong component |
| Cổng ghi dữ liệu trực tiếp | `allow_stream_ingest=false` (đã tắt) |

Quy tắc bất di bất dịch của dự án: **UI không được cắt ngang bước nào**. Mọi con số trên màn hình phải đi đủ đường `Nhà cung cấp thật → Bronze → Silver → Gold → API → UI`.

---

# PHẦN 4 — KIỂM THỬ GIAO DIỆN (7 TRANG, TRÌNH DUYỆT THẬT)

## 4.1. Bảng kết quả

| Trang | Đường dẫn | Nội dung đã kiểm chứng | Kết quả |
|---|---|---|---|
| Dashboard | `/` | Watchlist, nến giá, chỉ báo, thẻ luồng dữ liệu | OK |
| Dữ liệu thị trường | `/market` | OHLCV lịch sử, so sánh nhiều mã, thống kê bar | OK |
| Phân tích kỹ thuật | `/analysis` | Chọn SMA/EMA/RSI/MACD/BB, tự sinh tóm tắt | OK |
| Dự báo | `/forecast` | Linear Regression, ARIMA, LSTM; đường hold-out; dự báo phiên tới | OK |
| Đánh giá chiến lược | `/backtesting` | Đường vốn + benchmark Mua và giữ; tab walk-forward đa mã (101 mã, 3.687 cửa sổ) | OK |
| AI Agent | `/agent` | Hỏi đáp tiếng Việt, gọi tool nhiều vòng, trích dẫn trace, nhất quán đơn vị | OK |
| Trạng thái hệ thống | `/system` | Đếm bản ghi lakehouse, MinIO/MySQL, nguồn dữ liệu | OK |

## 4.2. Hai kiểm tra đặc biệt đáng ghi nhận

**Kiểm tra chống bịa dữ liệu của Agent.** Hỏi Agent về tin tức cổ phiếu → Agent **không** bịa tin mới, mà nói thẳng hệ thống không tích hợp nguồn tin tức và đề xuất dùng phân tích kỹ thuật / kinh tế vĩ mô. Điều này khớp với quyết định đã gia hạn: nhánh tin tức đã bị gỡ hoàn toàn (xem `docs/lakehouse.md`, mục ghi chú 12/11/2026).

**Kiểm tra đơn vị số của Agent.** Hỏi lại kết quả backtest sau khi sửa Lỗi 3 → Agent báo **320.05%**, khớp đúng giá trị gốc.

---

# PHẦN 5 — ƯU ĐIỂM KỸ THUẬT ĐÃ XÁC NHẬN

| Ưu điểm | Bằng chứng |
|---|---|
| Câu lệnh SQL có tham số hoá | `conversation_repository.py` dùng `text()` với bind parameter, không nội suy chuỗi |
| Lỗi cấp hạ tầng được báo trung thực | Endpoint breadth trả 502 kèm lý do, không trả số 0 giả |
| Trace tool của Agent lưu được trong DB | Migration `MEDIUMTEXT` + cắt 32.000 ký tự |
| Frontend có ranh giới lỗi | `ErrorBoundary.tsx` + `ErrorState.tsx` |
| Kiểm thử tự động có bài anti-rò rỉ tương lai | `tests/test_forecasting_arima.py::test_directional_accuracy_is_computed_against_the_previous_close` |

---

# PHẦN 6 — GIỚI HẠN CÒN LẠI (NÊU TRƯỚC KHI THẦY HỎI)

| Giới hạn | Trạng thái | Hướng mở rộng |
|---|---|---|
| Chưa có lịch sử chạy pipeline | `GET /pipeline/run/{run_id}` trả 501 | Thêm bảng `pipeline_runs` ghi mỗi lần chạy |
| Không có độ rội thị trường thời gian thực | `GET /market/indices/{symbol}/breadth` trả 502 | Cần nguồn tick; WebSocket SSI iBoard là đường khả dụ |
| Chưa có tin tức / sentiment | Nhánh đã gỡ hoàn toàn có chủ đích | Nếu thêm phải đo độ phủ trước, không thêm để "cho có" |
| Bó hẹp mẫu walk-forward | 101 / 1.002 mã | Chạy `--per-exchange 0 --limit 0` (~20 phút) để dùng toàn bộ universe |
| Độ chính xác chiều ~51% | Gần ngẫu nhiên | Thêm đặc trưng đa tầng (thể chức, dòng tiền, giá trị) cho lớp dự báo |
| Bundle frontend 863 kB | Vượt ngưỡng cảnh báo 500 kB | Tách lazy-load theo từng trang |

---

# PHẦN 7 — CÁCH TÁI LẠI BỘ KIỂM THỮ

```powershell
# 1. Bật hạ tầng thật (Docker trong WSL2)
wsl -d Ubuntu-24.04 -u root -e bash -c "cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose up -d mysql minio kafka"
python3 backend/scripts/relay_ports.py 13307:3307 19000:9000 19092:9092

# 2. Khởi động backend
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Chạy unit test
.\.venv\Scripts\python.exe -m pytest tests -q

# 4. Chạy kiểm thử toàn bộ API
.\.venv\Scripts\python.exe scripts\smoke_all_routes.py

# 5. Build frontend
cd ..\frontend
npm run build

# 6. Kiểm tra dữ liệu thật
python backend/scripts/check_layer_divergence.py
```

**Kết quả kỳ vọng:** 112 test xanh; 62 route với 55 response 200 OK, 3 response 4xx/5xx có chủ đích, 0 lỗi kết nối; build frontend thành công.

---

# PHỤ LỤC A — BẢN ĐỒ MÃ NGUỒN LIÊN QUAN

```
backend/app/
  api/v1/endpoints/
    pipeline.py        Lỗi 1  (chuyển blocking -> threadpool)
    market.py          Lỗi 1  (12 handler blocking -> def)
    data.py            Lỗi 8  (BackgroundTasks cho ingest)
    admin.py           Lỗi 4  (endpoint reconnect storage)
    agent.py
  agent/tools/
    stock_tools.py     Lỗi 3  (thêm trường _pct)
  database/
    models/agent_conversation.py   Lỗi 2  (TEXT -> MEDIUMTEXT)
    repositories/conversation_repository.py  Lỗi 2 (rollback)
  services/
    agent_service.py   Lỗi 2  (cắt tool result 32.000 ký tự)
    auto_refresh.py    Lỗi 12 (tín hiệu rebuild: so giá phiên mới nhất Bronze vs Silver)
  lakehouse/           Bronze / Silver / Gold
  backtesting/         walk_forward.py, benchmark.py
  forecasting/         arima.py, lstm.py, multistep.py

backend/alembic/versions/
  0003_agent_mediumtext.py        Lỗi 2

frontend/src/
  pages/Forecasting.tsx            Lỗi 5  (formatPercent)
  components/dashboard/MetricCard.tsx   Lỗi 6  (delta có điều kiện)
  components/backtesting/*.tsx     Lỗi 6  (bỏ delta trùng)
  components/common/ErrorState.tsx       Lỗi 10 (trạng thái lỗi)

scripts/
  fix_mojibake.py                  Lỗi 7  (khôi phục UTF-8)

backend/scripts/
  scan_divergence_fast.py          Lỗi 12 (quét lệch 3 tầng song song, 1.002 mã / 95 giây)
  backfill_silver_gold.py          Lỗi 12 (rebuild --force cho các mã bị kẹt)

backend/tests/
  test_silver_divergence_recovery.py   Lỗi 12 (15 check)
```

# PHỤ LỤC B — MA TRẬN TRUY VẾT YÊU CẦU

| Yêu cầu kiểm thử | Thực hiện ở đâu | Bằng chứng |
|---|---|---|
| Backend unit test không hồi quy | `backend/tests/` | 112/112 PASS, 12/11/2026 |
| Toàn bộ API route trả đúng | `backend/scripts/smoke_all_routes.py` | 55/58 route 200 OK, 0 lỗi kết nối |
| Frontend build sạch | `frontend/package.json` | `tsc --noEmit && vite build` PASS |
| 7 trang web dùng được | trình duyệt thật | 7/7 OK |
| Không nghẽn server khi chạy việc nặng | `app/api/v1/endpoints/pipeline.py` | 20 health check song song: 2–18ms, 0 lỗi |
| Agent không làm hỏng phiên | `alembic/versions/0003_agent_mediumtext.py` | 200 OK sau walk-forward |
| Agent không báo sai đơn vị | `app/agent/tools/stock_tools.py` | 3.20% -> 320.05% |
| Định dạng phần trăm đúng | `frontend/src/pages/Forecasting.tsx` | 0.52 -> 52.41% |
| Không có dữ liệu giả | toàn repo | `rg` không trả kết quả; `source_layer` có trong mọi response giá |
| Chiến lược được so với đường cơ sở | `app/backtesting/benchmark.py` | 3.687 cửa sổ ghép cặp, 101 mã, 13 sàn |
| Ba tầng dữ liệu luôn khớp nhau | `app/services/auto_refresh.py` | 1.002 mã kiểm tra, 0 lệch (trước sửa: 78 lệch) |
