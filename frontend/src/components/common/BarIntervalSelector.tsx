import { cn } from "@/lib/utils";
import { BAR_INTERVAL_LABELS, type BarInterval } from "@/utils/resample";

const INTERVALS: BarInterval[] = ["1d", "1w", "1mo"];

interface BarIntervalSelectorProps {
  value: BarInterval;
  onChange: (next: BarInterval) => void;
  size?: "sm" | "md";
}

/**
 * Timeframe (granularity) selector: daily / weekly / monthly bars.
 *
 * WHY THIS IS SEPARATE FROM `TimeRangeSelector`
 * ----------------------------------------------
 * The range selector answers "HOW FAR BACK?" (1 month, 3 months, all). This
 * one answers "HOW GRANULAR?" (one bar per day, per week, per month). They
 * are independent axes: "all + monthly" is a 10-year monthly chart, "all +
 * daily" is 2500 daily bars. Before this existed the dashboard only had the
 * first axis, so widening the window always produced an unreadable pile of
 * daily candles.
 *
 * The lakehouse only stores daily bars, so the coarser granularities are
 * derived on the client from the daily bars the API already returns - no new
 * endpoint, no extra storage.
 */
export function BarIntervalSelector({
  value,
  onChange,
  size = "sm",
}: BarIntervalSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Khung thời gian"
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-card p-0.5",
      )}
    >
      {INTERVALS.map((key) => {
        const active = key === value;
        return (
          <button
            key={key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(key)}
            type="button"
            className={cn(
              "rounded font-mono uppercase tracking-wider transition-colors",
              size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-3 py-1 text-[11px]",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {BAR_INTERVAL_LABELS[key]}
          </button>
        );
      })}
    </div>
  );
}
