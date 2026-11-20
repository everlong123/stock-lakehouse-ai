# Kiểm tra trực tiếp toàn bộ mã — 19/11/2026

**Kết luận: phần phục vụ dữ liệu hoạt động trên toàn bộ danh sách được quét; phần dự báo và tự cập nhật chưa ổn toàn bộ.** HTTP 200 và `available=true` chưa bảo đảm dự báo hợp lệ.

## Phạm vi và thời điểm

- Quét danh sách **1.002 mã** do API trả tại đầu lượt kiểm tra.
- Thời gian: **03:58:36–04:07:30 ngày 19/11/2026, giờ Việt Nam**.
- Thực hiện **2.149 lượt GET**: giá mới nhất và dự báo Linear Regression cho mọi mã; thêm ARIMA/LSTM tại các mã có registry tương ứng trên máy.
- Không chạy ingest mới, huấn luyện, xuất bản hay chấm dự báo. Các số liệu mô tả hệ thống đang chạy trong khoảng quét, không phải một snapshot nguyên tử. Batch của hệ thống có thể đang cập nhật dữ liệu cùng lúc.
- Không xác minh lại mọi giá với nhà cung cấp và không chứng minh độ chính xác thống kê của mô hình bằng lượt kiểm tra này.

## Kết quả đầy đủ

| Hạng mục | Kết quả |
|---|---:|
| Đọc giá mới nhất | **1.002/1.002 mã** |
| Nguồn của giá đọc được | **1.002 từ Gold** |
| Lỗi HTTP/timeout trong lượt quét | **0** |
| Linear Regression trả `available=true` | **973/1.002 mã** |
| Linear Regression không khả dụng | **29 mã**, đều báo thiếu mô hình |
| ARIMA trả kết quả trong số đã kiểm tra | **73/73 mã có registry** |
| LSTM trả kết quả trong số đã kiểm tra | **72/72 mã có registry** |
| Dự báo vi phạm bộ kiểm tra giá của chính hệ thống | **6 mã**, tất cả là Linear Regression |
| Dự báo báo đầu vào chậm phiên | LR: **8**; ARIMA: **2**; LSTM: **3** |
| Độ trễ API p50 / p95 trong lượt quét | **0,282 / 1,750 giây** |
| Health sau lượt quét | **HTTP 200, status=ok** |

“ARIMA 73/73, LSTM 72/72” chỉ có nghĩa kiểm tra thành công các model đã có; không có nghĩa mọi mã đều có cả ba mô hình. “973 trả kết quả” bao gồm cả sáu dự báo sai dưới đây và các dự báo từ đầu vào cũ.

## Lỗi dự báo cần ưu tiên chặn

API `/forecast/next-session/{symbol}?model_name=linear_regression` trả `available=true` cho các kết quả sau:

| Mã | Giá tham chiếu | Giá dự báo | Vấn đề |
|---|---:|---:|---|
| PARA | 0,073 | 279.013,540 | Lớn hơn giá tham chiếu khoảng **3,82 triệu lần** |
| SPXU | 39,030 | -39,359 | Giá âm |
| SQQQ | 46,950 | -458,039 | Giá âm |
| SOXS | 58,770 | -277.289.577,528 | Giá âm, lệch nhiều bậc độ lớn |
| UVXY | 22,680 | -28.501,897 | Giá âm |
| VXX | 22,140 | -52,264 | Giá âm |

Phân loại dùng `app.core.data_integrity.is_impossible_price`, tức quy tắc hiện có của dự án; không phải một ngưỡng mới tự đặt để chấm mô hình. Năm mã PARA/SPXU/SQQQ/SOXS/UVXY đã được gọi lại riêng và vẫn tái hiện kết quả.

Đường ghi vào database có bộ chặn giá không hợp lệ, nhưng đường trả dự báo đọc trực tiếp vẫn phục vụ các giá trên. Vì vậy không thể suy từ việc sổ kiểm chứng không có giá âm rằng API dự báo đã an toàn về tính đúng.

