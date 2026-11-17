"""Forecasting endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_forecasting_service
from app.core.data_integrity import is_impossible_price
from app.schemas.common import ok
from app.schemas.forecasting import PredictRequest, TrainRequest
from app.services.forecasting_service import ForecastingService

router = APIRouter(prefix="/forecast", tags=["forecasting"])


@router.post("/train")
def train_forecast(
    payload: TrainRequest,
    db: Session | None = Depends(get_db),
    service: ForecastingService = Depends(get_forecasting_service),
) -> dict:
    result = service.train(payload.model_dump(), db=db)
    return ok(result, message="Model trained on a chronological split. Metrics are not a profit guarantee.")


@router.post("/predict")
def predict_forecast(
    payload: PredictRequest,
    service: ForecastingService = Depends(get_forecasting_service),
) -> dict:
    return ok(service.predict(payload.symbol.upper(), payload.model_name, payload.horizon))


@router.get("/compare/{symbol}")
def compare_forecast(
    symbol: str,
    db: Session | None = Depends(get_db),
    service: ForecastingService = Depends(get_forecasting_service),
) -> dict:
    return ok(service.compare(symbol.upper(), db=db))


@router.get("/next-session/{symbol}")
def next_session_forecast(
    symbol: str,
    model_name: str | None = None,
    horizon: int = 1,
) -> dict:
    """Produce the forecast for the session that opens next.

    This uses an ALREADY TRAINED model. It never trains anything: a symbol
    without a trained model returns an explicit "no model" reason rather
    than a made-up number.
    """
    from app.services.next_session_forecast import build_next_session_forecast

    return ok(build_next_session_forecast(symbol.upper(), model_name=model_name, horizon=horizon))


@router.post("/next-session/{symbol}/store")
def store_next_session_forecast(
    symbol: str,
    model_name: str | None = None,
    horizon: int = 1,
    db: Session | None = Depends(get_db),
) -> dict:
    """Produce the next-session forecast AND store it in the database.

    This is the manual counterpart of what the EOD batch does on its own.
    The stored row is tagged ``manual_api`` so it can be told apart from
    the one the overnight run wrote.
    """
    from app.services.next_session_forecast import predict_and_store

    return ok(predict_and_store(symbol.upper(), model_name=model_name, horizon=horizon, source="manual_api"))


@router.get("/published/{symbol}")
def published_forecasts(symbol: str) -> dict:
    """The forecasts the SYSTEM published, one row per model, for one session.

    WHY THIS ENDPOINT EXISTS
    ------------------------
    The nightly batch can publish a forecast for every trained model of a
    symbol, all targeting the SAME session. Reading them side by side is
    what makes "which model do we trust?" answerable on live data rather
    than only on a backtest.

    WHAT IT READS
    -------------
    The ``predictions`` table - the same rows the Dashboard reads and the
    same rows the accuracy report scores. Nothing is recomputed here, so
    the number shown on the forecasting page is byte-for-byte the number
    the overnight batch wrote, with the score it will later be judged by.

    A model that has no trained model for this symbol simply has no row.
    It is reported as absent, never replaced by another model's number.
    """
    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory
    from app.forecasting.model_registry import list_trained_models

    symbol = symbol.upper()
    if not check_database_connection():
        return ok({"symbol": symbol, "target_session": None, "forecasts": [], "reason": "The database is unavailable."})

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        target_session = repository.latest_session_for_symbol(symbol)
        if target_session is None:
            return ok(
                {
                    "symbol": symbol,
                    "target_session": None,
                    "forecasts": [],
                    "trained_models": [],
                    "reason": "No published forecast for this symbol.",
                }
            )

        rows = repository.for_symbol_and_session(symbol, target_session)

        # The trained models are reported separately so the reader can see
        # WHICH models exist but did not publish a forecast for this
        # session. That is a different statement from "the model does not
        # exist", and the two must not be confused.
        trained = []
        for record in list_trained_models(symbol):
            name = record.get("model_name")
            if not name:
                continue
            trained.append(
                {
                    "model_name": name,
                    "mae": record.get("mae"),
                    "rmse": record.get("rmse"),
                    "mape": record.get("mape"),
                    "directional_accuracy": record.get("directional_accuracy"),
                    "trained_at": record.get("created_at"),
                }
            )

        published = []
        for row in rows:
            published.append(
                {
                    "model_name": row.model_name,
                    "target_session": row.target_session.isoformat() if row.target_session else None,
                    "reference_close": row.reference_close,
                    "predicted_close": row.predicted_close,
                    "predicted_return": row.predicted_return,
                    "horizon": row.horizon,
                    "source": row.source,
                    "source_layer": row.source_layer or "gold",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "actual_close": row.actual_close,
                    "abs_error": row.abs_error,
                    "error_pct": row.error_pct,
                    "direction_correct": row.direction_correct,
                }
            )
        return ok(
            {
                "symbol": symbol,
                "target_session": target_session.isoformat(),
                "forecasts": published,
                "trained_models": trained,
            }
        )
    finally:
        session.close()


@router.get("/accuracy")
def forecast_accuracy(
    symbol: str | None = Query(default=None, description="Restrict to one symbol."),
    model_name: str | None = Query(default=None, description="Restrict to one model."),
    limit: int = Query(default=180, ge=1, le=1000, description="How many verified forecasts to return."),
) -> dict:
    """The verified forecasts: what the system predicted, and what happened.

    WHY THIS ENDPOINT EXISTS
    ------------------------
    The forecasting page shows the model's accuracy on a HISTORICAL hold-out
    split - a backtest. That answers "how good is the model on sessions
    that had already happened when the model was built".

    This endpoint answers the other question: "how good were the
    forecasts this system actually published?". Every row here is a
    forecast the system made, stored in the ``predictions`` table BEFORE
    the session happened, and later scored against the real closing price
    read from Gold.

    The distinction matters for a thesis: a backtest measures the model, a
    verification table measures the SYSTEM.

    WHAT THE RESPONSE CONTAINS
    --------------------------
    * ``series``  - the verified forecasts, oldest first, with the predicted
      close, the real close and the error of each.
    * ``summary`` - the aggregate over the same rows: how many forecasts
      were verified, the mean absolute error, the mean relative error and
      the directional accuracy.
    * ``published_summary`` - the same aggregate over the forecasts the
      system actually PUBLISHED before the session opened. This is the
      stronger evidence, so it is reported on its own rather than blended
      into the backfilled numbers.

    An empty series is an honest answer: it means nothing has been
    verified yet, not that the system scored zero.
    """
    from app.core.logging_config import get_logger
    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory

    logger = get_logger(__name__)

    if not check_database_connection():
        return ok(
            {
                "series": [],
                "summary": _empty_summary(),
                "published_summary": _empty_summary(),
                "reason": "The database is unavailable.",
            }
        )

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        rows = repository.scored_series(symbol=symbol, model_name=model_name, limit=limit)
        summary = repository.accuracy_summary(symbol=symbol, model_name=model_name)
        # The median is the number that describes a TYPICAL verified
        # forecast. The mean is dragged around by symbols whose price is a
        # fraction of a unit, so both are reported and neither is hidden.
        summary["median_error_pct"] = repository.median_error_pct(
            symbol=symbol, model_name=model_name
        )

        series = [
            {
                "symbol": row.symbol,
                "model_name": row.model_name,
                "target_session": row.target_session.isoformat(),
                "reference_close": row.reference_close,
                "predicted_close": row.predicted_close,
                "actual_close": row.actual_close,
                "abs_error": row.abs_error,
                "error_pct": row.error_pct,
                "direction_correct": row.direction_correct,
                "source": row.source,
                "scored_at": row.scored_at.isoformat() if row.scored_at else None,
            }
            for row in rows
        ]

        # The per-model breakdown lets the page show which model family is
        # actually more accurate in production, not only in the backtest.
        per_model: list[dict] = []
        model_names = sorted({row.model_name for row in rows})
        for name in model_names:
            model_summary = repository.accuracy_summary(symbol=symbol, model_name=name)
            model_summary["median_error_pct"] = repository.median_error_pct(
                symbol=symbol, model_name=name
            )
            per_model.append({"model_name": name, **model_summary})

        # The PUBLISHED forecasts are queried separately, not filtered out
        # of `rows`. `rows` is limited to the most recent `limit` entries,
        # so a published row from an older date would be pushed out of
        # that window by the backfilled ones and the published summary
        # would come back empty even though published rows exist.
        published_rows = repository.published_scored_series(
            symbol=symbol, model_name=model_name, limit=5000
        )

        return ok(
            {
                "series": series,
                "summary": summary,
                "published_summary": _summarise(published_rows),
                "per_model": per_model,
            }
        )
    finally:
        session.close()


def _empty_summary() -> dict:
    return {
        "verified": 0,
        "mae": None,
        "mean_error_pct": None,
        "median_error_pct": None,
        "wape": None,
        "directional_accuracy": None,
        "first_session": None,
        "last_session": None,
        "excluded_impossible": 0,
    }


def _summarise(rows: list) -> dict:
    """Aggregate a set of scored rows in Python.

    The repository's aggregate runs in SQL, which is the right tool for the
    whole table. This one runs over an already-filtered list, so it is
    used for the "published only" split.

    WHY THE IMPOSSIBLE ROWS ARE COUNTED, NOT DROPPED SILENTLY
    ----------------------------------------------------------
    A row whose forecast price cannot exist on an exchange - negative, or
    more than ``MAX_PREDICTION_REFERENCE_FACTOR`` away from its reference
    - would otherwise drag the mean by orders of magnitude. Such rows are
    left out of the clean figures, but they are REPORTED in
    ``excluded_impossible`` so that a reader can see that something was
    left out and why.

    WHY WAPE IS REPORTED ALONGSIDE THE MEAN
    ---------------------------------------
    The arithmetic mean of a relative error is not a scale-free number: it
    weights every symbol equally no matter what it costs. WAPE normalises
    by the total reference value, so it answers "how much money did the
    forecasts get wrong, relative to the money they were about".
    """
    if not rows:
        return _empty_summary()

    clean = [row for row in rows if not _is_impossible_row(row)]
    excluded = len(rows) - len(clean)
    if not clean:
        summary = _empty_summary()
        summary["excluded_impossible"] = excluded
        return summary

    errors = [row.abs_error for row in clean if row.abs_error is not None]
    relative = [row.error_pct for row in clean if row.error_pct is not None]
    directions = [row.direction_correct for row in clean if row.direction_correct is not None]
    sessions = sorted(row.target_session for row in clean)

    # The median of the ABSOLUTE relative error. See
    # `PredictionRepository.median_error_pct` for why the mean alone is
    # not enough. Returned as a FRACTION, the same unit as `error_pct`.
    absolute_relative = sorted(abs(value) for value in relative)
    median_pct = None
    if absolute_relative:
        middle = len(absolute_relative) // 2
        if len(absolute_relative) % 2 == 1:
            median_pct = absolute_relative[middle]
        else:
            median_pct = (absolute_relative[middle - 1] + absolute_relative[middle]) / 2.0

    # The weighted absolute percentage error: the total absolute error
    # divided by the total reference value, so that a symbol quoted at
    # 0,10 cannot weigh as much as one quoted at 100.
    total_abs_error = sum(errors)
    total_reference = sum(
        float(row.reference_close)
        for row in clean
        if row.reference_close is not None and float(row.reference_close) > 0
    )
    wape = None
    if total_reference:
        wape = 100.0 * total_abs_error / total_reference

    return {
        "verified": len(clean),
        "mae": sum(errors) / len(errors) if errors else None,
        "mean_error_pct": sum(relative) / len(relative) if relative else None,
        "median_error_pct": median_pct,
        "wape": wape,
        "directional_accuracy": (
            sum(1 for value in directions if value == 1) / len(directions)
            if directions
            else None
        ),
        "first_session": sessions[0].isoformat() if sessions else None,
        "last_session": sessions[-1].isoformat() if sessions else None,
        "excluded_impossible": excluded,
    }


def _is_impossible_row(row) -> bool:
    """True when a scored row's forecast price could not exist.

    The same rule the write path applies (``app/core/data_integrity.py``),
    expressed against an ORM row rather than a payload dict.
    """
    return is_impossible_price(
        getattr(row, "predicted_close", None),
        getattr(row, "reference_close", None),
    )


@router.get("/accuracy/{symbol}")
def symbol_forecast_accuracy(
    symbol: str,
    model_name: str | None = None,
    limit: int = Query(default=180, ge=1, le=1000),
) -> dict:
    """The verified forecasts of one symbol."""
    return forecast_accuracy(symbol=symbol.upper(), model_name=model_name, limit=limit)


@router.post("/score")
def score_pending_forecasts(
    symbol: str | None = Query(default=None, description="Restrict to one symbol."),
) -> dict:
    """Score the forecasts whose target session has already happened.

    The nightly batch does this on its own. This endpoint is the manual
    counterpart, for when someone wants to check the accuracy report
    without waiting for the cron.
    """
    from app.services.forecast_scoring import score_all, score_symbol

    if symbol:
        return ok(score_symbol(symbol.upper()))
    return ok(score_all())
