import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Activity,
  ArrowUpRight,
  Database,
  LineChart as LineChartIcon,
  TrendingUp,
  Waves,
} from "lucide-react";
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
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Không kết nối được backend API.")} />;

  const data = query.data;
  if (!data) return <EmptyState message="Không có dữ liệu cho symbol này." />;

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
      {/* Hero */}
      <div className="card-elevated relative overflow-hidden p-0">
        <div className="relative bg-gradient-to-br from-brand-600 via-brand-500 to-brand-700 px-6 py-7 text-white">
          <div className="absolute inset-0 grid-bg opacity-15" />
          <div className="relative flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest opacity-90">
                <Waves size={12} />
                Lakehouse AI · {symbol}
              </div>
              <h1 className="text-3xl font-bold tracking-tight">{symbol} Live</h1>
              <p className="mt-1 max-w-xl text-sm opacity-90">
                Dữ liệu đi qua Bronze → Silver → Gold, mô hình Linear Regression, ARIMA, LSTM và AI Agent.
              </p>
            </div>
            <div className="text-right">
              <div className="font-mono text-4xl font-bold">{formatPrice(lastClose)}</div>
              <div className="mt-1 flex items-center justify-end gap-2">
                <ArrowUpRight size={14} />
                <span className="font-mono text-sm">
                  {changePct >= 0 ? "+" : ""}
                  {(changePct * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <PageTitle
        title="Tổng quan thị trường"
        subtitle={`Pipeline data lakehouse cho ${symbol}. ${DISCLAIMER}`}
        badge="Live"
      />

      {/* Metrics row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Giá hiện tại"
          value={formatPrice(lastClose)}
          delta={changePct}
          icon={<TrendingUp size={14} />}
        />
        <MetricCard
          label="Biến động %"
          value={`${(changePct * 100).toFixed(2)}%`}
          delta={changePct}
          icon={<Activity size={14} />}
        />
        <MetricCard
          label="Volume"
          value={formatVolume((data.volume as number) ?? candles.at(-1)?.volume)}
          hint="Phiên gần nhất"
          icon={<Database size={14} />}
        />
        <MetricCard
          label="RSI (14)"
          value={formatNumber(data.rsi as number)}
          hint="Gold layer"
          icon={<LineChartIcon size={14} />}
        />
        <MetricCard
          label="Model gần nhất"
          value={prediction ? String(prediction.model_name) : "Chưa train"}
          hint={prediction ? `MAE ${formatNumber(prediction.mae as number)}` : "Train để bắt đầu"}
        />
      </div>

      {/* Lakehouse flow + sidebar */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2 space-y-4">
          <LakehouseFlow
            bronzeCount={counts.bronze ?? 0}
            silverCount={counts.silver ?? 0}
            goldCount={counts.gold ?? 0}
          />
          <div className="card-elevated p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Giá 60 phiên gần nhất</h3>
                <p className="text-xs text-muted-foreground">Đường line trực tiếp từ Gold layer</p>
              </div>
              <span className="chip">{candles.length} bars</span>
            </div>
            <div className="h-56">
              <ResponsiveContainer>
                <LineChart data={lastSeries}>
                  <CartesianGrid stroke="hsl(152 25% 90%)" strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" hide />
                  <YAxis stroke="hsl(158 15% 50%)" fontSize={11} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{
                      background: "white",
                      border: "1px solid hsl(152 18% 88%)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="hsl(154 58% 42%)"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 5, fill: "hsl(154 58% 42%)" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="card-elevated p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Candlestick · Bronze layer</h3>
                <p className="text-xs text-muted-foreground">OHLCV gốc, không qua chỉnh sửa</p>
              </div>
            </div>
            {candles.length ? (
              <CandlestickChart points={candles.slice(-90)} height={300} />
            ) : (
              <EmptyState message="Không có dữ liệu candle." />
            )}
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
      <div className="card-elevated p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-foreground">Volume bars</h3>
            <p className="text-xs text-muted-foreground">80 phiên gần nhất</p>
          </div>
        </div>
        <div className="h-44">
          <ResponsiveContainer>
            <BarChart data={candles.slice(-80)}>
              <CartesianGrid stroke="hsl(152 25% 90%)" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" hide />
              <YAxis stroke="hsl(158 15% 50%)" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: "white",
                  border: "1px solid hsl(152 18% 88%)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="volume" fill="hsl(154 58% 50%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}