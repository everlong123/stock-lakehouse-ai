import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoadingProps {
  label?: string;
  variant?: "spinner" | "skeleton";
  className?: string;
}

/**
 * Loading indicator with two variants:
 * - "spinner" (default): inline spinner + label, used in compact cards.
 * - "skeleton": shimmer bars, used for chart / table placeholders so the
 *   layout does not jump when real data lands.
 *
 * Default label is in Vietnamese ("Đang tải dữ liệu…").
 */
export function Loading({
  label = "Đang tải dữ liệu…",
  variant = "spinner",
  className,
}: LoadingProps) {
  if (variant === "skeleton") {
    return (
      <div className={cn("flex w-full flex-col gap-2", className)} aria-busy="true">
        <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
      </div>
    );
  }
  return (
    <div
      className={cn(
        "flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground",
        className,
      )}
      aria-busy="true"
    >
      <Loader2 size={14} className="animate-spin" />
      <span>{label}</span>
    </div>
  );
}
