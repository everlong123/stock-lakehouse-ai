import { api, ApiEnvelope } from "@/api/client";
import { BacktestResult, MultiSymbolReport } from "@/types/backtesting";

export async function runBacktest(payload: Record<string, unknown>) {
  const { data } = await api.post<ApiEnvelope<BacktestResult>>("/backtests/run", payload);
  return data.data;
}

export async function fetchBacktestHistory(symbol?: string) {
    const { data } = await api.get<ApiEnvelope<Record<string, unknown>[]>>("/backtests/history", {
    params: { symbol },
  });
  return data.data;
}

/**
 * The multi-symbol walk-forward report.
 *
 * The report is produced AHEAD OF TIME - by the nightly `walk-forward`
 * cron job, which stores it in the lakehouse's `backtests` layer - and
 * the endpoint only reads it. The run replays ~100 symbols over ~37
 * windows each, which takes ~75 seconds of CPU, far too slow for a
 * request handler.
 *
 * The endpoint returns `{ available: false, reason }` when the report
 * has not been produced yet, and the page shows that reason instead of
 * a placeholder.
 */
export async function fetchMultiSymbolReport(strategy: string) {
  const { data } = await api.get<ApiEnvelope<MultiSymbolReport>>(
    "/backtests/multi-symbol-report",
    { params: { strategy } },
  );
  return data.data;
}
