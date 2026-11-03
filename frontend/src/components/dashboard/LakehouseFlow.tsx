import { ArrowRight, Layers } from "lucide-react";
import { isUsableNumber } from "@/utils/format";

interface FlowNode {
  label: string;
  desc: string;
}

const BRONZE: FlowNode = { label: "Bronze", desc: "Raw OHLCV" };
const SILVER: FlowNode = { label: "Silver", desc: "Cleaned & validated" };
const GOLD: FlowNode = { label: "Gold", desc: "Features & ML-ready" };

const SOURCES = [
  "Yahoo Finance",
  "SSI iBoard",
  "Finnhub",
  "Alpha Vantage",
];

interface LakehouseFlowProps {
  bronzeCount?: number | null;
  silverCount?: number | null;
  goldCount?: number | null;
}

// WHY null is allowed: the caller passes null while /system/status is loading or
// after it fails. Defaulting that to 0 would render "0 records", which is
// indistinguishable from a genuinely empty Bronze layer and makes a healthy
// lakehouse look broken.
export function LakehouseFlow({
  bronzeCount = null,
  silverCount = null,
  goldCount = null,
}: LakehouseFlowProps) {
  const layers = [
    { node: BRONZE, count: bronzeCount },
    { node: SILVER, count: silverCount },
    { node: GOLD, count: goldCount },
  ];

  return (
    <div className="rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Layers size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">Medallion lakehouse flow</h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Data &rarr; Bronze &rarr; Silver &rarr; Gold
        </span>
      </div>

      <div className="px-4 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Sources
          </span>
          {SOURCES.map((name) => (
            <span
              key={name}
              className="rounded border border-border bg-muted px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
            >
              {name}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          {layers.map(({ node, count }, idx) => (
            <div
              key={node.label}
              className="relative rounded-md border border-border bg-card p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Layer {idx + 1}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{node.label}</div>
                  <div className="text-[11px] text-muted-foreground">{node.desc}</div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-lg font-semibold text-foreground">
                    {isUsableNumber(count) ? count.toLocaleString("en-US") : "—"}
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {isUsableNumber(count) ? "records" : "chưa có dữ liệu"}
                  </div>
                </div>
              </div>
              {idx < 2 ? (
                <ArrowRight
                  size={14}
                  className="absolute -right-2 top-1/2 hidden -translate-y-1/2 bg-card text-muted-foreground md:block"
                />
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}