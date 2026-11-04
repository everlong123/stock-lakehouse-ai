import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
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
import { fetchDashboard, fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { BarIntervalSelector } from "@/components/common/BarIntervalSelector";
import { TimeRangeSelector, type TimeRange } from "@/components/common/TimeRangeSelector";
import { LakehouseFlow } from "@/components/dashboard/LakehouseFlow";
import { LiveWatchlist } from "@/components/dashboard/LiveWatchlist";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { OHLCVPoint } from "@/types/stock";
import { applyTimeRange, formatNumber, formatPercent, formatPrice, formatVolume, isUsableNumber, toFinite } from "@/utils/format";
import { resampleSolidBars, BAR_INTERVAL_LABELS, type BarInterval, type SolidBar } from "@/utils/resample";

const TEAL = "hsl(165 52% 28%)";
const TEAL_LIGHT = "hsl(165 45% 92%)";
const BORDER = "hsl(210 18% 90% / 0.6)";
const MUTED = "hsl(220 12% 45%)";
const GRID = "hsl(210 20% 92%)";

const cardStyle = (hover = false) => ({
  borderRadius: 16,
  border: `1px solid ${hover ? "hsl(210 18% 82%)" : "hsl(210 18% 90% / 0.6)"}`,
  background: "white",
  boxShadow: hover
    ? "0 4px 12px -2px hsl(0 0 0% / 0.07), 0 2px 6px -2px hsl(0 0 0% / 0.04)"
    : "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)",
  transition: "all 0.2s ease",
} as React.CSSProperties);

const tooltipStyle = {
  background: "white",
  border: `1px solid ${BORDER}`,
  borderRadius: 12,
  fontSize: 12,
  fontFamily: "JetBrains Mono, monospace",
  boxShadow: "0 4px 12px hsl(0 0 0% / 0.08)",
  padding: "8px 12px",
};

// ── Price area chart with gradient fill ───────────────────────────────────────
function PriceAreaChart({ data }: { data: Array<{ timestamp: string; price: number }> }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={TEAL} stopOpacity={0.15} />
            <stop offset="95%" stopColor={TEAL} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={MUTED}
          fontSize={11}
          fontFamily="JetBrains Mono, monospace"
          domain={["auto", "auto"]}
          width={55}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: MUTED, fontSize: 10, marginBottom: 4 }}
          formatter={(v: number) => [`$${v.toFixed(2)}`, "Price"]}
          itemStyle={{ color: TEAL, fontWeight: 600 }}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={TEAL}
          strokeWidth={2.5}
          fill="url(#priceGradient)"
          dot={false}
          activeDot={{ r: 5, fill: TEAL, stroke: "white" as never, strokeWidth: 2 }}
          animationDuration={600}
          animationEasing="ease-out"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Volume bar chart with up/down colors ──────────────────────────────────────
