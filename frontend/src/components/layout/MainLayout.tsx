import { Outlet, useLocation } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";

export function MainLayout() {
  const location = useLocation();
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main key={location.pathname} className="flex-1 overflow-auto px-8 pb-12 pt-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}