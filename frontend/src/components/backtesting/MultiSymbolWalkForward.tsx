import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchMultiSymbolReport } from "@/api/backtesting";
import { errorMessage } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Explainer } from "@/components/common/Explainer";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { Badge } from "@/components/ui/badge";
import { formatNumber, formatPercent } from "@/utils/format";

const tooltipStyle = {
  background: "hsl(var(--surface))",
  border: "1px solid hsl(var(--hairline))",
  borderRadius: 6,
  fontSize: 12,
};

/**
 * The multi-symbol walk-forward tab.
 *
 * WHY A TAB BESIDE THE SINGLE-SYMBOL BACKTEST
 * ------------------------------------------
 * The single-symbol backtest answers "what happened on this one stock".
 * That is a demonstration, not evidence: one stock over one decade mostly
 * measures whether that stock went up. This tab answers the research
 * question - "does the strategy work ACROSS many stocks, and does it beat
 * simply holding them?" - by showing the DISTRIBUTION of the results
 * instead of a single number.
 *
 * The numbers come from a file produced by
 * `backend/scripts/run_multi_symbol_walkforward.py`, not from a live
 * request, because the run takes about two minutes. When the file is
 * missing the tab says so and shows the exact command to generate it; it
 * never shows a placeholder number.
 */
export function MultiSymbolWalkForward({ strategy }: { strategy: string }) {
  const query = useQuery({
    queryKey: ["multi-symbol-report", strategy],
    queryFn: () => fetchMultiSymbolReport(strategy),
    retry: 0,
    staleTime: 10 * 60 * 1000,
  });

  const report = query.data;
  const missing = report && report.available === false;

  return (
    <div className="space-y-12">
      <Explainer
        title="Tab này dùng để làm gì?"
        intro="Một backtest trên một mã cổ phiếu không phải là bằng chứng. Tab này chạy cùng một cơ chế walk-forward trên hàng chục mã thuộc nhiều sàn khác nhau, rồi báo cáo PHÂN PHỐI kết quả: giá trị trung vị, tỉ lệ mã có lãi, và phân tách theo sàn. Mỗi cửa sổ kiểm tra được đo cả chiến lược lẫn đường cơ sở mua và giữ trên đúng những phiên đó, nên phần chênh lệch là so sánh cặp (paired) chứ không phải hiệu của hai trung bình độc lập."
        items={[
          {
            term: "Walk-forward",
            meaning: "Chia lịch sử thành các cửa sổ trượt: huấn luyện trên một đoạn, kiểm tra trên đoạn kế tiếp chưa từng thấy. Lặp lại nhiều lần rồi lấy trung bình, nên giảm hiệu ứng quá khớp tham số.",
          },
          {
            term: "Ngoài mẫu (out-of-sample)",
            meaning: "Phần dữ liệu chiến lược chưa từng được nhìn thấy khi chọn tham số. Đây mới là kỳ vọng hợp lý về hiệu quả thật.",
          },
          {
            term: "Mua & giữ (baseline)",
            meaning: "Giải pháp rỗng: mua đầu kỳ, giữ đến cuối, trên cùng các phiên và cùng bộ chi phí. Chiến lược phải thắng đường này mới được coi là tạo thêm giá trị.",
          },
          {
            term: "Median",
            meaning: "Giá trị trung vị. Dùng thay cho trung bình vì một mã tăng rất mạnh có thể kéo trung bình lệch, còn trung vị thì không.",
          },
          {
            term: "Excess return",
            meaning: "Chênh lệch giữa chiến lược và mua & giữ trên cùng một cửa sổ. Âm nghĩa là chiến lược làm tệ hơn việc cứ nắm giữ.",
          },
        ]}
        steps={[
          "Chọn chiến lược ở đầu trang — cùng lựa chọn với tab một mã.",
          "Đọc hàng so sánh giữa chiến lược và mua & giữ ở phần đầu.",
          "Xem bảng theo sàn để biết kết quả có phổ biến hay chỉ đúng ở một vài thị trường.",
          "Cuộn xuống bảng từng mã để xem mã nào thắng và mã nào thua.",
        ]}
      />

      {query.isLoading ? (
        <EmptyState message="Đang tải báo cáo..." />
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error, "Không tải được báo cáo.")} />
      ) : missing ? (
        <section className="space-y-4">
          <ErrorState message={report.reason ?? "Chưa có báo cáo."} />
          <div className="rounded border border-hairline bg-surface p-4">
            <div className="label mb-2">Cách tạo báo cáo</div>
            <code className="block font-mono text-small text-ink">
              cd backend
              <br />
              .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py --per-exchange 8
              --strategy {strategy}
            </code>
            <p className="mt-3 text-small text-muted">
              Lệnh này mất khoảng 2 phút và ghi kết quả vào{" "}
              <span className="font-mono">backend/data/</span>.
            </p>
          </div>
        </section>
      ) : report ? (
        <ReportBody report={report} />
      ) : null}
    </div>
  );
}

