"""Business invariants found by the whole-universe live audit."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.exceptions import PredictionError
from app.database.models.prediction import Prediction
from app.database.models.prediction_revision import PredictionRevision
from app.database.repositories.prediction_repository import PredictionRepository
from app.features.feature_engineering import build_gold_features
from app.features.macro_features import add_market_regime_features
from app.forecasting import light_forecast, sessions, trainer
from app.forecasting.dataset import SequenceDataset
from app.forecasting.linear_regression import LinearRegressionForecastModel
from app.forecasting.multistep import forecast_ahead
from tests.conftest import make_ohlcv


@pytest.mark.parametrize("predicted", [-39.35, -277_289_577., 279_013.54, float("inf")])
def test_read_forecast_rejects_prices_that_cannot_be_stored(monkeypatch, predicted):
    gold = make_ohlcv(80)
    monkeypatch.setattr(light_forecast, "load_model", lambda *args: object())
    monkeypatch.setattr("app.forecasting.multistep.forecast_ahead", lambda *args: [{"predicted": predicted}])
    with pytest.raises(PredictionError):
        light_forecast.future_series("AAPL", "linear_regression", gold)


def test_next_session_forecast_does_not_publish_stale_inputs(monkeypatch):
    gold = make_ohlcv(180)
    target = pd.Timestamp(gold.timestamp.iloc[-1]) + pd.Timedelta(days=10)
    monkeypatch.setattr(light_forecast, "future_series", lambda *args, **kw: [{"predicted": 105., "timestamp": str(target)}])
    result = light_forecast.next_point("AAPL", "linear_regression", gold)
    assert result["available"] is False
    assert result["data_staleness_days"] > 0


def test_recursive_features_use_the_full_history(monkeypatch):
    gold = build_gold_features(make_ohlcv(220))
    monkeypatch.setattr(sessions, "_today", lambda: gold.timestamp.iloc[-1].date())
    inputs = []

    class Model:
        def predict(self, frame):
            inputs.append(frame.copy())
            return frame.close.to_numpy() * 1.1

    points = forecast_ahead(Model(), gold, "linear_regression", 2)
    expected = np.mean([*gold.close.iloc[-19:], points[0]["predicted"]])
    assert inputs[1].sma_20.iloc[-1] == pytest.approx(expected)
    assert inputs[1].close_lag_1.iloc[-1] == pytest.approx(gold.close.iloc[-1])


def test_real_tabular_model_returns_every_requested_recursive_step(monkeypatch):
    from app.core.constants import LINEAR_REGRESSION_FEATURES

    gold = build_gold_features(make_ohlcv(240))
    clean = gold.dropna(subset=LINEAR_REGRESSION_FEATURES + ["target_close_next"])
    model = LinearRegressionForecastModel().fit(clean[LINEAR_REGRESSION_FEATURES], clean.target_close_next)
    monkeypatch.setattr(sessions, "_today", lambda: gold.timestamp.iloc[-1].date())
    points = forecast_ahead(model, gold, "linear_regression", 5)
    assert len(points) == 5
    assert all(np.isfinite(point["predicted"]) for point in points)


def test_supported_sixty_session_horizon_is_not_truncated(monkeypatch):
    gold = make_ohlcv(240)
    monkeypatch.setattr(sessions, "_today", lambda: gold.timestamp.iloc[-1].date())
    targets = sessions.future_session_timestamps(gold, gold.timestamp.iloc[-1], 60)
    assert len(targets) == 60
    assert targets[-1] > targets[0] + pd.Timedelta(days=45)


def test_future_prices_cannot_change_past_regimes():
    gold = make_ohlcv(220)
    changed = gold.copy()
    changed.loc[100:, "close"] *= np.exp(np.linspace(0, 5, len(changed) - 100))
    original = add_market_regime_features(gold)
    after = add_market_regime_features(changed)
    pd.testing.assert_series_equal(original.regime_numeric.iloc[:100], after.regime_numeric.iloc[:100])


def test_training_windows_include_the_last_valid_sequence():
    data = SequenceDataset(np.ones((5, 2)), np.arange(5), 3)
    assert len(data) == 3
    _, target = data[2]
    assert target.item() == 4


def test_full_fit_evaluates_before_refit_and_cannot_see_beyond_cutoff(monkeypatch, tmp_path):
    frame = make_ohlcv(220)
    frame["target_close_next"] = frame.close.shift(-1)
    boundary = frame.timestamp.iloc[160]
    traces = []

    class ObservedModel(LinearRegressionForecastModel):
        def fit(self, X, y):
            self.fit_indexes = set(X.index)
            traces.append(("fit", len(X), float(y.iloc[-1])))
            return super().fit(X, y)

        def evaluate(self, X, y):
            assert not (set(X.index) & self.fit_indexes)
            traces.append(("evaluate", len(X), None))
            return super().evaluate(X, y)

    monkeypatch.setattr(trainer, "GoldLayer", lambda: SimpleNamespace(read=lambda symbol: frame))
    monkeypatch.setattr(trainer, "LinearRegressionForecastModel", ObservedModel)
    monkeypatch.setattr(trainer, "model_directory", lambda *args: tmp_path)
    monkeypatch.setattr(trainer, "save_registry_record", MagicMock())
    record = trainer.train_model("AAPL", "linear_regression", end_date=boundary, full_fit=True)
    assert [x[0] for x in traces] == ["fit", "evaluate", "fit"]
    assert traces[-1][2] == pytest.approx(frame.close.iloc[160])
    assert record["test_target_end"] <= boundary
    assert (tmp_path / "evaluation" / "model.joblib").exists()


@pytest.fixture
def repository():
    engine = create_engine("sqlite:///:memory:")
    Prediction.__table__.create(engine)
    PredictionRevision.__table__.create(engine)
    with Session(engine) as session:
        yield PredictionRepository(session)
    engine.dispose()


def forecast_payload(**changes):
    return {"symbol": "AAPL", "model_name": "linear_regression", "target_session": date(2026, 11, 20),
            "reference_close": 100., "predicted_close": 110., "source": "manual_api", **changes}


def test_scored_forecast_cannot_be_replaced_with_a_different_price(repository):
    record = repository.upsert(forecast_payload())
    repository.score({"symbol": "AAPL", "model_name": "linear_regression", "target_session": record.target_session,
                      "actual_close": 105., "abs_error": 999.})
    assert record.abs_error == 5.
    with pytest.raises(ValueError, match="immutable"):
        repository.upsert(forecast_payload(predicted_close=120.))
    assert record.predicted_close == 110.
    assert record.abs_error == 5.


def test_unscored_revision_keeps_the_previous_publication(repository):
    record = repository.upsert(forecast_payload())
    repository.upsert(forecast_payload(predicted_close=120.))
    archived = repository.session.scalars(select(PredictionRevision)).one()
    assert archived.payload["predicted_close"] == 110.
    assert record.predicted_close == 120.


def test_backfill_cannot_overwrite_a_published_forecast(repository):
    record = repository.upsert(forecast_payload())
    repository.upsert(forecast_payload(predicted_close=120., source="backfill_walk_forward"))
    assert record.predicted_close == 110.
    assert record.source == "manual_api"


def test_a_forecast_cannot_target_a_session_that_already_opened(monkeypatch):
    frame = make_ohlcv(220)
    anchor = pd.Timestamp("2026-11-17 14:30:00Z")
    monkeypatch.setattr(sessions, "_now", lambda: datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc))
    targets = sessions.future_session_timestamps(frame, anchor, 1)
    assert targets[0].date() == date(2026, 11, 19)


@pytest.mark.parametrize("symbol,expected", [("BHP.AX", "ASX"), ("ENI.MI", "Milan"), ("ABEV3.SA", "B3")])
def test_sample_strata_use_the_correct_exchange(symbol, expected):
    from scripts.run_multi_symbol_walkforward import classify_exchange
    assert classify_exchange(symbol) == expected


def test_refresh_passes_cannot_overlap(monkeypatch):
    from app.services.auto_refresh import AutoRefreshService

    service = AutoRefreshService()
    monkeypatch.setattr(service, "_run_once", lambda symbols: {"ok": service.running})
    assert service.run_once(["AAPL"]) == {"ok": True}
    assert service.running is False
    service._run_lock.acquire()
    try:
        assert service.run_once(["AAPL"])["reason"] == "refresh_already_running"
    finally:
        service._run_lock.release()


def test_refresh_recovers_gold_watermark_without_new_provider_rows(monkeypatch):
    from app.services import auto_refresh

    bronze = SimpleNamespace(latest_timestamp=lambda symbol: pd.Timestamp("2026-11-18 14:30Z"))
    gold = SimpleNamespace(latest_timestamp=lambda symbol: pd.Timestamp("2026-11-17 14:30Z"))
    monkeypatch.setattr(auto_refresh, "BronzeLayer", lambda: bronze)
    monkeypatch.setattr(auto_refresh, "SilverLayer", lambda: object())
    monkeypatch.setattr("app.lakehouse.gold.GoldLayer", lambda: gold)
    monkeypatch.setattr(auto_refresh, "get_data_provider", lambda: object())
    monkeypatch.setattr(auto_refresh, "wait_while_user_active", lambda **kw: None)
    monkeypatch.setattr(auto_refresh, "_silver_diverged_from_bronze", lambda *args: False)
    monkeypatch.setattr(auto_refresh, "_memory_headroom_ok", lambda: True)
    monkeypatch.setattr(auto_refresh, "invalidate_symbol_cache", lambda symbol: None)
    jobs = []
    monkeypatch.setattr(auto_refresh, "run_in_process", lambda job, *args, **kw: jobs.append(job.__name__))
    monkeypatch.setattr(auto_refresh.settings, "auto_predict_enabled", True)
    monkeypatch.setattr("app.services.next_session_forecast.predict_and_store", lambda *args, **kw: {"available": True, "stored": True})
    service = auto_refresh.AutoRefreshService()
    monkeypatch.setattr(service, "_refresh_symbol", lambda *args: {"symbol": "AAPL", "new_rows": 0, "updated_rows": 0})
    result = service.run_once(["AAPL"])
    assert result["silver_rebuilt"] == result["gold_rebuilt"] == 1
    assert result["next_session_forecasts"] == 1
    assert len(jobs) == 2


def test_a_flat_prediction_of_a_moving_price_counts_as_a_direction_miss():
    from app.services.forecast_scoring import score_forecast

    forecast = SimpleNamespace(predicted_close=100., reference_close=100.)
    assert score_forecast(forecast, 105.)["direction_correct"] == 0


def test_unverified_publication_timing_is_not_claimed_as_forward_evidence(repository):
    record = repository.upsert(forecast_payload())
    repository.score({"symbol": "AAPL", "model_name": "linear_regression", "target_session": record.target_session, "actual_close": 105.})
    assert repository.published_scored_series() == []
    assert repository.publication_timing_counts()["timing_unknown"] == 1


def test_common_comparison_uses_the_same_target_dates_and_a_naive_baseline(monkeypatch, tmp_path):
    from app.services import forecasting_service

    gold = make_ohlcv(180)
    dates = gold.timestamp.iloc[-5:].tolist()
    actual = gold.close.iloc[-5:].tolist()
    records = [{"model_name": name, "metrics_source": "independent_chronological_holdout"} for name in ("linear_regression", "arima")]
    for index, record in enumerate(records):
        folder = tmp_path / record["model_name"]
        folder.mkdir()
        pd.DataFrame({"timestamp": dates[index:], "actual": actual[index:], "predicted": actual[index:]}).to_parquet(folder / "predictions.parquet")
    monkeypatch.setattr(forecasting_service, "model_directory", lambda symbol, name: tmp_path / name)
    monkeypatch.setattr("app.lakehouse.gold.GoldLayer", lambda: SimpleNamespace(read=lambda symbol: gold))
    compared, baseline, count = forecasting_service._common_session_metrics("AAPL", records)
    assert count == 4
    assert all(row["mae"] == 0 for row in compared)
    assert baseline["mae"] > 0


def test_pipeline_history_reads_an_actual_persisted_result(monkeypatch, tmp_path):
    from app.api.v1.endpoints import pipeline
    from app.lakehouse.local_storage import LocalStorageBackend
    from app.lakehouse.pipeline import PipelineRun

    storage = LocalStorageBackend(root=tmp_path)
    record = PipelineRun(run_id="audit-run", status="success", bronze_records=10)
    storage.write_json("quality", "_pipeline_runs/audit-run.json", record.to_dict())
    monkeypatch.setattr(pipeline, "get_storage_backend", lambda: storage)
    result = pipeline.get_pipeline_run("audit-run")
    assert result.status == "success"
    assert result.bronze_records == 10


def test_symbol_enumeration_only_returns_stored_unique_tickers(monkeypatch, tmp_path):
    from app.api.v1.endpoints import stocks
    from app.lakehouse.local_storage import LocalStorageBackend

    storage = LocalStorageBackend(root=tmp_path)
    storage.write_parquet("bronze", "symbol=AAPL/year=2026/month=11/part.parquet", make_ohlcv(2))
    monkeypatch.setattr(stocks, "get_storage_backend", lambda: storage)
    monkeypatch.setattr(stocks, "GLOBAL_SYMBOLS", ["AAPL", "AAPL", "MSFT"])
    assert stocks._available_symbols() == ["AAPL"]


def test_pipeline_counts_rows_separately_from_partition_objects():
    from app.lakehouse.pipeline import LakehousePipeline

    layer = SimpleNamespace(record_count=lambda symbol: 2, read=lambda symbol: make_ohlcv(10))
    pipeline = LakehousePipeline.__new__(LakehousePipeline)
    pipeline.storage = SimpleNamespace(backend_name="local")
    pipeline.bronze = pipeline.silver = pipeline.gold = layer
    info = pipeline.get_layer_info("AAPL")
    assert info["gold"]["records"] == 10
    assert info["gold"]["objects"] == 2


def test_australian_forecast_uses_the_exchange_session_date(monkeypatch):
    stamps = pd.date_range(end="2026-11-17", periods=220, freq="B", tz="UTC") + pd.Timedelta(hours=23)
    gold = pd.DataFrame({"symbol": "BHP.AX", "timestamp": stamps, "close": np.linspace(30, 40, len(stamps))})
    monkeypatch.setattr(sessions, "_now", lambda: datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc))
    target = sessions.future_session_timestamps(gold, stamps[-1], 1)[0]
    assert target == pd.Timestamp("2026-11-18 23:00:00Z")
    assert light_forecast.session_date(target, "BHP.AX") == date(2026, 11, 19)
    assert light_forecast.staleness_days(gold, date(2026, 11, 19)) == 0


def test_australian_scoring_uses_the_same_local_session_as_forecasting():
    from app.services.forecast_scoring import _closes_by_session

    gold = pd.DataFrame({"symbol": ["BHP.AX"], "timestamp": [pd.Timestamp("2026-11-17 23:00:00Z")], "close": [40.]})
    assert _closes_by_session(gold) == {date(2026, 11, 18): 40.}


def test_forecast_batch_keeps_inputs_when_the_shared_cache_is_cleared():
    from collections import Counter
    from app.services.universe_forecast import _forecast_frames
    from app.lakehouse.frame_cache import GLOBAL_CACHE

    reads = Counter()
    def read(symbol):
        reads[symbol] += 1
        return pd.DataFrame({"symbol": [symbol], "close": [reads[symbol]]})

    iterator = _forecast_frames(SimpleNamespace(read=read), ["AAPL", "MSFT", "FPT"], batch_size=2)
    first = next(iterator)
    GLOBAL_CACHE.clear()
    rest = list(iterator)
    assert [symbol for symbol, _ in [first, *rest]] == ["AAPL", "MSFT", "FPT"]
    assert reads == {"AAPL": 1, "MSFT": 1, "FPT": 1}


def test_scoring_does_not_download_prices_for_future_targets(monkeypatch, repository):
    from app.services import forecast_scoring

    repository.upsert(forecast_payload(target_session=date(2099, 1, 1)))
    def unexpected_read(*args):
        raise AssertionError("No price read should be needed for a future target")
    monkeypatch.setattr(forecast_scoring, "GoldLayer", lambda: SimpleNamespace(read=unexpected_read))
    result = forecast_scoring.score_all(db=repository.session)
    assert result["scored"] == 0


def test_optional_batch_training_does_not_expand_heavy_families_to_every_stock(monkeypatch):
    from app.services import universe_forecast, forecast_scoring

    calls = []
    def train(symbols, model_name):
        calls.append((model_name, symbols))
        return SimpleNamespace(trained=[], skipped={}, failed={})
    monkeypatch.setattr("app.forecasting.universe_training.train_universe", train)
    monkeypatch.setattr("app.forecasting.universe_training.list_gold_symbols", lambda: ["AAPL", "FPT"])
    monkeypatch.setattr(universe_forecast, "_has_model", lambda symbol, family: symbol == "AAPL")
    monkeypatch.setattr(universe_forecast, "GoldLayer", lambda: object())
    monkeypatch.setattr(universe_forecast, "_forecast_frames", lambda *args: iter([]))
    monkeypatch.setattr(forecast_scoring, "score_all", lambda: {"scored": 0})
    universe_forecast.run_universe_forecast(model_name=["linear_regression", "arima", "lstm"], train=True, store=False)
    assert calls == [("linear_regression", None), ("arima", ["AAPL"]), ("lstm", ["AAPL"])]
