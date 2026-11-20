import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCompare, fetchTape, type TapeQuote } from "@/api/stocks";
import { Sparkline } from "@/components/common/Sparkline";
import { useMarket } from "@/hooks/useMarket";
import { currencyForSymbol, formatPrice } from "@/utils/format";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { WATCHLIST_SYMBOLS } from "@/utils/constants";

/**
 * The tickers carried by the watchlist.
 *
 * WHY THE SAME LIST AS THE NAV TAPE: the tape across the top and the
 * watchlist in the sidebar are two views of one decision - "which names am
 * I actually looking at". Picking different sets would make the two panels
 * disagree about what the user is tracking. The list itself lives in
 * `utils/constants` so the two components cannot drift apart.
 */

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
 *
 * WHY THERE IS A SPARKLINE AND WHERE ITS NUMBERS COME FROM
 * -------------------------------------------------------
 * A watchlist row without a shape only tells you where the price is now;
 * a row with a 30-session line also tells you which way it has been
 * going, which is the other half of the comparison a watchlist exists
 * for.
 *
 * The line is drawn from `GET /api/v1/stocks/compare?days=30`, which
 * returns the real stored closes of every ticker in ONE request. It is
 * not a second copy of the tape (which has only the last close) and it
 * is not a synthetic series - the closes are the lakehouse's own.
 */
export function LakehouseWatchlist() {
  const { symbol, setSymbol } = useMarket();
  const { locale } = useI18n();
  const [expanded, setExpanded] = useState(false);

  const query = useQuery({
    // WHY THE KEY MATCHES THE TAPE'S KEY EXACTLY: the tape in the top
    // band and this panel read the same endpoint for the same list. Two
    // different cache keys would mean two identical requests, and the
    // numbers on the two panels could differ by the time they landed.
    queryKey: ["tape", WATCHLIST_SYMBOLS.join(","), symbol],
    queryFn: () => fetchTape([...new Set([...WATCHLIST_SYMBOLS, symbol])]),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  /**
   * The 30-session closes behind each sparkline.
   *
   * WHY A SEPARATE REQUEST AND NOT THE TAPE: the tape endpoint returns one
   * row per symbol - the last close and the change. A sparkline needs the
   * whole series. The compare endpoint already serves exactly that for
   * many symbols in one round trip, so the watchlist adds one request
   * instead of twelve.
   */
  const sparkQuery = useQuery({
    queryKey: ["watchlist-spark", WATCHLIST_SYMBOLS.join(",")],
    queryFn: () => fetchCompare([...WATCHLIST_SYMBOLS], 30),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const sparkBySymbol = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const series of sparkQuery.data?.series ?? []) {
      map.set(
        series.symbol,
        series.points.map((p) => p.close),
      );
    }
    return map;
  }, [sparkQuery.data]);

  const rows = (query.data ?? [])
    // The selected symbol may not be on the watchlist; it is still
    // shown, because it is the ticker the page is about.
    .filter((row) => row.symbol !== symbol)
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
  const visible = expanded ? rows : rows.slice(0, 6);

  return (
    <section className="rounded border border-hairline bg-surface shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-body font-semibold text-ink">
            {locale === "vi" ? "Danh sách theo dõi" : "Watchlist"}
          </h2>
          <span className="font-mono text-label text-muted">{rows.length}</span>
        </div>
        <Button
          variant="text"
          size="sm"
          onClick={() => {
            void query.refetch();
            void sparkQuery.refetch();
          }}
          aria-label={locale === "vi" ? "Làm mới" : "Refresh"}
        >
          <RefreshCw size={13} className={query.isFetching ? "animate-spin" : ""} />
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-5 text-small text-muted">
          {query.isError
            ? (locale === "vi"
                ? "Không đọc được dữ liệu từ lakehouse."
                : "Cannot read the lakehouse.")
            : (locale === "vi"
                ? "Chưa có mã nào trong danh sách. Chạy auto-refresh để nạp bar từ provider."
                : "No symbols in the watchlist. Run auto-refresh to load bars from the provider.")}
        </p>
      ) : (
        <ul>
          {visible.map((row: TapeQuote) => {
            const active = row.symbol === symbol;
            const currency = row.currency || currencyForSymbol(row.symbol);
            const up = row.change_pct >= 0;
            const spark = sparkBySymbol.get(row.symbol);
            return (
              <li key={row.symbol}>
                <button
                  type="button"
                  onClick={() => setSymbol(row.symbol)}
                  className={cn(
                    "pressable flex min-h-14 w-full items-center gap-3 border-b border-hairline px-4 py-2 text-left last:border-b-0",
                    active ? "bg-primary/10" : "hover:bg-surface-2",
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
                    <span
                      className={cn(
                        "block font-mono text-label font-medium tabular-nums",
                        up ? "text-up" : "text-negative",
                      )}
                    >
                      {up ? "+" : ""}
                      {(row.change_pct * 100).toFixed(2)}%
                    </span>
                  </span>

                  {/* The 30-session shape. Decorative: the number beside
                      it already carries the meaning for a screen reader. */}
                  <Sparkline
                    values={spark ?? []}
                    width={56}
                    height={22}
                    className="hidden sm:block"
                  />

                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-small font-semibold tabular-nums text-ink">
                      {formatPrice(row.close, currency)}
                    </span>
                    <span className="block font-mono text-label text-muted">
                      {row.timestamp?.slice(0, 10) ?? "—"}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {rows.length > 6 ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="min-h-11 w-full px-4 text-left text-small font-semibold text-primary transition-colors hover:bg-surface-2"
        >
          {expanded
            ? (locale === "vi" ? "Thu gọn" : "Show less")
            : (locale === "vi" ? `Xem tất cả ${rows.length} mã` : `Show all ${rows.length} stocks`)}
        </button>
      ) : null}
    </section>
  );
}
