import { OHLCVPoint } from "@/types/stock";

interface CandleProps {
  points: OHLCVPoint[];
  height?: number;
}

export function CandlestickChart({ points, height = 320 }: CandleProps) {
  if (!points.length) return <div className="h-40 text-sm text-muted-foreground">No chart data.</div>;
  const width = Math.max(640, points.length * 6);
  const highs = points.map((p) => p.high);
  const lows = points.map((p) => p.low);
  const max = Math.max(...highs);
  const min = Math.min(...lows);
  const span = max - min || 1;
  const pad = 16;
  const chartH = height - pad * 2;
  const candleW = Math.max(3, Math.min(8, width / points.length - 2));

  const y = (price: number) => pad + ((max - price) / span) * chartH;

  return (
    <div className="w-full overflow-x-auto">
      <svg width={width} height={height} className="min-w-full">
        {points.map((point, index) => {
          const x = (index + 0.5) * (width / points.length);
          const up = point.close >= point.open;
          const color = up ? "hsl(var(--up))" : "hsl(var(--down))";
          const bodyTop = y(Math.max(point.open, point.close));
          const bodyBottom = y(Math.min(point.open, point.close));
          const bodyH = Math.max(1, bodyBottom - bodyTop);
          return (
            <g key={`${point.timestamp}-${index}`}>
              <line x1={x} x2={x} y1={y(point.high)} y2={y(point.low)} stroke={color} strokeWidth={1} />
              <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={bodyH} fill={color} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
