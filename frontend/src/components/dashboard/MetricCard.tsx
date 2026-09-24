import { changeClass, formatNumber, formatPercent } from "@/utils/format";

export function MetricCard({
  label,
  value,
  delta,
  hint,
}: {
  label: string;
  value: string;
  delta?: number | null;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-2 font-mono text-2xl font-semibold">{value}</div>
      {delta !== undefined && delta !== null ? (
        <div className={`mt-1 text-sm ${changeClass(delta)}`}>
          {delta > 0 ? "+" : ""}
          {formatPercent(delta)}
        </div>
      ) : null}
      {hint ? <div className="mt-2 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function formatMetricNumber(value: number | null | undefined): string {
  return formatNumber(value);
}