**Cần xử lý:** kiểm tra cùng một quy tắc trước khi trả dự báo cho người dùng; trả trạng thái không khả dụng kèm lý do cho model hỏng. Kiểm tra/thu hồi các model cũ bị ảnh hưởng và chỉ huấn luyện lại sau khi thống nhất thang giá, corporate actions và lịch sử đầu vào. Không đổi giá âm thành 0 để che lỗi.

## Độ mới dữ liệu

Ngày phiên cuối đọc được trong lượt quét:

| Ngày | Số mã |
|---|---:|
| 18/11/2026 | 552 |
| 17/11/2026 | 414 |
| Trước 17/11/2026 | 36 |

Trong 36 mã cuối, **34 mã có phiên mới nhất cũ hơn 10 ngày lịch so với 18/11/2026**. Đây là ngưỡng phát hiện để điều tra, không phải kết luận tất cả 34 mã đều lỗi ingest. Có thể có mã ngừng giao dịch, đổi mã, mất nguồn hoặc cần đổi ánh xạ.

Danh sách 34 mã: AVB, BTF, EA, EQR, NSC, QRVO, ROKU, AKRO, ALXN, ATSG, BK, BLUE, CCRN, CHK, CMA, CPRX, CTRA, DAWN, DENN, EXPR, FOLD, HAB, HOLX, IPG, KLG, LTHM, PEAK, PGRE, PLL, SOFI, TCO, TGNA, WBA, WBD.

Không thể gọi tất cả là “dữ liệu mới nhất”. Cũng không nên tự xóa lịch sử của các mã này: cần phân biệt kho lịch sử với universe đang hoạt động.

Các mã có dự báo LR nhưng báo đầu vào chậm phiên:

| Mã | Số phiên chậm do API báo |
|---|---:|
| BTF | 19 |
| NSC | 8 |
| NWE | 2 |
| QRVO | 31 |
| ROKU | 7 |
| PVE | 2 |
| SOFI | 10 |
| WBD | 32 |

ROKU/LSTM, SOFI/ARIMA+LSTM và WBD/ARIMA+LSTM cũng báo chậm phiên. Các số này là kết quả của lịch suy ra trong ứng dụng, chưa đối chiếu độc lập với lịch sàn chính thức.

Trong các dự báo LR trả được, 552 nhắm ngày 19/11 và 421 nhắm ngày 18/11. Vì lượt quét diễn ra quanh thời điểm thị trường Mỹ đóng cửa, cần kiểm tra cutoff phát hành theo từng thị trường; không gọi mọi dòng trả về là dự báo cho một phiên còn ở tương lai. `data_staleness_days=0` cũng chưa bảo đảm thời điểm phát hành đúng.

## Mã thiếu mô hình Linear Regression

**29 mã:** AVB, EA, EQR, WOLF, AKRO, ALXN, ATSG, BK, BLUE, CCRN, CHK, CMA, CPRX, CTRA, DAWN, DENN, EXPR, FOLD, HAB, HOLX, IPG, KLG, LTHM, PEAK, PGRE, PLL, TCO, TGNA, WBA.

Hệ thống báo rõ thiếu model thay vì tạo số thay thế; hành vi báo thiếu này là đúng. Muốn tuyên bố toàn bộ mã có dự báo thì cần chốt universe đủ điều kiện, xác định mã nào còn hoạt động và huấn luyện các model còn thiếu trên dữ liệu hợp lệ.

## Lỗi trong tự cập nhật

Log ngày 19/11 ghi **516 cảnh báo trên 352 mã khác nhau** với nội dung:

```text
AutoRefresh: watermark compare failed for ...: name 'symbol' is not defined
```

Vị trí: [auto_refresh.py](../../backend/app/services/auto_refresh.py:451).

