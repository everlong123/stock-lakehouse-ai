import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "@/App";
import { MarketProvider } from "@/hooks/useMarket";
import "@/index.css";

const saved = localStorage.getItem("theme");
document.documentElement.classList.toggle("dark", saved ? saved === "dark" : true);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <MarketProvider>
          <App />
          <Toaster theme="system" position="top-right" />
        </MarketProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
