import { api, ApiEnvelope } from "@/api/client";
import { BacktestResult } from "@/types/backtesting";

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
