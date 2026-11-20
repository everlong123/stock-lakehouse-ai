import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchIndicators } from "@/api/indicators";
import { errorMessage } from "@/api/client";
import { PriceChart } from "@/components/charts/PriceChart";
import { IndicatorChart } from "@/components/charts/IndicatorChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageHeader } from "@/components/common/PageHeader";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { toFinite } from "@/utils/format";

/**
 * The backend's structured indicator facts.
 *
 * WHY FACTS AND NOT PROSE: the backend reports WHAT it observed (a code
 * plus the numbers it rests on) and this page writes the sentence in the
 * reader's language. If the prose came from the API it would be English
 * inside a Vietnamese UI.
 */
interface IndicatorFact {
  code: string;
  rsi?: number;
  width?: number;
}
interface IndicatorSummary {
  trend?: IndicatorFact;
  momentum?: IndicatorFact;
  volatility?: IndicatorFact;
}

/**
 * Turn one fact into a sentence in the active locale.
 *
 * The mapping is a CLOSED set of codes, and an unknown code falls back to
 * "not enough data" rather than being printed raw — a machine key like
 * `rsi_elevated` appearing on screen would be a bug, not a message.
 */
function describeFact(fact: IndicatorFact | undefined, locale: "vi" | "en"): string {
  if (!fact) return t("analysis.not_enough_data", locale);
  switch (fact.code) {
    case "uptrend":
      return t("close_above_sma20_sma50", locale);
    case "downtrend":
      return t("close_below_sma20_sma50", locale);
    case "mixed":
      return t("ma_mixed", locale);
    case "rsi_elevated":
      return `${t("rsi_elevated", locale)} RSI ${fact.rsi?.toFixed(2) ?? "—"}.`;
    case "rsi_depressed":
      return `${t("rsi_depressed", locale)} RSI ${fact.rsi?.toFixed(2) ?? "—"}.`;
    case "rsi_mid":
      return `${t("rsi_mid", locale)} RSI ${fact.rsi?.toFixed(2) ?? "—"}.`;
    case "bb_above":
      return t("bb_above", locale);
    case "bb_below":
      return t("bb_below", locale);
    case "bb_inside": {
      const width =
        fact.width != null
          ? t("bb_width", locale).replace("{width}", fact.width.toFixed(2))
          : "";
      return width ? `${t("bb_inside", locale)} ${width}` : t("bb_inside", locale);
    }
    default:
      return t("analysis.not_enough_data", locale);
  }
}

/**
 * TECHNICAL ANALYSIS — the indicator workbench.
 *
 * WHY THE INDICATOR STRIP IS A RECESSED BAR AND NOT A PANEL OF SETTINGS
 * -------------------------------------------------------------------
 * The toggles are FILTERS, not content. They sit on one row in a single
 * recessed strip so they read as a control bar, and so the chart below
 * owns the page. A column of checkboxes in a bordered box would make the
 * filters look like a section of their own.
 *
 * WHY THE CHARTS ARE STACKED AND NOT IN A GRID
 * --------------------------------------------
 * The price chart and the oscillator charts share one x-axis: the same
 * sessions, at the same scale. Stacking them means a reader can move
 * their eye down from a price move to the RSI that explains it without
 * re-aligning two separate plots. A side-by-side grid would put the
 * RSI's time axis at a different horizontal offset from the price's, and
 * "the RSI crossed 30 on the day the price fell" becomes a claim the
 * reader has to make by eye.
 */
