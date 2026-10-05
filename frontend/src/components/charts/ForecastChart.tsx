import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ForecastPoint } from "@/types/forecasting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  fontSize: 12,
};

export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(220 10% 50%)" fontSize={11} />
          <YAxis domain={["auto", "auto"]} stroke="hsl(220 10% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="actual"
            stroke="hsl(220 22% 14%)"
            strokeWidth={2}
            dot={false}
            name="ACTUAL"
          />
          <Line
            type="monotone"
            dataKey="predicted"
            stroke="hsl(178 70% 24%)"
            strokeWidth={2}
            strokeDasharray="6 3"
            dot={{ r: 3, fill: "hsl(178 70% 24%)" }}
            name="PREDICTED"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}