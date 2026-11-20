import { currencyForSymbol, formatPercent, formatPrice, isUsableNumber } from "@/utils/format";
import { changeClass } from "@/utils/format";
import { useI18n } from "@/lib/i18n";
import { MODELS } from "@/utils/constants";
import type { PublishedForecast, TrainedModelMetric } from "@/types/forecasting";

interface PublishedForecastComparisonProps {
  symbol: string;
  targetSession: string | null;
  forecasts: PublishedForecast[];
  trainedModels: TrainedModelMetric[];
  currency?: string | null;
}

/**
 * The models' forecasts for ONE session, side by side.
 *
 * WHY THIS SHOWS THE PUBLISHED ROWS AND NOT A FRESH COMPUTATION
 * --------------------------------------------------------------
 * Every row here is a number the nightly batch wrote to the
 * `predictions` table BEFORE the session opened. The page does not
 * recompute anything: a forecast that is recomputed on every render
 * would show a different number each time the page is opened, and the
 * reader would have no way to tell which one the system actually
 * committed to. The verification panel on the Forecast page scores
 * these exact rows against the real close.
 *
 * WHY THE HISTORICAL METRIC SITS NEXT TO THE FORECAST
 * ---------------------------------------------------
 * A forecast without its model's track record is a number without
 * context. The MAE and the directional accuracy are what the model
 * achieved on its hold-out split - the reader needs both to judge the
 * forecast. Showing them together also means the system displays its
 * own weak spots: the row with the worst MAE is visible, not hidden.
 *
 * WHY A MODEL WITH NO FORECAST IS LISTED AS ABSENT
 * ------------------------------------------------
 * A trained model that published nothing for this session is reported
 * as such, with its metric shown and no forecast beside it. It is never
 * filled with another model's number, and it is never hidden.
 */
