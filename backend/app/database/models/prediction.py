"""Stored next-session forecasts.

WHY A TABLE FOR PREDICTIONS
---------------------------
The forecasting models produce a number for a session that has not happened
yet. That number is only meaningful if it is dated, model-attributed and
reproducible, so it is persisted instead of being recomputed on every
request.

The table holds ONE ROW PER (symbol, model, target session). Re-running the
EOD batch for the same session overwrites the row rather than adding a
second one, so the table always holds the LATEST forecast for each target
session - which is what the Dashboard reads.

The `source` column records where the forecast came from. A row written by
the automated EOD batch carries ``auto_eod_batch``; a row written by the
forecast endpoint on demand carries ``manual_api``. The Dashboard can
therefore say whether the number it shows came from the overnight batch or
from a user clicking the button.

WHY THE SAME ROW HOLDS THE OUTCOME
----------------------------------
A forecast is only meaningful once the session it predicted has happened.
The outcome columns close that loop on the SAME row, so a forecast and its
score can never be separated:

    actual_close       the real close of the target session (Gold)
    abs_error          |predicted_close - actual_close|
    error_pct          the error as a fraction of the reference close
    direction_correct  1 when the forecast and the actual move agree
    scored_at          when the outcome was written

All of them are NULL until the target session has actually been ingested.
A NULL means "not scored yet" - it never means "scored as zero", because a
forecast that was never checked against reality is not a wrong forecast, it
is an unverified one, and the two must not look the same in a table.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Prediction(Base):
    """One next-session forecast for one symbol and one model."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: The trading session this forecast is about.
    target_session: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: The last close the forecast was anchored on (the close of the session
    #: BEFORE the target session).
    reference_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_close: Mapped[float] = mapped_column(Float, nullable=False)
    #: ``(predicted_close - reference_close) / reference_close`` as a fraction
    #: (0.01 = +1%). Stored as a fraction, not a percentage, so it can be
    #: compared with the price series without a unit conversion.
    predicted_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The horizon the model was asked for, in sessions.
    horizon: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    #: Where the forecast came from: ``auto_eod_batch`` or ``manual_api``.
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="auto_eod_batch")
    #: The layer the forecast's input data was read from.
    source_layer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: How many trading sessions the newest Gold bar lags behind the
    #: target session. 0 means the forecast was made on data that was
    #: current up to the session right before the target; 1 means the
    #: ingestion had missed one session; and so on.
    #:
    #: WHY THIS IS STORED
    #: ------------------
    #: A forecast made on stale data is still a valid forward forecast -
    #: it was published before the target session happened - but the
    #: reader has to be able to SEE how much history it actually rested
    #: on. A silent skip is worse than a wrong number: the forecast
    #: targets a session further away, and nothing on the row says so.
    #:
    #: A NULL means the row predates this column, so the lag was not
    #: recorded. It is not "0" and not "unknown quality".
    data_staleness_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # ── The outcome of the forecast ─────────────────────────────────────
    # All five are NULL until the target session has actually happened and
    # been ingested into Gold. The scoring pass fills them in.
    #: The real closing price of the target session, read from Gold.
    actual_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: ``|predicted_close - actual_close|``, in the symbol's own price unit.
    abs_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The error as a FRACTION of the reference close (0.01 = 1%). Stored as
    #: a fraction so it can be compared across symbols with very different
    #: price scales without a unit conversion.
    error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: 1 when the forecast and the actual move agree in direction, 0 when
    #: they disagree, NULL when the reference close is unavailable (the
    #: direction of a move is undefined without a starting point).
    direction_correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: When the outcome was written.
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
