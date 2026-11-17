# `backend/scripts/` — BẢN ĐỒ CÁC SCRIPT

**Mục đích:** biết script nào dùng khi nào, mà không phải mở từng file.

**Cập nhật:** 16/11/2026 — 86 script.

**Quy ước đặt tên:**

| Tiền tố | Nghĩa là gì | Chạy được bao nhiêu lần? |
|---|---|---|
| `ingest_` / `backfill_` | **Ghi** dữ liệu vào lakehouse | Cần cẩn thận — chạy lại vẫn an toàn (idempotent) |
| `verify_` / `check_` / `audit_` / `scan_` | **Chỉ đọc**, kiểm tra, báo cáo | An toàn, chạy thoải mái |
| `diagnose_` / `probe_` / `classify_` | Điều tra lỗi cụ thể | An toàn |
| `purge_` / `repair_` | **XOÁ / SỬA** dữ liệu | Cẩn thận — đọc kỹ trước khi chạy |
| `run_` / `train_` | Chạy tác vụ | Tuỳ |
| `transform_` / `rebuild_` / `reingest_` | Dựng lại tầng | Mất thời gian nhưng không mất dữ liệu gốc |

---

## 1. Khởi động & hạ tầng

| Script | Tác dụng |
|---|---|
| `bootstrap_infrastructure.py` | Tạo bucket MinIO + bảng MySQL + user admin lần đầu. |
| `init_database.py` | Tạo DB MySQL và chạy migration Alembic. |
| `seed_database.py` | Tạo user admin cho prototype. |
| `relay_ports.py` | **Cầu nối cổng WSL → Windows**: `python3 backend/scripts/relay_ports.py 13307:3307 19000:9000`. Chạy trong WSL. |
| `start_relay.py` | Khởi động relay **và** tự dò IP WSL, ghi ra `/tmp/relay_endpoints.txt` để phía Windows biết trỏ endpoint vào đâu. `--no-spawn` để chỉ refresh file khi relay đã chạy. |
| `relay_diag.py` | Chẩn đoán nhanh: relay có tới được MySQL/MinIO bên trong WSL không. |
| `enable_pagefile.ps1` | Bật pagefile Windows (máy này không có, cần cho job nặng). |
| `check_port_forward.sh` | Kiểm tra cầu nối cổng có thông không. |
| `check_port_stability.sh` | Theo dõi cổng có bị rớt sau thời gian không. |
| `check_wsl_keepalive.sh` | Giữ WSL không bị tắt ngầm. |
| `wslc.cmd`, `wslc.vbs`, `wsl_keepalive.vbs` | Wrapper chạy lệnh trong WSL. |
| `wsl_py.sh` | Chạy Python trong WSL. |
| `check_minio_api.py` | Ping MinIO xem sống không. |

## 2. Nạp dữ liệu (ghi vào Bronze)

| Script | Tác dụng |
|---|---|
| `ingest_all.py` | Nạp **toàn bộ** universe. |
| `ingest_historical.py` | Nạp lịch sử 1 nhóm mã. |
| `ingest_vn.py` | Nạp dữ liệu mã Việt Nam + sinh báo cáo chất lượng vào `backend/docs/vn_quality_reports/`. |
| `backfill_global.py` | Bổ sung lịch sử cho toàn bộ mã. |
| `backfill_gold.py` | Dựng lại tầng Gold từ Silver. |
| `backfill_silver_gold.py` | Dựng lại Silver + Gold. |
| `backfill_missing_days.py` | Bổ sung những ngày giao dịch bị thiếu. |
| `backfill_thin_history.py` | Bổ sung mã có lịch sử quá ngắn. |
| `backfill_forecast_ledger.py` | **Bổ sung sổ ghi dự báo** (lịch sử dự báo để đo độ chính xác). |
| `resume_backfill.py` | Tiếp tục backfill dở dang (bỏ qua mã đã có). |
| `backup_bronze.py` | Sao lưu tầng Bronze trước khi sửa. |
| `reingest_window.py` | Nạp lại một khoảng thời gian cụ thể. |
| `replay_provider_for_day.py` | Phát lại dữ liệu provider cho một ngày (điều tra). |

