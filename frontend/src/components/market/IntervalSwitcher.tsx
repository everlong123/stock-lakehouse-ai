import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMarket } from "@/hooks/useMarket";
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
 * Renders nothing while the lakehouse only holds a single interval, since a
 * one-button "switcher" is just noise in the header.
 */
export function IntervalSwitcher({ busy, className }: IntervalSwitcherProps) {
  const { interval, setInterval } = useMarket();

  if (INTERVALS.length < 2) return null;

  return (
    <div role="group" aria-label="Interval" className={cn("segmented", className)}>
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
              "segmented-item min-w-9 text-center disabled:cursor-not-allowed disabled:opacity-40",
              active && "bg-primary text-on-primary",
            )}
          >
            {busy && active ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              LABELS[key] ?? key
            )}
          </button>
        );
      })}
    </div>
  );
}
