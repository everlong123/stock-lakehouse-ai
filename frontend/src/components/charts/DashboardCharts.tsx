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
import { formatPrice, formatVolume, isUsableNumber, toFinite, tradingDay } from "@/utils/format";
import { barPeriodLabel, type BarInterval } from "@/utils/resample";
import { useI18n } from "@/lib/i18n";

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
// roles from index.css. No extra hues.
//
// NOTE THE SPLIT BETWEEN `BRAND` AND `DIR`: `BRAND` is the app's accent
// (a single series drawn in the accent colour), while `DIR` is the
// direction pair - green for a rising bar, red for a falling one. Keeping
// them apart is what stops a chart from looking like a wall of brand.
const BRAND = "hsl(var(--primary))";
const GRID = "hsl(var(--hairline))";
const AXIS = "hsl(var(--muted))";
const UP = "hsl(var(--up))";
const NEG = "hsl(var(--negative))";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 8,
  fontSize: 12,
  fontFamily: '"IBM Plex Mono", monospace',
  padding: "8px 12px",
  boxShadow: "var(--shadow-lg)",
} as React.CSSProperties;

// ── Price area chart ─────────────────────────────────────────────────────────
export function PriceAreaChart({ data, barInterval = "1d", currency }: {
  data: Array<{ timestamp: string; price: number }>;
  barInterval?: BarInterval;
  currency?: string | null;
}) {
  const { locale } = useI18n();
  if (!data.length) return null;
  // WHY THE ANIMATION IS CAPPED BY THE SERIES LENGTH: recharts
  // interpolates every point of the series on every frame of the
  // draw-in. On 2 500 bars that is 2 500 interpolations a frame for a
  // chart nobody can read point by point, and it keeps the main thread
  // busy for a second and a half. Below the cap the draw-in is cheap
  // and tells the reader the series just arrived; above it, the chart
  // simply appears.
  const animate = data.length <= 200;
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          {/*
            WHY A GRADIENT HERE AND ONLY HERE: the area under a price line
            is the one place in the app where a vertical ramp genuinely
            helps — it gives the region under the curve a depth that a
            flat tint cannot, and it points down the way the value does.
            It is the accent fading to nothing, so it introduces no new
            colour and stays inside the design system's rules.
          */}
          <linearGradient id="priceAreaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={BRAND} stopOpacity={0.22} />
            <stop offset="100%" stopColor={BRAND} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="timestamp" tickFormatter={tradingDay} minTickGap={32} stroke={AXIS} fontSize={12} tickLine={false} />
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
          labelFormatter={(v) => barPeriodLabel(String(v), barInterval, locale)}
          formatter={(v: number) => [formatPrice(v, currency), locale === "vi" ? "Giá đóng cửa" : "Close"]}
          itemStyle={{ color: BRAND, fontWeight: 600 }}
          cursor={{ stroke: AXIS, strokeWidth: 1, strokeDasharray: "3 3" }}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={BRAND}
          strokeWidth={2}
          fill="url(#priceAreaFill)"
          dot={false}
          activeDot={{ r: 4, fill: BRAND, stroke: "hsl(var(--surface))", strokeWidth: 2 }}
          isAnimationActive={animate}
          animationDuration={700}
          animationEasing="ease-out"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Volume bar chart ─────────────────────────────────────────────────────────
export function VolumeChart({ data, barInterval = "1d" }: { data: OHLCVPoint[]; barInterval?: BarInterval }) {
  const { locale } = useI18n();
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
        <XAxis dataKey="timestamp" tickFormatter={tradingDay} minTickGap={32} stroke={AXIS} fontSize={12} tickLine={false} />
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
          labelFormatter={(v) => barPeriodLabel(String(v), barInterval, locale)}
          formatter={(v: number) => [formatVolume(v), locale === "vi" ? "Khối lượng" : "Volume"]}
          itemStyle={{ color: AXIS }}
          cursor={{ fill: "hsl(var(--surface-2))" }}
        />
        {/* ONE bar series with one <Cell> per row.
            WHY: the previous code mapped the data to one `<Bar>` ELEMENT per
            row (`data.map(entry => <Bar .../>)`). In recharts a `<Bar>` is a
            *series*, not a bar: 2500 of them (the "Tất cả" range) means 2500
            series, each with its own scale/axis/animation state. The browser
            tab froze solid and never painted again. A single `<Bar>` plus
            per-row `<Cell>` elements is the supported way to colour bars
            individually, and it stays O(rows). */}
        <Bar dataKey="volume" maxBarSize={24} isAnimationActive={false} radius={[2, 2, 0, 0]}>
          {bars.map((entry, index) => (
            <Cell
              key={`vol-${entry.timestamp}-${index}`}
              fill={entry.up ? UP : NEG}
              fillOpacity={0.7}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
