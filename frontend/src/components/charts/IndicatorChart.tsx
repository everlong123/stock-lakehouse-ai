import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { shortDate } from "@/utils/format";

export function IndicatorChart({
  data,
  lines,
}: {
  data: Record<string, string | number | null>[];
  lines: { key: string; color: string }[];
}) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <ComposedChart data={data}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={24} stroke="hsl(var(--muted-foreground))" />
          <YAxis stroke="hsl(var(--muted-foreground))" />
          <Tooltip labelFormatter={(v) => shortDate(String(v))} />
          {lines.map((line) =>
            line.key === "macd_hist" ? (
              <Bar key={line.key} dataKey={line.key} fill={line.color} />
            ) : (
              <Line key={line.key} type="monotone" dataKey={line.key} stroke={line.color} dot={false} />
            ),
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
