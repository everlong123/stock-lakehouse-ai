import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ForecastPoint } from "@/types/forecasting";
import { shortDate } from "@/utils/format";

export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={24} stroke="hsl(var(--muted-foreground))" />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted-foreground))" />
          <Tooltip labelFormatter={(v) => shortDate(String(v))} />
          <Legend />
          <Line type="monotone" dataKey="actual" stroke="hsl(var(--foreground))" dot={false} name="ACTUAL" />
          <Line type="monotone" dataKey="predicted" stroke="hsl(var(--primary))" dot={false} name="PREDICTED" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
