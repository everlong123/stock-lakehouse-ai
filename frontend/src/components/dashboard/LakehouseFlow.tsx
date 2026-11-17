import { ArrowRight, Layers } from "lucide-react";
import { isUsableNumber } from "@/utils/format";

interface FlowNode {
  label: string;
  desc: string;
}

const BRONZE: FlowNode = { label: "Bronze", desc: "Raw OHLCV" };
const SILVER: FlowNode = { label: "Silver", desc: "Cleaned & validated" };
const GOLD: FlowNode = { label: "Gold", desc: "Features & ML-ready" };

/**
 * The data providers the lakehouse actually draws from.
 *
 * WHY THIS LIST IS NOT A CONSTANT ANYMORE: it used to include "Finnhub",
 * because the streaming path used to write Finnhub WebSocket ticks into
 * Bronze. Those ticks turned out to be attributed to the wrong ticker (NVDA
 * stored at 855-1938 against a true close of 237.47), so they were purged
 * and the streaming source is no longer part of the daily lakehouse.
 * Listing a provider that holds no rows makes the panel describe the system
 * inaccurately.
 */
const SOURCES = [
  "Yahoo Finance",
  "SSI iBoard",
  "yfinance",
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
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-3 pb-4">
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-muted" />
          <h2 className="font-display text-body font-semibold text-ink">
            Medallion lakehouse flow
          </h2>
        </div>
        <span className="font-mono text-label uppercase text-muted">
          Data &rarr; Bronze &rarr; Silver &rarr; Gold
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 pb-4">
        <span className="label">Sources</span>
        {SOURCES.map((name) => (
          <span
            key={name}
            className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-label uppercase text-muted"
          >
            {name}
          </span>
        ))}
      </div>

      {/* The three layers are a pipeline, not three equal cards. They are
          separated by arrows and share one continuous rule, which reads as
          a flow left-to-right instead of a row of identical widgets. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {layers.map(({ node, count }, idx) => (
          <div key={node.label} className="relative">
            <div className="flex items-baseline justify-between gap-3 border-b border-hairline pb-2">
              <div>
                <span className="font-mono text-label uppercase text-muted">
                  Layer {idx + 1}
                </span>
                <div className="mt-1 font-display text-body font-semibold text-ink">
                  {node.label}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-heading font-semibold tabular-nums text-ink">
                  {isUsableNumber(count) ? count.toLocaleString("en-US") : "?"}
                </div>
                {/*
                  WHY "files", not "records": the backend counts stored
                  objects (parquet partitions), not rows. Bronze holds
                  ~2.3M rows across ~113k partitions, so calling 114,904
                  "records" overstates the row count by 20x. The label has
                  to match what is actually being counted.
                */}
                <div className="label">
                  {isUsableNumber(count) ? "files" : "chưa có dữ liệu"}
                </div>
              </div>
            </div>
            <p className="mt-2 text-small text-muted">{node.desc}</p>
            {idx < 2 ? (
              <ArrowRight
                size={16}
                className="absolute -right-3 top-0 hidden text-muted md:block"
              />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
