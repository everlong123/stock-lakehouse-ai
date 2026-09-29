import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchIndicators } from "@/api/indicators";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { IndicatorChart } from "@/components/charts/IndicatorChart";
import { PriceChart } from "@/components/charts/PriceChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useMarket } from "@/hooks/useMarket";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
  "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
  "VIC", "VPB", "CTG", "TPB", "SHB", "STB", "PNJ", "HDB", "LPB", "MSB",
  "OCB", "REE", "NVL", "PDR", "BCM", "SBT", "IMP", "KDC", "PC1", "HDG",
  "DRC", "DXG", "IDJ", "ITA", "JVC", "LSG", "MSH", "NSC", "PVT", "MBC",
  "DIG", "FCN", "HCM", "CTC", "SMT", "KSC", "VGC", "BVH", "C22", "C32",
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
    queryFn: () => fetchIndicators(localSymbol || ctxSymbol, { sma, ema, rsi: rsiOn, macd: macdOn, bollinger: bb, rsi_period: rsiPeriod }),
    retry: 1,
  });

  const series = useMemo(() => (query.data?.series as Record<string, string | number | null>[]) || [], [query.data]);

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Cannot connect to backend API.")} />;
  if (!series.length) return <EmptyState message="No market data available for the selected range." />;

  const summary = (query.data?.summary as Record<string, string>) || {};

  return (
    <div className="space-y-4">
      <PageTitle title="Technical Analysis" subtitle="Mô tả chỉ báo lịch sử, không phải lệnh đầu tư." />
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <span>Symbol:</span>
          <select
            value={localSymbol || ctxSymbol}
            onChange={handleSymbolChange}
            className="rounded border border-border bg-background px-2 py-1 text-foreground"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-5">
        <Checkbox label="SMA" checked={sma} onChange={(e) => setSma(e.target.checked)} />
        <Checkbox label="EMA" checked={ema} onChange={(e) => setEma(e.target.checked)} />
        <Checkbox label="RSI" checked={rsiOn} onChange={(e) => setRsiOn(e.target.checked)} />
        <Checkbox label="MACD" checked={macdOn} onChange={(e) => setMacdOn(e.target.checked)} />
        <Checkbox label="Bollinger Bands" checked={bb} onChange={(e) => setBb(e.target.checked)} />
        <label className="text-sm">
          RSI period
          <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
        </label>
      </div>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-2 text-sm font-semibold">Price + SMA/EMA/Bollinger</div>
        <PriceChart
          data={series.map((row) => ({
            timestamp: String(row.timestamp),
            close: Number(row.close),
            sma_20: row.sma_20 == null ? undefined : Number(row.sma_20),
            sma_50: row.sma_50 == null ? undefined : Number(row.sma_50),
          }))}
        />
      </div>
      {rsiOn ? (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 text-sm font-semibold">RSI panel</div>
          <IndicatorChart data={series} lines={[{ key: "rsi_14", color: "#38bdf8" }]} />
        </div>
      ) : null}
      {macdOn ? (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 text-sm font-semibold">MACD panel</div>
          <IndicatorChart
            data={series}
            lines={[
              { key: "macd", color: "#38bdf8" },
              { key: "macd_signal", color: "#f59e0b" },
              { key: "macd_hist", color: "#64748b" },
            ]}
          />
        </div>
      ) : null}
      <div className="grid gap-3 md:grid-cols-3">
        {["trend", "momentum", "volatility"].map((key) => (
          <div key={key} className="rounded-lg border border-border bg-card p-4">
            <div className="text-xs uppercase text-muted-foreground">{key}</div>
            <p className="mt-2 text-sm">{summary[key] || "insufficient data"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
