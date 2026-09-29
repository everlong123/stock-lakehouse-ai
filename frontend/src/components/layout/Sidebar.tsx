import { NavLink } from "react-router-dom";
import { Activity, Bot, CandlestickChart, LayoutDashboard, LineChart, Server, TestTubes } from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/market", label: "Market Data", icon: CandlestickChart },
  { to: "/analysis", label: "Technical Analysis", icon: Activity },
  { to: "/forecast", label: "Forecasting", icon: LineChart },
  { to: "/backtesting", label: "Backtesting", icon: TestTubes },
  { to: "/agent", label: "AI Agent", icon: Bot },
  { to: "/system", label: "System Status", icon: Server },
];

export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-border bg-card/60 md:flex md:flex-col">
      <div className="border-b border-border px-5 py-5">
        <div className="text-base font-semibold tracking-tight">Stock Lakehouse AI</div>
        <div className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground">
          Data • ML • Deep Learning • Agent
        </div>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
              )
            }
          >
            <item.icon size={16} />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border p-4 text-[11px] leading-relaxed text-muted-foreground">
        Prototype học thuật. Không đặt lệnh thật. Không cam kết lợi nhuận.
      </div>
    </aside>
  );
}
