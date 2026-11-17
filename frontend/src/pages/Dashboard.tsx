import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
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
import { LakehouseWatchlist } from "@/components/dashboard/LakehouseWatchlist";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { NextSessionCard, type NextSessionForecast } from "@/components/dashboard/NextSessionCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { OHLCVPoint } from "@/types/stock";
import { applyTimeRange, formatNumber, formatPercent, formatPrice, formatVolume, isUsableNumber, rangeStartDate } from "@/utils/format";
import { resampleSolidBars, BAR_INTERVAL_LABELS, type BarInterval, type SolidBar } from "@/utils/resample";

/**
 * The two recharts-based charts are loaded asynchronously.
 *
 * WHY: `recharts` is 407 kB raw / 110 kB gzipped - heavier than React, the
 * router and the query client combined. Importing it directly meant the
 * browser could not paint the metric row until all of it had been
 * downloaded and parsed.
 *
 * With `React.lazy` the shell paints first and the charts fill in a frame
 * later, behind a skeleton. The library itself is downloaded once and
 * cached by the browser, so this costs nothing on the second visit.
 */
const PriceAreaChart = lazy(() =>
  import("@/components/charts/DashboardCharts").then((m) => ({ default: m.PriceAreaChart })),
);
const VolumeChart = lazy(() =>
  import("@/components/charts/DashboardCharts").then((m) => ({ default: m.VolumeChart })),
);

// ─────────────────────────────────────────────────────────────────────────────
export function DashboardPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const [range, setRange] = useState<TimeRange>("3M");
  // Granularity of the drawn bars. The lakehouse only stores daily bars, so
  // the weekly and monthly series are folded from the daily ones on the
  // client - see `utils/resample`.
  const [barInterval, setBarInterval] = useState<BarInterval>("1d");

  // The window, applied SERVER-SIDE.
  //
  // WHY: the stored history of a ten-year daily ticker is ~121 monthly
  // parquet partitions. Asking the backend for the last three months
  // lets it download three of them instead of all 121 - the page opens
  // in a fraction of the time, and the response shrinks with it.
  //
  // The anchor is the newest stored bar, which is not known before the
  // first request, so the first request measures the window from now
  // and the second - triggered by the anchor arriving - asks for the
  // exact window.
  const [anchorMs, setAnchorMs] = useState<number | null>(null);
  const startDate = useMemo(() => rangeStartDate(range, anchorMs), [range, anchorMs]);

  const query = useQuery({
    queryKey: ["dashboard", symbol, startDate ?? "all"],
    queryFn: () => fetchDashboard(symbol, startDate),
    retry: 1,
  });

  useEffect(() => {
    const candles = (query.data?.candles as { timestamp?: string }[] | undefined) ?? [];
    const last = candles[candles.length - 1];
    if (!last?.timestamp) return;
    const parsed = Date.parse(last.timestamp);
    if (!Number.isNaN(parsed)) setAnchorMs(parsed);
  }, [query.data?.candles]);

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
    <div className="space-y-12">
      {/* ── Page title ─────────────────────────────────────────── */}
      <PageTitle
        title={`${symbol} · ${t("dashboard.title", locale)}`}
        subtitle={`${t("dashboard.metrics", locale)} cho ${symbol}`}
        meta="01 · Dashboard"
      />

      {/*
        ── The metric row ───────────────────────────────────────────
        Five numbers in a row, divided by hairlines, no boxes. The row
        sits directly under the page title with a rule above the charts
        below it, so it reads as the header band of the dashboard rather
        than as five widgets that happen to be side by side.
      */}
      <section>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-3 xl:grid-cols-5">
          <MetricCard label={t("dashboard.price", locale)} value={formatPrice(lastClose, currency)} delta={changePct} />
          <MetricCard
            label={t("dashboard.change_pct", locale)}
            value={formatPercent(changePct)}
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

      {/*
        ── Two-column body ──────────────────────────────────────────
        The wide column holds the charts (the reason to open this page);
        the narrow column holds the reference material (watchlist, quote,
        activity). The chart column is wider because a chart squeezed into
        a third of the width is not readable.
      */}
      <div className="grid gap-12 xl:grid-cols-3">
        <div className="space-y-12 xl:col-span-2">

          {/* Price chart */}
          <section>
            <div className="section-head">
              <div>
                <h2 className="section-title">{t("dashboard.line_chart_title", locale)}</h2>
                <p className="section-sub">{t("dashboard.line_chart_sub", locale)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <BarIntervalSelector value={barInterval} onChange={setBarInterval} />
                <TimeRangeSelector value={range} onChange={setRange} />
                <span className="font-mono text-label uppercase text-muted">
                  {rangedCandles.length} bars · {BAR_INTERVAL_LABELS[barInterval]}
                </span>
              </div>
            </div>
            <div className="pt-4">
              <div className="h-72">
                {priceSeries.length ? (
                  <Suspense fallback={<Loading variant="skeleton" className="h-72" />}>
                    <PriceAreaChart data={priceSeries} />
                  </Suspense>
                ) : (
                  <EmptyState message="Không có dữ liệu giá." />
                )}
              </div>
            </div>
          </section>

          {/* Candlestick chart */}
          <section>
            <div className="section-head">
              <div>
                <h2 className="section-title">{t("dashboard.candle_title", locale)}</h2>
                <p className="section-sub">{t("dashboard.candle_sub", locale)}</p>
              </div>
            </div>
            <div className="pt-4">
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
          </section>

          {/* Volume chart */}
          <section>
            <div className="section-head">
              <div>
                <h2 className="section-title">{t("dashboard.volume_title", locale)}</h2>
                <p className="section-sub">{t("dashboard.volume_sub", locale)}</p>
              </div>
              <span className="font-mono text-label uppercase text-muted">
                {rangedCandles.length} bars · {BAR_INTERVAL_LABELS[barInterval]}
              </span>
            </div>
            <div className="h-48 pt-4">
              <Suspense fallback={<Loading variant="skeleton" className="h-48" />}>
                <VolumeChart data={rangedCandles} />
              </Suspense>
            </div>
          </section>

          {/* Lakehouse layer flow */}
          <LakehouseFlow
            bronzeCount={isUsableNumber(counts.bronze) ? counts.bronze : null}
            silverCount={isUsableNumber(counts.silver) ? counts.silver : null}
            goldCount={isUsableNumber(counts.gold) ? counts.gold : null}
          />
        </div>

        {/* Sidebar: reference column. Its own hairline separates it from
            the charts instead of a card around each block. */}
        <aside className="space-y-12 xl:border-l xl:border-hairline xl:pl-8">
          <MarketCard
            symbol={symbol}
            price={lastClose}
            source={String(data.data_source || "lakehouse")}
            updated={candles.at(-1)?.timestamp}
            currency={currency}
          />
          <NextSessionCard
            forecast={(data.next_session_forecast as NextSessionForecast | null) ?? null}
            currency={currency}
            modelCount={Array.isArray(data.published_forecasts) ? data.published_forecasts.length : 0}
            historicalMae={
              typeof data.forecast_model_mae === "number" ? data.forecast_model_mae : null
            }
            historicalDirectionalAccuracy={
              typeof data.forecast_model_directional_accuracy === "number"
                ? data.forecast_model_directional_accuracy
                : null
            }
          />
          <LakehouseWatchlist />
          <RecentActivity
            pipeline={data.pipeline as Record<string, unknown> | null}
            model={prediction}
            backtest={data.latest_backtest as Record<string, unknown> | null}
          />
        </aside>
      </div>
    </div>
  );
}
