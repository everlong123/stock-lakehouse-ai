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
import { relativeTime } from "@/utils/format";

const HEALTHY_STATUSES = new Set([
  "online", "connected", "enabled", "llm_ready", "local_tool_router",
  "sample", "yfinance", "local_storage_mode", "ready",
]);

function isHealthy(status?: string): boolean {
  if (!status) return false;
  return HEALTHY_STATUSES.has(status) || status.includes("ready");
}

function ServiceTile({
  label,
  status,
  icon,
}: {
  label: string;
  status: string;
  icon: React.ReactNode;
}) {
  const ok = isHealthy(status);
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground">{icon}</span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-foreground">{label}</div>
            <div className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {status.replaceAll("_", " ")}
            </div>
          </div>
        </div>
        {ok ? <CheckCircle2 size={14} className="text-up" /> : <XCircle size={14} className="text-muted-foreground" />}
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
  if (query.isError)
    return <ErrorState message={errorMessage(query.error, "Khong ket noi duoc backend API.")} />;

  const data = query.data || {};
  const counts = (data.counts as Record<string, number>) || {};
  const lastRun = data.last_pipeline_run as Record<string, unknown> | undefined;

  const services = [
    { key: "backend_api", label: "Backend API", icon: <Server size={14} /> },
    { key: "mysql",       label: "MySQL",       icon: <Database size={14} /> },
    { key: "minio",       label: "MinIO (S3)",  icon: <HardDrive size={14} /> },
    { key: "iceberg",     label: "Iceberg REST", icon: <Layers size={14} /> },
    { key: "kafka",       label: "Kafka",       icon: <Radio size={14} /> },
    { key: "data_source", label: "Data Source", icon: <Activity size={14} /> },
    { key: "ai_agent",    label: "AI Agent",    icon: <Sparkles size={14} /> },
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title="System status"
        subtitle="Trang thai cac service trong he thong Lakehouse. Auto-refresh moi 15 giay."
        meta="07 · Platform"
      />

      <section>
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Services
        </h2>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
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

      <section>
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Medallion counts
        </h2>
        <div className="grid gap-2 md:grid-cols-3">
          {[
            { label: "Bronze records", value: counts.bronze ?? 0 },
            { label: "Silver records", value: counts.silver ?? 0 },
            { label: "Gold records",   value: counts.gold ?? 0 },
          ].map((c) => (
            <div key={c.label} className="rounded-md border border-border bg-card p-4">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {c.label}
              </div>
              <div className="mt-2 font-mono text-[24px] font-semibold text-foreground">
                {c.value.toLocaleString("en-US")}
              </div>
            </div>
          ))}
        </div>
      </section>

      {lastRun ? (
        <section>
          <h2 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Last pipeline run
          </h2>
          <Card className="p-4">
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Run ID
                </div>
                <div className="mt-1 font-mono text-[13px] font-semibold">{String(lastRun.run_id ?? "—")}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Status
                </div>
                <div className="mt-1">
                  <Badge variant={lastRun.status === "success" ? "success" : "warn"}>
                    {String(lastRun.status ?? "—")}
                  </Badge>
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Symbols
                </div>
                <div className="mt-1 text-[13px] font-semibold">
                  {Array.isArray(lastRun.symbols_processed)
                    ? (lastRun.symbols_processed as string[]).join(", ")
                    : "—"}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Cap nhat
                </div>
                <div className="mt-1 text-[13px]">
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