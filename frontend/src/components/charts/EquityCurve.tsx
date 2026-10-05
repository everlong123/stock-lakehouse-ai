import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EquityPoint } from "@/types/backtesting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  fontSize: 12,
};

export function EquityCurve({ data }: { data: EquityPoint[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={data}>
          <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(220 10% 50%)" fontSize={11} />
          <YAxis stroke="hsl(220 10% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="hsl(178 70% 24%)"
            strokeWidth={2}
            fill="hsl(178 70% 24%)"
            fillOpacity={0.08}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}