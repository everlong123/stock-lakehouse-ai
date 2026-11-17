import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { Loading } from "@/components/common/Loading";
import { DashboardPage } from "@/pages/Dashboard";

/**
 * The pages are loaded ON DEMAND.
 *
 * WHY THIS EXISTS
 * ---------------
 * The build produced a single JavaScript bundle of 871 kB (253 kB gzipped)
 * that the browser had to download and parse BEFORE the first page could
 * appear - even for a visitor who only ever looks at the Dashboard.
 *
 * The pages are split with `React.lazy`, so the first visit downloads
 * only the Dashboard's code and the routes the user actually opens.
 * The shell (the navigation bar, the layout) stays in the main bundle
 * because it is on screen immediately.
 *
 * The payload of each route is fetched once and then cached by the
 * browser, so a second visit to a page costs nothing.
 */
const MarketDataPage = lazy(() => import("@/pages/MarketData").then((m) => ({ default: m.MarketDataPage })));
const TechnicalAnalysisPage = lazy(() => import("@/pages/TechnicalAnalysis").then((m) => ({ default: m.TechnicalAnalysisPage })));
const ForecastingPage = lazy(() => import("@/pages/Forecasting").then((m) => ({ default: m.ForecastingPage })));
const BacktestingPage = lazy(() => import("@/pages/Backtesting").then((m) => ({ default: m.BacktestingPage })));
const AIAgentPage = lazy(() => import("@/pages/AIAgent").then((m) => ({ default: m.AIAgentPage })));
const SystemStatusPage = lazy(() => import("@/pages/SystemStatus").then((m) => ({ default: m.SystemStatusPage })));

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/market" element={<MarketDataPage />} />
          <Route path="/analysis" element={<TechnicalAnalysisPage />} />
          <Route path="/forecast" element={<ForecastingPage />} />
          <Route path="/backtesting" element={<BacktestingPage />} />
          <Route path="/agent" element={<AIAgentPage />} />
          <Route path="/system" element={<SystemStatusPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