Trong `_rebuild_layers(sym, res)`, đoạn kiểm tra gọi `session_date(bronze_ts, symbol)` và `session_date(gold_ts, symbol)`, trong khi tên đang có là `sym`. Nhánh exception ghi cảnh báo rồi return. Do đó cơ chế kiểm tra Bronze tiến trước Gold có thể bị bỏ qua ở nhánh này.

352 mã có log cảnh báo **không đồng nghĩa 352 mã đang lệch dữ liệu**. Đối chiếu riêng MSFT trong lượt này cho thấy Bronze/Silver/Gold cùng phiên 18/11 và cùng close 502,8299866. Tuy nhiên, lỗi kiểm tra vẫn có thật và cần sửa trước khi tin vào khả năng tự phục hồi của toàn pipeline.

Endpoint auto-refresh vẫn trả `last_run_at=null`, `last_summary={}` ở những lần đọc trong lượt kiểm tra. Điều đó chưa xác nhận một lượt tự cập nhật toàn universe đã hoàn tất; riêng nó cũng không chứng minh không có công việc đang chạy.

## Cách đọc cảnh báo chất lượng

Snapshot chất lượng được API phục vụ có thời điểm **18/11/2026 11:35:09 UTC**, trước lượt quét hiện tại. Snapshot báo:

- Layer agreement: 1.002 mã được kiểm tra, không có mã fail trong cửa sổ được xét.
- Integrity: 1.002 mã được kiểm tra, không có mã fail.
- Freshness: 34 mã cảnh báo.
- Bronze giữ các snapshot giữa phiên đã có bản settled thay thế: 782 mã, 1.242 phiên. Cảnh báo này không tự chứng minh Silver/Gold đang phục vụ giá giữa phiên.
- Có các dòng bị chặn vì độ lớn giá, và một lần đối chiếu provider không thực hiện được.

Phải giữ nguyên thời điểm và phạm vi của snapshot; không trình bày như một lần kiểm tra mới mọi nhà cung cấp cho toàn universe.

## Thứ tự xử lý đề xuất

1. Chặn sáu dự báo không hợp lệ trên đường trả kết quả và kiểm tra model đang lưu.
2. Sửa biến chưa định nghĩa trong kiểm tra watermark; thêm kiểm thử cho nhánh tự phục hồi khi Gold chậm hơn Bronze.
3. Phân loại các mã lịch sử/ngừng nguồn/đổi mã, chốt universe đang hoạt động và hiển thị trạng thái trên giao diện.
4. Hoàn thiện coverage model của universe đủ điều kiện; không huấn luyện mù trên lịch sử lỗi hoặc đã ngừng cập nhật.
5. Xác nhận một lượt ingest → Silver → Gold → forecast → lưu → chấm điểm đã hoàn tất; kiểm tra cutoff và ngày đích theo thị trường.

Lượt kiểm tra này bổ sung script và báo cáo; **chưa sửa các lỗi nghiệp vụ trên**.

## Bằng chứng và cách chạy lại

- [Kết quả từng request, toàn bộ mã](live_universe_2026-11-19.json).
- [Danh sách phát hiện đã tổng hợp](live_universe_findings_2026-11-19.json).
- [Cảnh báo refresh trích từ log](live_refresh_errors_2026-11-19.json).
- [Gọi lại các dự báo nghiêm trọng](live_suspect_recheck_2026-11-19.json).
- [Đối chiếu MSFT giữa ba tầng](live_layer_sample_2026-11-19.json).
- [Snapshot chất lượng](live_quality_gate_2026-11-19.json).
- [Script kiểm tra](../../backend/scripts/audit_live_universe.py).

Chạy tại thư mục `backend`, đặt tên file đầu ra mới để không ghi đè bằng chứng:

```powershell
.\.venv\Scripts\python.exe scripts/audit_live_universe.py --workers 3 --timeout 25 --output ../docs/audits/live_universe_new_run.json
```
