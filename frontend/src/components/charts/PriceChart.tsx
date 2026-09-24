import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { shortDate } from "@/utils/format";

export function PriceChart({ data }: { data: { timestamp: string; close: number; sma_20?: number; sma_50?: number }[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <AreaChart data={data}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={24} stroke="hsl(var(--muted-foreground))" />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted-foreground))" />
          <Tooltip labelFormatter={(v) => shortDate(String(v))} />
          <Area type="monotone" dataKey="close" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.12)" />
          <Area type="monotone" dataKey="sma_20" stroke="#94a3b8" fill="transparent" />
          <Area type="monotone" dataKey="sma_50" stroke="#f59e0b" fill="transparent" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
