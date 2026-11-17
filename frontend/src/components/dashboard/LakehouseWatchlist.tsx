import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchTape, type TapeQuote } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";
import { currencyForSymbol, formatPrice } from "@/utils/format";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

/**
 * The tickers carried by the watchlist.
 *
 * WHY THE SAME LIST AS THE NAV TAPE: the tape across the top and the
 * watchlist in the sidebar are two views of one decision - "which names am
 * I actually looking at". Picking different sets would make the two panels
 * disagree about what the user is tracking.
 */
const WATCHLIST_SYMBOLS = [
  "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
  "FPT", "VCB", "VHM", "HPG", "MWG",
];

/**
 * Lakehouse watchlist.
 *
 * WHY IT READS THE LAKEHOUSE AND NOT A LIVE TICK FEED
 * ----------------------------------------------------
 * This panel used to read the in-memory stream cache, which was fed by
 * WebSocket clients. That path was removed on 11/11/2026: the project is
 * a batch pipeline, so the only prices that exist are the closing bars
 * that the cron jobs wrote to Bronze and rebuilt into Gold.
 *
 * So the watchlist now reads `GET /api/v1/stocks/tape` — the same
 * endpoint that draws the navigation tape. Every number on it is a real
 * stored close with a real timestamp, and a symbol with no lakehouse data
 * is simply absent rather than shown as zero.
 *
 * WHY IT IS A LIST, NOT A GRID OF CARDS
 * -------------------------------------
 * A watchlist is a ranked set of rows. Rendering it as a grid of tiles
 * forces the eye to hunt across three columns to compare two tickers, when
 * the whole point of a watchlist is comparing them down a single column.
 *
 * Each row is a plain row separated by a hairline. The symbol is the
 * anchor (left, mono), the price is right-aligned in mono so the decimal
 * points line up, and the change sits under the price. Everything a
 * trader scans for is in a predictable column.
 */
export function LakehouseWatchlist() {
  const { symbol, setSymbol } = useMarket();
  const { locale } = useI18n();

  const query = useQuery({
    queryKey: ["tape", WATCHLIST_SYMBOLS.join(",")],
    queryFn: () => fetchTape(WATCHLIST_SYMBOLS),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  const rows = (query.data ?? []).slice().sort((a, b) => a.symbol.localeCompare(b.symbol));

  return (
    <section>
      <div className="flex items-center justify-between gap-3 pb-3">
        <div className="flex items-center gap-2">
          <span className="dot" />
          <h2 className="font-display text-body font-semibold text-ink">
            {locale === "vi" ? "Danh sách theo dõi" : "Watchlist"}
          </h2>
        </div>
        <Button
          variant="text"
          size="sm"
          onClick={() => query.refetch()}
          aria-label={locale === "vi" ? "Làm mới" : "Refresh"}
        >
          <RefreshCw size={13} className={query.isFetching ? "animate-spin" : ""} />
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="border-t border-hairline py-4 text-small text-muted">
          {query.isError
            ? (locale === "vi"
                ? "Không đọc được dữ liệu từ lakehouse."
                : "Cannot read the lakehouse.")
            : (locale === "vi"
                ? "Chưa có mã nào trong danh sách. Chạy auto-refresh để nạp bar từ provider."
                : "No symbols in the watchlist. Run auto-refresh to load bars from the provider.")}
        </p>
      ) : (
        <ul className="border-t border-hairline">
          {rows.map((row: TapeQuote) => {
            const active = row.symbol === symbol;
            const currency = row.currency || currencyForSymbol(row.symbol);
            const up = row.change_pct >= 0;
            return (
              <li key={row.symbol}>
                <button
                  type="button"
                  onClick={() => setSymbol(row.symbol)}
                  className={cn(
                    "flex min-h-11 w-full items-center justify-between gap-3 border-b border-hairline py-2 text-left transition-colors last:border-b-0",
                    active ? "bg-surface-2" : "hover:bg-surface-2",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate font-mono text-small font-semibold",
                        active ? "text-primary" : "text-ink",
                      )}
                    >
                      {row.symbol}
                    </span>
                    <span className="block truncate font-mono text-label text-muted">
                      {row.source_layer || "lakehouse"}
                    </span>
                  </span>

                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-small font-semibold tabular-nums text-ink">
                      {formatPrice(row.close, currency)}
                    </span>
                    <span
                      className={cn(
                        "block font-mono text-label font-medium tabular-nums",
                        up ? "text-primary" : "text-negative",
                      )}
                    >
                      {up ? "+" : ""}
                      {(row.change_pct * 100).toFixed(2)}%
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
