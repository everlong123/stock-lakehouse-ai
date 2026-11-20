import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { fetchDashboard } from "@/api/agent";
import { fetchIndicators } from "@/api/indicators";
import { fetchPublishedForecasts } from "@/api/forecasting";
import { fetchStats } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { ChartTimeControls } from "@/components/common/ChartTimeControls";
import { ChartViewToggle, type ChartView } from "@/components/common/ChartViewToggle";
import { KeyStatistics, type KeyStat } from "@/components/common/KeyStatistics";
import { QuoteHeader } from "@/components/common/QuoteHeader";
import { SubTabs } from "@/components/common/SubTabs";
import type { TimeRange } from "@/components/common/TimeRangeSelector";
import { LakehouseWatchlist } from "@/components/dashboard/LakehouseWatchlist";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { NextSessionCard, type NextSessionForecast } from "@/components/dashboard/NextSessionCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { OHLCVPoint } from "@/types/stock";
import {
  applyTimeRange,
  formatNumber,
  formatSignedPercent,
  formatPrice,
  formatVolume,
  isUsableNumber,
  rangeStartDate,
  toFinite,
} from "@/utils/format";
import { resampleSolidBars, type BarInterval, type SolidBar } from "@/utils/resample";

/**
 * The overview price chart is loaded asynchronously.
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

/**
 * The candle view of the dashboard chart.
 *
 * WHY IT IS A SEPARATE LAZY COMPONENT: the candlestick chart is hand-drawn
 * SVG, so it costs no charting library at all — but it is only needed when
 * the reader switches to it, so it is loaded on demand like the others.
 */
const CandlestickPanel = lazy(() =>
  import("@/components/charts/CandlestickChart").then((m) => ({ default: m.CandlestickChart })),
);

const VolumePanel = lazy(() =>
  import("@/components/charts/DashboardCharts").then((m) => ({ default: m.VolumeChart })),
);

const PriceChartWithOverlays = lazy(() =>
  import("@/components/charts/PriceChart").then((m) => ({ default: m.PriceChart })),
);

const IndicatorChart = lazy(() =>
  import("@/components/charts/IndicatorChart").then((m) => ({ default: m.IndicatorChart })),
);

const PublishedForecastComparison = lazy(() =>
  import("@/components/forecasting/PublishedForecastComparison").then((m) => ({
    default: m.PublishedForecastComparison,
  })),
);

/** Which reading of the symbol the reader is looking at. */
type ViewId = "overview" | "analysis" | "forecast" | "activity";

