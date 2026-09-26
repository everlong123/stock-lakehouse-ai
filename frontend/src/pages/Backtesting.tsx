import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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
import { useBacktest } from "@/hooks/useBacktest";
import { STRATEGIES } from "@/utils/constants";
import { formatNumber, formatPercent, formatPrice, shortDate } from "@/utils/format";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
  "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
  "VIC", "VPB", "CTG", "TPB", "SHB", "STB", "PNJ", "HDB", "LPB", "MSB",
  "OCB", "REE", "NVL", "PDR", "BCM", "SBT", "IMP", "KDC", "PC1", "HDG",
  "DRC", "DXG", "IDJ", "ITA", "JVC", "LSG", "MSH", "NSC", "PVT", "MBC",
  "DIG", "FCN", "HCM", "CTC", "SMT", "KSC", "VGC", "BVH", "C22", "C32",
];

export function BacktestingPage() {
  const [symbol, setSymbol] = useState("VCB");
  const [strategy, setStrategy] = useState("ma_crossover");

  // Symbol selector
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
        strategy,
        initial_capital: capital,
        transaction_fee: fee,
        slippage: slip,
        short_window: shortW,
        long_window: longW,
        rsi_period: rsiPeriod,
        lower_threshold: lower,
        upper_threshold: upper,
      });
      toast.success("Backtest finished (historical only).");
    } catch (error) {
      toast.error(errorMessage(error, "Backtest failed."));
    }
  };

  return (
    <div className="space-y-4">
      <PageTitle
        title="Backtesting"
        subtitle="Đánh giá hiệu suất lịch sử giả định. Không chứng minh chiến lược sẽ sinh lời trong tương lai."
      />
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <span>Symbol:</span>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-foreground"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-4">
        <label className="text-sm">
          Strategy
          <Select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="mt-1 w-full">
            {STRATEGIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="text-sm">
          Initial Capital
          <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          Transaction Fee
          <Input type="number" step="0.0001" value={fee} onChange={(e) => setFee(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          Slippage
          <Input type="number" step="0.0001" value={slip} onChange={(e) => setSlip(Number(e.target.value))} />
        </label>
        {strategy === "ma_crossover" ? (
          <>
            <label className="text-sm">
              Short MA
              <Input type="number" value={shortW} onChange={(e) => setShortW(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Long MA
              <Input type="number" value={longW} onChange={(e) => setLongW(Number(e.target.value))} />
            </label>
          </>
        ) : (
          <>
            <label className="text-sm">
              RSI period
              <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Lower
              <Input type="number" value={lower} onChange={(e) => setLower(Number(e.target.value))} />
            </label>
            <label className="text-sm">
              Upper
              <Input type="number" value={upper} onChange={(e) => setUpper(Number(e.target.value))} />
            </label>
          </>
        )}
        <div className="flex items-end">
          <Button onClick={() => void onRun()} disabled={run.isPending}>
            {run.isPending ? "Running..." : "Run Backtest"}
          </Button>
        </div>
      </div>
      {run.isError ? <ErrorState message={errorMessage(run.error, "Backtest failed.")} /> : null}
      {result ? (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <MetricCard label="Total Return" value={formatPercent(result.total_return)} />
            <MetricCard label="Final Portfolio Value" value={formatPrice(result.final_capital)} />
            <MetricCard label="Sharpe Ratio" value={formatNumber(result.sharpe_ratio)} />
            <MetricCard label="Maximum Drawdown" value={formatPercent(result.maximum_drawdown)} />
            <MetricCard label="Win Rate" value={formatPercent(result.win_rate)} />
            <MetricCard label="Number of Trades" value={String(result.number_of_trades)} />
            <MetricCard label="Profit Factor" value={formatNumber(result.profit_factor)} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="mb-2 text-sm font-semibold">Equity Curve</div>
            <EquityCurve data={result.equity_curve} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="mb-2 text-sm font-semibold">Drawdown</div>
            <div className="h-48">
              <ResponsiveContainer>
                <AreaChart data={result.drawdown}>
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" hide />
                  <YAxis stroke="hsl(var(--muted-foreground))" />
                  <Tooltip />
                  <Area dataKey="drawdown" stroke="hsl(var(--down))" fill="hsl(var(--down) / 0.2)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="overflow-auto rounded-lg border border-border">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  {["Entry Time", "Exit Time", "Entry Price", "Exit Price", "Quantity", "PnL", "Return"].map((col) => (
                    <th key={col} className="px-3 py-2">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade, index) => (
                  <tr key={index} className="border-t border-border">
                    <td className="px-3 py-2">{shortDate(trade.entry_time)}</td>
                    <td className="px-3 py-2">{shortDate(trade.exit_time)}</td>
                    <td className="px-3 py-2 font-mono">{formatNumber(trade.entry_price)}</td>
                    <td className="px-3 py-2 font-mono">{formatNumber(trade.exit_price)}</td>
                    <td className="px-3 py-2 font-mono">{formatNumber(trade.quantity, 4)}</td>
                    <td className="px-3 py-2 font-mono">{formatNumber(trade.pnl)}</td>
                    <td className="px-3 py-2 font-mono">{formatPercent(trade.return_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <EmptyState message="Run a backtest to see equity, drawdown and trade history." />
      )}
    </div>
  );
}
