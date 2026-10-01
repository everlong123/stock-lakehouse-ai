import { OHLCVPoint } from "@/types/stock";

interface CandleProps {
  points: OHLCVPoint[];
  height?: number;
}

export function CandlestickChart({ points, height = 320 }: CandleProps) {
  if (!points.length) return <div className="h-40 text-sm text-muted-foreground">No chart data.</div>;
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

  // Build Y-axis grid lines
  const gridLines = 5;
  const gridYs = Array.from({ length: gridLines }, (_, i) => pad + ((chartH / (gridLines - 1)) * i));
  const gridPrices = gridYs.map((yPos) => max - ((yPos - pad) / chartH) * span);

  return (
    <div className="w-full overflow-x-auto">
      <svg width={width} height={height} className="min-w-full">
        {/* Grid lines */}
        {gridYs.map((yPos, i) => (
          <g key={i}>
            <line
              x1={40}
              x2={width}
              y1={yPos}
              y2={yPos}
              stroke="hsl(152 25% 92%)"
              strokeDasharray="3 3"
            />
            <text x={4} y={yPos + 4} fontSize={10} fill="hsl(158 15% 50%)" fontFamily="JetBrains Mono">
              {gridPrices[i].toFixed(0)}
            </text>
          </g>
        ))}

        {/* Candles */}
        {points.map((point, index) => {
          const x = 40 + (index + 0.5) * ((width - 50) / points.length);
          const up = point.close >= point.open;
          const color = up ? "hsl(154 60% 36%)" : "hsl(0 70% 50%)";
          const bodyTop = y(Math.max(point.open, point.close));
          const bodyBottom = y(Math.min(point.open, point.close));
          const bodyH = Math.max(1.5, bodyBottom - bodyTop);
          return (
            <g key={`${point.timestamp}-${index}`}>
              <line x1={x} x2={x} y1={y(point.high)} y2={y(point.low)} stroke={color} strokeWidth={1} />
              <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={bodyH} fill={color} rx={1} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}