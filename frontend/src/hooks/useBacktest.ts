import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchBacktestHistory, runBacktest } from "@/api/backtesting";

export function useBacktest(symbol: string) {
  const history = useQuery({
    queryKey: ["backtest-history", symbol],
    queryFn: () => fetchBacktestHistory(symbol),
    retry: 1,
  });
  const run = useMutation({
    mutationFn: (payload: Record<string, unknown>) => runBacktest({ symbol, ...payload }),
  });
  return { symbol, history, run };
}
