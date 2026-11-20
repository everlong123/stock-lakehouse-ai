import { ChartLine, CandlestickChart as CandlestickIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type ChartView = "line" | "candle";

interface ChartViewToggleProps {
  value: ChartView;
  onChange: (next: ChartView) => void;
  className?: string;
}

/**
 * Switches the price chart between a line and candles.
 *
 * WHY THE TOGGLE EXISTS: the two views answer different questions. A
 * line answers "which way did it go", a candle answers "how did the
 * session itself unfold" — where it opened, how far it reached, and
 * where it settled. A reader comparing a forecast against the market
 * wants the first; a reader looking for a session's structure wants the
 * second.
 *
 * WHY THE ICONS ARE IN BUTTONS AND NOT A SELECT: two options do not
 * justify a dropdown, and an icon pair reads faster than two words.
 * Each button carries an accessible name so the control still works with
 * a screen reader.
 *
 * WHY THE ACTIVE STATE IS A TINT AND NOT A FILLED BLOCK: the toolbar
 * already has the range words with an accent underline. A solid accent
 * block here would be a second, heavier accent on the same line.
 */
export function ChartViewToggle({ value, onChange, className }: ChartViewToggleProps) {
  return (
    <div
      className={cn("inline-flex items-center gap-0.5 rounded border border-hairline p-0.5", className)}
      role="group"
      aria-label="Kiểu biểu đồ"
    >
      <button
        type="button"
        onClick={() => onChange("line")}
        aria-pressed={value === "line"}
        title="Biểu đồ đường"
        aria-label="Biểu đồ đường"
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded transition-colors",
          value === "line" ? "bg-primary/10 text-primary" : "text-muted hover:bg-surface-2 hover:text-ink",
        )}
      >
        <ChartLine size={15} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onChange("candle")}
        aria-pressed={value === "candle"}
        title="Biểu đồ nến"
        aria-label="Biểu đồ nến"
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded transition-colors",
          value === "candle" ? "bg-primary/10 text-primary" : "text-muted hover:bg-surface-2 hover:text-ink",
        )}
      >
        <CandlestickIcon size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
