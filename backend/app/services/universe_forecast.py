"""Publish next-session forecasts in bounded groups, then score due targets.

Each group's Gold frames are held directly until all its models have run;
shared cache TTL expiry cannot trigger another universe-wide download.
Training is optional and separate from routine scheduled publication.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.logging_config import get_logger
from app.forecasting import light_forecast
from app.forecasting.model_registry import model_directory
from app.lakehouse import frame_cache
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)

#: How many symbols' Gold frames are read at the same time.
#:
#: Four outer reads limit contention with each storage reader's own pool.
#: The reads are MinIO round-trips and they overlap almost
#: perfectly, so the pass is latency-bound. Eight keeps the server
#: comfortably busy - the read path in the storage backend already uses
#: 6 threads per symbol, and MinIO resets connections when it is
#: overloaded (measured 22 resets during a 30-symbol browse on
#: 2026-11-03), so the number is deliberately not higher.
_READ_WORKERS = int(os.getenv("UNIVERSE_READ_WORKERS", "4"))


@dataclass
class UniverseForecastSummary:
    """What one universe-wide pass did."""

    trained: int = 0
    training_skipped: int = 0
    training_failed: int = 0
    forecast: int = 0
    forecast_failed: int = 0
    stored: int = 0
    scored: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trained": self.trained,
            "training_skipped": self.training_skipped,
            "training_failed": self.training_failed,
            "forecast": self.forecast,
            "forecast_failed": self.forecast_failed,
            "stored": self.stored,
            "scored": self.scored,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "errors": self.errors[:20],
        }


def _has_model(symbol: str, model_name: str) -> bool:
    try:
        return (model_directory(symbol, model_name) / "registry.json").exists()
    except Exception:  # noqa: BLE001
        return False


def run_universe_forecast(
    symbols: list[str] | None = None,
    model_name: str | list[str] = "linear_regression",
    train: bool = False,
    retrain_stale: bool = True,
    store: bool = True,
) -> UniverseForecastSummary:
    """Produce and store the next-session forecast for the whole universe.

    ``train=False`` skips the training pass, which is what the nightly
    batch does when a separate training job has already run.

    WHY THIS CAN PUBLISH SEVERAL MODELS FOR THE SAME SESSION
    ---------------------------------------------------------
    The batch used to publish exactly one forecast per symbol, from
    whichever model the configuration named. That made the comparison
    between models impossible to make on live data: the ledger held
    46,329 linear-regression forecasts and 5 ARIMA ones, so "which model
    is better in production" could only be answered from a backtest.

    Passing several model names makes the batch publish one forecast per
    (symbol, model) for the SAME target session. The ``predictions``
    table's unique key is ``(symbol, model_name, target_session)``, so
    the rows coexist without a schema change, and the Dashboard and the
    forecasting page can read them side by side.

    A symbol that has no trained model for one of the requested models
    simply gets no row for that model. It is never given a substitute.
    """
    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory
    from app.forecasting.universe_training import list_gold_symbols, train_universe

    # ONE model name, or several? Normalise to a list either way, so the
    # rest of the function has exactly one code path.
    model_names: list[str] = (
        [model_name] if isinstance(model_name, str) else list(model_name)
    )
    model_names = [name.strip().lower() for name in model_names if name and name.strip()]
    if not model_names:
        model_names = ["linear_regression"]

    summary = UniverseForecastSummary()
    started = time.perf_counter()

    # ── 1. Train what needs training ────────────────────────────────────
    if train:
        logger.info("Universe forecast: training pass starting.")
        # Each model family is trained on its own. Linear regression is
        # cheap enough to cover the whole universe; ARIMA and LSTM are
        # only trained for the symbols they were already prepared for,
        # because training LSTM for a thousand symbols would take hours.
        for name in model_names:
            training_symbols = symbols
            if symbols is None and name != "linear_regression":
                training_symbols = [symbol for symbol in list_gold_symbols() if _has_model(symbol, name)]
            training = train_universe(symbols=training_symbols, model_name=name)
            summary.trained += len(training.trained)
            summary.training_skipped += len(training.skipped)
            summary.training_failed += len(training.failed)
            for symbol, reason in list(training.failed.items())[:20]:
                summary.errors.append(f"train {name} {symbol}: {reason}")

    target = list(symbols) if symbols is not None else list_gold_symbols()
    if not target:
        summary.elapsed_seconds = time.perf_counter() - started
        return summary

    # ── 2 + 3. Forecast and store ───────────────────────────────────────
    owns_session = False
    session = None
    if store:
        if not check_database_connection():
            summary.errors.append("The database is unavailable; the forecasts were not stored.")
        else:
            try:
                session = get_session_factory()()
                owns_session = True
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"The database is unavailable: {exc}")

    layer = GoldLayer()
    repository = PredictionRepository(session) if session is not None else None

    # Hold a bounded group of frames directly. Cache TTL expiry must not
    # force the batch to download the whole universe a second time.
    previous_bound = frame_cache.GLOBAL_CACHE.max_symbols
    try:
        for symbol, gold in _forecast_frames(layer, target):
            symbol = symbol.upper()
            if gold is None or gold.empty:
                summary.forecast_failed += 1
                continue

            # Every model this symbol actually has. A symbol without a
            # trained model for a family gets NO row for that family -
            # it never receives a substitute forecast.
            available = [name for name in model_names if _has_model(symbol, name)]
            if not available:
                summary.forecast_failed += 1
                continue

            for name in available:
                try:
                    point = light_forecast.next_point(symbol, name, gold, horizon=1)
                    if not point.get("available"):
                        summary.forecast_failed += 1
                        continue

                    summary.forecast += 1

                    if repository is not None and point.get("target_session"):
                        payload = {
                            "symbol": symbol,
                            "model_name": name,
                            "target_session": point["target_session"],
                            "reference_close": point.get("reference_close"),
                            "predicted_close": point["predicted_close"],
                            "predicted_return": point.get("predicted_return"),
                            "horizon": 1,
                            "source": "auto_eod_batch",
                            "source_layer": "gold",
                            "data_staleness_days": point.get("data_staleness_days"),
                            "target_open_at": point.get("target_open_at"),
                            "input_data_end": point.get("input_data_end"),
                            "model_version": point.get("model_version"),
                        }
                        try:
                            with session.begin_nested():
                                repository.upsert(payload)
                            if owns_session:
                                session.commit()
                            summary.stored += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Universe forecast: cannot store %s/%s (%s)",
                                symbol,
                                name,
                                exc,
                            )
                            summary.errors.append(f"store {symbol}/{name}: {exc}")
                except Exception as exc:  # noqa: BLE001 - one model must not stop the pass
                    logger.warning(
                        "Universe forecast failed for %s/%s: %s", symbol, name, exc
                    )
                    summary.forecast_failed += 1

        if owns_session and session is not None:
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Universe forecast pass failed: %s", exc)
        summary.errors.append(str(exc))
        if owns_session and session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

    # ── 4. Score the forecasts that can now be verified ─────────────────
    #
    # The scoring pass only reads symbols with due, unscored targets.
    try:
        from app.services.forecast_scoring import score_all

        scored = score_all()
        summary.scored = int(scored.get("scored") or 0)
        for failure in scored.get("failed") or []:
            summary.errors.append(f"score {failure.get('symbol')}: {failure.get('reason')}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Universe forecast: the scoring pass failed: %s", exc)
        summary.errors.append(f"score: {exc}")
    finally:
        # The batch's larger cache bound is restored here, so the process
        # does not keep holding the whole lakehouse after the pass.
        frame_cache.GLOBAL_CACHE.resize(previous_bound)

    summary.elapsed_seconds = time.perf_counter() - started
    logger.info(
        "Universe forecast: %d forecasts, %d stored, %d scored, %d failures in %.1fs",
        summary.forecast,
        summary.stored,
        summary.scored,
        summary.forecast_failed,
        summary.elapsed_seconds,
    )
    return summary


def _forecast_frames(layer, symbols, batch_size: int = 32):
    """Read each symbol once per bounded group, independent of cache TTL."""
    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        for offset in range(0, len(symbols), batch_size):
            group = symbols[offset:offset + batch_size]
            frames = {}
            pending = {pool.submit(layer.read, symbol): symbol for symbol in group}
            for future in as_completed(pending):
                symbol = pending[future]
                try:
                    frames[symbol] = future.result()
                except Exception as exc:
                    logger.warning("Cannot read forecast input for %s: %s", symbol, exc)
                    frames[symbol] = None
            for symbol in group:
                yield symbol, frames[symbol]
            logger.info("Universe forecast progress: %s/%s symbols processed", min(offset + len(group), len(symbols)), len(symbols))
