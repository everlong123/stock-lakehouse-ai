import { formatPrice, relativeTime } from "@/utils/format";

interface MarketCardProps {
  symbol: string;
  // Nullable: the dashboard passes `null` when no usable close is available,
  // so `formatPrice` can render "—" instead of a misleading zero.
  price: number | null;
  source?: string;
  updated?: string;
  // The quote currency. Prices are unitless in the lakehouse, so without it
  // every symbol would be labelled as if it traded in dong.
  currency?: string | null;
}

/**
 * The quote header.
 *
 * WHY THE PRICE IS `display` SIZE: this is the one number on the page the
 * reader came for. It gets the largest type in the system and the
 * negative tracking that large type needs, so it reads as a headline
 * rather than as another field.
 *
 * WHY THERE IS NO BOX: the quote header sits above the sidebar charts.
 * A border around it would cut it off from the page and make it look like
 * a separate widget instead of the identity of the symbol being shown.
 */
export function MarketCard({
  symbol,
  price,
  source,
  updated,
  currency,
}: MarketCardProps) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="label">Symbol</div>
          <div className="mt-1 truncate font-display text-body font-bold text-ink">
            {symbol}
          </div>
        </div>
        <span className="flex items-center gap-2 font-mono text-label uppercase text-primary">
          <span className="dot dot-live" />
          Live
        </span>
      </div>

      <div className="mt-4 font-mono text-display font-semibold tabular-nums text-ink">
        {formatPrice(price, currency)}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-hairline pt-4">
        <div className="min-w-0">
          <dt className="label">Source</dt>
          <dd className="mt-1 truncate font-mono text-small text-ink">{source || "lakehouse"}</dd>
        </div>
        <div className="min-w-0">
          <dt className="label">Updated</dt>
          <dd className="mt-1 truncate font-mono text-small text-ink">{relativeTime(updated)}</dd>
        </div>
      </dl>
    </div>
  );
}
