import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, GitCompare, Loader2, Play, Sparkles, Target, Wand2 } from "lucide-react";
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

const MODEL_ICONS: Record<string, React.ReactNode> = {
  linear_regression: <Target size={14} />,
  arima: <Brain size={14} />,
  lstm: <Sparkles size={14} />,
};

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
      toast.success(`Đã train ${model} cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Training thất bại."));
    }
  };

  const onPredict = async () => {
    try {
      await predict.mutateAsync(horizon);
    } catch (error) {
      toast.error(errorMessage(error, "Chưa có model. Hãy train trước."));
    }
  };

  const onCompare = async () => {
    try {
      const result = await compareModels(symbol);
      setCompare(result.models);
      toast.success(`Đã so sánh ${result.models.length} models cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Không kết nối được backend."));
    }
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Forecasting"
        subtitle="So sánh Linear Regression, ARIMA, LSTM trên hold-out chronological. Không khẳng định mô hình nào chắc chắn tốt nhất."
        badge="ML"
        actions={
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-brand-500"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      {/* Model selector cards */}
      <div className="grid gap-3 md:grid-cols-3">
        {MODELS.map((m) => (
          <button
            key={m.id}
            onClick={() => setModel(m.id)}
            className={cn(
              "rounded-xl border bg-card p-4 text-left transition-all",
              model === m.id
                ? "border-brand-500 bg-brand-50/50 shadow-glow"
                : "border-border hover:border-brand-300",
            )}
          >
            <div className="flex items-center gap-2">
              <span className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                model === m.id ? "bg-brand-500 text-white" : "bg-muted text-muted-foreground",
              )}>
                {MODEL_ICONS[m.id]}
              </span>
              <div>
                <div className="font-semibold text-foreground">{m.label}</div>
                <div className="text-[11px] text-muted-foreground">
                  {m.id === "lstm" ? "Deep Learning · CPU" : m.id === "arima" ? "Statistical" : "Baseline"}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Train panel */}
      <div className="card-elevated p-5">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Model
            </span>
            <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-full">
              {MODELS.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Forecast horizon
            </span>
            <Input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          {model === "lstm" ? (
            <>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Sequence length
                </span>
                <Input type="number" value={seq} onChange={(e) => setSeq(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Hidden size
                </span>
                <Input type="number" value={hidden} onChange={(e) => setHidden(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Layers
                </span>
                <Input type="number" value={layers} onChange={(e) => setLayers(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
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
                  Training...
                </>
              ) : (
                <>
                  <Wand2 size={14} />
                  Train Model
                </>
              )}
            </Button>
            <Button variant="outline" onClick={() => void onPredict()} disabled={predict.isPending} className="min-w-[120px]">
              {predict.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Predicting...
                </>
              ) : (
                <>
                  <Play size={14} />
                  Run Prediction
                </>
              )}
            </Button>
          </div>
        </div>

        {(train.isPending || predict.isPending) ? (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-700">
            <Loader2 size={16} className="animate-spin" />
            <span>Training/prediction đang chạy... LSTM chạy trên CPU, có thể mất 30s-3 phút.</span>
          </div>
        ) : null}
        {train.isError ? <ErrorState message={errorMessage(train.error, "Training thất bại.")} /> : null}
        {predict.isError ? <ErrorState message={errorMessage(predict.error, "Chưa có model. Hãy train trước.")} /> : null}
      </div>

      {/* Metrics row */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="MAE" value={formatNumber(metrics?.mae)} hint="Mean Absolute Error" />
        <MetricCard label="RMSE" value={formatNumber(metrics?.rmse)} hint="Root Mean Squared Error" />
        <MetricCard label="MAPE" value={formatPercent(metrics?.mape != null ? metrics.mape / 100 : null)} hint="Mean Abs % Error" />
        <MetricCard label="Directional Acc" value={formatNumber(metrics?.directional_accuracy)} hint="% đoán đúng chiều" />
      </div>

      {/* Forecast chart */}
      <div className="card-elevated p-5">
        <div className="mb-3 flex items-center gap-2">
          <Sparkles size={14} className="text-brand-600" />
          <h3 className="text-base font-bold text-foreground">Actual vs Predicted</h3>
        </div>
        {predictions.length ? (
          <ForecastChart data={predictions} />
        ) : (
          <EmptyState message="Train model để xem biểu đồ so sánh." />
        )}
      </div>

      {/* Model comparison */}
      <div className="card-elevated overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <GitCompare size={14} className="text-brand-600" />
            <h3 className="text-base font-bold text-foreground">Model comparison</h3>
          </div>
          <Button variant="outline" onClick={() => void onCompare()}>
            <GitCompare size={14} />
            Compare All Models
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-muted/50 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {["Model", "MAE", "RMSE", "MAPE (%)", "Directional Acc"].map((col) => (
                  <th key={col} className="px-4 py-2.5 font-semibold">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(compare || []).map((row, i) => (
                <tr key={row.model_name} className="border-t border-border hover:bg-muted/30">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                        {MODEL_ICONS[row.model_name as keyof typeof MODEL_ICONS] ?? <Brain size={14} />}
                      </span>
                      <span className="font-semibold">{row.model_name}</span>
                      {i === 0 && compare && compare.length > 1 ? <Badge variant="primary">Best MAE</Badge> : null}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono">{formatNumber(row.mae)}</td>
                  <td className="px-4 py-2.5 font-mono">{formatNumber(row.rmse)}</td>
                  <td className="px-4 py-2.5 font-mono">{formatNumber(row.mape)}</td>
                  <td className="px-4 py-2.5 font-mono">{formatNumber(row.directional_accuracy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!compare ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              Bấm "Compare All Models" để xem bảng so sánh.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}