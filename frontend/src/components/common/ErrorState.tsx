import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  className?: string;
}

/**
 * Inline error placeholder.
 *
 * WHY IT IS A HAIRLINE BAND AND NOT A FILLED BOX: a solid red block in
 * the middle of a page is louder than the error deserves and breaks the
 * reading flow. A thin band with a red icon says the same thing without
 * shouting.
 */
export function ErrorState({ message, onRetry, className }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded border border-negative/30 bg-negative/5 px-4 py-3 text-small text-negative",
        className,
      )}
    >
      <AlertCircle size={15} className="mt-1 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry ? (
        <Button variant="text" size="sm" onClick={onRetry}>
          <RotateCcw size={13} />
          Thó lỗi
        </Button>
      ) : null}
    </div>
  );
}
