import { NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  CandlestickChart,
  Database,
  LayoutDashboard,
  LineChart,
  Server,
  TestTubes,
  Waves,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n, t } from "@/lib/i18n";

const ITEMS = [
  { to: "/",            labelKey: "nav.dashboard",    icon: LayoutDashboard, groupKey: "nav.overview" },
  { to: "/market",      labelKey: "nav.market",       icon: CandlestickChart, groupKey: "nav.data"     },
  { to: "/analysis",    labelKey: "nav.analysis",     icon: Activity,        groupKey: "nav.data"     },
  { to: "/forecast",    labelKey: "nav.forecast",     icon: LineChart,       groupKey: "nav.models"   },
  { to: "/backtesting", labelKey: "nav.backtesting",  icon: TestTubes,       groupKey: "nav.models"   },
  { to: "/agent",       labelKey: "nav.agent_full",   icon: Waves,           groupKey: "nav.agent"    },
  { to: "/system",      labelKey: "nav.system",       icon: Server,          groupKey: "nav.platform" },
];

export function Sidebar() {
  const { locale } = useI18n();
  const items = ITEMS.map((item) => ({
    to: item.to,
    icon: item.icon,
    group: t(item.groupKey, locale),
    label: t(item.labelKey, locale),
  }));
  const groups = items.reduce<Record<string, typeof items>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-border bg-card md:flex md:flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Database size={16} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-semibold leading-tight text-foreground">
            {t("app.title", locale)}
          </div>
          <div className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("app.subtitle", locale)}
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {Object.entries(groups).map(([group, groupItems]) => (
          <div key={group} className="mb-2">
            <div className="px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {group}
            </div>
            {groupItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-1.5 text-[13px] font-medium",
                    isActive
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )
                }
              >
                <item.icon
                  size={15}
                  className={cn(
                    "shrink-0",
                    "text-muted-foreground",
                  )}
                />
                <span className="truncate">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-start gap-2 rounded-md bg-muted px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
          <Bot size={12} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold text-foreground">
              {t("app.disclaimer_title", locale)}
            </div>
            {t("app.disclaimer_body", locale)}
          </div>
        </div>
      </div>
    </aside>
  );
}