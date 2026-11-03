/**
 * Aggregate daily OHLCV bars into weekly / monthly bars.
 *
 * WHY THIS EXISTS
 * ---------------
 * The lakehouse stores DAILY bars only (`SUPPORTED_INTERVALS = ["1d"]` on the
 * backend, `INTERVALS = ["1d"]` in the frontend). The dashboard's range
 * selector therefore had exactly one granularity: pick a window, get N daily
 * candles. Picking "Tất cả" meant 2500 daily candles, which is unreadable on
 * a 10-year span and expensive to draw.
 *
 * Users of a broker dashboard expect the TIMEFRAME and the WINDOW to be two
 * independent controls: 1 week of daily bars, or 10 years of monthly bars.
 * This module produces the second axis by folding the daily bars we already
 * have - no extra API call, no extra storage, no new pipeline.
 *
 * HOW THE AGGREGATION WORKS
 * -------------------------
 * For a bucket (a week or a month) the OHLC values follow the standard
 * definition:
 *   open  = first bar's open
 *   high  = max of all highs
 *   low   = min of all lows
 *   close = last bar's close
 *   volume = sum of all volumes
 * The bucket's timestamp is the FIRST bar's timestamp in it, so the series
 * stays ascending and the x-axis reads left to right.
 *
 * A bucket that contains no usable bar is skipped entirely rather than being
 * emitted with null prices - a null close would blank the price chart.
 */

import { OHLCVPoint } from "@/types/stock";
import { isUsableNumber, toFinite } from "@/utils/format";

/** Granularity of a bar series. */
export type BarInterval = "1d" | "1w" | "1mo";

export const BAR_INTERVAL_LABELS: Record<BarInterval, string> = {
  "1d": "1D",
  "1w": "1W",
  "1mo": "1M",
};

/** A bar whose OHLC values are all finite - safe to draw. */
export type SolidBar = OHLCVPoint & {
  open: number;
  high: number;
  low: number;
  close: number;
};

/**
 * The UTC day a timestamp belongs to, as `YYYY-MM-DD`.
 *
 * WHY UTC AND NOT LOCAL: the lakehouse stores timestamps in UTC, and the
 * "trading day" concept the backend already applies (see `tradingDay` in
 * utils/format) is defined in UTC. Using local time here would shift a bar
 * into the previous day for any user east of Greenwich in the evening, and
 * the bucket boundaries would no longer line up with the daily bars.
 */
function utcDayKey(timestamp: string): string {
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return "";
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * The Monday-anchored week a timestamp belongs to, as `YYYY-MM-DD`.
 *
 * ISO weeks start on Monday, which is also the first trading day of the week
 * for every exchange this project tracks (VN, US). Anchoring on Monday means
 * a weekly bar covers exactly one trading week.
 */
function weekKey(timestamp: string): string {
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return "";
  const d = new Date(ms);
  // getUTCDay() is 0 (Sunday) .. 6 (Saturday). Shift so Monday is 0.
  const offset = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - offset);
  return d.toISOString().slice(0, 10);
}

/** The month a timestamp belongs to, as `YYYY-MM`. */
function monthKey(timestamp: string): string {
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return "";
  return new Date(ms).toISOString().slice(0, 7);
}

function bucketKey(timestamp: string, interval: BarInterval): string {
  switch (interval) {
    case "1w":
      return weekKey(timestamp);
    case "1mo":
      return monthKey(timestamp);
    case "1d":
    default:
      return utcDayKey(timestamp);
  }
}

/**
 * Fold daily bars into weekly or monthly bars.
 *
 * The input is expected to be ascending by timestamp; the output preserves
 * that order. Bars with an unusable price are dropped from the aggregation
 * (they cannot contribute to open/high/low/close) but their volume is still
 * counted, because a day's traded volume is real even when its price feed
 * was broken.
 *
 * Returns the input unchanged for "1d" - no copy, no work.
 */
export function resampleBars(
  points: OHLCVPoint[],
  interval: BarInterval,
): OHLCVPoint[] {
  if (interval === "1d" || !points.length) return points;

  interface Bucket {
    symbol: string;
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    /** False once a usable price has been seen for this bucket. */
    priced: boolean;
  }

  const buckets = new Map<string, Bucket>();

  for (const p of points) {
    const key = bucketKey(p.timestamp, interval);
    if (!key) continue;

    const open = toFinite(p.open);
    const high = toFinite(p.high);
    const low = toFinite(p.low);
    const close = toFinite(p.close);
    const volume = toFinite(p.volume) ?? 0;

    const existing = buckets.get(key);
    if (!existing) {
      // First bar seen in this bucket. It sets the bucket's timestamp (the
      // series stays ascending) and, if its price is usable, also the open.
      buckets.set(key, {
        symbol: p.symbol,
        timestamp: p.timestamp,
        open: open ?? 0,
        high: high ?? open ?? 0,
        low: low ?? open ?? 0,
        close: close ?? open ?? 0,
        volume,
        priced: open !== undefined,
      });
      continue;
    }

    existing.volume += volume;
    if (open === undefined) continue; // no usable price - volume only

    if (!existing.priced) {
      // The bucket's first USABLE price wins the open.
      existing.priced = true;
      existing.open = open;
      existing.close = close ?? open;
      existing.high = high ?? open;
      existing.low = low ?? open;
      continue;
    }

    existing.high = Math.max(existing.high, high ?? existing.high);
    existing.low = Math.min(existing.low, low ?? existing.low);
    if (close !== undefined) existing.close = close;
  }

  const out: OHLCVPoint[] = [];
  for (const b of buckets.values()) {
    if (!b.priced) continue; // no usable price in this bucket - skip it
    out.push({
      symbol: b.symbol,
      timestamp: b.timestamp,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
      source: "resampled",
    });
  }

  out.sort((a, b) => (a.timestamp < b.timestamp ? -1 : a.timestamp > b.timestamp ? 1 : 0));
  return out;
}

/**
 * Fold daily bars into weekly / monthly bars, keeping only solid bars.
 *
 * Same aggregation as `resampleBars`, but the result is narrowed to bars
 * whose four prices are finite numbers, which is exactly what the charts
 * need. Bars that cannot be drawn are dropped rather than rendered as
 * gaps with nulls.
 */
export function resampleSolidBars(
  points: SolidBar[],
  interval: BarInterval,
): SolidBar[] {
  const folded = resampleBars(points, interval);
  return folded.filter(
    (b): b is SolidBar =>
      isUsableNumber(b.open) &&
      isUsableNumber(b.high) &&
      isUsableNumber(b.low) &&
      isUsableNumber(b.close),
  );
}
