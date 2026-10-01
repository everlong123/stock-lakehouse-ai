import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  Database,
  HardDrive,
  Layers,
  Radio,
  Server,
  Sparkles,
  XCircle,
} from "lucide-react";
import { fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/utils/format";

const HEALTHY_STATUSES = new Set([
  "online", "connected", "enabled", "llm_ready", "local_tool_router",
  "sample", "yfinance", "local_storage_mode", "ready",
]);

function isHealthy(status?: string): boolean {
  if (!status) return false;
  return HEALTHY_STATUSES.has(status) || status.includes("ready");
}

interface ServiceTileProps {
  label: string;
  status: string;
  icon: React.ReactNode;
}

function ServiceTile({ label, status, icon }: ServiceTileProps) {
  const ok = isHealthy(status);
  return (
    <div className="card-elevated relative overflow-hidden p-5">
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-1",
          ok ? "bg-gradient-to-r from-brand-400 to-brand-600" : "bg-muted",
        )}
      />
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-xl",
              ok ? "bg-brand-50 text-brand-700" : "bg-muted text-muted-foreground",
            )}
          >
            {icon}
          </div>
          <div>
            <div className="text-sm font-bold text-foreground">{label}</div>
            <div className="font-mono text-xs text-muted-foreground">{status.replaceAll("_", " ")}</div>
          </div>
        </div>
        {ok ? (
          <CheckCircle2 size={18} className="text-brand-600" />
        ) : (
          <XCircle size={18} className="text-muted-foreground" />
        )}
      </div>
    </div>
  );
}

export function SystemStatusPage() {
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    retry: 1,
    refetchInterval: 15000,
  });

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Không kết nối được backend API.")} />;

  const data = query.data || {};
  const counts = (data.counts as Record<string, number>) || {};
  const lastRun = data.last_pipeline_run as Record<string, unknown> | undefined;

  const services = [
    { key: "backend_api", label: "Backend API", icon: <Server size={16} /> },
    { key: "mysql",       label: "MySQL",       icon: <Database size={16} /> },
    { key: "minio",       label: "MinIO (S3)",  icon: <HardDrive size={16} /> },
    { key: "iceberg",     label: "Iceberg REST", icon: <Layers size={16} /> },
    { key: "kafka",       label: "Kafka",       icon: <Radio size={16} /> },
    { key: "data_source", label: "Data Source", icon: <Activity size={16} /> },
    { key: "ai_agent",    label: "AI Agent",    icon: <Sparkles size={16} /> },
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title="System Status"
        subtitle="Trạng thái các service trong hệ thống Lakehouse. Auto-refresh mỗi 15 giây."
        badge="Live"
      />

      {/* Service tiles */}
      <section>
        <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Services
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {services.map((s) => {
            const info = data[s.key] as { status: string; label?: string } | undefined;
            return (
              <ServiceTile
                key={s.key}
                label={info?.label || s.label}
                status={info?.status || "unknown"}
                icon={s.icon}
              />
            );
          })}
        </div>
      </section>

      {/* Layer counts */}
      <section>
        <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Medallion counts
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { label: "Bronze records", value: counts.bronze ?? 0, color: "from-amber-50 to-amber-100" },
            { label: "Silver records", value: counts.silver ?? 0, color: "from-slate-50 to-slate-100" },
            { label: "Gold records",   value: counts.gold ?? 0,   color: "from-brand-50 to-brand-100" },
          ].map((c) => (
            <Card key={c.label} className={cn("bg-gradient-to-br p-5", c.color)}>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {c.label}
              </div>
              <div className="mt-2 font-mono text-3xl font-bold text-foreground">
                {c.value.toLocaleString("en-US")}
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* Last pipeline run */}
      {lastRun ? (
        <section>
          <h2 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Last pipeline run
          </h2>
          <Card className="p-5">
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Run ID
                </div>
                <div className="mt-1 font-mono text-sm font-bold">{String(lastRun.run_id ?? "—")}</div>
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Status
                </div>
                <div className="mt-1">
                  <Badge variant={lastRun.status === "success" ? "primary" : "warn"}>
                    {String(lastRun.status ?? "—")}
                  </Badge>
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Symbols
                </div>
                <div className="mt-1 text-sm font-semibold">
                  {Array.isArray(lastRun.symbols_processed)
                    ? (lastRun.symbols_processed as string[]).join(", ")
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Cập nhật
                </div>
                <div className="mt-1 text-sm">
                  {relativeTime(lastRun.completed_at as string)}
                </div>
              </div>
            </div>
          </Card>
        </section>
      ) : null}
    </div>
  );
}