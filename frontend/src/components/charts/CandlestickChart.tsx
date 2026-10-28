import { useMemo, useState } from "react";
import { OHLCVPoint } from "@/types/stock";
import { isUsableNumber, formatPrice, formatVolume, shortDate, tradingDay } from "@/utils/format";

interface CandleProps {
  points: OHLCVPoint[];
  height?: number;
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
 *   • render a vertical crosshair that snaps to the nearest bar
 *   • overlay an OHLCV tooltip card on hover
 *   • keep colors consistent with the up/down CSS variables
 */
/** A bar whose four prices are all finite numbers — safe to draw. */
type ValidBar = OHLCVPoint & { open: number; high: number; low: number; close: number };

export function CandlestickChart({ points, height = 320 }: CandleProps) {
  const [hover, setHover] = useState<HoverInfo | null>(null);

  // Drop bars whose prices aren't finite, and de-duplicate by symbol+timestamp,
  // before they reach the scale math.
  //
  // WHY: `Math.max`/`Math.min` propagate NaN, so one bad bar makes max, min and
  // span all NaN. The old `span = max - min || 1` guard then quietly turned the
  // corrupted span into 1, every `y(...)` became NaN, and the SVG rendered
  // `y="NaN"` — the whole chart vanished with no error and no empty state.
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

  const layout = useMemo(() => {
    if (!bars.length) return null;
    const width = Math.max(640, bars.length * 8);
    const highs = bars.map((p) => p.high);
    const lows = bars.map((p) => p.low);
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    // Finite and strictly positive by construction now that bars are filtered,
    // so a flat series still yields a usable span instead of NaN.
    const span = max > min ? max - min : 1;
    const pad = 24;
    const chartH = height - pad * 2;
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
  }, [bars, height]);

  const dropped = points.length - bars.length;

  if (!layout) {
    return (
      <div className="h-40 text-sm text-muted-foreground">
        {points.length
          ? `Không có nến nào hợp lệ (${points.length} dòng dữ liệu lỗi).`
          : "No chart data."}
      </div>
    );
  }

  const { width, candleW, y, gridYs, gridPrices, slot } = layout;

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
    <div className="relative w-full overflow-x-auto">
      <svg
        width={width}
        height={height}
        className="min-w-full select-none"
        onMouseMove={handleMove}
        onMouseLeave={handleLeave}
        role="img"
        aria-label="Candlestick chart"
      >
        {/* Grid */}
        {gridYs.map((yPos, i) => (
          <g key={i}>
            <line
              x1={40}
              x2={width}
              y1={yPos}
              y2={yPos}
              stroke="hsl(var(--border))"
              strokeDasharray="3 3"
            />
            <text
              x={4}
              y={yPos + 4}
              fontSize={10}
              fill="hsl(var(--muted-foreground))"
              fontFamily="JetBrains Mono"
            >
              {gridPrices[i].toFixed(0)}
            </text>
          </g>
        ))}

        {/* Candles */}
        {bars.map((point, index) => {
          const x = 40 + (index + 0.5) * slot;
          const up = point.close >= point.open;
          const color = up ? "hsl(var(--up))" : "hsl(var(--down))";
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
              />
            </g>
          );
        })}

        {/* Crosshair (only when hovering) */}
        {hover ? (
          <g pointerEvents="none">
            <line
              x1={hover.x}
              y1={24}
              x2={hover.x}
              y2={height - 24}
              stroke="hsl(var(--primary))"
              strokeWidth={1}
              strokeDasharray="2 3"
              opacity={0.7}
            />
            <line
              x1={40}
              y1={hover.y}
              x2={width}
              y2={hover.y}
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
          className="pointer-events-none absolute top-2 z-10 rounded-md border border-border bg-card px-3 py-2 text-[11px] shadow-md"
          style={{
            left: tooltipSide === "right" ? hover.x + 12 : hover.x - 200,
            minWidth: 180,
          }}
        >
          <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {shortDate(active.timestamp)}
          </div>
          <OHLCVRow label="O" value={active.open} />
          <OHLCVRow label="H" value={active.high} tone="up" />
          <OHLCVRow label="L" value={active.low} tone="down" />
          <OHLCVRow label="C" value={active.close} strong />
          <div className="mt-1 flex justify-between border-t border-border pt-1 font-mono text-muted-foreground">
            <span>Vol</span>
            <span>{formatVolume(active.volume)}</span>
          </div>
        </div>
      ) : null}

      {/* Surface the filtering rather than hiding it: a chart that silently
          drops bars looks complete while quietly mis-representing the series. */}
      {dropped > 0 ? (
        <p
          className="mt-1 text-right text-[10px] text-muted-foreground"
          title="Các dòng không có OHLC hợp lệ đã được bỏ qua khi vẽ biểu đồ."
        >
          ⚠ {dropped} dòng lỗi đã ẩn
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
}: {
  label: string;
  value: number | null;
  tone?: "up" | "down";
  strong?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 font-mono">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={
          tone === "up"
            ? "text-up"
            : tone === "down"
            ? "text-down"
            : strong
            ? "font-semibold text-foreground"
            : "text-foreground"
        }
      >
        {formatPrice(value)}
      </span>
    </div>
  );
}