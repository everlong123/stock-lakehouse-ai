import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Badge({
  variant = "default",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: "default" | "primary" | "outline" | "warn" | "success" | "danger" }) {
  const styles = {
    default: "border border-border bg-muted text-muted-foreground",
    primary: "border border-primary/30 bg-primary/10 text-primary",
    outline: "border border-border bg-transparent text-foreground",
    warn:    "border border-warn/30 bg-warn/10 text-warn",
    success: "border border-up/30 bg-up/10 text-up",
    danger:  "border border-down/30 bg-down/10 text-down",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}