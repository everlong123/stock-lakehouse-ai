import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchMultiSymbolReport } from "@/api/backtesting";
import { errorMessage } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Explainer } from "@/components/common/Explainer";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Badge } from "@/components/ui/badge";
import { useI18n, t } from "@/lib/i18n";
import { formatNumber, formatPercent, shortDate } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
};

/**
 * The multi-symbol walk-forward tab.
 *
 * WHY A TAB BESIDE THE SINGLE-SYMBOL BACKTEST
 * ------------------------------------------
 * The single-symbol backtest answers "what happened on this one stock".
 * That is a demonstration, not evidence: one stock over one decade mostly
 * measures whether that stock went up. This tab answers the research
 * question - "does the strategy work ACROSS many stocks, and does it beat
 * simply holding them?" - by showing the DISTRIBUTION of the results
 * instead of a single number.
 *
 * The numbers come from a file produced by
 * `backend/scripts/run_multi_symbol_walkforward.py`, not from a live
 * request, because the run takes about two minutes. When the file is
 * missing the tab says so and shows the exact command to generate it; it
 * never shows a placeholder number.
 */
export function MultiSymbolWalkForward({ strategy }: { strategy: string }) {
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: ["multi-symbol-report", strategy],
    queryFn: () => fetchMultiSymbolReport(strategy),
    retry: 0,
    staleTime: 10 * 60 * 1000,
  });

  const report = query.data;
  const missing = report && report.available === false;

  return (
    <div className="space-y-12">
      <Explainer
        title={t("walkforward.explainer_title", locale)}
        intro={t("walkforward.explainer_intro", locale)}
        items={[
          {
            term: t("walkforward.term_walkforward", locale),
            meaning: t("walkforward.term_walkforward_meaning", locale),
          },
          {
            term: t("walkforward.term_oos", locale),
            meaning: t("walkforward.term_oos_meaning", locale),
          },
          {
            term: t("walkforward.term_bh", locale),
            meaning: t("walkforward.term_bh_meaning", locale),
          },
          {
            term: t("walkforward.term_median", locale),
            meaning: t("walkforward.term_median_meaning", locale),
          },
          {
            term: t("walkforward.term_excess", locale),
            meaning: t("walkforward.term_excess_meaning", locale),
          },
        ]}
        steps={[
          t("walkforward.step_1", locale),
          t("walkforward.step_2", locale),
          t("walkforward.step_3", locale),
          t("walkforward.step_4", locale),
        ]}
      />

      {query.isLoading ? (
        <EmptyState message={t("walkforward.loading", locale)} />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, t("walkforward.load_error", locale))} />
      ) : missing ? (
        <section className="space-y-4">
          <ErrorState message={report.reason ?? t("walkforward.missing", locale)} />
          <div className="rounded border border-hairline bg-surface p-4">
            <div className="label mb-2">{t("walkforward.how_to_title", locale)}</div>
            <code className="block font-mono text-small text-ink">
              cd backend
              <br />
              .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py --per-exchange 8
              --strategy {strategy}
            </code>
            <p className="mt-3 text-small text-muted">
              {t("walkforward.how_to_note", locale)}
            </p>
          </div>
        </section>
      ) : report ? (
        <ReportBody report={report} />
      ) : null}
    </div>
  );
}
function ReportBody({ report }: { report: Awaited<ReturnType<typeof fetchMultiSymbolReport>> }) {
  const { locale } = useI18n();
  const strat = report.strategy_distribution;
  const bh = report.buy_and_hold_distribution;
  const head = report.head_to_head;
  const exchanges = report.by_exchange ?? {};
  const rows = report.per_symbol ?? [];

  const chartData = Object.entries(exchanges).map(([exchange, row]) => ({
    exchange,
    strategy: row.strategy_median_return ?? 0,
    benchmark: row.buy_hold_median_return ?? 0,
  }));

  return (
    <>
      {/* The headline comparison. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">
            {`${t("walkforward.headline", locale)} ${report.config?.symbols_tested ?? 0} ${t("walkforward.symbols_on", locale)} ${report.config?.universe_size ?? 0}`}
          </h2>
          {/* WHEN THE REPORT WAS PRODUCED.
              This is the report's freshness, and it is load-bearing: the
              report is produced by the nightly `walk-forward` cron job, so
              without this stamp a reader cannot tell whether the numbers
              in front of them are from last night or from a month ago. */}
          {report.generated_at ? (
            <span className="font-mono text-label uppercase text-muted">
              {t("walkforward.generated_at", locale)} {shortDate(report.generated_at)}
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
          <MetricCard
            label={t("walkforward.median_strategy", locale)}
            value={formatPercent(strat?.median_avg_test_return ?? 0)}
          />
          <MetricCard
            label={t("walkforward.median_bh", locale)}
            value={formatPercent(bh?.median_avg_return ?? 0)}
          />
          <MetricCard
            label={t("walkforward.median_sharpe_strategy", locale)}
            value={formatNumber(strat?.median_avg_test_sharpe ?? 0)}
          />
          <MetricCard
            label={t("walkforward.median_sharpe_bh", locale)}
            value={formatNumber(bh?.median_sharpe ?? 0)}
          />
        </div>
      </section>

      <section>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
          <MetricCard
            label={t("walkforward.pct_profitable_strategy", locale)}
            value={`${(strat?.pct_symbols_profitable ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label={t("walkforward.pct_profitable_bh", locale)}
            value={`${(bh?.pct_symbols_profitable ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label={t("walkforward.pct_windows_beating", locale)}
            value={`${(head?.pct_windows_beating_buy_hold ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label={t("walkforward.median_excess", locale)}
            value={formatPercent(head?.median_paired_excess_return ?? 0)}
          />
        </div>
        <p className="mt-3 text-small text-muted">
          {t("walkforward.paired_note", locale).replace(
            "{windows}",
            String(head?.paired_windows ?? 0),
          )}
        </p>
      </section>

      {/* The finding, stated plainly. */}
      <section className="rounded border border-hairline bg-surface p-4">
        <div className="label mb-2">{t("walkforward.verdict_label", locale)}</div>
        <p className="max-w-3xl text-small text-ink">
          {(head?.median_paired_excess_return ?? 0) < 0
            ? t("walkforward.verdict_negative", locale)
                .replace("{excess}", formatPercent(head?.median_paired_excess_return ?? 0))
                .replace("{pct}", (head?.pct_symbols_beating_buy_hold ?? 0).toFixed(1))
            : t("walkforward.verdict_positive", locale)
                .replace("{excess}", formatPercent(head?.median_paired_excess_return ?? 0))
                .replace("{pct}", (head?.pct_symbols_beating_buy_hold ?? 0).toFixed(1))}
        </p>
        {report.note ? (
          <p className="mt-3 max-w-3xl text-small text-muted">{report.note}</p>
        ) : null}
      </section>

      {/* By exchange. */}
      {chartData.length ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">{t("walkforward.by_exchange", locale)}</h2>
          </div>
          <div className="pt-4">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={chartData}>
                <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
                {/* WHY THE TICKS ARE 12px: the design system's smallest
                    readable size is 12px (the `label` step). An 11px axis
                    label is below the floor the system sets everywhere
                    else, so the same number would look different here
                    than in every other chart. */}
                <XAxis
                  dataKey="exchange"
                  tick={{ fontSize: 12, fill: "hsl(var(--muted))", fontFamily: '"IBM Plex Mono", monospace' }}
                  angle={-30}
                  textAnchor="end"
                  height={70}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: "hsl(var(--muted))", fontFamily: '"IBM Plex Mono", monospace' }}
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => formatPercent(value)}
                />
                {/* WHY THE STRATEGY BAR IS THE BRAND ACCENT AND THE
                    BASELINE IS MUTED: this chart compares a MODEL against
                    a REFERENCE, not two directions of a price, so the
                    direction pair (blue/red) does not apply. The accent
                    marks the thing under test; the muted bar is the
                    reference it has to beat. */}
                <Bar
                  dataKey="strategy"
                  name={t("walkforward.series_strategy", locale)}
                  fill="hsl(var(--primary))"
                  radius={[6, 6, 0, 0]}
                />
                <Bar
                  dataKey="benchmark"
                  name={t("walkforward.series_bh", locale)}
                  fill="hsl(var(--muted))"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-8 overflow-auto rounded border border-hairline bg-surface shadow-sm">
            <table className="table">
              <thead>
                <tr>
                  {[
                    t("walkforward.col_exchange", locale),
                    t("walkforward.col_symbols", locale),
                    t("walkforward.col_median_strategy", locale),
                    t("walkforward.col_median_bh", locale),
                    t("walkforward.col_sharpe_strategy", locale),
                    t("walkforward.col_sharpe_bh", locale),
                    t("walkforward.col_pct_beating", locale),
                  ].map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(exchanges).map(([exchange, row]) => (
                  <tr key={exchange}>
                    <td className="font-mono">{exchange}</td>
                    <td className="font-mono tabular-nums">{row.symbols}</td>
                    <td className="font-mono tabular-nums">{formatPercent(row.strategy_median_return ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatPercent(row.buy_hold_median_return ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatNumber(row.strategy_median_sharpe ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatNumber(row.buy_hold_median_sharpe ?? 0)}</td>
                    <td>
                      <Badge variant={(row.pct_symbols_beating_buy_hold ?? 0) >= 50 ? "primary" : "negative"}>
                        {(row.pct_symbols_beating_buy_hold ?? 0).toFixed(1)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {/* Per symbol. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">
            {`${t("walkforward.per_symbol", locale)} ${rows.length} ${t("walkforward.symbols_suffix", locale)}`}
          </h2>
        </div>
        <div className="mt-4 max-h-[560px] overflow-auto rounded border border-hairline bg-surface shadow-sm">
          <table className="table">
            <thead className="sticky top-0">
              <tr>
                {[
                  t("walkforward.col_symbol", locale),
                  t("walkforward.col_exchange", locale),
                  t("walkforward.col_windows", locale),
                  t("walkforward.col_rr_strategy", locale),
                  t("walkforward.col_rr_bh", locale),
                  t("walkforward.col_sharpe_strategy", locale),
                  t("walkforward.col_sharpe_bh", locale),
                  t("walkforward.col_maxdd_strategy", locale),
                  t("walkforward.col_maxdd_bh", locale),
                  t("walkforward.col_beat", locale),
                ].map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.symbol}>
                  <td className="font-mono font-semibold">{row.symbol}</td>
                  <td className="font-mono text-muted">{row.exchange}</td>
                  <td className="font-mono tabular-nums text-muted">{row.passed_windows ?? "—"}</td>
                  <td className="font-mono tabular-nums">{formatPercent(row.avg_test_return ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatPercent(row.buy_hold_return ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.avg_test_sharpe ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.buy_hold_sharpe ?? 0)}</td>
                  <td className="font-mono tabular-nums text-muted">{formatPercent(row.avg_test_max_drawdown ?? 0)}</td>
                  <td className="font-mono tabular-nums text-muted">{formatPercent(row.buy_hold_max_drawdown ?? 0)}</td>
                  <td>
                    {row.beat_buy_hold == null ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <Badge variant={row.beat_buy_hold ? "primary" : "negative"}>
                        {row.beat_buy_hold ? t("walkforward.yes", locale) : t("walkforward.no", locale)}
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {report.errors && report.errors.length ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">
              {`${t("walkforward.unmeasurable", locale)} ${report.errors.length}`}
            </h2>
          </div>
          <div className="mt-4 overflow-auto rounded border border-hairline bg-surface shadow-sm">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("walkforward.col_symbol", locale)}</th>
                  <th>{t("walkforward.reason", locale)}</th>
                </tr>
              </thead>
              <tbody>
                {report.errors.map((err) => (
                  <tr key={err.symbol}>
                    <td className="font-mono">{err.symbol}</td>
                    <td className="text-muted">{err.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
