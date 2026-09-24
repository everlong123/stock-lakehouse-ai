import { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-md border border-border bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
