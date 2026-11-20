"""Sync the reviewed experiment sections from their actual result artifacts."""

import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
with urlopen("http://127.0.0.1:8000/api/v1/forecast/compare/AAPL", timeout=30) as response:
    comparison = json.load(response)["data"]
if comparison.get("comparison_scope") != "common_target_sessions":
    raise RuntimeError("No independently aligned comparison is available.")
ma = json.loads((ROOT / "backend/data/multi_symbol_walkforward.json").read_text(encoding="utf-8"))
rsi = json.loads((ROOT / "backend/data/multi_symbol_walkforward_rsi.json").read_text(encoding="utf-8"))


def number(value, places=2):
    return f"{value:.{places}f}".replace(".", ",")


def percent(value):
    return number(100 * value) + "%"


note = "> **Đính chính 19/11/2026:** xem [báo cáo sửa lỗi](audits/KET_QUA_SUA_LOI_2026-11-19.md) về mô hình đánh giá độc lập, cutoff nhãn, dự báo không hợp lệ, cập nhật dữ liệu và phạm vi lakehouse. Số đo ghi trước thời điểm này là snapshot lịch sử, không thay cho kết quả kiểm tra lại."
for name in ("HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md", "architecture.md"):
    path = ROOT / "docs" / name
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "KET_QUA_SUA_LOI_2026-11-19.md" in line:
            lines[index] = note
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

path = ROOT / "docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md"
text = path.read_text(encoding="utf-8")
start, end = text.index("## 6.8."), text.index("## 6.9.")
section = f"""## 6.8. Kết quả AAPL sau sửa giao thức đánh giá (19/11/2026)

Mô hình đánh giá được lưu riêng trước khi refit. Bảng dưới lấy giao **{comparison['comparison_points']} phiên đích chung**, cùng giá thật và quy tắc đo. Các số đo 06/11 trên số điểm khác nhau không được dùng để xếp hạng trực tiếp.

| Mô hình | MAE | RMSE | MAPE | Đúng hướng | Số phiên chung |
|---|---|---|---|---|---|
"""
baseline = comparison["baseline"]
section += f"| Giữ nguyên giá phiên trước (naive) | {number(baseline['mae'], 3)} | {number(baseline['rmse'], 3)} | {number(baseline['mape'], 3)}% | Không dự báo hướng | {comparison['comparison_points']} |\n"
labels = {"linear_regression": "Linear Regression", "arima": "ARIMA (5,1,0)", "lstm": "LSTM"}
for row in comparison["models"]:
    section += f"| {labels[row['model_name']]} | {number(row['mae'], 3)} | {number(row['rmse'], 3)} | {number(row['mape'], 3)}% | {percent(row['directional_accuracy'])} | {comparison['comparison_points']} |\n"
