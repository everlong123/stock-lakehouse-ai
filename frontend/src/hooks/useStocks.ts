import { useQuery } from "@tanstack/react-query";
import { fetchStock } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";

export function useStocks() {
  const { symbol, interval } = useMarket();
  return useQuery({
    queryKey: ["stocks", symbol, interval],
    queryFn: () => fetchStock(symbol, interval),
    retry: 1,
  });
}
