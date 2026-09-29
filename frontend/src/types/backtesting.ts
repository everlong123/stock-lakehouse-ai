export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  return_pct: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  price: number;
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
  disclaimer: string;
}
