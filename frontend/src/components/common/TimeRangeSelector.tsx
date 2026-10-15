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
 * Compact 1M/3M/6M/1Y/All range pill group, Vietnamese-first.
 * Returns the selected range; parents derive a cutoff timestamp themselves.
 */
export function TimeRangeSelector({
  value,
  onChange,
  size = "sm",
}: {
  value: TimeRange;
  onChange: (next: TimeRange) => void;
  size?: "sm" | "md";
}) {
  return (
    <div
      role="tablist"
      aria-label="Khoảng thời gian"
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-card p-0.5",
      )}
    >
      {RANGES.map((r) => {
        const active = r === value;
        return (
          <button
            key={r}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(r)}
            type="button"
            className={cn(
              "rounded font-mono uppercase tracking-wider transition-colors",
              size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-3 py-1 text-[11px]",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {LABELS[r]}
          </button>
        );
      })}
    </div>
  );
}
