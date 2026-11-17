import { cn } from "@/lib/utils";
import { BAR_INTERVAL_LABELS, type BarInterval } from "@/utils/resample";

const INTERVALS: BarInterval[] = ["1d", "1w", "1mo"];

interface BarIntervalSelectorProps {
  value: BarInterval;
  onChange: (next: BarInterval) => void;
}

/**
 * Timeframe picker: one bar per day, per week, or per month.
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
}: BarIntervalSelectorProps) {
  return (
    <div role="tablist" aria-label="Khung thời gian" className="segmented">
      {INTERVALS.map((key) => {
        const active = key === value;
        return (
          <button
            key={key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(key)}
            type="button"
            className={cn("segmented-item", active && "bg-primary text-on-primary")}
          >
            {BAR_INTERVAL_LABELS[key]}
          </button>
        );
      })}
    </div>
  );
}
