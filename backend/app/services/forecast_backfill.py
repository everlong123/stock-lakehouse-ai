"""Backfill the verification ledger with historical forecasts.

WHY THIS FILE EXISTS
--------------------
The verification ledger fills itself one row per day: the nightly batch
forecasts tomorrow, and tomorrow's close scores it. That is the honest
way to build the record, and it is what the system does from now on.

But a ledger with one row is not a measurement. On 13/11/2026 the table
held exactly ONE verified forecast for AAPL - which says nothing about
whether the system works, only that it had run once.

This module fills the ledger with the system's OWN past predictions,
replayed over the historical hold-out split.

WHAT A BACKFILLED ROW IS, AND WHAT IT IS NOT
--------------------------------------------
It IS: the trained model's genuine one-step-ahead prediction for a real
session, compared against that session's real close. Every number comes
from the lakehouse and from the model.

It IS NOT: a forecast the system actually published at the time. Nobody
was watching the model on 2026-08-14; the system was not running a
nightly forecast yet.

So every backfilled row carries ``source = "backfill_walk_forward"``, and
the UI says which kind of row it is showing. A backfilled row and a
published row are NOT silently mixed: they carry different source tags,
so a reader can tell them apart and the system can report them
separately. The published rows are the stronger evidence - they are
predictions the system committed to before the session opened.

WHY THE MODEL IS REPLAYED ONE STEP AT A TIME
--------------------------------------------
The replay is a WALK-FORWARD: for session *t*, the model is given only
the data up to *t-1* and asked what it expected for *t*. The actual
close of *t* is fed in afterwards, never before. That is the same
discipline the backtest engine uses, and it is what makes the resulting
error a real measurement rather than a look-ahead.

The alternative - predicting the whole hold-out in one multi-step shot -
would produce a long-range projection and then score it as if it were a
one-step forecast. That inflates the error enormously and measures
nothing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logging_config import get_logger
from app.forecasting.multistep import holdout_history
from app.forecasting.model_registry import load_model, load_registry_record

logger = get_logger(__name__)

#: The source tag every backfilled row carries. It is deliberately
#: different from ``auto_eod_batch`` (a published forecast) and from
#: ``manual_api`` (a forecast someone triggered by hand).
BACKFILL_SOURCE = "backfill_walk_forward"


@dataclass
class BackfillSummary:
    """What one backfill pass did."""

    symbols: int = 0
    rows: int = 0
    stored: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols": self.symbols,
            "rows": self.rows,
            "stored": self.stored,
            "skipped": self.skipped,
            "failed": self.failed,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "errors": self.errors[:20],
        }


def backfill_symbol(
    symbol: str,
    model_name: str = "linear_regression",
    limit: int = 120,
    db: Any = None,
) -> dict[str, Any]:
    """Replay one symbol's model over its hold-out split and store the rows.

    The rows land in the same table as the published forecasts, tagged with
    ``BACKFILL_SOURCE``, so the ledger is one chronological record of what
    the system believed, session by session.
    """
    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory
    from app.lakehouse.gold import GoldLayer

    symbol = symbol.upper()
    owns_session = db is None
    session = db

    if session is None:
        if not check_database_connection():
            return {"symbol": symbol, "stored": 0, "reason": "The database is unavailable."}
        session = get_session_factory()()

    try:
        from app.forecasting.model_registry import load_evaluation_model

        model = load_evaluation_model(symbol, model_name)
        registry = load_registry_record(symbol, model_name)
        gold = GoldLayer().read(symbol)
        if gold.empty:
            return {"symbol": symbol, "stored": 0, "reason": "No Gold data."}

        # The SAME window the metrics were computed on, so the backfilled
        # rows and the reported MAE describe the same sessions.
        window = _holdout_window(registry)
        points = holdout_history(model, gold, model_name, limit=limit, window=window)
        if not points:
            return {"symbol": symbol, "stored": 0, "reason": "The model produced no hold-out history."}

        repository = PredictionRepository(session)
        stored = 0
        for point in points:
            target = _session_date(point.get("timestamp"), symbol)
            actual = point.get("actual")
            predicted = point.get("predicted")
            if target is None or actual is None or predicted is None:
                continue

            reference = _previous_close(points, point.get("timestamp"))
            payload = {
                "symbol": symbol,
                "model_name": model_name,
                "target_session": target,
                "reference_close": reference,
                "predicted_close": float(predicted),
                "predicted_return": (
                    (float(predicted) - reference) / reference if reference else None
                ),
                "horizon": 1,
                "source": BACKFILL_SOURCE,
                "source_layer": "gold",
            }
            try:
                repository.upsert(payload)
                stored += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Backfill: cannot store %s/%s (%s)", symbol, target, exc)

        # The outcome columns are written by the scoring pass, not by the
        # forecast upsert, so the backfilled scores are applied explicitly.
        for point in points:
            target = _session_date(point.get("timestamp"), symbol)
            actual = point.get("actual")
            predicted = point.get("predicted")
            if target is None or actual is None or predicted is None:
                continue
            reference = _previous_close(points, point.get("timestamp"))
            repository.score(
                {
                    "symbol": symbol,
                    "model_name": model_name,
                    "target_session": target,
                    "actual_close": float(actual),
                    "abs_error": abs(float(predicted) - float(actual)),
                    "error_pct": (
                        (float(predicted) - float(actual)) / reference if reference else None
                    ),
                    "direction_correct": _direction(float(predicted), float(actual), reference),
                    "scored_at": _now(),
                }
            )

        if owns_session:
            session.commit()

        return {"symbol": symbol, "stored": stored, "points": len(points)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Backfill failed for %s/%s: %s", symbol, model_name, exc)
        if owns_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"symbol": symbol, "stored": 0, "reason": str(exc)}
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def backfill_universe(
    symbols: list[str] | None = None,
    model_name: str = "linear_regression",
    limit: int = 120,
) -> BackfillSummary:
    """Backfill the ledger for many symbols."""
    from app.forecasting.universe_training import list_gold_symbols

    summary = BackfillSummary()
    started = time.perf_counter()

    target = list(symbols) if symbols is not None else list_gold_symbols()
    for symbol in target:
        symbol = symbol.upper()
        result = backfill_symbol(symbol, model_name=model_name, limit=limit)
        if result.get("reason") and not result.get("stored"):
            summary.skipped += 1
            continue
        summary.symbols += 1
        summary.rows += int(result.get("points") or 0)
        summary.stored += int(result.get("stored") or 0)

    summary.elapsed_seconds = time.perf_counter() - started
    logger.info(
        "Backfill: %d symbols, %d rows, %d stored in %.1fs",
        summary.symbols,
        summary.rows,
        summary.stored,
        summary.elapsed_seconds,
    )
    return summary


def _holdout_window(registry: dict[str, Any]) -> tuple[Any, Any]:
    """The train/test boundaries the trainer recorded."""

    def _parse(value: Any) -> Any:
        if not value:
            return None
        try:
            import pandas as pd

            stamp = pd.to_datetime(value, utc=True)
        except Exception:  # noqa: BLE001
            return None
        return None if pd.isna(stamp) else stamp

    return (_parse(registry.get("test_target_start") or registry.get("test_start")), _parse(registry.get("test_target_end") or registry.get("test_end")))


def _session_date(timestamp: Any, symbol: str | None = None) -> Any:
    if not timestamp:
        return None
    try:
        import pandas as pd

        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        from app.lakehouse.exchange_timezone import session_day_of
        return session_day_of(stamp, symbol)
    except Exception:  # noqa: BLE001
        return None


def _previous_close(points: list[dict[str, Any]], timestamp: Any) -> float | None:
    """The close of the session BEFORE the one being scored.

    The direction of a move is measured from the previous close, not from
    the close of the session being predicted - the same convention the
    evaluator uses.
    """
    index = None
    for position, point in enumerate(points):
        if point.get("timestamp") == timestamp:
            index = position
            break
    if index is None or index == 0:
        return None
    previous = points[index - 1].get("actual")
    if previous is None:
        return None
    try:
        return float(previous)
    except (TypeError, ValueError):
        return None


def _direction(predicted: float, actual: float, reference: float | None) -> int | None:
    """1 when the forecast and the actual move agree, 0 when they do not."""
    if not reference:
        return None
    predicted_direction = (predicted > reference) - (predicted < reference)
    actual_direction = (actual > reference) - (actual < reference)
    if predicted_direction == 0 or actual_direction == 0:
        return None
    return 1 if predicted_direction == actual_direction else 0


def _now() -> Any:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)
