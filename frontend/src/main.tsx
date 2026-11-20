import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "@/App";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { MarketProvider } from "@/hooks/useMarket";
import { ThemeProvider } from "@/hooks/useTheme";
import { I18nProvider } from "@/lib/i18n";
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
          <I18nProvider>
            <ThemeProvider>
              <MarketProvider>
                <App />
                <Toaster
                  position="top-right"
                  toastOptions={{
                    style: {
                      background: "hsl(var(--surface))",
                      border: "1px solid hsl(var(--hairline))",
                      color: "hsl(var(--ink))",
                      fontFamily: '"DM Sans", system-ui, sans-serif',
                      fontSize: "14px",
                      borderRadius: "8px",
                      boxShadow: "var(--shadow-lg)",
                    },
                  }}
                />
              </MarketProvider>
            </ThemeProvider>
          </I18nProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
