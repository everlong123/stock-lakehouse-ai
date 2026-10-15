import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, RefreshCcw, Radio, Send } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchStreamHistory,
  fetchStreamLatest,
  fetchStreamStats,
  ingestStreamBars,
  StreamBar,
  subscribeStream,
} from "@/api/stream";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { useI18n, t } from "@/lib/i18n";

interface MultiLatestPayload {
  bars: Record<string, StreamBar>;
  stats: {
    symbols_tracked: number;
    total_recorded: number;
    started_at: string;
    uptime_seconds: number;
  };
}

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  fontSize: 12,
};

// Demo bars so the page is interactive even before Kafka is wired up.
const DEMO_BARS: Record<string, Array<Omit<StreamBar, "received_at" | "source">>> = {
  AAPL: [
    { symbol: "AAPL", timestamp: "", open: 332.5, high: 333.1, low: 331.8, close: 332.7, volume: 12000 },
    { symbol: "AAPL", timestamp: "", open: 332.7, high: 333.9, low: 332.5, close: 333.7, volume: 14500 },
    { symbol: "AAPL", timestamp: "", open: 333.7, high: 334.2, low: 333.1, close: 333.9, volume: 18900 },
  ],
  MSFT: [
    { symbol: "MSFT", timestamp: "", open: 415.2, high: 416.0, low: 414.8, close: 415.9, volume: 9000 },
    { symbol: "MSFT", timestamp: "", open: 415.9, high: 416.7, low: 415.6, close: 416.4, volume: 11200 },
  ],
  NVDA: [
    { symbol: "NVDA", timestamp: "", open: 510.0, high: 512.4, low: 509.5, close: 511.8, volume: 22000 },
  ],
};

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

function nowIso(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
}

