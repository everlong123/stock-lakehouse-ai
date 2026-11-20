import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { fetchForecastAccuracy } from "@/api/forecasting";
import { errorMessage } from "@/api/client";
import { VerifiedForecastChart } from "@/components/charts/VerifiedForecastChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { VerifiedForecast } from "@/types/forecasting";
import { formatNumber, formatPercent, formatPrice } from "@/utils/format";
import { cn } from "@/lib/utils";

interface ForecastVerificationProps {
  symbol: string;
  currency?: string | null;
}

/**
 * The verification panel: what the system forecast, and what happened.
 *
 * WHY THIS IS A DIFFERENT MEASUREMENT FROM THE MODEL EXPERIMENT
 * --------------------------------------------------------------
 * The training charts measure the MODEL on a historical hold-out split.
 * That is a backtest: the model is asked about sessions that had already
 * happened, and the split guarantees it never saw them.
 *
 * This panel measures the SYSTEM outside its training set. Every row is a
 * forecast that was WRITTEN DOWN before the session opened, and a close
 * that was read from the lakehouse after it closed. The forecast was made
 * on one day and the score on the next, with nothing in between that could
 * have changed the answer.
 *
 * That is the difference a thesis needs: "the model scores 1.1% MAPE on a
 * backtest" is a claim about a model; "the published forecasts were within
 * 0.9% of the real close, and the direction was right 54% of the time, over
 * N verified sessions" is a claim about the deployed system.
 *
 * WHY THE EMPTY STATE EXPLAINS ITSELF
 * -----------------------------------
 * Verification takes a DAY to produce the first row: a forecast is made
 * for tomorrow, and tomorrow has to come. An empty panel therefore does
 * not mean the system failed - it means nothing has been checked yet. The
 * message says so, and says what to do about it.
 *
 * WHY THE HEADLINE IS THE DIRECTIONAL ACCURACY
 * ---------------------------------------------
 * The absolute error is in the symbol's own price unit, so it cannot be
 * compared across symbols (AAPL at 340, VCB at 53,500). The relative
 * error can, and the direction match can be compared perfectly. So the
 * direction is the headline, the relative error is the supporting number,
 * and the absolute error is per-symbol.
 */
