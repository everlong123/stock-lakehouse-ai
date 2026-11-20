import { useMutation } from "@tanstack/react-query";
import { predictModel, trainModel } from "@/api/forecasting";

export function useForecast(symbol: string, modelName: string) {
  const train = useMutation({
    mutationFn: (payload: Record<string, unknown>) => trainModel({ symbol, model_name: modelName, ...payload }),
  });
  const predict = useMutation({
    mutationFn: (horizon: number) => predictModel(symbol, modelName, horizon),
  });
  return { train, predict };
}
