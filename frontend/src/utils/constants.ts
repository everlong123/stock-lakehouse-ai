export const SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
  "JNJ", "WMT", "UNH", "XOM", "CVX", "BAC", "KO", "PEP", "DIS", "NFLX",
] as const;
/**
 * The lakehouse ingests daily bars only (backend `SUPPORTED_INTERVALS = ["1d"]`).
 * Offering intraday chips would request partitions that were never written, so the
 * switcher is intentionally single-option until intraday ingestion exists.
 */
export const INTERVALS = ["1d"] as const;
export const MODELS = [
  { id: "linear_regression", label: "Linear Regression" },
  { id: "arima", label: "ARIMA" },
  { id: "lstm", label: "LSTM" },
] as const;
export const STRATEGIES = [
  { id: "ma_crossover", label: "MA Crossover" },
  { id: "rsi_strategy", label: "RSI Strategy" },
] as const;

export const DISCLAIMER =
  "Kết quả chỉ phục vụ nghiên cứu học thuật, không phải khuyến nghị đầu tư.";

export const QUICK_PROMPTS = [
  { icon: "TA", label: "Phân tích kỹ thuật AAPL", prompt: "Phân tích kỹ thuật AAPL 3 tháng gần nhất" },
  { icon: "ML", label: "So sánh 3 model cho NVDA", prompt: "So sánh Linear Regression, ARIMA, LSTM cho NVDA" },
  { icon: "BT", label: "Backtest MA Crossover TSLA", prompt: "Backtest chiến lược MA Crossover cho TSLA năm 2025" },
  { icon: "FC", label: "Dự báo MSFT bằng LSTM", prompt: "Dự báo giá MSFT 5 ngày tới bằng LSTM" },
];