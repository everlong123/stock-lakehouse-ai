import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp, Loader2, Play } from "lucide-react";
import { fetchSymbols } from "@/api/stocks";
import { errorMessage } from "@/api/client";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useMarket } from "@/hooks/useMarket";
import { useBacktest } from "@/hooks/useBacktest";
import { formatNumber, formatPercent, formatPrice, shortDate, currencyForSymbol } from "@/utils/format";
import { toast } from "sonner";

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "JPM", "V",
];

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
};

/**
 * The single-symbol tab of the strategy evaluation page.
 *
 * WHY IT IS A TAB AND NOT ITS OWN PAGE
 * -------------------------------------
 * A single-stock backtest and the multi-symbol walk-forward report answer
 * the same question at two different scales: "does this rule make money on
 * this stock?" and "does it make money *in general*?". Splitting them
 * across two navigation entries made the reader hunt for the baseline
 * comparison that only lived on one of them. Now they sit side by side
 * under one tab strip, and the single-symbol view points at the population
 * result that judges it.
 *
 * WHY THE STRATEGY IS A PROP AND NOT LOCAL STATE: the page owns the
 * strategy so that both tabs measure the SAME rule. The single-symbol run
 * and the population report then answer the same question at two scales,
 * and switching tabs does not silently change what is being compared.
 */
