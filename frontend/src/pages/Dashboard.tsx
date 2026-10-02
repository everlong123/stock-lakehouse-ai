import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchDashboard, fetchSystemStatus } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { LakehouseFlow } from "@/components/dashboard/LakehouseFlow";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { OHLCVPoint } from "@/types/stock";
import { formatNumber, formatPrice, formatVolume } from "@/utils/format";
import { DISCLAIMER } from "@/utils/constants";

const tooltipStyle = {
  background: "white",
  border: "1px solid hsl(220 14% 88%)",
  borderRadius: 6,
  fontSize: 12,
};

export function DashboardPage() {
  const { symbol } = useMarket();
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
    return <ErrorState message={errorMessage(query.error, "Khong ket noi duoc backend API.")} />;

  const data = query.data;
  if (!data) return <EmptyState message="Khong co du lieu cho symbol nay." />;

  const candles = (data.candles as OHLCVPoint[]) || [];
  const prediction = data.latest_prediction as Record<string, unknown> | null;
  const counts = (statusQuery.data?.counts as Record<string, number>) || {};

  const lastClose = candles.at(-1)?.close ?? (data.current_price as number) ?? 0;
  const prevClose = candles.at(-2)?.close ?? lastClose;
  const changePct = prevClose ? (lastClose - prevClose) / prevClose : 0;

  const lastSeries = candles.slice(-60).map((c) => ({
    timestamp: c.timestamp,
    price: c.close,
  }));

  return (
    <div className="space-y-6">
      <PageTitle
        title={`${symbol} · Tong quan`}
        subtitle={`Pipeline data lakehouse cho ${symbol}. ${DISCLAIMER}`}
        meta="01 · Dashboard"
      />

      {/* Metrics row */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Metrics · 5 cot
          </h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <MetricCard
            label="Gia hien tai"
            value={formatPrice(lastClose)}
            delta={changePct}
          />
          <MetricCard
            label="Bien dong %"
            value={`${(changePct * 100).toFixed(2)}%`}
            delta={changePct}
          />
          <MetricCard
            label="Volume"
            value={formatVolume((data.volume as number) ?? candles.at(-1)?.volume)}
            hint="Phien gan nhat"
          />
          <MetricCard
            label="RSI (14)"
            value={formatNumber(data.rsi as number)}
            hint="Gold layer"
          />
          <MetricCard
            label="Model gan nhat"
            value={prediction ? String(prediction.model_name) : "Chua train"}
            hint={prediction ? `MAE ${formatNumber(prediction.mae as number)}` : "Train de bat dau"}
          />
        </div>
      </section>

      {/* Lakehouse flow + sidebar */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <LakehouseFlow
            bronzeCount={counts.bronze ?? 0}
            silverCount={counts.silver ?? 0}
            goldCount={counts.gold ?? 0}
          />

          <div className="rounded-md border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Gia 60 phien gan nhat</h3>
                <p className="text-[11px] text-muted-foreground">Duong line truc tiep tu Gold layer</p>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {candles.length} bars
              </span>
            </div>
            <div className="h-56 px-2 py-3">
              <ResponsiveContainer>
                <LineChart data={lastSeries}>
                  <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" hide />
                  <YAxis stroke="hsl(220 10% 50%)" fontSize={11} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="hsl(168 76% 32%)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: "hsl(168 76% 32%)" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">Candlestick · Bronze layer</h3>
              <p className="text-[11px] text-muted-foreground">OHLCV goc, khong qua chinh sua</p>
            </div>
            <div className="px-2 py-3">
              {candles.length ? (
                <CandlestickChart points={candles.slice(-90)} height={300} />
              ) : (
                <EmptyState message="Khong co du lieu candle." />
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <MarketCard
            symbol={symbol}
            price={lastClose}
            source={String(data.data_source || "lakehouse")}
            updated={candles.at(-1)?.timestamp}
          />
          <RecentActivity
            pipeline={data.pipeline as Record<string, unknown> | null}
            model={prediction}
            backtest={data.latest_backtest as Record<string, unknown> | null}
          />
        </div>
      </div>

      {/* Volume */}
      <div className="rounded-md border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Volume bars</h3>
          <p className="text-[11px] text-muted-foreground">80 phien gan nhat</p>
        </div>
        <div className="h-44 px-2 py-3">
          <ResponsiveContainer>
            <BarChart data={candles.slice(-80)}>
              <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="hsl(220 10% 50%)" fontSize={11} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="volume" fill="hsl(168 76% 32%)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}