// ─────────────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const [range, setRange] = useState<TimeRange>("3M");
  // Granularity of the drawn bars. The lakehouse only stores daily bars, so
  // the weekly and monthly series are folded from the daily ones on the
  // client - see `utils/resample`.
  const [barInterval, setBarInterval] = useState<BarInterval>("1d");
  // Line or candles. Both read the same bars; they answer different
  // questions, so the reader picks.
  const [view, setView] = useState<ChartView>("line");
  // The sub-tab. A quote page on a big finance site splits one symbol into
  // several readings; here the split is "what it did" / "what it looks
  // like" / "what is expected" / "what has actually run".
  const [tab, setTab] = useState<ViewId>("overview");

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

  /**
   * The year's statistics, for the key-statistics panel.
   *
   * WHY A SECOND REQUEST AND NOT THE CANDLE WINDOW: the 52-week high and
   * low cannot be read from a three-month window, and the window the
   * reader picked is a chart setting, not a fact about the instrument.
   * The backend computes the extremes where the data already is, so this
   * is one cheap request that never changes with the chart's range.
   */
  const statsQuery = useQuery({
    queryKey: ["stock-stats", symbol, 365],
    queryFn: () => fetchStats(symbol, 365),
    retry: 1,
    staleTime: 60_000,
  });

  useEffect(() => {
    const candles = (query.data?.candles as { timestamp?: string }[] | undefined) ?? [];
    const last = candles[candles.length - 1];
    if (!last?.timestamp) return;
    const parsed = Date.parse(last.timestamp);
    if (!Number.isNaN(parsed)) setAnchorMs(parsed);
  }, [query.data?.candles]);

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
  // `Date.parse`, which repeats for every stored session in the "Tất cả"
  // range. Cache that work until the source candles or range changes.
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

  const lastBar = candles.at(-1);
  const lastClose = lastBar?.close ?? (isUsableNumber(data.current_price) ? data.current_price : null);
  const prevClose = candles.at(-2)?.close ?? null;
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

  // The session's own low and high, for the range bar in the quote header.
  const sessionLow = lastBar?.low ?? null;
  const sessionHigh = lastBar?.high ?? null;

  // The year's extremes, for the key-statistics panel.
  const yearStats = statsQuery.data;

  // The key-statistics rows.
  //
  // WHY THESE ARE THE STATISTICS A READER ACTUALLY COMPARES: open against
  // the previous close (did it gap?), the close against the year's range
  // (is it near the top?), volume against the average (was the day heavy?).
  const keyStats: KeyStat[] = [
    {
      label: locale === "vi" ? "Mở cửa" : "Open",
      value: formatPrice(lastBar?.open ?? null, currency),
    },
    {
      label: locale === "vi" ? "Đóng cửa trước" : "Previous close",
      value: formatPrice(prevClose, currency),
    },
    {
      label: locale === "vi" ? "Cao nhất 52 tuần" : "52-week high",
      value: formatPrice(yearStats?.high ?? null, currency),
    },
    {
      label: locale === "vi" ? "Thấp nhất 52 tuần" : "52-week low",
      value: formatPrice(yearStats?.low ?? null, currency),
    },
    {
      label: locale === "vi" ? "Khối lượng" : "Volume",
      value: formatVolume(lastBar?.volume ?? null),
    },
    {
      label: locale === "vi" ? "KL bình quân 52 tuần" : "52-week avg volume",
      value: formatVolume(yearStats?.avg_volume ?? null),
    },
    {
      label: "RSI (14)",
      value: formatNumber(data.rsi as number),
    },
    {
      label: locale === "vi" ? "Lợi nhuận 52 tuần" : "52-week return",
      value: formatSignedPercent(yearStats ? yearStats.total_return_pct / 100 : null),
      tone: yearStats ? yearStats.total_return_pct / 100 : null,
    },
  ];

  // The sub-tabs. The counts come from the data, so a reader knows which
  // reading has something in it before clicking.
  const publishedCount = Array.isArray(data.published_forecasts)
    ? data.published_forecasts.length
    : 0;
  const tabs = [
    {
      id: "overview" as ViewId,
      label: locale === "vi" ? "Tổng quan" : "Overview",
      hint: `${rangedDaily.length.toLocaleString("en-US")} ${locale === "vi" ? "phiên" : "sessions"}`,
    },
    {
      id: "analysis" as ViewId,
      label: locale === "vi" ? "Phân tích" : "Analysis",
      hint: locale === "vi" ? "Chỉ báo" : "Indicators",
    },
    {
      id: "forecast" as ViewId,
      label: locale === "vi" ? "Dự báo" : "Forecast",
      hint:
        publishedCount > 0
          ? `${publishedCount} ${locale === "vi" ? "mô hình" : "models"}`
          : locale === "vi"
            ? "chưa có"
            : "none",
    },
    {
      id: "activity" as ViewId,
      label: locale === "vi" ? "Hoạt động" : "Activity",
      hint: locale === "vi" ? "Pipeline & mô hình" : "Pipeline & models",
    },
  ];

  return (
    <div className="space-y-6">
      {/*
        ── The quote header ───────────────────────────────────────────
        Everything a reader needs to know about this instrument before
        looking at a single chart: what it is, what it costs, how much it
        moved, and where it sits inside the session's range.
      */}
      <QuoteHeader
        symbol={symbol}
        currency={currency}
        bar={{
          open: lastBar?.open ?? null,
          high: sessionHigh,
          low: sessionLow,
          close: lastClose,
          prevClose,
          volume: lastBar?.volume ?? null,
        }}
        change={changePct}
        spark={rangedDaily.map((c) => c.close)}
        range={{ high: sessionHigh, low: sessionLow }}
        session={lastBar?.timestamp?.slice(0, 10) ?? null}
      />

      {/*
        ── The sub-tabs ───────────────────────────────────────────────
        The four readings of this symbol. One row, one underline for the
        active one, and the row is a hairline above the content so the
        switch reads as a change of view rather than a new page.
      */}
      <SubTabs tabs={tabs} active={tab} onChange={setTab} />

      {/*
        ── Two-column body ────────────────────────────────────────────
        The wide column holds the charts (the reason to open this page);
        the narrow column holds the reference material (statistics,
        forecast, watchlist). The chart column is wider because a chart
        squeezed into a third of the width is not readable.
      */}
      <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
        <div className="min-w-0 space-y-8">
          {tab === "overview" ? (
            <>
              {/* Price chart */}
              <section>
                <div className="section-head">
                  <div>
                    <h2 className="section-title">
                      {locale === "vi" ? "Diễn biến giá" : "Price history"}
                    </h2>
                    <p className="section-sub">
                      {locale === "vi"
                        ? "Đường liền là giá đóng cửa, đọc trực tiếp từ tầng Gold."
                        : "The line is the closing price, read straight from the Gold layer."}
                    </p>
                  </div>
                </div>
                <ChartTimeControls
                  barInterval={barInterval}
                  onBarIntervalChange={setBarInterval}
                  range={range}
                  onRangeChange={setRange}
                  dailyPoints={rangedDaily}
                  barCount={rangedCandles.length}
                >
                  <ChartViewToggle value={view} onChange={setView} />
                </ChartTimeControls>
                <div className="pt-4">
                  <div className="h-80">
                    {view === "line" ? (
                      priceSeries.length ? (
                        <Suspense fallback={<Loading variant="skeleton" className="h-80" />}>
                          <PriceAreaChart data={priceSeries} barInterval={barInterval} currency={currency} />
                        </Suspense>
                      ) : (
                        <EmptyState message={locale === "vi" ? "Không có dữ liệu giá." : "No price data."} />
                      )
                    ) : rangedCandles.length ? (
                      <Suspense fallback={<Loading variant="skeleton" className="h-80" />}>
                        <CandlestickPanel
                          points={rangedCandles}
                          currency={currency}
                          barInterval={barInterval}
                        />
                      </Suspense>
                    ) : (
                      <EmptyState message={locale === "vi" ? "Không có dữ liệu nến." : "No candle data."} />
                    )}
                  </div>
                </div>
              </section>

              {/* Volume, under the price chart — the same window, the same
                  grouping, so the two read as one figure. */}
              <section>
                <div className="section-head">
                  <div>
                    <h2 className="section-title">
                      {locale === "vi" ? "Khối lượng giao dịch" : "Volume"}
                    </h2>
                    <p className="section-sub">
                      {locale === "vi"
                        ? "Cùng cách gộp và khoảng xem của biểu đồ giá."
                        : "The same grouping and date range as the price chart."}
                    </p>
                  </div>
                </div>
                <div className="h-48 pt-4">
                  {rangedCandles.length ? (
                    <Suspense fallback={<Loading variant="skeleton" className="h-48" />}>
                      <VolumePanel data={rangedCandles} barInterval={barInterval} />
                    </Suspense>
                  ) : (
                    <EmptyState message={locale === "vi" ? "Không có khối lượng." : "No volume data."} />
                  )}
                </div>
              </section>
            </>
          ) : null}

          {/*
            ── The analysis reading ─────────────────────────────────────
            The technical page is a full page of its own, so this tab
            shows the same indicators in the compact form a quote page
            uses: the price with its moving averages, and the oscillator
            that describes it.
          */}
          {tab === "analysis" ? (
            <Suspense fallback={<Loading variant="skeleton" className="h-80" />}>
              <AnalysisPanel symbol={symbol} currency={currency} />
            </Suspense>
          ) : null}

          {/*
            ── The forecast reading ─────────────────────────────────────
            The published forecasts, read from the same `predictions`
            table the Forecast page reads, so the two cannot disagree.
          */}
          {tab === "forecast" ? (
            <Suspense fallback={<Loading variant="skeleton" className="h-32" />}>
              <ForecastPanel symbol={symbol} currency={currency} />
            </Suspense>
          ) : null}

          {tab === "activity" ? (
            <section>
              <div className="section-head">
                <div>
                  <h2 className="section-title">
                    {locale === "vi" ? "Chi tiết phân tích" : "Analysis details"}
                  </h2>
                  <p className="section-sub">
                    {locale === "vi"
                      ? "Những gì đã chạy trong pipeline gần nhất."
                      : "What the last pipeline run actually produced."}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6 border-b border-hairline py-5">
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
              </div>
              <RecentActivity
                pipeline={data.pipeline as Record<string, unknown> | null}
                model={prediction}
                backtest={data.latest_backtest as Record<string, unknown> | null}
              />
            </section>
          ) : null}
        </div>

        <aside className="min-w-0 space-y-8 xl:border-l xl:border-hairline xl:pl-8">
          {/* The statistics: read down a column, compared against each
              other — which is why they are rows and not cards. */}
          <KeyStatistics
            title={locale === "vi" ? "Chỉ số chính" : "Key statistics"}
            stats={keyStats}
          />

          <NextSessionCard
            forecast={(data.next_session_forecast as NextSessionForecast | null) ?? null}
            currency={currency}
            modelCount={publishedCount}
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
        </aside>
      </div>
    </div>
  );
}

