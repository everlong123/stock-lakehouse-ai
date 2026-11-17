import { Outlet, useLocation } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { NavBar } from "@/components/layout/NavBar";

/**
 * The app shell: top bar, section nav, one wide content column.
 *
 * WHY THE CONTENT COLUMN IS 1600px AND CENTRED: the pages are chart-heavy
 * and a narrow column would squash them, but an unbounded column would
 * stretch a table's rows until they are unreadable from a laptop.
 */
export function MainLayout() {
  const location = useLocation();
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <Header />
      <NavBar />
      <main key={location.pathname} className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-8">
        <Outlet />
      </main>
      <footer className="mt-8 border-t border-hairline bg-surface px-6 py-4">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-label uppercase text-muted">
            Stock Lakehouse AI · Medallion architecture · Demo đồ án
          </span>
          <span className="font-mono text-label uppercase text-muted">
            Dữ liệu minh hoạ — không phải khuyến nghị đầu tư
          </span>
        </div>
      </footer>
    </div>
  );
}
