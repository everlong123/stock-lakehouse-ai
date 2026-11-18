"""Persistence helpers for the next-session forecasts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session

from app.core.data_integrity import (
    MAX_PREDICTION_REFERENCE_FACTOR,
    describe_fabricated_symbol,
    describe_impossible_price,
    is_fabricated_symbol,
    is_impossible_price,
)
from app.database.models.prediction import Prediction


class PredictionRepository:
    """CRUD operations for the ``predictions`` table.

    WHY THE UPSERT IS AN UPDATE AND NOT AN INSERT
    ----------------------------------------------
    The EOD batch may run more than once for the same session (a retry, a
    manual re-run, a second container). The table must hold ONE forecast per
    (symbol, model, target session) - the most recent one - so a re-run
    overwrites the row instead of accumulating duplicates that would make
    the Dashboard's "latest forecast" ambiguous.

    WHY THE UPSERT DOES NOT CLOBBER A SCORE
    ----------------------------------------
    The forecast and its outcome live on the same row, and they are written
    at DIFFERENT times: the forecast when the session is about to open, the
    score when the session has closed. A re-run of the forecast pass (a
    retry, a second container, a manual re-run) must therefore NOT wipe the
    score that a later pass already computed.

    The outcome columns are copied separately from the forecast columns, so
    a forecast upsert leaves ``actual_close`` and its siblings untouched.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, payload: dict[str, Any]) -> Prediction:
        """Store a forecast, replacing any earlier one for the same target.

        WHY A FABRICATED SYMBOL IS REJECTED HERE
        ----------------------------------------
        This is the single write path into the ``predictions`` table, so
        it is where a forecast for a symbol that does not exist has to
        stop. On 15/11/2026 the table held 200 rows for ``TST0`` ..
        ``TST199`` - invented prices under a tag that means "the system
        published this", and nothing in the table distinguished them from
        real published forecasts.

        The check is a prefix denylist of the well-known test-fixture
        markers. It is cheap, it needs no storage round-trip, and it can
        be pinned by a test. See ``app/core/data_integrity.py``.

        WHY AN IMPOSSIBLE PRICE IS REJECTED HERE
        ---------------------------------------
        The same write path is where a forecast for a negative price has to
        stop. On 15/11/2026 the ledger held nineteen such rows - LCID at
        -4.09, SOXS at -359,121,248 - produced by a price-level model
        fitted on a history that mixes two price scales. A negative price
        is not a large error, it is a value no exchange can print, and it
        poisons every mean that is computed over the table.
        """
        symbol = str(payload["symbol"]).upper()
        if is_fabricated_symbol(symbol):
            raise ValueError(describe_fabricated_symbol(symbol))

        if is_impossible_price(
            payload.get("predicted_close"),
            payload.get("reference_close"),
        ):
            raise ValueError(
                describe_impossible_price(
                    payload.get("predicted_close"),
                    payload.get("reference_close"),
                )
            )

        model_name = payload["model_name"]
        target_session = payload["target_session"]

        stmt = select(Prediction).where(
            Prediction.symbol == symbol,
            Prediction.model_name == model_name,
            Prediction.target_session == target_session,
        )
        record = self.session.scalars(stmt).first()
        if record is None:
            record = Prediction(**payload)
            self.session.add(record)
        else:
            # The outcome columns are deliberately excluded: a forecast
            # re-run must not erase a score that was already computed for
            # a session that has since happened.
            outcome_fields = _OUTCOME_FIELDS
            for key, value in payload.items():
                if key in ("id", *outcome_fields):
                    continue
                setattr(record, key, value)
            # `created_at` is when THIS forecast was published, so a
            # re-run has to move it. Without this, a retried batch that
            # ran with fresher data would leave the row claiming the
            # OLD publication time - and the reader would have no way to
            # tell that the forecast was redone.
            #
            # The timestamp is set in Python rather than by an
            # ``onupdate`` rule because the column's default is
            # ``server_default`` (the database supplies it on INSERT),
            # and a column with a server default does not fire
            # ``onupdate``.
            #
            # The microseconds are dropped on purpose. The column is a
            # plain ``DateTime``, so MySQL stores whole seconds - and a
            # value written with microseconds would come back ROUNDED,
            # which means the timestamp in memory and the timestamp read
            # back from the database would disagree. Writing the same
            # precision the column can hold keeps the two identical.
            record.created_at = datetime.now(UTC).replace(
                tzinfo=None, microsecond=0
            )
        self.session.flush()
        return record

    def score(self, payload: dict[str, Any]) -> Prediction | None:
        """Write the outcome of an already-stored forecast.

        The row is located by (symbol, model, target session) - the same
        key the forecast was stored under. When no such row exists the
        method returns None instead of creating one: a score without a
        forecast is meaningless, and inventing the forecast at scoring time
        would make the score look like it had a prediction behind it.
        """
        symbol = str(payload["symbol"]).upper()
        stmt = select(Prediction).where(
            Prediction.symbol == symbol,
            Prediction.model_name == payload["model_name"],
            Prediction.target_session == payload["target_session"],
        )
        record = self.session.scalars(stmt).first()
        if record is None:
            return None
        for key, value in payload.items():
            if key in ("id", "symbol", "model_name", "target_session"):
                continue
            setattr(record, key, value)
        self.session.flush()
        return record

    def unscored(self, symbol: str | None = None, limit: int = 5000) -> list[Prediction]:
        """Forecasts whose target session has passed but that carry no score.

        The batch scores a forecast once the session it predicted has been
        ingested. Until then the row stays unscored - so this query is what
        the scoring pass walks.
        """
        stmt = select(Prediction).where(Prediction.actual_close.is_(None))
        if symbol:
            stmt = stmt.where(Prediction.symbol == symbol.upper())
        stmt = stmt.order_by(Prediction.target_session.asc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def scored_series(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
        limit: int = 500,
    ) -> list[Prediction]:
        """The scored forecasts, oldest first - the verification series."""
        stmt = select(Prediction).where(Prediction.actual_close.isnot(None))
        if symbol:
            stmt = stmt.where(Prediction.symbol == symbol.upper())
        if model_name:
            stmt = stmt.where(Prediction.model_name == model_name)
        stmt = stmt.order_by(Prediction.target_session.asc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def accuracy_summary(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate the scores of the forecasts that have been verified.

        Every number here is computed by the database over rows that carry
        a REAL closing price. A row with no score is excluded from the
        count rather than counted as a failure - an unscored forecast is
        unverified, not wrong.

        ``directional_accuracy`` is the share of verified forecasts whose
        direction matched the actual move. ``mean_error_pct`` is the mean
        of the signed relative error, which shows whether the model
        systematically over- or under-predicts.

        WHY THE MEAN IS NOT THE HEADLINE
        ---------------------------------
        The arithmetic mean of a relative error is destroyed by a single
        row whose forecast is off by orders of magnitude. On 15/11/2026 the
        mean of the absolute relative error over 44.676 verified rows was
        26.385%, while the median was 1,15% - and one symbol (``PARA``)
        accounted for 99,993% of the total error mass on its own, because
        its history mixes two price scales (four reverse splits) and the
        price-level model extrapolated off the end of that series.

        So this method reports THREE views of the same rows:

        * ``mean_error_pct`` - the signed mean over the CLEAN rows. It is
          kept, because "does the model over- or under-predict on
          average" is a question worth answering.
        * ``median_error_pct`` - the robust headline: a typical forecast.
        * ``wape`` - the weighted absolute percentage error,
          ``sum(|error|) / sum(reference)``. It normalises by the total
          money the forecasts were about, so a penny stock cannot dominate
          it and a 100x-larger stock cannot drown it out.

        Rows whose forecast price cannot exist on an exchange (negative,
        or more than :data:`MAX_PREDICTION_REFERENCE_FACTOR` away from its
        reference) are EXCLUDED from the clean figures and COUNTED in
        ``excluded_impossible``. They are not silently dropped: a report
        that hides them would hide the very failure it exists to surface.
        """
        clean_filters = [
            Prediction.actual_close.isnot(None),
            Prediction.reference_close > 0,
            Prediction.actual_close > 0,
            Prediction.predicted_close > 0,
            Prediction.error_pct.isnot(None),
            _within_reference_factor(),
        ]
        scope: list[Any] = []
        if symbol:
            scope.append(Prediction.symbol == symbol.upper())
        if model_name:
            scope.append(Prediction.model_name == model_name)

        stmt = select(
            func.count(Prediction.id),
            func.avg(Prediction.abs_error),
            func.avg(Prediction.error_pct),
            func.avg(Prediction.direction_correct),
            func.min(Prediction.target_session),
            func.max(Prediction.target_session),
            func.sum(Prediction.abs_error),
            func.sum(Prediction.reference_close),
            func.sum(
                func.cast(
                    Prediction.data_staleness_days.isnot(None),
                    Integer,
                )
            ),
            func.sum(
                func.cast(
                    Prediction.data_staleness_days > 0,
                    Integer,
                )
            ),
            func.max(Prediction.data_staleness_days),
        ).where(*clean_filters, *scope)

        row = self.session.execute(stmt).first()
        if row is None:
            return {
                "verified": 0,
                "mae": None,
                "mean_error_pct": None,
                "directional_accuracy": None,
                "first_session": None,
                "last_session": None,
                "wape": None,
                "excluded_impossible": 0,
                "staleness_measured": 0,
                "staleness_unrecorded": 0,
                "stale_forecasts": 0,
                "max_staleness_days": None,
            }

        verified = int(row[0] or 0)
        total_abs_error = float(row[6]) if row[6] is not None else None
        total_reference = float(row[7]) if row[7] is not None else None
        wape = None
        if total_abs_error is not None and total_reference:
            wape = 100.0 * total_abs_error / total_reference

        # How fresh the input data was when these forecasts were made.
        #
        # A row with ``data_staleness_days = 0`` was made on current data;
        # a higher number means the ingestion had fallen behind and the
        # forecast rested on older history. Rows written before the
        # column existed carry NULL and are counted separately - they are
        # NOT treated as zero, because zero is a measurement and NULL
        # means the lag was never recorded.
        #
        # This is REPORTED, not used as a filter. Excluding the stale
        # rows would silently shrink the sample the accuracy is computed
        # over, and the reader is given the number instead.
        staleness_measured = int(row[8] or 0)
        stale_forecasts = int(row[9] or 0)

        return {
            "verified": verified,
            "mae": float(row[1]) if row[1] is not None else None,
            "mean_error_pct": float(row[2]) if row[2] is not None else None,
            "directional_accuracy": float(row[3]) if row[3] is not None else None,
            "first_session": row[4].isoformat() if row[4] else None,
            "last_session": row[5].isoformat() if row[5] else None,
            "wape": wape,
            "excluded_impossible": self.count_impossible(
                symbol=symbol,
                model_name=model_name,
            ),
            "staleness_measured": staleness_measured,
            "staleness_unrecorded": verified - staleness_measured,
            "stale_forecasts": stale_forecasts,
            "max_staleness_days": int(row[10]) if row[10] is not None else None,
        }

    def count_impossible(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
    ) -> int:
        """How many verified rows carry a forecast price that cannot exist.

        These are rows whose predicted price is negative, or whose
        reference price is not positive, or whose forecast sits more than
        :data:`MAX_PREDICTION_REFERENCE_FACTOR` away from its reference.
        They are counted, not returned, so the report can say how many
        rows it left out of the clean figures.
        """
        impossible = or_(
            Prediction.reference_close <= 0,
            Prediction.actual_close <= 0,
            Prediction.predicted_close <= 0,
            _beyond_reference_factor(),
        )
        stmt = select(func.count(Prediction.id)).where(
            Prediction.actual_close.isnot(None),
            Prediction.error_pct.isnot(None),
            impossible,
        )
        if symbol:
            stmt = stmt.where(Prediction.symbol == symbol.upper())
        if model_name:
            stmt = stmt.where(Prediction.model_name == model_name)
        return int(self.session.execute(stmt).scalar() or 0)

    def published_scored_series(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
        limit: int = 5000,
    ) -> list[Prediction]:
        """The verified forecasts the system PUBLISHED before the session.

        These are the rows whose source is NOT ``backfill_walk_forward`` -
        the ones the nightly batch wrote down while the session was still in
        the future. They are the strongest evidence the system has, so they
        are queried SEPARATELY rather than being filtered out of the
        general series: the general series is limited to the most recent
        ``limit`` rows, and a backfilled row from an older date would push
        a published row out of that window entirely.
        """
        stmt = select(Prediction).where(
            Prediction.actual_close.isnot(None),
            Prediction.source != "backfill_walk_forward",
        )
        if symbol:
            stmt = stmt.where(Prediction.symbol == symbol.upper())
        if model_name:
            stmt = stmt.where(Prediction.model_name == model_name)
        stmt = stmt.order_by(Prediction.target_session.asc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def median_error_pct(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
    ) -> float | None:
        """The MEDIAN of the absolute relative error.

        WHY THE MEDIAN AND NOT ONLY THE MEAN
        --------------------------------------
        The mean of the relative error is dragged around by a handful of
        rows whose forecast is off by orders of magnitude. On 13/11/2026
        the mean of the absolute relative error over 44.491 verified rows
        was 265%, while the median was 1,16%. On 15/11/2026 the cause was
        pinned down: one symbol (``PARA``) held 99,993% of the total error
        mass, because its history mixes two price scales and the
        price-level model extrapolated off the end of it. The median is the
        number that describes a TYPICAL verified forecast, so it is the one
        the report leads with.

        Rows whose forecast price could not exist on an exchange are
        EXCLUDED here for the same reason they are excluded from
        ``accuracy_summary``: a negative price is not a "large error", it
        is not an error at all.

        The result is returned as a FRACTION (0.01 = 1%), the same unit as
        ``error_pct``, so it can be formatted without a unit conversion.

        The rows are read back in error order and the middle one is taken,
        so the computation happens in SQL instead of pulling 44.000 rows
        into Python.
        """
        filters = [
            Prediction.actual_close.isnot(None),
            Prediction.error_pct.isnot(None),
            Prediction.reference_close > 0,
            Prediction.actual_close > 0,
            Prediction.predicted_close > 0,
            _within_reference_factor(),
        ]
        if symbol:
            filters.append(Prediction.symbol == symbol.upper())
        if model_name:
            filters.append(Prediction.model_name == model_name)

        total = int(
            self.session.execute(select(func.count(Prediction.id)).where(*filters)).scalar() or 0
        )
        if not total:
            return None

        value = self.session.execute(
            select(Prediction.error_pct)
            .where(*filters)
            .order_by(func.abs(Prediction.error_pct).asc())
            .offset(total // 2)
            .limit(1)
        ).scalar()
        if value is None:
            return None
        return abs(float(value))

    def latest_for_symbol(self, symbol: str) -> Prediction | None:
        """The most recent forecast for a symbol, across all models."""
        stmt = (
            select(Prediction)
            .where(Prediction.symbol == symbol.upper())
            .order_by(Prediction.target_session.desc(), Prediction.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def for_symbol_and_session(
        self, symbol: str, target_session: date
    ) -> list[Prediction]:
        """Every model's forecast for ONE symbol and ONE target session.

        WHY THIS EXISTS
        ----------------
        The nightly batch can publish one forecast per model for the same
        session, so a reader who wants to compare the models has to be
        able to fetch them TOGETHER. The rows live in the same table and
        differ only by ``model_name``, so they are read with one query
        rather than one query per model.

        The forecasting page shows them side by side, and the Dashboard
        shows the single best-known one. Both read the same rows - there
        is no second copy of a forecast anywhere.
        """
        stmt = (
            select(Prediction)
            .where(
                Prediction.symbol == symbol.upper(),
                Prediction.target_session == target_session,
            )
            .order_by(Prediction.model_name)
        )
        return list(self.session.scalars(stmt).all())

    def latest_session_for_symbol(self, symbol: str) -> date | None:
        """The newest target session this symbol has a forecast for."""
        stmt = (
            select(Prediction.target_session)
            .where(Prediction.symbol == symbol.upper())
            .order_by(Prediction.target_session.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def latest_for_session(self, target_session: date) -> list[Prediction]:
        """Every forecast stored for one target session."""
        stmt = (
            select(Prediction)
            .where(Prediction.target_session == target_session)
            .order_by(Prediction.symbol)
        )
        return list(self.session.scalars(stmt).all())

    def recent(self, limit: int = 50) -> list[Prediction]:
        stmt = select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())


#: The columns that hold the OUTCOME of a forecast. They are written by the
#: scoring pass, never by the forecast pass.
_OUTCOME_FIELDS = (
    "actual_close",
    "abs_error",
    "error_pct",
    "direction_correct",
    "scored_at",
)


def _reference_ratio():
    """The ratio between the forecast and its reference, as a distance.

    WHY THE GREATEST AND NOT THE LEAST
    ----------------------------------
    The ratio has to be AT LEAST 1, so that "100 times further away" means
    the same thing in both directions. ``LEAST(a/b, b/a)`` is the SMALLER
    of the two, so a forecast that is a million times too BIG still has a
    ratio of one-millionth - and it passes any "<= 100" test. That mistake
    is exactly what let the two most absurd rows in the table sit inside
    the clean figures on 15/11/2026: ``PARA`` was predicted at 242.751
    against a reference of 0,072, and its ratio computed with ``LEAST``
    came out as 0,0000003 - comfortably "under 100".

    ``GREATEST`` takes the larger of the two, so the ratio is the distance
    from the reference in both directions: 1,0 means the forecast equals
    its reference, and 100 means it is a hundred times further away.
    """
    return func.greatest(
        func.abs(Prediction.predicted_close / Prediction.reference_close),
        func.abs(Prediction.reference_close / Prediction.predicted_close),
    )


def _within_reference_factor():
    """The forecast sits close enough to its reference to be believable."""
    return _reference_ratio() <= MAX_PREDICTION_REFERENCE_FACTOR


def _beyond_reference_factor():
    """The forecast is so far from its reference that it cannot be trusted."""
    return _reference_ratio() > MAX_PREDICTION_REFERENCE_FACTOR
