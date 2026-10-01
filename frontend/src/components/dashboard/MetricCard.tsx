import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: number | null;
  hint?: string;
  icon?: ReactNode;
}

export function MetricCard({ label, value, delta, hint, icon }: MetricCardProps) {
  const trend =
    delta === undefined || delta === null
      ? "neutral"
      : delta > 0
        ? "up"
        : delta < 0
          ? "down"
          : "neutral";

  return (
    <div className="card-elevated p-5">
      <div className="flex items-start justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {icon ? (
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            {icon}
          </span>
        ) : null}
      </div>

      <div className="mt-3 font-mono text-[26px] font-bold leading-none text-foreground">
        {value}
      </div>

      <div className="mt-3 flex items-center gap-2">
        {trend === "up" && (
          <span className="flex items-center gap-1 rounded-full bg-up/10 px-2 py-0.5 text-[11px] font-semibold text-up">
            <ArrowUp size={12} />
            {(delta! * 100).toFixed(2)}%
          </span>
        )}
        {trend === "down" && (
          <span className="flex items-center gap-1 rounded-full bg-down/10 px-2 py-0.5 text-[11px] font-semibold text-down">
            <ArrowDown size={12} />
            {(delta! * 100).toFixed(2)}%
          </span>
        )}
        {trend === "neutral" && (
          <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
            <Minus size={12} />
            —
          </span>
        )}
        {hint ? <span className={cn("text-[11px] text-muted-foreground")}>{hint}</span> : null}
      </div>
    </div>
  );
}