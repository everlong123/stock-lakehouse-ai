"""Publication provenance and alignment must survive retries and data gaps."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.exceptions import PredictionError
from app.database.models.prediction import Prediction
from app.database.models.prediction_revision import PredictionRevision
from app.database.repositories.prediction_repository import PredictionRepository
from app.forecasting.multistep import forecast_ahead, holdout_history
from app.services.forecast_scoring import score_forecast


@pytest.fixture
def repository():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.connection.driver_connection.create_function(
            "greatest", -1, lambda *values: max(values) if all(v is not None for v in values) else None,
        )
    Prediction.__table__.create(engine)
    PredictionRevision.__table__.create(engine)
    with Session(engine) as session:
        yield PredictionRepository(session)
    engine.dispose()


def payload(**changes):
    return {"symbol": "AAPL", "model_name": "linear_regression",
            "target_session": date(2099, 1, 5), "reference_close": 100.,
            "predicted_close": 110., "source": "manual_api", **changes}


def test_retry_does_not_rewrite_the_original_publication_time(repository):
    record = repository.upsert(payload())
    record.created_at = datetime(2026, 1, 1)
    repository.session.flush()
    repository.upsert(payload())
    assert record.created_at == datetime(2026, 1, 1)


def test_provenance_change_is_archived_even_if_the_price_is_identical(repository):
    repository.upsert(payload(model_version="first"))
    repository.upsert(payload(model_version="second"))
    revision = repository.session.scalars(select(PredictionRevision)).one()
    assert revision.payload["model_version"] == "first"


def test_scored_publication_provenance_is_immutable(repository):
    record = repository.upsert(payload(model_version="first"))
    repository.score({"symbol": record.symbol, "model_name": record.model_name,
                      "target_session": record.target_session, "actual_close": 105.})
    with pytest.raises(ValueError, match="immutable"):
        repository.upsert(payload(model_version="second"))
    assert record.model_version == "first"


def test_target_time_is_compared_in_utc(repository):
    # This wall-clock date is tomorrow, but the instant is already past.
    future_zone = timezone(timedelta(hours=14))
    past = (datetime.now(timezone.utc) - timedelta(minutes=2)).astimezone(future_zone)
    with pytest.raises(ValueError, match="passed"):
        repository.upsert(payload(target_open_at=past))


def test_forecast_insert_cannot_inject_a_score_or_backdate_publication(repository):
    record = repository.upsert(payload(actual_close=105., abs_error=0.,
                                      created_at=datetime(2000, 1, 1)))
    assert record.actual_close is None
    assert record.abs_error is None
    assert record.created_at.year >= 2026


@pytest.mark.parametrize("actual", [float("nan"), float("inf"), -1., 0.])
def test_invalid_actual_price_cannot_become_a_score(actual):
    forecast = SimpleNamespace(predicted_close=110., reference_close=100.)
    with pytest.raises(ValueError, match="actual"):
        score_forecast(forecast, actual)


def gap_frame():
    return pd.DataFrame({"symbol": "AAPL", "timestamp": pd.date_range("2026-01-05", periods=5, freq="B", tz="UTC"),
                         "close": [10., 20., 30., 40., 50.], "return": [0., 1., np.nan, 1/3, .25]})


class NextCloseModel:
    def predict(self, frame):
        return frame.close.to_numpy() + 10.


def test_history_predictions_target_the_immediately_following_session():
    points = holdout_history(NextCloseModel(), gap_frame(), "linear_regression")
    assert [(p["actual"], p["predicted"]) for p in points] == [(20., 20.), (30., 30.), (50., 50.)]


def test_history_does_not_fall_back_to_training_rows_when_window_disappears():
    points = holdout_history(NextCloseModel(), gap_frame(), "linear_regression",
                             window=(pd.Timestamp("2099-01-01", tz="UTC"), None))
    assert points == []


def test_forecast_does_not_silently_anchor_on_an_older_complete_feature_row():
    gold = gap_frame()
    gold.loc[gold.index[-1], "return"] = np.nan
    with pytest.raises(PredictionError, match="latest|Latest"):
        forecast_ahead(NextCloseModel(), gold, "linear_regression", 1)


def test_arima_update_failure_cannot_publish_a_forecast_from_old_state(monkeypatch):
    from app.forecasting import light_forecast

    def broken_update(values):
        raise RuntimeError("state update failed")
    model = SimpleNamespace(extend=broken_update, predict=lambda rows: np.ones(len(rows)) * 50.)
    monkeypatch.setattr(light_forecast, "load_model", lambda *args: model)
    monkeypatch.setattr(light_forecast, "load_registry_record", lambda *args: {"fitted_through": "2026-01-05"})
    with pytest.raises(PredictionError, match="ARIMA"):
        light_forecast.future_series("AAPL", "arima", gap_frame())


def test_sequence_history_never_joins_windows_across_a_feature_gap():
    class SequenceModel:
        sequence_length = 2
        def predict(self, frame):
            assert np.all(np.diff(frame.close) == 10.)
            return frame.close.to_numpy()[1:] + 10.

    points = holdout_history(SequenceModel(), gap_frame(), "lstm")
    assert [(p["actual"], p["predicted"]) for p in points] == [(30., 30.)]


def test_limited_sequence_history_preserves_predictions_and_bounds_work():
    class SequenceModel:
        sequence_length = 3
        sizes = []
        def predict(self, frame):
            self.sizes.append(len(frame))
            return frame.close.to_numpy()[2:] + 10.

    frame = pd.DataFrame({"symbol": "AAPL",
                          "timestamp": pd.date_range("2026-01-01", periods=200, freq="B", tz="UTC"),
                          "close": np.arange(200, dtype=float) * 10. + 10., "return": 0.})
    model = SequenceModel()
    full = holdout_history(model, frame, "lstm", limit=200)
    model.sizes.clear()
    limited = holdout_history(model, frame, "lstm", limit=5)
    assert limited == full[-5:]
    assert max(model.sizes) <= 5 + model.sequence_length


def test_chart_direction_uses_the_actual_reference_even_for_its_first_point():
    from app.forecasting.predictor import _score_history

    history = [{"actual": 110., "predicted": 90., "reference_close": 100.},
               {"actual": 120., "predicted": 130., "reference_close": 110.}]
    assert _score_history(history)["directional_accuracy"] == .5


def test_settled_close_selection_is_ordered_and_ignores_invalid_prices():
    from app.services.forecast_scoring import _closes_by_session

    frame = pd.DataFrame({"symbol": "AAPL",
                          "timestamp": pd.to_datetime(["2026-01-05 21:00Z", "2026-01-05 14:30Z", "2026-01-06 21:00Z"]),
                          "close": [105., 100., float("inf")]})
    assert _closes_by_session(frame) == {date(2026, 1, 5): 105.}


@pytest.mark.parametrize("predicted,reference", [(1e-300, 1e300), (1e300, 1e-300)])
def test_extreme_finite_price_ratios_are_rejected_without_crashing(predicted, reference):
    from app.core.data_integrity import is_impossible_price

    assert is_impossible_price(predicted, reference)


@pytest.mark.parametrize("symbol,model", [("../AAPL", "arima"), ("AAPL", "../../outside"),
                                         ("C:\\outside", "arima"), ("", "lstm")])
def test_model_paths_reject_traversal_and_invalid_keys(symbol, model):
    from app.core.exceptions import NotFoundError
    from app.forecasting.model_registry import model_directory

    with pytest.raises(NotFoundError):
        model_directory(symbol, model)


def test_registry_reads_do_not_create_directories_but_saves_do(monkeypatch, tmp_path):
    from app.core.exceptions import NotFoundError
    from app.forecasting import model_registry

    monkeypatch.setattr(model_registry, "settings", SimpleNamespace(model_dir_path=tmp_path))
    assert model_registry.list_trained_models("aapl") == []
    with pytest.raises(NotFoundError):
        model_registry.load_registry_record("aapl", "arima")
    assert list(tmp_path.iterdir()) == []
    path = model_registry.save_registry_record("aapl", "arima", {"model_name": "arima"})
    assert path.is_file()
    assert model_registry.load_registry_record("AAPL", "arima")["model_name"] == "arima"
    assert len(model_registry.list_trained_models("aapl")) == 1


@pytest.mark.parametrize("count,expected", [(2, .15), (3, .2)])
def test_repository_median_matches_the_mathematical_median(repository, count, expected):
    for i in range(count):
        publication = payload(target_session=date(2099, 1, 5 + i), predicted_close=110. + 10 * i)
        repository.upsert(publication)
        repository.score({**publication, "actual_close": 100.})
    assert repository.median_error_pct() == pytest.approx(expected)


def test_verification_series_shows_the_latest_records_in_chronological_order(repository):
    for i in range(3):
        publication = payload(target_session=date(2099, 1, 5 + i), target_open_at=datetime(2099, 1, 5 + i))
        repository.upsert(publication)
        repository.score({**publication, "actual_close": 100.})
    expected = [date(2099, 1, 6), date(2099, 1, 7)]
    assert [p.target_session for p in repository.scored_series(limit=2)] == expected
    assert [p.target_session for p in repository.published_scored_series(limit=2)] == expected
