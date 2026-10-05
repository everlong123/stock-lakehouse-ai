import { useMemo, useState } from "react";
import { OHLCVPoint } from "@/types/stock";
import { formatPrice, formatVolume, shortDate } from "@/utils/format";

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
export function CandlestickChart({ points, height = 320 }: CandleProps) {
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const layout = useMemo(() => {
    if (!points.length) return null;
    const width = Math.max(640, points.length * 8);
    const highs = points.map((p) => p.high);
    const lows = points.map((p) => p.low);
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    const span = max - min || 1;
    const pad = 24;
    const chartH = height - pad * 2;
    const candleW = Math.max(4, Math.min(12, width / points.length - 2));

    const y = (price: number) => pad + ((max - price) / span) * chartH;
    const gridLines = 5;
    const gridYs = Array.from(
      { length: gridLines },
      (_, i) => pad + ((chartH / (gridLines - 1)) * i),
    );
    const gridPrices = gridYs.map((yPos) => max - ((yPos - pad) / chartH) * span);
    const slot = (width - 50) / points.length;
    return { width, chartH, candleW, y, gridYs, gridPrices, slot };
  }, [points, height]);

  if (!layout) {
    return (
      <div className="h-40 text-sm text-muted-foreground">No chart data.</div>
    );
  }

  const { width, candleW, y, gridYs, gridPrices, slot } = layout;

  // Snap hover index to nearest bar.
  const handleMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    // viewBox-relative x: subtract left offset, account for 50px left axis gutter.
    const xRaw = ((event.clientX - rect.left) / rect.width) * width;
    const dataX = Math.max(0, xRaw - 40);
    const index = Math.min(
      points.length - 1,
      Math.max(0, Math.round(dataX / slot - 0.5)),
    );
    const point = points[index];
    if (!point) return;
    const cx = 40 + (index + 0.5) * slot;
    // Crosshair y is the candle mid (between high and low).
    const cy = (y(point.high) + y(point.low)) / 2;
    setHover({ index, x: cx, y: cy });
  };

  const handleLeave = () => setHover(null);

  const active = hover ? points[hover.index] : null;
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
        {points.map((point, index) => {
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
  value: number;
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