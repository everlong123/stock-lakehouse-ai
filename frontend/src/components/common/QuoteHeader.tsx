import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, TrendingDown, TrendingUp } from "lucide-react";
import { Sparkline } from "@/components/common/Sparkline";
import {
  formatNumber,
  formatPercent,
  formatPrice,
  formatVolume,
  isUsableNumber,
} from "@/utils/format";
import { cn } from "@/lib/utils";

export interface QuoteBar {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  prevClose: number | null;
  volume: number | null;
}

interface QuoteHeaderProps {
  symbol: string;
  currency?: string | null;
  /** The last bar of the stored series. */
  bar: QuoteBar;
  /** Absolute change against the previous close. */
  change?: number | null;
  /** The closes used to draw the inline sparkline, oldest first. */
  spark?: number[];
  /** The window's high and low, for the range bar. */
  range?: { high: number | null; low: number | null };
  /** The trading day of the last bar. */
  session?: string | null;
  /** Small links under the quote, e.g. "Explore price data". */
  links?: Array<{ to: string; label: string }>;
  /** True when the stored bar is older than the market's freshness window. */
  stale?: boolean;
}

/**
 * The quote header.
 *
 * WHY THIS EXISTS AND WHY IT IS BUILT LIKE THIS
 * ---------------------------------------------
 * Every serious finance portal opens a symbol page with the same four
 * things, in this order: the instrument's identity, the current price,
 * how much it moved, and where that price sits inside the day's range.
 * This app had those numbers scattered across the page - the price was
 * under the title, the open/high/low were nowhere at all, and the volume
 * was buried in a collapsed "analysis details" accordion.
 *
 * So the header gathers them into one band that can be read in a single
 * pass, and the layout follows the convention: identity on the left, the
 * price as the largest type on the page, the change right beside it, and
 * the session facts in a hairline-divided row underneath.
 *
 * WHY THE RANGE BAR EXISTS: "where is the price inside today's range" is
 * the question a trader asks first and it needs a spatial answer. The bar
 * answers it in 60 pixels, and it also carries the day's low and high as
 * labels — so the visual and the numbers agree.
 *
 * WHY THE SPARKLINE IS IN THE HEADER: it is the cheapest possible proof
 * of direction, and it costs ~30 lines of SVG instead of a charting
 * library. It is drawn from the closes the page already has, so it adds
 * no request.
 *
 * WHY NO BOX AROUND ANY OF IT: this band is the identity of the page, not
 * a widget inside it. A border would cut it off from the content below.
 * A single hairline under the band is enough separation.
 */
