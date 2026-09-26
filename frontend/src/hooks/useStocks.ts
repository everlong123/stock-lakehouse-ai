import { useQuery } from "@tanstack/react-query";
import { fetchStock } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";

export function useStocks(symbolOverride?: string, intervalOverride?: string) {
  const { symbol: ctxSymbol, interval: ctxInterval } = useMarket();
  const symbol = symbolOverride ?? ctxSymbol;
  const interval = intervalOverride ?? ctxInterval;
  return useQuery({
    queryKey: ["stocks", symbol, interval],
    queryFn: () => fetchStock(symbol, interval),
    retry: 1,
  });
}
