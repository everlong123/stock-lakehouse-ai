import { Activity, ArrowDown, ArrowUp, Radio } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import {
  fetchStreamHistory,
  fetchStreamLatest,
  fetchStreamStats,
  StreamBar,
  subscribeStream,
} from "@/api/stream";
import { Loading } from "@/components/common/Loading";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMarket } from "@/hooks/useMarket";
import { formatPrice } from "@/utils/format";

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
  background: "white",
  border: "1px solid hsl(210 18% 90% / 0.6)",
  borderRadius: 6,
  fontSize: 10,
  fontFamily: "JetBrains Mono, monospace",
} as React.CSSProperties;

const cardStyle: React.CSSProperties = {
  borderRadius: 16,
  border: "1px solid hsl(210 18% 90% / 0.6)",
  background: "white",
  boxShadow: "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)",
};

// ── One mini tile: symbol, price, change %, sparkline ────────────────────────
function MiniTile({ symbol, bar }: { symbol: string; bar: StreamBar | undefined }) {
  const { setSymbol } = useMarket();

  // Pull last 30 bars for the sparkline
  const historyQuery = useQuery({
    queryKey: ["stream", "history", symbol],
    queryFn: () => fetchStreamHistory(symbol, 30),
    refetchInterval: false,
    retry: 1,
  });

  const points = (historyQuery.data?.bars ?? []).map((b) => ({ ts: b.timestamp, close: b.close }));
  const first = historyQuery.data?.bars?.[0];
  const change = bar && first ? bar.close - first.close : 0;
  const changePct = bar && first && first.close ? change / first.close : 0;
  const positive = change >= 0;
  const isVn = (bar?.source ?? "").includes("vn");

  return (
    <button
      type="button"
      onClick={() => setSymbol(symbol)}
      style={cardStyle}
      className="group flex w-full flex-col gap-1.5 p-2.5 text-left transition-all hover:border-teal-300 hover:shadow-md"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-semibold tracking-tight text-slate-900">{symbol}</span>
          {isVn && (
            <span className="rounded-sm bg-rose-50 px-1 font-mono text-[8px] font-bold text-rose-600">VN</span>
          )}
        </div>
        {bar ? (
          <span
            className={
              "flex items-center gap-0.5 font-mono text-[10px] font-semibold " +
              (positive ? "text-emerald-600" : "text-rose-600")
            }
          >
            {positive ? <ArrowUp size={8} /> : <ArrowDown size={8} />}
            {(changePct * 100).toFixed(2)}%
          </span>
        ) : (
          <span className="font-mono text-[9px] text-slate-400">…</span>
        )}
      </div>
      {bar ? (
        <div className="font-mono text-[13px] font-bold tabular-nums text-slate-900">
          {isVn ? `${(bar.close / 1000).toFixed(1)}K` : formatPrice(bar.close)}
        </div>
      ) : (
        <div className="h-4" />
      )}
      <div className="-mx-1 h-7">
        {points.length > 1 ? (
          <ResponsiveContainer>
            <LineChart data={points} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
              <Line
                type="monotone"
                dataKey="close"
                stroke={positive ? "hsl(158 64% 40%)" : "hsl(0 72% 50%)"}
                strokeWidth={1.2}
                dot={false}
                isAnimationActive={false}
              />
              <Tooltip contentStyle={tooltipStyle} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center font-mono text-[9px] text-slate-400">
            waiting…
          </div>
        )}
      </div>
    </button>
  );
}

// ── Main watchlist component for the dashboard ───────────────────────────────
export function LiveWatchlist({ maxTiles = 30 }: { maxTiles?: number }) {
  const queryClient = useQueryClient();
  const [pulse, setPulse] = useState(0);
  const [sseConnected, setSseConnected] = useState(false);

  const statsQuery = useQuery({
    queryKey: ["stream", "stats"],
    queryFn: fetchStreamStats,
    refetchInterval: 10000,
    retry: 1,
  });

  // One-shot initial fetch (no polling) — SSE keeps it fresh afterwards.
  const latestQuery = useQuery({
    queryKey: ["stream", "latest"],
    queryFn: () => fetchStreamLatest(),
    refetchInterval: false,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  useEffect(() => {
    const sub = subscribeStream(
      (event) => {
        if (event.type === "hello") setSseConnected(true);
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
        // Re-fetch that symbol's sparkline so it ticks
        queryClient.invalidateQueries({ queryKey: ["stream", "history", bar.symbol] });
        setPulse((n) => n + 1);
      },
      { onError: () => setSseConnected(false) },
    );
    return () => sub.close();
  }, [queryClient]);

  // Idle pulse so the dot blinks even when no new bar arrives
  useEffect(() => {
    const id = window.setInterval(() => setPulse((n) => n + 1), 3000);
    return () => window.clearInterval(id);
  }, []);

  const payload = latestQuery.data as MultiLatestPayload | undefined;
  const symbols = useMemo(
    () => Object.keys(payload?.bars ?? {}).sort().slice(0, maxTiles),
    [payload, maxTiles],
  );

  if (latestQuery.isLoading) return <Loading />;
  if (latestQuery.isError) return null; // Watchlist is decorative — don't break dashboard

  const stats = statsQuery.data;
  const usCount = symbols.filter((s) => (payload?.bars?.[s]?.source ?? "").includes("yfinance")).length;
  const vnCount = symbols.filter((s) => (payload?.bars?.[s]?.source ?? "").includes("vn")).length;

  return (
    <div style={cardStyle} className="overflow-hidden">
      {/* Header strip */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div key={pulse} className="relative flex h-2 w-2">
            <span
              className={
                "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 " +
                (sseConnected ? "bg-emerald-500" : "bg-amber-500")
              }
            />
            <span
              className={
                "relative inline-flex h-2 w-2 rounded-full " +
                (sseConnected ? "bg-emerald-500" : "bg-amber-500")
              }
            />
          </div>
          <Activity size={12} className="text-teal-700" />
          <span className="text-[12px] font-semibold text-slate-900">Live Watchlist</span>
          <span className="rounded-full bg-teal-50 px-1.5 py-0.5 font-mono text-[9px] font-medium text-teal-700">
            {symbols.length} streaming
          </span>
          {usCount > 0 && (
            <span className="rounded-full bg-blue-50 px-1.5 py-0.5 font-mono text-[9px] font-medium text-blue-700">
              {usCount} US
            </span>
          )}
          {vnCount > 0 && (
            <span className="rounded-full bg-rose-50 px-1.5 py-0.5 font-mono text-[9px] font-medium text-rose-700">
              {vnCount} VN
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-slate-500">
            {stats?.total_recorded ?? 0} bars · {Math.round(stats?.uptime_seconds ?? 0)}s up
          </span>
          <Link
            to="/stream"
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            <Radio size={9} /> Mở Live Stream
          </Link>
        </div>
      </div>
      {/* Tile grid */}
      {symbols.length === 0 ? (
        <div className="px-4 py-6 text-center font-mono text-[11px] text-slate-400">
          Đang chờ bar đầu tiên từ Kafka…
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {symbols.map((sym) => (
            <MiniTile key={sym} symbol={sym} bar={payload?.bars?.[sym]} />
          ))}
        </div>
      )}
    </div>
  );
}
