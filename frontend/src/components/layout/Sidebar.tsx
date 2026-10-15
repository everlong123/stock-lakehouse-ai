import { NavLink } from "react-router-dom";
import {
  Activity,
  Bot,
  CandlestickChart,
  Database,
  LayoutDashboard,
  LineChart,
  Radio,
  Server,
  TestTubes,
  Waves,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n, t } from "@/lib/i18n";

const ITEMS = [
  { to: "/",            labelKey: "nav.dashboard",    icon: LayoutDashboard, groupKey: "nav.overview"  },
  { to: "/market",      labelKey: "nav.market",       icon: CandlestickChart, groupKey: "nav.data"     },
  { to: "/analysis",    labelKey: "nav.analysis",     icon: Activity,        groupKey: "nav.data"     },
  { to: "/forecast",    labelKey: "nav.forecast",     icon: LineChart,       groupKey: "nav.models"   },
  { to: "/backtesting", labelKey: "nav.backtesting",  icon: TestTubes,       groupKey: "nav.models"   },
  { to: "/stream",      labelKey: "nav.stream",       icon: Radio,           groupKey: "nav.agent"    },
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
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 md:flex md:flex-col">
      {/* Gradient glass background */}
      <div
        className="absolute inset-0 rounded-r-2xl"
        style={{
          background: "linear-gradient(180deg, hsl(0 0% 100% / 0.95) 0%, hsl(210 20% 97% / 0.98) 100%)",
          backdropFilter: "blur(20px) saturate(180%)",
          WebkitBackdropFilter: "blur(20px) saturate(180%)",
        }}
      />
      {/* Left accent bar */}
      <div
        className="absolute left-0 top-0 h-full w-[2px] rounded-r"
        style={{
          background: "linear-gradient(180deg, hsl(165 52% 28%) 0%, hsl(165 52% 28% / 0.3) 60%, transparent 100%)",
        }}
      />

      {/* Content */}
      <div className="relative z-10 flex h-full flex-col">
        {/* Logo / Brand */}
        <div
          className="flex items-center gap-3 border-b border-border px-5 py-5"
          style={{ borderColor: "hsl(210 18% 90% / 0.6)" }}
        >
          <div
            className="flex h-10 w-10 items-center justify-center rounded-xl shadow-sm"
            style={{
              background: "linear-gradient(135deg, hsl(165 52% 28%) 0%, hsl(165 60% 35%) 100%)",
              boxShadow: "0 2px 8px -2px hsl(165 52% 28% / 0.4)",
            }}
          >
            <Database size={18} className="text-white" />
          </div>
          <div className="min-w-0">
            <div className="truncate font-semibold leading-tight text-foreground" style={{ fontSize: 15 }}>
              {t("app.title", locale)}
            </div>
            <div
              className="truncate font-mono uppercase tracking-widest"
              style={{ fontSize: 9, color: "hsl(220 12% 45%)" }}
            >
              {t("app.subtitle", locale)}
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {Object.entries(groups).map(([group, groupItems]) => (
            <div key={group} className="mb-4">
              {/* Group label */}
              <div
                className="mb-2 px-3 font-mono uppercase tracking-widest"
                style={{ fontSize: 9, color: "hsl(220 12% 55%)", letterSpacing: "0.12em" }}
              >
                {group}
              </div>

              {/* Nav items */}
              {groupItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  style={({ isActive }) =>
                    isActive
                      ? {
                          background: "linear-gradient(135deg, hsl(165 52% 28%) 0%, hsl(165 60% 38%) 100%)",
                          boxShadow: "0 1px 3px hsl(165 52% 28% / 0.3)",
                        }
                      : { background: "transparent" }
                  }
                  className={({ isActive }) =>
                    cn(
                      "group relative mb-1 flex items-center gap-3 rounded-xl px-3 py-2.5",
                      "font-medium transition-all duration-200",
                      isActive
                        ? "shadow-sm"
                        : "text-[hsl(220_25%_35%)] hover:text-[hsl(220_25%_15%)] hover:bg-[hsl(165_40%/8%)]",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {/* Active left indicator */}
                      {isActive && (
                        <div
                          className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full"
                          style={{ background: "white" }}
                        />
                      )}

                      <item.icon
                        size={16}
                        className={cn(
                          "shrink-0 transition-colors duration-200",
                          isActive ? "text-white" : "text-[hsl(220_12%_50%)] group-hover:text-[hsl(165_52%_30%)]",
                        )}
                      />

                      <span
                        className={cn(
                          "truncate text-[13px] transition-colors duration-200",
                          isActive ? "font-semibold text-white" : "text-[hsl(220_25%_35%)]",
                        )}
                      >
                        {item.label}
                      </span>

                      {/* Hover arrow */}
                      {!isActive && (
                        <span className="ml-auto opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "hsl(165 52% 40%)" }} />
                          </svg>
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Disclaimer footer */}
        <div
          className="mx-3 mb-4 rounded-xl p-3"
          style={{
            background: "linear-gradient(135deg, hsl(165 52% 28% / 0.06) 0%, hsl(165 40% 95% / 0.4) 100%)",
            border: "1px solid hsl(165 40% 90% / 0.6)",
          }}
        >
          <div className="flex items-start gap-2">
            <Bot size={12} className="mt-0.5 shrink-0" style={{ color: "hsl(165 52% 30%)" }} />
            <div>
              <div
                className="mb-0.5 font-semibold leading-snug"
                style={{ fontSize: 11, color: "hsl(165 52% 22%)" }}
              >
                {t("app.disclaimer_title", locale)}
              </div>
              <div className="leading-relaxed" style={{ fontSize: 10, color: "hsl(220 12% 50%)" }}>
                {t("app.disclaimer_body", locale)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
