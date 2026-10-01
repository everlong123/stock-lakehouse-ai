import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { shortDate } from "@/utils/format";

interface IndicatorChartProps {
  data: Array<Record<string, string | number | null | undefined>>;
  lines: Array<{ key: string; color: string; name?: string }>;
  referenceLines?: Array<{ y: number; label: string; color: string }>;
  height?: number;
}

const tooltipStyle = {
  background: "white",
  border: "1px solid hsl(152 18% 88%)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
};

export function IndicatorChart({ data, lines, referenceLines, height = 220 }: IndicatorChartProps) {
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data as Array<Record<string, string | number | null>>}>
          <CartesianGrid stroke="hsl(152 25% 92%)" strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(158 15% 50%)"
            fontSize={11}
          />
          <YAxis stroke="hsl(158 15% 50%)" fontSize={11} />
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
              strokeWidth={1.6}
              dot={false}
              name={line.name ?? line.key}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}