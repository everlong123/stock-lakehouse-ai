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
 * The offline multi-symbol walk-forward report.
 *
 * The report is produced by a script, not by a request, because the run
 * replays ~100 symbols and takes about 90 seconds. The endpoint returns
 * `{ available: false, reason }` when the file has not been generated
 * yet, and the page shows that reason instead of a placeholder.
 */
export async function fetchMultiSymbolReport(strategy: string) {
  const { data } = await api.get<ApiEnvelope<MultiSymbolReport>>(
    "/backtests/multi-symbol-report",
    { params: { strategy } },
  );
  return data.data;
}
