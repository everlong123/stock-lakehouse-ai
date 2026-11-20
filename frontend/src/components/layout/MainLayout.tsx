import { Outlet, useLocation } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { NavBar } from "@/components/layout/NavBar";
import { MarketTape } from "@/components/layout/MarketTape";
import { useI18n, t } from "@/lib/i18n";

/**
 * The app shell: top bar, section nav, the market tape, one wide content
 * column.
 *
 * WHY THE CONTENT COLUMN IS 1600px AND CENTRED: the pages are chart-heavy
 * and a narrow column would squash them, but an unbounded column would
 * stretch a table's rows until they are unreadable from a laptop.
 *
 * WHY THE TAPE IS A SEPARATE BAND AND NOT PART OF THE HEADER: the header
 * is a row of CONTROLS (search, refresh, language) and the tape is a
 * stream of NUMBERS. Mixing the two made both worse — the controls were
 * squeezed and the numbers were clipped. A band of its own lets the tape
 * scroll across the full width while the header stays a row of things you
 * press.
 *
 * WHY THE PAGE FADES IN: a route change on a light canvas is otherwise a
 * hard cut, which reads as a flash. 260ms is long enough to soften the
 * cut and short enough that the page still feels immediate.
 *
 * WHY THE CANVAS HAS A FAINT WASH: `app-canvas` lays one very soft
 * radial gradient of the accent over the page background. It is not
 * visible as a gradient — it reads as a page that is lit from the top
 * rather than as a flat sheet of colour — and it is what stops a screen
 * full of tables and charts from looking like a spreadsheet.
 */
export function MainLayout() {
  const location = useLocation();
  const { locale } = useI18n();
  return (
    <div className="app-canvas flex min-h-screen flex-col">
      <Header />
      <NavBar />
      <MarketTape />
      <main
        key={location.pathname}
        className="page-enter mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 sm:py-8"
      >
        <Outlet />
      </main>
      <footer className="mt-8 border-t border-hairline bg-surface/60 px-6 py-5">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-label uppercase text-muted">
            © {new Date().getFullYear()} {t("app.title", locale)}
          </span>
          <span className="font-mono text-label uppercase text-muted">
            {t("app.footer_disclaimer", locale)}
          </span>
        </div>
      </footer>
    </div>
  );
}
