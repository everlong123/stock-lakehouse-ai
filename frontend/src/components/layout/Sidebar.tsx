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

const items = [
  { to: "/",            label: "Dashboard",          icon: LayoutDashboard, group: "Overview" },
  { to: "/market",      label: "Market Data",        icon: CandlestickChart, group: "Data" },
  { to: "/analysis",    label: "Technical Analysis", icon: Activity,        group: "Data" },
  { to: "/forecast",    label: "Forecasting",        icon: LineChart,       group: "Models" },
  { to: "/backtesting", label: "Backtesting",        icon: TestTubes,       group: "Models" },
  { to: "/agent",       label: "AI Agent",           icon: Waves,           group: "Agent" },
  { to: "/system",      label: "System Status",      icon: Server,          group: "Platform" },
];

export function Sidebar() {
  const groups = items.reduce<Record<string, typeof items>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-border bg-card md:flex md:flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-foreground text-background">
          <Database size={16} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-semibold leading-tight text-foreground">
            Stock Lakehouse
          </div>
          <div className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            AI / Medallion / VN
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
            <div className="font-semibold text-foreground">Prototype hoc thuat</div>
            Du lieu minh hoa. Khong dat lenh that.
          </div>
        </div>
      </div>
    </aside>
  );
}