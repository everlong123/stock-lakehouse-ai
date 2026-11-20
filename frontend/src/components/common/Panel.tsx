import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  children: ReactNode;
  className?: string;
  /**
   * `flat` for a region that only needs a boundary, `raised` for a block
   * of data the reader is meant to focus on.
   */
  tone?: "flat" | "raised";
}

/**
 * The one container primitive.
 *
 * WHY THERE IS A PANEL PRIMITIVE AT ALL
 * -------------------------------------
 * The previous design system had exactly one container (`rounded border
 * bg-surface`) and used it for everything, so a page full of regions read
 * as a page full of identical flat rectangles. This app is dense with
 * data — charts, tables, statistic rows — and identical flat boxes make
 * a dense screen hard to scan.
 *
 * Two tones, and the difference is deliberate:
 *
 *   `flat`   — a hairline boundary, no shadow. For a region that only
 *              needs to be separated from what is around it.
 *   `raised` — a boundary PLUS a shadow. For a block the reader is meant
 *              to look AT: a chart, a table of results, a key figure.
 *
 * WHY SHADOWS AT ALL, WHEN THE OLD SYSTEM BANNED THEM
 * ---------------------------------------------------
 * A shadow on a light canvas is a lie unless it is very light: black at
 * any real opacity turns grey and muddy. The four shadow steps here are
 * all under 15% opacity and are tuned so the panel appears to float a
 * millimetre above the canvas rather than to be stamped on it. That is
 * the difference between "this is a card" and "this is a table pasted
 * onto the screen".
 */
export function Panel({ children, className, tone = "flat" }: PanelProps) {
  return (
    <div
      className={cn(
        "rounded border border-hairline bg-surface",
        tone === "raised" && "shadow-sm",
        className,
      )}
    >
      {children}
    </div>
  );
}