export function TechnicalAnalysisPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();

  const [sma, setSma] = useState(true);
  const [ema, setEma] = useState(true);
  const [rsiOn, setRsiOn] = useState(true);
  const [macdOn, setMacdOn] = useState(true);
  const [bb, setBb] = useState(true);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const query = useQuery({
    queryKey: ["indicators", symbol, sma, ema, rsiOn, macdOn, bb, rsiPeriod],
    queryFn: () => fetchIndicators(symbol, {
      sma, ema, rsi: rsiOn, macd: macdOn, bollinger: bb, rsi_period: rsiPeriod,
    }),
    retry: 1,
  });

  const series = useMemo(() => (query.data?.series as Array<Record<string, string | number | null>>) || [], [query.data]);

  if (query.isLoading) return <Loading />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("analysis.err_connect", locale))}
        onRetry={() => query.refetch()}
      />
    );
  if (!series.length) return <EmptyState message={t("analysis.empty_symbol", locale)} />;

  const summary = (query.data?.summary as IndicatorSummary) || {};

  // Scan back for the newest usable RSI. `toFinite` is used instead of a bare
  // `Number.isNaN` check so a string-typed value ("N/A", "") is handled too,
  // and Infinity can't slip through and blow up the >70 / <30 comparison.
  const latestRSI = (() => {
    for (let i = series.length - 1; i >= 0; i--) {
      const v = toFinite(series[i].rsi_14);
      if (v !== undefined) return v;
    }
    return null;
  })();

  return (
    <div className="space-y-10">
      {/*
        ── The page header ───────────────────────────────────────────
        The symbol is the subject, so it leads the title line.
      */}
      <PageHeader
        section={t("nav.data", locale)}
        title={t("analysis.title", locale)}
        subtitle={t("analysis.subtitle", locale)}
        aside={
          <span className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-small font-semibold text-ink">
            {symbol}
          </span>
        }
      />

      {/*
        Indicator toggles
        --------------------
        These are filters, not content. They sit in one recessed strip on
        a single row so they read as a control bar rather than as a
        panel of settings, and so the chart below owns the page.
      */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4 rounded border border-hairline bg-surface-2 px-4 py-3">
        <span className="label">{t("analysis.indicator_label", locale)}</span>
        <Checkbox label="SMA" checked={sma} onChange={(e) => setSma(e.target.checked)} />
        <Checkbox label="EMA" checked={ema} onChange={(e) => setEma(e.target.checked)} />
        <Checkbox label="RSI" checked={rsiOn} onChange={(e) => setRsiOn(e.target.checked)} />
        <Checkbox label="MACD" checked={macdOn} onChange={(e) => setMacdOn(e.target.checked)} />
        <Checkbox label="Bollinger" checked={bb} onChange={(e) => setBb(e.target.checked)} />
        <label className="flex items-center gap-2 text-small text-ink">
          <span className="label">{t("analysis.rsi_period", locale)}</span>
          <Input
            type="number"
            value={rsiPeriod}
            onChange={(e) => setRsiPeriod(Number(e.target.value))}
            className="w-16 font-mono"
          />
        </label>
        <span className="ml-auto font-mono text-label text-muted">
          {series.length} {t("analysis.bars", locale)}
        </span>
      </div>

          {/* Price + overlays */}
          <section>
            <div className="section-head">
              <h2 className="section-title">{t("analysis.price_title", locale)}</h2>
            </div>
            <div className="pt-4">
              <PriceChart
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
      {/*
        The oscillator charts, STACKED UNDER the price chart.
        Same x-axis, same sessions, so a price move and the indicator that
        describes it sit directly above one another.
      */}
      {rsiOn ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">RSI ({rsiPeriod})</h2>
            {latestRSI !== null ? (
              <Badge variant={latestRSI > 70 ? "negative" : "default"}>
                {latestRSI.toFixed(2)} ·{" "}
                {latestRSI > 70
                  ? t("analysis.overbought", locale)
                  : latestRSI < 30
                    ? t("analysis.oversold", locale)
                    : t("analysis.neutral", locale)}
              </Badge>
            ) : null}
          </div>
          <div className="pt-4">
            {/*
              WHY THE RSI LINE IS INK AND NOT THE BRAND GREEN: RSI is a
              measure of the same direction the candles already use (blue
              up, red down), so it inherits the direction pair's neighbour
              in the visual hierarchy — the body text — rather than the
              brand accent. A green RSI line next to blue candles reads as
              a third, unrelated series.

              WHY 70 IS RED AND 30 IS MUTED: 70 is the line the indicator
              can cross *above* to mean "overbought" — the caution the
              reader needs to notice. 30 is the calm side; the badge above
              the chart already calls out "quá bán" when the value is
              actually there.
            */}
            <IndicatorChart
              data={series}
              lines={[{ key: "rsi_14", color: "hsl(var(--ink))", name: "RSI" }]}
              referenceLines={[
                { y: 70, label: "70", color: "hsl(var(--negative))" },
                { y: 30, label: "30", color: "hsl(var(--muted))" },
                { y: 50, label: "50", color: "hsl(var(--hairline))" },
              ]}
              height={220}
            />
          </div>
        </section>
      ) : null}

      {macdOn ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">MACD (12,26,9)</h2>
          </div>
          <div className="pt-4">
            {/*
              WHY MACD, SIGNAL AND HISTOGRAM ARE THREE WEIGHTS OF INK:
              they are three views of ONE indicator, so they must not
              compete as three colours. The MACD line is the loud one, the
              signal line is quieter, and the histogram is the faintest —
              all in the same family, so the reader sees one figure with
              three parts instead of three unrelated series.
            */}
            <IndicatorChart
              data={series}
              lines={[
                { key: "macd", color: "hsl(var(--ink))", name: "MACD" },
                { key: "macd_signal", color: "hsl(var(--muted))", name: "Signal" },
                { key: "macd_hist", color: "hsl(var(--hairline))", name: "Histogram" },
              ]}
              height={220}
            />
          </div>
        </section>
      ) : null}

      {/* Narrative summary: three short paragraphs, NOT three cards.
          These are readings, not widgets, so they run as a three-column
          text block under one rule. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">{t("analysis.summary_title", locale)}</h2>
        </div>
        <div className="grid gap-x-8 gap-y-6 pt-6 md:grid-cols-3">
          {[
            { key: "trend", label: t("analysis.trend", locale) },
            { key: "momentum", label: t("analysis.momentum", locale) },
            { key: "volatility", label: t("analysis.volatility", locale) },
          ].map(({ key, label }) => (
            <div key={key}>
              <div className="label">{label}</div>
              <p className="mt-2 text-small text-ink">
                {describeFact(summary[key as keyof IndicatorSummary], locale)}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
