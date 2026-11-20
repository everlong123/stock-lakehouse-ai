import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
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
 *
 * WHY THE OPTIONS ARE PLAIN WORDS: same reason as the range selector — a
 * timeframe is a target the reader aims at, not a field they fill in. A
 * bordered tray around three short words adds a box without adding meaning.
 */
export function BarIntervalSelector({
  value,
  onChange,
}: BarIntervalSelectorProps) {
  const { locale } = useI18n();
  const label = locale === "vi" ? "Gộp theo" : "Group by";
  const labels = locale === "vi"
    ? BAR_INTERVAL_LABELS
    : { "1d": "Day", "1w": "Week", "1mo": "Month" };

  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">{label}</legend>
      <div className="flex flex-wrap items-center gap-x-1">
        {INTERVALS.map((key) => {
          const active = key === value;
          return (
            <button
              key={key}
              aria-pressed={active}
              onClick={() => onChange(key)}
              type="button"
              className={cn(
                "relative min-h-9 whitespace-nowrap rounded px-2 text-small font-medium transition-colors",
                active ? "text-primary" : "text-muted hover:text-ink",
              )}
            >
              {labels[key]}
              {active ? (
                <span
                  aria-hidden="true"
                  className="absolute inset-x-1 -bottom-px h-0.5 rounded-full bg-primary"
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
