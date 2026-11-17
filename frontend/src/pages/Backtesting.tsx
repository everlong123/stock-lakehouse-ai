import { useState } from "react";
import { Explainer } from "@/components/common/Explainer";
import { PageTitle } from "@/components/common/PageTitle";
import { MultiSymbolWalkForward } from "@/components/backtesting/MultiSymbolWalkForward";
import { SingleSymbolBacktest } from "@/components/backtesting/SingleSymbolBacktest";
import { STRATEGIES } from "@/utils/constants";
import { cn } from "@/lib/utils";

type TabId = "single" | "population";

/**
 * Strategy evaluation — one page, two scales.
 *
 * WHY TWO TABS INSTEAD OF TWO PAGES
 * ---------------------------------
 * A single-stock backtest and a multi-symbol walk-forward report are the
 * same question asked at two scales: does this trading rule actually make
 * money, or is the number just the stock going up? The reader almost
 * always wants both — the single run for intuition, the population run for
 * evidence — and the baseline comparison lived on only one of them, so the
 * reader had to know which page carried the honest half.
 *
 * Keeping them on one page also lets the page OWN the strategy choice: the
 * same rule is measured on one stock and on a hundred, so the two numbers
 * are comparable. Splitting them let each page carry its own selector, and
 * a reader could compare a MA run against an RSI report without noticing.
 *
 * WHY THE TABS SIT UNDER THE TITLE, NOT IN THE NAV BAR: they are two
 * readings of one section, not two sections of the product. The nav bar
 * holds the sections; this strip holds the views inside one section.
 */
export function BacktestingPage() {
  const [tab, setTab] = useState<TabId>("single");
  // The strategy is page-level state so BOTH tabs measure the same rule.
  const [strategy, setStrategy] = useState("ma_crossover");

  return (
    <div className="space-y-12">
      <PageTitle
        title="Đánh giá chiến lược"
        subtitle="Chạy một quy tắc mua/bán trên lịch sử thật, rồi so với đường cơ sở mua và giữ trên cùng các phiên."
        meta="05 · Models"
      />

      {/*
        ── The tab strip ────────────────────────────────────────────
        Two readings of the same evaluation, so they read as a switch
        inside one section rather than two links in the sitemap.
      */}
      <div
        role="tablist"
        aria-label="Phạm vi đánh giá"
        className="flex items-center gap-1 border-b border-hairline"
      >
        {(
          [
            { id: "single" as TabId, label: "Một mã cổ phiếu" },
            { id: "population" as TabId, label: "Walk-forward đa mã" },
          ]
        ).map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "-mb-px min-h-11 border-b-2 px-4 text-small font-medium transition-colors",
              tab === item.id
                ? "border-primary text-ink"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/*
        ── The shared strategy picker ───────────────────────────────
        ONE strategy for the whole page. The single-symbol run and the
        population report must describe the same rule, otherwise the two
        tabs answer different questions.
      */}
      <section>
        <div className="section-head">
          <h2 className="section-title">Chiến lược</h2>
        </div>
        <div className="pt-4">
          <div role="radiogroup" aria-label="Chiến lược" className="flex flex-wrap gap-x-8 gap-y-4">
            {STRATEGIES.map((s) => {
              const active = strategy === s.id;
              return (
                <button
                  key={s.id}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setStrategy(s.id)}
                  className="group flex min-h-11 items-center gap-3 text-left"
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                      active ? "border-primary" : "border-hairline",
                    )}
                  >
                    {active ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
                  </span>
                  <span>
                    <span
                      className={cn(
                        "block text-small font-semibold",
                        active ? "text-ink" : "text-muted",
                      )}
                    >
                      {s.label}
                    </span>
                    <span className="block font-mono text-label uppercase text-muted">
                      {s.hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {tab === "single" ? (
        <>
          <Explainer
            title="Tab này dùng để làm gì?"
            intro="Backtest trả lời câu hỏi: nếu bạn áp dụng một quy tắc mua/bán theo lịch sử thật, bạn sẽ có bao nhiêu tiền? Hệ thống chơi lại từng phiên một: tính tín hiệu khi đóng cửa phiên hôm đó, rồi khớp lệnh vào giá mở cửa của phiên kế tiếp — nên không bao giờ dùng thông tin của tương lai."
            items={[
              {
                term: "MA Crossover",
                meaning: "Mua khi đường trung bình ngắn hạn cắt lên đường trung bình dài hạn; bán khi cắt xuống.",
              },
              {
                term: "RSI Strategy",
                meaning: "Mua khi RSI rơi xuống dưới ngưỡng (ví dụ 30 = thị trường bị bán quá mức); bán khi RSI vượt ngưỡng trên (70).",
              },
              {
                term: "Equity curve",
                meaning: "Đường biểu diễn tổng giá trị tài khoản sau mỗi phiên. Đi lên là đang lãi, đi xuống là đang lỗ.",
              },
              {
                term: "Total Return",
                meaning: "Tổng lãi/lỗ tính theo phần trăm so với vốn ban đầu.",
              },
              {
                term: "Max Drawdown",
                meaning: "Mức lỗ tệ nhất tính từ đỉnh cao nhất xuống đáy thấp nhất. Càng nhỏ (ít âm) càng ổn định.",
              },
              {
                term: "Sharpe Ratio",
                meaning: "Lợi nhuận trên mỗi đơn vị rủi ro. Trên 1 là tốt, dưới 0 nghĩa là lãi ít hơn rủi ro.",
              },
              {
                term: "Win Rate",
                meaning: "Tỉ lệ % lệnh thắng. Cao không đảm bảo lãi — cần xem cả Total Return.",
              },
              {
                term: "Profit Factor",
                meaning: "Tổng lãi chia cho tổng lỗ. Trên 1 là lãi, dưới 1 là lỗ.",
              },
              {
                term: "Transaction fee / Slippage",
                meaning: "Chi phí mỗi lệnh và độ trượt giá so với giá mở cửa. Cả hai đều làm lợi nhuận thực tế thấp hơn.",
              },
              {
                term: "Mua & giữ (baseline)",
                meaning: "Kịch bản đối chứng: mua đầu kỳ và giữ đến cuối, trên cùng các phiên, cùng phí và cùng độ trượt. Nếu chiến lược không vượt được nó, thì việc chọn thời điểm vào lệnh không tạo thêm giá trị nào.",
              },
            ]}
            steps={[
              "Chọn mã cổ phiếu và chiến lược muốn thử.",
              "Đặt vốn ban đầu, phí giao dịch và độ trượt giá.",
              "Bấm Chạy backtest để xem kết quả.",
              "Đổi tham số (Short MA / Long MA hoặc ngưỡng RSI) rồi chạy lại để so sánh.",
              "Sang tab 'Walk-forward đa mã' để biết kết quả này có đúng trên nhiều mã không.",
            ]}
          />
          <SingleSymbolBacktest strategy={strategy} />
        </>
      ) : (
        <MultiSymbolWalkForward strategy={strategy} />
      )}
    </div>
  );
}
