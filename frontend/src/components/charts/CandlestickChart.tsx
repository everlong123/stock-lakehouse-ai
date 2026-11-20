import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { OHLCVPoint } from "@/types/stock";
import { isUsableNumber, formatPrice, formatVolume, tradingDay } from "@/utils/format";
import { barPeriodLabel, type BarInterval } from "@/utils/resample";
import { useI18n } from "@/lib/i18n";

interface CandleProps {
  points: OHLCVPoint[];
  height?: number;
  barInterval?: BarInterval;
  /**
   * ISO currency of the quoted prices.
   *
   * WHY: the lakehouse stores unitless prices, and the tooltip labels them.
   * Without this the chart would say "245.30 $" for a US dollar stock.
   */
  currency?: string | null;
}

interface HoverInfo {
  index: number;
  x: number;
  y: number;
}

/**
 * Interactive candlestick chart with crosshair + OHLCV tooltip.
 *
 * Built as raw SVG (instead of recharts) so we can:
 *   - render a vertical crosshair that snaps to the nearest bar
 *   - overlay an OHLCV tooltip card on hover
 *   - keep colors consistent with the up/down CSS variables
 */
/** A bar whose four prices are all finite numbers - safe to draw. */
type ValidBar = OHLCVPoint & { open: number; high: number; low: number; close: number };

