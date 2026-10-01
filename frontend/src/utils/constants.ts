export const SYMBOLS = ["VCB", "TCB", "MBB", "FPT", "HPG", "VHM", "VNM", "MSN", "MWG", "VIC", "VRE", "SSI", "VND", "CTG", "BID", "ACB", "HDB", "TPB", "VPB", "GAS"] as const;
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

export const QUICK_PROMPTS = [
  { icon: "TA", label: "Phân tích kỹ thuật VCB", prompt: "Phân tích kỹ thuật VCB 3 tháng gần nhất" },
  { icon: "ML", label: "So sánh 3 model cho FPT", prompt: "So sánh Linear Regression, ARIMA, LSTM cho FPT" },
  { icon: "BT", label: "Backtest MA Crossover HPG", prompt: "Backtest chiến lược MA Crossover cho HPG năm 2025" },
  { icon: "FC", label: "Dự báo VHM bằng LSTM", prompt: "Dự báo giá VHM 5 ngày tới bằng LSTM" },
];