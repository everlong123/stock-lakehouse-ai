import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Activity, TrendingUp, Zap } from "lucide-react";
import { fetchIndicators } from "@/api/indicators";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { PriceChart } from "@/components/charts/PriceChart";
import { IndicatorChart } from "@/components/charts/IndicatorChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
  "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
  "VIC", "VPB", "CTG", "TPB", "SHB", "STB", "PNJ", "HDB", "LPB", "MSB",
];

export function TechnicalAnalysisPage() {
  const { symbol: ctxSymbol, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);

  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols?.length
    ? symbolsQuery.data.symbols
    : DEFAULT_SYMBOLS;

  const handleSymbolChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setLocalSymbol(val);
    setSymbol(val);
  };

  const [sma, setSma] = useState(true);
  const [ema, setEma] = useState(true);
  const [rsiOn, setRsiOn] = useState(true);
  const [macdOn, setMacdOn] = useState(true);
  const [bb, setBb] = useState(true);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const query = useQuery({
    queryKey: ["indicators", localSymbol || ctxSymbol, sma, ema, rsiOn, macdOn, bb, rsiPeriod],
    queryFn: () => fetchIndicators(localSymbol || ctxSymbol, {
      sma, ema, rsi: rsiOn, macd: macdOn, bollinger: bb, rsi_period: rsiPeriod,
    }),
    retry: 1,
  });

  const series = useMemo(() => (query.data?.series as Array<Record<string, string | number | null>>) || [], [query.data]);

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Không kết nối được backend API.")} />;
  if (!series.length) return <EmptyState message="Không có dữ liệu cho mã này." />;

  const summary = (query.data?.summary as Record<string, string>) || {};

  const latestRSI = (() => {
    for (let i = series.length - 1; i >= 0; i--) {
      const v = series[i].rsi_14;
      if (typeof v === "number" && !Number.isNaN(v)) return v;
    }
    return null;
  })();

  return (
    <div className="space-y-6">
      <PageTitle
        title="Technical Analysis"
        subtitle="Chỉ báo kỹ thuật mô tả quá khứ — không phải khuyến nghị giao dịch."
        badge={localSymbol}
        actions={
          <select
            value={localSymbol || ctxSymbol}
            onChange={handleSymbolChange}
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-brand-500"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      {/* Controls */}
      <Card className="p-5">
        <div className="grid gap-4 md:grid-cols-5">
          <Checkbox label="SMA" checked={sma} onChange={(e) => setSma(e.target.checked)} />
          <Checkbox label="EMA" checked={ema} onChange={(e) => setEma(e.target.checked)} />
          <Checkbox label="RSI" checked={rsiOn} onChange={(e) => setRsiOn(e.target.checked)} />
          <Checkbox label="MACD" checked={macdOn} onChange={(e) => setMacdOn(e.target.checked)} />
          <Checkbox label="Bollinger Bands" checked={bb} onChange={(e) => setBb(e.target.checked)} />
          <label className="text-sm md:col-span-2">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              RSI period
            </span>
            <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
          </label>
        </div>
      </Card>

      {/* Price + Indicators */}
      <div className="card-elevated p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-brand-600" />
            <h3 className="text-base font-bold text-foreground">Price + SMA / EMA / Bollinger</h3>
          </div>
          <Badge variant="primary">{series.length} bars</Badge>
        </div>
        <PriceChart
          data={series.map((row) => ({
            timestamp: String(row.timestamp),
            close: Number(row.close),
            sma_20: row.sma_20 == null ? undefined : Number(row.sma_20),
            sma_50: row.sma_50 == null ? undefined : Number(row.sma_50),
            ema_12: row.ema_12 == null ? undefined : Number(row.ema_12),
            bb_upper: row.bb_upper == null ? undefined : Number(row.bb_upper),
            bb_lower: row.bb_lower == null ? undefined : Number(row.bb_lower),
          }))}
        />
      </div>

      {/* RSI + MACD in side-by-side */}
      <div className="grid gap-4 xl:grid-cols-2">
        {rsiOn ? (
          <div className="card-elevated p-5">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-brand-600" />
                <h3 className="text-base font-bold text-foreground">RSI ({rsiPeriod})</h3>
              </div>
              {latestRSI !== null ? (
                <Badge variant={latestRSI > 70 ? "warn" : latestRSI < 30 ? "primary" : "default"}>
                  {latestRSI.toFixed(2)} {latestRSI > 70 ? "Overbought" : latestRSI < 30 ? "Oversold" : "Neutral"}
                </Badge>
              ) : null}
            </div>
            <IndicatorChart
              data={series}
              lines={[{ key: "rsi_14", color: "hsl(154 58% 42%)", name: "RSI" }]}
              referenceLines={[
                { y: 70, label: "70", color: "hsl(0 70% 50%)" },
                { y: 30, label: "30", color: "hsl(154 60% 36%)" },
                { y: 50, label: "50", color: "hsl(158 15% 60%)" },
              ]}
              height={220}
            />
          </div>
        ) : null}

        {macdOn ? (
          <div className="card-elevated p-5">
            <div className="mb-2 flex items-center gap-2">
              <TrendingUp size={14} className="text-brand-600" />
              <h3 className="text-base font-bold text-foreground">MACD (12,26,9)</h3>
            </div>
            <IndicatorChart
              data={series}
              lines={[
                { key: "macd", color: "hsl(154 58% 42%)", name: "MACD" },
                { key: "macd_signal", color: "hsl(36 90% 50%)", name: "Signal" },
                { key: "macd_hist", color: "hsl(220 30% 60%)", name: "Histogram" },
              ]}
              height={220}
            />
          </div>
        ) : null}
      </div>

      {/* Summary */}
      <div className="grid gap-4 md:grid-cols-3">
        {[
          { key: "trend", label: "Trend", icon: TrendingUp },
          { key: "momentum", label: "Momentum", icon: Zap },
          { key: "volatility", label: "Volatility", icon: Activity },
        ].map(({ key, label, icon: Icon }) => (
          <div key={key} className="card-elevated p-5">
            <div className="mb-2 flex items-center gap-2">
              <Icon size={14} className="text-brand-600" />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {label}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-foreground">
              {summary[key] || "Chưa đủ dữ liệu để mô tả."}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}