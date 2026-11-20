import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Database,
  HardDrive,
  Server,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageHeader } from "@/components/common/PageHeader";
import { QualityGatePanel } from "@/components/quality/QualityGatePanel";
import { Badge } from "@/components/ui/badge";
import { useI18n, t } from "@/lib/i18n";
import { relativeTime } from "@/utils/format";

const HEALTHY_STATUSES = new Set([
  "online", "connected", "enabled", "llm_ready", "local_tool_router",
  "sample", "yfinance", "local_storage_mode", "ready",
  // The quality gate's verdict. "passed" means every check ran and the data
  // was verified. "warning" and "failed" are deliberately NOT in this set:
  // a warning is not healthy, and a failed check is not healthy, and the
  // dot on the row has to tell the truth.
  "passed",
]);

function isHealthy(status?: string): boolean {
  if (!status) return false;
  return HEALTHY_STATUSES.has(status) || status.includes("ready");
}

/**
 * One service row.
 *
 * WHY A ROW AND NOT A TILE: a status page is a checklist. Seven tiles in a
 * grid means the reader scans a wall of boxes and has to hunt for the one
 * that is broken. As rows, the healthy ones take up one line each and the
 * broken one stands out immediately because it is the only row with a red
 * dot.
 */
function ServiceRow({
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

  return (
    <li className="flex items-center gap-4 border-b border-hairline py-3 last:border-b-0">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded border ${
          ok ? "border-primary/30 bg-primary/10 text-primary" : "border-hairline bg-surface-2 text-muted"
        }`}
      >
        {icon}
      </span>

      <div className="min-w-0 flex-1">
        <div className="truncate text-small font-semibold text-ink">{label}</div>
        {sublabel ? (
          <div className="truncate font-mono text-label text-muted">{sublabel}</div>
        ) : null}
      </div>

      <div className="shrink-0 text-right">
        <div
          className={`font-mono text-label capitalize ${ok ? "text-primary" : "text-muted"}`}
        >
          {status.replaceAll("_", " ")}
        </div>
      </div>

      <span
        className={`dot shrink-0 ${ok ? "dot-live" : ""}`}
        aria-label={ok ? "healthy" : "not healthy"}
      />
    </li>
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
      icon: <Server size={15} />,
      sublabel: "REST API",
    },
    {
      key: "mysql",
      label: t("system.mysql", locale),
      icon: <Database size={15} />,
      sublabel: "PostgreSQL / MySQL",
    },
    {
      key: "minio",
      label: t("system.minio", locale),
      icon: <HardDrive size={15} />,
      sublabel: data.storage_backend === "minio" ? "S3 Compatible" : "Local filesystem",
    },
    {
      key: "data_source",
      label: t("system.data_source", locale),
      icon: <Activity size={15} />,
      // WHY the guard: `/system/status` returns `data_source` as an OBJECT
      // ({label, status}), like every other service entry - not as a plain
      // string. `String(obj)` on it renders the literal text "[object
      // Object]", which is what this page used to show.
      sublabel:
        typeof data.data_source === "object" && data.data_source !== null
          ? String((data.data_source as { status?: string })?.status ?? "?")
          : String(data.data_source || "?"),
    },
    {
      key: "ai_agent",
      label: t("system.ai_agent", locale),
      icon: <Sparkles size={15} />,
      sublabel: String((data.ai_agent as { status?: string })?.status || "?"),
    },
    {
      // WHY THE DATA QUALITY ROW IS IN THE SERVICE LIST: every other row
      // says a service is up; this one says whether the DATA is right.
      // A backend that is fully online while serving corrupted prices is
      // not healthy, and this is the row that says so.
      key: "data_quality",
      label: t("system.data_quality", locale),
      icon: <ShieldCheck size={15} />,
      sublabel: String(
        (data.data_quality as { checked_at?: string })?.checked_at
          ? relativeTime((data.data_quality as { checked_at: string }).checked_at)
          : "—",
      ),
    },
  ];

  const layerCounts = [
    { key: "bronze", label: t("system.bronze", locale) },
    { key: "silver", label: t("system.silver", locale) },
    { key: "gold", label: t("system.gold", locale) },
  ];

  return (
    <div className="space-y-10">
      {/*
        ── The page header ───────────────────────────────────────────
        The refresh cadence is stated in the subtitle, because a status
        page that auto-refreshes without saying so makes a reader wonder
        whether the numbers they are looking at are stale.
      */}
      <PageHeader
        section="Hệ thống"
        title={t("system.title", locale)}
        subtitle={
          locale === "vi"
            ? "Trạng thái các service trong hệ thống Lakehouse. Tự làm mới mỗi 15 giây."
            : "Status of all services in the Lakehouse. Auto-refresh every 15s."
        }
        aside={
          <span className="inline-flex items-center gap-2 font-mono text-label uppercase text-muted">
            <span className="dot dot-live" />
            {query.isFetching
              ? (locale === "vi" ? "Đang làm mới" : "Refreshing")
              : (locale === "vi" ? "Trực tiếp" : "Live")}
          </span>
        }
      />

      {/* ── The layer counts ─────────────────────────────────────────
          Three numbers that answer "how much data does this system
          actually hold". They are the first thing a reader of a status
          page wants, so they sit above the service checklist rather
          than beside it in a narrow column. */}
      <div className="grid grid-cols-3 gap-6 border-y border-hairline py-6">
        {layerCounts.map(({ key, label }) => (
          <div key={key} className="min-w-0">
            <div className="label">{label}</div>
            <div className="mt-1 font-mono text-heading font-semibold tabular-nums text-ink">
              {(counts[key] ?? 0).toLocaleString("en-US")}
            </div>
          </div>
        ))}
      </div>

      {/* Services: one checklist column, on the left. */}
      <div className="grid gap-12 xl:grid-cols-3">
        <section className="xl:col-span-2">
          <div className="section-head">
            <h2 className="section-title">Services</h2>
            <span className="font-mono text-label uppercase text-muted">
              {services.length} mã
            </span>
          </div>
          <ul className="pt-2">
            {services.map((s) => {
              const info = data[s.key] as { status: string; label?: string } | undefined;
              return (
                <ServiceRow
                  key={s.key}
                  label={info?.label || s.label}
                  status={info?.status || "unknown"}
                  icon={s.icon}
                  sublabel={s.sublabel}
                />
              );
            })}
          </ul>
        </section>

        <aside>
          {/* Data quality gate: the one panel that says whether the DATA
              is right. It moved into this column because it is the
              counterpart of the service checklist: "the services are up"
              and "the data is good" are two different claims. */}
          <QualityGatePanel />
        </aside>
      </div>

      {/* Last pipeline run */}
      {lastRun ? (
        <section>
          <div className="section-head">
            <div className="flex items-center gap-3">
              <Activity size={16} className="text-primary" />
              <h2 className="section-title">
                {locale === "vi" ? "Lần chạy pipeline gần nhất" : "Last pipeline run"}
              </h2>
            </div>
            <Badge variant={lastRun.status === "success" ? "primary" : "negative"}>
              {String(lastRun.status ?? "?")}
            </Badge>
          </div>

          <div className="mt-4 grid gap-6 border-y border-hairline py-6 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="label">Run ID</div>
              <div className="mt-1 truncate font-mono text-small font-medium text-ink">
                {String(lastRun.run_id ?? "?")}
              </div>
              <div className="mt-1 font-mono text-label text-muted">
                {relativeTime(lastRun.completed_at as string)}
              </div>
            </div>
            <div>
              <div className="label">Symbols</div>
              <div className="mt-1 truncate font-mono text-small font-medium text-ink">
                {Array.isArray(lastRun.symbols_processed)
                  ? (lastRun.symbols_processed as string[]).join(", ")
                  : "?"}
              </div>
            </div>
            <div>
              <div className="label">Bronze records</div>
              <div className="mt-1 font-mono text-small font-medium tabular-nums text-ink">
                {Number(lastRun.bronze_records ?? 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div className="label">Quality</div>
              <div className="mt-1 font-mono text-small font-medium tabular-nums text-ink">
                {(Number(lastRun.quality_score ?? 0)).toFixed(1)}%
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
