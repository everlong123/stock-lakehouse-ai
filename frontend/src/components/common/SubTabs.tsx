import { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SubTab {
  id: string;
  label: string;
  /** A short note shown under the label. */
  hint?: string;
}

interface SubTabsProps<T extends string> {
  tabs: Array<SubTab & { id: T }>;
  active: T;
  onChange: (id: T) => void;
  /** Rendered on the right of the tab row. */
  aside?: ReactNode;
  className?: string;
}

/**
 * The sub-navigation inside a page.
 *
 * WHY THE TABS ARE UNDERLINED AND NOT FILLED
 * --------------------------------------------
 * A filled block on the active tab is the loudest thing on the screen,
 * and the screen already has a filled accent somewhere else (the price,
 * the primary button). An underline says "you are here" just as clearly
 * and stays quiet, which is what lets the tab row sit above a chart
 * without competing with it.
 *
 * WHY THE COUNT IS SHOWN NEXT TO EACH LABEL
 * ------------------------------------------
 * A reader choosing between "Prices" and "Forecast" wants to know
 * which one has something in it before they click. The count answers
 * that without a click, and it is a fact from the data — never a
 * placeholder.
 */
export function SubTabs<T extends string>({ tabs, active, onChange, aside, className }: SubTabsProps<T>) {
  return (
    <div
      role="tablist"
      className={cn(
        "flex items-center justify-between gap-4 border-b border-hairline",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(tab.id)}
              className={cn(
                "group relative flex min-h-11 shrink-0 flex-col justify-center px-3 text-left transition-colors",
                selected ? "text-ink" : "text-muted hover:text-ink",
              )}
            >
              <span
                className={cn(
                  "whitespace-nowrap text-small transition-colors",
                  selected && "font-semibold",
                )}
              >
                {tab.label}
              </span>
              {tab.hint ? (
                <span
                  className={cn(
                    "font-mono text-label transition-colors",
                    selected ? "text-primary" : "text-muted",
                  )}
                >
                  {tab.hint}
                </span>
              ) : null}
              {/*
                The active rule. It grows out from the centre on the
                first paint of the page and then stays put, so it is a
                state change rather than a decoration.
              */}
              <span
                aria-hidden="true"
                className={cn(
                  "absolute inset-x-2 bottom-[-1px] h-0.5 rounded-full bg-primary transition-transform duration-200 ease-out",
                  selected ? "scale-x-100" : "scale-x-0",
                )}
              />
            </button>
          );
        })}
      </div>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </div>
  );
}
