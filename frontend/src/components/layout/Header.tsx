import { ChartNoAxesCombined, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { runPipeline } from "@/api/agent";
import { fetchSymbols } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { SymbolSearch } from "@/components/common/SymbolSearch";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import { cn } from "@/lib/utils";

/**
 * The top bar: identity, the symbol search, the refresh action, the theme
 * switch and the language switch.
 *
 * WHY THE SYMBOL PICKER BECAME A SEARCH BOX
 * -----------------------------------------
 * The lakehouse holds over a thousand tickers. A `<select>` listing all
 * of them is a flat, unsearchable list — and opening a native select with
 * a thousand options costs a visible stall on Windows. Yahoo Finance
 * solves this with a combobox, so this does too: type two letters and
 * the universe filters in front of you.
 *
 * WHY THE CLOCK IS IN THE BAR AND NOT ON THE QUOTE PAGE
 * ------------------------------------------------------
 * "Is the market open?" is a question about the app, not about one
 * ticker, and the answer belongs in the chrome that is on every page.
 * The session label is derived from the LAKEHOUSE's newest stored bar,
 * so it is a fact about the data rather than a guess about the wall
 * clock.
 *
 * WHY THE BAR IS TRANSLUCENT
 * --------------------------
 * The header sits on top of scrolling content. A solid bar would cut
 * the page in two with a hard edge; a translucent one with a blur lets
 * the content behind it show through faintly, so the bar reads as
 * floating above the page rather than as a wall. The blur is cheap
 * because the bar is a small, fixed area.
 */
export function Header() {
  const { symbol, setSymbol } = useMarket();
  const { locale, setLocale } = useI18n();
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();

  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const symbols = symbolsQuery.data?.symbols ?? [];

  const refresh = async () => {
    setBusy(true);
    try {
      await runPipeline(symbol, "1d");
      await queryClient.invalidateQueries();
      toast.success(
        locale === "vi" ? `Đã nạp dữ liệu cho ${symbol}` : `Data refreshed for ${symbol}`,
      );
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : locale === "vi"
            ? "Không thể nạp dữ liệu."
            : "Data refresh failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="glass-bar sticky top-0 z-40 border-b border-hairline">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:gap-5 sm:px-6">
        <a
          href="/"
          className="group flex min-w-0 shrink-0 items-center gap-2 text-ink"
          aria-label={t("app.title", locale)}
        >
          {/*
            The logo mark. It is a gradient square rather than a flat one
            because it is the ONE place in the app where the brand colour
            is allowed to be loud: it is 32 pixels wide, it is the thing
            the reader looks for when the page scrolls, and a flat navy
            square would disappear against a navy canvas in dark mode.
          */}
          <span className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded bg-primary text-on-primary transition-transform duration-200 ease-out group-hover:scale-105">
            <span
              aria-hidden="true"
              className="absolute inset-0 opacity-90"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, hsl(var(--primary)) 0%, hsl(var(--primary-2)) 100%)",
              }}
            />
            <ChartNoAxesCombined size={18} className="relative" aria-hidden="true" />
          </span>
          <span className="hidden whitespace-nowrap font-display text-small font-bold sm:block">
            StockVision AI
          </span>
        </a>

        <span className="hidden h-6 w-px shrink-0 bg-hairline sm:block" aria-hidden="true" />

        {/*
          The symbol search. It takes the room the market tape used to
          hold on the left, because a symbol is a CONTROL and the tape
          was decoration. The tape moved to its own strip below the
          navigation, where it has the full width to scroll.
        */}
        <SymbolSearch
          value={symbol}
          symbols={symbols}
          onSelect={setSymbol}
          placeholder={locale === "vi" ? "Tìm mã chứng khoán" : "Search symbol"}
          className="w-40 sm:w-56 lg:w-72"
        />

        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
          {/*
            The refresh button spins while the pipeline runs. It is the
            only animated control in the bar, and the animation IS the
            feedback: the reader does not have to wait for a toast to
            learn that the work is under way.
          */}
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={busy}
            title={locale === "vi" ? "Nạp lại dữ liệu mã đang chọn" : "Refresh selected stock data"}
            aria-label={locale === "vi" ? "Nạp lại dữ liệu mã đang chọn" : "Refresh selected stock data"}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded text-muted transition-colors",
              "hover:bg-surface-2 hover:text-ink disabled:opacity-50",
            )}
          >
            <RefreshCw size={17} className={busy ? "animate-spin" : ""} />
          </button>

          <ThemeToggle className="hidden sm:inline-flex" />

          <div
            className="inline-flex rounded border border-hairline bg-surface-2 p-0.5"
            role="group"
            aria-label={locale === "vi" ? "Ngôn ngữ" : "Language"}
          >
            {(["vi", "en"] as const).map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLocale(code)}
                aria-pressed={locale === code}
                className={cn(
                  "h-8 min-w-8 rounded px-2 font-mono text-label font-semibold uppercase transition-colors",
                  locale === code
                    ? "bg-primary text-on-primary"
                    : "text-muted hover:bg-surface-3 hover:text-ink",
                )}
              >
                {code}
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}
