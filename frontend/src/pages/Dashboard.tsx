import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  AreaChart,
} from "recharts";
import { fetchDashboard, fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { TimeRangeSelector, type TimeRange } from "@/components/common/TimeRangeSelector";
import { LakehouseFlow } from "@/components/dashboard/LakehouseFlow";
import { LiveWatchlist } from "@/components/dashboard/LiveWatchlist";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { OHLCVPoint } from "@/types/stock";
import { applyTimeRange, formatNumber, formatPrice, formatVolume } from "@/utils/format";

const TEAL = "hsl(165 52% 28%)";
const TEAL_LIGHT = "hsl(165 45% 92%)";
const BORDER = "hsl(210 18% 90% / 0.6)";
const MUTED = "hsl(220 12% 45%)";
const GRID = "hsl(210 20% 92%)";

const cardStyle = (hover = false) => ({
  borderRadius: 16,
  border: `1px solid ${hover ? "hsl(210 18% 82%)" : "hsl(210 18% 90% / 0.6)"}`,
  background: "white",
  boxShadow: hover
    ? "0 4px 12px -2px hsl(0 0 0% / 0.07), 0 2px 6px -2px hsl(0 0 0% / 0.04)"
    : "0 1px 3px hsl(0 0 0% / 0.04), 0 1px 2px hsl(0 0 0% / 0.02)",
  transition: "all 0.2s ease",
} as React.CSSProperties);

const tooltipStyle = {
  background: "white",
  border: `1px solid ${BORDER}`,
  borderRadius: 12,
  fontSize: 12,
  fontFamily: "JetBrains Mono, monospace",
  boxShadow: "0 4px 12px hsl(0 0 0% / 0.08)",
  padding: "8px 12px",
};

// ── Price area chart with gradient fill ───────────────────────────────────────
function PriceAreaChart({ data }: { data: Array<{ timestamp: string; price: number }> }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={TEAL} stopOpacity={0.15} />
            <stop offset="95%" stopColor={TEAL} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={MUTED}
          fontSize={11}
          fontFamily="JetBrains Mono, monospace"
          domain={["auto", "auto"]}
          width={55}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: MUTED, fontSize: 10, marginBottom: 4 }}
          formatter={(v: number) => [`$${v.toFixed(2)}`, "Price"]}
          itemStyle={{ color: TEAL, fontWeight: 600 }}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={TEAL}
          strokeWidth={2.5}
          fill="url(#priceGradient)"
          dot={false}
          activeDot={{ r: 5, fill: TEAL, stroke: "white" as never, strokeWidth: 2 }}
          animationDuration={600}
          animationEasing="ease-out"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Volume bar chart with up/down colors ──────────────────────────────────────