export function QuoteHeader({
  symbol,
  currency,
  bar,
  change,
  spark,
  range,
  session,
  links,
  stale,
}: QuoteHeaderProps) {
  const up = isUsableNumber(change) ? change > 0 : false;
  const down = isUsableNumber(change) ? change < 0 : false;

  // The absolute move, derived from the two closes the page already holds.
  //
  // WHY IT IS DERIVED HERE AND NOT PASSED IN: "up 12.34" and "up 1.53%"
  // are the same fact, and passing both would mean two callers could
  // disagree about it. Deriving the absolute move from the closes keeps
  // the pair consistent by construction.
  const changeAbs =
    isUsableNumber(bar.close) && isUsableNumber(bar.prevClose)
      ? bar.close - bar.prevClose
      : null;

  // Where the price sits inside the day's range, as a percentage.
  //
  // WHY IT IS COMPUTED HERE AND NOT FETCHED: it is a pure function of
  // three numbers the page already holds (low, high, close). Fetching it
  // would be a second source for a derived fact, and two sources for one
  // fact is how a page ends up disagreeing with itself.
  const position = useMemo(() => {
    if (!isUsableNumber(range?.high) || !isUsableNumber(range?.low)) return null;
    if (!isUsableNumber(bar.close)) return null;
    const span = range.high - range.low;
    if (span <= 0) return null;
    const raw = ((bar.close - range.low) / span) * 100;
    if (!Number.isFinite(raw)) return null;
    return Math.min(100, Math.max(0, raw));
  }, [range?.high, range?.low, bar.close]);

  // The direction arrow. It carries the same information as the colour,
  // but it survives a reader who cannot distinguish the hues — and the
  // colour is a secondary cue, never the only one.
  const DirectionIcon = up ? TrendingUp : down ? TrendingDown : null;

  return (
    <header className="border-b border-hairline pb-6">
      {/* ── Identity + price ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="font-display text-heading font-bold text-ink">{symbol}</h1>
            {currency ? (
              <span className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-label uppercase text-muted">
                {currency}
              </span>
            ) : null}
            {stale ? (
              <span className="rounded border border-negative/30 bg-negative/10 px-2 py-1 font-mono text-label uppercase text-negative">
                {session ? `Cũ · ${session}` : "Cũ"}
              </span>
            ) : null}
          </div>

          {/*
            The price block.

            WHY THE CHANGE IS IN A FILLED CHIP: on every big finance site
            the day's move sits in a small coloured badge next to the
            price, because it is the second number the reader looks at
            and a badge makes it findable. The chip's background is a TINT
            of the direction colour, so the colour is still the only
            thing carrying the meaning and the badge never competes with
            the price itself.
          */}
          <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-2">
            <strong
              className={cn(
                "font-mono text-display font-semibold tabular-nums",
                up ? "text-up" : down ? "text-negative" : "text-ink",
              )}
            >
              <FlashNumber
                value={bar.close}
                direction={up ? "up" : down ? "down" : "flat"}
                text={formatPrice(bar.close, currency)}
              />
            </strong>
            {isUsableNumber(change) ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-2 py-1 font-mono text-body font-semibold tabular-nums",
                  up
                    ? "bg-up/10 text-up"
                    : down
                      ? "bg-negative/10 text-negative"
                      : "bg-surface-2 text-muted",
                )}
              >
                {DirectionIcon ? <DirectionIcon size={15} aria-hidden="true" /> : null}
                {changeAbs !== null ? (
                  <>
                    {changeAbs > 0 ? "+" : ""}
                    {formatNumber(changeAbs)}
                  </>
                ) : null}
                <span>{formatPercent(change)}</span>
              </span>
            ) : (
              <span className="font-mono text-body text-muted">
                {session ? `Phiên ${session}` : "—"}
              </span>
            )}
          </div>

          {session ? (
            <p className="mt-2 font-mono text-label uppercase text-muted">
              {session}
              {bar.volume !== null ? ` · ${formatVolume(bar.volume)}` : ""}
            </p>
          ) : null}
        </div>

        {/* The sparkline: direction at a glance, no chart library. */}
        {spark && spark.length > 1 ? (
          <div className="shrink-0">
            <Sparkline values={spark} width={160} height={48} />
          </div>
        ) : null}
      </div>

      {/* ── The session facts ─────────────────────────────────────────── */}
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
        <Fact label="Mở cửa" value={formatPrice(bar.open, currency)} />
        <Fact label="Cao nhất" value={formatPrice(bar.high, currency)} tone="up" />
        <Fact label="Thấp nhất" value={formatPrice(bar.low, currency)} tone="down" />
        <Fact label="Đóng cửa trước" value={formatPrice(bar.prevClose, currency)} />
        <Fact label="Khối lượng" value={formatVolume(bar.volume)} />
      </dl>

      {/* ── The range bar ─────────────────────────────────────────────── */}
      {isUsableNumber(range?.low) && isUsableNumber(range?.high) ? (
        <div className="mt-6">
          <div className="flex items-baseline justify-between gap-4">
            <span className="label">Khoảng trong phiên</span>
            <span className="font-mono text-label text-muted">
              {formatPrice(range?.low, currency)} — {formatPrice(range?.high, currency)}
            </span>
          </div>
          <div className="relative mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-2">
            {/*
              The filled part of the range is drawn in the DIRECTION
              colour, not in the brand colour: the bar says "the price
              closed this far up the day's range", and that is a claim
              about the move, not about the app.
            */}
            <div
              className={cn(
                "absolute inset-y-0 left-0 rounded-full transition-[width] duration-300 ease-out",
                up ? "bg-up/30" : down ? "bg-negative/30" : "bg-hairline",
              )}
              style={{ width: `${position ?? 0}%` }}
            />
            <div
              className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded-full bg-ink transition-[left] duration-300 ease-out"
              style={{ left: `${position ?? 0}%` }}
              title={position !== null ? `${position.toFixed(0)}%` : undefined}
            />
          </div>
        </div>
      ) : null}

      {links?.length ? (
        <div className="mt-6 flex flex-wrap items-center gap-4">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="inline-flex min-h-9 items-center gap-2 text-small font-semibold text-primary transition-colors hover:gap-2.5"
            >
              {link.label}
              <ChevronRight size={14} aria-hidden="true" />
            </Link>
          ))}
        </div>
      ) : null}
    </header>
  );
}

/**
 * One session fact.
 *
 * WHY THE VALUE IS ALIGNED RIGHT ON A NARROW SCREEN: the facts form a
 * row of small numbers, and the reader compares them against each other
 * (open against high against close). Right-aligning the digits lines the
 * decimal points up, which is what makes the comparison possible at
 * 14px. On a wide screen the row is wide enough for the label to sit on
 * its own line above the number.
 */
function Fact({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
}) {
  return (
    <div className="min-w-0 border-l border-hairline pl-3 first:border-l-0 first:pl-0 sm:pl-4">
      <dt className="label">{label}</dt>
      <dd
        className={cn(
          "mt-1 font-mono text-small font-semibold tabular-nums",
          tone === "up" && "text-up",
          tone === "down" && "text-negative",
          !tone && "text-ink",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * A number that flashes when it changes.
 *
 * WHY THE FLASH LIVES HERE AND NOT IN A SHARED HOOK: the quote page and
 * the tape both need it, but they measure different things — the quote
 * flashes on a re-fetch, the tape on a poll — and a shared hook would
 * have to carry both policies. The rule is short enough to state twice.
 *
 * WHY THE VALUE IS A NUMBER AND NOT A STRING: the comparison has to be
 * exact. A formatted string would compare "1.00" against "1.000" as two
 * different prices.
 */
function FlashNumber({
  value,
  direction,
  text,
}: {
  value: number | null;
  direction: "up" | "down" | "flat";
  text: string;
}) {
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

  return (
    <span
      className={cn(
        "rounded px-1",
        flash === "up" ? "flash-up" : flash === "down" ? "flash-down" : "",
      )}
    >
      {text}
    </span>
  );
}
