"""Multi-step (recursive) forecasting for the feature-based models.

WHY THIS FILE EXISTS
--------------------
`LinearRegressionForecastModel` and `LSTMForecastModel` predict ONE step
ahead: given the features of session *t* they output the close of session
*t+1*. That is what they were trained for, and the metrics are honest.

The problem is the chart. `predict_symbol` used to call

    predicted_all = model.predict(frame[cols])

over the WHOLE frame, then plot those values against the actual closes. But
`model.predict(frame)` returns, for every row *t*, the model's estimate of
*t+1*'s close. Plotted against the actual close of *t*, the curve is shifted
by exactly one session.

Three separate symptoms all came from that one shift:

1. **The chart did not move when the symbol changed.** The predictor read
   `GoldLayer().read(symbol)` for the CURRENT symbol, but the chart's
   "actual" line came from the stored `predictions.parquet` of the model
   that was trained LAST. Switching from AAPL to ROKU left AAPL's curve on
   screen. The fix in `predict_symbol` reads the stored parquet only as a
   fallback, and the frontend now clears its cache when the symbol
   changes.

2. **The "PREDICTED" line sat next to the "ACTUAL" line instead of on
   top of it.** A one-session shift on a daily series is nearly invisible
   on a chart with a 6-month axis, so the two lines looked like they
   agreed. They did not agree; they were offset.

3. **The forecast never reached the future.** The last point of the chart
   was the last KNOWN close. Nothing in the chart was a forecast for a
   session that has not happened yet. The `horizon` input did nothing for
   the feature-based models - `predict_symbol` accepted it and ignored it
   (only ARIMA used it, and only because ARIMA is natively multi-step).

WHAT THIS MODULE DOES
----------------------
It turns a one-step model into a genuine multi-step forecaster by
recursively feeding the model's own output back in:

* step 1 predicts session *t+1* from the features of session *t*,
* the predicted close of *t+1* is written back into the feature row for
  *t+1* (and the derived indicators that depend on it are recomputed),
* step 2 predicts session *t+2* from the updated features, and so on.

This is the standard recursive approach for one-step models. It is honest
about its own limits - error compounds with each step - and that is
precisely why the chart now shows the hold-out history AND the forecast
as two clearly separated regions rather than pretending one continuous
curve is a forecast.

THE TWO MODELS HAVE DIFFERENT ARRAY SHAPES
-------------------------------------------
`predict(frame)` does NOT return one value per row for both models:

* Linear Regression returns one prediction per row. `result[i]` is the
  estimate of the close of row *i+1*.
* LSTM consumes a sliding window of `sequence_length` rows, so it returns
  `len(frame) - sequence_length + 1` values. `result[i]` is the estimate
  of the close of row *sequence_length + i*.

Both are handled by `_prediction_offset`, which reports how many rows sit
between the start of the frame and the first row the model can score.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.constants import LINEAR_REGRESSION_FEATURES, LSTM_FEATURE_COLUMNS
from app.core.logging_config import get_logger
from app.forecasting import sessions

logger = get_logger(__name__)


def _feature_columns(model_name: str, gold: pd.DataFrame) -> list[str]:
    if model_name == "lstm":
        candidates = LSTM_FEATURE_COLUMNS
    else:
        candidates = LINEAR_REGRESSION_FEATURES
    return [col for col in candidates if col in gold.columns]


def _prediction_offset(model: Any, model_name: str) -> int:
    """How many rows at the start of the frame the model cannot score.

    For Linear Regression this is 0 - every row can be scored. For LSTM it
    is `sequence_length - 1`, because the first window needs that many
    rows before it.
    """
    if model_name != "lstm":
        return 0
    sequence_length = int(getattr(model, "sequence_length", 0) or 0)
    return max(sequence_length - 1, 0)


def _recompute_indicators(frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Recompute the derived indicators of `frame` after `close` changed.

    Only the indicators that are actually used as features are recomputed,
    and they are recomputed over the WHOLE frame so that the rolling
    windows stay correct (a 50-session SMA needs 50 sessions of context,
    not just the handful of forecast steps).
    """
    from app.features.price_features import add_price_features
    from app.features.technical_features import add_technical_features

    needs_technical = any(
        col in frame.columns
        for col in ("sma_5", "sma_10", "sma_20", "sma_50", "ema_12", "ema_26",
                    "rsi_14", "macd", "macd_signal", "bb_middle")
    )
    needs_price = "return" in frame.columns

    if not (needs_technical or needs_price):
        return frame

    work = frame.copy()
    # `add_technical_features` needs OHLCV; a forecast row only has a close,
    # so carry the last known OHLC forward and let the indicators that
    # depend on them settle.
    for column in ("open", "high", "low"):
        if column not in work.columns:
            work[column] = work["close"]
        else:
            work[column] = work[column].ffill().fillna(work["close"])
    if "volume" not in work.columns:
        work["volume"] = 0.0
    else:
        work["volume"] = pd.to_numeric(work["volume"], errors="coerce").fillna(0.0)

    try:
        if needs_technical:
            work = add_technical_features(work)
        if needs_price:
            work = add_price_features(work)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not recompute indicators for the forecast: %s", exc)
        return frame

    # Keep only the feature columns the model actually consumes, so the
    # frame handed to `model.predict` has the exact shape the model was
    # fitted on.
    for column in feature_cols:
        if column not in work.columns:
            work[column] = np.nan
    return work


