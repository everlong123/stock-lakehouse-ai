/**
 * True only for a real, finite number.
 *
 * WHY: the formatters below used `Number.isNaN`, which lets `Infinity` and
 * `-Infinity` through — `Infinity.toFixed(2)` renders the literal string
 * "Infinity", and `(Infinity * 100).toFixed(2)` renders "Infinity%". Those
 * values reach the UI when a backend query produces an unbounded ratio (a
 * percentage change against a zero or missing previous close) or when JSON
 * carries a non-finite value. Use this everywhere a number is about to be
 * displayed or used in arithmetic.
 */
export function isUsableNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Coerce an untyped API field to a finite number, or undefined if it isn't one.
 *
 * WHY this exists instead of `Number(value)`: the indicator endpoints return
 * loosely-typed rows, and `Number()` has two silent traps —
 * `Number("")` is `0` and `Number("N/A")` is `NaN`. Passing either straight
 * into a chart destroys the Y-axis: a spurious `0` Bollinger band or price
 * drags the whole scale to zero, and NaN makes the series vanish. Returning
 * `undefined` lets recharts render a gap for that point instead.
 */
export function toFinite(value: unknown): number | undefined {
  if (typeof value === "number") return Number.isFinite(value) ? value : undefined;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (!isUsableNumber(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (!isUsableNumber(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatPrice(value: number | null | undefined): string {
  if (!isUsableNumber(value)) return "—";
  return `${formatNumber(value, 2)} ₫`;
}

export function formatVolume(value: number | null | undefined): string {
  if (!isUsableNumber(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function shortDate(value: string): string {
  return value.replace("T", " ").slice(0, 16);
}

/**
 * The trading day a timestamp belongs to, as `YYYY-MM-DD`.
 *
 * WHY: the lakehouse stores one trading session under two possible
 * timestamps - the exchange open (13:30 UTC in EDT, 14:30 UTC in EST) and
 * the settled close (20:00 UTC) - and an intraday feed can add a hundred
 * more rows for the same session. All of them belong to ONE day, so the
 * charts key on this value to draw one candle per session.
 *
 * The date is read from the ISO string directly rather than via `Date`, so
 * the calendar day is taken exactly as the backend recorded it. A `Date`
 * would re-interpret the string in the browser's local timezone and shift
 * the day for any bar stamped late in the UTC day.
 */
export function tradingDay(timestamp: string): string {
  if (!timestamp) return "";
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(timestamp);
  return match ? match[1] : timestamp.slice(0, 10);
}

export function changeClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-muted-foreground";
  if (value > 0) return "text-up";
  if (value < 0) return "text-down";
  return "text-muted-foreground";
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "—";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s trước`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h trước`;
  return `${Math.floor(diff / 86400)}d trước`;
}

/**
 * Slice a chronologically-sorted OHLCV array by user-facing range.
 * The lakehouse stores daily bars only (interval = "1d"), so a 1-month
 * range ≈ 22 sessions, 1-year ≈ 252. "ALL" returns the input untouched.
 * Input is expected to be ascending by timestamp; the function preserves
 * that order.
 */
export type TimeRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

const RANGE_DAYS: Record<Exclude<TimeRange, "ALL">, number> = {
  "1M": 31,
  "3M": 92,
  "6M": 183,
  "1Y": 366,
};

export function applyTimeRange<T extends { timestamp: string }>(
  points: T[],
  range: TimeRange,
): T[] {
  if (!points.length || range === "ALL") return points;
  const days = RANGE_DAYS[range];
  // Take the last bar's timestamp as the anchor so the user sees a stable
  // "lookback" rather than shifting with wall-clock time.
  const anchor = Date.parse(points[points.length - 1].timestamp);
  if (Number.isNaN(anchor)) return points;
  const cutoff = anchor - days * 86400_000;
  return points.filter((p) => Date.parse(p.timestamp) >= cutoff);
}