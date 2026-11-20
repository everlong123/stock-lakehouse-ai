import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EquityPoint } from "@/types/backtesting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 8,
  fontSize: 12,
  boxShadow: "var(--shadow-lg)",
};

interface MergedPoint extends EquityPoint {
  benchmark_equity?: number | null;
}

/**
 * Merge the strategy's equity curve with the buy-and-hold baseline.
 *
 * Both series are simulated over the SAME bars, so their timestamps
 * line up. They are still merged by timestamp rather than by index:
 * an index merge would silently shift the baseline by one point if the
 * two series ever had a different number of rows, and the chart would
 * then show a comparison that is off by a day without any error.
 */
function mergeCurves(strategy: EquityPoint[], benchmark?: EquityPoint[] | null): MergedPoint[] {
  if (!benchmark || benchmark.length === 0) {
    return strategy;
  }
  const byTimestamp = new Map<string, number>();
  for (const point of benchmark) {
    byTimestamp.set(point.timestamp, point.equity);
  }
  return strategy.map((point) => ({
    ...point,
    benchmark_equity: byTimestamp.get(point.timestamp) ?? null,
  }));
}

export function EquityCurve({
  data,
  benchmark,
}: {
  data: EquityPoint[];
  benchmark?: EquityPoint[] | null;
}) {
  const merged = useMemo(() => mergeCurves(data, benchmark), [data, benchmark]);
  const hasBenchmark = merged.some((point) => point.benchmark_equity != null);

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        {/* ComposedChart, not AreaChart: Recharts' AreaChart ignores a
            nested <Line>, so the baseline would silently never be drawn
            and the legend would list a series that does not exist. */}
        <ComposedChart data={merged}>
          <defs>
            <linearGradient id="equityAreaFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.24} />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="hsl(var(--hairline))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(var(--muted))" fontSize={12} tickLine={false} />
          <YAxis stroke="hsl(var(--muted))" fontSize={12} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
          {hasBenchmark ? (
            <Legend
              formatter={(value) => (
                <span style={{ color: "hsl(var(--muted))", fontSize: 12 }}>
                  {value === "equity" ? "Chiến lược" : "Mua & giữ (baseline)"}
                </span>
              )}
            />
          ) : null}
          {hasBenchmark ? (
            <Line
              type="monotone"
              dataKey="benchmark_equity"
              name="benchmark"
              stroke="hsl(var(--muted))"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
          ) : null}
          <Area
            type="monotone"
            dataKey="equity"
            name="equity"
            stroke="hsl(var(--primary))"
            strokeWidth={2.25}
            fill="url(#equityAreaFill)"
            isAnimationActive={merged.length <= 200}
            animationDuration={700}
            animationEasing="ease-out"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
