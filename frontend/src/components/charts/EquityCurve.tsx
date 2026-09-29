import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EquityPoint } from "@/types/backtesting";
import { shortDate } from "@/utils/format";

export function EquityCurve({ data }: { data: EquityPoint[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={data}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={24} stroke="hsl(var(--muted-foreground))" />
          <YAxis stroke="hsl(var(--muted-foreground))" />
          <Tooltip labelFormatter={(v) => shortDate(String(v))} />
          <Area type="monotone" dataKey="equity" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.15)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
