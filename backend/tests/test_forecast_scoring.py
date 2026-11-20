"""The scoring loop must never fabricate a score.

WHY THIS TEST EXISTS
--------------------
The verification ledger is the system's evidence that its forecasts mean
something. If that evidence can be produced without a real closing price,
the whole panel is worthless - and worse, it would be worthless in a way
nobody could detect from the UI, because the numbers would look normal.

So the two failure modes are pinned here:

  1. A forecast whose target session has NOT been ingested into Gold must
     stay UNSCORED. It must not receive a zero, a zero-error, or the
     model's own prediction as a stand-in for the truth.

  2. A forecast that is re-run (a retry, a second container, a manual
     re-run) must NOT wipe a score that has already been computed. The
     forecast and its outcome are written at different times, so the
     forecast upsert has to leave the outcome columns alone.

The test uses real data when it is reachable and SKIPS when it is not,
because a test that fails because the infrastructure is down teaches
nothing about the scoring logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.session import check_database_connection, get_session_factory  # noqa: E402
from app.services.forecast_scoring import score_forecast  # noqa: E402


class _FakeForecast:
    """The minimum surface `score_forecast` reads off a forecast row."""

    def __init__(self, predicted_close: float, reference_close: float | None) -> None:
        self.predicted_close = predicted_close
        self.reference_close = reference_close


def test_error_is_computed_from_two_stored_numbers() -> None:
    """The error is the difference between the forecast and the real close."""
    forecast = _FakeForecast(predicted_close=110.0, reference_close=100.0)
    result = score_forecast(forecast, actual_close=105.0)

    assert result["actual_close"] == 105.0
    assert result["abs_error"] == pytest.approx(5.0)
    # The relative error is measured against the REFERENCE close (the close
    # the forecast was anchored on), not against the actual close.
    assert result["error_pct"] == pytest.approx((110.0 - 105.0) / 100.0)


def test_direction_is_measured_from_the_reference_close() -> None:
    """A forecast that rose while the market fell is a direction miss."""
    forecast = _FakeForecast(predicted_close=110.0, reference_close=100.0)
    result = score_forecast(forecast, actual_close=95.0)
    assert result["direction_correct"] == 0

    forecast = _FakeForecast(predicted_close=110.0, reference_close=100.0)
    result = score_forecast(forecast, actual_close=108.0)
    assert result["direction_correct"] == 1


def test_direction_is_undefined_without_a_reference() -> None:
    """Without a starting price, a move has no direction to compare."""
    forecast = _FakeForecast(predicted_close=110.0, reference_close=None)
    result = score_forecast(forecast, actual_close=105.0)

    assert result["abs_error"] == pytest.approx(5.0)
    assert result["error_pct"] is None
    assert result["direction_correct"] is None


def test_a_flat_session_is_not_counted_as_a_miss() -> None:
    """Neither the forecast nor the market moved, so there is no verdict."""
    forecast = _FakeForecast(predicted_close=100.0, reference_close=100.0)
    result = score_forecast(forecast, actual_close=100.0)
    assert result["direction_correct"] is None


def test_a_forecast_with_a_missing_session_stays_unscored() -> None:
    """A target session that is not in Gold must not receive a score."""
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from app.database.repositories.prediction_repository import PredictionRepository
    from app.services.forecast_scoring import score_symbol

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        pending = repository.unscored(limit=1)
        if not pending:
            pytest.skip("There is no unscored forecast to test.")

        row = pending[0]
        before = (row.actual_close, row.scored_at)

        # The scoring pass runs against the real Gold data. If the target
        # session is not there, the row must stay exactly as it was.
        score_symbol(row.symbol, db=session)
        session.commit()

        after_row = repository.scored_series(symbol=row.symbol, model_name=row.model_name, limit=500)
        scored_for_target = [
            item for item in after_row if item.target_session == row.target_session
        ]
        if scored_for_target:
            # The session WAS in Gold, so the score is legitimate. Nothing
            # to assert about the "unscored" case here.
            assert scored_for_target[0].actual_close is not None
        else:
            refreshed = [
                item
                for item in repository.unscored(symbol=row.symbol)
                if item.target_session == row.target_session
            ]
            assert refreshed, "the row disappeared from the ledger"
            assert (refreshed[0].actual_close, refreshed[0].scored_at) == before
    finally:
        session.close()


def test_a_forecast_rerun_keeps_the_score() -> None:
    """Re-running the forecast must not erase a computed outcome."""
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from app.database.repositories.prediction_repository import PredictionRepository

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        scored = repository.scored_series(limit=1)
        if not scored:
            pytest.skip("There is no scored forecast to test.")

        row = scored[0]
        before = row.actual_close

        # Re-upsert the SAME forecast, exactly as a retried batch would.
        repository.upsert(
            {
                "symbol": row.symbol,
                "model_name": row.model_name,
                "target_session": row.target_session,
                "reference_close": row.reference_close,
                "predicted_close": row.predicted_close,
                "predicted_return": row.predicted_return,
                "horizon": row.horizon,
                "source": row.source,
                "source_layer": row.source_layer,
            }
        )
        session.commit()

        refreshed = repository.latest_for_symbol(row.symbol)
        # The score belongs to a SPECIFIC (symbol, model, session) row, so
        # it is checked on that row rather than on the symbol's latest one.
        matching = [
            item
            for item in repository.scored_series(symbol=row.symbol, model_name=row.model_name, limit=500)
            if item.target_session == row.target_session
        ]
        assert matching, "the scored row disappeared"
        assert matching[0].actual_close == before
    finally:
        session.close()


@pytest.fixture
def isolated_repository():
    """Publication tests must not edit forecasts in the live ledger."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.models.prediction import Prediction
    from app.database.models.prediction_revision import PredictionRevision
    from app.database.repositories.prediction_repository import PredictionRepository

    engine = create_engine("sqlite:///:memory:")
    Prediction.__table__.create(engine)
    PredictionRevision.__table__.create(engine)
    with Session(engine) as session:
        yield PredictionRepository(session)
    engine.dispose()


