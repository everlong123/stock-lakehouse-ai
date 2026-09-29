import { api, ApiEnvelope } from "@/api/client";
import { ForecastPoint, ModelMetrics } from "@/types/forecasting";

export async function trainModel(payload: Record<string, unknown>) {
  const { data } = await api.post<ApiEnvelope<Record<string, unknown>>>("/forecast/train", payload);
  return data.data;
}

export async function predictModel(symbol: string, model_name: string, horizon = 5) {
  const { data } = await api.post<ApiEnvelope<{ predictions: ForecastPoint[]; metrics: Record<string, number> }>>(
    "/forecast/predict",
    { symbol, model_name, horizon },
  );
  return data.data;
}

export async function compareModels(symbol: string) {
  const { data } = await api.get<ApiEnvelope<{ models: ModelMetrics[]; note: string }>>(`/forecast/compare/${symbol}`);
  return data.data;
}
