import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { shortDate } from "@/utils/format";

interface IndicatorChartProps {
  data: Array<Record<string, string | number | null | undefined>>;
  lines: Array<{ key: string; color: string; name?: string }>;
  referenceLines?: Array<{ y: number; label: string; color: string }>;
  height?: number;
}

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 8,
  fontSize: 12,
  boxShadow: "var(--shadow-lg)",
};

export function IndicatorChart({ data, lines, referenceLines, height = 220 }: IndicatorChartProps) {
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data as Array<Record<string, string | number | null>>}>
          <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={32}
            stroke="hsl(var(--muted))"
            fontSize={12}
            tickLine={false}
          />
          <YAxis stroke="hsl(var(--muted))" fontSize={12} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          {referenceLines?.map((ref) => (
            <ReferenceLine
              key={ref.label}
              y={ref.y}
              stroke={ref.color}
              strokeDasharray="3 3"
              label={{ value: ref.label, fill: ref.color, fontSize: 12, position: "insideTopRight" }}
            />
          ))}
          {lines.map((line) => (
            <Line
              key={line.key}
              type="monotone"
              dataKey={line.key}
              stroke={line.color}
              strokeWidth={1.75}
              dot={false}
              name={line.name ?? line.key}
              isAnimationActive={data.length <= 200}
              animationDuration={600}
              animationEasing="ease-out"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