export function SingleSymbolBacktest({ strategy }: { strategy: string }) {
  const { symbol: ctxSymbol, setSymbol } = useMarket();
  const [localSymbol, setLocalSymbol] = useState(ctxSymbol);
  // Sync localSymbol when ctxSymbol changes (e.g., user changes symbol from Header)
  useEffect(() => { setLocalSymbol(ctxSymbol); setSymbol(ctxSymbol); }, [ctxSymbol]);
  const symbol = localSymbol || ctxSymbol;

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
  // The portfolio is denominated in the traded instrument's own currency:
  // buying VCB shares spends dong, buying AAPL shares spends dollars. The
  // backtest engine works in raw price units, so the label has to follow
  // the symbol.
  const currency = currencyForSymbol(symbol);

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
    <div className="space-y-12">
      {/* The symbol picker belongs to this tab only, so it sits here rather
          than in the page header - the header is shared by both tabs. */}
      <section className="rounded border border-hairline bg-surface p-4">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="block text-small">
            <span className="label mb-1 block">Mã cổ phiếu</span>
            <Select
              value={symbol}
              onChange={(e) => { setLocalSymbol(e.target.value); setSymbol(e.target.value); }}
              className="w-full"
            >
              {availableSymbols.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </label>
          <label className="block text-small">
            <span className="label mb-1 block">Vốn ban đầu</span>
            <Input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} />
          </label>
          <label className="block text-small">
            <span className="label mb-1 block">Phí giao dịch</span>
            <Input type="number" step="0.0001" value={fee} onChange={(e) => setFee(Number(e.target.value))} />
          </label>
          <label className="block text-small">
            <span className="label mb-1 block">Độ trượt giá</span>
            <Input type="number" step="0.0001" value={slip} onChange={(e) => setSlip(Number(e.target.value))} />
          </label>

          {strategy === "ma_crossover" ? (
            <>
              <label className="block text-small">
                <span className="label mb-1 block">Short MA</span>
                <Input type="number" value={shortW} onChange={(e) => setShortW(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Long MA</span>
                <Input type="number" value={longW} onChange={(e) => setLongW(Number(e.target.value))} />
              </label>
            </>
          ) : (
            <>
              <label className="block text-small">
                <span className="label mb-1 block">RSI period</span>
                <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Lower threshold</span>
                <Input type="number" value={lower} onChange={(e) => setLower(Number(e.target.value))} />
              </label>
              <label className="block text-small">
                <span className="label mb-1 block">Upper threshold</span>
                <Input type="number" value={upper} onChange={(e) => setUpper(Number(e.target.value))} />
              </label>
            </>
          )}
          <div className="flex items-end md:col-span-2">
            <Button variant="primary" onClick={() => void onRun()} disabled={run.isPending} className="w-full">
              {run.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Đang chạy backtest
                </>
              ) : (
                <>
                  <Play size={14} />
                  Chạy backtest
                </>
              )}
            </Button>
          </div>
        </div>
        {run.isError ? <ErrorState message={errorMessage(run.error, "Backtest thất bại.")} /> : null}
      </section>

      {result ? (
        <>
          {/* Eight metrics: a 4-column hairline grid, no boxes. */}
          <section>
            <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
              <MetricCard
                label="Total Return"
                value={formatPercent(result.total_return)}
              />
              <MetricCard label="Final Value" value={formatPrice(result.final_capital, currency)} />
              <MetricCard label="Sharpe Ratio" value={formatNumber(result.sharpe_ratio)} />
              <MetricCard label="Max Drawdown" value={formatPercent(result.maximum_drawdown)} />
              <MetricCard label="Win Rate" value={formatPercent(result.win_rate)} />
              <MetricCard label="Trades" value={String(result.number_of_trades)} />
              <MetricCard label="Profit Factor" value={formatNumber(result.profit_factor)} />
              <MetricCard label="Initial Capital" value={formatPrice(result.initial_capital, currency)} />
            </div>
          </section>

          {/* The benchmark row: the same bars, the same fees, the only
              difference is that the baseline never sells. Without it the
              return above has nothing to be measured against. */}
          {result.benchmark ? (
            <section>
              <div className="section-head">
                <h2 className="section-title">So sánh với mua &amp; giữ</h2>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
                <MetricCard
                  label="Mua & giữ · Total Return"
                  value={formatPercent(result.benchmark.total_return ?? 0)}
                />
                <MetricCard
                  label="Mua & giữ · Sharpe"
                  value={formatNumber(result.benchmark.sharpe_ratio ?? 0)}
                />
                <MetricCard
                  label="Mua & giữ · Max Drawdown"
                  value={formatPercent(result.benchmark.maximum_drawdown ?? 0)}
                />
                <MetricCard
                  label="Chiến lược vượt baseline"
                  value={
                    result.excess_return_vs_benchmark == null
                      ? "—"
                      : formatPercent(result.excess_return_vs_benchmark)
                  }
                />
              </div>
              <p className="mt-3 text-small text-muted">
                Baseline "mua &amp; giữ" được mô phỏng trên{" "}
                <span className="font-mono">cùng các phiên</span>, cùng phí giao dịch và
                cùng độ trượt giá với chiến lược. Nếu chiến lược không vượt được đường này
                thì đó là bằng chứng rằng việc chọn điểm vào lệnh chưa tạo ra giá trị.
                Xem tab <span className="font-mono">Walk-forward đa mã</span> để biết kết quả
                này có đúng trên nhiều mã hay chỉ đúng với mã này.
              </p>
            </section>
          ) : null}

          <div className="grid gap-12 xl:grid-cols-2">
            <section>
              <div className="section-head">
                <h2 className="section-title">Equity curve</h2>
              </div>
              <div className="pt-4">
                <EquityCurve data={result.equity_curve} benchmark={result.benchmark?.equity_curve} />
              </div>
            </section>
            <section>
              <div className="section-head">
                <h2 className="section-title">Drawdown</h2>
              </div>
              <div className="h-72 pt-4">
                <ResponsiveContainer>
                  <AreaChart data={result.drawdown}>
                    <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
                    <XAxis dataKey="timestamp" hide />
                    <YAxis stroke="hsl(var(--muted))" fontSize={12} />
                    <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => shortDate(String(v))} />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="hsl(var(--negative))"
                      strokeWidth={1.5}
                      fill="hsl(var(--negative))"
                      fillOpacity={0.1}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          <section>
            <div className="section-head">
              <h2 className="section-title">Lịch sử lệnh · {result.trades.length} lệnh</h2>
            </div>
            <div className="mt-4 max-h-[480px] overflow-auto rounded border border-hairline bg-surface">
              <table className="table">
                <thead className="sticky top-0">
                  <tr>
                    {["Entry", "Exit", "Entry $", "Exit $", "Qty", "Fees", "PnL", "Return"].map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((trade, index) => (
                    <tr key={index}>
                      <td className="font-mono whitespace-nowrap text-muted">{shortDate(trade.entry_time)}</td>
                      <td className="font-mono whitespace-nowrap text-muted">{shortDate(trade.exit_time)}</td>
                      <td className="font-mono tabular-nums">{formatNumber(trade.entry_price)}</td>
                      <td className="font-mono tabular-nums">{formatNumber(trade.exit_price)}</td>
                      <td className="font-mono tabular-nums">{formatNumber(trade.quantity, 4)}</td>
                      <td className="font-mono tabular-nums text-muted">{formatNumber(trade.fees)}</td>
                      <td className="font-mono font-semibold tabular-nums">
                        <span className={trade.pnl >= 0 ? "text-primary" : "text-negative"}>
                          {formatNumber(trade.pnl)}
                        </span>
                      </td>
                      <td>
                        <Badge variant={trade.return_pct >= 0 ? "primary" : "negative"}>
                          {trade.return_pct >= 0 ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
                          {formatPercent(trade.return_pct)}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <EmptyState message="Chạy backtest để xem equity curve, drawdown và danh sách trades." />
      )}
    </div>
  );
}
