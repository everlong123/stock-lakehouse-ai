import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { VerifiedForecast } from "@/types/forecasting";
import { formatPrice, shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
};

/**
 * The verification chart: what was forecast, and what actually happened.
 *
 * WHY THIS CHART IS NOT THE FORECAST CHART
 * -----------------------------------------
 * The forecasting page draws the model's own opinion about sessions that
 * already happened - a backtest. This chart draws something stronger: the
 * prediction the system WROTE DOWN before the session, next to the close
 * that actually printed. Every point here is a claim the system made
 * about the future and then had to live with.
 *
 * WHY TWO PANELS AND NOT ONE
 * --------------------------
 * The prices and the errors live on different scales: a ticker that trades
 * near 50,000 would squash an error of 300 against its price line, and the
 * error - the thing the reader actually came for - would be invisible.
 * So the price comparison and the error are drawn separately, each on its
 * own axis. The reader sees how close the lines are, and then sees the
 * size of the misses.
 *
 * WHY THE COLOURS ARE INK AND PRIMARY, NOT GREEN AND RED
 * -------------------------------------------------------
 * The reader has to see two PRICES, not two verdicts. Green/red would
 * frame every miss as a failure and every hit as a triumph, which the
 * data does not support: a forecaster that is right about the direction
 * but wrong about the magnitude is not a "hit".
 *
 * The error bars are coloured by DIRECTION, not by size: a green bar means
 * the forecast pointed the same way as the market moved, a red one means
 * it pointed the wrong way. A big green bar is still a big miss - the
 * colour says "the direction was right", not "the forecast was good".
 */
export function VerifiedForecastChart({
  data,
  currency,
}: {
  data: VerifiedForecast[];
  currency?: string | null;
}) {
  if (!data.length) return null;

  const chartData = data.map((row) => ({
    timestamp: row.target_session,
    actual: row.actual_close,
    predicted: row.predicted_close,
    error: row.abs_error,
    // The direction verdict drives the bar colour, not the error size.
    directionCorrect: row.direction_correct,
  }));

  return (
    <div className="space-y-6">
      <div className="h-64 w-full">
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="hsl(var(--hairline))" strokeDasharray="3 3" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(v) => shortDate(String(v))}
              minTickGap={32}
              stroke="hsl(var(--muted))"
              fontSize={12}
            />
            <YAxis
              domain={["auto", "auto"]}
              stroke="hsl(var(--muted))"
              fontSize={12}
              width={64}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => shortDate(String(v))}
              formatter={(value, name) => [
                typeof value === "number" ? formatPrice(value, currency) : String(value ?? ""),
                name === "actual" ? "Giá thật" : "Giá dự báo",
              ]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="actual"
              stroke="hsl(var(--ink))"
              strokeWidth={2}
              dot={false}
              name="actual"
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="predicted"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={{ r: 2.5, fill: "hsl(var(--primary))" }}
              name="predicted"
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/*
        The error panel. Its own chart, its own axis, so a large error
        stays readable next to a large price.
      */}
      <div>
        <p className="mb-2 font-mono text-label uppercase text-muted">
          Sai số mỗi phiên · xanh = đúng hướng, đỏ = sai hướng
        </p>
        <div className="h-40 w-full">
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="hsl(var(--hairline))" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v) => shortDate(String(v))}
                minTickGap={32}
                stroke="hsl(var(--muted))"
                fontSize={12}
              />
              <YAxis
                stroke="hsl(var(--muted))"
                fontSize={12}
                width={64}
                tickFormatter={(v: number) => v.toFixed(0)}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(v) => shortDate(String(v))}
                formatter={(value) => [
                  typeof value === "number" ? formatPrice(value, currency) : String(value ?? ""),
                  "Sai số",
                ]}
              />
              <Bar dataKey="error" maxBarSize={24} isAnimationActive={false}>
                {chartData.map((row, index) => (
                  <Cell
                    key={`err-${row.timestamp}-${index}`}
                    fill={
                      row.directionCorrect === 1
                        ? "hsl(var(--primary))"
                        : row.directionCorrect === 0
                          ? "hsl(var(--negative))"
                          : "hsl(var(--muted))"
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
