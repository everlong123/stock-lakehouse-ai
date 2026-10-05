import { createContext, ReactNode, useContext, useMemo, useState } from "react";

interface MarketSelection {
  symbol: string;
  interval: string;
  setSymbol: (value: string) => void;
  setInterval: (value: string) => void;
}

const MarketContext = createContext<MarketSelection | null>(null);

export function MarketProvider({ children }: { children: ReactNode }) {
  const [symbol, setSymbol] = useState("AAPL");
  const [interval, setInterval] = useState("1d");
  const value = useMemo(() => ({ symbol, interval, setSymbol, setInterval }), [symbol, interval]);
  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}

export function useMarket(): MarketSelection {
  const ctx = useContext(MarketContext);
  if (!ctx) throw new Error("useMarket must be used within MarketProvider");
  return ctx;
}
