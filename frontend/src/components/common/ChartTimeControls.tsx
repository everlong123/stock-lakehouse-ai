import { BarIntervalSelector } from "@/components/common/BarIntervalSelector";
import { TimeRangeSelector, type TimeRange } from "@/components/common/TimeRangeSelector";
import { useI18n } from "@/lib/i18n";
import { tradingDay } from "@/utils/format";
import type { BarInterval } from "@/utils/resample";

interface ChartTimeControlsProps {
  barInterval: BarInterval;
  onBarIntervalChange: (value: BarInterval) => void;
  range: TimeRange;
  onRangeChange: (value: TimeRange) => void;
  dailyPoints: Array<{ timestamp: string }>;
  barCount: number;
  /** Extra controls rendered on the right of the toolbar. */
  children?: React.ReactNode;
}

/**
 * The chart toolbar: the window, the granularity, and a coverage readout.
 *
 * WHY THE TWO SELECTORS SIT ON ONE LINE AND NOT IN TWO BOXES: they are
 * one control conceptually — "how much history, at what zoom" — and the
 * reader changes them together. Splitting them into separate boxed
 * widgets made the chart look like it had two settings panels instead of
 * one toolbar.
 *
 * WHY THE COVERAGE READOUT IS KEPT: it states exactly which sessions are
 * on screen and how many points were drawn. A chart that silently dropped
 * rows (duplicate sessions, unusable prices) would otherwise look
 * complete, so the count is the reader's check on it.
 *
 * WHY THE READOUT SITS BELOW THE CONTROLS ON A NARROW SCREEN: the
 * counts are a footnote, and on a phone the controls need the whole
 * width. The toolbar is `flex-wrap`, so the readout drops to its own
 * line instead of squeezing the buttons.
 */
export function ChartTimeControls({
  barInterval,
  onBarIntervalChange,
  range,
  onRangeChange,
  dailyPoints,
  barCount,
  children,
}: ChartTimeControlsProps) {
  const { locale } = useI18n();
  const first = dailyPoints[0];
  const last = dailyPoints.at(-1);

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-hairline py-2">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <TimeRangeSelector value={range} onChange={onRangeChange} />
        <span aria-hidden="true" className="hidden h-4 w-px bg-hairline sm:block" />
        <BarIntervalSelector value={barInterval} onChange={onBarIntervalChange} />
      </div>

      {children}

      <p
        aria-live="polite"
        aria-atomic="true"
        className="w-full font-mono text-label text-muted sm:w-auto"
      >
        {first && last
          ? `${tradingDay(first.timestamp)} → ${tradingDay(last.timestamp)} · ${dailyPoints.length.toLocaleString()} ${locale === "vi" ? "phiên" : "sessions"} · ${barCount.toLocaleString()} ${locale === "vi" ? "điểm" : "points"}`
          : (locale === "vi" ? "Không có phiên trong khoảng xem." : "No sessions in this range.")}
      </p>
    </div>
  );
}