section += """
**Diễn giải:** trên mẫu này, chưa có model nào có MAE thấp hơn baseline giữ nguyên giá. Sai số phần trăm nhỏ chưa tự chứng minh có kỹ năng dự báo. Độ chính xác hướng cần so với tỉ lệ lớp và lượng hóa độ bất định trước khi kết luận hơn ngẫu nhiên; không suy rộng kết quả AAPL ra mọi mã.

Nguồn: API `GET /forecast/compare/AAPL`, `comparison_scope=common_target_sessions`, và các artifact `data/models/AAPL/*/predictions.parquet`. Registry giữ số điểm của split gốc; API chấm lại trên giao phiên nên số điểm trong bảng có thể khác số điểm split.

"""
text = text[:start] + section + text[end:]
start = text.index("## 8.7.")
end = text.index("**Ba thay đổi trong code", start)
m, r, bh = ma["strategy_distribution"], rsi["strategy_distribution"], ma["buy_and_hold_distribution"]
mh, rh = ma["head_to_head"], rsi["head_to_head"]
section = """## 8.7. Đánh giá đa mã sau sửa nhóm thị trường (19/11/2026)

Mẫu có **102 mã / 14 nhóm thị trường / 3.724 cửa sổ cặp**, từ universe 1.002 mã. Cấu hình train/test/step 365/90/90 ngày, vốn 10.000 theo đơn vị mỗi mã, phí 0,1%, trượt giá 0,05%. Hai chiến lược dùng tham số cố định; đoạn trước cung cấp ngữ cảnh chỉ báo, không có bước tối ưu tham số ẩn.

Đã sửa Australia thành ASX, Italy thành Milan. Vietnam, Euronext, NYSE/NASDAQ là nhóm thị trường, không phải sàn đơn lẻ; chưa xác minh từng mã Việt Nam thuộc HOSE/HNX/UPCoM. Bản 101 mã/13 nhóm ngày 11/11 là snapshot cũ, không thay cho kết quả mới.

| Chỉ số | MA Crossover | RSI | Mua & giữ |
|---|---|---|---|
"""
section += f"| Trung vị lợi nhuận ngoài mẫu | {percent(m['median_avg_test_return'])} | {percent(r['median_avg_test_return'])} | {percent(bh['median_avg_return'])} |\n"
section += f"| Trung vị Sharpe | {number(m['median_avg_test_sharpe'], 3)} | {number(r['median_avg_test_sharpe'], 3)} | {number(bh['median_sharpe'], 3)} |\n"
section += f"| Trung vị max drawdown | {percent(m['median_avg_test_max_drawdown'])} | {percent(r['median_avg_test_max_drawdown'])} | {percent(bh['median_max_drawdown'])} |\n"
section += f"| Tỉ lệ mã có lãi | {number(m['pct_symbols_profitable'])}% | {number(r['pct_symbols_profitable'])}% | {number(bh['pct_symbols_profitable'])}% |\n"
section += f"| Tỉ lệ cửa sổ thắng mua & giữ | {number(mh['pct_windows_beating_buy_hold'])}% | {number(rh['pct_windows_beating_buy_hold'])}% | — |\n"
section += f"| Tỉ lệ mã thắng mua & giữ | {number(mh['pct_symbols_beating_buy_hold'])}% | {number(rh['pct_symbols_beating_buy_hold'])}% | — |\n"
section += """
**Kết luận trong phạm vi mẫu:** cả hai chiến lược có lợi nhuận trung vị thấp hơn mua & giữ, đồng thời drawdown trung vị nhỏ hơn. Đây là thống kê mô tả, chưa phải kiểm định một quy luật cho toàn thị trường. Không coi 3.724 cửa sổ là quan sát độc lập; cần xét phụ thuộc thời gian, chọn mẫu và giả định chi phí.

Nguồn: `backend/data/multi_symbol_walkforward.json`, `multi_symbol_walkforward_rsi.json`. Tài liệu [nghiên cứu đa mã](NGHIEN_CUU_DA_MA_WALK_FORWARD.md) giữ phần giải thích và snapshot cũ để tra cứu.

"""
text = text[:start] + section + text[end:]
text = text.replace('Hàm đó **xáo trộn ngẫu nhiên**.', 'Mặc định hàm đó dùng `shuffle=True`; nếu giữ mặc định, nó **xáo trộn ngẫu nhiên**. Có thể dùng `shuffle=False`, nhưng vẫn phải kiểm tra thứ tự và cutoff của nhãn.')
text = text.replace('| **Backtest trên 1 cổ phiếu** | Minh hoạ khung | Đã hỗ trợ đủ 1.037 mã |', '| **Mẫu backtest hữu hạn** | Đã đo 102 mã trong 14 nhóm; chưa là mẫu xác suất của toàn thị trường | Mở rộng mẫu và kiểm định độ bất định |')
text = text.replace('overfitting ratio 4.0', 'tỉ số lợi nhuận train/test 4.0 (chỉ mô tả, không phải kiểm định quá khớp)')
text = text.replace('## 1.4. Chi tiết: 4 đóng góp khoa học chính', '## 1.4. Chi tiết: 4 đóng góp triển khai của khóa luận')
path.write_text(text, encoding="utf-8")

path = ROOT / "docs/NGHIEN_CUU_DA_MA_WALK_FORWARD.md"
text = path.read_text(encoding="utf-8")
if "Cập nhật 19/11/2026" not in text:
    index = text.index("\n") + 1
    text = text[:index] + "\n> **Cập nhật 19/11/2026:** kết quả mới có **102 mã / 14 nhóm thị trường / 3.724 cửa sổ cặp**, sau khi sửa phân nhóm. Xem mục 8.7 của [tài liệu chính](HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md) và [báo cáo sửa lỗi](audits/KET_QUA_SUA_LOI_2026-11-19.md). Phần 101 mã/13 sàn bên dưới là snapshot 11/11, giữ để tra cứu lịch sử, không dùng làm kết quả hiện tại.\n" + text[index:]
path.write_text(text, encoding="utf-8")

path = ROOT / "presentation.md"
text = path.read_text(encoding="utf-8")
text = text.replace('với **~1,1 triệu dòng dữ liệu thật** mỗi ngày.', 'với **~1,1 triệu dòng lịch sử** trong snapshot được báo cáo; đây không phải lượng tăng thêm mỗi ngày.')
text = text.replace('Tuy nhiên, vì thầy cô có thể là người **chưa quen với công nghệ thông tin**, em xin phép dành riêng chương tiếp theo để giải thích tất cả các thuật ngữ em sẽ dùng xuyên suốt bài. Thầy cô đọc chương 2 trước rồi quay lại đọc các chương sau sẽ dễ hiểu hơn rất nhiều ạ.', 'Em sẽ giải thích ngắn gọn các thuật ngữ cần thiết khi trình bày; bảng thuật ngữ chi tiết đặt ở phần tra cứu để tham khảo khi cần.')
text = text.replace('tính năng xem dữ liệu cũ giờ do **cách chia thư mục** đảm nhiệm, không cần catalog riêng.', 'cách chia thư mục chỉ tổ chức dữ liệu theo mã/tháng, **chưa thay thế time-travel hay snapshot bảng**.')
if "Các con số lịch sử trong bản nháp" not in text:
    index = text.index("---") + 3
    text = text[:index] + "\n\n> Các con số lịch sử trong bản nháp cần đối chiếu với báo cáo sửa lỗi 19/11/2026 trước khi đưa vào slide cuối. Không dùng kết quả full-fit cũ làm bằng chứng ngoài mẫu.\n" + text[index:]
path.write_text(text, encoding="utf-8")
print("Updated thesis result sections and presentation notes from verified artifacts.")
