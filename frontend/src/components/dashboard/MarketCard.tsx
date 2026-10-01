import { Database } from "lucide-react";
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
    <div className="card-elevated overflow-hidden p-0">
      <div className="relative bg-gradient-to-br from-brand-500 to-brand-700 p-5 text-white">
        <div className="absolute inset-0 opacity-30 mix-blend-overlay">
          <svg width="100%" height="100%">
            <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="white" strokeWidth="0.5" />
            </pattern>
            <rect width="100%" height="100%" fill="url(#grid)" />
          </svg>
        </div>
        <div className="relative">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider opacity-90">
            <Database size={12} />
            Lakehouse · Live
          </div>
          <div className="mt-3 text-2xl font-bold tracking-tight">{symbol}</div>
          <div className="mt-1 font-mono text-3xl font-bold">{formatPrice(price)}</div>
        </div>
      </div>
      <div className="p-4 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Source</span>
          <span className="font-medium text-foreground">{source || "lakehouse"}</span>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-muted-foreground">Cập nhật</span>
          <span className="font-medium text-foreground">{relativeTime(updated)}</span>
        </div>
      </div>
    </div>
  );
}