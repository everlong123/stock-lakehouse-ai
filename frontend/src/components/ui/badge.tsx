import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Badge ? the small uppercase chip that tags a value's state.
 *
 * WHY ONLY TWO COLOURS: a badge that carries meaning uses `primary` (live,
 * active, good) or `negative` (failed, falling). Everything else is a
 * neutral tag with no semantic weight and stays `muted`. A badge palette
 * of five colours turns every chip into a competing accent.
 */
export function Badge({
  variant = "default",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "primary" | "negative";
}) {
  const styles = {
    default: "border border-hairline bg-surface-2 text-muted",
    primary: "border border-primary/30 bg-primary/10 text-primary",
    negative: "border border-negative/30 bg-negative/10 text-negative",
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
