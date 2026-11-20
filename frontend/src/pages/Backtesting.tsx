import { useState } from "react";
import { Explainer } from "@/components/common/Explainer";
import { PageHeader } from "@/components/common/PageHeader";
import { MultiSymbolWalkForward } from "@/components/backtesting/MultiSymbolWalkForward";
import { SingleSymbolBacktest } from "@/components/backtesting/SingleSymbolBacktest";
import { STRATEGIES } from "@/utils/constants";
import { useI18n, t } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type TabId = "single" | "population";

/**
 * Strategy evaluation — one page, two scales.
 *
 * WHY TWO TABS INSTEAD OF TWO PAGES
 * ---------------------------------
 * A single-stock backtest and a multi-symbol walk-forward report are the
 * same question asked at two scales: does this trading rule actually make
 * money, or is the number just the stock going up? The reader almost
 * always wants both — the single run for intuition, the population run for
 * evidence — and the baseline comparison lived on only one of them, so the
 * reader had to know which page carried the honest half.
 *
 * Keeping them on one page also lets the page OWN the strategy choice: the
 * same rule is measured on one stock and on a hundred, so the two numbers
 * are comparable. Splitting them let each page carry its own selector, and
 * a reader could compare a MA run against an RSI report without noticing.
 *
 * WHY THE TABS SIT UNDER THE TITLE, NOT IN THE NAV BAR: they are two
 * readings of one section, not two sections of the product. The nav bar
 * holds the sections; this strip holds the views inside one section.
 */
export function BacktestingPage() {
  const { locale } = useI18n();
  const [tab, setTab] = useState<TabId>("single");
  // The strategy is page-level state so BOTH tabs measure the same rule.
  const [strategy, setStrategy] = useState("ma_crossover");

  return (
    <div className="space-y-10">
      {/*
        ── The page header ───────────────────────────────────────────
        The strategy is page-level state, so it is named in the header:
        the reader can see which rule the whole page measures.
      */}
      <PageHeader
        section={t("nav.models", locale)}
        title={t("backtest.title", locale)}
        subtitle={t("backtest.subtitle", locale)}
      />

      {/*
        ── The tab strip ────────────────────────────────────────────
        Two readings of the same evaluation, so they read as a switch
        inside one section rather than two links in the sitemap.

        WHY THE STRIP IS ITS OWN ROW ABOVE THE STRATEGY PICKER: the
        strategy picker is a page-level control that BOTH tabs share, so
        it sits BELOW the switch that decides which reading is on screen.
        Putting the picker above the tabs would make it look like it
        belonged to the tab above it.
      */}
      <div
        role="tablist"
        aria-label={t("backtest.scope_label", locale)}
        className="flex items-center gap-1 border-b border-hairline"
      >
        {(
          [
            { id: "single" as TabId, label: t("backtest.tab_single", locale) },
            { id: "population" as TabId, label: t("backtest.tab_population", locale) },
          ]
        ).map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "relative -mb-px flex min-h-11 flex-col justify-center border-b-2 px-4 text-left transition-colors",
              tab === item.id
                ? "border-primary text-ink"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            <span className={cn("text-small", tab === item.id && "font-semibold")}>
              {item.label}
            </span>
          </button>
        ))}
      </div>

      {/*
        ── The shared strategy picker ───────────────────────────────
        ONE strategy for the whole page. The single-symbol run and the
        population report must describe the same rule, otherwise the two
        tabs answer different questions.
      */}
      <section>
        <div className="section-head">
          <h2 className="section-title">{t("backtest.strategy_title", locale)}</h2>
          <span className="font-mono text-label uppercase text-muted">
            {STRATEGIES.find((s) => s.id === strategy)?.label}
          </span>
        </div>
        <div className="pt-4">
          <div role="radiogroup" aria-label={t("backtest.strategy_label", locale)} className="flex flex-wrap gap-x-8 gap-y-4">
            {STRATEGIES.map((s) => {
              const active = strategy === s.id;
              return (
                <button
                  key={s.id}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setStrategy(s.id)}
                  className="group flex min-h-11 items-center gap-3 text-left"
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                      active ? "border-primary" : "border-hairline",
                    )}
                  >
                    {active ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                  </span>
                  <span>
                    <span
                      className={cn(
                        "block text-small font-semibold",
                        active ? "text-ink" : "text-muted",
                      )}
                    >
                      {s.label}
                    </span>
                    <span className="block font-mono text-label uppercase text-muted">
                      {s.hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {tab === "single" ? (
        <>
          <Explainer
            title={t("backtest.explainer_title", locale)}
            intro={t("backtest.explainer_intro", locale)}
            items={[
              {
                term: t("backtest.term_ma", locale),
                meaning: t("backtest.term_ma_meaning", locale),
              },
              {
                term: t("backtest.term_rsi", locale),
                meaning: t("backtest.term_rsi_meaning", locale),
              },
              {
                term: t("backtest.term_equity", locale),
                meaning: t("backtest.term_equity_meaning", locale),
              },
              {
                term: t("backtest.term_return", locale),
                meaning: t("backtest.term_return_meaning", locale),
              },
              {
                term: t("backtest.term_drawdown", locale),
                meaning: t("backtest.term_drawdown_meaning", locale),
              },
              {
                term: t("backtest.term_sharpe", locale),
                meaning: t("backtest.term_sharpe_meaning", locale),
              },
              {
                term: t("backtest.term_winrate", locale),
                meaning: t("backtest.term_winrate_meaning", locale),
              },
              {
                term: t("backtest.term_profit", locale),
                meaning: t("backtest.term_profit_meaning", locale),
              },
              {
                term: t("backtest.term_fees", locale),
                meaning: t("backtest.term_fees_meaning", locale),
              },
              {
                term: t("backtest.term_bh", locale),
                meaning: t("backtest.term_bh_meaning", locale),
              },
            ]}
            steps={[
              t("backtest.step_1", locale),
              t("backtest.step_2", locale),
              t("backtest.step_3", locale),
              t("backtest.step_4", locale),
              t("backtest.step_5", locale),
            ]}
          />
          <SingleSymbolBacktest strategy={strategy} />
        </>
      ) : (
        <MultiSymbolWalkForward strategy={strategy} />
      )}
    </div>
  );
}
