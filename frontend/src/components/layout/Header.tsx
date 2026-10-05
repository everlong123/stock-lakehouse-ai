import { Languages, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { runPipeline } from "@/api/agent";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
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

  // Full list from lakehouse; keep a short list as last-resort fallback.
  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols ?? ["AAPL", "MSFT", "GOOGL"];

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
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-border bg-card px-8 py-3">
      <Select
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        aria-label="Symbol"
      >
        {availableSymbols.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>

      <div className="flex items-center gap-2">
        <IntervalSwitcher busy={fetching > 0} />
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {fetching > 0 ? t("interval.loading", locale) : ""}
        </span>
      </div>

      <Button onClick={refresh} disabled={busy} size="sm">
        <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
        {busy
          ? locale === "vi"
            ? "Đang chạy pipeline…"
            : "Running pipeline…"
          : t("system.refresh", locale)}
      </Button>

      <div className="ml-auto flex items-center gap-3">
        {/* Locale toggle */}
        <div
          className="flex items-center rounded-md border border-border bg-card p-0.5"
          role="group"
          aria-label="Language"
        >
          <button
            type="button"
            onClick={() => setLocale("vi")}
            aria-pressed={locale === "vi"}
            className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              locale === "vi"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Languages size={11} />
            VI
          </button>
          <button
            type="button"
            onClick={() => setLocale("en")}
            aria-pressed={locale === "en"}
            className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              locale === "en"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            EN
          </button>
        </div>

        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-up" aria-hidden="true" />
          Lakehouse live
        </div>
      </div>
    </header>
  );
}