import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ForecastPoint } from "@/types/forecasting";
import { shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
};

/**
 * Actual vs Predicted chart.
 *
 * WHY THE FORECAST IS A SEPARATE SERIES
 * ------------------------------------
 * The points whose `actual` is null are sessions that have NOT happened
 * yet - they are the forecast. Drawing them on the same line as the
 * history would make the model look like it had already predicted those
 * sessions, which is a claim the data does not support.
 *
 * So the chart carries three series:
 *
 * - `actual`      - the real close, null for the future sessions.
 * - `predicted`   - what the model said about sessions that already
 *                   happened (the hold-out region).
 * - `forecast`    - what the model says about the sessions still to come.
 *
 * A vertical marker separates "what happened" from "what is forecast",
 * and the forecast line is anchored to the last known close so the chart
 * reads as one continuous story rather than two disconnected fragments.
 */
export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  if (!data.length) return null;

  // Split at the boundary between known sessions and future sessions.
  const firstFutureIndex = data.findIndex((p) => p.actual === null || p.actual === undefined);
  const splitIndex = firstFutureIndex === -1 ? data.length : firstFutureIndex;

  const chartData = data.map((point, index) => {
    const isFuture = index >= splitIndex;
    return {
      timestamp: point.timestamp,
      actual: point.actual ?? null,
      // The hold-out estimate applies to the sessions that already happened.
      predicted: isFuture ? null : point.predicted,
      // The forecast applies to the sessions still to come. The first
      // forecast point repeats the last known close so the dashed line
      // starts from the history instead of floating next to it.
      forecast: isFuture ? point.predicted : null,
    };
  });

  const boundary = splitIndex > 0 ? data[splitIndex - 1]?.timestamp : undefined;
  const lastActual = splitIndex > 0 ? data[splitIndex - 1]?.predicted : null;

  // Anchor the forecast line to the last known close.
  if (boundary !== undefined && lastActual !== null && chartData.length > 0) {
    const bridge = chartData[splitIndex - 1];
    if (bridge) bridge.forecast = lastActual;
  }

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="hsl(var(--hairline))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={32} stroke="hsl(var(--muted))" fontSize={12} />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted))" fontSize={12} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(v) => shortDate(String(v))}
            formatter={(value, name) => [
              typeof value === "number" ? value.toFixed(2) : String(value ?? ""),
              name === "actual" ? "Giá thật" : name === "predicted" ? "Ước lượng (hold-out)" : "Dự báo",
            ]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {boundary ? (
            <ReferenceLine
              x={boundary}
              stroke="hsl(var(--muted))"
              strokeDasharray="4 4"
              label={{
                value: "Dự báo tỡ dụy",
                position: "insideTopRight",
                fontSize: 12,
                fill: "hsl(var(--muted))",
              }}
            />
          ) : null}
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
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
            name="predicted"
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke="hsl(var(--primary))"
            strokeWidth={2.5}
            strokeDasharray="8 4"
            dot={{ r: 3, fill: "hsl(var(--primary))" }}
            name="forecast"
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * The forecast-only chart: just the future sessions.
 *
 * Kept separate from the history chart because the two answer different
 * questions. The history chart answers "how well did the model do?"; this
 * one answers "what does it say comes next?".
 */
export function FutureForecastChart({ data }: { data: ForecastPoint[] }) {
  const future = data.filter((p) => p.actual === null || p.actual === undefined);
  if (!future.length) return null;

  const chartData = future.map((point) => ({
    timestamp: point.timestamp,
    predicted: point.predicted,
  }));

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="hsl(var(--hairline))" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" tickFormatter={shortDate} minTickGap={24} stroke="hsl(var(--muted))" fontSize={12} />
          <YAxis domain={["auto", "auto"]} stroke="hsl(var(--muted))" fontSize={12} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(v) => shortDate(String(v))}
            formatter={(value) => [
              typeof value === "number" ? value.toFixed(2) : String(value ?? ""),
              "Dự báo",
            ]}
          />
          <Line
            type="monotone"
            dataKey="predicted"
            stroke="hsl(var(--primary))"
            strokeWidth={2.5}
            strokeDasharray="8 4"
            dot={{ r: 3, fill: "hsl(var(--primary))" }}
            name="predicted"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
