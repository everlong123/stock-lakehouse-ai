import { api, ApiEnvelope } from "@/api/client";

/**
 * The data quality gate's verdict.
 *
 * WHY A DEDICATED TYPE
 * --------------------
 * The gate reports six checks, each with its own status, and the page
 * renders them as a checklist. A `Record<string, unknown>` would make every
 * field access a cast, and the casts are where a typo becomes a silently
 * wrong number on screen.
 */
export interface QualityCheck {
  status: "passed" | "warning" | "failed" | "unavailable";
  checked: number;
  failed: number;
  warned: number;
  reason: string;
  offenders: string[];
  details: Record<string, unknown>;
}

export interface QualityGateSummary {
  verdict: "passed" | "warning" | "failed" | "unknown";
  checked_at: string | null;
  elapsed_seconds?: number;
  checks: Record<string, QualityCheck>;
  history: Array<{ checked_at: string | null; verdict: string }>;
  verdict_trend?: "improving" | "degrading" | "flat";
  note?: string;
}

/** The gate's stored snapshot. It does not run the gate. */
export async function fetchQualityGate(): Promise<QualityGateSummary> {
  const { data } = await api.get<ApiEnvelope<QualityGateSummary>>("/quality/gate");
  return data.data;
}

/**
 * Run the gate now and return the fresh snapshot.
 *
 * This is the manual counterpart of the nightly job. It costs a provider
 * round-trip per symbol in the batch, so the button shows a pending state
 * for as long as it takes.
 */
export async function runQualityGate(symbols?: string): Promise<QualityGateSummary> {
  const { data } = await api.post<ApiEnvelope<QualityGateSummary>>("/quality/gate/run", null, {
    params: symbols ? { symbols } : {},
  });
  return data.data;
}
