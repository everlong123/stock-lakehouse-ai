export interface ForecastPoint {
  timestamp: string;
  actual: number | null;
  predicted: number;
}

export interface ModelMetrics {
  model_name: string;
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  directional_accuracy?: number | null;
  parameters?: Record<string, unknown> | string | null;
}