export function PublishedForecastComparison({
  symbol,
  targetSession,
  forecasts,
  trainedModels,
  currency,
}: PublishedForecastComparisonProps) {
  const { locale } = useI18n();
  const vi = locale === "vi";
  const quoteCurrency = currency ?? currencyForSymbol(symbol);
  if (forecasts.length === 0) {
    return (
      <div className="border-t border-hairline py-4">
        <p className="text-small text-muted">
          {trainedModels.length > 0
            ? (vi ? `${trainedModels.length} mô hình đã được huấn luyện cho ${symbol}, nhưng chưa có dự báo nào được công bố cho phiên này.` : `${trainedModels.length} models are trained for ${symbol}, but no forecast has been published for this session.`)
            : (vi ? `Chưa có mô hình được huấn luyện cho ${symbol}.` : `No trained model is available for ${symbol}.`)}
        </p>
      </div>
    );
  }

  // The metric of each trained model, keyed by name, so a forecast row can
  // show the track record of the model that wrote it.
  const metricsByModel = new Map<string, TrainedModelMetric>();
  for (const record of trainedModels) {
    metricsByModel.set(record.model_name, record);
  }

  // The models that are trained but published nothing for this session.
  const publishedNames = new Set(forecasts.map((f) => f.model_name));
  const silentModels = trainedModels.filter((m) => !publishedNames.has(m.model_name));

  return (
    <div>
      <div className="space-y-2 sm:hidden">
        {forecasts.map((forecast) => {
          const metric = metricsByModel.get(forecast.model_name);
          return (
            <article key={forecast.model_name} className="rounded border border-hairline bg-surface p-4 shadow-sm">
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="break-all text-small font-semibold text-ink">{MODELS.find((item) => item.id === forecast.model_name)?.label ?? forecast.model_name}</h3>
                <span className={`shrink-0 font-mono text-small font-semibold ${changeClass(forecast.predicted_return)}`}>{formatPercent(forecast.predicted_return)}</span>
              </div>
              <p className="mt-3 font-display text-heading font-semibold tabular-nums text-ink">{formatPrice(forecast.predicted_close, quoteCurrency)}</p>
              {isUsableNumber(forecast.actual_close) ? (
                <p className="mt-1 text-small text-muted">{vi ? "Đóng cửa thực tế" : "Actual close"}: {formatPrice(forecast.actual_close, quoteCurrency)}</p>
              ) : null}
              <details className="mt-3 border-t border-hairline pt-2 text-small">
                <summary className="cursor-pointer font-medium text-primary">{vi ? "Xem độ chính xác lịch sử" : "View historical accuracy"}</summary>
                <dl className="mt-2 flex justify-between gap-3 text-muted">
                  <div><dt>MAE</dt><dd className="font-mono text-ink">{metric && isUsableNumber(metric.mae) ? Number(metric.mae).toFixed(2) : "—"}</dd></div>
                  <div><dt>{vi ? "Đúng hướng" : "Direction"}</dt><dd className="font-mono text-ink">{metric && isUsableNumber(metric.directional_accuracy) ? formatPercent(metric.directional_accuracy) : "—"}</dd></div>
                </dl>
              </details>
            </article>
          );
        })}
      </div>
      <div className="hidden overflow-x-auto rounded border border-hairline bg-surface sm:block shadow-sm">
        <table className="w-full text-small">
          <thead>
            <tr className="border-b border-hairline text-left">
              <th className="px-4 py-3 font-mono text-label uppercase text-muted">
                Mô hình
              </th>
              <th className="px-4 py-3 text-right font-mono text-label uppercase text-muted">
                Dự báo
              </th>
              <th className="px-4 py-3 text-right font-mono text-label uppercase text-muted">
                Thay đổi
              </th>
              <th className="px-4 py-3 text-right font-mono text-label uppercase text-muted">
                MAE lịch sử
              </th>
              <th className="px-4 py-3 text-right font-mono text-label uppercase text-muted">
                Đúng hướng
              </th>
            </tr>
          </thead>
          <tbody>
            {forecasts.map((forecast) => {
              const metric = metricsByModel.get(forecast.model_name);
              const change = forecast.predicted_return;
              // Once the session has happened, the real close is known and
              // it is the most honest thing to show next to the forecast.
              const scored = isUsableNumber(forecast.actual_close);
              return (
                <tr
                  key={forecast.model_name}
                  className="border-b border-hairline last:border-b-0"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{MODELS.find((item) => item.id === forecast.model_name)?.label ?? forecast.model_name}</div>
                    {scored ? (
                      <div className="mt-1 font-mono text-label text-muted">
                        Thực tế {formatPrice(forecast.actual_close, quoteCurrency)}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-ink">
                    {formatPrice(forecast.predicted_close, quoteCurrency)}
                  </td>
                  <td
                    className={`px-4 py-3 text-right font-mono tabular-nums ${
                      isUsableNumber(change) ? changeClass(change) : "text-muted"
                    }`}
                  >
                    {formatPercent(change)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-muted">
                    {metric && isUsableNumber(metric.mae)
                      ? Number(metric.mae).toFixed(2)
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-muted">
                    {metric && isUsableNumber(metric.directional_accuracy)
                      ? formatPercent(metric.directional_accuracy)
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {silentModels.length > 0 ? (
        <p className="mt-3 text-label text-muted">
          Đã huấn luyện nhưng không có dự báo cho phiên này:{" "}
          {silentModels.map((m) => m.model_name).join(", ")}
        </p>
      ) : null}

      {targetSession ? <p className="mt-3 text-small text-muted">{vi ? "Phiên dự báo" : "Forecast session"}: {targetSession}</p> : null}
      <details className="mt-2 text-small text-muted">
        <summary className="cursor-pointer font-medium text-primary">{vi ? "Nguồn và cách đánh giá" : "Source and evaluation"}</summary>
        <p className="mt-2">{vi ? "Dự báo đã được ghi trước phiên. MAE và tỉ lệ đúng hướng đo trên dữ liệu kiểm tra lịch sử của từng mô hình." : "Forecasts were recorded before the session. MAE and directional accuracy come from each model's historical test set."}</p>
        <p className="mt-1 font-mono text-label">{forecasts[0]?.source ?? "auto_eod_batch"} · {forecasts[0]?.source_layer ?? "gold"}</p>
      </details>
    </div>
  );
}
