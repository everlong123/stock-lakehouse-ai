"""The universe-wide nightly forecast pass.

WHY THIS FILE EXISTS
--------------------
The EOD batch could only forecast the 18 symbols that already had a
trained model on disk. Everything else was invisible to the forecasting
system - which meant the "next-session forecast" was a demo for a
curated list rather than a feature of the platform.

This module produces a forecast for EVERY symbol that has usable Gold
history and a trained model. It is the piece that turns the forecasting
system from a per-ticker tool into a platform capability.

WHAT IT DOES, IN ORDER
----------------------
  1. **Train** the symbols that need it (see `universe_training.py`).
     A symbol whose model has not reached its newest Gold session is
     retrained, because a model anchored on a stale price produces a
     forecast that is wrong by the whole gap.
  2. **Forecast** the next session for every symbol that has a model.
  3. **Store** each forecast in the `predictions` table.
  4. **Score** the forecasts whose target session has already happened,
     against the real close read from Gold.

STEP 4 IS THE POINT OF THE WHOLE LOOP
-------------------------------------
Steps 1-3 publish forecasts. Step 4 is what turns them into evidence.
Without it, the system's accuracy can only ever be measured on a
backtest - on sessions that had already happened when the model was
built. With it, the table accumulates a record of what the system
actually predicted and how it actually turned out.

THE COST, MEASURED
------------------
On this machine on 13/11/2026, with ~897 symbols in Gold:

    Gold read ................. 0.41 s per symbol
    train linear_regression ... 0.45 s per symbol
    light forecast ............ 0.02 s per symbol

So a full pass over the universe costs roughly:
    training  (stale symbols only) ... ~7 minutes for the whole universe
    forecasting ..................... ~18 seconds
    scoring  (one Gold read per symbol, shared with the forecast)

The forecast and the score SHARE the Gold read, which is why the scoring
step is nearly free: the data is already in memory.

WHY THE FORECAST AND THE SCORE SHARE ONE GOLD READ
---------------------------------------------------
The forecast needs the newest session (to predict the next one) and the
score needs the sessions that have already happened (to verify the older
forecasts). Both come from the same frame. Reading Gold twice would
double the dominant cost of the whole pass.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logging_config import get_logger
from app.forecasting import light_forecast
from app.forecasting.model_registry import model_directory
from app.lakehouse import frame_cache
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)

#: How many symbols' Gold frames are read at the same time.
#:
#: WHY 8: the reads are MinIO round-trips and they overlap almost
#: perfectly, so the pass is latency-bound. Eight keeps the server
#: comfortably busy - the read path in the storage backend already uses
#: 6 threads per symbol, and MinIO resets connections when it is
#: overloaded (measured 22 resets during a 30-symbol browse on
#: 2026-11-03), so the number is deliberately not higher.
_READ_WORKERS = int(os.getenv("UNIVERSE_READ_WORKERS", "8"))


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
    train: bool = True,
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
            training = train_universe(symbols=symbols, model_name=name)
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

    # The pass wants EVERY symbol in memory at once, which is more than
    # the cache's default bound (256 symbols, sized for a browsing
    # session). The bound is raised for the duration of the pass and
    # restored afterwards, so the batch does not permanently hold the
    # whole lakehouse.
    previous_bound = frame_cache.GLOBAL_CACHE.max_symbols
    frame_cache.GLOBAL_CACHE.resize(max(previous_bound, len(target) + 16))

    try:
        # ── Warm the Gold cache CONCURRENTLY ──────────────────────────────
        #
        # WHY: reading a symbol from MinIO costs ~0.5 s (measured 13/11/2026
        # on this machine) because the symbol's ~121 monthly parquet
        # partitions are downloaded one round-trip at a time. At 973
        # symbols, reading them serially was ~8 minutes of the pass - and
        # the forecast itself is only 0.06 s per symbol. The reads are
        # independent and side-effect free, so they overlap almost
        # perfectly: the pass is latency-bound, not CPU-bound.
        #
        # Warming the cache FIRST also means the scoring pass at the end
        # of this function reads the same frames from memory instead of
        # downloading every symbol's history a second time.
        read_started = time.perf_counter()
        warmed = frame_cache.warm_cache(
            "gold",
            target,
            reader=layer.read,
            workers=_READ_WORKERS,
        )
        read_elapsed = time.perf_counter() - read_started
        logger.info(
            "Universe forecast: warmed %s/%s Gold frames in %.1fs (%s failed)",
            warmed["cached"],
            warmed["requested"],
            read_elapsed,
            warmed["failed"],
        )

        for symbol in target:
            symbol = symbol.upper()

            # The Gold frame comes from the cache the warm-up filled. It is
            # read ONCE and shared by every model, because the download is
            # the expensive part and the models all need the same history.
            try:
                gold = layer.read(symbol)
                if gold.empty:
                    summary.forecast_failed += 1
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Universe forecast failed for %s: %s", symbol, exc)
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
                        }
                        try:
                            repository.upsert(payload)
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
    # WHY THE SCORING PASS RUNS BEFORE THE CACHE BOUND IS RESTORED
    # --------------------------------------------------------------
    # The scoring pass reads the same Gold frames the forecast pass
    # just warmed. Restoring the bound first would EVICT most of those
    # frames (the batch raised it to hold the whole universe, the
    # default is sized for a browsing session), and the scoring pass
    # would then download every symbol's history a second time - the
    # exact cost the warm-up exists to avoid.
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
