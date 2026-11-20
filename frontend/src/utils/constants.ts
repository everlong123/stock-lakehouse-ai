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
  { id: "ma_crossover", label: "MA Crossover", hint: "Short MA cắt lên Long MA · mua" },
  { id: "rsi_strategy", label: "RSI Strategy", hint: "RSI vượt 30/70 · mua/bán" },
] as const;

/**
 * The tickers carried by the market tape and by the dashboard watchlist.
 *
 * WHY A FIXED LIST AND NOT "THE FIRST N SYMBOLS": the tape is a watchlist,
 * and a watchlist is a decision. Auto-picking from the lakehouse would make
 * the strip jump around whenever the ingest set changes, and the user would
 * lose the ability to recognise their ticker in the row. This list mixes
 * the US heavyweights with a few Vietnamese names, because the lakehouse
 * holds both markets and a strip that only shows one of them would make
 * the app look like it cannot read anything else.
 *
 * WHY IT LIVES HERE AND NOT IN THE COMPONENT: the tape in the top bar and
 * the watchlist panel on the dashboard are two views of one decision - "which
 * names am I actually looking at". If they carried different lists, the two
 * panels would disagree about what the user is tracking.
 */
export const WATCHLIST_SYMBOLS = [
  "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
  "FPT", "VCB", "VHM", "HPG", "MWG",
] as const;

export const DISCLAIMER =
  "Phân tích và dự báo mang tính tham khảo, không phải khuyến nghị đầu tư.";

export const QUICK_PROMPTS = [
  { icon: "TA", label: "Phân tích kỹ thuật AAPL", prompt: "Phân tích kỹ thuật AAPL 3 tháng gần nhất" },
  { icon: "ML", label: "So sánh 3 model cho NVDA", prompt: "So sánh Linear Regression, ARIMA, LSTM cho NVDA" },
  { icon: "BT", label: "Backtest MA Crossover TSLA", prompt: "Backtest chiến lược MA Crossover cho TSLA năm 2025" },
  { icon: "FC", label: "Dự báo MSFT bằng LSTM", prompt: "Dự báo giá MSFT 5 ngày tới bằng LSTM" },
];