## 3. Dựng lại tầng

| Script | Tác dụng |
|---|---|
| `transform_to_silver.py` | Biến Bronze → Silver. |
| `rebuild_gold.py` | Dựng lại Gold. |
| `run_pipeline.py` | Chạy trọn Bronze → Silver → Gold cho 1 nhóm mã. |
| `run_spark_pipeline.py` | Biến thể dùng PySpark (tùy chọn, mặc định tắt). |

## 4. Kiểm tra & kiểm chứng (chỉ đọc — an toàn)

| Script | Tác dụng |
|---|---|
| `verify_against_source.py` | **Script kiểm chứng quan trọng nhất**: tải lại từ provider thật rồi so từng bar Bronze/Silver/Gold. |
| `verify_layers.py` | So khớp 3 tầng với nhau. |
| `verify_latest_fast_path.py` | Kiểm tra đường đọc nhanh cho bar mới nhất. |
| `verify_windowed_stats.py` | Kiểm tra số liệu thống kê theo cửa sổ. |
| `check_layer_divergence.py` | Phát hiện tầng lệch nhau. |
| `scan_divergence_fast.py` | Quét lệch tầng nhanh hơn. |
| `check_coverage.py` | Tỉ lệ mã có dữ liệu. |
| `check_day_coverage.py` | Tỉ lệ ngày giao dịch có dữ liệu. |
| `check_unserved_symbols.py` | Mã nào API chưa phục vụ được. |
| `check_missing_symbols.py` | Mã nào còn thiếu trong Bronze. |
| `check_dead_symbols.py` | Mã nào đã bị hủy niêm yết. |
| `check_universe_alive.py` | Mã nào còn sống. |
| `check_latest_date.py` | Ngày giao dịch mới nhất trong mỗi tầng. |
| `check_max_trade_date.py` | Ngày giao dịch lớn nhất tìm được. |
| `check_api_sessions.py` | Kiểm tra phiên trả về từ API. |
| `check_mysql_counts.py` | Đếm số dòng từng bảng MySQL. |
| `count_layer_objects.py` | Đếm object từng tầng trong MinIO. |
| `check_gap_rule_collisions.py` | Va chạm quy tắc xử lý khoảng trống. |
| `check_vn_data_loss.py` | Kiểm tra mất dữ liệu mã Việt Nam. |
| `check_epoch_symbols.py` | Mã có dấu hiệu lỗi epoch (timestamp 1970). |
| `check_epoch_timestamps.py` | Timestamp kiểu epoch bị lẫn. |
| `audit_layer_coverage.py` | Audit độ phủ từng tầng. |
| `audit_universe_coverage.py` | Audit độ phủ toàn universe. |
| `audit_vn_dedupe.py` | Audit trùng lặp dữ liệu Việt Nam. |
| `analyze_ohlc.py` | Thống kê OHLC. |
| `read_lineage.py` | Truy vết nguồn gốc của một dòng. |
| `show_multibar_days.py` | Liệt kê ngày có nhiều bar (nghi vấn bar giữa phiên). |

## 5. Điều tra lỗi

| Script | Tác dụng |
|---|---|
| `diagnose_calendar_gaps.py` | Tìm lỗi lịch giao dịch (thiếu ngày). |
| `diagnose_dst_stamps.py` | Tìm lỗi múi giờ mùa hè (DST). |
| `diagnose_duplicates.py` | Tìm bar trùng lặp. |
| `diagnose_gold_calendar.py` | Kiểm tra lịch ở tầng Gold. |
| `diagnose_silver_calendar.py` | Kiểm tra lịch ở tầng Silver. |
| `diagnose_missing_day.py` | Điều tra một ngày bị thiếu cụ thể. |
| `diagnose_row_sources.py` | Thống kê dòng theo nguồn. |
| `classify_mismatches.py` | Phân loại các cặp dữ liệu lệch nhau. |
| `probe_yahoo_period_boundary.py` | Dò biên kỳ lịch sử của Yahoo. |
| `validate_session_fix.py` | Kiểm tra bản vá phiên giao dịch. |

## 6. Dọn dữ liệu bẩn (CẨN THẬN)

