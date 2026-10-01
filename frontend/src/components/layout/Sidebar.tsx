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
  { to: "/",            label: "Dashboard",          icon: LayoutDashboard, group: "OVERVIEW" },
  { to: "/market",      label: "Market Data",        icon: CandlestickChart, group: "DATA" },
  { to: "/analysis",    label: "Technical Analysis", icon: Activity,        group: "DATA" },
  { to: "/forecast",    label: "Forecasting",        icon: LineChart,       group: "ML" },
  { to: "/backtesting", label: "Backtesting",        icon: TestTubes,       group: "ML" },
  { to: "/agent",       label: "AI Agent",           icon: Waves,           group: "AI" },
  { to: "/system",      label: "System Status",      icon: Server,          group: "PLATFORM" },
];

export function Sidebar() {
  // Group items
  const groups = items.reduce<Record<string, typeof items>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-border bg-card/70 backdrop-blur md:flex md:flex-col">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-border px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-glow">
          <Database size={20} />
        </div>
        <div>
          <div className="text-[15px] font-bold leading-tight text-gradient">
            Stock Lakehouse
          </div>
          <div className="text-[11px] font-medium text-muted-foreground">
            AI · Medallion · Vietnam
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-3">
        {Object.entries(groups).map(([group, groupItems]) => (
          <div key={group} className="mb-3">
            <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
              {group}
            </div>
            {groupItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    isActive
                      ? "bg-brand-50 text-brand-700 shadow-soft"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon
                      size={16}
                      className={cn(
                        "transition-transform group-hover:scale-110",
                        isActive ? "text-brand-600" : "text-muted-foreground",
                      )}
                    />
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Footer disclaimer */}
      <div className="border-t border-border p-4">
        <div className="rounded-lg bg-muted/70 p-3 text-[11px] leading-relaxed text-muted-foreground">
          <div className="mb-1 flex items-center gap-1.5 font-semibold text-foreground">
            <Bot size={12} className="text-brand-600" />
            Prototype học thuật
          </div>
          Dữ liệu minh hoạ. Không đặt lệnh thật. Không cam kết lợi nhuận.
        </div>
      </div>
    </aside>
  );
}