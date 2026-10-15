import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Brain,
  Database,
  HardDrive,
  Layers,
  Radio,
  Server,
  Sparkles,
} from "lucide-react";
import { fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Badge } from "@/components/ui/badge";
import { useI18n, t } from "@/lib/i18n";
import { relativeTime } from "@/utils/format";

const HEALTHY_STATUSES = new Set([
  "online", "connected", "enabled", "llm_ready", "local_tool_router",
  "sample", "yfinance", "local_storage_mode", "ready",
]);

const TEAL = "hsl(165 52% 28%)";
const BORDER = "hsl(210 18% 90% / 0.7)";

function isHealthy(status?: string): boolean {
  if (!status) return false;
  return HEALTHY_STATUSES.has(status) || status.includes("ready");
}

function ServiceTile({
  label,
  status,
  icon,
  sublabel,
}: {
  label: string;
  status: string;
  icon: React.ReactNode;
  sublabel?: string;
}) {
  const ok = isHealthy(status);
  const statusColor = ok ? "hsl(152 58% 38%)" : "hsl(220 12% 55%)";

  return (
    <div
      className="group relative overflow-hidden rounded-2xl border p-4 transition-all duration-300 hover:shadow-md hover:-translate-y-0.5"
      style={{
        background: ok ? "linear-gradient(135deg, hsl(152 58% 38% / 0.03) 0%, white 60%)" : "white",
        borderColor: BORDER,
        boxShadow: ok
          ? "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02), inset 0 1px 0 hsl(152 58% 38% / 0.1)"
          : "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)",
      }}
    >
      {/* Status accent dot */}
      <div
        className="absolute right-4 top-4 h-2 w-2 rounded-full"
        style={{
          background: statusColor,
          boxShadow: ok ? `0 0 6px ${statusColor}` : "none",
          animation: ok ? "pulse-ring 2s ease-in-out infinite" : "none",
        }}
      />

      <div className="flex items-start gap-3">
        {/* Icon container */}
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105"
          style={{
            background: ok
              ? `linear-gradient(135deg, hsl(165 52% 28%) 0%, hsl(165 58% 35%) 100%)`
              : "hsl(210 20% 95%)",
            boxShadow: ok ? "0 2px 8px hsl(165 52% 28% / 0.25)" : "none",
          }}
        >
          <span style={{ color: ok ? "white" : "hsl(220 12% 55%)" }}>{icon}</span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
            {label}
          </div>
          <div
            className="mt-1 font-mono text-[11px] capitalize"
            style={{ color: statusColor }}
          >
            {status.replaceAll("_", " ")}
          </div>
          {sublabel && (
            <div
              className="mt-0.5 font-mono text-[10px]"
              style={{ color: "hsl(220 12% 55%)" }}
            >
              {sublabel}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CountCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color?: string;
}) {
  const c = color || TEAL;
  return (
    <div
      className="group relative overflow-hidden rounded-2xl border p-5 transition-all duration-300 hover:shadow-md"
      style={{
        background: `linear-gradient(135deg, ${c}05 0%, white 70%)`,
        borderColor: `${c}20`,
        boxShadow: `0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)`,
      }}
    >
      {/* Top gradient bar */}
      <div
        className="absolute inset-x-0 top-0 h-[3px] rounded-t-2xl"
        style={{ background: `linear-gradient(90deg, ${c} 0%, ${c}60 100%)` }}
      />

      <div className="flex items-center gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{
            background: `${c}12`,
            border: `1px solid ${c}25`,
          }}
        >
          {icon}
        </div>
        <div>
          <div
            className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: "hsl(220 12% 50%)" }}
          >
            {label}
          </div>
          <div
            className="mt-1 font-mono text-[28px] font-bold"
            style={{ color: c, lineHeight: 1 }}
          >
            {value.toLocaleString("en-US")}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SystemStatusPage() {
  const { locale } = useI18n();
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    retry: 1,
    refetchInterval: 15000,
  });

  if (query.isLoading) return <Loading />;
  if (query.isError)
    return <ErrorState message={errorMessage(query.error, t("dashboard.err_connect", locale))} />;

  const data = query.data || {};
  const counts = (data.counts as Record<string, number>) || {};
  const lastRun = data.last_pipeline_run as Record<string, unknown> | undefined;

  const services = [
    {
      key: "backend_api",
      label: t("system.backend", locale),
      icon: <Server size={18} />,
      sublabel: "REST API",
    },
    {
      key: "mysql",
      label: t("system.mysql", locale),
      icon: <Database size={18} />,
      sublabel: "PostgreSQL / MySQL",
    },
    {
      key: "minio",
      label: t("system.minio", locale),
      icon: <HardDrive size={18} />,
      sublabel: data.storage_backend === "minio" ? "S3 Compatible" : "Local filesystem",
    },
    {
      key: "iceberg",
      label: t("system.iceberg", locale),
      icon: <Layers size={18} />,
      sublabel: "Iceberg REST",
    },
    {
      key: "kafka",
      label: t("system.kafka", locale),
      icon: <Radio size={18} />,
      sublabel: "Kafka Streams",
    },
    {
      key: "data_source",
      label: t("system.data_source", locale),
      icon: <Activity size={18} />,
      sublabel: String(data.data_source || "—"),
    },
    {
      key: "ai_agent",
      label: t("system.ai_agent", locale),
      icon: <Sparkles size={18} />,
      sublabel: String((data.ai_agent as { status?: string })?.status || "—"),
    },
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title={t("system.title", locale)}
        subtitle={
          locale === "vi"
            ? "Trạng thái các service trong hệ thống Lakehouse. Auto-refresh mỗi 15 giây."
            : "Status of all services in the Lakehouse. Auto-refresh every 15s."
        }
        meta="07 · Platform"
      />

      {/* ── Service grid ─────────────────────────────────────── */}
      <section>
        <div
          className="mb-3 font-mono text-[10px] uppercase tracking-widest"
          style={{ color: "hsl(220 12% 50%)" }}
        >
          {locale === "vi" ? "Services" : "Services"}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {services.map((s) => {
            const info = data[s.key] as { status: string; label?: string } | undefined;
            return (
              <ServiceTile
                key={s.key}
                label={info?.label || s.label}
                status={info?.status || "unknown"}
                icon={s.icon}
                sublabel={s.sublabel}
              />
            );
          })}
        </div>
      </section>

      {/* ── Layer counts ─────────────────────────────────────── */}
      <section>
        <div
          className="mb-3 font-mono text-[10px] uppercase tracking-widest"
          style={{ color: "hsl(220 12% 50%)" }}
        >
          {t("system.counts", locale)}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <CountCard
            label={t("system.bronze", locale)}
            value={counts.bronze ?? 0}
            icon={<Database size={18} style={{ color: "hsl(165 52% 28%)" }} />}
          />
          <CountCard
            label={t("system.silver", locale)}
            value={counts.silver ?? 0}
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="hsl(220 50% 55%)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
                <line x1="12" y1="22" x2="12" y2="15.5" />
                <polyline points="22 8.5 12 15.5 2 8.5" />
              </svg>
            }
          />
          <CountCard
            label={t("system.gold", locale)}
            value={counts.gold ?? 0}
            icon={<Brain size={18} style={{ color: "hsl(45 85% 50%)" }} />}
          />
        </div>
      </section>

      {/* ── Last pipeline run ─────────────────────────────────── */}
      {lastRun ? (
        <section>
          <div
            className="mb-3 font-mono text-[10px] uppercase tracking-widest"
            style={{ color: "hsl(220 12% 50%)" }}
          >
            {locale === "vi" ? "Lần chạy pipeline gần nhất" : "Last pipeline run"}
          </div>
          <div
            className="overflow-hidden rounded-2xl border"
            style={{
              borderColor: BORDER,
              background: "white",
              boxShadow: "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)",
            }}
          >
            <div
              className="flex items-center gap-3 border-b px-5 py-4"
              style={{ borderColor: BORDER }}
            >
              <div
                className="flex h-8 w-8 items-center justify-center rounded-lg"
                style={{ background: "hsl(165 52% 28% / 0.1)", border: "1px solid hsl(165 52% 28% / 0.2)" }}
              >
                <Activity size={14} style={{ color: TEAL }} />
              </div>
              <div className="flex-1">
                <div className="font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
                  {String(lastRun.run_id ?? "—")}
                </div>
                <div className="text-[11px]" style={{ color: "hsl(220 12% 50%)" }}>
                  {relativeTime(lastRun.completed_at as string)}
                </div>
              </div>
              <Badge
                variant={lastRun.status === "success" ? "success" : "warn"}
                style={{
                  background: lastRun.status === "success" ? "hsl(152 58% 38% / 0.1)" : "hsl(38 92% 50% / 0.1)",
                  border: lastRun.status === "success" ? "1px solid hsl(152 58% 38% / 0.3)" : "1px solid hsl(38 92% 50% / 0.3)",
                  color: lastRun.status === "success" ? "hsl(152 58% 38%)" : "hsl(38 92% 50%)",
                }}
              >
                {String(lastRun.status ?? "—")}
              </Badge>
            </div>
            <div className="grid gap-4 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "hsl(220 12% 55%)" }}>
                  Symbols
                </div>
                <div className="mt-1 text-[13px] font-medium">
                  {Array.isArray(lastRun.symbols_processed)
                    ? (lastRun.symbols_processed as string[]).join(", ")
                    : "—"}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "hsl(220 12% 55%)" }}>
                  Bronze
                </div>
                <div className="mt-1 font-mono text-[13px] font-medium">
                  {Number(lastRun.bronze_records ?? 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "hsl(220 12% 55%)" }}>
                  Silver
                </div>
                <div className="mt-1 font-mono text-[13px] font-medium">
                  {Number(lastRun.silver_records ?? 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "hsl(220 12% 55%)" }}>
                  Quality
                </div>
                <div className="mt-1 font-mono text-[13px] font-medium">
                  {(Number(lastRun.quality_score ?? 0)).toFixed(1)}%
                </div>
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
