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
 *
 * WHY IT IS DASHED AND NOT BORDERED: a solid border would make an empty
 * region look like a populated one. A dashed outline says "nothing here
 * yet" without needing a word to say it.
 */
export function EmptyState({ message, hint, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded border border-dashed border-hairline bg-surface-2/60 px-6 py-12 text-center",
        className,
      )}
    >
      <span className="text-muted">{icon ?? <FileSearch size={20} />}</span>
      <p className="text-small font-medium text-ink">{message}</p>
      {hint ? <p className="max-w-sm text-small text-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
