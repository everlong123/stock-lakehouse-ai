import { useIsFetching } from "@tanstack/react-query";

/**
 * Returns true if any "stocks / dashboard / indicators / forecast /
 * backtests" query for the current symbol or interval is in flight.
 * Used by Header to flash a spinner when the user changes timeframe.
 */
export function useMarketBusy(): number {
  return useIsFetching({
    predicate: (query) => {
      const key = query.queryKey as readonly unknown[];
      return (
        key[0] === "stocks" ||
        key[0] === "dashboard" ||
        key[0] === "indicators" ||
        key[0] === "forecast-compare" ||
        key[0] === "backtest-history"
      );
    },
  });
}