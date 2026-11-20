import { ReactNode } from "react";

interface PageHeaderProps {
  /** The section this page belongs to, e.g. "Dữ liệu", "Mô hình". */
  section?: string;
  title: string;
  subtitle?: string;
  /** A badge or chip that names the page's subject, e.g. the symbol. */
  aside?: ReactNode;
  actions?: ReactNode;
}

/**
 * The page header.
 *
 * WHY THE SECTION CAPTION: the navigation is grouped into three clusters
 * (data / models / tools) and this caption tells the reader which one
 * they are inside. It is the same 12px uppercase mono label the nav bar
 * uses for its cluster captions, so the page header and the nav bar read
 * as one system rather than as two decorations that happen to look alike.
 *
 * WHY THE SUBTITLE IS MUTED AND SHORT: it is context, not content. If it
 * needs two sentences it belongs in the body, not under the title.
 *
 * WHY NO CARD AROUND IT: a page title sitting in a bordered box is the
 * single most common "AI generated" tell. A title, one line of context
 * and a hairline is enough — the hairline is what separates the header
 * from the content, and it costs 1px instead of a whole box.
 */
export function PageHeader({
  section,
  title,
  subtitle,
  aside,
  actions,
}: PageHeaderProps) {
  return (
    <div className="section-head">
      <div className="min-w-0">
        {section ? (
          <div className="mb-2 font-mono text-label uppercase text-muted">{section}</div>
        ) : null}
        <h1 className="font-display text-heading text-ink">{title}</h1>
        {subtitle ? (
          <p className="section-sub max-w-3xl">{subtitle}</p>
        ) : null}
      </div>
      {aside || actions ? (
        <div className="flex items-center gap-3">
          {aside}
          {actions}
        </div>
      ) : null}
    </div>
  );
}
