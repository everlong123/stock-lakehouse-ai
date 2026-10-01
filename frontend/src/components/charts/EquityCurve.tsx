import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EquityPoint } from "@/types/backtesting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "white",
  border: "1px solid hsl(152 18% 88%)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
};

export function EquityCurve({ data }: { data: EquityPoint[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(154 58% 45%)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="hsl(154 58% 45%)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="hsl(152 25% 92%)" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(158 15% 50%)" fontSize={11} />
          <YAxis stroke="hsl(158 15% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="hsl(154 58% 42%)"
            strokeWidth={2.4}
            fill="url(#equityFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}