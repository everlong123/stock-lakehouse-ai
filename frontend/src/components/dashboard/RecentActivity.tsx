import { CheckCircle2, FlaskConical, History, Zap } from "lucide-react";

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
    <li className="flex items-start gap-3 rounded-lg border border-border bg-background p-3">
      <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${ok ? "bg-brand-50 text-brand-700" : "bg-muted text-muted-foreground"}`}>
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-foreground">{title}</div>
          {ok ? <CheckCircle2 size={14} className="text-brand-600" /> : null}
        </div>
        <div className="mt-0.5 truncate text-[12px] text-muted-foreground">{detail}</div>
      </div>
    </li>
  );
}

export function RecentActivity({ pipeline, model, backtest }: RecentActivityProps) {
  return (
    <div className="card-elevated p-5">
      <div className="mb-3 flex items-center gap-2">
        <History size={14} className="text-brand-600" />
        <h3 className="text-sm font-bold text-foreground">Hoạt động gần đây</h3>
      </div>
      <ul className="space-y-2">
        <StatusRow
          icon={<Zap size={14} />}
          title="Pipeline run"
          detail={pipeline ? String(pipeline.status ?? "ok") : "Chưa chạy lần nào"}
          ok={Boolean(pipeline)}
        />
        <StatusRow
          icon={<FlaskConical size={14} />}
          title="Model mới nhất"
          detail={
            model
              ? `${String(model.model_name)} · MAE ${String(model.mae ?? "—")}`
              : "Chưa train model"
          }
          ok={Boolean(model)}
        />
        <StatusRow
          icon={<History size={14} />}
          title="Backtest gần nhất"
          detail={backtest ? String(backtest.strategy ?? "ok") : "Chưa chạy backtest"}
          ok={Boolean(backtest)}
        />
      </ul>
    </div>
  );
}