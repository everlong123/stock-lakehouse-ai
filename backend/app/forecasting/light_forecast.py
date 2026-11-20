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

from app.core.data_integrity import describe_impossible_price, is_impossible_price
from app.core.exceptions import PredictionError
from app.core.logging_config import get_logger
from app.forecasting import sessions
from app.forecasting.model_registry import load_model, load_registry_record
from app.lakehouse.exchange_timezone import session_day_of

logger = get_logger(__name__)


def _reference_close(gold: pd.DataFrame) -> float | None:
    """The last ACTUAL close in the Gold series - the anchor of a forecast."""
    if gold is None or gold.empty or "close" not in gold.columns:
        return None
    closes = pd.to_numeric(gold["close"], errors="coerce").dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1])


def session_date(timestamp: Any, symbol: str | None = None) -> Any:
    """The trading day a forecast timestamp belongs to."""
    if not timestamp:
        return None
    try:
        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return session_day_of(stamp, symbol)
    except Exception:  # noqa: BLE001
        return None


def staleness_days(gold: pd.DataFrame, target_session: Any) -> int | None:
    """How many trading sessions the newest Gold bar lags behind the target.

    WHY THIS IS MEASURED IN SESSIONS AND NOT IN CALENDAR DAYS
    ----------------------------------------------------------
    A calendar count says "three days late" on a Friday-to-Monday gap
    where the ingestion was not late at all - the exchange was closed.
    What the reader actually needs to know is how many TRADING sessions
    of history are missing, because that is how much the market moved
    without the model seeing it.

    So the count walks the symbol's OWN trading calendar from the newest
    bar to the target session, and counts the sessions in between.

    THE RESULT
    ----------
    0
        The newest bar is the session immediately before the target: the
        forecast is a plain next-session forecast on current data.

    1
        One session is missing - the ingestion fell behind by a day.

    None
        The lag cannot be established - the frame has no timestamps, or
        the target is not on the symbol's calendar. It means "not
        measured", not "zero".
    """
    if gold is None or gold.empty or "timestamp" not in gold.columns:
        return None
    if target_session is None:
        return None

    try:
        stamps = pd.to_datetime(gold["timestamp"], errors="coerce", utc=True)
        stamps = stamps.dropna()
        if stamps.empty:
            return None
        latest = stamps.max()
        target = pd.Timestamp(target_session)
        if target.tzinfo is None:
            target = target.tz_localize("UTC")
        target_day = target.date()
        symbol = str(gold["symbol"].iloc[-1]) if "symbol" in gold.columns else None
        latest_day = session_day_of(latest, symbol)
    except Exception:  # noqa: BLE001
        return None

    if target_day <= latest_day:
        # The target is not ahead of the data - the caller is asking
        # about a session that is already in the frame, so there is no
        # lag to report.
        return None

    calendar = sessions.build_calendar(gold)
    # Walk the symbol's own trading calendar from the newest bar towards
    # the target, counting the sessions that lie BETWEEN them. A
    # Friday-to-Monday gap is one session, not three days, because the
    # exchange was closed.
    #
    # The count is the number of MISSING sessions: the sessions the
    # market traded through while the ingestion had not caught up. The
    # target itself is NOT counted - it is the session being predicted,
    # not a session that was missed. So a current symbol, whose newest
    # bar is the session right before the target, has a staleness of 0.
    sessions_seen = 0
    cursor = latest_day
    for _ in range(sessions.MAX_SEARCH_DAYS):
        nxt = calendar.next_sessions(
            cursor,
            1,
            floor=cursor + pd.Timedelta(days=1),
        )
        if not nxt:
            break
        cursor = nxt[0]
        if cursor >= target_day:
            # Reached the target without passing it: no session was
            # missed between the newest bar and the target.
            break
        sessions_seen += 1
    return sessions_seen


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
        points = _arima_future(symbol, gold, horizon)
    else:
        from app.forecasting.multistep import forecast_ahead

        model = load_model(symbol, model_name)
        points = forecast_ahead(model, gold, model_name, horizon)
    reference = _reference_close(gold)
    if points and len(points) != horizon:
        raise PredictionError(f"Requested {horizon} future sessions, but only {len(points)} points were available.")
    for point in points:
        if is_impossible_price(point.get("predicted"), reference):
            raise PredictionError(describe_impossible_price(point.get("predicted"), reference))
    return points


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
    target = session_date(point.get("timestamp"), symbol)
    lag = staleness_days(gold, target)
    if lag is not None and lag > 0:
        return {
            "available": False,
            "reason": f"Input data is {lag} trading session(s) behind. Refresh the data before forecasting.",
            "data_staleness_days": lag,
        }
    return {
        "available": True,
        "symbol": symbol.upper(),
        "model_name": model_name,
        "timestamp": point.get("timestamp"),
        "target_session": target,
        "reference_close": reference,
        "predicted_close": predicted,
        "predicted_return": (
            (predicted - reference) / reference if reference else None
        ),
        "horizon": horizon,
        "target_open_at": pd.to_datetime(point["timestamp"], utc=True).to_pydatetime().replace(tzinfo=None),
        "input_data_end": pd.to_datetime(gold["timestamp"], utc=True).max().to_pydatetime().replace(tzinfo=None),
        "model_version": load_registry_record(symbol, model_name).get("model_version"),
        # How many trading sessions of history were missing when this
        # forecast was made. 0 means the data was current. See
        # `staleness_days` for why this is counted in sessions.
        "data_staleness_days": lag,
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
                raise PredictionError(f"Could not update ARIMA with the latest observations for {symbol}: {exc}") from exc

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
    value = registry.get("fitted_through") or registry.get("train_end")
    if not value:
        return None
    try:
        stamp = pd.to_datetime(value, utc=True)
    except Exception:  # noqa: BLE001
        return None
    return None if pd.isna(stamp) else stamp
