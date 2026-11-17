import { formatPercent, formatPrice, isUsableNumber } from "@/utils/format";
import { changeClass } from "@/utils/format";
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
 * committed to. The accuracy report on the Market Data page scores
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
  if (forecasts.length === 0) {
    return (
      <div className="rounded border border-hairline bg-surface px-4 py-6">
        <p className="text-small text-muted">
          {trainedModels.length > 0
            ? `${trainedModels.length} mô hình đã được huấn luyện cho ${symbol}, nhưng chưa có dự báo nào được ghi cho phiên này. Batch EOD sẽ ghi dự báo sau khi đóng cửa.`
            : `Chưa có mô hình nào được huấn luyện cho ${symbol}. Vào trang này để huấn luyện, hoặc chạy batch EOD.`}
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
      <div className="overflow-x-auto rounded border border-hairline bg-surface">
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
                    <div className="font-mono text-ink">{forecast.model_name}</div>
                    {scored ? (
                      <div className="mt-1 font-mono text-label text-muted">
                        Thực tế {formatPrice(forecast.actual_close, currency)}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-ink">
                    {formatPrice(forecast.predicted_close, currency)}
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

      {targetSession ? (
        <p className="mt-3 font-mono text-label uppercase text-muted">
          {targetSession} · nguồn:{" "}
          {forecasts[0]?.source ?? "auto_eod_batch"} · tầng:{" "}
          {forecasts[0]?.source_layer ?? "gold"}
        </p>
      ) : null}

      <p className="mt-3 text-label text-muted">
        MAE lịch sử và tỉ lệ đúng hướng là kết quả đo trên tập hold-out của từng
        mô hình. Dự báo ở trên là số hệ thống đã ghi xuống trước khi phiên mở
        cửa.
      </p>
    </div>
  );
}
