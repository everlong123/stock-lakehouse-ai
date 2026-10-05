import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMarket } from "@/hooks/useMarket";
import { useStocks } from "@/hooks/useStocks";
import { csvUrl, fetchSymbols } from "@/api/stocks";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/api/client";
import { useI18n, t } from "@/lib/i18n";
import { formatNumber, formatPrice, formatVolume, shortDate } from "@/utils/format";

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
  "JNJ", "WMT", "UNH", "XOM", "CVX", "BAC", "KO", "PEP", "DIS", "NFLX",
  "CRM", "ORCL", "ADBE", "INTC", "CSCO", "IBM", "QCOM", "TXN", "AVGO", "COST",
];

export function MarketDataPage() {
  const { symbol: ctxSymbol, interval, setSymbol } = useMarket();
  const { locale } = useI18n();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  // Sync localSymbol when ctxSymbol changes (e.g., user changes symbol from Header)
  useEffect(() => { setLocalSymbol(ctxSymbol); }, [ctxSymbol]);
  const [filter, setFilter] = useState("");
  const query = useStocks(localSymbol || ctxSymbol, interval);

  const symbolsQuery = useQuery({
   queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols?.length
    ? symbolsQuery.data.symbols
    : DEFAULT_SYMBOLS;
  const visibleSymbols = availableSymbols.filter((s) =>
    s.toLowerCase().includes(filter.toLowerCase()),
  );
  if (query.isLoading) return <Loading />;
  if (query.isError)
    return <ErrorState message={errorMessage(query.error, t("dashboard.err_connect", locale))} />;

  const rows = query.data?.rows ?? [];
  if (!rows.length)
    return <EmptyState message={`${t("market.empty", locale)} ${localSymbol || ctxSymbol}.`} />;

  const latest = query.data?.latest;
  const headerStats = [
   { label: t("market.source", locale),      value: query.data?.data_source || "Yahoo" },
    { label: t("market.rows", locale),         value: rows.length.toLocaleString("en-US") },
    { label: t("market.last_close", locale),   value: formatPrice(latest?.close) },
    { label: t("market.last_volume", locale),  value: formatVolume(latest?.volume) },
  ];

  const COLUMNS = [
    t("market.col_time", locale),
    t("market.col_open", locale),
    t("market.col_high", locale),
    t("market.col_low", locale),
    t("market.col_close", locale),
    t("market.col_volume", locale),
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title={t("market.title", locale)}
       subtitle={`${t("market.subtitle", locale)} ${interval}`}
        meta={`02 · ${rows.length} bars`}
        actions={
          <a href={csvUrl(localSymbol || ctxSymbol, interval)}>
            <Button variant="outline" size="sm">
              <Download size={14} />
              {t("market.csv", locale)}
            </Button>
          </a>
        }
     />

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="space-y-4 xl:col-span-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {headerStats.map((s) => (
              <div key={s.label} className="rounded-md border border-border bg-card p-3">
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {s.label}
                </div>
               <div className="mt-1.5 font-mono text-lg font-semibold text-foreground">{s.value}</div>
              </div>
            ))}
          </div>

          <div className="rounded-md border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">{t("market.candle_title", locale)}</h3>
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {interval}
             </span>
            </div>
            <div className="px-2 py-3">
              <CandlestickChart points={rows.slice(-180)} height={340} />
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">{t("market.table_title", locale)}</h3>
           </div>
            <div className="max-h-[480px] overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    {COLUMNS.map((col) => (
                      <th key={col} className="px-3 py-2 font-semibold">
                        {col}
                      </th>
                    ))}
                 </tr>
                </thead>
                <tbody>
                  {rows.slice(-80).reverse().map((row) => (
                    <tr
                      key={row.timestamp}
                      className="border-t border-border hover:bg-muted/40"
                    >
                      <td className="px-3 py-2 font-mono text-xs">{shortDate(row.timestamp)}</td>
                      <td className="px-3 py-2 font-mono">{formatNumber(row.open)}</td>
                     <td className="px-3 py-2 font-mono text-up">{formatNumber(row.high)}</td>
                      <td className="px-3 py-2 font-mono text-down">{formatNumber(row.low)}</td>
                      <td className="px-3 py-2 font-mono font-semibold">{formatNumber(row.close)}</td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">
                        {formatVolume(row.volume)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
           </div>
          </div>
        </div>

        <div className="rounded-md border border-border bg-card p-3">
          <div className="mb-3">
            <h3 className="text-sm font-semibold text-foreground">{t("market.picker", locale)}</h3>
          </div>
          <Input
            value={filter}
           onChange={(e) => setFilter(e.target.value)}
            placeholder={t("market.filter_placeholder", locale)}
            className="mb-3 font-mono"
          />
          <div className="max-h-[440px] space-y-1 overflow-auto pr-1">
            {visibleSymbols.map((s) => {
              const active = (localSymbol || ctxSymbol) === s;
              return (
                <button
                  key={s}
                 onClick={() => {
                    setLocalSymbol(s);
                    setSymbol(s);
                  }}
                  className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] ${
                    active
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-foreground hover:bg-muted"
                  }`}
                >
                 <span className="font-mono">{s}</span>
                  {active ? <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" /> : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
 );
}