/**
 * Simple i18n: Vietnamese-first với nút chuyển EN/Vi ở Header.
 *
 * Usage:
 *   import { useI18n, t } from "@/lib/i18n";
 *   const { locale, setLocale } = useI18n();
 *   return <div>{t("dashboard.title")}</div>;
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type Locale = "vi" | "en";

// ── Dictionary ──────────────────────────────────────────────────────────────
// Mỗi khoá có 2 bản: tiếng Việt (mặc định) + tiếng Anh
const DICT: Record<Locale, Record<string, string>> = {
  vi: {
    // App
    "app.title": "StockVision AI",
    "app.subtitle": "Phân tích & Dự báo chứng khoán",
    "app.footer_disclaimer": "Thông tin tham khảo · Không phải khuyến nghị đầu tư",

    // Sidebar
    "nav.overview": "Tổng quan",
    "nav.data": "Dữ liệu",
    "nav.models": "Mô hình",
    "nav.agent": "Agent",
    "nav.platform": "Hệ thống",
    "nav.dashboard": "Tổng quan",
    "nav.market": "Thị trường",
    "nav.analysis": "Phân tích",
    "nav.forecast": "Dự báo",
    "nav.backtesting": "Chiến lược",
    "nav.agent_full": "Trợ lý AI",
    "nav.system": "Hệ thống",
    "nav.tools": "Công cụ",

    // Dashboard
    "dashboard.title": "Tổng quan",
    "dashboard.metrics": "Chỉ số · 5 cột",
    "dashboard.price": "Giá đóng cửa gần nhất",
    "dashboard.change_pct": "Biến động %",
    "dashboard.volume": "Khối lượng",
    "dashboard.volume_hint": "Phiên gần nhất",
    "dashboard.rsi": "RSI (14)",
    "dashboard.rsi_hint": "Gold layer",
    "dashboard.model": "Mô hình gần nhất",
    "dashboard.model_no_train": "Chưa train",
    "dashboard.model_hint_trained": "MAE",
    "dashboard.model_hint_untrained": "Train để bắt đầu",
    "dashboard.line_chart_title": "Diễn biến giá",
    "dashboard.line_chart_sub": "Đường line trực tiếp từ Gold layer",
    "dashboard.candle_title": "Nến · Bronze layer",
    "dashboard.candle_sub": "OHLCV gốc, không qua chỉnh sửa",
    "dashboard.volume_title": "Khối lượng giao dịch",
    "dashboard.volume_sub": "Theo khoảng và khung thời gian đã chọn",
    "dashboard.empty_candle": "Không có dữ liệu nến.",
    "dashboard.empty_symbol": "Không có dữ liệu cho symbol này.",
    "dashboard.err_connect": "Không kết nối được backend API.",
    "dashboard.data_source": "Nguồn dữ liệu",
    "dashboard.pipeline": "Pipeline",
    "dashboard.last_update": "Cập nhật",

    // Market data
    "market.title": "Dữ liệu thị trường",
    "market.subtitle": "Theo dõi giá, so sánh cổ phiếu và xem lịch sử giao dịch.",
    "market.source": "Nguồn",
    "market.rows": "Số phiên",
    "market.last_close": "Giá đóng cuối",
    "market.last_volume": "Khối lượng cuối",
    "market.candle_title": "Nến · theo khung đã chọn",
    "market.table_title": "Bảng phiên giao dịch",
    "market.picker": "Chọn mã",
    "market.filter_placeholder": "Lọc mã CK...",
    "market.col_time": "Thời gian",
    "market.col_open": "Mở",
    "market.col_high": "Cao",
    "market.col_low": "Thấp",
    "market.col_close": "Đóng",
    "market.col_volume": "Khối lượng",
    "market.csv": "CSV",
    "market.empty": "Không có dữ liệu cho",
    "market.stats_title": "Hồ sơ thống kê",
    "market.stats_sub": "Tính từ các phiên đã lưu trong lakehouse",
    "market.stats_empty": "Chưa tính được thống kê cho khung này",
    "market.stat_return": "Tổng lợi nhuận",
    "market.stat_volatility": "Biến động năm",
    "market.stat_drawdown": "Sụt giảm tối đa",
    "market.stat_high": "Cao nhất",
    "market.stat_low": "Thấp nhất",
    "market.stat_avg_volume": "KL bình quân",
    "market.stat_sessions": "Số phiên",
    "market.stat_up_days": "Phiên tăng",
    "market.stat_down_days": "Phiên giảm",
    "market.stat_total_volume": "Tổng KL",
    "market.compare_title": "So sánh nhiều mã",
    "market.compare_sub": "Mọi đường được chuẩn hoá về 100 tại đầu khoảng",
    "market.compare_add": "Thêm mã để so sánh",
    "market.compare_add_short": "Thêm",
    "market.compare_empty": "Chưa có mã nào để so sánh",
    "market.compare_col_symbol": "Mã",
    "market.compare_col_base": "Giá đầu khoảng",
    "market.compare_col_return": "Lợi nhuận khoảng",

    // Technical analysis
    "analysis.title": "Phân tích kỹ thuật",
    "analysis.subtitle":
      "Theo dõi xu hướng và động lượng giá. Chỉ báo không phải tín hiệu mua bán.",
    "analysis.indicator_label": "Chỉ báo",
    "analysis.window_label": "Cửa sổ",
    "analysis.compute": "Tính toán",
    "analysis.no_data": "Chưa có dữ liệu. Bấm Tính toán để chạy.",
    "analysis.rsi_period": "Kỳ RSI",
    "analysis.bars": "nến",
    "analysis.price_title": "Giá + SMA / EMA / Bollinger",
    "analysis.summary_title": "Tóm tắt chỉ báo",
    "analysis.trend": "Xu hướng",
    "analysis.momentum": "Động lượng",
    "analysis.volatility": "Biến động",
    "analysis.not_enough_data": "Chưa đủ dữ liệu để mô tả.",
    "analysis.overbought": "Quá mua",
    "analysis.oversold": "Quá bán",
    "analysis.neutral": "Trung tính",
    "close_above_sma20_sma50": "Giá nằm trên SMA20 và SMA20 nằm trên SMA50 (cấu trúc xu hướng tăng).",
    "close_below_sma20_sma50": "Giá nằm dưới SMA20 và SMA20 nằm dưới SMA50 (cấu trúc xu hướng giảm).",
    "ma_mixed": "Các đường trung bình đan xen, không có cấu trúc xu hướng rõ ràng.",
    "rsi_elevated": "RSI ở vùng cao theo lịch sử.",
    "rsi_depressed": "RSI ở vùng thấp theo lịch sử.",
    "rsi_mid": "RSI ở vùng trung tính.",
    "bb_above": "Giá đóng cửa nằm trên dải Bollinger trên (lệch mở rộng).",
    "bb_below": "Giá đóng cửa nằm dưới dải Bollinger dưới (lệch mở rộng).",
    "bb_inside": "Giá đóng cửa nằm trong dải Bollinger.",
    "bb_width": "Độ rộng dải là {width}.",
    "analysis.err_connect": "Không kết nối được backend API.",
    "analysis.empty_symbol": "Không có dữ liệu cho mã này.",

    // Forecasting
    "forecast.title": "Dự báo cổ phiếu",
    "forecast.subtitle":
      "Xem dự báo đã công bố hoặc chạy mô hình cho mã đang chọn. Kết quả chỉ mang tính tham khảo.",
    "forecast.explainer_title": "Hiểu các chỉ số và cách đọc dự báo",
    "forecast.explainer_intro":
      "Ở đây bạn huấn luyện một mô hình trên lịch sử giá của một mã cổ phiếu, rồi xem mô hình đó đã đoán sai bao nhiêu và dự báo giá cho các phiên sắp tới. Mọi con số đều chỉ mô tả quá khứ — chúng không phải lời khuyên mua bán.",
    "forecast.term_verification": "Kiểm chứng dự báo và thử mô hình",
    "forecast.term_verification_meaning":
      "Phần Kiểm chứng dự báo đối chiếu các dự báo đã lưu với giá thực tế, kèm nguồn công bố hoặc tái dựng. Phần thử mô hình bên dưới đo sai số trên tập hold-out. Mỗi phần thể hiện một phép đo riêng.",
    "forecast.term_holdout": "Hold-out (tập kiểm tra)",
    "forecast.term_holdout_meaning":
      "Phần dữ liệu mô hình chưa từng thấy khi huấn luyện. Đây là nơi đo độ chính xác thật của mô hình.",
    "forecast.term_mae": "MAE / RMSE",
    "forecast.term_mae_meaning":
      "Sai số trung bình (MAE) và sai số bình phương trung bình (RMSE), tính bằng đơn vị tiền. Càng nhỏ càng tốt.",
    "forecast.term_mape": "MAPE",
    "forecast.term_mape_meaning":
      "Sai số trung bình tính theo phần trăm. Cho phép so sánh giữa các mã có giá rất khác nhau.",
    "forecast.term_direction": "Directional Accuracy",
    "forecast.term_direction_meaning":
      "Tỉ lệ % phiên mà mô hình đoán đúng hướng đi lên hay xuống (không quan tâm độ lớn).",
    "forecast.term_lines": "Đường liền vs đường đứt",
    "forecast.term_lines_meaning":
      "Đường liền là giá thật. Đường đứt là ước lượng của mô hình cho các phiên đã xảy ra.",
    "forecast.term_region": "Vùng dự báo",
    "forecast.term_region_meaning":
      "Phần đường đứt nằm bên phắt vạch phân cách: đó là các phiên chưa xảy ra. Sai số tích luỹ dần theo mỗi bước.",
    "forecast.term_train_predict": "Train vs Predict",
    "forecast.term_train_predict_meaning":
      "Train là học lại mô hình từ đầu. Predict chỉ dùng mô hình đã có để dự báo — nhanh hơn nhiều.",
    "forecast.steps_label": "Cách dùng",
    "forecast.step_1": "Chọn mã cổ phiếu trên thanh đầu trang.",
    "forecast.step_2": "Chọn model (Linear Regression / ARIMA / LSTM) và số phiên muốn dự báo.",
    "forecast.step_3": "Bấm 'Train và Dự báo' — một bước là xong.",
    "forecast.step_4":
      "Nếu mã và model đã được huấn luyện, bấm 'Dùng mô hình đã có' để dự báo nhanh hơn.",
    "forecast.published_title": "Dự báo đã công bố",
    "forecast.published_sub":
      "Dự báo được ghi trước phiên giao dịch, kèm giá thực tế khi đã có.",
    "forecast.published_empty": "Không đọc được dự báo đã công bố.",
    "forecast.verification_title": "Kiểm chứng dự báo",
    "forecast.verification_sub":
      "Lịch sử dự báo so với giá thực tế, kèm sai số và nguồn của từng bản ghi.",
    "forecast.form_title": "Tạo dự báo cho",
    "forecast.model_label": "Model",
    "forecast.horizon_label": "Số phiên dự báo",
    "forecast.seq_label": "Sequence length",
    "forecast.hidden_label": "Hidden size",
    "forecast.layers_label": "Layers",
    "forecast.epochs_label": "Epochs",
    "forecast.train_predict": "Train và Dự báo",
    "forecast.reuse_model": "Dùng mô hình đã có",
    "forecast.running": "Đang chạy",
    "forecast.predicting": "Đang dự báo",
    "forecast.running_note":
      "Training/dự báo đang chạy. LSTM trên CPU có thể mất 30s đến 3 phút.",
    "forecast.train_error": "Training thất bại.",
    "forecast.predict_error": "Chưa có model cho mã này. Hãy bấm 'Train và Dự báo'.",
    "forecast.metrics_note":
      "Số trên được tính lại trên đúng tập hold-out hiển thị ở biểu đồ dưới.",
    "forecast.chart_title": "Giá thật và dự báo",
    "forecast.no_new_forecast": "Chưa có dự báo mới:",
    "forecast.empty_chart": "Train model để xem biểu đồ so sánh.",
    "forecast.empty_chart_hint":
      "Chọn model, số phiên rồi bấm 'Train và Dự báo', hoặc 'Dùng mô hình đã có' nếu đã huấn luyện.",
    "forecast.compare_title": "So sánh model",
    "forecast.compare_all": "So sánh tất cả",
    "forecast.compare_empty": "Bấm \"So sánh tất cả\" để xem bảng.",
    "forecast.best_mae": "MAE tốt nhất",
    "forecast.metric_mae": "MAE",
    "forecast.metric_rmse": "RMSE",
    "forecast.metric_mape": "MAPE",
    "forecast.metric_direction": "Directional Acc",
    "forecast.hint_mae": "Sai số tuyệt đối trung bình",
    "forecast.hint_rmse": "Sai số bình phương trung bình",
    "forecast.hint_mape": "Sai số % trung bình",
    "forecast.hint_direction": "% đoán đúng chiều",

    // Backtesting
    "backtest.title": "Đánh giá chiến lược",
    "backtest.subtitle":
      "Chạy một quy tắc mua/bán trên lịch sử thật, rồi so với đường cơ sở mua và giữ trên cùng các phiên.",
    "backtest.scope_label": "Phạm vi đánh giá",
    "backtest.tab_single": "Một mã cổ phiếu",
    "backtest.tab_population": "Walk-forward đa mã",
    "backtest.strategy_title": "Chiến lược",
    "backtest.strategy_label": "Chiến lược",
    "backtest.explainer_title": "Tab này dùng để làm gì?",
    "backtest.explainer_intro":
      "Backtest trả lời câu hỏi: nếu bạn áp dụng một quy tắc mua/bán theo lịch sử thật, bạn sẽ có bao nhiêu tiền? Hệ thống chơi lại từng phiên một: tính tín hiệu khi đóng cửa phiên hôm đó, rồi khớp lệnh vào giá mở cửa của phiên kế tiếp — nên không bao giờ dùng thông tin của tương lai.",
    "backtest.term_ma": "MA Crossover",
    "backtest.term_ma_meaning":
      "Mua khi đường trung bình ngắn hạn cắt lên đường trung bình dài hạn; bán khi cắt xuống.",
    "backtest.term_rsi": "RSI Strategy",
    "backtest.term_rsi_meaning":
      "Mua khi RSI rơi xuống dưới ngưỡng (ví dụ 30 = thị trường bị bán quá mức); bán khi RSI vượt ngưỡng trên (70).",
    "backtest.term_equity": "Equity curve",
    "backtest.term_equity_meaning":
      "Đường biểu diễn tổng giá trị tài khoản sau mỗi phiên. Đi lên là đang lãi, đi xuống là đang lỗ.",
    "backtest.term_return": "Total Return",
    "backtest.term_return_meaning":
      "Tổng lãi/lỗ tính theo phần trăm so với vốn ban đầu.",
    "backtest.term_drawdown": "Max Drawdown",
    "backtest.term_drawdown_meaning":
      "Mức lỗ tệ nhất tính từ đỉnh cao nhất xuống đáy thấp nhất. Càng nhỏ (ít âm) càng ổn định.",
    "backtest.term_sharpe": "Sharpe Ratio",
    "backtest.term_sharpe_meaning":
      "Lợi nhuận trên mỗi đơn vị rủi ro. Trên 1 là tốt, dưới 0 nghĩa là lãi ít hơn rủi ro.",
    "backtest.term_winrate": "Win Rate",
    "backtest.term_winrate_meaning":
      "Tỉ lệ % lệnh thắng. Cao không đảm bảo lãi — cần xem cả Total Return.",
    "backtest.term_profit": "Profit Factor",
    "backtest.term_profit_meaning": "Tổng lãi chia cho tổng lỗ. Trên 1 là lãi, dưới 1 là lỗ.",
    "backtest.term_fees": "Transaction fee / Slippage",
    "backtest.term_fees_meaning":
      "Chi phí mỗi lệnh và độ trượt giá so với giá mở cửa. Cả hai đều làm lợi nhuận thực tế thấp hơn.",
    "backtest.term_bh": "Mua & giữ (baseline)",
    "backtest.term_bh_meaning":
      "Kịch bản đối chứng: mua đầu kỳ và giữ đến cuối, trên cùng các phiên, cùng phí và cùng độ trượt. Nếu chiến lược không vượt được nó, thì việc chọn thời điểm vào lệnh không tạo thêm giá trị nào.",
    "backtest.steps_label": "Cách dùng",
    "backtest.step_1": "Chọn mã cổ phiếu và chiến lược muốn thử.",
    "backtest.step_2": "Đặt vốn ban đầu, phí giao dịch và độ trượt giá.",
    "backtest.step_3": "Bấm Chạy backtest để xem kết quả.",
    "backtest.step_4":
      "Đổi tham số (Short MA / Long MA hoặc ngưỡng RSI) rồi chạy lại để so sánh.",
    "backtest.step_5":
      "Sang tab 'Walk-forward đa mã' để biết kết quả này có đúng trên nhiều mã không.",
    "backtest.form_title": "Backtest ·",
    "backtest.final_value": "Giá trị cuối",
    "backtest.initial_capital": "Vốn ban đầu",
    "backtest.trades": "Số lệnh",
    "backtest.capital": "Vốn ban đầu",
    "backtest.fee": "Phí giao dịch",
    "backtest.slippage": "Độ trượt giá",
    "backtest.short_ma": "Short MA",
    "backtest.long_ma": "Long MA",
    "backtest.rsi_period": "RSI period",
    "backtest.lower": "Lower threshold",
    "backtest.upper": "Upper threshold",
    "backtest.run": "Chạy backtest",
    "backtest.running": "Đang chạy backtest",
    "backtest.run_error": "Backtest thất bại.",
    "backtest.done": "Backtest hoàn tất (lịch sử).",
    "backtest.empty": "Chạy backtest để xem equity curve, drawdown và danh sách trades.",
    "backtest.benchmark_title": "So sánh với mua & giữ",
    "backtest.bh_return": "Mua & giữ · Total Return",
    "backtest.bh_sharpe": "Mua & giữ · Sharpe",
    "backtest.bh_drawdown": "Mua & giữ · Max Drawdown",
    "backtest.excess": "Chiến lược vượt baseline",
    "backtest.benchmark_note":
      "Baseline \"mua & giữ\" được mô phỏng trên cùng các phiên, cùng phí giao dịch và cùng độ trượt giá với chiến lược. Nếu chiến lược không vượt được đường này thì đó là bằng chứng rằng việc chọn điểm vào lệnh chưa tạo ra giá trị. Xem tab \"Walk-forward đa mã\" để biết kết quả này có đúng trên nhiều mã hay chỉ đúng với mã này.",
    "backtest.equity_title": "Equity curve",
    "backtest.drawdown_title": "Drawdown",
    "backtest.trades_title": "Lịch sử lệnh ·",
    "backtest.trades_suffix": "lệnh",

    // Multi-symbol walk-forward
    "walkforward.explainer_title": "Tab này dùng để làm gì?",
    "walkforward.explainer_intro":
      "Một backtest trên một mã cổ phiếu không phải là bằng chứng. Tab này chạy cùng một cơ chế walk-forward trên hàng chục mã thuộc nhiều sàn khác nhau, rồi báo cáo PHÂN PHỐI kết quả: giá trị trung vị, tỉ lệ mã có lãi, và phân tách theo sàn. Mỗi cửa sổ kiểm tra được đo cả chiến lược lẫn đường cơ sở mua và giữ trên đúng những phiên đó, nên phần chênh lệch là so sánh cặp (paired) chứ không phải hiệu của hai trung bình độc lập.",
    "walkforward.term_walkforward": "Walk-forward",
    "walkforward.term_walkforward_meaning":
      "Chia lịch sử thành các cửa sổ trượt: huấn luyện trên một đoạn, kiểm tra trên đoạn kế tiếp chưa từng thấy. Lặp lại nhiều lần rồi lấy trung bình, nên giảm hiệu ứng quá khớp tham số.",
    "walkforward.term_oos": "Ngoài mẫu (out-of-sample)",
    "walkforward.term_oos_meaning":
      "Phần dữ liệu chiến lược chưa từng được nhìn thấy khi chọn tham số. Đây mới là kỳ vọng hợp lý về hiệu quả thật.",
    "walkforward.term_bh": "Mua & giữ (baseline)",
    "walkforward.term_bh_meaning":
      "Giải pháp rỗng: mua đầu kỳ, giữ đến cuối, trên cùng các phiên và cùng bộ chi phí. Chiến lược phải thắng đường này mới được coi là tạo thêm giá trị.",
    "walkforward.term_median": "Median",
    "walkforward.term_median_meaning":
      "Giá trị trung vị. Dùng thay cho trung bình vì một mã tăng rất mạnh có thể kéo trung bình lệch, còn trung vị thì không.",
    "walkforward.term_excess": "Excess return",
    "walkforward.term_excess_meaning":
      "Chênh lệch giữa chiến lược và mua & giữ trên cùng một cửa sổ. Âm nghĩa là chiến lược làm tệ hơn việc cứ nắm giữ.",
    "walkforward.step_1": "Chọn chiến lược ở đầu trang — cùng lựa chọn với tab một mã.",
    "walkforward.step_2": "Đọc hàng so sánh giữa chiến lược và mua & giữ ở phần đầu.",
    "walkforward.step_3": "Xem bảng theo sàn để biết kết quả có phổ biến hay chỉ đúng ở một vài thị trường.",
    "walkforward.step_4": "Cuộn xuống bảng từng mã để xem mã nào thắng và mã nào thua.",
    "walkforward.loading": "Đang tải báo cáo...",
    "walkforward.load_error": "Không tải được báo cáo.",
    "walkforward.missing": "Chưa có báo cáo.",
    "walkforward.how_to_title": "Cách tạo báo cáo",
    "walkforward.how_to_note":
      "Lệnh này mất khoảng 2 phút và ghi kết quả vào tầng backtests của lakehouse. Hệ thống cũng chạy lệnh này tự động mỗi tối qua cron job 'walk-forward'.",
    "walkforward.headline": "Chiến lược vs mua & giữ ·",
    "walkforward.generated_at": "Đo lúc",
    "walkforward.symbols_on": "mã trên",
    "walkforward.median_strategy": "Median lợi nhuận · chiến lược",
    "walkforward.median_bh": "Median lợi nhuận · mua & giữ",
    "walkforward.median_sharpe_strategy": "Median Sharpe · chiến lược",
    "walkforward.median_sharpe_bh": "Median Sharpe · mua & giữ",
    "walkforward.pct_profitable_strategy": "% mã có lãi · chiến lược",
    "walkforward.pct_profitable_bh": "% mã có lãi · mua & giữ",
    "walkforward.pct_windows_beating": "% cửa sổ thắng baseline",
    "walkforward.median_excess": "Median excess return",
    "walkforward.paired_note":
      "So sánh cặp trên {windows} cửa sổ kiểm tra. Mỗi cửa sổ đóng góp một chênh lệch giữa chiến lược và mua & giữ, nên hai bên luôn được đo trên cùng những phiên giống nhau.",
    "walkforward.verdict_label": "Kết luận của phép đo",
    "walkforward.verdict_negative":
      "Trên phép đo này, chiến lược KHÔNG vượt được đường cơ sở mua và giữ: chênh lệch trung vị theo cửa sổ là {excess}, và chỉ {pct}% số mã thắng được baseline. Đây là phát hiện thật, không phải lỗi kỹ thuật: chiến lược có lợi thế là giảm biến động (median drawdown nhỏ hơn), nhưng cái giá phải trả là bỏ lỡ phần lợi nhuận của xu hướng.",
    "walkforward.verdict_positive":
      "Trên phép đo này, chiến lược vượt được đường cơ sở mua và giữ với chênh lệch trung vị {excess} theo cửa sổ, và {pct}% số mã thắng được baseline.",
    "walkforward.by_exchange": "Phân phối theo sàn",
    "walkforward.per_symbol": "Chi tiết từng mã ·",
    "walkforward.symbols_suffix": "mã",
    "walkforward.unmeasurable": "Mã không đo được ·",
    "walkforward.reason": "Lý do",
    "walkforward.yes": "Có",
    "walkforward.no": "Không",
    "walkforward.col_exchange": "Sàn",
    "walkforward.col_symbols": "Số mã",
    "walkforward.col_median_strategy": "Median RR chiến lược",
    "walkforward.col_median_bh": "Median RR mua&giữ",
    "walkforward.col_sharpe_strategy": "Sharpe CL",
    "walkforward.col_sharpe_bh": "Sharpe B&H",
    "walkforward.col_pct_beating": "% mã thắng B&H",
    "walkforward.col_symbol": "Mã",
    "walkforward.col_windows": "Cửa sổ",
    "walkforward.col_rr_strategy": "RR chiến lược",
    "walkforward.col_rr_bh": "RR mua&giữ",
    "walkforward.col_maxdd_strategy": "MaxDD CL",
    "walkforward.col_maxdd_bh": "MaxDD B&H",
    "walkforward.col_beat": "Thắng B&H",
    "walkforward.series_strategy": "Chiến lược",
    "walkforward.series_bh": "Mua & giữ",

    // AI Agent
    "agent.title": "AI Agent",
    "agent.subtitle": "Phân tích thị trường, tra cứu dữ liệu và khám phá chiến lược cùng StockVision AI.",
    "agent.symbol_badge": "Symbol",
    "agent.clear": "Xoá",
    "agent.new_chat": "Chat mới",
    "agent.history": "Lịch sử",
    "agent.history_loading": "Đang tải lịch sử…",
    "agent.history_empty": "Chưa có cuộc trò chuyện nào.",
    "agent.untitled": "Cuộc trò chuyện không tiêu đề",
    "agent.delete_chat": "Xoá cuộc trò chuyện này",
    "agent.welcome_title": "Chào mừng đến với StockVision AI",
    "agent.welcome_body": "Tôi có thể giúp bạn phân tích kỹ thuật, so sánh mô hình dự báo, đánh giá chiến lược và giải thích các chỉ số dựa trên dữ liệu thị trường của hệ thống.",
    "agent.welcome_warn": "Phân tích và dự báo mang tính tham khảo, không phải khuyến nghị đầu tư.",
    "agent.placeholder": "Phân tích kỹ thuật AAPL 3 tháng gần nhất...",
    "agent.send": "Gửi",
    "agent.thinking": "Agent đang gọi tool và suy nghĩ",
    "agent.failed": "Agent request failed.",

    // System status
    "system.title": "Trạng thái hệ thống",
    "system.backend": "Backend API",
    "system.mysql": "MySQL",
    "system.minio": "MinIO (S3)",
    "system.data_source": "Nguồn dữ liệu",
    "system.ai_agent": "AI Agent",
    "system.data_quality": "Kiểm chứng dữ liệu",
    "system.online": "Online",
    "system.offline": "Offline",
    "system.disabled": "Tắt",
    "system.connected": "Đã kết nối",
    "system.disconnected": "Mất kết nối",
    "system.counts": "Số object theo layer",
    "system.bronze": "Bronze",
    "system.silver": "Silver",
    "system.gold": "Gold",
    "system.refresh": "Làm mới",
    "system.refreshing": "Đang tải…",
    "interval.loading": "đang tải…",
  },
  en: {
    "app.title": "StockVision AI",
    "app.subtitle": "Stock Analytics & Forecasting",
    "app.footer_disclaimer": "For information only · Not investment advice",

    "nav.overview": "Overview",
    "nav.data": "Data",
    "nav.models": "Models",
    "nav.agent": "Agent",
    "nav.platform": "Platform",
    "nav.dashboard": "Overview",
    "nav.market": "Market",
    "nav.analysis": "Analysis",
    "nav.forecast": "Forecasts",
    "nav.backtesting": "Strategies",
    "nav.agent_full": "AI Assistant",
    "nav.system": "System",
    "nav.tools": "Tools",

    "dashboard.title": "Overview",
    "dashboard.metrics": "Metrics · 5 columns",
    "dashboard.price": "Latest close",
    "dashboard.change_pct": "Change %",
    "dashboard.volume": "Volume",
    "dashboard.volume_hint": "Latest session",
    "dashboard.rsi": "RSI (14)",
    "dashboard.rsi_hint": "Gold layer",
    "dashboard.model": "Latest model",
    "dashboard.model_no_train": "Not trained",
    "dashboard.model_hint_trained": "MAE",
    "dashboard.model_hint_untrained": "Train to start",
    "dashboard.line_chart_title": "Price trend",
    "dashboard.line_chart_sub": "Line drawn directly from Gold layer",
    "dashboard.candle_title": "Candles · Bronze layer",
    "dashboard.candle_sub": "Raw OHLCV, unprocessed",
    "dashboard.volume_title": "Volume bars",
    "dashboard.volume_sub": "Selected range and timeframe",
    "dashboard.empty_candle": "No candle data.",
    "dashboard.empty_symbol": "No data for this symbol.",
    "dashboard.err_connect": "Cannot connect to backend API.",
    "dashboard.data_source": "Data source",
    "dashboard.pipeline": "Pipeline",
    "dashboard.last_update": "Updated",

    "market.title": "Market Data",
    "market.subtitle": "Track prices, compare stocks and explore trading history.",
    "market.source": "Source",
    "market.rows": "Rows",
    "market.last_close": "Last close",
    "market.last_volume": "Last volume",
    "market.candle_title": "Candles · selected window",
    "market.table_title": "Session table",
    "market.picker": "Symbol picker",
    "market.filter_placeholder": "Filter ticker...",
    "market.col_time": "Time",
    "market.col_open": "Open",
    "market.col_high": "High",
    "market.col_low": "Low",
    "market.col_close": "Close",
    "market.col_volume": "Volume",
    "market.csv": "CSV",
    "market.empty": "No data for",
    "market.stats_title": "Statistical profile",
    "market.stats_sub": "Computed from the sessions stored in the lakehouse",
    "market.stats_empty": "Statistics not available for this window",
    "market.stat_return": "Total return",
    "market.stat_volatility": "Volatility (ann.)",
    "market.stat_drawdown": "Max drawdown",
    "market.stat_high": "High",
    "market.stat_low": "Low",
    "market.stat_avg_volume": "Avg volume",
    "market.stat_sessions": "Sessions",
    "market.stat_up_days": "Up days",
    "market.stat_down_days": "Down days",
    "market.stat_total_volume": "Total volume",
    "market.compare_title": "Cross-ticker comparison",
    "market.compare_sub": "Every line is rebased to 100 at the start of the window",
    "market.compare_add": "Add a ticker",
    "market.compare_add_short": "Add",
    "market.compare_empty": "No tickers to compare yet",
    "market.compare_col_symbol": "Symbol",
    "market.compare_col_base": "Base price",
    "market.compare_col_return": "Window return",

    "analysis.title": "Technical Analysis",
    "analysis.subtitle":
      "Track trend and momentum. Indicators are not buy or sell signals.",
    "analysis.indicator_label": "Indicator",
    "analysis.window_label": "Window",
    "analysis.compute": "Compute",
    "analysis.no_data": "No data yet. Click Compute to run.",
    "analysis.rsi_period": "RSI period",
    "analysis.bars": "bars",
    "analysis.price_title": "Price + SMA / EMA / Bollinger",
    "analysis.summary_title": "Indicator summary",
    "analysis.trend": "Trend",
    "analysis.momentum": "Momentum",
    "analysis.volatility": "Volatility",
    "analysis.not_enough_data": "Not enough data to describe yet.",
    "analysis.overbought": "Overbought",
    "analysis.oversold": "Oversold",
    "analysis.neutral": "Neutral",
    "analysis.err_connect": "Cannot connect to backend API.",
    "close_above_sma20_sma50": "Price is above SMA20 and SMA20 is above SMA50 (uptrend structure).",
    "close_below_sma20_sma50": "Price is below SMA20 and SMA20 is below SMA50 (downtrend structure).",
    "ma_mixed": "Moving averages are mixed; no dominant trend structure.",
    "rsi_elevated": "RSI is in the historically elevated zone.",
    "rsi_depressed": "RSI is in the historically depressed zone.",
    "rsi_mid": "RSI is in a mid-range zone.",
    "bb_above": "Close is above the upper Bollinger Band (expanded deviation).",
    "bb_below": "Close is below the lower Bollinger Band (expanded deviation).",
    "bb_inside": "Close is inside the Bollinger Band.",
    "bb_width": "Band width is {width}.",
    "analysis.empty_symbol": "No data for this symbol.",

    "forecast.title": "Stock Forecast",
    "forecast.subtitle":
      "Read the published forecasts or run a model on the selected symbol. Results are for reference only.",
    "forecast.explainer_title": "Understanding the metrics and reading a forecast",
    "forecast.explainer_intro":
      "Here you train a model on one ticker's price history, then see how often it was wrong and what it predicts for the sessions ahead. Every number describes the past — none of them is advice to buy or sell.",
    "forecast.term_verification": "Forecast verification and model trials",
    "forecast.term_verification_meaning":
      "The verification section scores stored forecasts against the real close, with the publication source. The model trial below measures the error on the hold-out split. Each is a separate measurement.",
    "forecast.term_holdout": "Hold-out split",
    "forecast.term_holdout_meaning":
      "The part of the data the model never saw while training. This is where the model's true accuracy is measured.",
    "forecast.term_mae": "MAE / RMSE",
    "forecast.term_mae_meaning":
      "Mean absolute error and root mean squared error, in the instrument's own currency. Smaller is better.",
    "forecast.term_mape": "MAPE",
    "forecast.term_mape_meaning":
      "Mean absolute percentage error. Lets you compare tickers whose prices differ by orders of magnitude.",
    "forecast.term_direction": "Directional Accuracy",
    "forecast.term_direction_meaning":
      "The share of sessions where the model called the direction (up or down) correctly, regardless of magnitude.",
    "forecast.term_lines": "Solid line vs dashed line",
    "forecast.term_lines_meaning":
      "The solid line is the real close. The dashed line is the model's estimate for sessions that already happened.",
    "forecast.term_region": "The forecast region",
    "forecast.term_region_meaning":
      "The dashed line to the right of the divider: sessions that have not happened yet. The error accumulates step by step.",
    "forecast.term_train_predict": "Train vs Predict",
    "forecast.term_train_predict_meaning":
      "Train relearns the model from scratch. Predict reuses the model that already exists — much faster.",
    "forecast.steps_label": "How to use it",
    "forecast.step_1": "Pick a ticker in the top bar.",
    "forecast.step_2": "Choose a model (Linear Regression / ARIMA / LSTM) and how many sessions to forecast.",
    "forecast.step_3": "Press 'Train and Predict' — one step is enough.",
    "forecast.step_4":
      "If the ticker and model are already trained, press 'Use the existing model' for a faster run.",
    "forecast.published_title": "Published forecasts",
    "forecast.published_sub":
      "Recorded before the session opened, with the real close once it exists.",
    "forecast.published_empty": "Cannot read the published forecasts.",
    "forecast.verification_title": "Forecast verification",
    "forecast.verification_sub":
      "The forecast history against the real close, with the error and the source of each record.",
    "forecast.form_title": "Create a forecast for",
    "forecast.model_label": "Model",
    "forecast.horizon_label": "Forecast horizon",
    "forecast.seq_label": "Sequence length",
    "forecast.hidden_label": "Hidden size",
    "forecast.layers_label": "Layers",
    "forecast.epochs_label": "Epochs",
    "forecast.train_predict": "Train and Predict",
    "forecast.reuse_model": "Use the existing model",
    "forecast.running": "Running",
    "forecast.predicting": "Predicting",
    "forecast.running_note":
      "Training/prediction is running. An LSTM on CPU can take 30s to 3 minutes.",
    "forecast.train_error": "Training failed.",
    "forecast.predict_error": "No model for this ticker yet. Press 'Train and Predict'.",
    "forecast.metrics_note":
      "The numbers above were recomputed on the same hold-out split shown in the chart below.",
    "forecast.chart_title": "Actual price and forecast",
    "forecast.no_new_forecast": "No new forecast:",
    "forecast.empty_chart": "Train a model to see the comparison chart.",
    "forecast.empty_chart_hint":
      "Pick a model and a horizon, then press 'Train and Predict' — or 'Use the existing model' if it is already trained.",
    "forecast.compare_title": "Model comparison",
    "forecast.compare_all": "Compare all",
    "forecast.compare_empty": "Press \"Compare all\" to see the table.",
    "forecast.best_mae": "Best MAE",
    "forecast.metric_mae": "MAE",
    "forecast.metric_rmse": "RMSE",
    "forecast.metric_mape": "MAPE",
    "forecast.metric_direction": "Directional Acc",
    "forecast.hint_mae": "Mean absolute error",
    "forecast.hint_rmse": "Root mean squared error",
    "forecast.hint_mape": "Mean percentage error",
    "forecast.hint_direction": "% of correct directions",

    "backtest.title": "Strategy evaluation",
    "backtest.subtitle":
      "Run a buy/sell rule against real history, then compare it with buying and holding over the same sessions.",
    "backtest.scope_label": "Evaluation scope",
    "backtest.tab_single": "Single ticker",
    "backtest.tab_population": "Multi-symbol walk-forward",
    "backtest.strategy_title": "Strategy",
    "backtest.strategy_label": "Strategy",
    "backtest.explainer_title": "What this tab is for",
    "backtest.explainer_intro":
      "A backtest answers one question: if you had applied a buy/sell rule to real history, what would you have made? The system replays it session by session — it computes the signal at that session's close, then fills the order at the NEXT session's open, so it never uses information from the future.",
    "backtest.term_ma": "MA Crossover",
    "backtest.term_ma_meaning":
      "Buy when the short moving average crosses above the long one; sell when it crosses back below.",
    "backtest.term_rsi": "RSI Strategy",
    "backtest.term_rsi_meaning":
      "Buy when RSI falls below the lower threshold (e.g. 30 = the market is oversold); sell when it rises above the upper one (70).",
    "backtest.term_equity": "Equity curve",
    "backtest.term_equity_meaning":
      "The total account value after each session. Going up means gaining; going down means losing.",
    "backtest.term_return": "Total Return",
    "backtest.term_return_meaning": "Total profit or loss as a percentage of the starting capital.",
    "backtest.term_drawdown": "Max Drawdown",
    "backtest.term_drawdown_meaning":
      "The worst drop from a peak to a trough. The smaller (less negative) it is, the more stable the strategy.",
    "backtest.term_sharpe": "Sharpe Ratio",
    "backtest.term_sharpe_meaning":
      "Return per unit of risk. Above 1 is good; below 0 means the reward was smaller than the risk taken.",
    "backtest.term_winrate": "Win Rate",
    "backtest.term_winrate_meaning":
      "The share of winning trades. A high rate does not guarantee a profit — read Total Return alongside it.",
    "backtest.term_profit": "Profit Factor",
    "backtest.term_profit_meaning": "Gross profit divided by gross loss. Above 1 is a profit, below 1 is a loss.",
    "backtest.term_fees": "Transaction fee / Slippage",
    "backtest.term_fees_meaning":
      "The cost of each trade and the price slippage against the open. Both make the realised return lower.",
    "backtest.term_bh": "Buy & hold (baseline)",
    "backtest.term_bh_meaning":
      "The reference scenario: buy at the start, hold to the end, over the same sessions with the same costs. If the strategy cannot beat it, then timing the entries created no extra value.",
    "backtest.steps_label": "How to use it",
    "backtest.step_1": "Pick a ticker and the strategy to try.",
    "backtest.step_2": "Set the starting capital, the transaction fee and the slippage.",
    "backtest.step_3": "Press Run backtest to see the result.",
    "backtest.step_4":
      "Change a parameter (Short MA / Long MA or the RSI thresholds) and run again to compare.",
    "backtest.step_5":
      "Switch to the 'Multi-symbol walk-forward' tab to see whether the result holds across many tickers.",
    "backtest.form_title": "Backtest ·",
    "backtest.final_value": "Final value",
    "backtest.initial_capital": "Initial capital",
    "backtest.trades": "Trades",
    "backtest.capital": "Initial capital",
    "backtest.fee": "Transaction fee",
    "backtest.slippage": "Slippage",
    "backtest.short_ma": "Short MA",
    "backtest.long_ma": "Long MA",
    "backtest.rsi_period": "RSI period",
    "backtest.lower": "Lower threshold",
    "backtest.upper": "Upper threshold",
    "backtest.run": "Run backtest",
    "backtest.running": "Running backtest",
    "backtest.run_error": "Backtest failed.",
    "backtest.done": "Backtest finished (historical).",
    "backtest.empty": "Run a backtest to see the equity curve, the drawdown and the trade list.",
    "backtest.benchmark_title": "Compared with buy & hold",
    "backtest.bh_return": "Buy & hold · Total Return",
    "backtest.bh_sharpe": "Buy & hold · Sharpe",
    "backtest.bh_drawdown": "Buy & hold · Max Drawdown",
    "backtest.excess": "Strategy beats baseline",
    "backtest.benchmark_note":
      "The \"buy & hold\" baseline is simulated over the same sessions, with the same transaction fee and the same slippage as the strategy. If the strategy cannot beat this line, that is evidence that choosing the entry point created no extra value. See the \"Multi-symbol walk-forward\" tab to find out whether the result holds across many tickers or only for this one.",
    "backtest.equity_title": "Equity curve",
    "backtest.drawdown_title": "Drawdown",
    "backtest.trades_title": "Trade history ·",
    "backtest.trades_suffix": "trades",

    // Multi-symbol walk-forward
    "walkforward.explainer_title": "What this tab is for",
    "walkforward.explainer_intro":
      "A backtest on one ticker is not evidence. This tab runs the same walk-forward mechanism across dozens of tickers from several exchanges, then reports the DISTRIBUTION of the results: the median, the share of tickers that profited, and a breakdown by exchange. Every test window measures both the strategy and the buy-and-hold baseline over exactly the same sessions, so the difference is a paired comparison rather than a difference of two independent means.",
    "walkforward.term_walkforward": "Walk-forward",
    "walkforward.term_walkforward_meaning":
      "The history is split into rolling windows: train on one stretch, test on the next stretch it has never seen. Repeating that and averaging reduces the effect of overfitting the parameters.",
    "walkforward.term_oos": "Out-of-sample",
    "walkforward.term_oos_meaning":
      "The part of the data the strategy never saw while its parameters were chosen. This is the fair expectation of real performance.",
    "walkforward.term_bh": "Buy & hold (baseline)",
    "walkforward.term_bh_meaning":
      "The null solution: buy at the start, hold to the end, over the same sessions and the same cost model. A strategy only creates value if it beats this line.",
    "walkforward.term_median": "Median",
    "walkforward.term_median_meaning":
      "The middle value. Used instead of the mean because one very strong ticker can drag a mean sideways, while the median does not move.",
    "walkforward.term_excess": "Excess return",
    "walkforward.term_excess_meaning":
      "The gap between the strategy and buy & hold over the same window. A negative value means the strategy did worse than simply holding.",
    "walkforward.step_1": "Pick the strategy at the top of the page — the same choice as the single-ticker tab.",
    "walkforward.step_2": "Read the strategy-versus-buy-and-hold row at the top.",
    "walkforward.step_3": "Check the by-exchange table to see whether the result is broad or confined to a few markets.",
    "walkforward.step_4": "Scroll down the per-ticker table to see which tickers won and which lost.",
    "walkforward.loading": "Loading the report...",
    "walkforward.load_error": "Cannot load the report.",
    "walkforward.missing": "No report yet.",
    "walkforward.how_to_title": "How to generate the report",
    "walkforward.how_to_note":
      "This command takes about two minutes and writes the result into the lakehouse's backtests layer. The system also runs it automatically every night, via the 'walk-forward' cron job.",
    "walkforward.headline": "Strategy vs buy & hold ·",
    "walkforward.generated_at": "Measured at",
    "walkforward.symbols_on": "tickers out of",
    "walkforward.median_strategy": "Median return · strategy",
    "walkforward.median_bh": "Median return · buy & hold",
    "walkforward.median_sharpe_strategy": "Median Sharpe · strategy",
    "walkforward.median_sharpe_bh": "Median Sharpe · buy & hold",
    "walkforward.pct_profitable_strategy": "% of tickers profitable · strategy",
    "walkforward.pct_profitable_bh": "% of tickers profitable · buy & hold",
    "walkforward.pct_windows_beating": "% of windows beating the baseline",
    "walkforward.median_excess": "Median excess return",
    "walkforward.paired_note":
      "A paired comparison across {windows} test windows. Each window contributes one difference between the strategy and buy & hold, so both sides are always measured over the same sessions.",
    "walkforward.verdict_label": "What the measurement says",
    "walkforward.verdict_negative":
      "On this measurement, the strategy does NOT beat the buy-and-hold baseline: the median per-window gap is {excess}, and only {pct}% of tickers beat the baseline. That is a real finding, not a bug: the strategy's advantage is lower volatility (a smaller median drawdown), and the price of that is giving up part of a trending market's upside.",
    "walkforward.verdict_positive":
      "On this measurement, the strategy beats the buy-and-hold baseline with a median per-window gap of {excess}, and {pct}% of tickers beat the baseline.",
    "walkforward.by_exchange": "Distribution by exchange",
    "walkforward.per_symbol": "Per-ticker detail ·",
    "walkforward.symbols_suffix": "tickers",
    "walkforward.unmeasurable": "Tickers that could not be measured ·",
    "walkforward.reason": "Reason",
    "walkforward.yes": "Yes",
    "walkforward.no": "No",
    "walkforward.col_exchange": "Exchange",
    "walkforward.col_symbols": "Tickers",
    "walkforward.col_median_strategy": "Median ret · strategy",
    "walkforward.col_median_bh": "Median ret · B&H",
    "walkforward.col_sharpe_strategy": "Sharpe strat",
    "walkforward.col_sharpe_bh": "Sharpe B&H",
    "walkforward.col_pct_beating": "% beating B&H",
    "walkforward.col_symbol": "Ticker",
    "walkforward.col_windows": "Windows",
    "walkforward.col_rr_strategy": "Ret · strategy",
    "walkforward.col_rr_bh": "Ret · B&H",
    "walkforward.col_maxdd_strategy": "MaxDD strat",
    "walkforward.col_maxdd_bh": "MaxDD B&H",
    "walkforward.col_beat": "Beat B&H",
    "walkforward.series_strategy": "Strategy",
    "walkforward.series_bh": "Buy & hold",

    "agent.title": "AI Agent",
    "agent.subtitle": "Analyze markets, explore data, and evaluate strategies with StockVision AI.",
    "agent.symbol_badge": "Symbol",
    "agent.clear": "Clear",
    "agent.new_chat": "New chat",
    "agent.history": "History",
    "agent.history_loading": "Loading history…",
    "agent.history_empty": "No conversations yet.",
    "agent.untitled": "Untitled conversation",
    "agent.delete_chat": "Delete this conversation",
    "agent.welcome_title": "Welcome to StockVision AI",
    "agent.welcome_body": "I can help you analyze technical indicators, compare forecast models, evaluate strategies, and understand metrics using the platform's market data.",
    "agent.welcome_warn": "Analysis and forecasts are for information only, not investment advice.",
    "agent.placeholder": "Technical analysis of AAPL for the past 3 months...",
    "agent.send": "Send",
    "agent.thinking": "Agent is calling tools and thinking",
    "agent.failed": "Agent request failed.",

    "system.title": "System Status",
    "system.backend": "Backend API",
    "system.mysql": "MySQL",
    "system.minio": "MinIO (S3)",
    "system.data_source": "Data source",
    "system.ai_agent": "AI Agent",
    "system.data_quality": "Data quality gate",
    "system.online": "Online",
    "system.offline": "Offline",
    "system.disabled": "Disabled",
    "system.connected": "Connected",
    "system.disconnected": "Disconnected",
    "system.counts": "Objects by layer",
    "system.bronze": "Bronze",
    "system.silver": "Silver",
    "system.gold": "Gold",
    "system.refresh": "Refresh",
    "system.refreshing": "Loading…",
    "interval.loading": "loading…",
  },
};

// ── Context ────────────────────────────────────────────────────────────────
type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
};

const I18nContext = createContext<Ctx | null>(null);

const STORAGE_KEY = "stock-lakehouse-locale";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window === "undefined") return "vi";
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "en" || stored === "vi" ? stored : "vi";
  });

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
      document.documentElement.lang = next === "vi" ? "vi" : "en";
    }
  }, []);

  const ctx = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <I18nContext.Provider value={ctx}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  return ctx ?? { locale: "vi", setLocale: () => undefined };
}

// ── Translation helper ─────────────────────────────────────────────────────
export function t(key: string, locale: Locale = "vi"): string {
  return DICT[locale][key] ?? DICT.vi[key] ?? key;
}
