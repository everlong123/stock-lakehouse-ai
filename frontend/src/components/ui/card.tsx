import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Cards.
 *
 * WHY THE `panel` PRIMITIVE IS DELIBERATELY PLAIN: a card here is a
 * bordered region on a light canvas. Hairline border, 6px radius, no
 * shadow. Anything that needs to float (a dropdown, a popover) uses
 * `shadow-popover` — that is the only shadow in the system.
 */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded border border-hairline bg-surface", className)} {...props} />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border-b border-hairline px-4 py-3",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("font-display text-body font-semibold text-ink", className)} {...props} />
  );
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 py-4", className)} {...props} />;
}
