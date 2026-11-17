export interface ForecastPoint {
  timestamp: string;
  actual: number | null;
  predicted: number;
}

export interface ForecastResponse {
  symbol: string;
  model_name: string;
  horizon: number;
  metrics: Record<string, number | null>;
  /**
   * Where the displayed metrics came from:
   * - "chart_holdout" - recomputed over exactly the history shown on the
   *   chart, so the number describes the curve below it.
   * - "training_split" - the metrics recorded when the model was trained.
   */
  metrics_source?: "chart_holdout" | "training_split";
  parameters?: Record<string, unknown> | string | null;
  predictions: ForecastPoint[];
}

export interface ModelMetrics {
  model_name: string;
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  directional_accuracy?: number | null;
  parameters?: Record<string, unknown> | string | null;
}

/**
 * One forecast that has been verified against the real close.
 *
 * This is a DIFFERENT measurement from `ModelMetrics`. Those describe the
 * model's accuracy on a historical hold-out split - a backtest. These
 * describe what happened to the forecasts this system actually published:
 * the predicted close was written down before the session, and the actual
 * close was read from the lakehouse after it.
 */
export interface VerifiedForecast {
  symbol: string;
  model_name: string;
  /** The trading session the forecast was about. */
  target_session: string;
  /** The close the forecast was anchored on. */
  reference_close: number | null;
  predicted_close: number;
  /** The real close of the target session. */
  actual_close: number;
  abs_error: number | null;
  /** The relative error, as a fraction (0.01 = 1%). */
  error_pct: number | null;
  /** 1 when the direction matched, 0 when it did not. */
  direction_correct: number | null;
  source: string | null;
  scored_at: string | null;
}

/** The aggregate over the verified forecasts. */
export interface AccuracySummary {
  /** How many forecasts have been verified. */
  verified: number;
  /** Mean absolute error, in the symbol's own price unit. */
  mae: number | null;
  /** Mean relative error, as a fraction. */
  mean_error_pct: number | null;
  /**
   * The MEDIAN of the absolute relative error.
   *
   * This is the number that describes a TYPICAL verified forecast. The
   * mean is dragged around by a few rows whose forecast is off by orders
   * of magnitude - a price-level model fitted across a reverse-split
   * scale break once produced a forecast of 242,751 against a reference
   * of 0,072 - so both are reported and neither is hidden.
   */
  median_error_pct?: number | null;
  /**
   * The Weighted Absolute Percentage Error, as a percentage.
   *
   * `sum(|error|) / sum(reference) * 100`. It normalises by the total
   * reference value instead of the row count, so a symbol quoted at 0,07
   * cannot weigh as much as one quoted at 100.
   */
  wape?: number | null;
  /**
   * How many verified rows were LEFT OUT of the clean figures because
   * their forecast price could not exist on an exchange - a negative
   * price, or one more than 100x away from its own reference.
   *
   * They are counted, never silently dropped: a report that hides them
   * would hide the very failure it exists to surface.
   */
  excluded_impossible?: number;
  /** Share of forecasts whose direction matched, 0-1. */
  directional_accuracy: number | null;
  first_session: string | null;
  last_session: string | null;
}

export interface AccuracyResponse {
  series: VerifiedForecast[];
  summary: AccuracySummary;
  /**
   * The aggregate over the forecasts the system actually PUBLISHED before
   * the session opened - the strongest evidence, and reported separately
   * from the backfilled rows.
   */
  published_summary?: AccuracySummary;
  per_model?: Array<AccuracySummary & { model_name: string }>;
  reason?: string | null;
}

/**
 * One forecast the system PUBLISHED for a session, as it was written down
 * before that session opened.
 *
 * WHY THIS EXISTS ALONGSIDE `VerifiedForecast`: a `VerifiedForecast` is a
 * row that has already been scored, so it carries the outcome. A
 * `PublishedForecast` may or may not have been scored yet, but it always
 * carries the model's HISTORICAL accuracy, so a reader can weigh the
 * number before the session happens.
 */
export interface PublishedForecast {
  model_name: string;
  target_session: string | null;
  reference_close: number | null;
  predicted_close: number;
  predicted_return: number | null;
  horizon: number | null;
  source: string | null;
  source_layer: string | null;
  created_at: string | null;
  /** Present once the session has happened and the score was written. */
  actual_close?: number | null;
  abs_error?: number | null;
  error_pct?: number | null;
  direction_correct?: number | null;
}

/**
 * A model that has been trained for a symbol, with the metrics measured
 * on its historical hold-out split.
 */
export interface TrainedModelMetric {
  model_name: string;
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  directional_accuracy?: number | null;
  trained_at?: string | null;
}

export interface PublishedForecastResponse {
  symbol: string;
  target_session: string | null;
  forecasts: PublishedForecast[];
  /**
   * Every model that has been trained for this symbol, including the ones
   * that published no forecast for this session. Reported separately so
   * "the model exists but did not publish" is never confused with "the
   * model does not exist".
   */
  trained_models: TrainedModelMetric[];
  reason?: string | null;
}