export function LiveStreamPage() {
  const { locale } = useI18n();
  const queryClient = useQueryClient();
  const [pulse, setPulse] = useState(0);
  const [sseConnected, setSseConnected] = useState(false);

  // Stats are pulled once on mount + after manual ingests; they're cheap and
  // don't need sub-second freshness.
  const statsQuery = useQuery({
    queryKey: ["stream", "stats"],
    queryFn: fetchStreamStats,
    refetchInterval: 5000,
    retry: 1,
  });

  // Initial snapshot so the page renders before the first SSE event arrives.
  // After mount we ditch polling entirely and rely on the push stream below.
  const latestQuery = useQuery({
    queryKey: ["stream", "latest"],
    queryFn: () => fetchStreamLatest(),
    refetchInterval: false,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  // Open a single SSE connection to the backend. Every bar pushed by the
  // Kafka consumer (or by manual /stream/ingest) lands here in real time.
  useEffect(() => {
    const sub = subscribeStream(
      (event) => {
        if (event.type === "hello") {
          setSseConnected(true);
          return;
        }
        if (event.type !== "bar") return;
        const bar = event.data as StreamBar;
        queryClient.setQueryData<MultiLatestPayload>(["stream", "latest"], (prev) => {
          const bars = { ...(prev?.bars ?? {}), [bar.symbol]: bar };
          const stats = prev?.stats ?? {
            symbols_tracked: Object.keys(bars).length,
            total_recorded: 0,
            started_at: new Date().toISOString(),
            uptime_seconds: 0,
          };
          return { bars, stats };
        });
        // Invalidate per-symbol history queries so the chart re-fetches the
        // rolling window including the new bar. TanStack dedupes calls in
        // flight, so this is safe even when 8+ symbols update at once.
        queryClient.invalidateQueries({ queryKey: ["stream", "history", bar.symbol] });
        // Bump the pulse so the "live" dot blinks on every new tick.
        setPulse((n) => n + 1);
      },
      {
        onError: () => setSseConnected(false),
      },
    );
    return () => sub.close();
  }, [queryClient]);

  // Fallback pulse for the live dot when no bars arrive (e.g. quiet market).
  useEffect(() => {
    const id = window.setInterval(() => setPulse((n) => n + 1), 2000);
    return () => window.clearInterval(id);
  }, []);

  const ingest = useMutation({
    mutationFn: ingestStreamBars,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stream", "stats"] });
    },
  });

  // Compute derived values first so that hook count is identical across renders
  // regardless of loading flags. Early returns go BELOW all hooks.
  const payload = latestQuery.data as MultiLatestPayload | undefined;
  const stats = statsQuery.data;

  const symbols = useMemo(() => Object.keys(payload?.bars ?? {}).sort(), [payload]);
  const totalRecorded = stats?.total_recorded ?? 0;
  const isEmpty = symbols.length === 0;

  const demoIngest = (sym: keyof typeof DEMO_BARS) => {
    ingest.mutate({
      symbol: sym,
      bars: DEMO_BARS[sym].map((b) => ({ ...b, timestamp: nowIso(), source: "manual", received_at: nowIso() })),
    });
  };

  if (latestQuery.isLoading || statsQuery.isLoading) return <Loading />;
  if (latestQuery.isError)
    return <ErrorState message={t("stream.err_connect", locale)} />;

  return (
    <div className="space-y-6">
      <PageTitle
        title={t("stream.title", locale)}
        subtitle={t("stream.subtitle", locale)}
        meta="07 · Live Stream"
        actions={
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["stream"] })}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted"
          >
            <RefreshCcw size={12} />
            {t("stream.refresh", locale)}
          </button>
        }
      />

      {/* Status banner */}
      <section className="rounded-md border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              key={pulse}
              className="relative flex h-2.5 w-2.5 items-center justify-center"
            >
              <span
                className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${
                  sseConnected ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  sseConnected ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground">
                {sseConnected
                  ? t("stream.live_label", locale)
                  : t("stream.connecting", locale)}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {sseConnected
                  ? t("stream.sse_active", locale)
                  : t("stream.sse_fallback", locale)}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <Stat label={t("stream.symbols_tracked", locale)} value={String(stats?.symbols_tracked ?? 0)} />
            <Stat label={t("stream.bars_recorded", locale)} value={totalRecorded.toLocaleString()} />
            <Stat
              label={t("stream.uptime", locale)}
              value={stats ? `${Math.round(stats.uptime_seconds)}s` : "—"}
            />
          </div>
        </div>
      </section>

      {/* Demo controls: when Kafka is off, the user can still push synthetic
          bars via the REST ingest endpoint so the page is demo-able. */}
      <section className="rounded-md border border-dashed border-border bg-card p-4">
        <div className="mb-2 flex items-center gap-2">
          <Send size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">
            {t("stream.demo_title", locale)}
          </h3>
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("stream.demo_sub", locale)}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(DEMO_BARS) as Array<keyof typeof DEMO_BARS>).map((sym) => (
            <button
              key={sym}
              type="button"
              onClick={() => demoIngest(sym)}
              disabled={ingest.isPending}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted disabled:opacity-60"
            >
              <Send size={11} />
              {sym}
            </button>
          ))}
        </div>
      </section>

      {/* Per-symbol tiles */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("stream.symbols_label", locale)}
          </h2>
        </div>
        {isEmpty ? (
          <div className="rounded-md border border-border bg-card p-8 text-center">
            <Radio className="mx-auto mb-3 text-muted-foreground" size={24} />
            <p className="text-sm font-medium text-foreground">{t("stream.empty_title", locale)}</p>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {t("stream.empty_body", locale)}
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {symbols.map((sym) => (
              <StreamTile key={sym} symbol={sym} bar={(payload?.bars ?? {})[sym]} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-base font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  );
}

function StreamTile({ symbol, bar }: { symbol: string; bar: StreamBar | undefined }) {
  const { locale } = useI18n();
  const historyQuery = useQuery({
    queryKey: ["stream", "history", symbol],
    queryFn: () => fetchStreamHistory(symbol, 60),
    refetchInterval: 5000,
    retry: 1,
  });

  const history = historyQuery.data?.bars ?? [];
  const points = history.map((b) => ({ ts: b.timestamp, close: b.close }));
  const last = bar;
  const first = history[0];
  const change = last && first ? last.close - first.close : 0;
  const changePct = last && first && first.close ? change / first.close : 0;
  const positive = change >= 0;

  return (
    <div className="rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-foreground">{symbol}</div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {t("stream.last_bar", locale)}
          </div>
        </div>
        <Activity size={14} className="text-emerald-500" />
      </div>
      <div className="px-4 pt-3">
        {last ? (
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums text-foreground">
              {last.close.toFixed(2)}
            </span>
            <span
              className={positive ? "text-[12px] font-medium text-emerald-600" : "text-[12px] font-medium text-red-600"}
            >
              {positive ? "+" : ""}
              {(changePct * 100).toFixed(2)}%
            </span>
          </div>
        ) : (
          <div className="text-[12px] text-muted-foreground">—</div>
        )}
        {last && (
          <div className="mt-1 grid grid-cols-4 gap-1 text-[10px] text-muted-foreground">
            <div>O {last.open.toFixed(2)}</div>
            <div>H {last.high.toFixed(2)}</div>
            <div>L {last.low.toFixed(2)}</div>
            <div>V {Math.round(last.volume).toLocaleString()}</div>
          </div>
        )}
      </div>
      <div className="h-24 px-1 py-2">
        <ResponsiveContainer>
          <LineChart data={points}>
            <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis stroke="hsl(220 10% 50%)" fontSize={10} domain={["auto", "auto"]} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line
              type="monotone"
              dataKey="close"
              stroke={positive ? "hsl(158 64% 40%)" : "hsl(0 72% 50%)"}
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}