| Script | Tác dụng |
|---|---|
| `purge_fabricated_rows.py` | **Xoá dòng dữ liệu bịa** đã lọt vào Bronze. |
| `purge_fake_predictions.py` | Xoá dự báo giả trong bảng `predictions`. |
| `purge_impossible_predictions.py` | Xoá dự báo có giá không thể tồn tại (âm, lệch 100 lần). |
| `purge_implausible_bronze.py` | Xoá bar Bronze vô lý. |
| `purge_symbol_bronze_junk.py` | Xoá dữ liệu rác của một mã cụ thể. |
| `purge_epoch_partitions.py` | Xoá partition có timestamp kiểu epoch. |
| `repair_bronze.py` | Sửa tầng Bronze (ví dụ: scale break do chia tách). |

> **Trước khi chạy script trong nhóm này:** chạy `backup_bronze.py` trước, và đọc
> phần "Dry run" trong đầu script (nhiều script có chế độ `--dry-run` chỉ báo
> cáo, không xoá).

## 7. Mô hình & backtest

| Script | Tác dụng |
|---|---|
| `train_models.py` | Huấn luyện Linear Regression / ARIMA / LSTM cho các mã chỉ định. |
| `train_universe.py` | Huấn luyện mô hình cho toàn universe. |
| `run_multi_symbol_walkforward.py` | Chạy walk-forward đa mã → ghi báo cáo JSON. |
| `run_agent.py` | Chạy trợ lý AI từ CLI. |
| `sync_models_to_vps.py` | Đồng bộ file mô hình lên máy chủ. |

## 8. Lịch & vận hành

| Script | Tác dụng |
|---|---|
| `run_scheduled_job.py` | Chạy một job theo lịch (`eod`, `forecast`, ...). |
| `schedule_batch.py` | Lên lịch batch. |
| `smoke_all_routes.py` | Gọi thử mọi endpoint, báo cáo cái nào lỗi. |

## 8.1. Kiểm chứng khóa luận

Ba script dưới đây kiểm tra `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md` — chạy chúng
trước khi nộp bài, vì số trong bài phải khớp với hệ thống đang chạy.

| Script | Tác dụng |
|---|---|
| `verify_thesis_numbers.py` | Đối chiếu từng con số trong khóa luận với MySQL và MinIO hiện tại. Thoát với mã khác 0 nếu có sai lệch. |
| `check_thesis_markdown.py` | Kiểm tra cấu trúc Markdown: bảng có đủ cột không, code fence có cân bằng không, heading có nhảy cấp không. |
| `check_thesis_style.py` | Quét các cụm từ "ngon ngon máy" (filler, connector lạ, mật độ em-dash) để giữ văn phong tự nhiên. |

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\verify_thesis_numbers.py
.\.venv\Scripts\python.exe scripts\check_thesis_markdown.py
.\.venv\Scripts\python.exe scripts\check_thesis_style.py
```

> `reduce_em_dash.py` là script **dùng một lần** để giảm mật độ em-dash trong
> bài luận (116 → 27). Chạy lại nó sẽ không có tác dụng gì thêm.

---

## 8.1. Khi nào dùng script nào?

| Tình huống | Script |
|---|---|
| "Dữ liệu có thật không?" | `verify_against_source.py` |
| "Các tầng có khớp nhau không?" | `check_layer_divergence.py` hoặc `scan_divergence_fast.py` |
| "Tầng nào đang hỏng?" | `check_latest_date.py` + `check_layer_divergence.py` |
| "API trả lỗi ở đâu?" | `smoke_all_routes.py` |
| "Cần nạp thêm mã" | `ingest_all.py` / `ingest_historical.py` |
| "Cần dựng lại Gold sau khi sửa Silver" | `rebuild_gold.py` |
| "Có dữ liệu giả lọt vào không?" | `purge_fake_predictions.py` + `purge_fabricated_rows.py` |
| "Muốn xem độ chính xác dự báo" | `backfill_forecast_ledger.py` rồi `GET /api/v1/forecast/accuracy` |
| "Muốn biết chiến lược có thắng thị trường không" | `run_multi_symbol_walkforward.py` |
