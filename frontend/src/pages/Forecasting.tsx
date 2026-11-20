import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitCompare, Loader2, Play } from "lucide-react";
import { compareModels, fetchPublishedForecasts } from "@/api/forecasting";
import { errorMessage } from "@/api/client";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { Explainer } from "@/components/common/Explainer";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageHeader } from "@/components/common/PageHeader";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { PublishedForecastComparison } from "@/components/forecasting/PublishedForecastComparison";
import { ForecastVerification } from "@/components/forecasting/ForecastVerification";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { useForecast } from "@/hooks/useForecast";
import { useI18n, t } from "@/lib/i18n";
import { ModelMetrics } from "@/types/forecasting";
import { MODELS } from "@/utils/constants";
import { currencyForSymbol, formatNumber, formatPercent } from "@/utils/format";
import { toast } from "sonner";

export function ForecastingPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const [model, setModel] = useState("linear_regression");
  const [horizon, setHorizon] = useState(5);
  const [epochs, setEpochs] = useState(8);
  const [hidden, setHidden] = useState(64);
  const [layers, setLayers] = useState(2);
  const [seq, setSeq] = useState(60);
  const [compare, setCompare] = useState<ModelMetrics[] | null>(null);
  const [compareNote, setCompareNote] = useState("");
  const [commonComparison, setCommonComparison] = useState(false);

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
    setCompareNote("");
    setCommonComparison(false);
    // `train` and `predict` are recreated on every render, so they are
    // intentionally left out of the dependency list - the reset only needs
    // to happen when the symbol or the model changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, model]);

  const predictions =
    ((predict.data?.predictions || train.data?.predictions) as Array<{
      timestamp: string; actual: number | null; predicted: number;
    }> | undefined) ?? [];
  const metrics = (predict.data?.metrics || train.data) as Record<string, number> | undefined;
  // `chart_holdout` means the numbers describe the curve below them;
  // `training_split` means they are the values recorded at training time.
  const metricsSource = predict.data?.metrics_source;
  const modelNameLabel = MODELS.find((m) => m.id === model)?.label ?? model;

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
      setCompare(result.baseline ? [...result.models, result.baseline] : result.models);
      setCompareNote(result.note);
      setCommonComparison(result.comparison_scope === "common_target_sessions");
      toast.success(`Đã so sánh ${result.models.length} models cho ${symbol}`);
    } catch (error) {
      toast.error(errorMessage(error, "Không kết nối được backend."));
    }
  };

  return (
    <div className="space-y-10">
      {/*
        ── The page header ───────────────────────────────────────────
        The symbol leads, because the page is about one symbol's models.
      */}
      <PageHeader
        section={t("nav.models", locale)}
        title={t("forecast.title", locale)}
        subtitle={t("forecast.subtitle", locale)}
        aside={
          <span className="rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-small font-semibold text-ink">
            {symbol}
          </span>
        }
      />

      <Explainer
        title={t("forecast.explainer_title", locale)}
        intro={t("forecast.explainer_intro", locale)}
        items={[
          {
            term: t("forecast.term_verification", locale),
            meaning: t("forecast.term_verification_meaning", locale),
          },
          {
            term: t("forecast.term_holdout", locale),
            meaning: t("forecast.term_holdout_meaning", locale),
          },
          {
            term: t("forecast.term_mae", locale),
            meaning: t("forecast.term_mae_meaning", locale),
          },
          {
            term: t("forecast.term_mape", locale),
            meaning: t("forecast.term_mape_meaning", locale),
          },
          {
            term: t("forecast.term_direction", locale),
            meaning: t("forecast.term_direction_meaning", locale),
          },
          {
            term: t("forecast.term_lines", locale),
            meaning: t("forecast.term_lines_meaning", locale),
          },
          {
            term: t("forecast.term_region", locale),
            meaning: t("forecast.term_region_meaning", locale),
          },
          {
            term: t("forecast.term_train_predict", locale),
            meaning: t("forecast.term_train_predict_meaning", locale),
          },
        ]}
        steps={[
          t("forecast.step_1", locale),
          t("forecast.step_2", locale),
          t("forecast.step_3", locale),
          t("forecast.step_4", locale),
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
            <h2 className="section-title">{t("forecast.published_title", locale)}</h2>
            <p className="section-sub">{t("forecast.published_sub", locale)}</p>
          </div>
        </div>
        <div className="pt-4">
          {publishedQuery.isLoading ? (
            <Loading variant="skeleton" className="h-32" />
          ) : publishedQuery.isError ? (
            <ErrorState
              message={errorMessage(publishedQuery.error, t("forecast.published_empty", locale))}
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

      <section id="forecast-verification">
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("forecast.verification_title", locale)}</h2>
            <p className="section-sub">{t("forecast.verification_sub", locale)}</p>
          </div>
        </div>
        <div className="pt-4">
          <ForecastVerification symbol={symbol} currency={currencyForSymbol(symbol)} />
        </div>
      </section>

      {/*
        ── Parameters + action ─────────────────────────────────────
        Parameters are grouped by what they affect: the forecast window
        applies to every model; the neural-network knobs only appear for
        LSTM. One primary button ("Train và Dự báo") carries the page —
        the second action reuses a model that is already trained.

        WHY THE FORM IS A RECESSED PANEL: it is a set of inputs, and
        inputs read as a form. The panel gives them one background, so
        the results below are clearly "output" and not "more settings".
      */}
      <section className="rounded border border-hairline bg-surface-2 p-4">
        <h2 className="mb-4 font-display text-body font-semibold">
          {`${t("forecast.form_title", locale)} ${symbol}`}
        </h2>
        <div className="grid gap-4 md:grid-cols-4">
          <label className="block text-small">
            <span className="label mb-1 block">{t("forecast.model_label", locale)}</span>
            <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-full">
              {MODELS.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="block text-small">
            <span className="label mb-1 block">{t("forecast.horizon_label", locale)}</span>
            <Input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          {model === "lstm" ? (
            <>
              <label className="block text-small">
                <span className="label mb-1 block">{t("forecast.seq_label", locale)}</span>
                <Input type="number" value={seq} onChange={(e) => setSeq(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">{t("forecast.hidden_label", locale)}</span>
                <Input type="number" value={hidden} onChange={(e) => setHidden(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">{t("forecast.layers_label", locale)}</span>
                <Input type="number" value={layers} onChange={(e) => setLayers(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">{t("forecast.epochs_label", locale)}</span>
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
                  {t("forecast.running", locale)}
                </>
              ) : (
                <>
                  <Play size={14} />
                  {t("forecast.train_predict", locale)}
                </>
              )}
            </Button>
            <Button variant="outline" onClick={() => void onPredict()} disabled={train.isPending || predict.isPending}>
              {predict.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {t("forecast.predicting", locale)}
                </>
              ) : (
                <>
                  <Play size={14} />
                  {t("forecast.reuse_model", locale)}
                </>
              )}
            </Button>
          </div>
        </div>

        {(train.isPending || predict.isPending) ? (
          <div className="mt-4 flex items-center gap-3 rounded border border-hairline bg-surface-2 px-3 py-2 text-small text-ink">
            <Loader2 size={14} className="animate-spin" />
            {t("forecast.running_note", locale)}
          </div>
        ) : null}
        {train.isError ? <ErrorState message={errorMessage(train.error, t("forecast.train_error", locale))} /> : null}
        {predict.isError ? (
          <ErrorState message={errorMessage(predict.error, t("forecast.predict_error", locale))} />
        ) : null}
      </section>

      {/* Metrics: four numbers in a hairline-divided row, no boxes. */}
      {metrics ? <section>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 xl:grid-cols-4">
          <MetricCard label={t("forecast.metric_mae", locale)} value={formatNumber(metrics?.mae)} hint={t("forecast.hint_mae", locale)} />
          <MetricCard label={t("forecast.metric_rmse", locale)} value={formatNumber(metrics?.rmse)} hint={t("forecast.hint_rmse", locale)} />
          <MetricCard label={t("forecast.metric_mape", locale)} value={formatPercent(metrics?.mape != null ? metrics.mape / 100 : null)} hint={t("forecast.hint_mape", locale)} />
          <MetricCard
            label={t("forecast.metric_direction", locale)}
            value={formatPercent(metrics?.directional_accuracy)}
            hint={t("forecast.hint_direction", locale)}
          />
        </div>
        {metricsSource === "chart_holdout" ? (
          <p className="mt-3 text-small text-muted">
            {t("forecast.metrics_note", locale)}
          </p>
        ) : null}
      </section> : null}

      <section>
        <div className="section-head">
          <div>
            <h2 className="section-title">{t("forecast.chart_title", locale)}</h2>
            <p className="section-sub">
              {modelNameLabel}: đường liền là giá thật, đường đứt là ước lượng trên tập
              hold-out. Phần bên phải vạch phân cách là dự báo {horizon} phiên tới.
            </p>
          </div>
        </div>
        <div className="pt-4">
          {predict.data?.forecast_available === false && predict.data.forecast_reason ? (
            <p role="status" className="mb-3 border-l-2 border-negative pl-3 text-small text-negative">
              {t("forecast.no_new_forecast", locale)} {predict.data.forecast_reason}
            </p>
          ) : null}
          {predictions.length ? (
            <ForecastChart data={predictions} />
          ) : (
            <EmptyState
              message={t("forecast.empty_chart", locale)}
              hint={t("forecast.empty_chart_hint", locale)}
            />
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2 className="section-title">{t("forecast.compare_title", locale)}</h2>
          <Button variant="outline" size="sm" onClick={() => void onCompare()}>
            <GitCompare size={13} />
            {t("forecast.compare_all", locale)}
          </Button>
        </div>
        <div className="mt-4 overflow-x-auto rounded border border-hairline bg-surface shadow-sm">
          <table className="table">
            <thead>
              <tr>
                {["Model", t("forecast.metric_mae", locale), t("forecast.metric_rmse", locale), `${t("forecast.metric_mape", locale)} (%)`, `${t("forecast.metric_direction", locale)} (%)`].map((col) => (
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
                    {commonComparison && i === 0 && compare && compare.length > 1 && row.mae != null && row.mae === Math.min(...compare.filter((r) => r.mae != null).map((r) => r.mae!)) ? <Badge variant="primary">{t("forecast.best_mae", locale)}</Badge> : null}
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
              {t("forecast.compare_empty", locale)}
            </div>
          ) : null}
          {compareNote ? <p className="px-4 py-3 text-small text-muted">{compareNote}</p> : null}
        </div>
      </section>
    </div>
  );
}
