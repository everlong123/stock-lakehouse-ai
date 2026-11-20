import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  ChartCandlestick,
  ChartNoAxesCombined,
  ChevronDown,
  FlaskConical,
  LayoutDashboard,
  Server,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n, t } from "@/lib/i18n";

/**
 * The section navigation.
 *
 * WHY ONE FLAT ROW AND NOT THREE CAPTIONED CLUSTERS
 * ---------------------------------------------------
 * The previous bar carried a 12px uppercase caption above each group
 * ("Dữ liệu", "Mô hình", "Công cụ"), which made the bar two levels
 * deep: a caption, then links, then an icon. A reader looking for
 * "Forecast" had to read a caption first to learn which group it
 * belonged to — information the caption only supplied because the
 * labels had been made cryptic.
 *
 * Every big finance site solves this the same way: a flat row of
 * destination names, with the active one underlined. The groups are
 * still there, but they are expressed by a hairline between them rather
 * than by a label above them, so the bar reads as ONE list of places
 * instead of a sitemap of sections.
 *
 * WHY THE LABELS STAY FULL WORDED: "Dự báo" and "Chiến lược" are
 * shorter than "Forecasts" and "Strategies", but the pair reads as one
 * thing at a glance, which is what a flat row needs.
 *
 * WHY THE MOBILE VERSION IS AN ACCORDION: on a narrow screen seven
 * destinations cannot sit on one line without the type dropping below
 * the readable floor, so they fold under the current page's name.
 */
const LINKS = [
  { to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/market", labelKey: "nav.market", icon: ChartCandlestick },
  { to: "/analysis", labelKey: "nav.analysis", icon: Activity },
  { to: "/forecast", labelKey: "nav.forecast", icon: ChartNoAxesCombined },
  { to: "/backtesting", labelKey: "nav.backtesting", icon: FlaskConical },
  { to: "/agent", labelKey: "nav.agent_full", icon: Bot },
  { to: "/system", labelKey: "nav.system", icon: Server },
];

export function NavBar() {
  const { locale } = useI18n();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const active = LINKS.find((link) => link.to === pathname) ?? LINKS[0];

  return (
    <div className="glass-bar sticky top-14 z-30 border-b border-hairline">
      <nav
        className="mx-auto hidden max-w-[1600px] overflow-x-auto lg:block"
        aria-label={locale === "vi" ? "Điều hướng chính" : "Main navigation"}
      >
        <ul className="flex w-full items-center gap-1 px-6">
          {LINKS.map((link, index) => (
            <li
              key={link.to}
              className={cn(
                "flex items-center",
                // A hairline between the three groups keeps them apart
                // without drawing a box around any of them.
                index === 3 && "ml-3 border-l border-hairline pl-3",
              )}
            >
              <NavLink to={link.to} end={link.to === "/"} className="navtab">
                <link.icon size={15} className="shrink-0" aria-hidden="true" />
                {t(link.labelKey, locale)}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/*
        ── Mobile: one accordion, the same seven destinations ──────────
      */}
      <div className="lg:hidden">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="mobile-navigation"
          className="flex min-h-12 w-full items-center gap-2 px-4 text-left text-small font-semibold text-ink"
        >
          <active.icon size={17} className="text-primary" aria-hidden="true" />
          <span className="flex-1">{t(active.labelKey, locale)}</span>
          <ChevronDown
            size={17}
            className={cn("text-muted transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
        </button>
        {open ? (
          <nav
            id="mobile-navigation"
            className="border-t border-hairline p-2"
            aria-label={locale === "vi" ? "Điều hướng chính" : "Main navigation"}
          >
            <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3">
              {LINKS.map((link) => (
                <li key={link.to}>
                  <NavLink
                    to={link.to}
                    end={link.to === "/"}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "flex min-h-11 items-center gap-2 rounded px-3 text-small font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 font-semibold text-primary"
                          : "text-muted hover:bg-surface-2 hover:text-ink",
                      )
                    }
                  >
                    <link.icon size={16} className="shrink-0" aria-hidden="true" />
                    <span>{t(link.labelKey, locale)}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </div>
    </div>
  );
}
