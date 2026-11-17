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
  borderRadius: 6,
  fontSize: 12,
};

/**
 * Price with moving-average overlays and Bollinger bands.
 *
 * WHY FOUR GREY-ISH LINES AND NOT FOUR COLOURS: the chart's subject is the
 * price. The overlays are context. So the price gets the accent, the
 * averages get progressively quieter weights of ink and muted, and the
 * Bollinger band is a hairline. A rainbow of five hues would make the
 * overlays compete with the price they are supposed to explain.
 */
export function PriceChart({ data }: PriceChartProps) {
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
          />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted))" fontSize={12} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Line
            type="monotone"
            dataKey="close"
            stroke="hsl(var(--primary))"
            strokeWidth={1.5}
            dot={false}
            name="Close"
            connectNulls
          />
          {/* connectNulls: SMA/EMA/Bollinger are undefined for the first N bars
              of a series (the lookback window isn't full yet). Without this,
              recharts breaks the line there, so the indicator appears to start
              mid-chart instead of fading in from the left edge. */}
          <Line type="monotone" dataKey="sma_20" stroke="hsl(var(--ink))" strokeWidth={1.2} dot={false} name="SMA20" connectNulls />
          <Line type="monotone" dataKey="sma_50" stroke="hsl(var(--muted))" strokeWidth={1.2} dot={false} name="SMA50" connectNulls />
          <Line type="monotone" dataKey="ema_12" stroke="hsl(var(--muted))" strokeWidth={1} strokeDasharray="4 3" dot={false} name="EMA12" connectNulls />
          <Line
            type="monotone"
            dataKey="bb_upper"
            stroke="hsl(var(--hairline))"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Upper"
            connectNulls
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
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
