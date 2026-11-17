import { Languages, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { runPipeline } from "@/api/agent";
import { Button } from "@/components/ui/button";
import { IntervalSwitcher } from "@/components/market/IntervalSwitcher";
import { useMarket } from "@/hooks/useMarket";
import { useMarketBusy } from "@/hooks/useMarketBusy";
import { useI18n, t } from "@/lib/i18n";
import { fetchSymbols } from "@/api/stocks";

/**
 * The global top bar.
 *
 * WHY IT LOOKS THE WAY IT DOES
 * ------------------------------
 * A finance app's top bar is a single flat row: wordmark on the left, the
 * symbol picker next to it, small controls on the right. No gradient, no
 * shadow, no floating pill. The wordmark uses the DISPLAY font family so
 * the brand reads as a title, while every control around it uses the body
 * font - that contrast is what stops the bar looking like one flat strip
 * of grey.
 */
export function Header() {
  const { symbol, setSymbol } = useMarket();
  const fetching = useMarketBusy();
  const { locale, setLocale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [symbolFocused, setSymbolFocused] = useState(false);

  // Full list from lakehouse; short list as fallback.
  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols ?? ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"];

  const refresh = async () => {
    setBusy(true);
    try {
      await runPipeline(symbol, "1d");
      toast.success(
        locale === "vi"
          ? `Pipeline đã chạy cho ${symbol}`
          : `Pipeline ran for ${symbol}`,
      );
    } catch {
      toast.error(
        locale === "vi"
          ? "Không kết nối được backend API."
          : "Cannot connect to backend API.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-surface">
      <div className="flex h-14 items-center gap-6 px-6">
        {/* -- Brand ----------------------------------------------- */}
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-primary text-on-primary">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M3 17.5 9 10l4.5 4.5L21 5"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="hidden leading-none sm:block">
            <div className="font-display text-small font-bold tracking-tight text-ink">
              {t("app.title", locale)}
            </div>
            <div className="mt-1 font-mono text-label uppercase text-muted">
              {t("app.subtitle", locale)}
            </div>
          </div>
        </div>

        {/* -- Symbol picker --------------------------------------- */}
        <div className="relative flex items-center">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 text-muted"
          />
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onFocus={() => setSymbolFocused(true)}
            onBlur={() => setSymbolFocused(false)}
            className="appearance-none rounded border bg-surface py-2 pl-8 pr-8 font-mono text-small font-medium text-ink outline-none transition-colors"
            style={{
              borderColor: symbolFocused ? "hsl(var(--primary))" : "hsl(var(--hairline))",
              minWidth: 140,
            }}
            aria-label="Symbol"
          >
            {availableSymbols.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute right-3 text-muted">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>

        {/* -- Interval switcher ------------------------------------ */}
        <div className="flex items-center gap-3">
          <IntervalSwitcher busy={fetching > 0} />
          {fetching > 0 ? (
            <span className="font-mono text-label uppercase text-primary">
              {t("interval.loading", locale)}
            </span>
          ) : null}
        </div>

        {/* -- Right controls --------------------------------------- */}
        <div className="ml-auto flex items-center gap-3">
          {/* Locale toggle */}
          <div
            className="flex items-center rounded border border-hairline p-1"
            role="group"
            aria-label="Language"
          >
            {(["vi", "en"] as const).map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLocale(code)}
                aria-pressed={locale === code}
                className="inline-flex items-center gap-1 rounded px-2 py-1 font-mono text-label font-medium uppercase transition-colors"
                style={
                  locale === code
                    ? { background: "hsl(var(--primary))", color: "hsl(var(--on-primary))" }
                    : { color: "hsl(var(--muted))" }
                }
              >
                {code === "vi" ? <Languages size={11} /> : null}
                {code.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Pipeline button */}
          <Button onClick={refresh} disabled={busy} size="sm" variant="outline">
            <RefreshCw size={13} className={busy ? "animate-spin" : ""} />
            {busy
              ? (locale === "vi" ? "Đang chạy…" : "Running…")
              : t("system.refresh", locale)}
          </Button>

          {/* Live indicator */}
          <div className="flex items-center gap-2 rounded border border-hairline px-2 py-1">
            <span className="dot dot-live" />
            <span className="font-mono text-label font-medium uppercase text-primary">
              Live
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
