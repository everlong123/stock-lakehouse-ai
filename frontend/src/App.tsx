import { Navigate, Route, Routes } from "react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { AIAgentPage } from "@/pages/AIAgent";
import { BacktestingPage } from "@/pages/Backtesting";
import { DashboardPage } from "@/pages/Dashboard";
import { ForecastingPage } from "@/pages/Forecasting";
import { MarketDataPage } from "@/pages/MarketData";
import { SystemStatusPage } from "@/pages/SystemStatus";
import { TechnicalAnalysisPage } from "@/pages/TechnicalAnalysis";

export default function App() {
  return (
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
  );
}
