import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ForecastPoint } from "@/types/forecasting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "white",
  border: "1px solid hsl(152 18% 88%)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
};

export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke="hsl(152 25% 92%)" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(158 15% 50%)" fontSize={11} />
          <YAxis domain={["auto", "auto"]} stroke="hsl(158 15% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="actual"
            stroke="hsl(158 25% 30%)"
            strokeWidth={2}
            dot={false}
            name="ACTUAL"
          />
          <Line
            type="monotone"
            dataKey="predicted"
            stroke="hsl(154 58% 42%)"
            strokeWidth={2.5}
            strokeDasharray="6 3"
            dot={{ r: 3, fill: "hsl(154 58% 42%)" }}
            name="PREDICTED"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}