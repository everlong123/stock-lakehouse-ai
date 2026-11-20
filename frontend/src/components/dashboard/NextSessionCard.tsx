import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown, TrendingDown, TrendingUp } from "lucide-react";
import { changeClass, formatPercent, formatPrice, isUsableNumber } from "@/utils/format";
import { useI18n } from "@/lib/i18n";
import { MODELS } from "@/utils/constants";
import { cn } from "@/lib/utils";

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
  data_staleness_days?: number | null;
  created_at: string | null;
}

interface NextSessionCardProps {
  forecast: NextSessionForecast | null;
  currency?: string | null;
  modelCount?: number;
  historicalMae?: number | null;
  historicalDirectionalAccuracy?: number | null;
}

/**
 * The next-session forecast.
 *
 * WHY IT IS A RAISED PANEL
 * ------------------------
 * It is the one card on the quote page that carries a CLAIM about the
 * future, and it is the thing a reader opens the page to find. So it is
 * lifted off the canvas with a shadow, and the predicted price is set in
 * the direction colour of its own return — the reader sees "down" before
 * they read the number.
 */
export function NextSessionCard({ forecast, currency, modelCount, historicalMae, historicalDirectionalAccuracy }: NextSessionCardProps) {
  const { locale } = useI18n();
  const vi = locale === "vi";
  const [open, setOpen] = useState(false);

  const direction = isUsableNumber(forecast?.predicted_return)
    ? forecast.predicted_return > 0
      ? "up"
      : forecast.predicted_return < 0
        ? "down"
        : "flat"
    : "flat";
  const DirectionIcon = direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : null;

  return (
    <section className="rounded border border-hairline bg-surface p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-body font-semibold text-ink">{vi ? "Dự báo phiên kế tiếp" : "Next session forecast"}</h2>
          <p className="mt-1 font-mono text-label text-muted">
            {forecast?.target_session?.slice(0, 10) ?? (vi ? "Chưa có phiên dự báo" : "No forecast session")}
          </p>
        </div>
        {forecast ? (
          <span className="shrink-0 rounded bg-surface-2 px-2 py-1 text-label font-medium text-muted">
            {MODELS.find((item) => item.id === forecast.model_name)?.label ?? forecast.model_name}
          </span>
        ) : null}
      </div>

      {!forecast ? (
        <p className="mt-5 text-small text-muted">
          {vi ? "Chưa có dự báo được công bố cho mã này. Xem trang Dự báo để kiểm tra mô hình." : "No published forecast for this stock. Check model availability on the Forecast page."}
        </p>
      ) : (
        <>
          <p
            className={cn(
              "mt-5 font-display text-heading font-semibold tabular-nums",
              direction === "up" ? "text-up" : direction === "down" ? "text-negative" : "text-ink",
            )}
          >
            {formatPrice(forecast.predicted_close, currency)}
          </p>
          <p className={cn("mt-1 flex items-center gap-1.5 font-mono text-small font-semibold tabular-nums", changeClass(forecast.predicted_return))}>
            {DirectionIcon ? <DirectionIcon size={14} aria-hidden="true" /> : null}
            {formatPercent(forecast.predicted_return)}{" "}
            <span className="font-sans font-normal text-muted">
              {vi ? "so với giá tham chiếu" : "from reference close"}
            </span>
          </p>
          {typeof forecast.data_staleness_days === "number" && forecast.data_staleness_days > 0 ? (
            <p role="status" className="mt-4 border-l-2 border-negative pl-3 text-small text-negative">
              {vi ? `Dữ liệu đầu vào trễ ${forecast.data_staleness_days} phiên giao dịch.` : `Input data is ${forecast.data_staleness_days} trading sessions behind.`}
            </p>
          ) : null}

          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-5 flex w-full items-center justify-between border-t border-hairline pt-3 text-small font-medium text-muted transition-colors hover:text-ink"
          >
            {vi ? "Độ tin cậy & nguồn" : "Accuracy & source"}
            <ChevronDown size={15} className={cn("transition-transform duration-200", open && "rotate-180")} />
          </button>
          {open ? (
            <dl className="animate-fade-in mt-3 grid grid-cols-2 gap-3 text-small">
              <div>
                <dt className="text-muted">{vi ? "Giá tham chiếu" : "Reference close"}</dt>
                <dd className="font-mono text-ink">{formatPrice(forecast.reference_close, currency)}</dd>
              </div>
              <div>
                <dt className="text-muted">{vi ? "Sai số TB lịch sử" : "Historical MAE"}</dt>
                <dd className="font-mono text-ink">
                  {isUsableNumber(historicalMae) ? Number(historicalMae).toFixed(2) : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{vi ? "Đúng hướng" : "Direction accuracy"}</dt>
                <dd className="font-mono text-ink">
                  {isUsableNumber(historicalDirectionalAccuracy) ? formatPercent(historicalDirectionalAccuracy) : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{vi ? "Nguồn" : "Source"}</dt>
                <dd className="break-all text-ink">{forecast.source ?? "—"}</dd>
              </div>
            </dl>
          ) : null}
          {forecast.created_at ? (
            <p className="mt-3 font-mono text-label text-muted">
              {vi ? "Công bố" : "Published"}: {forecast.created_at.replace("T", " ").slice(0, 16)} UTC
            </p>
          ) : null}
        </>
      )}

      <Link
        to="/forecast"
        className="mt-5 inline-flex items-center gap-2 text-small font-semibold text-primary transition-colors hover:gap-2.5"
      >
        {vi
          ? modelCount && modelCount > 1
            ? `So sánh ${modelCount} mô hình`
            : "Xem dự báo"
          : modelCount && modelCount > 1
            ? `Compare ${modelCount} models`
            : "Explore forecasts"}
        <ArrowRight size={15} />
      </Link>
      <p className="mt-3 font-mono text-label text-muted">
        {vi ? "Chỉ mang tính tham khảo, không phải khuyến nghị đầu tư." : "For reference only, not investment advice."}
      </p>
    </section>
  );
}
