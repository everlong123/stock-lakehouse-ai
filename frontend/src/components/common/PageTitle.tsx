import { ReactNode } from "react";

interface PageTitleProps {
  title: string;
  subtitle?: string;
  badge?: string;
  actions?: ReactNode;
}

export function PageTitle({ title, subtitle, badge, actions }: PageTitleProps) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 animate-slide-up">
      <div>
        <div className="mb-1.5 flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            {title}
          </h1>
          {badge ? (
            <span className="chip-primary">{badge}</span>
          ) : null}
        </div>
        {subtitle ? (
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}