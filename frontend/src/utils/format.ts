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

/**
 * A percentage that always carries its sign.
 *
 * WHY THIS EXISTS: `formatPercent(0.3179)` returns "31.79%", which reads
 * as a magnitude and hides the direction. A return is a signed quantity -
 * "+31.79%" and "-31.79%" are different facts - so a row whose whole
 * point is the direction needs the sign on the face of the number.
 *
 * WHY THE ZERO CASE IS UNSIGNED: "+0.00%" claims a move that did not
 * happen. "0.00%" is the honest rendering of a flat period.
 */
export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (!isUsableNumber(value)) return "—";
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

/**
 * Render a price with its currency.
 *
 * WHY the currency is an argument and not a global default: prices in this
 * lakehouse are unitless. VCB trades near 53,500 (VND) and AAPL near 330
 * (USD) - both are a "close". A formatter that hardcoded one symbol would
 * label every stock in the universe with the wrong unit, which is worse than
 * showing no unit at all.
 *
 * Passing an unknown or missing currency renders the bare number, because a
 * wrong unit is a wrong fact while a missing one is merely incomplete.
 */
export function formatPrice(value: number | null | undefined, currency?: string | null): string {
  if (!isUsableNumber(value)) return "—";
  const unit = currencySymbol(currency);
  const formatted = formatNumber(value, 2);
  if (!unit) return formatted;
  const code = currency?.trim().toUpperCase();
  if (["USD", "EUR", "GBP", "JPY", "HKD", "KRW", "CNY", "TWD"].includes(code ?? "")) {
    return `${unit}${formatted}`;
  }
  return `${formatted} ${unit}`;
}

/**
 * The quote currency of a symbol, derived from the symbol itself.
 *
 * WHY the frontend needs its own copy: some read endpoints return a bare
 * bar with no currency field, so a watchlist tile has to work the unit out
 * from the ticker. The backend resolves the same way (see
 * `app.core.constants.currency_for_symbol`), and the two agree because both
 * read the same suffix conventions.
 *
 * Resolution order:
 *   1. A crypto pair carries its quote in the ticker: "BTC-USD" -> "USD".
 *   2. A Yahoo exchange suffix names the currency: ".DE" -> "EUR".
 *   3. A Vietnamese ticker -> "VND".
 *   4. Everything else -> "USD".
 *
 * Step 3 needs a list because Vietnamese tickers carry no suffix on Yahoo.
 */
export function currencyForSymbol(symbol: string): string {
  const sym = (symbol || "").trim().toUpperCase();
  if (!sym) return "USD";

  if (sym.includes("-")) {
    const tail = sym.split("-").pop() ?? "";
    if (tail.length === 3 && /^[A-Z]{3}$/.test(tail)) return tail;
  }

  if (sym.includes(".")) {
    const suffix = sym.split(".").pop() ?? "";
    const bySuffix: Record<string, string> = {
      VN: "VND", T: "JPY", HK: "HKD", KS: "KRW", SS: "CNY", SZ: "CNY",
      TW: "TWD", DE: "EUR", AS: "EUR", PA: "EUR", BR: "EUR", MI: "EUR",
      MC: "EUR", LS: "EUR", VI: "EUR", HE: "EUR", IR: "EUR", SG: "EUR",
      L: "GBP", SW: "CHF", TO: "CAD", V: "CAD", AX: "AUD", NZ: "NZD",
      SI: "SGD", JO: "ZAR", NS: "INR", BO: "INR", SA: "SAR", ME: "SAR",
      TA: "ILS", ST: "SEK", OL: "NOK", CO: "DKK",
      WA: "AUD", AU: "AUD", SE: "SEK", IS: "EUR", IL: "ILS", MCX: "EUR",
    };
    const found = bySuffix[suffix];
    if (found) return found;
  }

  // These colliding bare tickers hold US series in the lakehouse.
  if (["FRT", "NET", "DBC"].includes(sym)) return "USD";

  // Vietnamese tickers: the lakehouse serves them from SSI iBoard, and Yahoo
  // has no ".VN" listing for them, so they carry no suffix to read.
  if (VN_TICKERS.has(sym)) return "VND";
  return "USD";
}

/**
 * Vietnamese tickers, mirroring `app.core.constants.VN_SYMBOLS`.
 *
 * WHY a duplicated list: the frontend cannot import from the backend
 * package, and the set only has to answer "is this a VN ticker", so it is
 * kept here explicitly rather than guessed from a pattern (there is no
 * pattern - "FPT" and "TNH" are as Vietnamese as "VCB").
 */
