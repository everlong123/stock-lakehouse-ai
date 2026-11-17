import { useState } from "react";
import { ChevronDown, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ExplainerItem {
  term: string;
  meaning: string;
}

export interface ExplainerProps {
  title: string;
  intro: string;
  items: ExplainerItem[];
  /** A short "what to do" list shown under the terms. */
  steps?: string[];
  className?: string;
}

/**
 * A collapsible plain-language explainer.
 *
 * WHY THIS EXISTS
 * ---------------
 * The forecasting and backtesting pages are dense with concepts that are
 * easy to get wrong: "hold-out", "MAE", "walk-forward", "slippage". A
 * newcomer staring at a chart of a dashed line has no way to tell which
 * part is history and which part is a claim about the future.
 *
 * So the page explains itself instead of making the reader go and look
 * the terms up. It is collapsed by default so it does not crowd the
 * actual results, but it is one click away.
 */
export function Explainer({
  title,
  intro,
  items,
  steps,
  className,
}: ExplainerProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("rounded border border-hairline bg-surface-2", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full min-h-11 items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-small font-semibold text-ink">
          <Lightbulb size={15} className="text-primary" />
          {title}
        </span>
        <ChevronDown
          size={15}
          className={cn("shrink-0 text-muted transition-transform", open && "rotate-180")}
        />
      </button>

      {open ? (
        <div className="space-y-6 border-t border-hairline px-4 py-4 text-small">
          <p className="max-w-3xl text-muted">{intro}</p>

          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {items.map((item) => (
              <div key={item.term} className="min-w-0">
                <dt className="font-semibold text-ink">{item.term}</dt>
                <dd className="mt-1 text-muted">{item.meaning}</dd>
              </div>
            ))}
          </dl>

          {steps?.length ? (
            <div>
              <div className="label mb-2">Cách dùng</div>
              <ol className="list-inside list-decimal space-y-1 text-muted">
                {steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
