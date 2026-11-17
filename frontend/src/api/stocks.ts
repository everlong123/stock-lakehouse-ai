import { api, ApiEnvelope } from "@/api/client";
import { LatestQuote, OHLCVPoint } from "@/types/stock";

export async function fetchStock(symbol: string, interval: string, start?: string) {
  const { data } = await api.get<
    ApiEnvelope<{ rows: OHLCVPoint[]; latest: LatestQuote; count: number; last_updated: string; data_source: string; currency: string }>
  >(`/stocks/${symbol}`, { params: { interval, ...(start ? { start } : {}) } });
  return data.data;
}

export async function fetchLatest(symbol: string) {
  const { data } = await api.get<ApiEnvelope<LatestQuote>>(`/stocks/${symbol}/latest`);
  return data.data;
}

export function csvUrl(symbol: string, interval: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return `${base}/stocks/${symbol}/csv?interval=${interval}`;
}

export async function fetchSymbols(): Promise<{ symbols: string[] }> {
  const { data } = await api.get<ApiEnvelope<{ symbols: string[] }>>("/stocks/symbols");
  return data.data;
}

/** One row of the market tape shown in the navigation bar. */
export interface TapeQuote {
  symbol: string;
  close: number;
  change_pct: number;
  currency: string;
  timestamp: string;
  source_layer?: string | null;
}

/**
 * Latest quote for several symbols in one request.
 *
 * WHY: the navigation tape renders a dozen tickers. Fetching them one by
 * one would saturate the browser's per-host connection pool and the strip
 * would paint in waves. One round trip keeps it to a single paint.
 */
export async function fetchTape(symbols: string[]): Promise<TapeQuote[]> {
  const { data } = await api.get<ApiEnvelope<{ quotes: TapeQuote[] }>>("/stocks/tape", {
    params: { symbols: symbols.join(",") },
  });
  return data.data.quotes;
}

/** One point of a rebased comparison series. */
export interface ComparePoint {
  timestamp: string;
  close: number;
  /** Price rebased to 100 at the first bar of the window. */
  rebased: number;
}

/** One ticker's normalised series over the comparison window. */
export interface CompareSeries {
  symbol: string;
  currency: string;
  base_close: number;
  base_timestamp: string;
  points: ComparePoint[];
  /** Total return over the window, in percent. */
  return_pct: number;
}

/**
 * Compare several symbols over one window, rebased to 100.
 *
 * WHY THE REBASE: raw closes cannot share an axis - AAPL sits near 340 and
 * FPT near 51,000, so plotting both raw would pin one line to the floor.
 * Rebasing to 100 at the window's first bar turns each series into "percent
 * change since the window opened", which is directly comparable.
 */
export async function fetchCompare(
  symbols: string[],
  days: number,
): Promise<{ series: CompareSeries[]; symbols: string[]; days: number; anchor: string | null }> {
  const { data } = await api.get<ApiEnvelope<{ series: CompareSeries[]; symbols: string[]; days: number; anchor: string | null }>>(
    "/stocks/compare",
    { params: { symbols: symbols.join(","), days } },
  );
  return data.data;
}

/** Descriptive statistics for one symbol over one window. */
export interface SymbolStats {
  symbol: string;
  currency: string;
  days: number;
  sessions: number;
  window_start: string;
  window_end: string;
  first_close: number;
  last_close: number;
  high: number;
  low: number;
  mean_close: number;
  total_return_pct: number;
  /** Annualised standard deviation of daily log returns, in percent. */
  volatility_pct: number | null;
  max_drawdown_pct: number;
  up_days: number;
  down_days: number;
  avg_volume: number | null;
  total_volume: number | null;
}

/**
 * Statistical profile of one symbol over one window.
 *
 * WHY THE BACKEND COMPUTES IT: volatility and maximum drawdown depend on
 * the exact window of stored closes, and the frontend does not hold the
 * full history in a form it can reduce without shipping 2500 rows first.
 * Computing it where the data already is keeps the response small and the
 * definition in one place.
 */
export async function fetchStats(symbol: string, days: number): Promise<SymbolStats> {
  const { data } = await api.get<ApiEnvelope<SymbolStats>>(`/stocks/stats/${symbol}`, {
    params: { days },
  });
  return data.data;
}
