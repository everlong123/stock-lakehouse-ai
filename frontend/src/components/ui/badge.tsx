import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Badge({
  variant = "default",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: "default" | "primary" | "outline" | "warn" }) {
  const styles = {
    default: "border border-border bg-muted text-muted-foreground",
    primary: "bg-brand-50 text-brand-700 border border-brand-200",
    outline: "border border-border bg-transparent text-foreground",
    warn: "border border-warn/40 bg-warn/10 text-warn",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}