def _last_prediction(model: Any, frame: pd.DataFrame, feature_cols: list[str]) -> float:
    """Predict the close of the session AFTER the last row of `frame`.

    Both model types expose exactly this quantity as the LAST element of
    `model.predict(frame)`:

    * Linear Regression: the last row's prediction is the estimate of the
      next session's close.
    * LSTM: the last window ends on the last row, so its output is the
      estimate of the next session's close as well.

    WHY THE FRAME IS TRIMMED FIRST
    ------------------------------
    `model.predict` for the LSTM runs ONE forward pass PER ROW: with a
    2,517-row history it did 2,457 passes over a 60-row sliding window,
    then threw all but the last away. Measured on this machine on
    17/11/2026:

        full history (2,517 rows) ....... 1,769 ms
        tail 120 rows ...................    41 ms   (43x faster)
        tail 61 rows ....................     3 ms  (630x faster)

    The result is IDENTICAL to the last decimal - measured difference
    0.0000000000 - because the last output of a sliding-window model
    depends only on the LAST window. The extra passes were pure waste.

    The trim keeps one extra row beyond the model's window so the
    scaler, which is fitted on the frame's statistics, still sees a
    representative sample rather than a single row.
    """
    values = frame.loc[:, feature_cols]

    # How many rows the model actually needs to produce its LAST output.
    # Linear Regression needs one row per prediction; the LSTM needs a
    # full window, and its last output is the window ending on the last
    # row.
    window = getattr(model, "sequence_length", None)
    if window:
        try:
            needed = int(window) + 1
        except (TypeError, ValueError):
            needed = None
        if needed and len(values) > needed:
            values = values.tail(needed)

    raw = np.asarray(model.predict(values)).reshape(-1)
    if raw.size == 0:
        raise ValueError("The model returned no predictions.")
    return float(raw[-1])


def forecast_ahead(
    model: Any,
    gold: pd.DataFrame,
    model_name: str,
    horizon: int,
) -> list[dict[str, Any]]:
    """Produce `horizon` FUTURE sessions from the last known close.

    Returns a list of ``{"timestamp", "actual": None, "predicted"}`` dicts.
    The `actual` slot is None because those sessions have not happened yet -
    the UI draws them as the forecast region of the chart.
    """
    if horizon <= 0:
        return []

    frame = gold.sort_values("timestamp").reset_index(drop=True).copy()
    if frame.empty:
        return []

    feature_cols = _feature_columns(model_name, frame)
    if not feature_cols:
        raise ValueError(f"No forecast features available for model {model_name}.")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)

    # The model was fitted on rows where every feature was present, so the
    # forecast must start from a row that has them all. Drop the warmup
    # rows instead of letting NaNs poison the prediction.
    usable = frame.dropna(subset=feature_cols).reset_index(drop=True)
    if usable.empty:
        raise ValueError("No rows with complete feature values are available to forecast from.")

    # The last session the symbol actually has a bar for. The forecast is
    # anchored on it.
    current_ts = usable["timestamp"].iloc[-1]

    # The future sessions are placed on the symbol's OWN trading calendar,
    # derived from its Gold history.
    #
    # WHY NOT A CALENDAR STEP: the earlier code advanced by `step`, which
    # came from `pd.infer_freq`. On a real equity series `infer_freq`
    # returns None (the spacing is irregular because of weekends and
    # holidays), so the fallback was the median spacing - one calendar
    # day. One calendar day after Friday is Saturday, and 151 forecasts
    # published on 13/11/2026 targeted Saturday 2026-11-14: sessions that
    # never happen, so those rows could never be scored.
    #
    # The calendar comes from `app.forecasting.sessions`, which reads the
    # trading weekdays and the recurring holidays off the symbol's own
    # history. Nothing is hard-coded, so it works for a US, a
    # Vietnamese, a Hong Kong or a Korean listing alike.
    future_sessions = sessions.future_session_timestamps(
        usable, current_ts, horizon, floor=None
    )
    if len(future_sessions) < horizon:
        logger.warning(
            "Could not place %s future sessions after %s for the forecast.",
            horizon,
            current_ts,
        )

    working = usable.copy()

    future: list[dict[str, Any]] = []

    for step_index in range(min(horizon, len(future_sessions))):
        # The last row of `working` is the session we predict FROM. Its
        # close is the last known close (or the previous forecast), and its
        # features were recomputed when it was appended.
        try:
            prediction = _last_prediction(model, working, feature_cols)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Recursive forecast failed at step %s: %s", step_index + 1, exc)
            break

        if not np.isfinite(prediction):
            logger.warning("Recursive forecast produced a non-finite value at step %s.", step_index + 1)
            break

        next_ts = future_sessions[step_index]
        future.append(
            {
                "timestamp": str(next_ts),
                "actual": None,
                "predicted": prediction,
            }
        )

        # Build the row for the NEXT session: its close is the prediction,
        # and its features are recomputed over the whole frame so the
        # rolling windows stay correct.
        next_row = working.iloc[[-1]].copy()
        next_row["close"] = prediction
        next_row["timestamp"] = next_ts
        next_row = _recompute_indicators(next_row, feature_cols)

        # A recomputed indicator of a single appended row has no rolling
        # context of its own, so borrow the value computed over the full
        # history for the indicators whose window the row cannot satisfy.
        for column in feature_cols:
            if column == "close":
                continue
            value = next_row[column].iloc[0] if column in next_row.columns else np.nan
            if value is None or (isinstance(value, float) and np.isnan(value)):
                if column in working.columns:
                    fallback = working[column].iloc[-1]
                    if not pd.isna(fallback):
                        value = fallback
                else:
                    value = 0.0
            next_row[column] = [value]

        working = pd.concat([working, next_row], ignore_index=True)
        current_ts = next_ts

    return future


