import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Badge ? the small uppercase chip that tags a value's state.
 *
 * WHY ONLY TWO COLOURS: a badge that carries meaning uses `primary` (live,
 * active, good) or `negative` (failed, falling). Everything else is a
 * neutral tag with no semantic weight and stays `muted`. A badge palette
 * of five colours turns every chip into a competing accent.
 *
 * WHY THERE IS A SEPARATE `up` VARIANT: `primary` is the app's own
 * accent (the logo, the active tab, the primary button). A badge that
 * says "this trade closed up" is a DIRECTION, not an app state, so it
 * takes the direction colour - the same blue the candle chart uses for a
 * rising bar. One meaning, one colour, everywhere.
 */
export function Badge({
  variant = "default",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "primary" | "negative" | "up";
}) {
  const styles = {
    default: "border border-hairline bg-surface-2 text-muted",
    primary: "border border-primary/30 bg-primary/10 text-primary",
    negative: "border border-negative/30 bg-negative/10 text-negative",
    up: "border border-up/30 bg-up/10 text-up",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-label font-medium uppercase",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}
