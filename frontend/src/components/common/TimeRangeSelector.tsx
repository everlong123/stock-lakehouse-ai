import { cn } from "@/lib/utils";

export type TimeRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

const RANGES: TimeRange[] = ["1M", "3M", "6M", "1Y", "ALL"];

const LABELS: Record<TimeRange, string> = {
  "1M": "1T",
  "3M": "3T",
  "6M": "6T",
  "1Y": "1N",
  ALL: "Tất cả",
};

/**
 * Range picker: how far back to look.
 *
 * WHY THIS IS A SEGMENTED CONTROL AND NOT A SELECT: the five options are
 * the primary axis of the dashboard and are worth showing at once. A
 * dropdown would hide the choice behind a click and make the chart's
 * window ambiguous.
 */
export function TimeRangeSelector({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (next: TimeRange) => void;
}) {
  return (
    <div role="tablist" aria-label="Khoảng thời gian" className="segmented">
      {RANGES.map((r) => {
        const active = r === value;
        return (
          <button
            key={r}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(r)}
            type="button"
            className={cn("segmented-item", active && "bg-primary text-on-primary")}
          >
            {LABELS[r]}
          </button>
        );
      })}
    </div>
  );
}
