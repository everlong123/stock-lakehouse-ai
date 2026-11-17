import { NavLink } from "react-router-dom";
import {
  Activity,
  CandlestickChart,
  LayoutDashboard,
  LineChart,
  Server,
  TestTubes,
  Waves,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useI18n, t } from "@/lib/i18n";
import { useMarket } from "@/hooks/useMarket";
import { fetchTape } from "@/api/stocks";
import { changeClass, formatPercent, formatPrice } from "@/utils/format";

const ITEMS = [
  { to: "/",            labelKey: "nav.dashboard",   icon: LayoutDashboard },
  { to: "/market",      labelKey: "nav.market",      icon: CandlestickChart },
  { to: "/analysis",    labelKey: "nav.analysis",    icon: Activity },
  { to: "/forecast",    labelKey: "nav.forecast",    icon: LineChart },
  { to: "/backtesting", labelKey: "nav.backtesting", icon: TestTubes },
  { to: "/agent",       labelKey: "nav.agent_full",  icon: Waves },
  { to: "/system",      labelKey: "nav.system",      icon: Server },
];

/**
 * The tickers carried by the tape.
 *
 * WHY A FIXED LIST AND NOT "THE FIRST N SYMBOLS": the tape is a watchlist,
 * and a watchlist is a decision. Auto-picking from the lakehouse would make
 * the strip jump around whenever the ingest set changes, and the user would
 * lose the ability to recognise their ticker in the row. This list mixes
 * the US heavyweights with three Vietnamese names, because the lakehouse
 * holds both markets and a strip that only shows one of them would make the
 * app look like it cannot read anything else.
 */
const TAPE_SYMBOLS = [
  "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
  "FPT", "VCB", "VHM", "HPG", "MWG",
];

/**
 * The navigation: a live market tape above the section tabs.
 *
 * WHY A TAPE AND NOT JUST TABS
 * -----------------------------
 * A row of eight grey links is a sitemap, not an instrument. Traders expect
 * the market to be *present* in the chrome — the first thing their eye
 * lands on when the app opens should be a price, not a word. So the bar
 * carries a real tape of real closes, read from the lakehouse, and it moves
 * when the data moves.
 *
 * WHY THE TAPE SCROLLS
 * ---------------------
 * Twelve tickers do not fit in 1600px without shrinking the type below the
 * 12px label floor, and shrinking is worse than scrolling. The strip is
 * duplicated and translated by exactly half its width, so the loop is
 * seamless, and it pauses the moment the pointer lands on it so a row can
 * actually be read.
 *
 * WHY CLICKING A TICKER MATTERS
 * ------------------------------
 * The tape is not decoration: clicking a ticker sets the symbol that every
 * page then reads. That is what turns the strip from a status display into
 * a control.
 *
 * WHY NOTHING HERE IS INVENTED
 * ----------------------------
 * Every close and every change on this bar comes from
 * ``GET /api/v1/stocks/tape``, which reads the same Gold -> Silver ->
 * Bronze path as every other endpoint. A ticker with no lakehouse data is
 * omitted from the strip rather than shown as 0.00 — an absent ticker is
 * honest, a zero-priced one is a lie.
 */
export function NavBar() {
  const { locale } = useI18n();
  const { symbol, setSymbol } = useMarket();

  const tape = useQuery({
    queryKey: ["tape", TAPE_SYMBOLS.join(",")],
    queryFn: () => fetchTape(TAPE_SYMBOLS),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  const quotes = tape.data ?? [];
  // Rendered twice so the marquee can translate by exactly half the track
  // width and come back around without a visible seam.
  const track = [...quotes, ...quotes];

  return (
    <div className="sticky top-14 z-20 border-b border-hairline bg-surface">
      {/* ── Market tape: real closes, straight from the lakehouse ── */}
      <div className="flex h-10 items-center gap-4 border-b border-hairline pr-6">
        <div className="flex shrink-0 items-center gap-2 pl-6">
          <span className="dot dot-live" />
          <span className="label">{locale === "vi" ? "Băng giá" : "Tape"}</span>
        </div>

        {quotes.length === 0 ? (
          <p className="truncate text-small text-muted">
            {tape.isError
              ? (locale === "vi"
                  ? "Không đọc được dải giá từ lakehouse."
                  : "Cannot read the tape from the lakehouse.")
              : (locale === "vi" ? "Đang tải dải giá…" : "Loading the tape…")}
          </p>
        ) : (
          <div className="tape-viewport min-w-0 flex-1 overflow-hidden">
            <div className="tape-track flex w-max items-center gap-8">
              {track.map((quote, index) => {
                const active = quote.symbol === symbol;
                return (
                  <button
                    key={`${quote.symbol}-${index}`}
                    type="button"
                    onClick={() => setSymbol(quote.symbol)}
                    aria-hidden={index >= quotes.length}
                    tabIndex={index >= quotes.length ? -1 : 0}
                    className={cn(
                      "flex shrink-0 items-baseline gap-2 rounded px-1 py-1 transition-colors",
                      "hover:bg-surface-2 focus-visible:outline-none",
                      active && "bg-surface-2",
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
                    <span className="font-mono text-label tabular-nums text-muted">
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
              })}
            </div>
          </div>
        )}
      </div>

      {/*
        ── Section tabs ─────────────────────────────────────────────────
        WHY THE TABS FILL THE BAR
        --------------------------
        A centred row of eight tabs leaves a wide blank margin on both
        sides of a 1474px viewport, and that emptiness reads as a broken
        layout rather than as deliberate spacing. Making every tab grow
        by the same amount (`flex-1`) turns the bar into one solid band
        of navigation: the eye reads a single full-width strip instead
        of a small cluster floating in the middle of the page, and the
        active tab is still obvious because it is the only filled one.

        `overflow-x-auto` plus `min-w` on the tabs keeps the row usable
        on a narrow window: instead of squashing the Vietnamese labels
        into an unreadable sliver, the bar scrolls sideways.
      */}
      <nav
        className="flex items-stretch gap-2 overflow-x-auto px-6 py-3"
        aria-label="Main navigation"
      >
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "navtab flex-1 justify-center",
                isActive && "border-primary bg-primary text-on-primary",
              )
            }
          >
            <item.icon size={14} className="shrink-0" />
            {t(item.labelKey, locale)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
