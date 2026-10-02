import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: number | null;
  hint?: string;
}

export function MetricCard({ label, value, delta, hint }: MetricCardProps) {
  const trend =
    delta === undefined || delta === null
      ? "neutral"
      : delta > 0
        ? "up"
        : delta < 0
          ? "down"
          : "neutral";

  return (
    <div className="rounded-md border border-border bg-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>

      <div className="mt-2 font-mono text-[22px] font-semibold leading-none text-foreground">
        {value}
      </div>

      <div className="mt-3 flex items-center gap-2 text-[11px]">
        {trend === "up" && (
          <span className="inline-flex items-center gap-1 font-mono text-up">
            <ArrowUp size={11} />
            {(delta! * 100).toFixed(2)}%
          </span>
        )}
        {trend === "down" && (
          <span className="inline-flex items-center gap-1 font-mono text-down">
            <ArrowDown size={11} />
            {(delta! * 100).toFixed(2)}%
          </span>
        )}
        {trend === "neutral" && (
          <span className="inline-flex items-center gap-1 font-mono text-muted-foreground">
            <Minus size={11} />
            0.00%
          </span>
        )}
        {hint ? <span className={cn("text-muted-foreground")}>{hint}</span> : null}
      </div>
    </div>
  );
}