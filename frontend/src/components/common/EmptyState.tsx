import type { ReactNode } from "react";
import { FileSearch } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  message: string;
  hint?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * Inline placeholder shown when a list / chart has no data yet.
 * Default copy is in Vietnamese; English technical terms (RSI, MAE, …)
 * are passed in via the `message` prop by the caller.
 */
export function EmptyState({ message, hint, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/40 px-6 py-10 text-center",
        className,
      )}
    >
      <span className="text-muted-foreground">{icon ?? <FileSearch size={20} />}</span>
      <p className="text-sm font-medium text-foreground">{message}</p>
      {hint ? <p className="max-w-sm text-[12px] text-muted-foreground">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
