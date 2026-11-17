"""The fast path to a next-session forecast.

WHY THIS FILE EXISTS
--------------------
`predict_symbol` builds the WHOLE chart: the model's hold-out history
("what would it have said") plus the forward projection. That history is
what the forecasting page needs, and it is not what the nightly batch
needs.

The measured cost of the difference, on this machine on 13/11/2026:

    linear_regression   full 0.46 s   light 0.02 s
    arima              full 1.83 s   light 0.00 s
    lstm               full 4.14 s   light 2.03 s

Across the ~897 symbols in the Gold layer, the full path would cost ~7
minutes per nightly run (linear regression) or ~27 minutes (ARIMA, whose
walk-forward re-fits the state-space model once per session). The light
path costs ~18 seconds. That difference is what makes a universe-wide
nightly forecast possible at all.

THE ONE RULE THIS FILE MUST NOT BREAK
--------------------------------------
The light path and the full path MUST produce the SAME number for the
same symbol, model and moment. Otherwise the Dashboard (which reads the
stored forecast) and the forecasting page (which computes the chart) could
disagree about what the system predicted - and a disagreement nobody can
see is the worst kind of bug.

So this module holds the ONLY implementation of the forward projection.
`predict_symbol` calls it for the ARIMA branch, and
`backend/tests/test_light_path_matches_full_path.py` checks the two paths
against each other on real data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.logging_config import get_logger
from app.forecasting import sessions
from app.forecasting.model_registry import load_model, load_registry_record

logger = get_logger(__name__)


def _reference_close(gold: pd.DataFrame) -> float | None:
    """The last ACTUAL close in the Gold series - the anchor of a forecast."""
    if gold is None or gold.empty or "close" not in gold.columns:
        return None
    closes = pd.to_numeric(gold["close"], errors="coerce").dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1])


def session_date(timestamp: Any) -> Any:
    """The trading day a forecast timestamp belongs to."""
    if not timestamp:
        return None
    try:
        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.date()
    except Exception:  # noqa: BLE001
        return None


def future_series(
    symbol: str,
    model_name: str,
    gold: pd.DataFrame,
    horizon: int = 1,
) -> list[dict[str, Any]]:
    """The forward projection of a model, computed the fast way.

    Returns a list of ``{"timestamp", "actual": None, "predicted"}`` dicts
    - the same shape the forecasting chart consumes. The ``actual`` slot
    is None because those sessions have not happened yet.

    This is the ONE implementation of the forward projection. The chart
    path and the nightly batch both call it, so they cannot disagree.
    """
    if gold is None or gold.empty or horizon <= 0:
        return []

    if model_name == "arima":
        return _arima_future(symbol, gold, horizon)

    from app.forecasting.multistep import forecast_ahead

    model = load_model(symbol, model_name)
    try:
        return forecast_ahead(model, gold, model_name, horizon)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Light forecast failed for %s/%s: %s", symbol, model_name, exc)
        return []


def next_point(
    symbol: str,
    model_name: str,
    gold: pd.DataFrame,
    horizon: int = 1,
) -> dict[str, Any]:
    """The first forward point of a model's forecast, computed the fast way.

    ``gold`` must be the symbol's Gold frame, sorted ascending. It is
    passed in rather than read here, because the caller usually has it
    already - reading Gold costs 0.41 s per symbol, and the nightly pass
    reads it once and uses it for both the forecast and the scoring.

    Returns the same shape as the first forward point of
    `predict_symbol`'s series: the timestamp, the predicted close, and
    the anchor the prediction was made from.
    """
    series = future_series(symbol, model_name, gold, horizon=horizon)
    if not series:
        return {"available": False, "reason": "The model produced no forward point."}

    point = series[0]
    reference = _reference_close(gold)
    predicted = float(point["predicted"])
    return {
        "available": True,
        "symbol": symbol.upper(),
        "model_name": model_name,
        "timestamp": point.get("timestamp"),
        "target_session": session_date(point.get("timestamp")),
        "reference_close": reference,
        "predicted_close": predicted,
        "predicted_return": (
            (predicted - reference) / reference if reference else None
        ),
        "horizon": horizon,
    }


def _arima_future(
    symbol: str,
    gold: pd.DataFrame,
    horizon: int,
) -> list[dict[str, Any]]:
    """The ARIMA forward projection.

    ARIMA is natively multi-step, but it was FITTED on the training split,
    which ends long before the newest session. A forecast taken straight
    from that state is anchored at the stale training price, so the model
    is extended with every session published since it was trained - the
    same correction `predict_symbol` applies.
    """
    model = load_model(symbol, "arima")
    registry = load_registry_record(symbol, "arima")

    ordered = gold.sort_values("timestamp").reset_index(drop=True)
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True)

    fitted_through = _fitted_through(registry)
    if fitted_through is not None:
        unseen = ordered[ordered["timestamp"] > fitted_through]
        if len(unseen):
            try:
                model.extend(unseen["close"].to_numpy(dtype=float))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not extend the ARIMA model for %s: %s", symbol, exc)

    try:
        predicted = model.predict(list(range(horizon)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ARIMA forecast failed for %s: %s", symbol, exc)
        return []

    last_ts = ordered["timestamp"].iloc[-1]

    # The future sessions are placed on the symbol's OWN trading calendar,
    # exactly as the feature-based path does it in `multistep.forecast_ahead`.
    #
    # The earlier code used `pd.date_range(..., freq=...)` with a fallback
    # of "B" (business days). Business days skip the weekends but NOT the
    # exchange holidays, so a forecast could land on Christmas Day. More
    # importantly, the two paths have to agree - the test
    # `test_light_path_matches_full_path.py` checks that they do, and a
    # calendar step in one path and a real calendar in the other would
    # break it.
    future_sessions = sessions.future_session_timestamps(ordered, last_ts, horizon)
    if len(future_sessions) < horizon:
        logger.warning(
            "Could not place %s future sessions after %s for the ARIMA forecast.",
            horizon,
            last_ts,
        )

    return [
        {"timestamp": str(ts), "actual": None, "predicted": float(value)}
        for ts, value in zip(future_sessions, predicted)
    ]


def _fitted_through(registry: dict[str, Any]) -> pd.Timestamp | None:
    """The last session the ARIMA model was fitted on."""
    value = registry.get("train_end")
    if not value:
        return None
    try:
        stamp = pd.to_datetime(value, utc=True)
    except Exception:  # noqa: BLE001
        return None
    return None if pd.isna(stamp) else stamp
