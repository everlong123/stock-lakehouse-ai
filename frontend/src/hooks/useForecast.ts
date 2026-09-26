import { useMutation, useQuery } from "@tanstack/react-query";
import { compareModels, predictModel, trainModel } from "@/api/forecasting";

export function useForecast(symbol: string, modelName: string) {
  const compareQuery = useQuery({
    queryKey: ["forecast-compare", symbol],
    queryFn: () => compareModels(symbol),
    retry: 1,
  });
  const train = useMutation({
    mutationFn: (payload: Record<string, unknown>) => trainModel({ symbol, model_name: modelName, ...payload }),
  });
  const predict = useMutation({
    mutationFn: (horizon: number) => predictModel(symbol, modelName, horizon),
  });
  return { symbol, compareQuery, train, predict };
}
