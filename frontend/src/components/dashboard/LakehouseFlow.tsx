import { Activity, Layers, Sparkles, ArrowRight } from "lucide-react";

interface FlowNode {
  label: string;
  desc: string;
  color: string;
  Icon: typeof Activity;
}

const BRONZE: FlowNode = { label: "Bronze", desc: "Raw OHLCV", color: "from-amber-50 to-amber-100 border-amber-200", Icon: Activity };
const SILVER: FlowNode = { label: "Silver", desc: "Cleaned & Validated", color: "from-slate-50 to-slate-100 border-slate-200", Icon: Layers };
const GOLD: FlowNode = { label: "Gold", desc: "Features & ML-ready", color: "from-brand-50 to-brand-100 border-brand-200", Icon: Sparkles };

const SOURCES: { name: string; tone: string }[] = [
  { name: "Yahoo Finance", tone: "bg-blue-50 text-blue-700 border-blue-200" },
  { name: "SSI iBoard", tone: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  { name: "Finnhub", tone: "bg-violet-50 text-violet-700 border-violet-200" },
  { name: "Alpha Vantage", tone: "bg-orange-50 text-orange-700 border-orange-200" },
];

interface LakehouseFlowProps {
  bronzeCount?: number;
  silverCount?: number;
  goldCount?: number;
}

export function LakehouseFlow({ bronzeCount = 0, silverCount = 0, goldCount = 0 }: LakehouseFlowProps) {
  return (
    <div className="card-elevated p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-foreground">Medallion Lakehouse Flow</h3>
          <p className="text-xs text-muted-foreground">Data &rarr; Bronze &rarr; Silver &rarr; Gold</p>
        </div>
        <span className="chip-primary">Live</span>
      </div>

      {/* Sources row */}
      <div className="mb-4 flex items-center gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Sources</span>
        <div className="flex flex-wrap gap-2">
          {SOURCES.map((source) => (
            <span key={source.name} className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${source.tone}`}>
              {source.name}
            </span>
          ))}
        </div>
      </div>

      {/* Layers */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {[BRONZE, SILVER, GOLD].map((node, idx) => {
          const count = idx === 0 ? bronzeCount : idx === 1 ? silverCount : goldCount;
          const Icon = node.Icon;
          return (
            <div
              key={node.label}
              className={`relative rounded-xl border bg-gradient-to-br p-4 transition-transform hover:-translate-y-0.5 ${node.color}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Icon size={18} className="text-foreground/70" />
                  <div>
                    <div className="text-sm font-bold text-foreground">{node.label}</div>
                    <div className="text-[11px] text-muted-foreground">{node.desc}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-lg font-bold text-foreground">
                    {count.toLocaleString("en-US")}
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">records</div>
                </div>
              </div>
              {/* Arrow */}
              {idx < 2 && (
                <div className="absolute -right-3 top-1/2 hidden -translate-y-1/2 text-brand-500 md:block">
                  <ArrowRight size={20} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
