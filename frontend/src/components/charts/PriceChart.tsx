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
  border: "1px solid hsl(152 18% 88%)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
};

export function PriceChart({ data }: PriceChartProps) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="closeFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(154 58% 50%)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="hsl(154 58% 50%)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="hsl(152 25% 92%)" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(158 15% 50%)"
            fontSize={11}
          />
          <YAxis domain={["auto", "auto"]} stroke="hsl(158 15% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Line
            type="monotone"
            dataKey="close"
            stroke="hsl(154 58% 38%)"
            strokeWidth={2.4}
            dot={false}
            name="Close"
            fill="url(#closeFill)"
          />
          <Line type="monotone" dataKey="sma_20" stroke="hsl(154 50% 55%)" strokeWidth={1.5} dot={false} name="SMA20" />
          <Line type="monotone" dataKey="sma_50" stroke="hsl(36 90% 50%)" strokeWidth={1.5} dot={false} name="SMA50" />
          <Line type="monotone" dataKey="ema_12" stroke="hsl(220 60% 55%)" strokeWidth={1.2} strokeDasharray="4 3" dot={false} name="EMA12" />
          <Line
            type="monotone"
            dataKey="bb_upper"
            stroke="hsl(220 30% 70%)"
            strokeWidth={1}
            strokeDasharray="2 4"
            dot={false}
            name="BB Upper"
          />
          <Line
            type="monotone"
            dataKey="bb_lower"
            stroke="hsl(220 30% 70%)"
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