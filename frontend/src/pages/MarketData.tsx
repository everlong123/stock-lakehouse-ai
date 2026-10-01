import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
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
import { formatNumber, formatPrice, formatVolume, shortDate } from "@/utils/format";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
  "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
  "VIC", "VPB", "CTG", "TPB", "SHB", "STB", "PNJ", "HDB", "LPB", "MSB",
];

export function MarketDataPage() {
  const { symbol: ctxSymbol, interval, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
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
  if (query.isError) return <ErrorState message={errorMessage(query.error, "Không kết nối được backend API.")} />;

  const rows = query.data?.rows ?? [];
  if (!rows.length) return <EmptyState message={`Không có dữ liệu cho ${localSymbol || ctxSymbol}.`} />;

  const latest = query.data?.latest;
  const headerStats = [
    { label: "Source", value: query.data?.data_source || "Yahoo" },
    { label: "Rows", value: rows.length.toLocaleString("en-US") },
    { label: "Last Close", value: formatPrice(latest?.close) },
    { label: "Last Volume", value: formatVolume(latest?.volume) },
  ];

  return (
    <div className="space-y-6">
      <PageTitle
        title="Market Data"
        subtitle={`Dữ liệu OHLCV thô từ Bronze layer · interval ${interval}`}
        badge={`${rows.length} bars`}
        actions={
          <a href={csvUrl(localSymbol || ctxSymbol, interval)}>
            <Button variant="outline">
              <Download size={14} />
              Download CSV
            </Button>
          </a>
        }
      />

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="xl:col-span-3 space-y-4">
          {/* Stats row */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {headerStats.map((s) => (
              <div key={s.label} className="card-elevated p-4">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {s.label}
                </div>
                <div className="mt-1.5 font-mono text-lg font-bold text-foreground">{s.value}</div>
              </div>
            ))}
          </div>

          {/* Chart */}
          <div className="card-elevated p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-bold text-foreground">Candlestick · 180 phiên gần nhất</h3>
              <span className="chip">{interval}</span>
            </div>
            <CandlestickChart points={rows.slice(-180)} height={340} />
          </div>

          {/* Table */}
          <div className="card-elevated overflow-hidden p-0">
            <div className="border-b border-border px-5 py-3">
              <h3 className="text-sm font-bold text-foreground">Bảng dữ liệu · 80 phiên cuối</h3>
            </div>
            <div className="max-h-[480px] overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-muted/80 backdrop-blur text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    {["Time", "Open", "High", "Low", "Close", "Volume"].map((col) => (
                      <th key={col} className="px-4 py-2.5 font-semibold">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(-80).reverse().map((row) => (
                    <tr
                      key={row.timestamp}
                      className="border-t border-border transition-colors hover:bg-muted/40"
                    >
                      <td className="px-4 py-2 font-mono text-xs">{shortDate(row.timestamp)}</td>
                      <td className="px-4 py-2 font-mono">{formatNumber(row.open)}</td>
                      <td className="px-4 py-2 font-mono text-up">{formatNumber(row.high)}</td>
                      <td className="px-4 py-2 font-mono text-down">{formatNumber(row.low)}</td>
                      <td className="px-4 py-2 font-mono font-semibold">{formatNumber(row.close)}</td>
                      <td className="px-4 py-2 font-mono text-muted-foreground">
                        {formatVolume(row.volume)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Sidebar: symbol picker */}
        <div className="card-elevated p-4">
          <div className="mb-3 flex items-center gap-2">
            <Search size={14} className="text-muted-foreground" />
            <h3 className="text-sm font-bold text-foreground">Symbol picker</h3>
          </div>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Lọc mã CK..."
            className="mb-3"
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
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-brand-50 font-semibold text-brand-700"
                      : "text-foreground hover:bg-muted"
                  }`}
                >
                  <span className="font-mono">{s}</span>
                  {active ? <span className="h-2 w-2 rounded-full bg-brand-500" /> : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}