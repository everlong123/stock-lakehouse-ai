/**
 * Shapes for stock/lakehouse API payloads.
 *
 * A note on nullability: every field here is declared nullable even where the
 * lakehouse usually has a value. That is deliberate. The Bronze→Silver→Gold
 * pipeline drops rows that fail validation, so a symbol fetched during a
 * partial failure really can come back with a null close or a null
 * `change_pct`. When these were declared as plain required `number`, the
 * compiler reported no problem and the NaN/null leaked all the way into the
 * charts, where `Math.max`/`Math.min` propagate it and silently blank the
 * whole series. Optional+nullable makes the call sites handle it explicitly,
 * and `isUsableNumber`/`toFinite` in `utils/format` are the sanctioned
 * narrowing helpers.
 */
export interface OHLCVPoint {
  symbol: string;
  timestamp: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adj_close?: number | null;
  volume: number | null;
  source?: string | null;
}

export interface LatestQuote {
  latest_session?: string | null;
  age_calendar_days?: number | null;
  data_status?: "stale" | "recent";
  symbol: string;
  timestamp: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  /** Absent when there is no previous bar to compare against. */
  change_pct?: number | null;
  source_layer?: string | null;
  interval?: string | null;
  /**
   * ISO code of the quote currency.
   *
   * WHY: prices in the lakehouse are unitless. VCB trades near 53,500 and
   * AAPL near 330, and both are a "close". Labelling every symbol as if it
   * traded in dong is simply wrong, so the unit comes from the symbol's
   * market. Absent means the backend did not say - render the bare number
   * rather than guessing.
   */
  currency?: string | null;
}

/** One row of the indicator series returned by `/stocks/{symbol}/indicators`. */
export interface IndicatorPoint {
  timestamp: string;
  [indicator: string]: string | number | null;
}

export interface IndicatorSummary {
  [key: string]: string | number | null;
}
