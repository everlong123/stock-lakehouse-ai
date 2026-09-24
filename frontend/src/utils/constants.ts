export const SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META"] as const;
export const INTERVALS = ["1d", "1h", "15m", "5m"] as const;
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
