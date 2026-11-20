import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { shortDate } from "@/utils/format";

interface PriceChartProps {
  data: Array<{
    timestamp: string;
    close: number;
    sma_20?: number;
    sma_50?: number;
    bb_upper?: number;
    bb_middle?: number;
    bb_lower?: number;
    ema_12?: number;
    ema_26?: number;
  }>;
}

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 8,
  fontSize: 12,
  boxShadow: "var(--shadow-lg)",
};

/**
 * Price with moving-average overlays and Bollinger bands.
 *
 * WHY ONE ACCENT AND THREE WEIGHTS OF INK: the chart's subject is the
 * price. The overlays are context. So the price gets the brand accent —
 * it is the only thing the reader is here to see — and the averages get
 * progressively quieter weights of ink and muted, with the Bollinger band
 * as a hairline. A rainbow of five hues would make the overlays compete
 * with the price they are supposed to explain.
 *
 * WHY THE TWO AVERAGES ARE NOT BOTH GREY: SMA20 and SMA50 sit one
 * `border-l` apart in the reader's mind (short vs long), and two
 * identical grey lines cannot be told apart at a glance. The short
 * average is ink (solid, 1.2px) and the long one is muted (dashed), so
 * the pair is separable without adding a third hue.
 *
 * WHY THE DRAW-IN ANIMATION IS SWITCHED OFF ON A LONG SERIES: recharts
 * animates by interpolating every point of every series on every frame.
 * On a 2 500-bar series that is six interpolations a frame over a chart
 * the reader cannot read anyway, and it keeps the main thread busy for
 * a second and a half. Below 200 bars the animation is cheap and it
 * tells the reader the chart just arrived; above it, the chart simply
 * appears.
 */
export function PriceChart({ data }: PriceChartProps) {
  const animate = data.length <= 200;
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(var(--muted))"
            fontSize={12}
            tickLine={false}
          />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted))" fontSize={12} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Line
            type="monotone"
            dataKey="close"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            name="Close"
            connectNulls
            isAnimationActive={animate}
            animationDuration={600}
            animationEasing="ease-out"
          />
          {/* connectNulls: SMA/EMA/Bollinger are undefined for the first N bars
              of a series (the lookback window isn't full yet). Without this,
              recharts breaks the line there, so the indicator appears to start
              mid-chart instead of fading in from the left edge. */}
          <Line type="monotone" dataKey="sma_20" stroke="hsl(var(--ink))" strokeWidth={1.3} dot={false} name="SMA20" connectNulls isAnimationActive={animate} animationDuration={600} />
          <Line type="monotone" dataKey="sma_50" stroke="hsl(var(--muted))" strokeWidth={1.3} strokeDasharray="5 4" dot={false} name="SMA50" connectNulls isAnimationActive={animate} animationDuration={600} />
          <Line type="monotone" dataKey="ema_12" stroke="hsl(var(--muted))" strokeWidth={1} strokeDasharray="4 3" dot={false} name="EMA12" connectNulls isAnimationActive={animate} animationDuration={600} />
          <Line
            type="monotone"
            dataKey="bb_upper"
            stroke="hsl(var(--hairline))"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Upper"
            connectNulls
            isAnimationActive={animate}
            animationDuration={600}
          />
          <Line
            type="monotone"
            dataKey="bb_lower"
            stroke="hsl(var(--hairline))"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Lower"
            connectNulls
            isAnimationActive={animate}
            animationDuration={600}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
