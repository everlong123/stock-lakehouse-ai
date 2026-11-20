import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Download, X } from "lucide-react";
import { useMarket } from "@/hooks/useMarket";
import { useStocks } from "@/hooks/useStocks";
import { csvUrl, fetchCompare, fetchStats } from "@/api/stocks";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { VolumeChart } from "@/components/charts/DashboardCharts";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageHeader } from "@/components/common/PageHeader";
import { ChartTimeControls } from "@/components/common/ChartTimeControls";
import { ChartViewToggle, type ChartView } from "@/components/common/ChartViewToggle";
import { DataTable, sortRows, type Column, type SortState } from "@/components/common/DataTable";
import { KeyStatistics, type KeyStat } from "@/components/common/KeyStatistics";
import type { TimeRange } from "@/components/common/TimeRangeSelector";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/api/client";
import { useI18n, t } from "@/lib/i18n";
import {
  changeClass,
  formatNumber,
  formatPercent,
  formatSignedPercent,
  formatPrice,
  formatVolume,
  isUsableNumber,
  rangeStartDate,
  shortDate,
} from "@/utils/format";
import { resampleSolidBars, barPeriodLabel, type BarInterval, type SolidBar } from "@/utils/resample";
import { cn } from "@/lib/utils";

/**
 * How many days of history the "statistics" and "comparison" panels use.
 *
 * WHY THESE ARE DAYS AND NOT BARS: a year of *trading* is ~250 sessions,
 * but a year of *calendar* days is 365 — and the comparison window has to
 * be expressed in calendar days so that every ticker is cut at the same
 * moment. 365 days ≈ one trading year, which is the window a person
 * actually means by "over the last year".
 */
const WINDOW_DAYS: Record<Exclude<TimeRange, "ALL">, number> = {
  "1M": 31,
  "3M": 92,
  "6M": 183,
  "1Y": 366,
};

const COMPARE_COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--up))",
  "hsl(var(--muted))",
  "hsl(var(--ink))",
  "hsl(var(--hairline))",
];

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
  fontFamily: '"IBM Plex Mono", monospace',
} as React.CSSProperties;

/**
 * MARKET DATA — the lakehouse exploration workbench.
 *
 * WHY THIS PAGE IS NOT THE DASHBOARD
 * ---------------------------------
 * The dashboard answers "how is my symbol doing right now" — one symbol,
 * a summary, a recent chart. This page answers a different question:
 * "what does the stored data actually contain, and how do these tickers
 * compare against each other".
 *
 * So the two pages do different jobs:
 *
 *   Dashboard  ->  one symbol, live summary, charts, model/backtest context
 *   Market Data ->  the RAW lakehouse: full history, statistical profile,
 *                  cross-ticker comparison, the complete session table
 *
 * Concretely, this page has four things the dashboard does not:
 *
 *   1. A TIME WINDOW + GRANULARITY control. The dashboard's 3M/1W default
 *      hides two thirds of the stored history. Here the whole archive is
 *      reachable, and the window follows the range selector.
 *
 *   2. A STATISTICAL PROFILE computed by the backend from the stored
 *      closes: annualised volatility, maximum drawdown, up/down days,
 *      average volume. These describe what the price DID — a candle chart
 *      cannot.
 *
 *   3. A CROSS-TICKER COMPARISON on a common scale. Every series is
 *      rebased to 100 at the window's first bar, because AAPL near 340 and
 *      FPT near 51,000 cannot share an axis. One chart, several tickers,
 *      directly comparable.
 *
 *   4. The COMPLETE session table with every bar, sortable, plus a real
 *      CSV export of exactly what is on screen.
 *
 * WHY NOTHING HERE IS INVENTED
 * ----------------------------
 * Every figure comes from the lakehouse through the API. The statistics
 * are computed by `backend/app/api/v1/endpoints/stocks.py` from the stored
 * closes, the comparison is rebased from those same closes, and the table
 * is the stored rows. Nothing is smoothed, extrapolated, or filled in.
 */
