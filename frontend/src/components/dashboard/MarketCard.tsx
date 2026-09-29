import { formatPrice } from "@/utils/format";

export function MarketCard({
  symbol,
  price,
  source,
  updated,
}: {
  symbol: string;
  price: number;
  source?: string;
  updated?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">Market</div>
      <div className="mt-2 text-lg font-semibold">{symbol}</div>
      <div className="font-mono text-2xl">{formatPrice(price)}</div>
      <div className="mt-2 text-xs text-muted-foreground">
        Data source: {source || "lakehouse"}
        {updated ? ` · Last updated: ${updated.replace("T", " ").slice(0, 19)}` : ""}
      </div>
    </div>
  );
}
