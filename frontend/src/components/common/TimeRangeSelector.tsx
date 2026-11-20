import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export type TimeRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

const RANGES: TimeRange[] = ["1M", "3M", "6M", "1Y", "ALL"];

const LABELS: Record<TimeRange, string> = {
  "1M": "1 tháng",
  "3M": "3 tháng",
  "6M": "6 tháng",
  "1Y": "1 năm",
  ALL: "Tất cả",
};

/**
 * Range picker: how far back to look.
 *
 * WHY THIS IS A ROW OF PLAIN WORDS AND NOT A BOXED SEGMENT
 * -------------------------------------------------------
 * A bordered segmented control is a form widget — it says "this is a
 * setting you fill in". But the range is not a setting: it is the single
 * most-used control on a quote page, the one the reader reaches for
 * constantly to change the chart's window, and it deserves to read as a
 * row of targets rather than as a dropdown in a tray.
 *
 * So the options are bare words separated by space, and the active one is
 * the accent colour with an underline. The underline is what makes the
 * current window legible at a glance without drawing a filled box that
 * would compete with the chart below it.
 *
 * WHY THE LABELS ARE WRITTEN OUT AND NOT ABBREVIATED: "1M" is ambiguous
 * in a Vietnamese interface — it could be a million or a month. "1 tháng"
 * removes the ambiguity, and these are short enough to fit.
 */
export function TimeRangeSelector({
  value,
  onChange,
  className,
}: {
  value: TimeRange;
  onChange: (next: TimeRange) => void;
  className?: string;
}) {
  const { locale } = useI18n();
  const label = locale === "vi" ? "Khoảng xem" : "Date range";
  const labels = locale === "vi"
    ? LABELS
    : { "1M": "1 month", "3M": "3 months", "6M": "6 months", "1Y": "1 year", ALL: "All" };

  return (
    <fieldset className={cn("min-w-0", className)}>
      <legend className="sr-only">{label}</legend>
      <div className="flex flex-wrap items-center gap-x-1">
        {RANGES.map((r) => {
          const active = r === value;
          return (
            <button
              key={r}
              aria-pressed={active}
              onClick={() => onChange(r)}
              type="button"
              className={cn(
                "relative min-h-9 whitespace-nowrap rounded px-2 text-small font-medium transition-colors",
                active ? "text-primary" : "text-muted hover:text-ink",
              )}
            >
              {labels[r]}
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
