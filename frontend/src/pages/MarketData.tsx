import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
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
import { csvUrl, fetchCompare, fetchStats, fetchSymbols } from "@/api/stocks";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { BarIntervalSelector } from "@/components/common/BarIntervalSelector";
import { TimeRangeSelector, type TimeRange } from "@/components/common/TimeRangeSelector";
import { ForecastVerification } from "@/components/dashboard/ForecastVerification";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/api/client";
import { useI18n, t } from "@/lib/i18n";
import {
  changeClass,
  formatNumber,
  formatPercent,
  formatPrice,
  formatVolume,
  isUsableNumber,
  rangeStartDate,
  shortDate,
} from "@/utils/format";
import { BAR_INTERVAL_LABELS, resampleSolidBars, type BarInterval, type SolidBar } from "@/utils/resample";
import { cn } from "@/lib/utils";

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
  "JNJ", "WMT", "UNH", "XOM", "CVX", "BAC", "KO", "PEP", "DIS", "NFLX",
  "CRM", "ORCL", "ADBE", "INTC", "CSCO", "IBM", "QCOM", "TXN", "AVGO", "COST",
];

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
  "hsl(var(--negative))",
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
  const { symbol: ctxSymbol, interval, setSymbol } = useMarket();
  const { locale } = useI18n();

  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  useEffect(() => { setLocalSymbol(ctxSymbol); }, [ctxSymbol]);

  const [filter, setFilter] = useState("");
  // The window for the charts and the table.
  const [range, setRange] = useState<TimeRange>("1Y");
  // The granularity of the drawn bars.
  const [barInterval, setBarInterval] = useState<BarInterval>("1d");
  // The tickers being compared on the common-scale chart.
  const [compareSymbols, setCompareSymbols] = useState<string[]>([
    "AAPL", "MSFT", "FPT",
  ]);
  const [compareInput, setCompareInput] = useState("");

  const activeSymbol = localSymbol || ctxSymbol;

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
  // `latest.timestamp`. It is not known before the first request, so
  // the first request asks for the window measured from TODAY and the
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

  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols?.length
    ? symbolsQuery.data.symbols
    : DEFAULT_SYMBOLS;
  const visibleSymbols = availableSymbols.filter((s) =>
    s.toLowerCase().includes(filter.toLowerCase()),
  );

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

  const COLUMNS = [
    t("market.col_time", locale),
    t("market.col_open", locale),
    t("market.col_high", locale),
    t("market.col_low", locale),
    t("market.col_close", locale),
    t("market.col_volume", locale),
  ];

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

  return (
    <div className="space-y-12">
      <PageTitle
        title={t("market.title", locale)}
        subtitle={t("market.subtitle", locale)}
        meta={`02 · ${rows.length.toLocaleString("en-US")} bars · ${activeSymbol}`}
        actions={
          <a href={csvUrl(activeSymbol, interval)}>
            <Button variant="outline" size="sm">
              <Download size={13} />
              {t("market.csv", locale)}
            </Button>
          </a>
        }
      />

      {/*
        ── The controls ────────────────────────────────────────────────
        The window and the granularity are the two axes a reader needs,
        and they are independent: "one month of daily bars" and "ten years
        of monthly bars" are different requests. Both live in the header
        of the data section so the chart below always shows what the
        controls say it shows.
      */}
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("market.candle_title", locale)}</h2>
            <p className="section-sub">
              {windowedRows.length.toLocaleString("en-US")} / {rows.length.toLocaleString("en-US")} phiên
              {" · "}
              {chartBars.length} bars · {BAR_INTERVAL_LABELS[barInterval]}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <BarIntervalSelector value={barInterval} onChange={setBarInterval} />
            <TimeRangeSelector value={range} onChange={setRange} />
          </div>
        </div>

        <div className="pt-4">
          {chartBars.length ? (
            <CandlestickChart
              points={chartBars.slice(-260)}
              height={360}
              currency={currency}
            />
          ) : (
            <EmptyState message={t("dashboard.empty_candle", locale)} />
          )}
        </div>
      </section>

      {/*
        ── Forecast verification ───────────────────────────────────────
        WHY IT SITS HERE AND NOT ON ITS OWN PAGE
        ------------------------------------------
        The candles above show what the price DID. This panel shows what
        the system SAID would happen, and whether it was right. The two
        belong on the same page: the reader's question at this point is
        "what does this ticker do, and can the system predict it?", and
        answering it in two places makes them hunt.

        The forecasting page keeps its own charts, because that page is
        where models are trained and compared - a laboratory. This panel
        is the production record: forecasts that were published, and their
        outcomes.
      */}
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">Kiểm chứng dự báo</h2>
            <p className="section-sub">
              Những dự báo đã được ghi xuống trước khi phiên mở cửa, so với giá đóng cửa
              thật sau đó. Đây là độ chính xác ngoài tập huấn luyện — không phải backtest.
            </p>
          </div>
        </div>
        <div className="pt-4">
          <ForecastVerification symbol={activeSymbol} currency={currency} />
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
          <div className="section-head">
            <div>
              <h2 className="section-title">{t("market.stats_title", locale)}</h2>
              <p className="section-sub">{t("market.stats_sub", locale)}</p>
            </div>
          </div>

          {statsQuery.isLoading ? (
            <Loading variant="skeleton" className="pt-4" />
          ) : statsQuery.isError ? (
            <EmptyState
              className="mt-4"
              message={t("market.stats_empty", locale)}
              hint={errorMessage(statsQuery.error, "")}
            />
          ) : stats ? (
            <>
              <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-3">
                <Stat label={t("market.stat_return", locale)} value={formatPercent(stats.total_return_pct / 100)} tone={stats.total_return_pct} />
                <Stat label={t("market.stat_volatility", locale)} value={formatPercent(stats.volatility_pct === null ? null : stats.volatility_pct / 100)} />
                <Stat label={t("market.stat_drawdown", locale)} value={formatPercent(stats.max_drawdown_pct / 100)} tone={stats.max_drawdown_pct} />
                <Stat label={t("market.stat_high", locale)} value={formatPrice(stats.high, stats.currency)} />
                <Stat label={t("market.stat_low", locale)} value={formatPrice(stats.low, stats.currency)} />
                <Stat label={t("market.stat_avg_volume", locale)} value={formatVolume(stats.avg_volume)} />
              </dl>

              <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
                <Stat label={t("market.stat_sessions", locale)} value={stats.sessions.toLocaleString("en-US")} />
                <Stat label={t("market.stat_up_days", locale)} value={stats.up_days.toLocaleString("en-US")} tone={1} />
                <Stat label={t("market.stat_down_days", locale)} value={stats.down_days.toLocaleString("en-US")} tone={-1} />
                <Stat label={t("market.stat_total_volume", locale)} value={formatVolume(stats.total_volume)} />
              </dl>

              <p className="mt-4 font-mono text-label uppercase text-muted">
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
            {compareSymbols.map((symbol) => (
              <button
                key={symbol}
                type="button"
                onClick={() => toggleCompare(symbol)}
                className="inline-flex items-center gap-2 rounded border border-hairline bg-surface px-2 py-1 font-mono text-label font-medium uppercase text-ink transition-colors hover:bg-surface-2"
                title="Bỏ khỏi so sánh"
              >
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
                  <Legend
                    wrapperStyle={{ fontSize: 12, fontFamily: '"IBM Plex Mono", monospace' }}
                    iconType="plainline"
                    iconSize={14}
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
                  <th>{t("market.compare_col_base", locale)}</th>
                  <th>{t("market.compare_col_return", locale)}</th>
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
        Every bar in the window, newest first, with a sticky header. This
        is the page's reason to exist: the dashboard shows a summary of
        the latest session, this shows the archive.
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
        <div className="mt-4 max-h-[520px] overflow-auto rounded border border-hairline bg-surface">
          <table className="table">
            <thead className="sticky top-0">
              <tr>
                {COLUMNS.map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...windowedRows].reverse().map((row) => (
                <tr key={row.timestamp}>
                  <td className="font-mono whitespace-nowrap text-muted">
                    {shortDate(row.timestamp)}
                  </td>
                  <td className="font-mono tabular-nums">{formatNumber(row.open)}</td>
                  <td className="font-mono tabular-nums text-primary">{formatNumber(row.high)}</td>
                  <td className="font-mono tabular-nums text-negative">{formatNumber(row.low)}</td>
                  <td className="font-mono font-semibold tabular-nums">{formatNumber(row.close)}</td>
                  <td className="font-mono tabular-nums text-muted">
                    {formatVolume(row.volume)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/*
        ── Symbol picker rail ─────────────────────────────────────────
        The picker is a control, not content, so it sits at the bottom as
        a full-width search rather than a narrow column that steals
        width from the chart.
      */}
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("market.picker", locale)}</h2>
            <p className="section-sub">
              {visibleSymbols.length} / {availableSymbols.length} mã
            </p>
          </div>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("market.filter_placeholder", locale)}
            className="max-w-xs font-mono"
          />
        </div>
        <ul className="mt-4 flex flex-wrap gap-2">
          {visibleSymbols.slice(0, 120).map((s) => {
            const active = activeSymbol === s;
            return (
              <li key={s}>
                <button
                  onClick={() => {
                    setLocalSymbol(s);
                    setSymbol(s);
                  }}
                  className={cn(
                    "min-h-11 rounded border px-3 font-mono text-label transition-colors",
                    active
                      ? "border-primary text-primary"
                      : "border-hairline text-ink hover:bg-surface-2",
                  )}
                >
                  {s}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

/**
 * One statistic in the profile panel.
 *
 * WHY NO BOX: same reason as the dashboard's metric row — five numbers in
 * a row read as data, not as five widgets. The hairline does the
 * separating.
 */
function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: number | null;
}) {
  return (
    <div className="min-w-0 border-l border-hairline pl-4 first:border-l-0 first:pl-0">
      <dt className="label">{label}</dt>
      <dd className={cn("mt-1 font-mono text-body font-semibold tabular-nums", changeClass(tone))}>
        {value}
      </dd>
    </div>
  );
}
