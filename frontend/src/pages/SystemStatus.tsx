import { useQuery } from "@tanstack/react-query";
import { fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";

function StatusDot({ online }: { online: boolean }) {
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${online ? "bg-up" : "bg-muted-foreground"}`} />;
}

export function SystemStatusPage() {
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    retry: 1,
    refetchInterval: 15000,
  });

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Cannot connect to backend API.")} />;
  const data = query.data || {};
  const items = ["backend_api", "mysql", "minio", "spark", "data_source", "ai_agent"]
    .map((key) => data[key] as { label: string; status: string } | undefined)
    .filter(Boolean) as { label: string; status: string }[];
  const counts = (data.counts as Record<string, number>) || {};

  return (
    <div className="space-y-4">
      <PageTitle title="System Status" subtitle="Health of API, MySQL, storage, Spark and the AI agent." />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const online = !["disconnected", "disabled_pandas_mode", "local_storage_mode"].includes(item.status)
            ? item.status !== "disconnected"
            : item.label === "Backend API" || item.status.includes("ready") || item.status === "online" || item.status === "connected" || item.status === "enabled" || item.status === "llm_ready" || item.status === "local_tool_router" || item.status === "sample" || item.status === "yfinance" || item.status === "local_storage_mode" || item.status === "disabled_pandas_mode";
          const isLive = ["online", "connected", "enabled", "llm_ready", "local_tool_router", "sample", "yfinance"].includes(item.status);
          return (
            <div key={item.label} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <StatusDot online={isLive || online} />
                {item.label}
              </div>
              <div className="mt-2 font-mono text-sm text-muted-foreground">{item.status.replaceAll("_", " ")}</div>
            </div>
          );
        })}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4">Bronze count: {counts.bronze ?? 0}</div>
        <div className="rounded-lg border border-border bg-card p-4">Silver count: {counts.silver ?? 0}</div>
        <div className="rounded-lg border border-border bg-card p-4">Gold count: {counts.gold ?? 0}</div>
      </div>
    </div>
  );
}
