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
    "app.title": "Stock Lakehouse AI",
    "app.subtitle": "AI / Medallion / VN",

    // Sidebar
    "nav.overview": "Tổng quan",
    "nav.data": "Dữ liệu",
    "nav.models": "Mô hình",
    "nav.agent": "Agent",
    "nav.platform": "Hệ thống",
    "nav.dashboard": "Dashboard",
    "nav.market": "Dữ liệu thị trường",
    "nav.analysis": "Phân tích kỹ thuật",
    "nav.forecast": "Huấn luyện & so sánh model",
    "nav.backtesting": "Đánh giá chiến lược",
    "nav.agent_full": "AI Agent",
    "nav.system": "Trạng thái hệ thống",

    // Dashboard
    "dashboard.title": "Tổng quan",
    "dashboard.metrics": "Chỉ số · 5 cột",
    "dashboard.price": "Giá hiện tại",
    "dashboard.change_pct": "Biến động %",
    "dashboard.volume": "Khối lượng",
    "dashboard.volume_hint": "Phiên gần nhất",
    "dashboard.rsi": "RSI (14)",
    "dashboard.rsi_hint": "Gold layer",
    "dashboard.model": "Mô hình gần nhất",
    "dashboard.model_no_train": "Chưa train",
    "dashboard.model_hint_trained": "MAE",
    "dashboard.model_hint_untrained": "Train để bắt đầu",
    "dashboard.line_chart_title": "Giá theo khoảng đã chọn",
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
    "market.subtitle": "Kho dữ liệu gốc: thống kê, so sánh nhiều mã và toàn bộ phiên giao dịch",
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
    "analysis.indicator_label": "Chỉ báo",
    "analysis.window_label": "Cửa sổ",
    "analysis.compute": "Tính toán",
    "analysis.no_data": "Chưa có dữ liệu. Bấm Tính toán để chạy.",

    // Forecasting
    "forecast.title": "Huấn luyện & so sánh model",
    "forecast.model": "Mô hình",
    "forecast.horizon": "Số phiên dự báo",
    "forecast.train": "Train & dự báo",
    "forecast.training": "Đang train…",
    "forecast.compare": "So sánh các mô hình",
    "forecast.metrics": "Chỉ số đánh giá",
    "forecast.predict": "Dự đoán",
    "forecast.actual": "Giá thực tế",
    "forecast.future": "Tương lai",

    // Backtesting
    "backtest.title": "Backtest",
    "backtest.strategy": "Chiến lược",
    "backtest.start": "Ngày bắt đầu",
    "backtest.end": "Ngày kết thúc",
    "backtest.capital": "Vốn ban đầu",
    "backtest.run": "Chạy backtest",
    "backtest.running": "Đang chạy…",
    "backtest.metrics": "Chỉ số",
    "backtest.equity_curve": "Đường vốn",
    "backtest.trades": "Lệnh",

    // AI Agent
    "agent.title": "AI Agent",
    "agent.subtitle": "Agent gọi tool backend. Không bịa giá, indicator, forecast hay backtest metrics.",
    "agent.symbol_badge": "Symbol",
    "agent.clear": "Xoá",
    "agent.new_chat": "Chat mới",
    "agent.history": "Lịch sử",
    "agent.history_loading": "Đang tải lịch sử…",
    "agent.history_empty": "Chưa có cuộc trò chuyện nào.",
    "agent.untitled": "Cuộc trò chuyện không tiêu đề",
    "agent.delete_chat": "Xoá cuộc trò chuyện này",
    "agent.welcome_title": "Chào thầy/cô",
    "agent.welcome_body": "Em có thể phân tích kỹ thuật, so sánh mô hình dự báo, chạy backtest, hoặc giải thích chỉ số. Dữ liệu lấy thẳng từ lakehouse phía sau.",
    "agent.welcome_warn": "Lưu ý: không phải khuyến nghị đầu tư. Demo học thuật.",
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
    "app.title": "Stock Lakehouse AI",
    "app.subtitle": "AI / Medallion / VN",

    "nav.overview": "Overview",
    "nav.data": "Data",
    "nav.models": "Models",
    "nav.agent": "Agent",
    "nav.platform": "Platform",
    "nav.dashboard": "Dashboard",
    "nav.market": "Market Data",
    "nav.analysis": "Technical Analysis",
    "nav.forecast": "Model Training & Comparison",
    "nav.backtesting": "Strategy Evaluation",
    "nav.agent_full": "AI Agent",
    "nav.system": "System Status",

    "dashboard.title": "Overview",
    "dashboard.metrics": "Metrics · 5 columns",
    "dashboard.price": "Current price",
    "dashboard.change_pct": "Change %",
    "dashboard.volume": "Volume",
    "dashboard.volume_hint": "Latest session",
    "dashboard.rsi": "RSI (14)",
    "dashboard.rsi_hint": "Gold layer",
    "dashboard.model": "Latest model",
    "dashboard.model_no_train": "Not trained",
    "dashboard.model_hint_trained": "MAE",
    "dashboard.model_hint_untrained": "Train to start",
    "dashboard.line_chart_title": "Price · selected range",
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
    "market.subtitle": "The raw archive: statistics, cross-ticker comparison, and every session",
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
    "analysis.indicator_label": "Indicator",
    "analysis.window_label": "Window",
    "analysis.compute": "Compute",
    "analysis.no_data": "No data yet. Click Compute to run.",

    "forecast.title": "Model Training & Comparison",
    "forecast.model": "Model",
    "forecast.horizon": "Forecast horizon",
    "forecast.train": "Train & predict",
    "forecast.training": "Training…",
    "forecast.compare": "Compare models",
    "forecast.metrics": "Evaluation metrics",
    "forecast.predict": "Prediction",
    "forecast.actual": "Actual price",
    "forecast.future": "Future",

    "backtest.title": "Backtest",
    "backtest.strategy": "Strategy",
    "backtest.start": "Start date",
    "backtest.end": "End date",
    "backtest.capital": "Initial capital",
    "backtest.run": "Run backtest",
    "backtest.running": "Running…",
    "backtest.metrics": "Metrics",
    "backtest.equity_curve": "Equity curve",
    "backtest.trades": "Trades",

    "agent.title": "AI Agent",
    "agent.subtitle": "Agent calls backend tools. No fabricated prices, forecasts, or backtest metrics.",
    "agent.symbol_badge": "Symbol",
    "agent.clear": "Clear",
    "agent.new_chat": "New chat",
    "agent.history": "History",
    "agent.history_loading": "Loading history…",
    "agent.history_empty": "No conversations yet.",
    "agent.untitled": "Untitled conversation",
    "agent.delete_chat": "Delete this conversation",
    "agent.welcome_title": "Hello",
    "agent.welcome_body": "I can analyze technicals, compare forecast models, run backtests, or explain metrics. Data comes straight from the lakehouse.",
    "agent.welcome_warn": "Note: not investment advice. Academic demo.",
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
