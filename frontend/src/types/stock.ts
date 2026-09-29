export interface OHLCVPoint {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close?: number;
  volume: number;
  source?: string;
}

export interface LatestQuote {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change_pct: number;
  source_layer?: string;
  interval?: string;
}
