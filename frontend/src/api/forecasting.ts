import { api, ApiEnvelope } from "@/api/client";
import {
  AccuracyResponse,
  ForecastResponse,
  ModelMetrics,
  PublishedForecastResponse,
} from "@/types/forecasting";

export async function trainModel(payload: Record<string, unknown>) {
  const { data } = await api.post<ApiEnvelope<Record<string, unknown>>>("/forecast/train", payload);
  return data.data;
}

export async function predictModel(symbol: string, model_name: string, horizon = 5) {
  const { data } = await api.post<ApiEnvelope<ForecastResponse>>(
    "/forecast/predict",
    { symbol, model_name, horizon },
  );
  return data.data;
}

export async function compareModels(symbol: string) {
  const { data } = await api.get<ApiEnvelope<{ models: ModelMetrics[]; note: string }>>(`/forecast/compare/${symbol}`);
  return data.data;
}

/**
 * The verified forecasts: what the system predicted, and what happened.
 *
 * WHY THIS IS SEPARATE FROM `/forecast/predict`: the predict endpoint
 * returns a fresh computation for the chart, including the model's
 * backtest history. This one returns only the forecasts that were
 * PUBLISHED and then CHECKED against a real close - the evidence that
 * the system works outside the training set.
 */
export async function fetchForecastAccuracy(
  symbol?: string,
  modelName?: string,
  limit = 180,
): Promise<AccuracyResponse> {
  const params: Record<string, string | number> = { limit };
  if (symbol) params.symbol = symbol;
  if (modelName) params.model_name = modelName;
  const { data } = await api.get<ApiEnvelope<AccuracyResponse>>("/forecast/accuracy", { params });
  return data.data;
}

/**
 * The forecasts the system PUBLISHED for one symbol, one row per model.
 *
 * WHY THIS IS NOT `/forecast/predict`: the predict endpoint computes a
 * fresh forecast for the chart. This one reads the rows the nightly batch
 * wrote, so the numbers are exactly the ones the system committed to
 * before the session opened - the same rows the accuracy report later
 * scores.
 */
export async function fetchPublishedForecasts(
  symbol: string,
): Promise<PublishedForecastResponse> {
  const { data } = await api.get<ApiEnvelope<PublishedForecastResponse>>(
    `/forecast/published/${symbol}`,
  );
  return data.data;
}