const VN_TICKERS = new Set([
  "VCB", "VHM", "VIC", "VNM", "MSN", "BID", "CTG", "HPG", "FPT", "MWG",
  "GAS", "SAB", "PLX", "VRE", "NVL", "POW", "HDB", "TCB", "MBB", "TPB",
  "SSI", "VCI", "HCM", "BCM", "VJC", "ACB", "SHB", "VPB", "EIB", "OCB",
  "LPB", "STB", "BMP", "DGC", "GMD", "PVT", "DPM", "DCM", "REE", "KDH",
  "NLG", "PC1", "PNJ", "FRT", "VGC", "CTR", "SBT", "HSG", "NKG", "GVR",
  "VCS", "TNH", "DHA", "DXG", "HNG", "PVD", "PVS", "PVC", "PGS", "PXS",
  "PVE", "PVB", "BFC", "DBC", "HAB", "TSC", "LIX", "NET", "VTO", "SGT",
  "VIB", "MSB", "CII", "DIG", "HDG", "HQC", "IDC", "KBC", "LDG", "PHR",
  "SZC",
]);

/**
 * The display glyph for an ISO currency code.
 *
 * WHY a map rather than `Intl`: `Intl.NumberFormat` renders VND as "₫" but
 * also renders amounts as "1,234.00" with locale-specific spacing and
 * grouping rules that differ from the rest of this file's formatters. A
 * single symbol keeps a price column visually aligned.
 */
export function currencySymbol(currency?: string | null): string {
  if (!currency) return "";
  const code = currency.trim().toUpperCase();
  const map: Record<string, string> = {
    VND: "₫",
    USD: "$",
    EUR: "€",
    GBP: "£",
    JPY: "¥",
    HKD: "HK$",
    KRW: "₩",
    CNY: "¥",
    TWD: "NT$",
    CHF: "CHF",
    CAD: "C$",
    AUD: "A$",
    NZD: "NZ$",
    SGD: "S$",
    ZAR: "R",
    INR: "₹",
    SAR: "﷼",
    ILS: "₪",
    SEK: "kr",
    NOK: "kr",
    DKK: "kr",
  };
  return map[code] ?? "";
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

/**
 * Colour for a signed change.
 *
 * WHY A RISE IS GREEN AND NOT THE ACCENT
 * --------------------------------------
 * The accent is the app's own voice: the logo, the active nav tab, the
 * primary button, the live dot. While the accent was emerald it was ALSO
 * the colour of a rising price, which put two different meanings on one
 * hue — on a candle chart a reader could not tell "this candle is up"
 * from "this is the brand".
 *
 * The accent is navy now, so the collision is gone, and the direction
 * pair can go back to the convention every finance reader already has in
 * their fingers: green for up, red for down.
 *
 * WHY RED STAYS THE SAME: "down" was already the `negative` role, and
 * it was never competing with the accent for attention.
 */
export function changeClass(value: number | null | undefined): string {
  if (!isUsableNumber(value)) return "text-muted";
  if (value > 0) return "text-up";
  if (value < 0) return "text-negative";
  return "text-muted";
}

/**
 * The chart-side counterpart of `changeClass`.
 *
 * WHY A SEPARATE FUNCTION: the CSS classes carry the text colour, but a
 * chart needs a raw colour value for `fill` and `stroke`. Handing a
 * class name to recharts would silently paint nothing, so the two
 * directions are also expressed as raw CSS variables.
 */
export function changeColor(value: number | null | undefined): string {
  if (!isUsableNumber(value) || value === 0) return "hsl(var(--muted))";
  return value > 0 ? "hsl(var(--up))" : "hsl(var(--negative))";
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

export { RANGE_DAYS };

/**
 * The window as a START DATE for the server.
 *
 * WHY THE WINDOW IS APPLIED SERVER-SIDE
 * -------------------------------------
 * The stored history of a ten-year daily ticker is ~121 monthly parquet
 * partitions. Asking the backend for "the last three months" lets it
 * download three of them instead of all 121, so the page opens in a
 * fraction of the time and the response shrinks with it.
 *
 * The anchor is the newest stored bar, which is not known before the
 * first request - so the first request measures the window from now and
 * the second, triggered by the anchor arriving, asks for the exact
 * window. Both requests return real stored rows.
 */
export function rangeStartDate(range: TimeRange, anchorMs?: number | null): string | undefined {
  if (range === "ALL") return undefined;
  const anchor = anchorMs ?? Date.now();
  const cutoff = new Date(anchor - RANGE_DAYS[range] * 86400_000);
  return cutoff.toISOString();
}

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
