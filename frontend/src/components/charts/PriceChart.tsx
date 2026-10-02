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
  background: "white",
  border: "1px solid hsl(220 14% 88%)",
  borderRadius: 6,
  fontSize: 12,
};

export function PriceChart({ data }: PriceChartProps) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(220 10% 50%)"
            fontSize={11}
          />
          <YAxis domain={["auto", "auto"]} stroke="hsl(220 10% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Line
            type="monotone"
            dataKey="close"
            stroke="hsl(168 76% 32%)"
            strokeWidth={2}
            dot={false}
            name="Close"
          />
          <Line type="monotone" dataKey="sma_20" stroke="hsl(168 50% 45%)" strokeWidth={1.4} dot={false} name="SMA20" />
          <Line type="monotone" dataKey="sma_50" stroke="hsl(32 88% 44%)" strokeWidth={1.4} dot={false} name="SMA50" />
          <Line type="monotone" dataKey="ema_12" stroke="hsl(220 50% 45%)" strokeWidth={1.2} strokeDasharray="4 3" dot={false} name="EMA12" />
          <Line
            type="monotone"
            dataKey="bb_upper"
            stroke="hsl(220 10% 60%)"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Upper"
          />
          <Line
            type="monotone"
            dataKey="bb_lower"
            stroke="hsl(220 10% 60%)"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Lower"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}