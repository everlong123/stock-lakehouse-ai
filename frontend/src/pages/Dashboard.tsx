import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchDashboard } from "@/api/agent";
import { errorMessage } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { MarketCard } from "@/components/dashboard/MarketCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useMarket } from "@/hooks/useMarket";
import { OHLCVPoint } from "@/types/stock";
import { formatNumber, formatPrice } from "@/utils/format";
import { DISCLAIMER } from "@/utils/constants";

export function DashboardPage() {
  const { symbol } = useMarket();
  const query = useQuery({
    queryKey: ["dashboard", symbol],
    queryFn: () => fetchDashboard(symbol),
    retry: 1,
  });

  if (query.isLoading) return <Loading label="Loading dashboard..." />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Cannot connect to backend API.")} />;
  const data = query.data;
  if (!data) return <EmptyState message="No market data available for the selected range." />;

  const candles = (data.candles as OHLCVPoint[]) || [];
  const prediction = data.latest_prediction as Record<string, unknown> | null;

  return (
    <div className="space-y-4">
      <PageTitle title="Dashboard" subtitle={`Lakehouse analytics for ${symbol}. ${DISCLAIMER}`} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Current Price" value={formatPrice(data.current_price as number)} delta={data.change_pct as number} />
        <MetricCard label="Price Change %" value={`${(((data.change_pct as number) || 0) * 100).toFixed(2)}%`} />
        <MetricCard label="Volume" value={formatNumber(data.volume as number, 0)} />
        <MetricCard label="RSI" value={formatNumber(data.rsi as number)} />
        <MetricCard
          label="Latest Prediction"
          value={prediction ? String(prediction.model_name) : "None"}
          hint={prediction ? `MAE ${formatNumber(prediction.mae as number)}` : "No trained model found. Please train the model first."}
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4 xl:col-span-2">
          <div className="mb-3 text-sm font-semibold">Candlestick · SMA overlay in Gold features</div>
          {candles.length ? <CandlestickChart points={candles} /> : <EmptyState message="No market data available for the selected range." />}
        </div>
        <div className="space-y-3">
          <MarketCard
            symbol={symbol}
            price={data.current_price as number}
            source={String(data.data_source || "sample")}
            updated={candles.at(-1)?.timestamp}
          />
          <RecentActivity
            pipeline={data.pipeline as Record<string, unknown> | null}
            model={prediction}
            backtest={data.latest_backtest as Record<string, unknown> | null}
          />
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 text-sm font-semibold">Volume</div>
        <div className="h-40">
          <ResponsiveContainer>
            <BarChart data={candles.slice(-80)}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="hsl(var(--muted-foreground))" />
              <Tooltip />
              <Bar dataKey="volume" fill="hsl(var(--primary) / 0.7)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
