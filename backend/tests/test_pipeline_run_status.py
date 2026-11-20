"""Pipeline completion must reflect the records produced by this run."""

from types import SimpleNamespace

import pandas as pd

from app.lakehouse.pipeline import LakehousePipeline, PipelineConfig


def _pipeline(bronze: int, silver: int, gold: int, errors: list[str] | None = None):
    pipeline = LakehousePipeline.__new__(LakehousePipeline)
    pipeline.config = PipelineConfig(symbols=["AAPL"])
    pipeline.storage = type("Storage", (), {"backend_name": "local"})()

    def ingest(_symbols):
        pipeline.current_run.bronze_records = bronze
        pipeline.current_run.duplicates_removed = bronze
        pipeline.current_run.errors.extend(errors or [])

    def transform_silver(_symbols):
        pipeline.current_run.silver_records = silver

    def transform_gold(_symbols):
        pipeline.current_run.gold_records = gold

    pipeline._ingest_bronze = ingest
    pipeline._transform_silver = transform_silver
    pipeline._transform_gold = transform_gold
    return pipeline


def test_pipeline_reingest_is_success_without_duplicate_penalty():
    run = _pipeline(85, 2500, 2500).run(["AAPL"])
    assert run.status == "success"
    assert run.quality_score == 100.0


def test_pipeline_reports_ingest_failure_even_with_cached_layers():
    run = _pipeline(0, 2500, 2500, ["provider unavailable"]).run(["AAPL"])
    assert run.status == "failed"
    assert run.quality_score == 0.0


def test_pipeline_reports_empty_required_layer():
    run = _pipeline(85, 2500, 0).run(["AAPL"])
    assert run.status == "failed"
    assert run.errors


def test_pipeline_reports_partial_symbol_failure(monkeypatch):
    class Provider:
        def get_historical_data(self, symbol, **_kwargs):
            return pd.DataFrame() if symbol == "MISSING" else pd.DataFrame({"close": [1]})

    monkeypatch.setattr("app.data_sources.get_data_provider", lambda _source: Provider())
    pipeline = _pipeline(0, 1, 1)
    pipeline._ingest_bronze = LakehousePipeline._ingest_bronze.__get__(pipeline)
    pipeline.bronze = SimpleNamespace(append=lambda *_args, **_kwargs: {
        "records_written": 1, "duplicate_count": 0,
    })

    run = pipeline.run(["AAPL", "MISSING"])
    assert run.bronze_records == 1
    assert run.status == "failed"
    assert "No source data for MISSING" in run.errors
