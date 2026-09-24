import { useState } from "react";
import { compareModels } from "@/api/forecasting";
import { errorMessage } from "@/api/client";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageTitle } from "@/components/common/PageTitle";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useForecast } from "@/hooks/useForecast";
import { ForecastPoint, ModelMetrics } from "@/types/forecasting";
import { MODELS } from "@/utils/constants";
import { formatNumber } from "@/utils/format";
import { toast } from "sonner";

export function ForecastingPage() {
  const [model, setModel] = useState("linear_regression");
  const [horizon, setHorizon] = useState(5);
  const [epochs, setEpochs] = useState(8);
  const [hidden, setHidden] = useState(64);
  const [layers, setLayers] = useState(2);
  const [seq, setSeq] = useState(60);
  const [compare, setCompare] = useState<ModelMetrics[] | null>(null);
  const { symbol, train, predict } = useForecast(model);
  const predictions = ((predict.data?.predictions || train.data?.predictions) as ForecastPoint[] | undefined) ?? [];
  const metrics = (predict.data?.metrics || train.data) as Record<string, number> | undefined;

  const onTrain = async () => {
    try {
      await train.mutateAsync({
        horizon,
        epochs,
        hidden_size: hidden,
        num_layers: layers,
        sequence_length: seq,
      });
      toast.success(`Trained ${model} for ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Training failed."));
    }
  };

  const onPredict = async () => {
    try {
      await predict.mutateAsync(horizon);
    } catch (error) {
      toast.error(errorMessage(error, "No trained model found. Please train the model first."));
    }
  };

  const onCompare = async () => {
    try {
      const result = await compareModels(symbol);
      setCompare(result.models);
    } catch (error) {
      toast.error(errorMessage(error, "Cannot connect to backend API."));
    }
  };

  return (
    <div className="space-y-4">
      <PageTitle
        title="Forecasting"
        subtitle="So sánh Linear Regression, ARIMA và LSTM trên hold-out chronological. Không khẳng định mô hình nào chắc chắn tốt nhất."
      />
      <div className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-4">
        <label className="text-sm">
          Model
          <Select value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full">
            {MODELS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="text-sm">
          Forecast horizon
          <Input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
        </label>
        {model === "lstm" ? (
          <>
            <label className="text-sm">
              Sequence Length
              <Input type="number" value={seq} onChange={(e) => setSeq(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Hidden Size
              <Input type="number" value={hidden} onChange={(e) => setHidden(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Layers
              <Input type="number" value={layers} onChange={(e) => setLayers(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Epochs
              <Input type="number" value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} />
            </label>
          </>
        ) : null}
        <div className="flex items-end gap-2">
          <Button onClick={() => void onTrain()} disabled={train.isPending}>
            {train.isPending ? "Training..." : "Train Model"}
          </Button>
          <Button variant="outline" onClick={() => void onPredict()} disabled={predict.isPending}>
            {predict.isPending ? "Predicting..." : "Run Prediction"}
          </Button>
        </div>
      </div>
      {train.isPending || predict.isPending ? (
        <div className="rounded-md border border-border bg-muted px-4 py-3 text-sm">Training/prediction in progress. LSTM runs on CPU.</div>
      ) : null}
      {train.isError ? <ErrorState message={errorMessage(train.error, "Training failed.")} /> : null}
      {predict.isError ? (
        <ErrorState message={errorMessage(predict.error, "No trained model found. Please train the model first.")} />
      ) : null}
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard label="MAE" value={formatNumber(metrics?.mae)} />
        <MetricCard label="RMSE" value={formatNumber(metrics?.rmse)} />
        <MetricCard label="MAPE" value={formatNumber(metrics?.mape)} />
        <MetricCard label="Directional Accuracy" value={formatNumber(metrics?.directional_accuracy)} />
      </div>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-2 text-sm font-semibold">ACTUAL vs PREDICTED</div>
        {predictions.length ? <ForecastChart data={predictions} /> : <EmptyState message="Train a model to see the comparison chart." />}
      </div>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold">MODEL COMPARISON</div>
          <Button variant="outline" onClick={() => void onCompare()}>
            Compare All Models
          </Button>
        </div>
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted-foreground">
            <tr>
              {["Model", "MAE", "RMSE", "MAPE", "Directional Accuracy"].map((col) => (
                <th key={col} className="px-2 py-2">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(compare || []).map((row) => (
              <tr key={row.model_name} className="border-t border-border">
                <td className="px-2 py-2">{row.model_name}</td>
                <td className="px-2 py-2 font-mono">{formatNumber(row.mae)}</td>
                <td className="px-2 py-2 font-mono">{formatNumber(row.rmse)}</td>
                <td className="px-2 py-2 font-mono">{formatNumber(row.mape)}</td>
                <td className="px-2 py-2 font-mono">{formatNumber(row.directional_accuracy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
