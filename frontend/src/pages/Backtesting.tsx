import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp, Loader2, Play } from "lucide-react";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageTitle } from "@/components/common/PageTitle";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { useBacktest } from "@/hooks/useBacktest";
import { STRATEGIES } from "@/utils/constants";
import { formatNumber, formatPercent, formatPrice, shortDate } from "@/utils/format";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
];

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  fontSize: 12,
};

export function BacktestingPage() {
  const { symbol: ctxSymbol, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  // Sync localSymbol when ctxSymbol changes (e.g., user changes symbol from Header)
  useEffect(() => { setLocalSymbol(ctxSymbol); setSymbol(ctxSymbol); }, [ctxSymbol]);
  const symbol = localSymbol || ctxSymbol;
  const [strategy, setStrategy] = useState("ma_crossover");

  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: fetchSymbols,
    staleTime: 5 * 60 * 1000,
  });
  const availableSymbols = symbolsQuery.data?.symbols?.length
    ? symbolsQuery.data.symbols
    : DEFAULT_SYMBOLS;

  const { run } = useBacktest(symbol);
  const [capital, setCapital] = useState(10000);
  const [fee, setFee] = useState(0.001);
  const [slip, setSlip] = useState(0.0005);
  const [shortW, setShortW] = useState(20);
  const [longW, setLongW] = useState(50);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [lower, setLower] = useState(30);
  const [upper, setUpper] = useState(70);

  const result = run.data;

  const onRun = async () => {
    try {
      await run.mutateAsync({
        strategy, initial_capital: capital, transaction_fee: fee, slippage: slip,
        short_window: shortW, long_window: longW,
        rsi_period: rsiPeriod, lower_threshold: lower, upper_threshold: upper,
      });
      toast.success("Backtest hoan tat (lich su).");
    } catch (error) {
      toast.error(errorMessage(error, "Backtest that bai."));
    }
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Backtesting"
        subtitle="Danh gia hieu suat lich su gia dinh. Khong chung minh chien luoc se sinh loi trong tuong lai."
        meta="05 · Models"
        actions={
          <select
            value={symbol}
            onChange={(e) => { setLocalSymbol(e.target.value); setSymbol(e.target.value); }}
            className="h-9 rounded-md border border-input bg-card px-3 font-mono text-sm outline-none focus:border-foreground"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      <div>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Chien luoc
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {STRATEGIES.map((s) => (
            <button
              key={s.id}
              onClick={() => setStrategy(s.id)}
              className={cn(
                "rounded-md border bg-card p-3 text-left",
                strategy === s.id
                  ? "border-foreground"
                  : "border-border hover:border-foreground/40",
              )}
            >
              <div className="text-sm font-semibold text-foreground">{s.label}</div>
              <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {s.id === "ma_crossover" ? "Short MA cat len Long MA · buy" : "RSI vuot 30/70 · buy/sell"}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-md border border-border bg-card p-4">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Strategy
            </span>
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="w-full">
              {STRATEGIES.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Initial capital (VND)
            </span>
            <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Transaction fee
            </span>
            <Input type="number" step="0.0001" value={fee} onChange={(e) => setFee(Number(e.target.value))} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Slippage
            </span>
            <Input type="number" step="0.0001" value={slip} onChange={(e) => setSlip(Number(e.target.value))} />
          </label>

          {strategy === "ma_crossover" ? (
            <>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Short MA
                </span>
                <Input type="number" value={shortW} onChange={(e) => setShortW(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Long MA
                </span>
                <Input type="number" value={longW} onChange={(e) => setLongW(Number(e.target.value))} />
              </label>
            </>
          ) : (
            <>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  RSI period
                </span>
                <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Lower threshold
                </span>
                <Input type="number" value={lower} onChange={(e) => setLower(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Upper threshold
                </span>
                <Input type="number" value={upper} onChange={(e) => setUpper(Number(e.target.value))} />
              </label>
            </>
          )}
          <div className="flex items-end md:col-span-2">
            <Button onClick={() => void onRun()} disabled={run.isPending} className="w-full">
              {run.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Dang chay backtest
                </>
              ) : (
                <>
                  <Play size={14} />
                  Chay backtest
                </>
              )}
            </Button>
          </div>
        </div>
        {run.isError ? <ErrorState message={errorMessage(run.error, "Backtest that bai.")} /> : null}
      </div>

      {result ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Total Return"
              value={formatPercent(result.total_return)}
              delta={result.total_return}
            />
            <MetricCard label="Final Value" value={formatPrice(result.final_capital)} />
            <MetricCard label="Sharpe Ratio" value={formatNumber(result.sharpe_ratio)} />
            <MetricCard label="Max Drawdown" value={formatPercent(result.maximum_drawdown)} delta={result.maximum_drawdown} />
            <MetricCard label="Win Rate" value={formatPercent(result.win_rate)} delta={result.win_rate} />
            <MetricCard label="Trades" value={String(result.number_of_trades)} />
            <MetricCard label="Profit Factor" value={formatNumber(result.profit_factor)} />
            <MetricCard label="Initial Capital" value={formatPrice(result.initial_capital)} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-md border border-border bg-card">
              <div className="border-b border-border px-4 py-3">
                <h3 className="text-sm font-semibold text-foreground">Equity curve</h3>
              </div>
              <div className="px-2 py-3">
                <EquityCurve data={result.equity_curve} />
              </div>
            </div>
            <div className="rounded-md border border-border bg-card">
              <div className="border-b border-border px-4 py-3">
                <h3 className="text-sm font-semibold text-foreground">Drawdown</h3>
              </div>
              <div className="h-72 px-2 py-3">
                <ResponsiveContainer>
                  <AreaChart data={result.drawdown}>
                    <CartesianGrid stroke="hsl(220 14% 92%)" strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis stroke="hsl(220 10% 50%)" fontSize={11} />
                    <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="hsl(0 64% 48%)"
                      strokeWidth={1.5}
                      fill="hsl(0 64% 48%)"
                      fillOpacity={0.1}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-border bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">Trade history · {result.trades.length} lenh</h3>
            </div>
            <div className="max-h-[480px] overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    {["Entry", "Exit", "Entry $", "Exit $", "Qty", "PnL", "Return"].map((col) => (
                      <th key={col} className="px-3 py-2 font-semibold">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((trade, index) => (
                    <tr key={index} className="border-t border-border hover:bg-muted/30">
                      <td className="px-3 py-2 font-mono text-xs">{shortDate(trade.entry_time)}</td>
                      <td className="px-3 py-2 font-mono text-xs">{shortDate(trade.exit_time)}</td>
                      <td className="px-3 py-2 font-mono">{formatNumber(trade.entry_price)}</td>
                      <td className="px-3 py-2 font-mono">{formatNumber(trade.exit_price)}</td>
                      <td className="px-3 py-2 font-mono">{formatNumber(trade.quantity, 4)}</td>
                      <td className="px-3 py-2 font-mono font-semibold">
                        <span className={trade.pnl >= 0 ? "text-up" : "text-down"}>
                          {formatNumber(trade.pnl)}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={trade.return_pct >= 0 ? "success" : "danger"}>
                          {trade.return_pct >= 0 ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
                          {formatPercent(trade.return_pct)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <EmptyState message="Chay backtest de xem equity curve, drawdown va danh sach trades." />
      )}
    </div>
  );
}