export function CandlestickChart({ points, height = 320, currency, barInterval = "1d" }: CandleProps) {
  const { locale } = useI18n();
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(640);

  // A position from the old series must never label a new candle after a
  // range or aggregation change.
  useEffect(() => setHover(null), [points]);

  // Drop bars whose prices aren't finite, and de-duplicate by symbol+timestamp,
  // before they reach the scale math.
  //
  // WHY: `Math.max`/`Math.min` propagate NaN, so one bad bar makes max, min and
  // span all NaN. The old `span = max - min || 1` guard then quietly turned the
  // corrupted span into 1, every `y(...)` became NaN, and the SVG rendered
  // `y="NaN"` - the whole chart vanished with no error and no empty state.
  // Filtering here also stops a bad bar from being mis-coloured: `NaN >= NaN`
  // is false, so a corrupt bar used to paint as a legitimate "down" day.
  //
  // WHY the second key (the trading DAY): a session can be stored twice under
  // two timestamps - the exchange open (13:30 UTC) and the settled close
  // (20:00 UTC) - and an intraday burst can add a hundred more rows for the
  // same day. Keying on the full timestamp lets all of them through, so the
  // chart draws several candles for one session. The backend now emits one
  // bar per trading day; this second key keeps the chart correct even if a
  // stale row is still in flight. Both keys are kept, because the same
  // instant can legitimately carry a re-stamped copy.
  const bars = useMemo<ValidBar[]>(() => {
    const seen = new Set<string>();
    const seenDays = new Set<string>();
    const valid: ValidBar[] = [];
    for (const p of points) {
      const key = `${p.symbol}|${p.timestamp}`;
      if (seen.has(key)) continue;
      seen.add(key);
      if (
        isUsableNumber(p.open) &&
        isUsableNumber(p.high) &&
        isUsableNumber(p.low) &&
        isUsableNumber(p.close)
      ) {
        const dayKey = `${p.symbol}|${tradingDay(p.timestamp)}`;
        if (seenDays.has(dayKey)) continue;
        seenDays.add(dayKey);
        valid.push({ ...p, open: p.open, high: p.high, low: p.low, close: p.close });
      }
    }
    return valid;
  }, [points]);

  const hasBars = bars.length > 0;
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const measure = () => setContainerWidth(Math.floor(container.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [hasBars]);

  const layout = useMemo(() => {
    if (!bars.length) return null;
    // Match the visible container for short series and scroll long series.
    // CSS min-width alone enlarges the SVG canvas without moving its shapes.
    const width = Math.max(320, containerWidth, bars.length * 8 + 50);
    const highs = bars.map((p) => p.high);
    const lows = bars.map((p) => p.low);
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    // Finite and strictly positive by construction now that bars are filtered,
    // so a flat series still yields a usable span instead of NaN.
    const span = max > min ? max - min : 1;
    const pad = 24;
    const chartH = height - pad - 42;
    const candleW = Math.max(4, Math.min(12, width / bars.length - 2));

    const y = (price: number) => pad + ((max - price) / span) * chartH;
    const gridLines = 5;
    const gridYs = Array.from(
      { length: gridLines },
      (_, i) => pad + ((chartH / (gridLines - 1)) * i),
    );
    const gridPrices = gridYs.map((yPos) => max - ((yPos - pad) / chartH) * span);
    const slot = (width - 50) / bars.length;
    return { width, chartH, candleW, y, gridYs, gridPrices, slot };
  }, [bars, height, containerWidth]);

  const dropped = points.length - bars.length;

  if (!layout) {
    return (
      <div className="h-40 text-small text-muted">
        {points.length
          ? (locale === "vi" ? `Không có nến hợp lệ (${points.length} dòng dữ liệu lỗi).` : `No valid candles (${points.length} invalid rows).`)
          : (locale === "vi" ? "Không có dữ liệu biểu đồ." : "No chart data.")}
      </div>
    );
  }

  const { width, candleW, y, gridYs, gridPrices, slot } = layout;
  const tickStep = Math.max(1, Math.ceil(110 / slot));

  // Snap hover index to nearest bar.
  const handleMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    // domX is the actual cursor position in the SVG's DOM pixel space.
    // Since the SVG has no viewBox attribute, the SVG-local coordinate
    // system matches DOM pixels (modulo CSS scaling). Storing domX (not
    // xRaw) keeps the crosshair + tooltip aligned with the cursor.
    const domX = event.clientX - rect.left;
    // Subtract the 40px left axis gutter so dataX = 0 sits at candle 0's
    // left edge, then snap to the nearest candle centre.
    const dataX = domX - 40;
    const index = Math.min(
      bars.length - 1,
      Math.max(0, Math.round(dataX / slot - 0.5)),
    );
    const point = bars[index];
    if (!point) return;
    // Crosshair x uses the literal DOM cursor position. With no viewBox
    // this is the same coordinate used when drawing the SVG <line>, so the
    // line stays visually under the pointer.
    const cx = domX;
    // Crosshair y is the candle mid (between high and low).
    const cy = (y(point.high) + y(point.low)) / 2;
    setHover({ index, x: cx, y: cy });
  };

  const handleLeave = () => setHover(null);

  const active = hover ? bars[hover.index] : null;
  const tooltipSide: "right" | "left" =
    hover && hover.x > width * 0.6 ? "left" : "right";

  return (
    <div ref={containerRef} className="relative w-full overflow-x-auto">
      <svg
        width={width}
        height={height}
        className="select-none"
        onMouseMove={handleMove}
        onMouseLeave={handleLeave}
        role="img"
        aria-label={locale === "vi" ? "Biểu đồ nến" : "Candlestick chart"}
      >
        {/* Grid */}
        {gridYs.map((yPos, i) => (
          <g key={i}>
            <line
              x1={40}
              x2={width}
              y1={yPos}
              y2={yPos}
              stroke="hsl(var(--hairline))"
              strokeDasharray="3 3"
            />
            <text
              x={4}
              y={yPos + 4}
              fontSize={12}
              fill="hsl(var(--muted))"
              fontFamily='"IBM Plex Mono", monospace'
            >
              {gridPrices[i].toFixed(0)}
            </text>
          </g>
        ))}

        {/* Candles */}
        {bars.map((point, index) => {
          const x = 40 + (index + 0.5) * slot;
          const up = point.close >= point.open;
          // WHY THE UP-CANDLE IS GREEN AND NOT THE ACCENT NAVY: the accent
          // is the app's own voice (logo, active tab, primary button).
          // Painting half the candles with it made "up" and "this is the
          // app" the same colour. The direction pair is green/red, the
          // convention every finance reader already has in their fingers.
          const color = up ? "hsl(var(--up))" : "hsl(var(--negative))";
          const bodyTop = y(Math.max(point.open, point.close));
          const bodyBottom = y(Math.min(point.open, point.close));
          const bodyH = Math.max(1.5, bodyBottom - bodyTop);
          const isHover = hover?.index === index;
          return (
            <g key={`${point.timestamp}-${index}`}>
              <line
                x1={x}
                x2={x}
                y1={y(point.high)}
                y2={y(point.low)}
                stroke={color}
                strokeWidth={1}
              />
              <rect
                x={x - candleW / 2}
                y={bodyTop}
                width={candleW}
                height={bodyH}
                fill={color}
                rx={1}
                opacity={hover && !isHover ? 0.55 : 1}
                className="transition-opacity duration-150"
              />
            </g>
          );
        })}

        {/* Date labels describe sessions; timestamps never imply hourly bars. */}
        {bars.filter((_, index) => index % tickStep === 0).map((point, index) => (
          <text
            key={point.timestamp}
            x={40 + (index * tickStep + 0.5) * slot}
            y={height - 12}
            textAnchor="middle"
            fontSize={12}
            fill="hsl(var(--muted))"
            fontFamily='"IBM Plex Mono", monospace'
          >
            {tradingDay(point.timestamp)}
          </text>
        ))}

        {/* Crosshair (only when hovering) */}
        {hover ? (
          <g pointerEvents="none">
            <line
              x1={hover.x}
              y1={24}
              x2={hover.x}
              y2={height - 42}
              stroke="hsl(var(--primary))"
              strokeWidth={1}
              strokeDasharray="2 3"
              opacity={0.7}
            />
            <line
              x1={40}
              y2={hover.y}
              x2={width}
              y1={hover.y}
              stroke="hsl(var(--primary))"
              strokeWidth={1}
              strokeDasharray="2 3"
              opacity={0.5}
            />
          </g>
        ) : null}
      </svg>

      {/* OHLCV tooltip */}
      {active && hover ? (
        <div
          className="pointer-events-none absolute top-2 z-10 rounded border border-hairline bg-surface px-3 py-2 text-label shadow-lg"
          style={{
            left: tooltipSide === "right" ? hover.x + 12 : hover.x - 200,
            minWidth: 180,
          }}
        >
          <div className="mb-1 font-mono text-label uppercase tracking-wider text-muted">
            {barPeriodLabel(active.timestamp, barInterval, locale)}
          </div>
          <OHLCVRow label="O" value={active.open} currency={currency} />
          <OHLCVRow label="H" value={active.high} tone="up" currency={currency} />
          <OHLCVRow label="L" value={active.low} tone="down" currency={currency} />
          <OHLCVRow label="C" value={active.close} strong currency={currency} />
          <div className="mt-1 flex justify-between border-t border-hairline pt-1 font-mono text-muted">
            <span>Vol</span>
            <span>{formatVolume(active.volume)}</span>
          </div>
        </div>
      ) : null}

      {/* Surface the filtering rather than hiding it: a chart that silently
          drops bars looks complete while quietly mis-representing the series. */}
      {dropped > 0 ? (
        <p
          className="mt-1 text-right text-label text-muted"
          title={locale === "vi" ? "Các dòng trùng phiên hoặc không có OHLC hợp lệ được bỏ qua khi vẽ biểu đồ." : "Duplicate sessions and invalid OHLC rows are omitted."}
        >
          {locale === "vi" ? `Đã bỏ qua ${dropped} dòng trùng hoặc lỗi dữ liệu` : `Omitted ${dropped} duplicate or invalid rows`}
        </p>
      ) : null}
    </div>
  );
}

function OHLCVRow({
  label,
  value,
  tone,
  strong,
  currency,
}: {
  label: string;
  value: number | null;
  tone?: "up" | "down";
  strong?: boolean;
  currency?: string | null;
}) {
  return (
    <div className="flex items-center justify-between gap-3 font-mono">
      <span className="text-muted">{label}</span>
      <span
        className={
          tone === "up"
            ? "text-up"
            : tone === "down"
              ? "text-negative"
              : strong
                ? "font-semibold text-ink"
                : "text-ink"
        }
      >
        {formatPrice(value, currency)}
      </span>
    </div>
  );
}
