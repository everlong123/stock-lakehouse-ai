import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

/**
 * Inline error placeholder. Message is rendered in Vietnamese with English
 * technical terms (API, 500, …) preserved. The optional retry button keeps
 * the user in the flow instead of forcing a hard reload.
 */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-down/30 bg-down/5 px-3 py-2 text-sm text-down">
      <AlertCircle size={14} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <span>{message}</span>
      </div>
      {onRetry ? (
        <Button variant="ghost" size="sm" onClick={onRetry}>
          <RotateCcw size={12} />
          Thử lại
        </Button>
      ) : null}
    </div>
  );
}
