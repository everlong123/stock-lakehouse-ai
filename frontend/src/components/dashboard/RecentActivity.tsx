import { CheckCircle2, FlaskConical, History, XCircle, Zap } from "lucide-react";

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
    <li className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2">
      <span className="text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[13px] font-semibold text-foreground">{title}</div>
          {ok ? (
            <CheckCircle2 size={13} className="text-up" />
          ) : (
            <XCircle size={13} className="text-muted-foreground" />
          )}
        </div>
        <div className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{detail}</div>
      </div>
    </li>
  );
}

export function RecentActivity({ pipeline, model, backtest }: RecentActivityProps) {
  return (
    <div className="rounded-md border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <History size={14} className="text-muted-foreground" />
        <h3 className="text-sm font-semibold text-foreground">Hoat dong gan day</h3>
      </div>
      <ul className="space-y-2 p-3">
        <StatusRow
          icon={<Zap size={13} />}
          title="Pipeline run"
          detail={pipeline ? String(pipeline.status ?? "ok") : "Chua chay lan nao"}
          ok={Boolean(pipeline)}
        />
        <StatusRow
          icon={<FlaskConical size={13} />}
          title="Model moi nhat"
          detail={
            model
              ? `${String(model.model_name)} · MAE ${String(model.mae ?? "—")}`
              : "Chua train model"
          }
          ok={Boolean(model)}
        />
        <StatusRow
          icon={<History size={13} />}
          title="Backtest gan nhat"
          detail={backtest ? String(backtest.strategy ?? "ok") : "Chua chay backtest"}
          ok={Boolean(backtest)}
        />
      </ul>
    </div>
  );
}