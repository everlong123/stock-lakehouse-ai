"""Score the forecasts that have already been made.

WHY THIS FILE EXISTS
--------------------
The forecasting system had one direction in time. The nightly EOD batch
ingested the day's bars, asked the model what it expected for the next
session, and wrote that number to the ``predictions`` table. Then it
stopped.

The consequence was that the system's REAL accuracy was unmeasurable. The
MAE and MAPE shown on the forecasting page are computed on a historical
hold-out split - a backtest. They answer "how accurate was this model on
sessions that had already happened when the model was built", which is a
different question from "how accurate were the forecasts this system
actually published".

This module closes that loop:

    forecast  ──►  the session happens  ──►  score against the real close
    (Gold, yesterday)     (Gold, today)         (stored, permanently)

WHY THE SCORE MUST BE COMPUTED FROM GOLD, NOT FROM THE FORECAST
--------------------------------------------------------------
The outcome is the REAL closing price of the target session, read from the
same Gold layer every other endpoint reads. It is never re-derived from
the model's own output, and never approximated. If Gold has no bar for the
target session, the forecast stays unscored - an honest "not verified yet"
rather than a fabricated score.

WHY THE DIRECTION IS THE HEADLINE METRIC
-----------------------------------------
``abs_error`` is in the symbol's own price unit, so it cannot be compared
across AAPL (340) and VCB (53,500). The relative error can, and the
direction match can be compared perfectly. So the accuracy report leads
with the directional accuracy and carries the error metrics alongside.

WHY THIS NEVER TRAINS OR FORECASTS
-----------------------------------
This module only COMPARES. It never trains a model and it never produces
a new forecast: the forecast was already published, and changing it now
would destroy the very evidence this module exists to collect.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.session import check_database_connection, get_session_factory
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)


def _session_date(value: Any) -> date | None:
    """The trading day a stored timestamp belongs to.

    Gold stamps a daily bar at the session OPEN, but a provider may also
    publish an after-hours bar at the CLOSE for the same trading day. The
    forecast targets a trading DAY, so the day has to be extracted the same
    way on both sides - otherwise the score would be written against the
    wrong session.
    """
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.date()


def _closes_by_session(frame: pd.DataFrame) -> dict[date, float]:
    """Map each trading day in ``frame`` to its closing price."""
    if frame.empty or "close" not in frame.columns:
        return {}
    working = frame.loc[:, ["timestamp", "close"]].copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.dropna(subset=["timestamp", "close"])
    if working.empty:
        return {}

    closes: dict[date, float] = {}
    for stamp, close in zip(working["timestamp"], working["close"]):
        day = _session_date(stamp)
        if day is None:
            continue
        # The last bar of a trading day wins: a provider may publish an
        # open-stamped bar first and settle it at the close.
        closes[day] = float(close)
    return closes


def score_forecast(
    forecast: Any,
    actual_close: float,
    scored_at: datetime | None = None,
) -> dict[str, Any]:
    """Compute the outcome of one forecast against a real close.

    Returns the payload that is written back to the row. Every field is
    derived from two stored numbers - the forecast and the real close - so
    the result is reproducible by hand from the table itself.
    """
    predicted_close = float(forecast.predicted_close)
    reference_close = forecast.reference_close

    abs_error = abs(predicted_close - actual_close)
    error_pct: float | None = None
    if reference_close:
        error_pct = (predicted_close - actual_close) / float(reference_close)

    direction_correct: int | None = None
    if reference_close:
        predicted_direction = (predicted_close > float(reference_close)) - (
            predicted_close < float(reference_close)
        )
        actual_direction = (actual_close > float(reference_close)) - (
            actual_close < float(reference_close)
        )
        # A flat session has no direction to agree or disagree with, so it
        # is excluded rather than counted as a miss.
        if predicted_direction != 0 and actual_direction != 0:
            direction_correct = 1 if predicted_direction == actual_direction else 0

    return {
        "actual_close": float(actual_close),
        "abs_error": abs_error,
        "error_pct": error_pct,
        "direction_correct": direction_correct,
        "scored_at": scored_at or datetime.now(timezone.utc).replace(tzinfo=None),
    }


def score_symbol(symbol: str, db: Session | None = None) -> dict[str, Any]:
    """Score every unscored forecast of one symbol.

    Returns a summary describing what happened. A symbol with no Gold data
    is reported as such - it is not an error, and it does not produce
    scores.

    WHY THE GOLD READ HAPPENS BEFORE THE DATABASE WORK
    ---------------------------------------------------
    The bug this fixes: this function used to open the session, query the
    pending forecasts, and only THEN read Gold. Reading a ten-year daily
    symbol from MinIO costs ~120 s when the cache is cold, and the session
    held an open InnoDB transaction for that whole time. Every UPDATE that
    followed then waited on a lock that could not be granted until the
    read was finished - and ``innodb_lock_wait_timeout`` is 50 s. The
    result was a reproducible ``Lock wait timeout exceeded`` on a row that
    was not locked by anybody else.

    The fix is to do the slow I/O FIRST and the database work SECOND, so
    the transaction is open for milliseconds instead of minutes.
    """
    symbol = symbol.upper()
    owns_session = db is None
    session = db

    # Step 1: read the prices BEFORE touching the database. This is the
    # slow part, and it must not happen inside a transaction.
    try:
        frame = GoldLayer().read(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scoring: cannot read Gold for %s (%s)", symbol, exc)
        return {"symbol": symbol, "scored": 0, "reason": f"Cannot read Gold: {exc}"}

    if frame.empty:
        return {"symbol": symbol, "scored": 0, "reason": "Gold holds no usable bar."}

    closes = _closes_by_session(frame)
    if not closes:
        return {"symbol": symbol, "scored": 0, "reason": "Gold holds no usable bar."}

    # Step 2: the database work. The session is opened here, and it stays
    # open only for the duration of the SELECT and the UPDATEs.
    if session is None:
        if not check_database_connection():
            return {
                "symbol": symbol,
                "scored": 0,
                "reason": "The database is unavailable.",
            }
        try:
            session = get_session_factory()()
        except Exception as exc:  # noqa: BLE001
            return {"symbol": symbol, "scored": 0, "reason": str(exc)}

    try:
        repository = PredictionRepository(session)
        pending = repository.unscored(symbol=symbol)
        if not pending:
            return {"symbol": symbol, "scored": 0, "reason": "No unscored forecast."}

        scored = 0
        skipped: list[str] = []
        for forecast in pending:
            actual = closes.get(forecast.target_session)
            if actual is None:
                # The target session has not been ingested yet. It stays
                # unscored, and it will be picked up by a later pass.
                skipped.append(forecast.target_session.isoformat())
                continue
            payload = score_forecast(forecast, actual)
            payload["symbol"] = forecast.symbol
            payload["model_name"] = forecast.model_name
            payload["target_session"] = forecast.target_session
            repository.score(payload)
            scored += 1

        if owns_session:
            session.commit()

        return {
            "symbol": symbol,
            "scored": scored,
            "pending_sessions": skipped,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scoring failed for %s: %s", symbol, exc)
        if owns_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"symbol": symbol, "scored": 0, "reason": str(exc)}
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def score_all(
    symbols: list[str] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Score the pending forecasts of many symbols.

    This is the batch entry point. It is called after the nightly ingest,
    when the newest session has landed in Gold - which is exactly when the
    previous session's forecast becomes verifiable.

    WHY THE PASS IS SPLIT IN TWO PHASES
    ------------------------------------
    Phase 1 reads Gold for every symbol and remembers the closing price of
    each session. Phase 2 writes the scores. The split exists because of
    the lock timeout that used to break this pass: the old code opened one
    session, read Gold for symbol after symbol, and wrote inside the same
    open transaction. With ~970 symbols the transaction stayed open for
    minutes, so the UPDATE at the end of it waited on its own lock until
    ``innodb_lock_wait_timeout`` fired and the whole pass was lost.

    Splitting the pass means the slow reads happen with NO transaction
    open, and the writes happen in short committed chunks.
    """
    owns_session = db is None
    session = db

    # ---- Phase 0: find out what is pending ---------------------------
    # A short read-only transaction. It is committed immediately so it
    # holds no locks while the Gold reads happen.
    if session is None:
        if not check_database_connection():
            return {"scored": 0, "symbols": 0, "reason": "The database is unavailable."}
        try:
            session = get_session_factory()()
        except Exception as exc:  # noqa: BLE001
            return {"scored": 0, "symbols": 0, "reason": str(exc)}

    try:
        repository = PredictionRepository(session)
        if symbols is None:
            pending = repository.unscored(limit=200_000)
        else:
            pending = []
            for symbol in symbols:
                pending.extend(repository.unscored(symbol=symbol))

        if not pending:
            return {"scored": 0, "symbols": 0, "reason": "Nothing to score."}

        # Group by symbol so each symbol's Gold data is read exactly once.
        by_symbol: dict[str, list] = {}
        for forecast in pending:
            by_symbol.setdefault(forecast.symbol, []).append(forecast)

        # The pending rows are loaded into memory, so the read transaction
        # can be closed before the slow phase starts.
        if owns_session:
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scoring pass failed: %s", exc)
        if owns_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"scored": 0, "symbols": 0, "reason": str(exc)}
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

    # ---- Phase 1: read the prices, with NO transaction open ----------
    closes_by_symbol: dict[str, dict[date, float]] = {}
    failed: list[dict[str, str]] = []
    for symbol in by_symbol:
        try:
            # The frame comes from the shared cache. The universe pass
            # warmed it a moment ago, so this is a memory lookup
            # instead of another download of the symbol's whole
            # history.
            frame = GoldLayer().read(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scoring: cannot read Gold for %s (%s)", symbol, exc)
            failed.append({"symbol": symbol, "reason": str(exc)})
            continue
        closes = _closes_by_session(frame)
        if closes:
            closes_by_symbol[symbol] = closes

    # ---- Phase 2: write the scores ----------------------------------
    session = db
    if session is None:
        if not check_database_connection():
            return {
                "scored": 0,
                "symbols": len(by_symbol),
                "failed": failed,
                "reason": "The database is unavailable.",
            }
        try:
            session = get_session_factory()()
        except Exception as exc:  # noqa: BLE001
            return {
                "scored": 0,
                "symbols": len(by_symbol),
                "failed": failed,
                "reason": str(exc),
            }

    try:
        repository = PredictionRepository(session)
        total = 0
        for symbol, forecasts in by_symbol.items():
            closes = closes_by_symbol.get(symbol)
            if not closes:
                continue
            for forecast in forecasts:
                actual = closes.get(forecast.target_session)
                if actual is None:
                    continue
                payload = score_forecast(forecast, actual)
                payload["symbol"] = forecast.symbol
                payload["model_name"] = forecast.model_name
                payload["target_session"] = forecast.target_session
                repository.score(payload)
                total += 1

        if owns_session:
            session.commit()

        return {
            "scored": total,
            "symbols": len(by_symbol),
            "failed": failed,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scoring pass failed: %s", exc)
        if owns_session:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"scored": 0, "symbols": len(by_symbol), "failed": failed, "reason": str(exc)}
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass
