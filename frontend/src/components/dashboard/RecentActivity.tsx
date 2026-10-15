import { CheckCircle2, FlaskConical, History, XCircle, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface RecentActivityProps {
  pipeline?: Record<string, unknown> | null;
  model?: Record<string, unknown> | null;
  backtest?: Record<string, unknown> | null;
}

const TEAL = "hsl(165 52% 28%)";
const BORDER = "hsl(210 18% 90% / 0.6)";

function StatusRow({
  icon,
  title,
  detail,
  ok,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  ok: boolean;
  color?: string;
}) {
  const c = color || TEAL;
  return (
    <li
      className="flex items-center gap-3 rounded-xl border px-3 py-3 transition-all duration-200 hover:shadow-sm"
      style={{
        background: ok ? `${c}06` : "white",
        borderColor: ok ? `${c}20` : BORDER,
      }}
    >
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
        style={{
          background: ok ? `${c}12` : "hsl(210 20% 95%)",
          border: `1px solid ${ok ? `${c}25` : BORDER}`,
        }}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div
            className="truncate text-[13px] font-semibold"
            style={{ color: ok ? c : "hsl(220 25% 35%)" }}
          >
            {title}
          </div>
          {ok ? (
            <CheckCircle2 size={14} style={{ color: "hsl(152 58% 38%)", flexShrink: 0 }} />
          ) : (
            <XCircle size={14} className="flex-shrink-0" style={{ color: "hsl(220 12% 70%)" }} />
          )}
        </div>
        <div
          className="mt-0.5 truncate font-mono text-[11px]"
          style={{ color: ok ? "hsl(220 25% 30%)" : "hsl(220 12% 60%)" }}
        >
          {detail}
        </div>
      </div>
    </li>
  );
}

export function RecentActivity({ pipeline, model, backtest }: RecentActivityProps) {
  const { locale } = useI18n();

  return (
    <div className="p-4">
      {/* Header */}
      <div
        className="mb-3 flex items-center gap-2"
        style={{ borderBottom: `1px solid ${BORDER}`, paddingBottom: 12 }}
      >
        <History size={14} style={{ color: TEAL }} />
        <h3
          className="text-[14px] font-semibold"
          style={{ color: "hsl(220 25% 10%)" }}
        >
          {locale === "vi" ? "Hoạt động gần đây" : "Recent Activity"}
        </h3>
      </div>

      <ul className="space-y-2">
        <StatusRow
          icon={<Zap size={14} style={{ color: TEAL }} />}
          title={locale === "vi" ? "Pipeline" : "Pipeline run"}
          detail={
            pipeline
              ? `${locale === "vi" ? "Trạng thái:" : "Status:"} ${String(pipeline.status ?? "ok")}`
              : locale === "vi" ? "Chưa chạy pipeline nào" : "No pipeline runs yet"
          }
          ok={Boolean(pipeline)}
        />
        <StatusRow
          icon={<FlaskConical size={14} style={{ color: TEAL }} />}
          title={locale === "vi" ? "Model gần nhất" : "Latest model"}
          detail={
            model
              ? `${String(model.model_name)} · MAE ${String(model.mae ?? "—")}`
              : locale === "vi" ? "Chưa train model" : "No model trained"
          }
          ok={Boolean(model)}
        />
        <StatusRow
          icon={<History size={14} style={{ color: TEAL }} />}
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
