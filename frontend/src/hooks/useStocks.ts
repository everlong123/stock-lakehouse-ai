import { useQuery } from "@tanstack/react-query";
import { fetchStock } from "@/api/stocks";
import { useMarket } from "@/hooks/useMarket";

/**
 * The symbol's stored bars.
 *
 * WHY `start` IS PART OF THE QUERY KEY
 * ------------------------------------
 * The window is applied SERVER-SIDE: the backend reads only the
 * partitions that can hold the requested range, instead of downloading
 * the symbol's whole ten-year history and filtering it here. That is
 * roughly twelve parquet partitions for a one-year window instead of a
 * hundred and twenty-one, so the page opens in a fraction of the time.
 *
 * Because the server's answer depends on the window, the window has to
 * be part of the cache key - otherwise switching the range would show
 * the previous range's rows.
 */
export function useStocks(
  symbolOverride?: string,
  intervalOverride?: string,
  start?: string,
) {
  const { symbol: ctxSymbol, interval: ctxInterval } = useMarket();
  const symbol = symbolOverride ?? ctxSymbol;
  const interval = intervalOverride ?? ctxInterval;
  return useQuery({
    queryKey: ["stocks", symbol, interval, start ?? "all"],
    queryFn: () => fetchStock(symbol, interval, start),
    retry: 1,
  });
}
