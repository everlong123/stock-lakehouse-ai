import { useMutation } from "@tanstack/react-query";
import { runBacktest } from "@/api/backtesting";

export function useBacktest(symbol: string) {
  const run = useMutation({
    mutationFn: (payload: Record<string, unknown>) => runBacktest({ symbol, ...payload }),
  });
  return { run };
}
