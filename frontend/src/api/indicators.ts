import { api, ApiEnvelope } from "@/api/client";

export async function fetchIndicators(symbol: string, params: Record<string, string | boolean | number>) {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>>>(`/stocks/${symbol}/indicators`, { params });
  return data.data;
}
