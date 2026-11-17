import { ReactNode } from "react";

interface PageTitleProps {
  title: string;
  subtitle?: string;
  meta?: string;
  actions?: ReactNode;
}

/**
 * The page header.
 *
 * WHY NO CARD AROUND IT: a page title sitting in a bordered box is the
 * single most common "AI generated" tell. A title, one line of context
 * and a hairline is enough — the hairline is what separates the header
 * from the content, and it costs 1px instead of a whole box.
 *
 * WHY THE SUBTITLE IS MUTED AND SHORT: it is context, not content. If it
 * needs two sentences it belongs in the body, not under the title.
 */
export function PageTitle({ title, subtitle, meta, actions }: PageTitleProps) {
  return (
    <div className="section-head mb-8">
      <div className="min-w-0">
        {meta ? (
          <div className="mb-2 font-mono text-label uppercase text-muted">{meta}</div>
        ) : null}
        <h1 className="font-display text-heading text-ink">{title}</h1>
        {subtitle ? (
          <p className="section-sub max-w-3xl">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
    </div>
  );
}
