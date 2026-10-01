import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp, Crosshair, Loader2, Play, TestTubes, TrendingUp } from "lucide-react";
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
import { useBacktest } from "@/hooks/useBacktest";
import { STRATEGIES } from "@/utils/constants";
import { formatNumber, formatPercent, formatPrice, shortDate } from "@/utils/format";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "FPT", "HPG", "VHM", "VNM", "VIC",
];

const tooltipStyle = {
  background: "white",
  border: "1px solid hsl(152 18% 88%)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10)",
};

export function BacktestingPage() {
  const [symbol, setSymbol] = useState("VCB");
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
      toast.success("Backtest hoàn tất (lịch sử).");
    } catch (error) {
      toast.error(errorMessage(error, "Backtest thất bại."));
    }
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Backtesting"
        subtitle="Đánh giá hiệu suất lịch sử giả định. Không chứng minh chiến lược sẽ sinh lời trong tương lai."
        badge="ML"
        actions={
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-brand-500"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        }
      />

      {/* Strategy selector */}
      <div className="grid gap-3 md:grid-cols-2">
        {STRATEGIES.map((s) => (
          <button
            key={s.id}
            onClick={() => setStrategy(s.id)}
            className={cn(
              "rounded-xl border bg-card p-4 text-left transition-all",
              strategy === s.id
                ? "border-brand-500 bg-brand-50/50 shadow-glow"
                : "border-border hover:border-brand-300",
            )}
          >
            <div className="flex items-center gap-2">
              <span className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                strategy === s.id ? "bg-brand-500 text-white" : "bg-muted text-muted-foreground",
              )}>
                {s.id === "ma_crossover" ? <Crosshair size={14} /> : <TrendingUp size={14} />}
              </span>
              <div>
                <div className="font-semibold text-foreground">{s.label}</div>
                <div className="text-[11px] text-muted-foreground">
                  {s.id === "ma_crossover" ? "Short MA cắt lên Long MA → buy" : "RSI vượt 30/70 → buy/sell"}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Param panel */}
      <div className="card-elevated p-5">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Strategy
            </span>
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="w-full">
              {STRATEGIES.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Initial capital (₫)
            </span>
            <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Transaction fee
            </span>
            <Input type="number" step="0.0001" value={fee} onChange={(e) => setFee(Number(e.target.value))} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Slippage
            </span>
            <Input type="number" step="0.0001" value={slip} onChange={(e) => setSlip(Number(e.target.value))} />
          </label>

          {strategy === "ma_crossover" ? (
            <>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Short MA
                </span>
                <Input type="number" value={shortW} onChange={(e) => setShortW(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Long MA
                </span>
                <Input type="number" value={longW} onChange={(e) => setLongW(Number(e.target.value))} />
              </label>
            </>
          ) : (
            <>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  RSI period
                </span>
                <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Lower threshold
                </span>
                <Input type="number" value={lower} onChange={(e) => setLower(Number(e.target.value))} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
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
                  Running backtest...
                </>
              ) : (
                <>
                  <Play size={14} />
                  Run Backtest
                </>
              )}
            </Button>
          </div>
        </div>
        {run.isError ? <ErrorState message={errorMessage(run.error, "Backtest thất bại.")} /> : null}
      </div>

      {result ? (
        <>
          {/* Metrics grid */}
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

          {/* Equity + Drawdown */}
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="card-elevated p-5">
              <div className="mb-2 flex items-center gap-2">
                <TestTubes size={14} className="text-brand-600" />
                <h3 className="text-base font-bold text-foreground">Equity Curve</h3>
              </div>
              <EquityCurve data={result.equity_curve} />
            </div>
            <div className="card-elevated p-5">
              <div className="mb-2 flex items-center gap-2">
                <ArrowDown size={14} className="text-down" />
                <h3 className="text-base font-bold text-foreground">Drawdown</h3>
              </div>
              <div className="h-72 w-full">
                <ResponsiveContainer>
                  <AreaChart data={result.drawdown}>
                    <defs>
                      <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(0 70% 55%)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="hsl(0 70% 55%)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="hsl(152 25% 92%)" strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis stroke="hsl(158 15% 50%)" fontSize={11} />
                    <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="hsl(0 70% 55%)"
                      strokeWidth={2}
                      fill="url(#ddFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Trades table */}
          <div className="card-elevated overflow-hidden p-0">
            <div className="border-b border-border px-5 py-3">
              <h3 className="text-sm font-bold text-foreground">Trade history · {result.trades.length} lệnh</h3>
            </div>
            <div className="max-h-[480px] overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-muted/80 backdrop-blur text-[11px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    {["Entry Time", "Exit Time", "Entry", "Exit", "Qty", "PnL", "Return"].map((col) => (
                      <th key={col} className="px-4 py-2.5 font-semibold">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((trade, index) => (
                    <tr key={index} className="border-t border-border hover:bg-muted/30">
                      <td className="px-4 py-2 font-mono text-xs">{shortDate(trade.entry_time)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{shortDate(trade.exit_time)}</td>
                      <td className="px-4 py-2 font-mono">{formatNumber(trade.entry_price)}</td>
                      <td className="px-4 py-2 font-mono">{formatNumber(trade.exit_price)}</td>
                      <td className="px-4 py-2 font-mono">{formatNumber(trade.quantity, 4)}</td>
                      <td className="px-4 py-2 font-mono font-semibold">
                        <span className={trade.pnl >= 0 ? "text-up" : "text-down"}>
                          {formatNumber(trade.pnl)}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <Badge variant={trade.return_pct >= 0 ? "primary" : "warn"}>
                          <ArrowUp size={10} className={trade.return_pct >= 0 ? "" : "hidden"} />
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
        <EmptyState message="Chạy backtest để xem equity curve, drawdown và danh sách trades." />
      )}
    </div>
  );
}