import { formatPercent, formatPrice, isUsableNumber } from "@/utils/format";
import { changeClass } from "@/utils/format";

export interface NextSessionForecast {
  symbol: string;
  model_name: string;
  target_session: string | null;
  reference_close: number | null;
  predicted_close: number;
  predicted_return: number | null;
  horizon: number | null;
  source: string | null;
  source_layer: string | null;
  created_at: string | null;
}

interface NextSessionCardProps {
  forecast: NextSessionForecast | null;
  currency?: string | null;
  /**
   * How many models published a forecast for this session.
   *
   * WHY THIS IS A COUNT AND NOT A LIST: the Dashboard answers "what do
   * we expect next" with ONE number. The full per-model comparison lives
   * on the Models page, where the reader opens it deliberately. The count
   * is enough to say "two models agree on this" without turning the
   * summary card into a table.
   */
  modelCount?: number;
  /**
   * The historical MAE of the model that wrote this forecast.
   *
   * WHY IT IS SHOWN NEXT TO THE FORECAST: a forecast without its model's
   * track record is a number without context. The reader needs both to
   * judge it. It also means the card displays the system's own weak
   * spots instead of hiding them.
   */
  historicalMae?: number | null;
  historicalDirectionalAccuracy?: number | null;
}

/**
 * The next-session forecast.
 *
 * WHY THIS SHOWS A STORED NUMBER AND NOT A FRESH ONE: the card reads the
 * row the EOD batch wrote to the `predictions` table. That is the same
 * number the overnight run produced, so the page and the batch can never
 * disagree about what was forecast. A card that recomputed the forecast
 * on every render would show a different number each time the page was
 * opened, and the reader would have no way to tell which one the batch
 * had actually recorded.
 *
 * WHY IT SAYS WHEN IT WAS WRITTEN: a forecast without a date is a
 * prediction of the future made at an unknown time in the past. The
 * `created_at` line says when the batch ran, and `source` says whether it
 * was the overnight run or a manual call.
 *
 * WHY THERE IS NO NUMBER WHEN THERE IS NO FORECAST: the card renders an
 * explicit "no forecast" line. It never substitutes a moving average, a
 * last close, or a zero - a number that did not come from a model would
 * be a made-up number.
 *
 * WHY THIS CARD DOES NOT LIST EVERY MODEL: the Dashboard is the summary
 * of the CURRENT state. The per-model comparison belongs to the future
 * axis and lives on the Models page, which the card links to. One source
 * (`predictions`), two levels of detail.
 */
export function NextSessionCard({
  forecast,
  currency,
  modelCount,
  historicalMae,
  historicalDirectionalAccuracy,
}: NextSessionCardProps) {
  if (!forecast) {
    return (
      <div>
        <div className="label">Next session forecast</div>
        <p className="mt-2 text-small text-muted">
          Chưa có dự báo phiên kế tiếp. Batch EOD sẽ ghi dự báo này sau khi
          đóng cửa, hoặc gọi POST /api/v1/forecast/next-session/&lt;Mã&gt;/store.
        </p>
      </div>
    );
  }

  const change = forecast.predicted_return;
  const showMae = isUsableNumber(historicalMae);
  const showDa = isUsableNumber(historicalDirectionalAccuracy);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="label">Next session forecast</div>
          <div className="mt-1 truncate font-display text-body font-bold text-ink">
            {forecast.target_session ?? "—"}
          </div>
        </div>
        <span className="shrink-0 font-mono text-label uppercase text-muted">
          {forecast.model_name}
        </span>
      </div>

      <div className="mt-4 font-mono text-display font-semibold tabular-nums text-ink">
        {formatPrice(forecast.predicted_close, currency)}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-hairline pt-4">
        <div className="min-w-0">
          <dt className="label">Reference close</dt>
          <dd className="mt-1 truncate font-mono text-small tabular-nums text-ink">
            {formatPrice(forecast.reference_close, currency)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="label">Expected change</dt>
          <dd
            className={`mt-1 truncate font-mono text-small font-semibold tabular-nums ${
              isUsableNumber(change) ? changeClass(change) : "text-muted"
            }`}
          >
            {formatPercent(change)}
          </dd>
        </div>
        {/* The model's historical accuracy, so the forecast is read with
            its track record rather than on its own. */}
        <div className="min-w-0">
          <dt className="label">Sai số TB lịch sử</dt>
          <dd className="mt-1 truncate font-mono text-small tabular-nums text-ink">
            {showMae ? Number(historicalMae).toFixed(2) : "—"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="label">Đúng hướng</dt>
          <dd className="mt-1 truncate font-mono text-small tabular-nums text-ink">
            {showDa ? formatPercent(historicalDirectionalAccuracy) : "—"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="label">Source</dt>
          <dd className="mt-1 truncate font-mono text-small text-ink">
            {forecast.source ?? "auto_eod_batch"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="label">Layer</dt>
          <dd className="mt-1 truncate font-mono text-small text-ink">
            {forecast.source_layer ?? "gold"}
          </dd>
        </div>
      </dl>

      {/* The full comparison lives on the Models page. The card points at
          it instead of repeating it, so no number appears in two places
          for two different purposes. */}
      {modelCount && modelCount > 1 ? (
        <a
          href="/forecast"
          className="mt-4 block border-t border-hairline pt-3 font-mono text-label uppercase text-primary hover:underline"
        >
          {modelCount} mô hình đã dự báo phiên này · xem so sánh →
        </a>
      ) : null}

      {forecast.created_at ? (
        <p className="mt-3 font-mono text-label uppercase text-muted">
          {forecast.created_at.replace("T", " ").slice(0, 16)} UTC
        </p>
      ) : null}
    </div>
  );
}
