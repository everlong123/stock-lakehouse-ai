import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { shortDate } from "@/utils/format";

interface IndicatorChartProps {
  data: Array<Record<string, string | number | null | undefined>>;
  lines: Array<{ key: string; color: string; name?: string }>;
  referenceLines?: Array<{ y: number; label: string; color: string }>;
  height?: number;
}

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  fontSize: 12,
};

export function IndicatorChart({ data, lines, referenceLines, height = 220 }: IndicatorChartProps) {
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data as Array<Record<string, string | number | null>>}>
          <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(220 10% 50%)"
            fontSize={11}
          />
          <YAxis stroke="hsl(220 10% 50%)" fontSize={11} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          {referenceLines?.map((ref) => (
            <ReferenceLine
              key={ref.label}
              y={ref.y}
              stroke={ref.color}
              strokeDasharray="3 3"
              label={{ value: ref.label, fill: ref.color, fontSize: 11, position: "insideTopRight" }}
            />
          ))}
          {lines.map((line) => (
            <Line
              key={line.key}
              type="monotone"
              dataKey={line.key}
              stroke={line.color}
              strokeWidth={1.5}
              dot={false}
              name={line.name ?? line.key}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}