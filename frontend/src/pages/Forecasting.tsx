import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompare, Loader2, Play, Wand2 } from "lucide-react";
import { compareModels } from "@/api/forecasting";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageTitle } from "@/components/common/PageTitle";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useForecast } from "@/hooks/useForecast";
import { ModelMetrics } from "@/types/forecasting";
import { MODELS } from "@/utils/constants";
import { formatNumber, formatPercent } from "@/utils/format";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "FPT", "HPG", "VHM", "VNM", "VIC",
];

export function ForecastingPage() {
  const [symbol, setSymbol] = useState("VCB");
  const [model, setModel] = useState("linear_regression");
  const [horizon, setHorizon] = useState(5);
  const [epochs, setEpochs] = useState(8);
  const [hidden, setHidden] = useState(64);
  const [layers, setLayers] = useState(2);
  const [seq, setSeq] = useState(60);
  const [compare, setCompare] = useState<ModelMetrics[] | null>(null);

  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols?.length
    ? symbolsQuery.data.symbols
    : DEFAULT_SYMBOLS;

  const { train, predict } = useForecast(symbol, model);
  const predictions =
    ((predict.data?.predictions || train.data?.predictions) as Array<{
      timestamp: string; actual: number | null; predicted: number;
    }> | undefined) ?? [];
  const metrics = (predict.data?.metrics || train.data) as Record<string, number> | undefined;

  const onTrain = async () => {
    try {
      await train.mutateAsync({
        horizon, epochs, hidden_size: hidden, num_layers: layers, sequence_length: seq,
      });
      toast.success(`Da train ${model} cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Training that bai."));
    }
  };

  const onPredict = async () => {
    try {
      await predict.mutateAsync(horizon);
    } catch (error) {
      toast.error(errorMessage(error, "Chua co model. Hay train truoc."));
    }
  };

  const onCompare = async () => {
    try {
      const result = await compareModels(symbol);
      setCompare(result.models);
      toast.success(`Da so sanh ${result.models.length} models cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Khong ket noi duoc backend."));
    }
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Forecasting"
        subtitle="So sanh Linear Regression, ARIMA, LSTM tren hold-out chronological. Khong khang dinh mo hinh nao chac chan tot nhat."
        meta="04 · Models"
        actions={
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="h-9 rounded-md border border-input bg-card px-3 font-mono text-sm outline-none focus:border-foreground"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      <div>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Chon model
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {MODELS.map((m) => (
            <button
              key={m.id}
              onClick={() => setModel(m.id)}
              className={cn(
                "rounded-md border bg-card p-3 text-left",
                model === m.id
                  ? "border-foreground"
                  : "border-border hover:border-foreground/40",
              )}
            >
              <div className="text-sm font-semibold text-foreground">{m.label}</div>
              <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {m.id === "lstm" ? "Deep learning · CPU" : m.id === "arima" ? "Statistical" : "Baseline"}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-md border border-border bg-card p-4">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Model
            </span>
            <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-full">
              {MODELS.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Forecast horizon
            </span>
            <Input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          {model === "lstm" ? (
            <>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Sequence length
                </span>
                <Input type="number" value={seq} onChange={(e) => setSeq(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Hidden size
                </span>
                <Input type="number" value={hidden} onChange={(e) => setHidden(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Layers
                </span>
                <Input type="number" value={layers} onChange={(e) => setLayers(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Epochs
                </span>
                <Input type="number" value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} />
              </label>
            </>
          ) : null}
          <div className="flex items-end gap-2 md:col-span-2">
            <Button onClick={() => void onTrain()} disabled={train.isPending} className="min-w-[120px]">
              {train.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Training
                </>
              ) : (
                <>
                  <Wand2 size={14} />
                  Train
                </>
              )}
            </Button>
            <Button variant="outline" onClick={() => void onPredict()} disabled={predict.isPending} className="min-w-[120px]">
              {predict.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Predicting
                </>
              ) : (
                <>
                  <Play size={14} />
                  Predict
                </>
              )}
            </Button>
          </div>
        </div>

        {(train.isPending || predict.isPending) ? (
          <div className="mt-4 flex items-center gap-3 rounded-md border border-border bg-muted px-3 py-2 text-sm text-foreground">
            <Loader2 size={14} className="animate-spin" />
            Training/prediction dang chay. LSTM tren CPU co the mat 30s den 3 phut.
          </div>
        ) : null}
        {train.isError ? <ErrorState message={errorMessage(train.error, "Training that bai.")} /> : null}
        {predict.isError ? <ErrorState message={errorMessage(predict.error, "Chua co model. Hay train truoc.")} /> : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="MAE" value={formatNumber(metrics?.mae)} hint="Mean Absolute Error" />
        <MetricCard label="RMSE" value={formatNumber(metrics?.rmse)} hint="Root Mean Squared Error" />
        <MetricCard label="MAPE" value={formatPercent(metrics?.mape != null ? metrics.mape / 100 : null)} hint="Mean Abs % Error" />
        <MetricCard label="Directional Acc" value={formatNumber(metrics?.directional_accuracy)} hint="% doan dung chieu" />
      </div>

      <div className="rounded-md border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Actual vs Predicted</h3>
        </div>
        <div className="px-2 py-3">
          {predictions.length ? (
            <ForecastChart data={predictions} />
          ) : (
            <EmptyState message="Train model de xem bieu do so sanh." />
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Model comparison</h3>
          <Button variant="outline" size="sm" onClick={() => void onCompare()}>
            <GitCompare size={14} />
            Compare all
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {["Model", "MAE", "RMSE", "MAPE (%)", "Directional Acc"].map((col) => (
                  <th key={col} className="px-3 py-2 font-semibold">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(compare || []).map((row, i) => (
                <tr key={row.model_name} className="border-t border-border hover:bg-muted/30">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-foreground">{row.model_name}</span>
                      {i === 0 && compare && compare.length > 1 ? <Badge variant="primary">Best MAE</Badge> : null}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono">{formatNumber(row.mae)}</td>
                  <td className="px-3 py-2.5 font-mono">{formatNumber(row.rmse)}</td>
                  <td className="px-3 py-2.5 font-mono">{formatNumber(row.mape)}</td>
                  <td className="px-3 py-2.5 font-mono">{formatNumber(row.directional_accuracy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!compare ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              Bam "Compare all" de xem bang so sanh.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}