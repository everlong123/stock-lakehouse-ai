import { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded border border-hairline bg-surface px-2 text-small text-ink outline-none transition-colors focus:border-primary",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
