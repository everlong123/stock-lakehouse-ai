import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTape, type TapeQuote } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";
import { changeClass, formatPercent, formatPrice } from "@/utils/format";
import { WATCHLIST_SYMBOLS } from "@/utils/constants";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

/**
 * The market tape: a horizontal strip of real closes that scrolls under
 * the navigation.
 *
 * WHY IT MOVED OUT OF THE HEADER
 * ------------------------------
 * The header used to hold the symbol picker, the tape and the language
 * switch on one 56px line. Three things wanted that space and the tape
 * lost: a search box for a thousand-ticker universe cannot share a row
 * with a scrolling strip.
 *
 * So the tape gets its own band, one row under the navigation. That band
 * is also where the market clock lives, so the strip reads as "the state
 * of the market" rather than as decoration stuck under the menu.
 *
 * WHY IT SCROLLS
 * ---------------
 * Twelve tickers do not fit across a 1600px band at a readable type
 * size, and shrinking the type below the 12px label floor is worse than
 * scrolling. The strip is rendered twice and translated by exactly half
 * its width, so the loop is seamless, and it pauses the moment the
 * pointer lands on it so a row can actually be read.
 *
 * WHY CLICKING A TICKER MATTERS
 * ------------------------------
 * The tape is not decoration: clicking a ticker sets the symbol that
 * every page then reads. That is what turns the strip from a status
 * display into a control.
 *
 * WHY NOTHING HERE IS INVENTED
 * ----------------------------
 * Every close and every change on this strip comes from
 * `GET /api/v1/stocks/tape`, which reads the same Gold -> Silver -> Bronze
 * path as every other endpoint. A ticker with no lakehouse data is omitted
 * from the strip rather than shown as 0.00 - an absent ticker is honest, a
 * zero-priced one is a lie.
 */
export function MarketTape() {
  const { locale } = useI18n();
  const { symbol, setSymbol } = useMarket();

  const tape = useQuery({
    queryKey: ["tape", WATCHLIST_SYMBOLS.join(","), symbol],
    // The selected symbol is appended to the watchlist so the market
    // clock at the right of the band always has a session to report,
    // even for a ticker that is not on the watchlist.
    queryFn: () => fetchTape([...new Set([...WATCHLIST_SYMBOLS, symbol])]),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  const quotes = tape.data ?? [];
  // Rendered twice so the marquee can translate by exactly half the track
  // width and come back around without a visible seam.
  const track = [...quotes, ...quotes];

  // The newest session the lakehouse holds for the selected symbol.
  // It is the DATA's own timestamp, so the clock in the band reports a
  // fact about the stored bars instead of a guess about the wall clock.
  const latestSession = useMemo(() => {
    const row = quotes.find((quote) => quote.symbol === symbol);
    const stamp = row?.timestamp?.slice(0, 10);
    return stamp && stamp.length === 10 ? stamp : null;
  }, [quotes, symbol]);

  return (
    <div className="border-b border-hairline bg-surface/50">
      <div className="mx-auto flex h-9 max-w-[1600px] items-center gap-3 px-4 sm:px-6">
        <div className="hidden shrink-0 items-center gap-2 sm:flex">
          <span className="dot dot-live" />
          <span className="label">{locale === "vi" ? "Băng giá" : "Tape"}</span>
        </div>

        {quotes.length === 0 ? (
          <p className="truncate text-label text-muted">
            {tape.isError
              ? locale === "vi"
                ? "Không đọc được dải giá từ lakehouse."
                : "Cannot read the tape from the lakehouse."
              : locale === "vi"
                ? "Đang tải dải giá…"
                : "Loading the tape…"}
          </p>
        ) : (
          <div className="tape-viewport min-w-0 flex-1 overflow-hidden">
            <div className="tape-track flex w-max items-center">
              {track.map((quote: TapeQuote, index: number) => {
                const active = quote.symbol === symbol;
                return (
                  <TapeRow
                    key={`${quote.symbol}-${index}`}
                    quote={quote}
                    active={active}
                    duplicated={index >= quotes.length}
                    onSelect={() => setSymbol(quote.symbol)}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/*
          The market clock. It reads the NEWEST bar the lakehouse holds
          for the selected symbol, so it reports what the DATA says, not
          what the wall clock says. A stale bar is named as stale rather
          than being dressed up as "today".
        */}
        <div className="hidden shrink-0 items-center gap-2 border-l border-hairline pl-3 md:flex">
          <span className="dot dot-live" />
          <span className="font-mono text-label uppercase text-muted">
            {latestSession ? `Cập nhật ${latestSession}` : locale === "vi" ? "Chưa có phiên" : "No session"}
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * One ticker on the tape.
 *
 * WHY THE PRICE FLASHES WHEN IT CHANGES: the tape re-reads every minute,
 * and the reader cannot tell whether a number moved or whether they
 * simply looked away. A brief tint in the direction of the move is the
 * cheapest honest way to say "this just landed" — and it is the same
 * flash the quote page uses, so the two speak the same language.
 */
function TapeRow({
  quote,
  active,
  duplicated,
  onSelect,
}: {
  quote: TapeQuote;
  active: boolean;
  duplicated: boolean;
  onSelect: () => void;
}) {
  const direction = quote.change_pct > 0 ? "up" : quote.change_pct < 0 ? "down" : "flat";
  const flash = usePriceFlash(quote.close, direction);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-hidden={duplicated}
      tabIndex={duplicated ? -1 : 0}
      className={cn(
        "pressable flex shrink-0 items-baseline gap-2 rounded px-2 py-1",
        "hover:bg-surface-3 focus-visible:outline-none",
        active && "bg-primary/10",
      )}
      title={`${quote.symbol} · ${quote.timestamp}`}
    >
      <span
        className={cn(
          "font-mono text-label font-medium uppercase tracking-normal",
          active ? "text-primary" : "text-ink",
        )}
      >
        {quote.symbol}
      </span>
      <span
        className={cn(
          "rounded px-1 font-mono text-label tabular-nums",
          flash === "up"
            ? "flash-up"
            : flash === "down"
              ? "flash-down"
              : "text-muted",
        )}
      >
        {formatPrice(quote.close, quote.currency)}
      </span>
      <span
        className={cn(
          "font-mono text-label font-medium tabular-nums",
          changeClass(quote.change_pct),
        )}
      >
        {formatPercent(quote.change_pct)}
      </span>
    </button>
  );
}

/**
 * Flash a price when it changes.
 *
 * WHY THE COMPARISON IS KEPT IN A REF AND NOT IN STATE: the ref holds
 * the previous value without causing a render, and the flash class is
 * applied on the render that follows the change. The ref is cleared on a
 * timer so the same value does not flash twice.
 *
 * WHY THE FIRST VALUE NEVER FLASHES: on the first paint there is no
 * previous price, so there is no change to report. Flashing anyway would
 * announce a move that never happened.
 */
function usePriceFlash(value: number, direction: "up" | "down" | "flat"): "up" | "down" | null {
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const previous = useRef<number | null>(null);

  useEffect(() => {
    if (previous.current !== null && previous.current !== value) {
      setFlash(direction === "flat" ? null : direction);
      const timer = setTimeout(() => setFlash(null), 640);
      previous.current = value;
      return () => clearTimeout(timer);
    }
    previous.current = value;
    return undefined;
  }, [value, direction]);

  return flash;
}
