import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { isUsableNumber } from "@/utils/format";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: number | null;
  hint?: string;
}

/**
 * A single statistic.
 *
 * WHY THERE IS NO BOX AROUND IT
 * -----------------------------
 * This used to be a rounded card with a gradient top-border and a hover
 * shadow. Five of them in a row meant five boxes for five numbers — the
 * row stopped being read as data and started being read as widgets.
 *
 * A quote page's statistic row works the other way round: the numbers sit
 * on the page, separated by hairlines, and the row is divided from the
 * chart by a rule. There is no container because there is nothing to
 * contain — the value and its label are already visually a pair.
 *
 * The `border-l` divider is what carries the separation that the card
 * border used to, so the row still reads as one unit.
 */
export function MetricCard({ label, value, delta, hint }: MetricCardProps) {
  const [flashing, setFlashing] = useState(false);
  const prevValue = useRef<string>(value);

  // A delta that is not a usable number (null, undefined, NaN, Infinity)
  // means "there is no delta", not "the delta is zero".
  const hasDelta = isUsableNumber(delta);

  const trend =
    !hasDelta
      ? "neutral"
      : (delta as number) > 0
        ? "up"
        : (delta as number) < 0
          ? "down"
          : "neutral";

  // Flash when the value changes — this is the one animation that earns
  // its place: it tells you a tick just landed.
  useEffect(() => {
    if (prevValue.current !== value) {
      setFlashing(true);
      const t = setTimeout(() => setFlashing(false), 600);
      prevValue.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  return (
    <div className="group min-w-0 border-l border-hairline pl-4 transition-colors first:border-l-0 first:pl-0">
      <div className="label">{label}</div>
      <div
        className={cn(
          "mt-1 font-mono text-heading font-semibold tabular-nums text-ink transition-opacity",
          flashing ? "opacity-50" : "opacity-100",
        )}
      >
        {value}
      </div>
      {/* WHY THE ROW IS CONDITIONAL
          ---------------------------
          This row used to render unconditionally: a trend arrow plus the
          delta, with "—" standing in when there was no delta. Two problems
          came out of that. A metric with no delta (Sharpe, trade count,
          initial capital) showed a lone "—" that reads as "missing data"
          even though the value right above it is perfectly good. And where
          the caller passed the SAME number as both `value` and `delta` -
          the trend arrow and the value repeated each other, e.g.
          "320.05%" printed twice on the Total Return card.

          So the row only appears when there is something to put in it,
          and the delta is dropped when it would just repeat the value. */}
      {hasDelta || hint ? (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {hasDelta ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 font-mono text-label font-medium tabular-nums",
                trend === "up" && "text-up",
                trend === "down" && "text-negative",
                trend === "neutral" && "text-muted",
              )}
            >
              {trend === "up" && <ArrowUp size={11} />}
              {trend === "down" && <ArrowDown size={11} />}
              {trend === "neutral" && <Minus size={11} />}
              {/* A NaN or Infinity delta used to render the literal text
                  "NaN%" here: the old check only null-tested, and `NaN >= 0` is
                  false, so it skipped the "+" and printed the raw value. */}
              {`${(delta as number) >= 0 ? "+" : ""}${((delta as number) * 100).toFixed(2)}%`}
            </span>
          ) : null}
          {hint ? (
            <span className="truncate text-label text-muted">{hint}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
