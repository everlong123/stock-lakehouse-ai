import { cn } from "@/lib/utils";
import { changeClass } from "@/utils/format";

export interface KeyStat {
  label: string;
  value: string;
  /**
   * The direction of this number, used to COLOUR the value.
   *
   * WHY THIS IS A NUMBER AND NOT A LABEL: the caller already has the
   * signed number and wants the row to read "up" or "down" without
   * printing it a second time. A signed value and its colour are the
   * same fact, so this carries the direction and `value` carries the
   * digits.
   *
   * WHY IT IS NOT RENDERED AS TEXT: an earlier version printed
   * "+31.79%" next to a value that was already "31.79%", which produced
   * "31.79%+31.79%" - the same number twice, in two different styles.
   * Worse, a count like "up days" passed `tone: 1`, which printed
   * "+100.00%" next to the number of up days: a percentage invented out
   * of a direction flag.
   */
  tone?: number | null;
  /**
   * An explicit direction, for rows whose number is not a signed ratio.
   *
   * WHY THIS EXISTS NEXT TO `tone`: a count of up days is coloured by
   * direction but is NOT a signed number - it is not "+100%" of
   * anything. Passing `1` through `tone` would be a lie about the
   * quantity. This flag carries only the colour.
   */
  direction?: "up" | "down" | null;
  /** Extra explanation shown under the value. */
  hint?: string;
}

interface KeyStatisticsProps {
  title: string;
  stats: KeyStat[];
  className?: string;
}

/**
 * The key-statistics panel.
 *
 * WHY A DENSE TABLE AND NOT A GRID OF CARDS
 * -----------------------------------------
 * A quote page's statistics are read by COMPARING them — is the volume
 * above or below the average, is the RSI overbought, is the price near
 * the year's high. That is a tabular task: the eye moves down a column
 * and across a row, and the alignment has to hold for the comparison to
 * work.
 *
 * Cards break the alignment: each value floats in its own box with its
 * own padding, so two numbers that should be compared under each other
 * are not under each other. The rows here share one baseline and one
 * right-aligned numeric column, which is what makes the comparison
 * possible.
 *
 * WHY THE LABEL IS ON THE LEFT AND THE VALUE ON THE RIGHT: the labels
 * are words of varying length and the values are numbers of varying
 * length. Pinning the numbers to a single right edge is what makes the
 * decimals line up, and that is the whole point of the panel.
 */
export function KeyStatistics({ title, stats, className }: KeyStatisticsProps) {
  if (stats.length === 0) return null;

  return (
    <section className={cn("min-w-0", className)}>
      <div className="section-head">
        <h2 className="section-title">{title}</h2>
      </div>
      <dl className="mt-2">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="flex items-baseline justify-between gap-4 border-b border-hairline py-2 transition-colors last:border-b-0 hover:bg-surface-2/60"
          >
            <dt className="min-w-0 text-small text-muted">{stat.label}</dt>
            <dd className="flex shrink-0 items-baseline gap-2 text-right">
              <span
                className={cn(
                  "font-mono text-small font-semibold tabular-nums",
                  typeof stat.tone === "number"
                    ? changeClass(stat.tone)
                    : stat.direction === "up"
                      ? "text-up"
                      : stat.direction === "down"
                        ? "text-negative"
                        : "text-ink",
                )}
              >
                {stat.value}
              </span>
              {stat.hint ? (
                <span className="font-mono text-label text-muted">{stat.hint}</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