def _publication(**changes):
    from datetime import date
    return {"symbol": "AAPL", "model_name": "linear_regression",
            "target_session": date(2099, 1, 5), "reference_close": 100.,
            "predicted_close": 110., "source": "manual_api", **changes}


def test_staleness_survives_a_forecast_rerun(isolated_repository) -> None:
    """Scored publication metadata cannot be rewritten by a retried batch."""
    repository = isolated_repository
    row = repository.upsert(_publication(data_staleness_days=0))
    repository.score({"symbol": row.symbol, "model_name": row.model_name,
                      "target_session": row.target_session, "actual_close": 105.})
    with pytest.raises(ValueError, match="immutable"):
        repository.upsert(_publication(data_staleness_days=3))
    assert row.data_staleness_days == 0
    assert row.actual_close == 105.


def test_a_forecast_revision_moves_the_publication_time(isolated_repository) -> None:
    """A changed unscored forecast records a new issue time and archives the old one."""
    from datetime import datetime
    from sqlalchemy import select
    from app.database.models.prediction_revision import PredictionRevision

    repository = isolated_repository
    row = repository.upsert(_publication())
    row.created_at = datetime(2020, 1, 1)
    repository.session.flush()
    repository.upsert(_publication(predicted_close=120.))
    assert row.created_at > datetime(2020, 1, 1)
    revision = repository.session.scalars(select(PredictionRevision)).one()
    assert revision.issued_at == datetime(2020, 1, 1)
    assert revision.payload["predicted_close"] == 110.


def test_staleness_is_none_when_it_was_not_measured(isolated_repository) -> None:
    """Unknown freshness must stay distinct from measured zero lag."""
    row = isolated_repository.upsert(_publication())
    assert row.data_staleness_days is None
