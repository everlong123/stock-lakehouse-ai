import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, ShieldAlert, ShieldQuestion } from "lucide-react";
import { fetchQualityGate, runQualityGate, QualityCheck } from "@/api/quality";
import { errorMessage } from "@/api/client";
import { useI18n, t } from "@/lib/i18n";
import { relativeTime } from "@/utils/format";

/**
 * One check of the quality gate, as a row.
 *
 * WHY A ROW AND NOT A TILE: the gate's whole point is that a reader can
 * see WHICH check failed. Six identical tiles in a grid make the reader
 * hunt for the broken one; six rows make it the only line with a red dot.
 */
function CheckRow({
  label,
  check,
}: {
  label: string;
  check: QualityCheck;
}) {
  const failed = check.status === "failed";
  const warning = check.status === "warning";
  const unavailable = check.status === "unavailable";

  const dotClass = failed
    ? "bg-negative"
    : warning
      ? "bg-muted"
      : unavailable
        ? "bg-muted"
        : "bg-primary";

  return (
    <li className="flex items-center gap-4 border-b border-hairline py-3 last:border-b-0">
      <span className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} aria-hidden="true" />

      <div className="min-w-0 flex-1">
        <div className="truncate text-small font-semibold text-ink">{label}</div>
        <div className="truncate font-mono text-label text-muted">
          {unavailable
            ? check.reason || "không chạy được"
            : `${check.checked} symbol · ${check.failed} lỗi · ${check.warned} cảnh báo`}
        </div>
      </div>

      {check.offenders.length > 0 ? (
        <div className="hidden max-w-48 truncate font-mono text-label text-muted sm:block">
          {check.offenders.slice(0, 6).join(", ")}
          {check.offenders.length > 6 ? ` +${check.offenders.length - 6}` : ""}
        </div>
      ) : null}

      <div
        className={`shrink-0 font-mono text-label uppercase ${
          failed ? "text-negative" : unavailable ? "text-muted" : "text-muted"
        }`}
      >
        {failed ? "lỗi" : unavailable ? "chưa chạy" : warning ? "cảnh báo" : "đạt"}
      </div>
    </li>
  );
}

/**
 * The data quality gate panel.
 *
 * WHY THIS PANEL EXISTS ON THE STATUS PAGE
 * ----------------------------------------
 * Every other row on that page says a SERVICE is up. This one says
 * whether the DATA is right. They are different questions, and a system
 * whose services are all green while it serves corrupted prices is not
 * healthy - it is just quiet.
 *
 * WHY THE VERDICT IS SHOWN IN PLAIN WORDS
 * ---------------------------------------
 * "passed" is a word from the backend. The reader needs to know what it
 * means: the layers agree, the rows obey the market's rules, the symbols
 * are current, and a slice of the universe still matches the live
 * provider. So the panel spells the verdict out and names the checks.
 *
 * WHY AN UNAVAILABLE CHECK IS SHOWN AS "CHƯA CHẠY" AND NOT AS A PASS
 * ---------------------------------------------------------------
 * This is the single most important behaviour in the panel. A check that
 * could not run proves nothing, and rendering it as green would turn an
 * outage into false reassurance.
 */
export function QualityGatePanel() {
  const { locale } = useI18n();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["quality-gate"],
    queryFn: fetchQualityGate,
    refetchInterval: 60000,
  });

  const runMutation = useMutation({
    mutationFn: () => runQualityGate(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["quality-gate"] }),
  });

  const data = query.data;
  const verdict = data?.verdict ?? "unknown";
  const checks = data?.checks ?? {};

  const CHECK_LABELS: Record<string, string> =
    locale === "vi"
      ? {
          plausibility: "Bộ lọc khả thi giá",
          layer_agreement: "Ba tầng khớp nhau",
          integrity: "Bar đúng luật thị trường",
          freshness: "Mã còn cập nhật",
          source_agreement: "Các nguồn giá khớp nhau",
          forming_snapshots: "Bar đóng băng giữa phiên",
          provider_agreement: "Khớp provider trực tiếp",
        }
      : {
          plausibility: "Plausibility screen",
          layer_agreement: "Layers agree",
          integrity: "Bars obey market rules",
          freshness: "Symbols are current",
          source_agreement: "Sources agree",
          forming_snapshots: "Mid-session snapshots",
          provider_agreement: "Matches live provider",
        };

  const verdictLabel =
    verdict === "passed"
      ? locale === "vi"
        ? "Dữ liệu đạt"
        : "Data verified"
      : verdict === "warning"
        ? locale === "vi"
          ? "Có cảnh báo"
          : "Warnings"
        : verdict === "failed"
          ? locale === "vi"
            ? "Có lỗi"
            : "Problems found"
          : locale === "vi"
            ? "Chưa kiểm tra"
            : "Not checked yet";

  const VerdictIcon =
    verdict === "passed" ? ShieldCheck : verdict === "unknown" ? ShieldQuestion : ShieldAlert;

  return (
    <section>
      <div className="section-head">
        <div className="flex items-center gap-3">
          <VerdictIcon size={16} className={verdict === "failed" ? "text-negative" : "text-muted"} />
          <h2 className="section-title">
            {locale === "vi" ? "Kiểm chứng dữ liệu" : "Data quality gate"}
          </h2>
        </div>
        <button
          type="button"
          className="rounded border border-hairline px-3 py-2 text-small text-ink transition-colors hover:bg-surface-2 disabled:opacity-50"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
        >
          {runMutation.isPending
            ? locale === "vi"
              ? "Đang kiểm tra…"
              : "Checking…"
            : locale === "vi"
              ? "Chạy lại"
              : "Run now"}
        </button>
      </div>

      {query.isError ? (
        <p className="pt-4 text-small text-negative">
          {errorMessage(query.error, t("dashboard.err_connect", locale))}
        </p>
      ) : null}

      {data?.note ? (
        <p className="pt-4 text-small text-muted">{data.note}</p>
      ) : null}

      {data && !data.note ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-4 border-y border-hairline py-6">
            <div>
              <div className="label">
                {locale === "vi" ? "Kết luận" : "Verdict"}
              </div>
              <div
                className={`mt-1 font-mono text-heading font-semibold ${
                  verdict === "failed" ? "text-negative" : "text-ink"
                }`}
              >
                {verdictLabel}
              </div>
            </div>
            <div>
              <div className="label">
                {locale === "vi" ? "Kiểm tra lúc" : "Checked at"}
              </div>
              <div className="mt-1 font-mono text-small text-ink">
                {data.checked_at ? relativeTime(data.checked_at) : "—"}
              </div>
            </div>
            <div>
              <div className="label">
                {locale === "vi" ? "Xu hướng" : "Trend"}
              </div>
              <div className="mt-1 font-mono text-small text-ink">
                {data.verdict_trend === "improving"
                  ? locale === "vi"
                    ? "đang cải thiện"
                    : "improving"
                  : data.verdict_trend === "degrading"
                    ? locale === "vi"
                      ? "đang xấu đi"
                      : "degrading"
                    : locale === "vi"
                      ? "ổn định"
                      : "flat"}
              </div>
            </div>
          </div>

          <ul className="pt-2">
            {Object.entries(checks).map(([name, check]) => (
              <CheckRow
                key={name}
                label={CHECK_LABELS[name] ?? name}
                check={check}
              />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