/**
 * The technical reading, in the compact form a quote page uses.
 *
 * WHY THIS READS THE INDICATOR ENDPOINT DIRECTLY: the full Technical
 * Analysis page has its own controls (which indicators, which RSI
 * period). Inside a quote page the reader wants the default set and the
 * numbers, not another control panel — so this takes the same endpoint
 * with the same defaults and shows the result.
 */
function AnalysisPanel({
  symbol,
  currency,
}: {
  symbol: string;
  currency?: string | null;
}) {
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: ["indicators", symbol, true, true, true, true, true, 14],
    queryFn: () =>
      fetchIndicators(symbol, {
        sma: true,
        ema: true,
        rsi: true,
        macd: true,
        bollinger: true,
        rsi_period: 14,
      }),
    retry: 1,
  });

  const series = useMemo(
    () => (query.data?.series as Array<Record<string, string | number | null>>) ?? [],
    [query.data],
  );

  if (query.isLoading) return <Loading variant="skeleton" className="h-80" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("analysis.err_connect", locale))}
        onRetry={() => query.refetch()}
      />
    );
  if (!series.length) {
    return (
      <EmptyState
        message={locale === "vi" ? "Không có chỉ báo cho mã này." : "No indicators for this symbol."}
        hint={
          locale === "vi"
            ? "Mở trang Phân tích để chọn chỉ báo."
            : "Open the Analysis page to choose indicators."
        }
      />
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">
              {locale === "vi" ? "Giá + SMA / EMA / Bollinger" : "Price + SMA / EMA / Bollinger"}
            </h2>
            <p className="section-sub">
              {locale === "vi"
                ? "Đường giá và các đường trung bình đọc từ tầng Gold."
                : "The price line and its moving averages, read from the Gold layer."}
            </p>
          </div>
        </div>
        <div className="pt-4">
          <PriceChartWithOverlays
            data={series.map((row) => ({
              timestamp: String(row.timestamp),
              close: toFinite(row.close) ?? 0,
              sma_20: toFinite(row.sma_20),
              sma_50: toFinite(row.sma_50),
              ema_12: toFinite(row.ema_12),
              bb_upper: toFinite(row.bb_upper),
              bb_lower: toFinite(row.bb_lower),
            }))}
          />
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2 className="section-title">RSI (14)</h2>
        </div>
        <div className="pt-4">
          <IndicatorChart
            data={series}
            lines={[{ key: "rsi_14", color: "hsl(var(--ink))", name: "RSI" }]}
            referenceLines={[
              { y: 70, label: "70", color: "hsl(var(--negative))" },
              { y: 30, label: "30", color: "hsl(var(--muted))" },
            ]}
            height={200}
          />
        </div>
      </section>

      <p className="font-mono text-label text-muted">
        {series.length.toLocaleString("en-US")} {locale === "vi" ? "nến" : "bars"} ·{" "}
        {currency ?? "—"}
      </p>
    </div>
  );
}

/**
 * The forecast reading: the forecasts the system published, next to the
 * real close once it exists.
 */
function ForecastPanel({ symbol, currency }: { symbol: string; currency?: string | null }) {
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: ["published-forecasts", symbol],
    queryFn: () => fetchPublishedForecasts(symbol),
    staleTime: 60_000,
    retry: 1,
  });

  if (query.isLoading) return <Loading variant="skeleton" className="h-32" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("forecast.published_empty", locale))}
        onRetry={() => query.refetch()}
      />
    );

  const forecasts = query.data?.forecasts ?? [];
  if (!forecasts.length) {
    return (
      <EmptyState
        message={
          locale === "vi" ? "Chưa có dự báo nào cho mã này." : "No published forecast for this symbol."
        }
        hint={
          locale === "vi"
            ? "Mở trang Dự báo để chạy mô hình."
            : "Open the Forecast page to run a model."
        }
      />
    );
  }

  return (
    <PublishedForecastComparison
      symbol={symbol}
      targetSession={query.data?.target_session ?? null}
      forecasts={forecasts}
      trainedModels={query.data?.trained_models ?? []}
      currency={currency}
    />
  );
}