export function MarketDataPage() {
  const { symbol: activeSymbol, interval } = useMarket();
  const { locale } = useI18n();

  // The window for the charts and the table.
  const [range, setRange] = useState<TimeRange>("1Y");
  // The granularity of the drawn bars.
  const [barInterval, setBarInterval] = useState<BarInterval>("1d");
  // Line or candles.
  const [view, setView] = useState<ChartView>("candle");
  // The tickers being compared on the common-scale chart.
  const [compareSymbols, setCompareSymbols] = useState<string[]>([
    "AAPL", "MSFT", "FPT",
  ]);
  const [compareInput, setCompareInput] = useState("");
  // The session table's sort order. Newest session first is the default,
  // because that is what a reader opening an archive wants to see.
  const [sort, setSort] = useState<SortState<string>>({ key: "timestamp", direction: "desc" });

  // The window in calendar days. "ALL" means the entire stored history.
  const windowDays = range === "ALL" ? null : WINDOW_DAYS[range];

  // The window, expressed as a START DATE for the server.
  //
  // WHY THE WINDOW IS APPLIED SERVER-SIDE
  // -------------------------------------
  // The stored history of a ten-year daily ticker is ~121 monthly
  // parquet partitions. Asking the backend for "the last year" lets it
  // download ~12 of them instead of all 121, so the page opens in a
  // fraction of the time.
  //
  // The anchor is the newest stored bar, which the backend returns as
  // `latest.timestamp`. It is not known before the first request, so the
  // first request asks for the window measured from TODAY and the
  // second - triggered by the anchor arriving - asks for the exact
  // window. Both are real requests for real stored rows.
  const [anchorTs, setAnchorTs] = useState<number | null>(null);
  const startDate = useMemo(
    () => rangeStartDate(range, anchorTs),
    [range, anchorTs],
  );

  const query = useStocks(activeSymbol, interval, startDate);

  useEffect(() => {
    const latest = query.data?.latest?.timestamp;
    if (!latest) return;
    const parsed = Date.parse(latest);
    if (!Number.isNaN(parsed)) setAnchorTs(parsed);
  }, [query.data?.latest?.timestamp]);

  // Statistics for the focused symbol, over the same window.
  const statsQuery = useQuery({
    queryKey: ["stock-stats", activeSymbol, windowDays ?? "all"],
    queryFn: () => fetchStats(activeSymbol, windowDays ?? 3650),
    retry: 1,
    staleTime: 60_000,
  });

  // Cross-ticker comparison over the same window.
  const compareQuery = useQuery({
    queryKey: ["stock-compare", compareSymbols.join(","), windowDays ?? "all"],
    queryFn: () => fetchCompare(compareSymbols, windowDays ?? 3650),
    retry: 1,
    staleTime: 60_000,
    enabled: compareSymbols.length > 0,
  });

  // ────────────────────────────────────────────────────────────────────
  // All the derived data is computed BEFORE the early returns below.
  //
  // WHY: React requires the same number of hooks on every render. A
  // `useMemo` placed after an `if (query.isLoading) return <Loading />`
  // would mean the loading render calls fewer hooks than the loaded
  // render, and React throws "Rendered more hooks than during the
  // previous render". The Dashboard page carries the same warning in a
  // comment; this file follows it.
  // ────────────────────────────────────────────────────────────────────

  const rows = query.data?.rows ?? [];

  // ────────────────────────────────────────────────────────────────────
  // The session table's columns.
  //
  // WHY THE TABLE IS DEFINED AS DATA: the page needs the same column set
  // for rendering AND for sorting, and a table that renders one shape and
  // sorts another is a table that sorts the wrong thing. One definition
  // feeds both.
  //
  // WHY IT IS A MEMO: the columns close over the locale, and rebuilding
  // them on every render would invalidate the sorted-rows memo below.
  // ────────────────────────────────────────────────────────────────────
  type SessionRow = (typeof rows)[number];

  const COLUMNS = useMemo<Column<SessionRow>[]>(
    () => [
      {
        key: "timestamp",
        label: t("market.col_time", locale),
        sortValue: (row) => Date.parse(row.timestamp),
        render: (row) => (
          <span className="font-mono whitespace-nowrap text-muted">
            {shortDate(row.timestamp)}
          </span>
        ),
      },
      {
        key: "open",
        label: t("market.col_open", locale),
        align: "right",
        sortValue: (row) => (isUsableNumber(row.open) ? row.open : null),
        render: (row) => (
          <span className="font-mono tabular-nums">{formatNumber(row.open)}</span>
        ),
      },
      {
        key: "high",
        label: t("market.col_high", locale),
        align: "right",
        sortValue: (row) => (isUsableNumber(row.high) ? row.high : null),
        render: (row) => (
          <span className="font-mono tabular-nums text-up">{formatNumber(row.high)}</span>
        ),
      },
      {
        key: "low",
        label: t("market.col_low", locale),
        align: "right",
        sortValue: (row) => (isUsableNumber(row.low) ? row.low : null),
        render: (row) => (
          <span className="font-mono tabular-nums text-negative">{formatNumber(row.low)}</span>
        ),
      },
      {
        key: "close",
        label: t("market.col_close", locale),
        align: "right",
        sortValue: (row) => (isUsableNumber(row.close) ? row.close : null),
        render: (row) => (
          <span className="font-mono font-semibold tabular-nums text-ink">
            {formatNumber(row.close)}
          </span>
        ),
      },
      {
        key: "volume",
        label: t("market.col_volume", locale),
        align: "right",
        sortValue: (row) => (isUsableNumber(row.volume) ? row.volume : null),
        render: (row) => (
          <span className="font-mono tabular-nums text-muted">
            {formatVolume(row.volume)}
          </span>
        ),
      },
    ],
    [locale],
  );

  // The window, applied to the stored rows.
  // The rows arrive ascending; the window keeps the tail.
  const windowedRows = useMemo(() => {
    if (windowDays === null || !rows.length) return rows;
    const anchor = Date.parse(rows[rows.length - 1].timestamp);
    if (Number.isNaN(anchor)) return rows;
    const cutoff = anchor - windowDays * 86_400_000;
    return rows.filter((r) => Date.parse(r.timestamp) >= cutoff);
  }, [rows, windowDays]);

  // Fold to the requested granularity. Solid bars only — a bar with a null
  // price cannot be drawn, and drawing a gap would misrepresent the series.
  const chartBars = useMemo<SolidBar[]>(() => {
    const solid = windowedRows.filter(
      (r): r is typeof r & { open: number; high: number; low: number; close: number } =>
        isUsableNumber(r.open) &&
        isUsableNumber(r.high) &&
        isUsableNumber(r.low) &&
        isUsableNumber(r.close),
    );
    return resampleSolidBars(solid, barInterval);
  }, [windowedRows, barInterval]);

  // The comparison series, folded onto a shared time axis.
  //
  // WHY: each ticker has its own trading days (a US ticker has no Saigon
  // holiday, a VN ticker has no US holiday). Plotting them as separate
  // recharts would misalign them, so the series are merged on the union of
  // their timestamps and each ticker's value is carried forward to the day
  // it was last observed. A day a ticker did not trade keeps its previous
  // value — that is what "the price was still X on that day" means.
  const compareChart = useMemo(() => {
    const series = compareQuery.data?.series ?? [];
    if (!series.length) return [];

    const days = new Set<string>();
    for (const s of series) {
      for (const p of s.points) days.add(p.timestamp.slice(0, 10));
    }
    const axis = Array.from(days).sort();

    // Walk each series once, carrying the last observed value forward.
    const carried = series.map((s) => {
      const byDay = new Map<string, number>();
      for (const p of s.points) byDay.set(p.timestamp.slice(0, 10), p.rebased);
      return { symbol: s.symbol, byDay, last: s.points[0]?.rebased ?? 100 };
    });

    return axis.map((day) => {
      const row: Record<string, number | string> = { day };
      for (const s of carried) {
        const value = s.byDay.get(day);
        if (value !== undefined) s.last = value;
        row[s.symbol] = s.last;
      }
      return row;
    });
  }, [compareQuery.data]);

  // ────────────────────────────────────────────────────────────────────
  // The session table's rows, in the reader's chosen order.
  // ────────────────────────────────────────────────────────────────────
  const sortedRows = useMemo(
    () => sortRows(windowedRows, COLUMNS, sort),
    [windowedRows, COLUMNS, sort],
  );

  if (query.isLoading) return <Loading />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("dashboard.err_connect", locale))}
        onRetry={() => query.refetch()}
      />
    );

  if (!rows.length)
    return (
      <EmptyState
        message={`${t("market.empty", locale)} ${activeSymbol}.`}
        hint="Chọn mã khác trên thanh trên cùng, hoặc chạy ingest để nạp dữ liệu."
      />
    );

  const latest = query.data?.latest;
  const currency = latest?.currency ?? null;

  const toggleCompare = (symbol: string) => {
    setCompareSymbols((current) =>
      current.includes(symbol)
        ? current.filter((s) => s !== symbol)
        : [...current, symbol].slice(0, 5),
    );
  };

  const addCompare = () => {
    const symbol = compareInput.trim().toUpperCase();
    if (!symbol) return;
    setCompareSymbols((current) =>
      current.includes(symbol) ? current : [...current, symbol].slice(0, 5),
    );
    setCompareInput("");
  };

  const stats = statsQuery.data;

  // The statistics panel's rows.
  const statRows: KeyStat[] = stats
    ? [
        {
          label: t("market.stat_return", locale),
          value: formatSignedPercent(stats.total_return_pct / 100),
          tone: stats.total_return_pct / 100,
        },
        {
          label: t("market.stat_volatility", locale),
          value: formatPercent(stats.volatility_pct === null ? null : stats.volatility_pct / 100),
        },
        {
          label: t("market.stat_drawdown", locale),
          value: formatPercent(stats.max_drawdown_pct / 100),
        },
        {
          label: t("market.stat_high", locale),
          value: formatPrice(stats.high, stats.currency),
        },
        {
          label: t("market.stat_low", locale),
          value: formatPrice(stats.low, stats.currency),
        },
        {
          label: t("market.stat_sessions", locale),
          value: stats.sessions.toLocaleString("en-US"),
        },
        {
          label: t("market.stat_up_days", locale),
          value: stats.up_days.toLocaleString("en-US"),
          direction: "up",
        },
        {
          label: t("market.stat_down_days", locale),
          value: stats.down_days.toLocaleString("en-US"),
          direction: "down",
        },
        {
          label: t("market.stat_avg_volume", locale),
          value: formatVolume(stats.avg_volume),
        },
        {
          label: t("market.stat_total_volume", locale),
          value: formatVolume(stats.total_volume),
        },
      ]
    : [];

  return (
    <div className="space-y-10">
      {/*
        ── The page header ───────────────────────────────────────────
        The symbol and the export action. The title stays a title; the
        symbol lives beside it because that is the thing the page is
        actually about.
      */}
      <PageHeader
        section="Dữ liệu"
        title={t("market.title", locale)}
        subtitle={t("market.subtitle", locale)}
        aside={
          <>
            <span className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-small font-semibold text-ink">
              {activeSymbol}
            </span>
            <a href={csvUrl(activeSymbol, interval)}>
              <Button variant="outline" size="sm">
                <Download size={13} />
                {t("market.csv", locale)}
              </Button>
            </a>
          </>
        }
      />

      {latest?.data_status === "stale" ? (
        <p role="status" className="border-l-2 border-negative pl-3 text-small text-negative">
          {locale === "vi"
            ? `Dữ liệu lịch sử chưa được cập nhật. Phiên cuối: ${latest.latest_session ?? latest.timestamp.slice(0, 10)}. Cần kiểm tra nguồn hoặc trạng thái giao dịch của mã này.`
            : `Historical data has not been updated. Latest session: ${latest.latest_session ?? latest.timestamp.slice(0, 10)}. Check the data source or listing status.`}
        </p>
      ) : null}

      {/*
        ── The controls ────────────────────────────────────────────────
        The window and the granularity are the two axes a reader needs,
        and they are independent: "one month of daily bars" and "ten years
        of monthly bars" are different requests. Both live in the header
        of the data section so the chart below always shows what the
        controls say it shows.
      */}
      <section>
        <ChartTimeControls
          barInterval={barInterval}
          onBarIntervalChange={setBarInterval}
          range={range}
          onRangeChange={setRange}
          dailyPoints={windowedRows}
          barCount={chartBars.length}
        >
          <ChartViewToggle value={view} onChange={setView} />
        </ChartTimeControls>

        <div className="pt-4">
          {view === "candle" ? (
            chartBars.length ? (
              <CandlestickChart
                points={chartBars}
                height={360}
                currency={currency}
                barInterval={barInterval}
              />
            ) : (
              <EmptyState message={t("dashboard.empty_candle", locale)} />
            )
          ) : chartBars.length ? (
            <PriceLine points={chartBars} currency={currency} barInterval={barInterval} />
          ) : (
            <EmptyState message={t("dashboard.empty_candle", locale)} />
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("dashboard.volume_title", locale)}</h2>
            <p className="section-sub">
              {locale === "vi"
                ? "Khối lượng theo cùng cách gộp và khoảng xem của biểu đồ nến."
                : "Volume uses the same grouping and date range as the candlestick chart."}
            </p>
          </div>
        </div>
        <div className="h-48 pt-4">
          <VolumeChart data={chartBars} barInterval={barInterval} />
        </div>
      </section>

      {/*
        ── Two columns ─────────────────────────────────────────────────
        The left column is the focused symbol's statistical profile; the
        right column is the cross-ticker comparison. A hairline separates
        them instead of two cards.
      */}
      <div className="grid gap-12 xl:grid-cols-2">
        {/* ── Statistical profile ─────────────────────────────────── */}
        <section>
          {statsQuery.isLoading ? (
            <>
              <div className="section-head">
                <h2 className="section-title">{t("market.stats_title", locale)}</h2>
              </div>
              <Loading variant="skeleton" className="pt-4" />
            </>
          ) : statsQuery.isError ? (
            <>
              <div className="section-head">
                <h2 className="section-title">{t("market.stats_title", locale)}</h2>
              </div>
              <EmptyState
                className="mt-4"
                message={t("market.stats_empty", locale)}
                hint={errorMessage(statsQuery.error, "")}
              />
            </>
          ) : stats ? (
            <>
              <KeyStatistics
                title={t("market.stats_title", locale)}
                stats={statRows}
              />
              <p className="mt-3 font-mono text-label uppercase text-muted">
                {shortDate(stats.window_start)} → {shortDate(stats.window_end)}
                {" · "}
                {stats.currency}
              </p>
            </>
          ) : null}
        </section>

        {/* ── Cross-ticker comparison ──────────────────────────────── */}
        <section>
          <div className="section-head">
            <div>
              <h2 className="section-title">{t("market.compare_title", locale)}</h2>
              <p className="section-sub">{t("market.compare_sub", locale)}</p>
            </div>
          </div>

          {/* Ticker picker: the chips ARE the legend, so the reader can
              see which line is which without hovering the chart. */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {compareSymbols.map((symbol, index) => (
              <button
                key={symbol}
                type="button"
                onClick={() => toggleCompare(symbol)}
                className="inline-flex items-center gap-2 rounded border border-hairline bg-surface px-2 py-1 font-mono text-label font-medium uppercase text-ink transition-colors hover:bg-surface-2"
                title={locale === "vi" ? `Bỏ ${symbol} khỏi so sánh` : `Remove ${symbol} from comparison`}
              >
                <span
                  aria-hidden="true"
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: COMPARE_COLORS[index % COMPARE_COLORS.length] }}
                />
                {symbol}
                <X size={11} className="text-muted" />
              </button>
            ))}
            <div className="flex items-center gap-2">
              <Input
                value={compareInput}
                onChange={(e) => setCompareInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addCompare();
                  }
                }}
                placeholder={t("market.compare_add", locale)}
                className="h-8 w-28 font-mono text-label"
                aria-label={t("market.compare_add", locale)}
              />
              <Button variant="outline" size="sm" onClick={addCompare}>
                {t("market.compare_add_short", locale)}
              </Button>
            </div>
          </div>

          <div className="mt-4 h-72">
            {compareQuery.isLoading ? (
              <Loading variant="skeleton" />
            ) : compareChart.length ? (
              <ResponsiveContainer>
                <LineChart data={compareChart} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
                  <XAxis
                    dataKey="day"
                    tickFormatter={(v: string) => v.slice(5)}
                    minTickGap={32}
                    stroke="hsl(var(--muted))"
                    fontSize={12}
                  />
                  <YAxis
                    stroke="hsl(var(--muted))"
                    fontSize={12}
                    fontFamily='"IBM Plex Mono", monospace'
                    domain={["auto", "auto"]}
                    width={56}
                    tickFormatter={(v: number) => v.toFixed(0)}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: "hsl(var(--muted))", fontSize: 12 }}
                    formatter={(v: number, name: string) => [
                      `${v.toFixed(1)} (${(((v - 100) / 100) * 100).toFixed(2)}%)`,
                      name,
                    ]}
                  />
                  {compareSymbols.map((symbol, index) => (
                    <Line
                      key={symbol}
                      type="monotone"
                      dataKey={symbol}
                      stroke={COMPARE_COLORS[index % COMPARE_COLORS.length]}
                      strokeWidth={symbol === activeSymbol ? 2 : 1.25}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message={t("market.compare_empty", locale)} />
            )}
          </div>

          {/* The ranked returns: a comparison chart without the numbers
              next to it is only half the answer. */}
          {compareQuery.data?.series?.length ? (
            <table className="table mt-4">
              <thead>
                <tr>
                  <th>{t("market.compare_col_symbol", locale)}</th>
                  <th className="text-right">{t("market.compare_col_base", locale)}</th>
                  <th className="text-right">{t("market.compare_col_return", locale)}</th>
                </tr>
              </thead>
              <tbody>
                {compareQuery.data.series.map((series) => (
                  <tr key={series.symbol}>
                    <td className="font-mono font-semibold text-ink">{series.symbol}</td>
                    <td className="font-mono tabular-nums text-muted">
                      {formatPrice(series.base_close, series.currency)}
                    </td>
                    <td
                      className={cn(
                        "font-mono font-semibold tabular-nums",
                        changeClass(series.return_pct / 100),
                      )}
                    >
                      {series.return_pct >= 0 ? "+" : ""}
                      {series.return_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      </div>

      {/*
        ── The complete session table ─────────────────────────────────
        Every bar in the window, sortable, with a sticky header. This is
        the page's reason to exist: the dashboard shows a summary of the
        latest session, this shows the archive.
      */}
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("market.table_title", locale)}</h2>
            <p className="section-sub">
              {windowedRows.length.toLocaleString("en-US")} phiên trong khung đang chọn
            </p>
          </div>
          <span className="font-mono text-label uppercase text-muted">
            {activeSymbol} · {interval}
          </span>
        </div>
        <div className="mt-4">
          <DataTable
            columns={COLUMNS}
            rows={sortedRows}
            sort={sort}
            onSortChange={setSort}
            rowKey={(row) => row.timestamp}
            emptyMessage={
              locale === "vi"
                ? "Không có phiên nào trong khoảng xem này."
                : "No sessions in this range."
            }
            maxHeight="max-h-[520px]"
          />
        </div>
      </section>
    </div>
  );
}

/**
 * The line view of the price chart.
 *
 * WHY IT IS ITS OWN COMPONENT: the candlestick chart is hand-drawn SVG
 * while this one uses recharts, and the page chooses between them. Keeping
 * them apart means neither pays for the other's code path.
 */
function PriceLine({
  points,
  currency,
  barInterval,
}: {
  points: SolidBar[];
  currency?: string | null;
  barInterval: BarInterval;
}) {
  const { locale } = useI18n();
  const data = useMemo(
    () => points.map((p) => ({ timestamp: p.timestamp, price: p.close })),
    [points],
  );
  if (!data.length) return null;

  return (
    <ResponsiveContainer>
      <AreaLineChart
        data={data}
        currency={currency}
        barInterval={barInterval}
        locale={locale}
      />
    </ResponsiveContainer>
  );
}

/**
 * The recharts line chart, kept separate so `PriceLine` stays a thin
 * wrapper and the chart itself is easy to read.
 */
function AreaLineChart({
  data,
  currency,
  barInterval,
  locale,
}: {
  data: Array<{ timestamp: string; price: number }>;
  currency?: string | null;
  barInterval: BarInterval;
  locale: "vi" | "en";
}) {
  return (
    <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
      <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
      <XAxis
        dataKey="timestamp"
        tickFormatter={(v: string) => v.slice(5)}
        minTickGap={32}
        stroke="hsl(var(--muted))"
        fontSize={12}
      />
      <YAxis
        stroke="hsl(var(--muted))"
        fontSize={12}
        fontFamily='"IBM Plex Mono", monospace'
        domain={["auto", "auto"]}
        width={64}
        tickFormatter={(v: number) => v.toFixed(0)}
      />
      <Tooltip
        contentStyle={tooltipStyle}
        labelStyle={{ color: "hsl(var(--muted))", fontSize: 12 }}
        formatter={(v: number) => [
          formatPrice(v, currency),
          locale === "vi" ? "Giá đóng cửa" : "Close",
        ]}
        labelFormatter={(v) => barPeriodLabel(String(v), barInterval, locale)}
      />
      <Line
        type="monotone"
        dataKey="price"
        stroke="hsl(var(--primary))"
        strokeWidth={1.75}
        dot={false}
        activeDot={{ r: 3, fill: "hsl(var(--primary))" }}
        isAnimationActive={false}
      />
    </LineChart>
  );
}
