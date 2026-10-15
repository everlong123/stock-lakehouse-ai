export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${formatNumber(value, 2)} ₫`;
}

export function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function shortDate(value: string): string {
  return value.replace("T", " ").slice(0, 16);
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