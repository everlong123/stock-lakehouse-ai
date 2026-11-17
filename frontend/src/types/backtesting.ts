export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  /** The NET result of the round trip, after both the entry and the exit fee. */
  pnl: number;
  return_pct: number;
  /** The total fees paid on this trade (entry + exit). The PnL is already net of them. */
  fees?: number | null;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  price: number;
}

/**
 * The buy-and-hold baseline measured on the SAME bars as the strategy,
 * with the same fees and the same next-bar execution. It is the null
 * hypothesis the strategy has to beat, so it is drawn on the same axis.
 */
export interface BacktestBenchmark {
  name: string;
  total_return: number | null;
  sharpe_ratio: number | null;
  maximum_drawdown: number | null;
  final_capital: number | null;
  equity_curve: EquityPoint[];
  drawdown: { timestamp: string; drawdown: number }[];
}

export interface BacktestResult {
  symbol: string;
  strategy: string;
  initial_capital: number;
  final_capital: number;
  total_return: number;
  win_rate: number;
  sharpe_ratio: number;
  maximum_drawdown: number;
  number_of_trades: number;
  profit_factor: number;
  equity_curve: EquityPoint[];
  drawdown: { timestamp: string; drawdown: number }[];
  trades: BacktestTrade[];
  markers: { timestamp: string; price: number; side: string }[];
  benchmark?: BacktestBenchmark | null;
  /** strategy total_return - benchmark total_return, on the same bars. */
  excess_return_vs_benchmark?: number | null;
  beat_benchmark?: boolean | null;
  disclaimer: string;
}

/**
 * One symbol's row in the multi-symbol walk-forward report.
 */
export interface MultiSymbolRow {
  symbol: string;
  exchange: string;
  total_windows: number | null;
  passed_windows: number | null;
  avg_train_return: number | null;
  avg_test_return: number | null;
  avg_test_sharpe: number | null;
  avg_test_max_drawdown: number | null;
  total_test_trades: number | null;
  return_consistency: number | null;
  overfitting_ratio: number | null;
  buy_hold_return: number | null;
  buy_hold_sharpe: number | null;
  buy_hold_max_drawdown: number | null;
  buy_hold_windows: number | null;
  paired_excess_return: number | null;
  paired_excess_median: number | null;
  beat_buy_hold: boolean | null;
}

export interface MultiSymbolReport {
  /** False when the report file has not been generated yet. */
  available?: boolean;
  /** Why the report is missing, when it is. */
  reason?: string;
  generated_at?: string;
  config?: {
    strategy: string;
    train_period_days: number;
    test_period_days: number;
    step_days: number;
    initial_capital: number;
    transaction_fee: number;
    slippage: number;
    symbols_tested: number;
    universe_size: number;
    sampling: string;
  };
  strategy_distribution?: {
    symbols_with_usable_windows: number;
    median_avg_test_return: number | null;
    mean_avg_test_return: number | null;
    median_avg_test_sharpe: number | null;
    mean_avg_test_sharpe: number | null;
    median_avg_test_max_drawdown: number | null;
    pct_symbols_profitable: number | null;
    median_return_consistency: number | null;
  };
  buy_and_hold_distribution?: {
    symbols_with_usable_windows: number;
    median_avg_return: number | null;
    mean_avg_return: number | null;
    median_sharpe: number | null;
    mean_sharpe: number | null;
    median_max_drawdown: number | null;
    pct_symbols_profitable: number | null;
  };
  head_to_head?: {
    paired_windows: number;
    pct_windows_beating_buy_hold: number | null;
    mean_paired_excess_return: number | null;
    median_paired_excess_return: number | null;
    symbols_compared: number;
    pct_symbols_beating_buy_hold: number | null;
    median_symbol_excess_return: number | null;
  };
  by_exchange?: Record<
    string,
    {
      symbols: number;
      strategy_median_return: number | null;
      strategy_median_sharpe: number | null;
      strategy_pct_profitable: number | null;
      buy_hold_median_return: number | null;
      buy_hold_median_sharpe: number | null;
      buy_hold_pct_profitable: number | null;
      median_paired_excess_return: number | null;
      pct_symbols_beating_buy_hold: number | null;
    }
  >;
  per_symbol?: MultiSymbolRow[];
  errors?: { symbol: string; error: string }[];
  elapsed_seconds?: number;
  note?: string;
}
