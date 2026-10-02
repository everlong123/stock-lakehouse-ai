import { formatPrice, relativeTime } from "@/utils/format";

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
    <div className="rounded-md border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Symbol
          </span>
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-up">
            <span className="h-1.5 w-1.5 rounded-full bg-up" aria-hidden="true" />
            Live
          </span>
        </div>
        <div className="mt-1 font-mono text-[20px] font-semibold text-foreground">{symbol}</div>
      </div>
      <div className="px-4 py-4">
        <div className="font-mono text-[28px] font-semibold leading-none text-foreground">
          {formatPrice(price)}
        </div>
      </div>
      <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>Source</span>
          <span className="font-mono text-foreground">{source || "lakehouse"}</span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span>Cap nhat</span>
          <span className="font-mono text-foreground">{relativeTime(updated)}</span>
        </div>
      </div>
    </div>
  );
}