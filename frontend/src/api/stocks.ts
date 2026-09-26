import { api, ApiEnvelope } from "@/api/client";
import { LatestQuote, OHLCVPoint } from "@/types/stock";

export async function fetchStock(symbol: string, interval: string) {
  const { data } = await api.get<
    ApiEnvelope<{ rows: OHLCVPoint[]; latest: LatestQuote; count: number; last_updated: string; data_source: string }>
  >(`/stocks/${symbol}`, { params: { interval } });
  return data.data;
}

export async function fetchLatest(symbol: string) {
  const { data } = await api.get<ApiEnvelope<LatestQuote>>(`/stocks/${symbol}/latest`);
  return data.data;
}

export function csvUrl(symbol: string, interval: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
  return `${base}/stocks/${symbol}/csv?interval=${interval}`;
}

export async function fetchSymbols(): Promise<{ symbols: string[] }> {
  const { data } = await api.get<ApiEnvelope<{ symbols: string[] }>>("/stocks/symbols");
  return data.data;
}
