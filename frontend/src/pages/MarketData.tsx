import { csvUrl } from "@/api/stocks";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Loading } from "@/components/common/Loading";
import { PageTitle } from "@/components/common/PageTitle";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { useMarket } from "@/hooks/useMarket";
import { useStocks } from "@/hooks/useStocks";
import { formatNumber, formatPrice, shortDate } from "@/utils/format";

export function MarketDataPage() {
  const { symbol, interval } = useMarket();
  const query = useStocks();

  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Cannot connect to backend API.")} />;
  const rows = query.data?.rows ?? [];
  if (!rows.length) return <EmptyState message="No market data available for the selected range." />;
  const latest = query.data?.latest;

  return (
    <div className="space-y-4">
      <PageTitle title="Market Data" subtitle={`${symbol} · ${interval}`} />
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        <span>Data source: {query.data?.data_source || "Yahoo Finance / sample"}</span>
        <span>Last updated: {query.data?.last_updated?.replace("T", " ").slice(0, 19)}</span>
        <span>Close: {formatPrice(latest?.close)}</span>
        <a href={csvUrl(symbol, interval)}>
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
