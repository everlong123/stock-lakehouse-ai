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
    <header
      className="sticky top-0 z-20 border-b"
      style={{
        borderColor: "hsl(210 18% 90% / 0.7)",
        background: "linear-gradient(180deg, hsl(0 0% 100% / 0.97) 0%, hsl(210 20% 97% / 0.95) 100%)",
        backdropFilter: "blur(16px) saturate(180%)",
        WebkitBackdropFilter: "blur(16px) saturate(180%)",
        boxShadow: "0 1px 0 hsl(210 18% 90% / 0.5), 0 2px 12px -4px hsl(0 0% 0% / 0.04)",
      }}
    >
      <div className="flex flex-wrap items-center gap-3 px-8 py-3">

        {/* ── Symbol search ──────────────────────────────────────── */}
        <div className="relative flex items-center">
          <Search
            size={13}
            className="absolute left-3 pointer-events-none"
            style={{ color: "hsl(220 12% 55%)" }}
          />
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onFocus={() => setSymbolFocused(true)}
            onBlur={() => setSymbolFocused(false)}
            className="appearance-none rounded-xl border bg-white pl-8 pr-8 py-1.5 font-mono text-sm font-semibold shadow-sm transition-all duration-200 focus:outline-none"
            style={{
              borderColor: symbolFocused ? "hsl(165 52% 28%)" : "hsl(210 18% 85%)",
              color: "hsl(220 25% 10%)",
              boxShadow: symbolFocused ? "0 0 0 3px hsl(165 52% 28% / 0.12), 0 1px 3px rgb(0 0 0 / 0.06)" : "0 1px 3px rgb(0 0 0 / 0.05)",
              minWidth: 120,
            }}
            aria-label="Symbol"
          >
            {availableSymbols.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          {/* Custom dropdown arrow */}
          <div
            className="absolute right-2.5 pointer-events-none"
            style={{ color: "hsl(220 12% 55%)" }}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>

        {/* ── Interval switcher ──────────────────────────────────── */}
        <div className="flex items-center gap-2">
          <IntervalSwitcher busy={fetching > 0} />
          {fetching > 0 && (
            <span
              className="animate-pulse font-mono text-[10px] uppercase tracking-wider"
              style={{ color: "hsl(165 52% 35%)" }}
            >
              {t("interval.loading", locale)}
            </span>
          )}
        </div>

        {/* ── Pipeline button ───────────────────────────────────── */}
        <Button
          onClick={refresh}
          disabled={busy}
          size="sm"
          className="rounded-xl shadow-sm transition-all duration-200"
          style={{
            background: "linear-gradient(135deg, hsl(165 52% 28%) 0%, hsl(165 58% 35%) 100%)",
            border: "none",
            boxShadow: busy ? "none" : "0 1px 4px hsl(165 52% 28% / 0.3)",
          }}
        >
          <RefreshCw
            size={13}
            className={`${busy ? "animate-spin" : ""} transition-transform duration-200`}
            style={{ color: "white" }}
          />
          <span style={{ color: "white", fontSize: 12 }}>
            {busy
              ? (locale === "vi" ? "Đang chạy…" : "Running…")
              : t("system.refresh", locale)}
          </span>
        </Button>

        {/* ── Right controls ─────────────────────────────────────── */}
        <div className="ml-auto flex items-center gap-3">

          {/* Locale toggle */}
          <div
            className="flex items-center rounded-xl border p-0.5"
            style={{
              borderColor: "hsl(210 18% 88%)",
              background: "hsl(210 20% 96%)",
            }}
            role="group"
            aria-label="Language"
          >
            <button
              type="button"
              onClick={() => setLocale("vi")}
              aria-pressed={locale === "vi"}
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition-all duration-200"
              style={
                locale === "vi"
                  ? {
                      background: "linear-gradient(135deg, hsl(165 52% 28%), hsl(165 58% 35%))",
                      color: "white",
                      boxShadow: "0 1px 3px hsl(165 52% 28% / 0.3)",
                    }
                  : { color: "hsl(220 12% 50%)" }
              }
            >
              <Languages size={11} />
              VI
            </button>
            <button
              type="button"
              onClick={() => setLocale("en")}
              aria-pressed={locale === "en"}
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition-all duration-200"
              style={
                locale === "en"
                  ? {
                      background: "linear-gradient(135deg, hsl(165 52% 28%), hsl(165 58% 35%))",
                      color: "white",
                      boxShadow: "0 1px 3px hsl(165 52% 28% / 0.3)",
                    }
                  : { color: "hsl(220 12% 50%)" }
              }
            >
              EN
            </button>
          </div>

          {/* Live indicator */}
          <div
            className="flex items-center gap-2 rounded-xl border px-3 py-1.5"
            style={{
              borderColor: "hsl(152 58% 38% / 0.3)",
              background: "hsl(152 58% 38% / 0.06)",
            }}
          >
            <span className="pulse-dot" />
            <span className="font-mono text-[11px] font-semibold uppercase tracking-wider" style={{ color: "hsl(152 58% 38%)" }}>
              Lakehouse Live
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
