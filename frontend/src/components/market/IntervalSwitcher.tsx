import { Loader2 } from "lucide-react";
import { useMarket } from "@/hooks/useMarket";
import { cn } from "@/lib/utils";
import { INTERVALS } from "@/utils/constants";

const LABELS: Record<string, string> = {
  "1d": "1D",
};

interface IntervalSwitcherProps {
  busy?: boolean;
  className?: string;
}

/**
 * Compact interval selector with quick-switch chips.
 *
 * Designed to mirror the look of broker dashboards (TCBS / VNDirect /
 * SSI) where the time-frame is a row of mutually-exclusive pills.
 *
 * Renders nothing while the lakehouse only holds a single interval, since a
 * one-button "switcher" is just noise in the header.
 */
export function IntervalSwitcher({ busy, className }: IntervalSwitcherProps) {
  const { interval, setInterval } = useMarket();

  if (INTERVALS.length < 2) return null;

  return (
    <div
      role="group"
      aria-label="Interval"
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-card p-0.5",
        className,
      )}
    >
      {INTERVALS.map((key) => {
        const active = interval === key;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={active}
            onClick={() => setInterval(key)}
            disabled={busy}
            className={cn(
              "inline-flex min-w-[34px] items-center justify-center rounded px-2 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {busy && active ? (
              <Loader2 size={10} className="animate-spin" />
            ) : (
              LABELS[key] ?? key
            )}
          </button>
        );
      })}
    </div>
  );
}