function VolumeChart({ data }: { data: OHLCVPoint[] }) {
  // Coerce here rather than trusting the caller: `entry.close >= entry.open`
  // with either side null/undefined silently evaluates false and paints the bar
  // red, i.e. a data gap is displayed as a down-volume day.
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
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={MUTED}
          fontSize={11}
          fontFamily="JetBrains Mono, monospace"
          tickFormatter={(v: number) =>
            v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`
          }
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: MUTED, fontSize: 10, marginBottom: 4 }}
          formatter={(v: number) => [formatVolume(v), "Volume"]}
          itemStyle={{ color: MUTED }}
        />
        {/* ONE bar series with one <Cell> per row.
            WHY: the previous code mapped the data to one `<Bar>` ELEMENT per
            row (`data.map(entry => <Bar .../>)`). In recharts a `<Bar>` is a
            *series*, not a bar: 2500 of them (the "Tất cả" range) means 2500
            series, each with its own scale/axis/animation state. The browser
            tab froze solid and never painted again. A single `<Bar>` plus
            per-row `<Cell>` elements is the supported way to colour bars
            individually, and it stays O(rows). */}
        <Bar dataKey="volume" radius={[3, 3, 0, 0]} maxBarSize={24} isAnimationActive={false}>
          {bars.map((entry, index) => (
            <Cell
              key={`vol-${entry.timestamp}-${index}`}
              fill={entry.up ? "hsl(152 58% 38%)" : "hsl(4 80% 52%)"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const [range, setRange] = useState<TimeRange>("3M");
  // Granularity of the drawn bars. The lakehouse only stores daily bars, so
  // the weekly and monthly series are folded from the daily ones on the
  // client - see `utils/resample`.
  const [barInterval, setBarInterval] = useState<BarInterval>("1d");

  const query = useQuery({
    queryKey: ["dashboard", symbol],
    queryFn: () => fetchDashboard(symbol),
    retry: 1,
  });

  const statusQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    retry: 1,
    refetchInterval: 15000,
  });

  // Sanitize the series once, up front.
  //
  // WHY: the old code did `candles.at(-1)?.close ?? current_price ?? 0` and
  // `candles.at(-2)?.close ?? lastClose`. `??` only covers null/undefined, so a
  // single NaN close propagated straight into `changePct` — and because the
  // guard was `prevClose ? ... : 0`, a truthy NaN passed it and produced
  // `changePct = NaN`, which rendered as the literal string "NaN%".
  //
  // WHY this is a useMemo placed BEFORE the early returns: hooks must run in
  // the same order on every render, so a `useMemo` below `if (query.isLoading)
  // return <Loading />` would change the hook count between the loading and
  // the loaded render and crash React.
  const candles = useMemo<SolidBar[]>(() => {
    const rows = (query.data?.candles as OHLCVPoint[]) || [];
    return rows
      .filter(
        (c): c is OHLCVPoint & { open: number; high: number; low: number; close: number } =>
          isUsableNumber(c.open) &&
          isUsableNumber(c.high) &&
          isUsableNumber(c.low) &&
          isUsableNumber(c.close),
      )
      .map((c) => ({ ...c, open: c.open, high: c.high, low: c.low, close: c.close }));
  }, [query.data]);

  // Memoise the range slice: `applyTimeRange` re-parses every timestamp with
  // `Date.parse`, which is 2500 parses for the "Tất cả" range. Without this,
  // each range switch (and each 15s system-status refetch re-render) repeated
  // that work on the main thread.
  const rangedDaily = useMemo(
    () => applyTimeRange(candles, range),
    [candles, range],
  );

  // Fold the daily bars into the requested granularity.
  //
  // WHY THIS ORDER MATTERS: the range slice is applied to the DAILY bars
  // first, so "all + monthly" folds the whole 10-year history into ~120
  // monthly bars, and "3 months + weekly" folds ~63 daily bars into ~9
  // weekly bars. Resampling first and slicing afterwards would give the
  // wrong answer: a month bucket that straddles the range boundary would
  // be counted in full even though only part of it is inside the window.
  const rangedCandles = useMemo(
    () => resampleSolidBars(rangedDaily, barInterval),
    [rangedDaily, barInterval],
  );

  const priceSeries = useMemo(
    () => rangedCandles.map((c) => ({ timestamp: c.timestamp, price: c.close })),
    [rangedCandles],
  );

  if (query.isLoading) return <Loading />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("dashboard.err_connect", locale))}
        onRetry={() => query.refetch()}
      />
    );

  const data = query.data;
  if (!data) return <EmptyState message={t("dashboard.empty_symbol", locale)} />;

  const prediction = data.latest_prediction as Record<string, unknown> | null;
  const counts = (statusQuery.data?.counts as Record<string, number>) || {};

  const lastClose = candles.at(-1)?.close ?? (isUsableNumber(data.current_price) ? data.current_price : null);
  const prevClose = candles.at(-2)?.close ?? lastClose;
  // The quote currency of this symbol. Prices in the lakehouse are unitless,
  // so the unit has to come from the backend rather than being assumed.
  const currency = (data.currency as string | undefined) ?? null;
  // Only a real, non-zero previous close yields a change figure. Returning
  // null (not 0) lets the metric card render "—" instead of a fake "0.00%",
  // which would read as "flat today" rather than "unknown".
  const changePct =
    isUsableNumber(lastClose) && isUsableNumber(prevClose) && prevClose !== 0
      ? (lastClose - prevClose) / prevClose
      : null;

  return (
    <div className="space-y-5">
      {/* ── Page title ─────────────────────────────────────────── */}
      <PageTitle
        title={`${symbol} · ${t("dashboard.title", locale)}`}
        subtitle={`${t("dashboard.metrics", locale)} cho ${symbol}`}
        meta="01 · Dashboard"
      />

      {/* ── Live watchlist: real-time prices from Kafka stream ── */}
      <section className="animate-fade-in-up" style={{ animationDelay: "0.05s" }}>
        <LiveWatchlist maxTiles={30} />
      </section>

      {/* ── Metrics row ───────────────────────────────────────── */}
      <section>
        <div className="mb-3 font-mono text-[10px] uppercase tracking-widest" style={{ color: MUTED }}>
          {t("dashboard.metrics", locale)}
        </div>
        <div
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
          style={{ animation: "fade-in-up 0.4s ease-out both" }}
        >
          <MetricCard label={t("dashboard.price", locale)} value={formatPrice(lastClose, currency)} delta={changePct} />
          <MetricCard
            label={t("dashboard.change_pct", locale)}
            value={formatPercent(changePct)}
            delta={changePct}
          />
          <MetricCard
            label={t("dashboard.volume", locale)}
            value={formatVolume((data.volume as number) ?? candles.at(-1)?.volume)}
            hint={t("dashboard.volume_hint", locale)}
          />
          <MetricCard
            label={t("dashboard.rsi", locale)}
            value={formatNumber(data.rsi as number)}
            hint={t("dashboard.rsi_hint", locale)}
          />
          <MetricCard
            label={t("dashboard.model", locale)}
            value={prediction ? String(prediction.model_name) : t("dashboard.model_no_train", locale)}
            hint={
              prediction
                ? `${t("dashboard.model_hint_trained", locale)} ${formatNumber(prediction.mae as number)}`
                : t("dashboard.model_hint_untrained", locale)
            }
          />
        </div>
      </section>

      {/* ── Main grid: charts + sidebar ────────────────────────── */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">

          {/* Lakehouse layer flow */}
          <div className="animate-fade-in-up stagger-1" style={cardStyle()}>
            {/* Only show a count once /system/status has actually answered.
                `?? 0` rendered "0" while the query was loading or after it
                failed, which is indistinguishable from a genuinely empty
                Bronze layer — an empty lakehouse looks like a broken one. */}
            <LakehouseFlow
              bronzeCount={isUsableNumber(counts.bronze) ? counts.bronze : null}
              silverCount={isUsableNumber(counts.silver) ? counts.silver : null}
              goldCount={isUsableNumber(counts.gold) ? counts.gold : null}
            />
          </div>

          {/* Price area chart */}
          <div className="animate-fade-in-up stagger-2" style={cardStyle()}>
            <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: BORDER }}>
              <div>
                <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
                  {t("dashboard.line_chart_title", locale)}
                </h3>
                <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
                  {t("dashboard.line_chart_sub", locale)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <BarIntervalSelector value={barInterval} onChange={setBarInterval} />
                <TimeRangeSelector value={range} onChange={setRange} />
                <span
                  className="rounded-full px-2 py-0.5 font-mono text-[10px] font-medium"
                  style={{ background: TEAL_LIGHT, color: TEAL }}
                >
                  {rangedCandles.length} bars · {BAR_INTERVAL_LABELS[barInterval]}
                </span>
              </div>
            </div>
            <div className="h-56 px-3 py-4">
              {priceSeries.length ? <PriceAreaChart data={priceSeries} /> : <EmptyState message="No price data" />}
            </div>
          </div>

          {/* Candlestick chart */}
          <div className="animate-fade-in-up stagger-3" style={cardStyle()}>
            <div className="border-b px-5 py-4" style={{ borderColor: BORDER }}>
              <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
                {t("dashboard.candle_title", locale)}
              </h3>
              <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
                {t("dashboard.candle_sub", locale)}
              </p>
            </div>
            <div className="px-2 py-4">
              {rangedCandles.length ? (
                /* The candle chart follows the selected range too, but is capped
                   at 180 sessions: the raw SVG draws one <g> per candle, and
                   the "Tất cả" range would mean 2500 of them. The cap keeps the
                   chart readable and the DOM small; the price/volume charts
                   above still show the full range. */
                <CandlestickChart points={rangedCandles.slice(-180)} height={300} />
              ) : (
                <EmptyState
                  message={t("dashboard.empty_candle", locale)}
                  hint="Kiểm tra Bronze layer hoặc bấm Train để ingest dữ liệu mới."
                />
              )}
            </div>
          </div>
        </div>

        {/* Sidebar: market info + activity */}
        <div className="space-y-4">
          <div className="animate-fade-in-up stagger-2" style={cardStyle()}>
            <MarketCard
              symbol={symbol}
              price={lastClose}
              source={String(data.data_source || "lakehouse")}
              updated={candles.at(-1)?.timestamp}
              currency={currency}
            />
          </div>
          <div className="animate-fade-in-up stagger-3" style={cardStyle()}>
            <RecentActivity
              pipeline={data.pipeline as Record<string, unknown> | null}
              model={prediction}
              backtest={data.latest_backtest as Record<string, unknown> | null}
            />
          </div>
        </div>
      </div>

      {/* ── Volume chart ───────────────────────────────────────── */}
      <div className="animate-fade-in-up stagger-4" style={cardStyle()}>
        <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: BORDER }}>
          <div>
            <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
              {t("dashboard.volume_title", locale)}
            </h3>
            <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
              {t("dashboard.volume_sub", locale)}
            </p>
          </div>
          <span
            className="rounded-full px-2 py-0.5 font-mono text-[10px] font-medium"
            style={{ background: TEAL_LIGHT, color: TEAL }}
          >
            {rangedCandles.length} bars · {BAR_INTERVAL_LABELS[barInterval]}
          </span>
        </div>
        <div className="h-44 px-3 py-4">
          <VolumeChart data={rangedCandles} />
        </div>
      </div>
    </div>
  );
}