export function ForecastVerification({ symbol, currency }: ForecastVerificationProps) {
  const query = useQuery({
    queryKey: ["forecast-accuracy", symbol],
    queryFn: () => fetchForecastAccuracy(symbol, undefined, 180),
    retry: 1,
    staleTime: 60_000,
  });

  const series = useMemo<VerifiedForecast[]>(() => query.data?.series ?? [], [query.data]);
  const summary = query.data?.summary;

  if (query.isLoading) {
    return (
      <div className="rounded border border-hairline bg-surface-2 px-4 py-6 text-center text-small text-muted">
        Đang tải lịch sử kiểm chứng dự báo…
      </div>
    );
  }

  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "Không đọc được lịch sử kiểm chứng dự báo.")}
        onRetry={() => query.refetch()}
      />
    );
  }

  if (!series.length) {
    return (
      <EmptyState
        message="Chưa có dự báo nào được kiểm chứng cho mã này."
        hint={
          query.data?.reason
            ? query.data.reason
            : "Kiểm chứng cần ít nhất một phiên: dự báo được ghi vào tối hôm trước, và giá thật của phiên đó chỉ xuất hiện ở phiên kế tiếp. Batch cuối ngày sẽ tự chấm điểm."
        }
      />
    );
  }

  const directionAccuracy = summary?.directional_accuracy ?? null;

  // The two kinds of rows, counted separately.
  //
  // A PUBLISHED row was written down before the session opened, so it is
  // a commitment the system had to live with. A BACKFILLED row is the
  // model's own prediction for a session in its hold-out split, replayed
  // afterwards - a real measurement, but not a commitment. Mixing them
  // silently would overstate what the running system has actually done.
  const publishedCount = series.filter((row) => row.source !== "backfill_walk_forward").length;
  const backfilledCount = series.length - publishedCount;

  return (
    <div className="space-y-6">
      {/*
        The four numbers, in the same hairline-divided row the rest of the
        app uses. "Verified" comes FIRST because it is the one that
        qualifies the others: a 0.5% mean error over three forecasts is a
        very different claim from a 0.5% mean error over three hundred.
      */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-6 border-y border-hairline py-6 xl:grid-cols-4">
        <MetricCard
          label="Đã kiểm chứng"
          value={formatNumber(summary?.verified ?? series.length)}
          hint="Số dự báo đã được so với giá thật"
        />
        <MetricCard
          label="Đúng hướng"
          value={formatPercent(directionAccuracy)}
          hint="Tỷ lệ trên toàn bộ dự báo đã có giá thực tế"
        />
        <MetricCard
          label="Sai số trung bình"
          value={formatPercent(summary?.median_error_pct != null ? summary.median_error_pct : null)}
          hint="Trung vị sai số tương đối của một dự báo điển hình"
        />
        <MetricCard
          label="Sai số tuyệt đối"
          value={formatPrice(summary?.mae, currency)}
          hint="MAE trong đơn vị giá của mã"
        />
      </div>

      {/*
        The scale-free error, and the count of the rows that had to be left
        out.

        WHY WAPE IS SHOWN NEXT TO THE MEDIAN
        ------------------------------------
        The median says how a TYPICAL forecast was off. WAPE says how much
        the forecasts got wrong relative to the money they were about:
        `sum(|error|) / sum(reference)`. The two answer different
        questions, and a reader who only sees one of them can draw the
        wrong conclusion - the median alone does not say whether the
        misses were big or small in absolute terms.

        WHY THE EXCLUDED COUNT IS SHOWN
        --------------------------------
        Rows whose forecast price could not exist on an exchange - a
        negative price, or one more than 100x away from its own
        reference - are left out of the clean figures. They are counted
        here, because a number that quietly disappears is a number the
        reader cannot account for.
      */}
      {(summary?.wape != null || (summary?.excluded_impossible ?? 0) > 0) && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-b border-hairline pb-6 xl:grid-cols-2">
          <MetricCard
            label="Sai số có trọng số"
            value={summary?.wape != null ? `${summary.wape.toFixed(2)}%` : "—"}
            hint="Tổng sai số tuyệt đối chia cho tổng giá tham chiếu"
          />
          <MetricCard
            label="Dòng bị loại"
            value={formatNumber(summary?.excluded_impossible ?? 0)}
            hint="Dự báo có giá không tồn tại (âm, hoặc lệch quá 100 lần giá tham chiếu)"
          />
        </div>
      )}

      {/*
        The provenance line. A reader has to know WHICH rows the numbers
        above come from, because a claim about a published forecast and a
        claim about a backfilled one carry different weight.
      */}
      <p className="font-mono text-label uppercase text-muted">
        Trong {series.length} dòng hiển thị: {publishedCount} bản ghi có nguồn công bố
        {" · "}
        {backfilledCount} dự báo tái dựng từ tập hold-out
        {summary?.first_session ? ` · ${summary.first_session} → ${summary.last_session}` : ""}
      </p>
      {(query.data?.publication_timing?.timing_unknown ?? 0) > 0 ? (
        <p className="text-small text-muted">
          {query.data?.publication_timing?.timing_unknown} dự báo cũ thiếu mốc phiên đích để xác nhận giờ phát hành;
          các dòng này không được tính là bằng chứng dự báo phát hành trước phiên.
        </p>
      ) : null}

      <VerifiedForecastChart data={series} currency={currency} />

      {/*
        The last rows of the ledger. A reader who wants to check one
        specific session can find it here rather than having to trust the
        chart. Only the most recent rows are shown - the full series is
        available from the API.
      */}
      <div className="overflow-x-auto rounded border border-hairline bg-surface shadow-sm">
        <table className="table">
          <thead>
            <tr>
              {["Phiên", "Giá dự báo", "Giá thật", "Sai số", "Sai số %", "Hướng"].map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...series].reverse().slice(0, 12).map((row) => (
              <tr key={`${row.target_session}-${row.model_name}`}>
                <td className="font-mono tabular-nums">{row.target_session}</td>
                <td className="font-mono tabular-nums">{formatPrice(row.predicted_close, currency)}</td>
                <td className="font-mono tabular-nums">{formatPrice(row.actual_close, currency)}</td>
                <td className="font-mono tabular-nums">
                  {row.abs_error != null ? formatPrice(row.abs_error, currency) : "—"}
                </td>
                <td className="font-mono tabular-nums">
                  {formatPercent(row.error_pct != null ? row.error_pct : null)}
                </td>
                <td>
                  {row.direction_correct === null ? (
                    <span className="text-muted">—</span>
                  ) : (
                    <span
                      className={cn(
                        "font-mono text-small font-medium",
                        // The direction verdict borrows the direction pair
                        // (blue = right, red = wrong), NOT the app accent —
                        // so a column of verdicts scans at a glance without
                        // competing with the brand colour elsewhere.
                        row.direction_correct === 1 ? "text-up" : "text-negative",
                      )}
                    >
                      {row.direction_correct === 1 ? "Đúng" : "Sai"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-small text-muted">
        Mỗi dòng là một dự báo đã được so với giá đóng cửa thật đọc từ tầng Gold
        {summary?.first_session ? ` (${summary.first_session} → ${summary.last_session})` : ""}.
        Dòng có nguồn <code className="font-mono">auto_eod_batch</code> là dự báo hệ thống đã
        công bố <strong>trước</strong> khi phiên mở cửa; dòng có nguồn{" "}
        <code className="font-mono">backfill_walk_forward</code> là mô hình được tái chạy trên
        tập hold-out để lấy số liệu ngay. Đây là số đo ngoài tập huấn luyện, không phải backtest
        trên cùng dữ liệu đã dùng để train.
      </p>

      <p className="text-small text-muted">
        Muốn xem cách <strong>huấn luyện và so sánh ba mô hình</strong> trên tập hold-out
        (MAE / RMSE / MAPE của từng model) thì mở tab{" "}
        <span className="font-medium text-ink">Huấn luyện &amp; so sánh model</span> — đó là
        phòng thí nghiệm; bảng ở đây là sổ kiểm chứng của hệ thống đang chạy.
      </p>
    </div>
  );
}
