import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompare, Loader2, Play, Wand2 } from "lucide-react";
import { compareModels, fetchPublishedForecasts } from "@/api/forecasting";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { ForecastChart, FutureForecastChart } from "@/components/charts/ForecastChart";
import { Explainer } from "@/components/common/Explainer";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageTitle } from "@/components/common/PageTitle";
import { Loading } from "@/components/common/Loading";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { PublishedForecastComparison } from "@/components/forecasting/PublishedForecastComparison";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { useForecast } from "@/hooks/useForecast";
import { ModelMetrics } from "@/types/forecasting";
import { MODELS } from "@/utils/constants";
import { formatNumber, formatPercent } from "@/utils/format";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
];

const MODEL_KIND: Record<string, string> = {
  lstm: "Deep learning · CPU",
  arima: "Thống kê",
  linear_regression: "Baseline",
};

export function ForecastingPage() {
  const { symbol: ctxSymbol, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  // Sync localSymbol when ctxSymbol changes (e.g., user changes symbol from Header)
  useEffect(() => { setLocalSymbol(ctxSymbol); setSymbol(ctxSymbol); }, [ctxSymbol]);
  const symbol = localSymbol || ctxSymbol;
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

  /*
    THE PUBLISHED FORECASTS - THE FUTURE AXIS
    ------------------------------------------
    This is the set of forecasts the nightly batch wrote down BEFORE the
    session opened, one row per model. It is read from the `predictions`
    table through the same endpoint the Dashboard uses, so the two pages
    cannot show different numbers for the same forecast.

    It is deliberately NOT the result of the train/predict buttons below:
    those recompute a forecast for the chart. This is the record of what
    the system actually committed to, which is what makes it comparable
    across models and scoreable against the real close.
  */
  const publishedQuery = useQuery({
    queryKey: ["published-forecasts", symbol],
    queryFn: () => fetchPublishedForecasts(symbol),
    staleTime: 60 * 1000,
    retry: 1,
  });

  const { train, predict } = useForecast(symbol, model);

  // WHY THESE ARE RESET WHEN THE SYMBOL OR MODEL CHANGES
  // ----------------------------------------------------
  // A React Query mutation keeps its `data` until the next mutation runs.
  // So after training AAPL and then switching to ROKU, `predict.data` still
  // held AAPL's predictions - the chart kept showing the old symbol's
  // curve, which is exactly the "the predicted line never changes"
  // symptom. Resetting clears the stale series so the chart reflects the
  // symbol that is actually selected.
  useEffect(() => {
    train.reset();
    predict.reset();
    setCompare(null);
    // `train` and `predict` are recreated on every render, so they are
    // intentionally left out of the dependency list - the reset only needs
    // to happen when the symbol or the model changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, model]);

  const predictions =
    ((predict.data?.predictions || train.data?.predictions) as Array<{
      timestamp: string; actual: number | null; predicted: number;
    }> | undefined) ?? [];
  // The points with no actual close are the future sessions - the forecast.
  const futurePoints = predictions.filter((p) => p.actual === null || p.actual === undefined);
  const metrics = (predict.data?.metrics || train.data) as Record<string, number> | undefined;
  // `chart_holdout` means the numbers describe the curve below them;
  // `training_split` means they are the values recorded at training time.
  const metricsSource = predict.data?.metrics_source;
  const modelNameLabel = MODELS.find((m) => m.id === model)?.label ?? model;

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

  /**
   * Train and then predict, in one click.
   *
   * WHY THIS EXISTS: a newcomer opening this page sees two buttons and
   * has to guess the order. If they press "Predict" first, the request
   * fails with "no trained model", which looks like a broken feature
   * rather than a missing step. The combined button removes the guess.
   */
  const onTrainAndPredict = async () => {
    try {
      await train.mutateAsync({
        horizon, epochs, hidden_size: hidden, num_layers: layers, sequence_length: seq,
      });
      await predict.mutateAsync(horizon);
      toast.success(`Đã train và dự báo ${model} cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Training/dự báo thất bại."));
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
    <div className="space-y-12">
      <PageTitle
        title="Huấn luyện & so sánh model"
        subtitle="Ba mô hình được đo trên cùng một tập hold-out. Trang này không chọn mô hình nào là tốt nhất."
        meta="04 · Models"
        actions={
          <select
            value={symbol}
            onChange={(e) => { setLocalSymbol(e.target.value); setSymbol(e.target.value); }}
            className="h-9 rounded border border-hairline bg-surface px-2 font-mono text-small text-ink outline-none focus:border-primary"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      <Explainer
        title="Trang này dùng để làm gì?"
        intro="Ở đây bạn huấn luyện một mô hình trên lịch sử giá của một mã cổ phiếu, rồi xem mô hình đó đã đoán sai bao nhiêu và dự báo giá cho các phiên sắp tới. Mọi con số đều chỉ mô tả quá khứ — chúng không phải lời khuyên mua bán."
        items={[
          {
            term: "Khác với kiểm chứng ở trang Dữ liệu thị trường",
            meaning:
              "Trang này đo MÔ HÌNH trên tập hold-out: dữ liệu đã xảy ra, mô hình được hỏi sau đó. Trang Dữ liệu thị trường đo HỆ THỐNG đang chạy: dự báo được ghi xuống trước khi phiên mở cửa, rồi mới so với giá thật. Hai con số khác nhau và không thay thế cho nhau.",
          },
          {
            term: "Hold-out (tập kiểm tra)",
            meaning: "Phần dữ liệu mô hình chưa từng thấy khi huấn luyện. Đây là nơi đo độ chính xác thật của mô hình.",
          },
          {
            term: "MAE / RMSE",
            meaning: "Sai số trung bình (MAE) và sai số bình phương trung bình (RMSE), tính bằng đơn vị tiền. Càng nhỏ càng tốt.",
          },
          {
            term: "MAPE",
            meaning: "Sai số trung bình tính theo phần trăm. Cho phép so sánh giữa các mã có giá rất khác nhau.",
          },
          {
            term: "Directional Accuracy",
            meaning: "Tỉ lệ % phiên mà mô hình đoán đúng hướng đi lên hay xuống (không quan tâm độ lớn).",
          },
          {
            term: "Đường liền vs đường đứt",
            meaning: "Đường liền là giá thật. Đường đứt là ước lượng của mô hình cho các phiên đã xảy ra.",
          },
          {
            term: "Vùng dự báo",
            meaning: "Phần đường đứt nằm bên phải vạch phân cách: đó là các phiên chưa xảy ra. Sai số tích luỹ dần theo mỗi bước.",
          },
          {
            term: "Train vs Predict",
            meaning: "Train là học lại mô hình từ đầu. Predict chỉ dùng mô hình đã có để dự báo — nhanh hơn nhiều.",
          },
        ]}
        steps={[
          "Chọn mã cổ phiếu ở góc trên bên phải.",
          "Chọn model (Linear Regression / ARIMA / LSTM) và số phiên muốn dự báo.",
          "Bấm 'Train và Dự báo' — một bước là xong.",
          "Đổi mã hoặc đổi model thì phải Train lại cho mã/model mới.",
        ]}
      />

      {/*
        ── Published forecasts (the FUTURE axis) ────────────────────
        The forecasts the system wrote down before the session opened.
        It is here, on the Models page, because it answers "what does
        each model expect next" - and it is not on the Dashboard, because
        the Dashboard is the summary: it shows one number, not a table.

        The Dashboard's card and this table read the SAME rows from the
        `predictions` table. One source, two levels of detail.
      */}
      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">Dự báo đã công bố</h2>
            <p className="section-sub">
              Số hệ thống đã ghi xuống trước khi phiên mở cửa, cho từng mô hình
              trên cùng một phiên. Khi phiên đã xảy ra, giá thật hiện ngay bên
              dưới để so sánh.
            </p>
          </div>
        </div>
        <div className="pt-4">
          {publishedQuery.isLoading ? (
            <Loading variant="skeleton" className="h-32" />
          ) : publishedQuery.isError ? (
            <ErrorState
              message={errorMessage(publishedQuery.error, "Không đọc được dự báo đã công bố.")}
              onRetry={() => void publishedQuery.refetch()}
            />
          ) : (
            <PublishedForecastComparison
              symbol={symbol}
              targetSession={publishedQuery.data?.target_session ?? null}
              forecasts={publishedQuery.data?.forecasts ?? []}
              trainedModels={publishedQuery.data?.trained_models ?? []}
            />
          )}
        </div>
      </section>

      {/*
        ── Model picker ────────────────────────────────────────────
        The three models are *choices*, and a choice is exactly the thing
        that should look clickable. They are radio-like rows in one
        continuous list rather than three separate cards, so the reader
        compares them against each other instead of seeing three equal
        little boxes.
      */}
      <section>
        <div className="section-head">
          <h2 className="section-title">Mô hình</h2>
        </div>
        <div className="pt-4">
          <div role="radiogroup" aria-label="Mô hình" className="flex flex-wrap gap-x-8 gap-y-4">
            {MODELS.map((m) => {
              const active = model === m.id;
              return (
                <button
                  key={m.id}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setModel(m.id)}
                  className="group flex min-h-11 items-center gap-3 text-left"
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                      active ? "border-primary" : "border-hairline",
                    )}
                  >
                    {active ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                  </span>
                  <span>
                    <span
                      className={cn(
                        "block text-small font-semibold",
                        active ? "text-ink" : "text-muted",
                      )}
                    >
                      {m.label}
                    </span>
                    <span className="block font-mono text-label uppercase text-muted">
                      {MODEL_KIND[m.id]}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/*
        ── Parameters + action ─────────────────────────────────────
        Parameters are grouped by what they affect: the forecast window
        applies to every model; the neural-network knobs only appear for
        LSTM. One primary button ("Train và Dự báo") carries the page —
        the other two are quieter alternatives.
      */}
      <section className="rounded border border-hairline bg-surface p-4">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="block text-small">
            <span className="label mb-1 block">Model</span>
            <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-full">
              {MODELS.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="block text-small">
            <span className="label mb-1 block">Số phiên dự báo</span>
            <Input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          {model === "lstm" ? (
            <>
              <label className="block text-small">
                <span className="label mb-1 block">Sequence length</span>
                <Input type="number" value={seq} onChange={(e) => setSeq(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Hidden size</span>
                <Input type="number" value={hidden} onChange={(e) => setHidden(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Layers</span>
                <Input type="number" value={layers} onChange={(e) => setLayers(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Epochs</span>
                <Input type="number" value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} />
              </label>
            </>
          ) : null}
          <div className="flex flex-wrap items-end gap-2 md:col-span-2">
            <Button
              variant="primary"
              onClick={() => void onTrainAndPredict()}
              disabled={train.isPending || predict.isPending}
            >
              {train.isPending || predict.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Đang chạy
                </>
              ) : (
                <>
                  <Play size={14} />
                  Train và Dự báo
                </>
              )}
            </Button>
            <Button variant="outline" onClick={() => void onTrain()} disabled={train.isPending}>
              {train.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Training
                </>
              ) : (
                <>
                  <Wand2 size={14} />
                  Chỉ Train
                </>
              )}
            </Button>
            <Button variant="text" onClick={() => void onPredict()} disabled={predict.isPending}>
              {predict.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Predicting
                </>
              ) : (
                <>
                  <Play size={14} />
                  Chỉ Predict
                </>
              )}
            </Button>
          </div>
        </div>

        {(train.isPending || predict.isPending) ? (
          <div className="mt-4 flex items-center gap-3 rounded border border-hairline bg-surface-2 px-3 py-2 text-small text-ink">
            <Loader2 size={14} className="animate-spin" />
            Training/dự báo đang chạy. LSTM trên CPU có thể mất 30s đến 3 phút.
          </div>
        ) : null}
        {train.isError ? <ErrorState message={errorMessage(train.error, "Training thất bại.")} /> : null}
        {predict.isError ? (
          <ErrorState message={errorMessage(predict.error, "Chưa có model cho mã này. Hãy bấm 'Train và Dự báo'.")} />
        ) : null}
      </section>

      {/* Metrics: four numbers in a hairline-divided row, no boxes. */}
      <section>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 xl:grid-cols-4">
          <MetricCard label="MAE" value={formatNumber(metrics?.mae)} hint="Sai số tuyệt đối trung bình" />
          <MetricCard label="RMSE" value={formatNumber(metrics?.rmse)} hint="Sai số bình phương trung bình" />
          <MetricCard label="MAPE" value={formatPercent(metrics?.mape != null ? metrics.mape / 100 : null)} hint="Sai số % trung bình" />
          <MetricCard
            label="Directional Acc"
            value={formatPercent(metrics?.directional_accuracy)}
            hint="% đoán đúng chiều"
          />
        </div>
        {metricsSource === "chart_holdout" ? (
          <p className="mt-3 text-small text-muted">
            Số trên được tính lại trên đúng tập hold-out hiển thị ở biểu đồ dưới.
          </p>
        ) : null}
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">Giá thật vs dự báo</h2>
            <p className="section-sub">
              Đường liền là giá thật, đường đứt là ước lượng của model trên tập hold-out
              (cùng tập dùng để tính MAE ở trên).
            </p>
          </div>
        </div>
        <div className="pt-4">
          {predictions.length ? (
            <ForecastChart data={predictions} />
          ) : (
            <EmptyState
              message="Train model để xem biểu đồ so sánh."
              hint="Chọn model, đặt horizon, bấm Train. Sau đó biểu đồ sẽ hiện đường dự báo so với giá thật."
            />
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">Dự báo {horizon} phiên tới</h2>
            <p className="section-sub">
              {modelNameLabel} dự báo giá đóng cửa cho {horizon} phiên chưa xảy ra. Sai số tích luỹ
              theo từng bước, nên đây là tham chiếu chứ không phải dự đoán chắc chắn.
            </p>
          </div>
        </div>
        <div className="pt-4">
          {futurePoints.length ? (
            <FutureForecastChart data={futurePoints} />
          ) : (
            <EmptyState
              message="Chưa có dự báo cho các phiên sắp tới."
              hint="Bấm Predict sau khi train để tạo dự báo."
            />
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2 className="section-title">So sánh model</h2>
          <Button variant="outline" size="sm" onClick={() => void onCompare()}>
            <GitCompare size={13} />
            So sánh tất cả
          </Button>
        </div>
        <div className="mt-4 overflow-x-auto rounded border border-hairline bg-surface">
          <table className="table">
            <thead>
              <tr>
                {["Model", "MAE", "RMSE", "MAPE (%)", "Directional Acc (%)"].map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(compare || []).map((row, i) => (
                <tr key={row.model_name}>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-ink">{row.model_name}</span>
                      {i === 0 && compare && compare.length > 1 ? <Badge variant="primary">Best MAE</Badge> : null}
                    </div>
                  </td>
                  <td className="font-mono tabular-nums">{formatNumber(row.mae)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.rmse)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.mape)}</td>
                  <td className="font-mono tabular-nums">{formatPercent(row.directional_accuracy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!compare ? (
            <div className="px-4 py-6 text-center text-small text-muted">
              Bấm "So sánh tất cả" để xem bảng.
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
