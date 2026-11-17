import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  AreaChart,
} from "recharts";
import { OHLCVPoint } from "@/types/stock";
import { formatVolume, isUsableNumber, toFinite } from "@/utils/format";

/**
 * The Dashboard's two recharts-based charts.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `recharts` is by far the heaviest dependency in the app: 407 kB raw,
 * 110 kB gzipped - more than React, the router and the query client put
 * together. When the Dashboard imported it directly, the browser had to
 * download and parse all of it before the first paint, even though the
 * numbers in the metric row were already on screen.
 *
 * Moving the charts into their own module and importing it with
 * `React.lazy` turns the charting library into an ASYNC chunk:
 *   - the shell (nav bar, title, metric row) paints first,
 *   - the charts fill in a frame later with a skeleton in their place,
 *   - the library is downloaded once and cached by the browser.
 *
 * The candle chart below is NOT in this file on purpose: it is hand-drawn
 * SVG, so it costs no library and can paint immediately.
 */

// ── Chart palette ────────────────────────────────────────────────────────────
// Every colour comes from a CSS variable, so the palette is literally the
// seven roles from index.css. No gradient fills, no extra hues.
const BRAND = "hsl(var(--primary))";
const GRID = "hsl(var(--hairline))";
const AXIS = "hsl(var(--muted))";
const NEG = "hsl(var(--negative))";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
  fontFamily: '"IBM Plex Mono", monospace',
  padding: "8px 12px",
} as React.CSSProperties;

// ── Price area chart ─────────────────────────────────────────────────────────
export function PriceAreaChart({ data }: { data: Array<{ timestamp: string; price: number }> }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={AXIS}
          fontSize={12}
          fontFamily='"IBM Plex Mono", monospace'
          domain={["auto", "auto"]}
          width={64}
          tickFormatter={(v: number) => v.toFixed(0)}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: AXIS, fontSize: 12, marginBottom: 4 }}
          formatter={(v: number) => [v.toFixed(2), "Price"]}
          itemStyle={{ color: BRAND, fontWeight: 600 }}
        />
        {/* WHY NO GRADIENT FILL: a gradient under a line chart is the single
            most recognisable AI-generated chart style. A flat 8% tint of the
            same brand colour does the same job without the effect. */}
        <Area
          type="monotone"
          dataKey="price"
          stroke={BRAND}
          strokeWidth={1.5}
          fill={BRAND}
          fillOpacity={0.08}
          dot={false}
          activeDot={{ r: 3, fill: BRAND }}
          animationDuration={400}
          animationEasing="ease-out"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Volume bar chart ─────────────────────────────────────────────────────────
export function VolumeChart({ data }: { data: OHLCVPoint[] }) {
  // Coerce here rather than trusting the caller: `entry.close >= entry.open`
  // with either side null/undefined silently evaluates false and paints the
  // bar red, i.e. a data gap is displayed as a down-volume day.
  const bars = useMemo<Array<{ timestamp: string; volume: number; up: boolean }>>(
    () =>
      data.flatMap((d) => {
        const volume = toFinite(d.volume);
        if (volume === undefined) return [];
        const open = toFinite(d.open);
        const close = toFinite(d.close);
        return [
          {
            timestamp: d.timestamp,
            volume,
            up: isUsableNumber(open) && isUsableNumber(close) ? close >= open : true,
          },
        ];
      }),
    [data],
  );
  if (!bars.length) return null;
  return (
    <ResponsiveContainer>
      <BarChart data={bars} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={AXIS}
          fontSize={12}
          fontFamily='"IBM Plex Mono", monospace'
          tickFormatter={(v: number) =>
            v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`
          }
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: AXIS, fontSize: 12, marginBottom: 4 }}
          formatter={(v: number) => [formatVolume(v), "Volume"]}
          itemStyle={{ color: AXIS }}
        />
        {/* ONE bar series with one <Cell> per row.
            WHY: the previous code mapped the data to one `<Bar>` ELEMENT per
            row (`data.map(entry => <Bar .../>)`). In recharts a `<Bar>` is a
            *series*, not a bar: 2500 of them (the "Tất cả" range) means 2500
            series, each with its own scale/axis/animation state. The browser
            tab froze solid and never painted again. A single `<Bar>` plus
            per-row `<Cell>` elements is the supported way to colour bars
            individually, and it stays O(rows). */}
        <Bar dataKey="volume" maxBarSize={24} isAnimationActive={false}>
          {bars.map((entry, index) => (
            <Cell
              key={`vol-${entry.timestamp}-${index}`}
              fill={entry.up ? BRAND : NEG}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
