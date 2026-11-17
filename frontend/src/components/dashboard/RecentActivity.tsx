import { CheckCircle2, FlaskConical, History, XCircle, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface RecentActivityProps {
  pipeline?: Record<string, unknown> | null;
  model?: Record<string, unknown> | null;
  backtest?: Record<string, unknown> | null;
}

function StatusRow({
  icon,
  title,
  detail,
  ok,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  ok: boolean;
}) {
  return (
    <li className="flex items-center gap-3 border-b border-hairline py-3 last:border-b-0">
      <span className={ok ? "text-primary" : "text-muted"}>{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-small font-medium text-ink">{title}</div>
        <div className="truncate font-mono text-label text-muted">{detail}</div>
      </div>
      {ok ? (
        <CheckCircle2 size={15} className="shrink-0 text-primary" />
      ) : (
        <XCircle size={15} className="shrink-0 text-muted" />
      )}
    </li>
  );
}

/**
 * A status list.
 *
 * WHY A LIST AND NOT THREE CARDS: this panel answers one question — "what
 * has actually run?" — and the answer is a set of rows. Rows separated by
 * hairlines read as one column of related facts; three separate cards read
 * as three unrelated widgets that happen to be stacked.
 */
export function RecentActivity({ pipeline, model, backtest }: RecentActivityProps) {
  const { locale } = useI18n();

  return (
    <div>
      <div className="flex items-center gap-2 pb-3">
        <History size={14} className="text-muted" />
        <h2 className="font-display text-body font-semibold text-ink">
          {locale === "vi" ? "Hoạt động gần đây" : "Recent Activity"}
        </h2>
      </div>

      <ul>
        <StatusRow
          icon={<Zap size={14} />}
          title={locale === "vi" ? "Pipeline" : "Pipeline run"}
          detail={
            pipeline
              ? `${locale === "vi" ? "Trạng thái:" : "Status:"} ${String(pipeline.status ?? "ok")}`
              : locale === "vi" ? "Chưa chạy pipeline nào" : "No pipeline runs yet"
          }
          ok={Boolean(pipeline)}
        />
        <StatusRow
          icon={<FlaskConical size={14} />}
          title={locale === "vi" ? "Model gần nhất" : "Latest model"}
          detail={
            model
              ? `${String(model.model_name)} · MAE ${String(model.mae ?? "—")}`
              : locale === "vi" ? "Chưa train model" : "No model trained"
          }
          ok={Boolean(model)}
        />
        <StatusRow
          icon={<History size={14} />}
          title={locale === "vi" ? "Backtest gần nhất" : "Latest backtest"}
          detail={
            backtest
              ? `${String(backtest.strategy ?? "—")} · ${String(backtest.total_return != null ? `${(Number(backtest.total_return) * 100).toFixed(1)}%` : "—")}`
              : locale === "vi" ? "Chưa chạy backtest" : "No backtest run"
          }
          ok={Boolean(backtest)}
        />
      </ul>
    </div>
  );
}
