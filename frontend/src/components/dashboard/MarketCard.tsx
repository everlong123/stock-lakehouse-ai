import { formatPrice, relativeTime } from "@/utils/format";

const TEAL = "hsl(165 52% 28%)";
const BORDER = "hsl(210 18% 90% / 0.6)";

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
    <div className="p-5">
      {/* Header row */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Symbol badge */}
          <div
            className="flex h-9 w-9 items-center justify-center rounded-xl font-mono text-[13px] font-bold"
            style={{
              background: `linear-gradient(135deg, ${TEAL} 0%, hsl(165 58% 35%) 100%)`,
              color: "white",
              boxShadow: `0 2px 8px ${TEAL}40`,
            }}
          >
            {symbol.slice(0, 2)}
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "hsl(220 12% 50%)" }}>
              Symbol
            </div>
            <div className="font-mono text-[15px] font-bold" style={{ color: "hsl(220 25% 10%)" }}>
              {symbol}
            </div>
          </div>
        </div>

        {/* Live badge */}
        <div
          className="flex items-center gap-1.5 rounded-full px-2.5 py-1"
          style={{
            background: "hsl(152 58% 38% / 0.1)",
            border: "1px solid hsl(152 58% 38% / 0.2)",
          }}
        >
          <span className="pulse-dot" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-wider" style={{ color: "hsl(152 58% 38%)" }}>
            Live
          </span>
        </div>
      </div>

      {/* Price */}
      <div className="mb-4">
        <div className="font-mono text-[11px] uppercase tracking-widest" style={{ color: "hsl(220 12% 50%)" }}>
          Price
        </div>
        <div
          className="mt-1 font-mono font-bold"
          style={{ fontSize: 32, color: "hsl(220 25% 10%)", lineHeight: 1.1 }}
        >
          {formatPrice(price)}
        </div>
      </div>

      {/* Metadata */}
      <div
        className="grid grid-cols-2 gap-2 rounded-xl p-3"
        style={{ background: "hsl(210 20% 97%)", border: `1px solid ${BORDER}` }}
      >
        <div>
          <div className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "hsl(220 12% 55%)" }}>
            Source
          </div>
          <div className="mt-0.5 truncate font-mono text-[12px] font-medium" style={{ color: TEAL }}>
            {source || "lakehouse"}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "hsl(220 12% 55%)" }}>
            Updated
          </div>
          <div className="mt-0.5 truncate font-mono text-[12px] font-medium" style={{ color: "hsl(220 25% 30%)" }}>
            {relativeTime(updated)}
          </div>
        </div>
      </div>
    </div>
  );
}
