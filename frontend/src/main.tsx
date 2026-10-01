import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "@/App";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { MarketProvider } from "@/hooks/useMarket";
import "@/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <MarketProvider>
            <App />
            <Toaster
              position="top-right"
              toastOptions={{
                style: {
                  background: "white",
                  border: "1px solid hsl(152 18% 88%)",
                  color: "hsl(158 25% 12%)",
                  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
                },
              }}
            />
          </MarketProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);