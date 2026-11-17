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
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { toFinite } from "@/utils/format";

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
    return <ErrorState message={errorMessage(query.error, "Không kết nối được backend API.")} />;
  if (!series.length) return <EmptyState message="Không có dữ liệu cho mã này." />;

  const summary = (query.data?.summary as Record<string, string>) || {};

  // Scan back for the newest usable RSI. `toFinite` is used instead of a bare
  // `Number.isNaN` check so a string-typed value ("N/A", "") is handled too,
  // and Infinity can't slip through and blow up the >70 / <30 comparison.
  const latestRSI = (() => {
    for (let i = series.length - 1; i >= 0; i--) {
      const v = toFinite(series[i].rsi_14);
      if (v !== undefined) return v;
    }
    return null;
  })();

  return (
    <div className="space-y-12">
      <PageTitle
        title="Phân tích kỹ thuật"
        subtitle="Chỉ báo momentum từ quỹ khởi. Không phải tín hiệu giao dịch."
        meta={`03 · ${localSymbol}`}
        actions={
          <select
            value={localSymbol || ctxSymbol}
            onChange={handleSymbolChange}
            className="h-9 rounded border border-hairline bg-surface px-2 font-mono text-small text-ink outline-none focus:border-primary"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      {/*
        Indicator toggles
        --------------------
        These are filters, not content. They sit in one recessed strip on
        a single row so they read as a control bar rather than as a
        panel of settings, and so the chart below owns the page.
      */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4 rounded border border-hairline bg-surface-2 px-4 py-3">
        <span className="label">Indicators</span>
        <Checkbox label="SMA" checked={sma} onChange={(e) => setSma(e.target.checked)} />
        <Checkbox label="EMA" checked={ema} onChange={(e) => setEma(e.target.checked)} />
        <Checkbox label="RSI" checked={rsiOn} onChange={(e) => setRsiOn(e.target.checked)} />
        <Checkbox label="MACD" checked={macdOn} onChange={(e) => setMacdOn(e.target.checked)} />
        <Checkbox label="Bollinger" checked={bb} onChange={(e) => setBb(e.target.checked)} />
        <label className="flex items-center gap-2 text-small text-ink">
          <span className="label">RSI period</span>
          <Input
            type="number"
            value={rsiPeriod}
            onChange={(e) => setRsiPeriod(Number(e.target.value))}
            className="w-16 font-mono"
          />
        </label>
      </div>

      {/* Price + overlays */}
      <section>
        <div className="section-head">
          <h2 className="section-title">Price + SMA / EMA / Bollinger</h2>
          <span className="font-mono text-label uppercase text-muted">
            {series.length} bars
          </span>
        </div>
        <div className="pt-4">
          <PriceChart
            data={series.map((row) => ({
              timestamp: String(row.timestamp),
              close: toFinite(row.close) ?? 0,
              sma_20: toFinite(row.sma_20),
              sma_50: toFinite(row.sma_50),
              ema_12: toFinite(row.ema_12),
              bb_upper: toFinite(row.bb_upper),
              bb_lower: toFinite(row.bb_lower),
            }))}
          />
        </div>
      </section>

      {/* RSI + MACD side by side: two charts of the same length, so a
          two-column grid is the honest layout here. */}
      <div className="grid gap-12 xl:grid-cols-2">
        {rsiOn ? (
          <section>
            <div className="section-head">
              <h2 className="section-title">RSI ({rsiPeriod})</h2>
              {latestRSI !== null ? (
                <Badge variant={latestRSI > 70 ? "negative" : "default"}>
                  {latestRSI.toFixed(2)} · {latestRSI > 70 ? "Quá mua" : latestRSI < 30 ? "Quá bán" : "Trung tính"}
                </Badge>
              ) : null}
            </div>
            <div className="pt-4">
              <IndicatorChart
                data={series}
                lines={[{ key: "rsi_14", color: "hsl(var(--primary))", name: "RSI" }]}
                referenceLines={[
                  { y: 70, label: "70", color: "hsl(var(--negative))" },
                  { y: 30, label: "30", color: "hsl(var(--muted))" },
                  { y: 50, label: "50", color: "hsl(var(--hairline))" },
                ]}
                height={220}
              />
            </div>
          </section>
        ) : null}

        {macdOn ? (
          <section>
            <div className="section-head">
              <h2 className="section-title">MACD (12,26,9)</h2>
            </div>
            <div className="pt-4">
              <IndicatorChart
                data={series}
                lines={[
                  { key: "macd", color: "hsl(var(--primary))", name: "MACD" },
                  { key: "macd_signal", color: "hsl(var(--muted))", name: "Signal" },
                  { key: "macd_hist", color: "hsl(var(--hairline))", name: "Histogram" },
                ]}
                height={220}
              />
            </div>
          </section>
        ) : null}
      </div>

      {/* Narrative summary: three short paragraphs, NOT three cards.
          These are readings, not widgets, so they run as a three-column
          text block under one rule. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">Tóm tắt chỉ báo</h2>
        </div>
        <div className="grid gap-x-8 gap-y-6 pt-6 md:grid-cols-3">
          {[
            { key: "trend", label: "Xu hướng" },
            { key: "momentum", label: "Động lượng" },
            { key: "volatility", label: "Biến động" },
          ].map(({ key, label }) => (
            <div key={key}>
              <div className="label">{label}</div>
              <p className="mt-2 text-small text-ink">
                {summary[key] || "Chưa đủ dữ liệu để mô tả."}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
