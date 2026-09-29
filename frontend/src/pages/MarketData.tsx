import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useMarket } from "@/hooks/useMarket";
import { useStocks } from "@/hooks/useStocks";
import { csvUrl, fetchSymbols } from "@/api/stocks";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { formatNumber, formatPrice, shortDate } from "@/utils/format";

// Default VN stocks list
const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
  "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
  "VIC", "VPB", "CTG", "TPB", "SHB", "STB", "PNJ", "HDB", "LPB", "MSB",
  "OCB", "REE", "NVL", "PDR", "BCM", "SBT", "IMP", "KDC", "PC1", "HDG",
  "DRC", "DXG", "IDJ", "ITA", "JVC", "LSG", "MSH", "NSC", "PVT", "MBC",
  "DIG", "FCN", "HCM", "CTC", "SMT", "KSC", "VGC", "BVH", "C22", "C32",
];

export function MarketDataPage() {
  const { symbol: ctxSymbol, interval, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  const query = useStocks(localSymbol || ctxSymbol, interval);

  // Fetch available symbols from API
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

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Cannot connect to backend API.")} />;
  const rows = query.data?.rows ?? [];
  if (!rows.length) return <EmptyState message={`No market data for ${localSymbol || ctxSymbol}.`} />;
  const latest = query.data?.latest;

  return (
    <div className="space-y-4">
      <PageTitle title="Market Data" subtitle={`${interval}`} />
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
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
        <span>Data source: {query.data?.data_source || "Yahoo Finance"}</span>
        <span>Rows: {rows.length}</span>
        <span>Close: {formatPrice(latest?.close)}</span>
        <a href={csvUrl(localSymbol || ctxSymbol, interval)}>
          <Button variant="outline">Download CSV</Button>
        </a>
      </div>
      <div className="rounded-lg border border-border bg-card p-4">
        <CandlestickChart points={rows.slice(-180)} />
      </div>
      <div className="overflow-auto rounded-lg border border-border">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-muted text-xs uppercase text-muted-foreground">
            <tr>
              {["Time", "Open", "High", "Low", "Close", "Volume"].map((col) => (
                <th key={col} className="px-3 py-2 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(-80).reverse().map((row) => (
              <tr key={row.timestamp} className="border-t border-border">
                <td className="px-3 py-2 font-mono">{shortDate(row.timestamp)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(row.open)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(row.high)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(row.low)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(row.close)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(row.volume, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