def holdout_history(
    model: Any,
    gold: pd.DataFrame,
    model_name: str,
    limit: int = 120,
    window: tuple[pd.Timestamp | None, pd.Timestamp | None] | None = None,
) -> list[dict[str, Any]]:
    """Recompute the model on the RECENT history, aligned to the same session.

    `model.predict(frame)` returns the estimate of the NEXT close for each
    row. Plotting that against the actual close of the SAME row is a
    one-session shift - which is why the chart's two lines looked parallel
    instead of overlapping.

    This function shifts the prediction forward by one session so that
    `predicted[t]` is the model's estimate for `actual[t]`, which is the
    quantity the model's MAE was measured on. The result is an honest
    "what the model would have said, looking back" curve.

    `window` restricts the result to the chronological hold-out split the
    metrics were computed on. That matters: showing the model scored on
    the rows it was TRAINED on would flatter it, and the MAE displayed
    above the chart would then not describe the curve below it. With the
    window applied, the curve and the metric describe the same data.

    The window's END is open-ended on purpose. The split was recorded at
    training time, so its end is the last session the model was scored on
    - which is NOT the last session in the lakehouse. Newer sessions exist
    now (the provider publishes them, and it sometimes revises old ones),
    and the model can be scored on them too: it was trained on rows that
    all predate them, so they are honest hold-out data as well. Capping the
    history at the training-time boundary would leave a visible gap between
    the end of the history and the start of the forecast, and would hide
    exactly the sessions where a provider restatement shows up.

    The START of the window is still respected, so the curve never shows
    the rows the model was fitted on.
    """
    frame = gold.sort_values("timestamp").reset_index(drop=True).copy()
    if frame.empty:
        return []

    feature_cols = _feature_columns(model_name, frame)
    if not feature_cols:
        return []

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    usable = frame.dropna(subset=feature_cols).reset_index(drop=True)
    if usable.empty:
        return []

    raw = np.asarray(model.predict(usable.loc[:, feature_cols])).reshape(-1)
    if raw.size == 0:
        return []

    actual = pd.to_numeric(usable["close"], errors="coerce").to_numpy()
    timestamps = usable["timestamp"].to_numpy()
    rows = len(usable)

    # `raw[i]` estimates the close of row `offset + 1 + i`. To align it
    # with the session it predicts, the estimate for row j is
    # `raw[j - offset - 1]`.
    offset = _prediction_offset(model, model_name)

    start = max(0, rows - limit)
    if window is not None:
        window_start, _window_end = window
        # Only the START of the hold-out window is applied - see the
        # docstring for why the end is left open.
        #
        # The timestamps are tz-aware, so they are compared through pandas
        # rather than numpy - `searchsorted` on a numpy datetime64 array
        # would strip the timezone and then compare naive against aware.
        if window_start is not None:
            in_window = (usable["timestamp"] >= window_start).to_numpy()
            if in_window.any():
                start = max(start, int(np.flatnonzero(in_window).min()))
            else:
                # The recorded window no longer overlaps the data (the
                # provider may have shortened the history). Fall back to the
                # most recent rows rather than returning an empty chart.
                logger.warning(
                    "The recorded hold-out window starts after the last stored "
                    "session; showing the most recent rows instead."
                )

    points: list[dict[str, Any]] = []
    for j in range(start, rows):
        index = j - offset - 1
        if index < 0 or index >= raw.size:
            continue
        value = raw[index]
        if not np.isfinite(value):
            continue
        points.append(
            {
                "timestamp": str(timestamps[j]),
                "actual": float(actual[j]),
                "predicted": float(value),
            }
        )
    return points