function VolumeChart({ data }: { data: OHLCVPoint[] }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="timestamp" hide />
        <YAxis
          stroke={MUTED}
          fontSize={11}
          fontFamily="JetBrains Mono, monospace"
          tickFormatter={(v: number) =>
            v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : `${v}`
          }
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: MUTED, fontSize: 10, marginBottom: 4 }}
          formatter={(v: number) => [formatVolume(v), "Volume"]}
          itemStyle={{ color: MUTED }}
        />
        {data.map((entry, index) => (
          <Bar
            key={`vol-${index}`}
            dataKey="volume"
            fill={entry.close >= entry.open ? "hsl(152 58% 38%)" : "hsl(4 80% 52%)"}
            radius={[3, 3, 0, 0]}
            maxBarSize={24}
            animationDuration={500}
            animationEasing="ease-out"
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const [range, setRange] = useState<TimeRange>("3M");

  const query = useQuery({
    queryKey: ["dashboard", symbol],
    queryFn: () => fetchDashboard(symbol),
    retry: 1,
  });

  const statusQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    retry: 1,
    refetchInterval: 15000,
  });

  if (query.isLoading) return <Loading />;
  if (query.isError)
    return (
      <ErrorState
        message={errorMessage(query.error, t("dashboard.err_connect", locale))}
        onRetry={() => query.refetch()}
      />
    );

  const data = query.data;
  if (!data) return <EmptyState message={t("dashboard.empty_symbol", locale)} />;

  const candles = (data.candles as OHLCVPoint[]) || [];
  const prediction = data.latest_prediction as Record<string, unknown> | null;
  const counts = (statusQuery.data?.counts as Record<string, number>) || {};

  const lastClose = candles.at(-1)?.close ?? (data.current_price as number) ?? 0;
  const prevClose = candles.at(-2)?.close ?? lastClose;
  const changePct = prevClose ? (lastClose - prevClose) / prevClose : 0;

  const rangedCandles = applyTimeRange(candles, range);
  const priceSeries = rangedCandles.map((c) => ({ timestamp: c.timestamp, price: c.close }));

  return (
    <div className="space-y-5">
      {/* ── Page title ─────────────────────────────────────────── */}
      <PageTitle
        title={`${symbol} · ${t("dashboard.title", locale)}`}
        subtitle={`${t("dashboard.metrics", locale)} cho ${symbol}`}
        meta="01 · Dashboard"
      />

      {/* ── Live watchlist: real-time prices from Kafka stream ── */}
      <section className="animate-fade-in-up" style={{ animationDelay: "0.05s" }}>
        <LiveWatchlist maxTiles={30} />
      </section>

      {/* ── Metrics row ───────────────────────────────────────── */}
      <section>
        <div className="mb-3 font-mono text-[10px] uppercase tracking-widest" style={{ color: MUTED }}>
          {t("dashboard.metrics", locale)}
        </div>
        <div
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
          style={{ animation: "fade-in-up 0.4s ease-out both" }}
        >
          <MetricCard label={t("dashboard.price", locale)} value={formatPrice(lastClose)} delta={changePct} />
          <MetricCard
            label={t("dashboard.change_pct", locale)}
            value={`${(changePct * 100).toFixed(2)}%`}
            delta={changePct}
          />
          <MetricCard
            label={t("dashboard.volume", locale)}
            value={formatVolume((data.volume as number) ?? candles.at(-1)?.volume)}
            hint={t("dashboard.volume_hint", locale)}
          />
          <MetricCard
            label={t("dashboard.rsi", locale)}
            value={formatNumber(data.rsi as number)}
            hint={t("dashboard.rsi_hint", locale)}
          />
          <MetricCard
            label={t("dashboard.model", locale)}
            value={prediction ? String(prediction.model_name) : t("dashboard.model_no_train", locale)}
            hint={
              prediction
                ? `${t("dashboard.model_hint_trained", locale)} ${formatNumber(prediction.mae as number)}`
                : t("dashboard.model_hint_untrained", locale)
            }
          />
        </div>
      </section>

      {/* ── Main grid: charts + sidebar ────────────────────────── */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">

          {/* Lakehouse layer flow */}
          <div className="animate-fade-in-up stagger-1" style={cardStyle()}>
            <LakehouseFlow
              bronzeCount={counts.bronze ?? 0}
              silverCount={counts.silver ?? 0}
              goldCount={counts.gold ?? 0}
            />
          </div>

          {/* Price area chart */}
          <div className="animate-fade-in-up stagger-2" style={cardStyle()}>
            <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: BORDER }}>
              <div>
                <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
                  {t("dashboard.line_chart_title", locale)}
                </h3>
                <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
                  {t("dashboard.line_chart_sub", locale)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <TimeRangeSelector value={range} onChange={setRange} />
                <span
                  className="rounded-full px-2 py-0.5 font-mono text-[10px] font-medium"
                  style={{ background: TEAL_LIGHT, color: TEAL }}
                >
                  {rangedCandles.length} bars
                </span>
              </div>
            </div>
            <div className="h-56 px-3 py-4">
              {priceSeries.length ? <PriceAreaChart data={priceSeries} /> : <EmptyState message="No price data" />}
            </div>
          </div>

          {/* Candlestick chart */}
          <div className="animate-fade-in-up stagger-3" style={cardStyle()}>
            <div className="border-b px-5 py-4" style={{ borderColor: BORDER }}>
              <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
                {t("dashboard.candle_title", locale)}
              </h3>
              <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
                {t("dashboard.candle_sub", locale)}
              </p>
            </div>
            <div className="px-2 py-4">
              {candles.length ? (
                <CandlestickChart points={candles.slice(-90)} height={300} />
              ) : (
                <EmptyState
                  message={t("dashboard.empty_candle", locale)}
                  hint="Kiểm tra Bronze layer hoặc bấm Train để ingest dữ liệu mới."
                />
              )}
            </div>
          </div>
        </div>

        {/* Sidebar: market info + activity */}
        <div className="space-y-4">
          <div className="animate-fade-in-up stagger-2" style={cardStyle()}>
            <MarketCard
              symbol={symbol}
              price={lastClose}
              source={String(data.data_source || "lakehouse")}
              updated={candles.at(-1)?.timestamp}
            />
          </div>
          <div className="animate-fade-in-up stagger-3" style={cardStyle()}>
            <RecentActivity
              pipeline={data.pipeline as Record<string, unknown> | null}
              model={prediction}
              backtest={data.latest_backtest as Record<string, unknown> | null}
            />
          </div>
        </div>
      </div>

      {/* ── Volume chart ───────────────────────────────────────── */}
      <div className="animate-fade-in-up stagger-4" style={cardStyle()}>
        <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: BORDER }}>
          <div>
            <h3 className="text-[15px] font-semibold" style={{ color: "hsl(220 25% 10%)" }}>
              {t("dashboard.volume_title", locale)}
            </h3>
            <p className="mt-0.5 text-[11px]" style={{ color: MUTED }}>
              {t("dashboard.volume_sub", locale)}
            </p>
          </div>
          <span
            className="rounded-full px-2 py-0.5 font-mono text-[10px] font-medium"
            style={{ background: TEAL_LIGHT, color: TEAL }}
          >
            {rangedCandles.length} bars
          </span>
        </div>
        <div className="h-44 px-3 py-4">
          <VolumeChart data={rangedCandles} />
        </div>
      </div>
    </div>
  );
}