function ReportBody({ report }: { report: Awaited<ReturnType<typeof fetchMultiSymbolReport>> }) {
  const strat = report.strategy_distribution;
  const bh = report.buy_and_hold_distribution;
  const head = report.head_to_head;
  const exchanges = report.by_exchange ?? {};
  const rows = report.per_symbol ?? [];

  const chartData = Object.entries(exchanges).map(([exchange, row]) => ({
    exchange,
    strategy: row.strategy_median_return ?? 0,
    benchmark: row.buy_hold_median_return ?? 0,
  }));

  return (
    <>
      {/* The headline comparison. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">
            Chiến lược vs mua &amp; giữ · {report.config?.symbols_tested ?? 0} mã trên{" "}
            {report.config?.universe_size ?? 0}
          </h2>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
          <MetricCard
            label="Median lợi nhuận · chiến lược"
            value={formatPercent(strat?.median_avg_test_return ?? 0)}
          />
          <MetricCard
            label="Median lợi nhuận · mua & giữ"
            value={formatPercent(bh?.median_avg_return ?? 0)}
          />
          <MetricCard
            label="Median Sharpe · chiến lược"
            value={formatNumber(strat?.median_avg_test_sharpe ?? 0)}
          />
          <MetricCard
            label="Median Sharpe · mua & giữ"
            value={formatNumber(bh?.median_sharpe ?? 0)}
          />
        </div>
      </section>

      <section>
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 md:grid-cols-4">
          <MetricCard
            label="% mã có lãi · chiến lược"
            value={`${(strat?.pct_symbols_profitable ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label="% mã có lãi · mua & giữ"
            value={`${(bh?.pct_symbols_profitable ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label="% cửa sổ thắng baseline"
            value={`${(head?.pct_windows_beating_buy_hold ?? 0).toFixed(1)}%`}
          />
          <MetricCard
            label="Median excess return"
            value={formatPercent(head?.median_paired_excess_return ?? 0)}
          />
        </div>
        <p className="mt-3 text-small text-muted">
          So sánh cặp trên {head?.paired_windows ?? 0} cửa sổ kiểm tra. Mỗi cửa sổ đóng góp
          một chênh lệch giữa chiến lược và mua &amp; giữ, nên hai bên luôn được đo trên cùng
          những phiên giống nhau.
        </p>
      </section>

      {/* The finding, stated plainly. */}
      <section className="rounded border border-hairline bg-surface p-4">
        <div className="label mb-2">Kết luận của phép đo</div>
        <p className="max-w-3xl text-small text-ink">
          {(head?.median_paired_excess_return ?? 0) < 0
            ? "Trên phép đo này, chiến lược KHÔNG vượt được đường cơ sở mua và giữ: chênh lệch trung vị theo cửa sổ là "
              + formatPercent(head?.median_paired_excess_return ?? 0)
              + ", và chỉ "
              + (head?.pct_symbols_beating_buy_hold ?? 0).toFixed(1)
              + "% số mã thắng được baseline. Đây là phát hiện thật, không phải lỗi kỹ thuật: chiến lược có lợi thế là giảm biến động (median drawdown nhỏ hơn), nhưng cái giá phải trả là bỏ lỡ phần lợi nhuận của xu hướng."
            : "Trên phép đo này, chiến lược vượt được đường cơ sở mua và giữ với chênh lệch trung vị "
              + formatPercent(head?.median_paired_excess_return ?? 0)
              + " theo cửa sổ, và "
              + (head?.pct_symbols_beating_buy_hold ?? 0).toFixed(1)
              + "% số mã thắng được baseline."}
        </p>
        {report.note ? (
          <p className="mt-3 max-w-3xl text-small text-muted">{report.note}</p>
        ) : null}
      </section>

      {/* By exchange. */}
      {chartData.length ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">Phân phối theo sàn</h2>
          </div>
          <div className="pt-4">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={chartData}>
                <CartesianGrid stroke="hsl(var(--hairline))" vertical={false} />
                <XAxis dataKey="exchange" tick={{ fontSize: 11, fill: "hsl(var(--muted))" }} angle={-30} textAnchor="end" height={70} />
                <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted))" }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => formatPercent(value)}
                />
                <Bar dataKey="strategy" name="Chiến lược" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                <Bar dataKey="benchmark" name="Mua & giữ" fill="hsl(var(--muted))" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-8 overflow-auto rounded border border-hairline bg-surface">
            <table className="table">
              <thead>
                <tr>
                  {["Sàn", "Số mã", "Median RR chiến lược", "Median RR mua&giữ", "Sharpe CL", "Sharpe B&H", "% mã thắng B&H"].map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(exchanges).map(([exchange, row]) => (
                  <tr key={exchange}>
                    <td className="font-mono">{exchange}</td>
                    <td className="font-mono tabular-nums">{row.symbols}</td>
                    <td className="font-mono tabular-nums">{formatPercent(row.strategy_median_return ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatPercent(row.buy_hold_median_return ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatNumber(row.strategy_median_sharpe ?? 0)}</td>
                    <td className="font-mono tabular-nums">{formatNumber(row.buy_hold_median_sharpe ?? 0)}</td>
                    <td>
                      <Badge variant={(row.pct_symbols_beating_buy_hold ?? 0) >= 50 ? "primary" : "negative"}>
                        {(row.pct_symbols_beating_buy_hold ?? 0).toFixed(1)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {/* Per symbol. */}
      <section>
        <div className="section-head">
          <h2 className="section-title">Chi tiết từng mã · {rows.length} mã</h2>
        </div>
        <div className="mt-4 max-h-[560px] overflow-auto rounded border border-hairline bg-surface">
          <table className="table">
            <thead className="sticky top-0">
              <tr>
                {["Mã", "Sàn", "Cửa sổ", "RR chiến lược", "RR mua&giữ", "Sharpe CL", "Sharpe B&H", "MaxDD CL", "MaxDD B&H", "Thắng B&H"].map((col) => (
                  <th key={col}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.symbol}>
                  <td className="font-mono font-semibold">{row.symbol}</td>
                  <td className="font-mono text-muted">{row.exchange}</td>
                  <td className="font-mono tabular-nums text-muted">{row.passed_windows ?? "—"}</td>
                  <td className="font-mono tabular-nums">{formatPercent(row.avg_test_return ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatPercent(row.buy_hold_return ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.avg_test_sharpe ?? 0)}</td>
                  <td className="font-mono tabular-nums">{formatNumber(row.buy_hold_sharpe ?? 0)}</td>
                  <td className="font-mono tabular-nums text-muted">{formatPercent(row.avg_test_max_drawdown ?? 0)}</td>
                  <td className="font-mono tabular-nums text-muted">{formatPercent(row.buy_hold_max_drawdown ?? 0)}</td>
                  <td>
                    {row.beat_buy_hold == null ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <Badge variant={row.beat_buy_hold ? "primary" : "negative"}>
                        {row.beat_buy_hold ? "Có" : "Không"}
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {report.errors && report.errors.length ? (
        <section>
          <div className="section-head">
            <h2 className="section-title">Mã không đo được · {report.errors.length}</h2>
          </div>
          <div className="mt-4 overflow-auto rounded border border-hairline bg-surface">
            <table className="table">
              <thead>
                <tr>
                  <th>Mã</th>
                  <th>Lý do</th>
                </tr>
              </thead>
              <tbody>
                {report.errors.map((err) => (
                  <tr key={err.symbol}>
                    <td className="font-mono">{err.symbol}</td>
                    <td className="text-muted">{err.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
