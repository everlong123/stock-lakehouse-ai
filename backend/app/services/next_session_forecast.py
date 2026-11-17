"""Next-session forecasting: run a trained model and persist its forecast.

WHY A SEPARATE SERVICE
----------------------
The EOD batch has to do three things after a session closes:

  1. ingest the day's bars into Bronze,
  2. rebuild Silver and Gold for the symbols that changed,
  3. produce a forecast for the session that is about to open.

Step 3 lives here so the batch stays readable, and so the Dashboard and
the batch use the SAME code path to produce a forecast. A number that the
Dashboard shows and a number the batch stored must come from the same
function, otherwise the two can disagree and the disagreement is
undetectable.

WHAT THIS NEVER DOES
--------------------
It never TRAINS a model. Training a model on the VPS is not viable: the
LSTM needs roughly 32 GB of RAM to train and the target VPS has 8 GB. The
models are trained manually on a workstation and copied to the server (see
``backend/scripts/sync_models_to_vps.py``). This service only USES models
that already exist on disk.

When a symbol has no trained model, the service says so and returns
nothing. It never substitutes a default, a moving average, or a random
number: a forecast that did not come from a model would be a fabricated
number on the Dashboard.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.logging_config import get_logger
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.session import check_database_connection, get_session_factory
from app.forecasting.model_registry import list_trained_models, model_directory

logger = get_logger(__name__)


def has_trained_model(symbol: str, model_name: str) -> bool:
    """True when a trained model for the symbol exists on disk."""
    try:
        directory = model_directory(symbol, model_name)
    except Exception:  # noqa: BLE001
        return False
    return (directory / "registry.json").exists()


def build_next_session_forecast(
    symbol: str,
    model_name: str | None = None,
    horizon: int = 1,
) -> dict[str, Any]:
    """Produce the next-session forecast for a symbol.

    Returns a payload that always says where the numbers came from:

        {
            "symbol": "AAPL",
            "model_name": "arima",
            "target_session": "2026-11-11",
            "reference_close": 331.2,
            "predicted_close": 334.0,
            "predicted_return": 0.0084,
            "horizon": 1,
            "source_layer": "gold",
            "generated_at": "...",
        }

    When the symbol has no trained model, the payload carries
    ``available: False`` and a reason. It does NOT contain a price.
    """
    symbol = symbol.upper()

    if model_name is None:
        trained = list_trained_models(symbol)
        if not trained:
            return {
                "available": False,
                "symbol": symbol,
                "reason": (
                    f"No trained model exists for {symbol}. Train one before a "
                    "next-session forecast can be produced."
                ),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        model_name = trained[0].get("model_name", "arima")

    if not has_trained_model(symbol, model_name):
        return {
            "available": False,
            "symbol": symbol,
            "model_name": model_name,
            "reason": f"No trained {model_name} model found for {symbol}.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        # The forecast is computed through the SHARED light path, so the
        # nightly batch and the forecasting page cannot disagree about the
        # number. See `app/forecasting/light_forecast.py`.
        from app.forecasting import light_forecast
        from app.lakehouse.gold import GoldLayer

        gold = GoldLayer().read(symbol)
        if gold.empty:
            return {
                "available": False,
                "symbol": symbol,
                "model_name": model_name,
                "reason": f"No Gold data available for {symbol}.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        point = light_forecast.next_point(symbol, model_name, gold, horizon=horizon)
        if not point.get("available"):
            return {
                "available": False,
                "symbol": symbol,
                "model_name": model_name,
                "reason": point.get("reason", "The model could not produce a forecast."),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        predicted_close = float(point["predicted_close"])
        reference_close = point.get("reference_close")
        predicted_return = point.get("predicted_return")
        target_session = point.get("target_session")
        metrics = None
        metrics_source = None
    except NotFoundError as exc:
        return {
            "available": False,
            "symbol": symbol,
            "model_name": model_name,
            "reason": str(exc),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Next-session forecast failed for %s/%s: %s", symbol, model_name, exc)
        return {
            "available": False,
            "symbol": symbol,
            "model_name": model_name,
            "reason": f"The model could not produce a forecast: {exc}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "available": True,
        "symbol": symbol,
        "model_name": model_name,
        "target_session": target_session.isoformat() if target_session else None,
        "target_timestamp": point.get("timestamp"),
        "reference_close": reference_close,
        "predicted_close": predicted_close,
        "predicted_return": predicted_return,
        "horizon": horizon,
        "metrics": metrics,
        "metrics_source": metrics_source,
        "source_layer": "gold",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _reference_close(predictions: list[dict[str, Any]]) -> float | None:
    """The last ACTUAL close in the series - the anchor of the forecast."""
    for point in reversed(predictions):
        actual = point.get("actual")
        if actual is not None:
            try:
                return float(actual)
            except (TypeError, ValueError):
                return None
    return None


def store_next_session_forecast(
    forecast: dict[str, Any],
    db: Session | None = None,
    source: str = "auto_eod_batch",
) -> bool:
    """Persist a forecast in the ``predictions`` table.

    Returns True when the row was written. Returns False (and logs why) when
    the database is unavailable or the table has not been migrated yet. It
    NEVER raises: a missing forecast must not take down the EOD batch.
    """
    if not forecast.get("available"):
        return False
    if forecast.get("target_session") is None:
        return False

    owns_session = db is None
    session = db
    if session is None:
        if not check_database_connection():
            logger.warning("Next-session forecast not stored: the database is unavailable.")
            return False
        try:
            session = get_session_factory()()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Next-session forecast not stored: %s", exc)
            return False

    try:
        PredictionRepository(session).upsert(
            {
                "symbol": forecast["symbol"],
                "model_name": forecast["model_name"],
                "target_session": forecast["target_session"],
                "reference_close": forecast.get("reference_close"),
                "predicted_close": forecast["predicted_close"],
                "predicted_return": forecast.get("predicted_return"),
                "horizon": forecast.get("horizon", 1),
                "source": source,
                "source_layer": forecast.get("source_layer", "gold"),
            }
        )
        if owns_session:
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Next-session forecast for %s could not be stored: %s. "
            "The `predictions` table may be missing its Alembic migration "
            "(backend/alembic/versions/0002_predictions.py).",
            forecast.get("symbol"),
            exc,
        )
        if owns_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return False
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def predict_and_store(
    symbol: str,
    model_name: str | None = None,
    horizon: int = 1,
    source: str = "auto_eod_batch",
) -> dict[str, Any]:
    """Build the next-session forecast and store it. Used by the EOD batch."""
    forecast = build_next_session_forecast(symbol, model_name=model_name, horizon=horizon)
    if forecast.get("available"):
        stored = store_next_session_forecast(forecast, source=source)
        forecast["stored"] = stored
    else:
        forecast["stored"] = False
    return forecast
