import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
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
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
  "JNJ", "WMT", "UNH", "XOM", "CVX", "BAC", "KO", "PEP", "DIS", "NFLX",
  "CRM", "ORCL", "ADBE", "INTC", "CSCO", "IBM", "QCOM", "TXN", "AVGO", "COST",
];

export function TechnicalAnalysisPage() {
  const { symbol: ctxSymbol, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  // Sync localSymbol when ctxSymbol changes (e.g., user changes symbol from Header)
  useEffect(() => { setLocalSymbol(ctxSymbol); }, [ctxSymbol]);

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
  if (query.isError)
    return <ErrorState message={errorMessage(query.error, "Khong ket noi duoc backend API.")} />;
  if (!series.length) return <EmptyState message="Khong co du lieu cho ma nay." />;

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
        title="Technical analysis"
        subtitle="Chi bao ky thuat mo ta qua khu. Khong phai khuyen nghi giao dich."
        meta={`03 · ${localSymbol}`}
        actions={
          <select
            value={localSymbol || ctxSymbol}
            onChange={handleSymbolChange}
            className="h-9 rounded-md border border-input bg-card px-3 font-mono text-sm outline-none focus:border-foreground"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      <Card className="p-4">
        <div className="grid gap-4 md:grid-cols-5">
          <Checkbox label="SMA" checked={sma} onChange={(e) => setSma(e.target.checked)} />
          <Checkbox label="EMA" checked={ema} onChange={(e) => setEma(e.target.checked)} />
          <Checkbox label="RSI" checked={rsiOn} onChange={(e) => setRsiOn(e.target.checked)} />
          <Checkbox label="MACD" checked={macdOn} onChange={(e) => setMacdOn(e.target.checked)} />
          <Checkbox label="Bollinger Bands" checked={bb} onChange={(e) => setBb(e.target.checked)} />
          <label className="text-sm md:col-span-2">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              RSI period
            </span>
            <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
          </label>
        </div>
      </Card>

      <div className="rounded-md border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Price + SMA / EMA / Bollinger</h3>
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {series.length} bars
          </span>
        </div>
        <div className="px-2 py-3">
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
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {rsiOn ? (
          <div className="rounded-md border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">RSI ({rsiPeriod})</h3>
              {latestRSI !== null ? (
                <Badge variant={latestRSI > 70 ? "warn" : latestRSI < 30 ? "success" : "default"}>
                  {latestRSI.toFixed(2)} · {latestRSI > 70 ? "Overbought" : latestRSI < 30 ? "Oversold" : "Neutral"}
                </Badge>
              ) : null}
            </div>
            <div className="px-2 py-3">
              <IndicatorChart
                data={series}
                lines={[{ key: "rsi_14", color: "hsl(168 76% 32%)", name: "RSI" }]}
                referenceLines={[
                  { y: 70, label: "70", color: "hsl(0 64% 48%)" },
                  { y: 30, label: "30", color: "hsl(152 60% 32%)" },
                  { y: 50, label: "50", color: "hsl(220 10% 60%)" },
                ]}
                height={220}
              />
            </div>
          </div>
        ) : null}

        {macdOn ? (
          <div className="rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">MACD (12,26,9)</h3>
            </div>
            <div className="px-2 py-3">
              <IndicatorChart
                data={series}
                lines={[
                  { key: "macd", color: "hsl(168 76% 32%)", name: "MACD" },
                  { key: "macd_signal", color: "hsl(32 88% 44%)", name: "Signal" },
                  { key: "macd_hist", color: "hsl(220 30% 50%)", name: "Histogram" },
                ]}
                height={220}
              />
            </div>
          </div>
        ) : null}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {[
          { key: "trend", label: "Trend" },
          { key: "momentum", label: "Momentum" },
          { key: "volatility", label: "Volatility" },
        ].map(({ key, label }) => (
          <div key={key} className="rounded-md border border-border bg-card p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {label}
            </div>
            <p className="mt-2 text-sm leading-relaxed text-foreground">
              {summary[key] || "Chua du du lieu de mo ta."}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}