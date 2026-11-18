"""Record how stale the input data was when a forecast was published.

Revision ID: 0005_prediction_staleness
Revises: 0004_prediction_scoring
Create Date: 2026-11-18

WHY
---
The ``predictions`` table records WHAT was forecast and WHEN. It did not
record HOW FRESH the input data was at that moment.

That gap matters because the target-session rule works like this: a
forecast targets the first trading session that is not earlier than
today, and not earlier than the session after the newest bar in Gold.
When the ingestion is current, those two coincide and the forecast is a
plain next-session forecast. When the ingestion has fallen behind - a
failed fetch, a holiday on the local machine, a container restart - the
two separate, and the forecast silently targets a session further away
than the one right after the newest bar.

    10|Silently is the problem. The number on the row is not wrong: it is still a
forward forecast, published before the target session happened, and it
will still be scored against the real close. But a reader cannot tell
that it was made on data three sessions old, and an accuracy report
cannot separate "the model was right" from "the model was looking at
yesterday's news and predicting three days out".

WHAT THIS COLUMN HOLDS
----------------------
``data_staleness_days``
    The number of trading sessions between the newest bar in Gold and
    the target session.

    0
        The newest bar is the session immediately before the target.
        This is the ordinary case: the forecast is a next-session
        forecast made on current data.

    1
        The newest bar is two sessions before the target. The ingestion
        missed one session.

    2 and above
        The ingestion is lagging further and further behind.

    NULL
        The row was written before this column existed, so the lag was
        never measured. It is not a zero, and it is not a claim about
        quality.

WHY IT IS NULLABLE
------------------
Every existing row already has a forecast and an outcome. Re-deriving
the lag for them would mean re-reading Gold for tens of thousands of
rows and guessing which bar was the newest at the moment the forecast
was published - a reconstruction, not a measurement. The honest value
for those rows is "not recorded".

WHY THIS IS NOT A DATA-QUALITY GATE
-----------------------------------
The column is INFORMATION, not a filter. A forecast made on stale data
is still evidence, and excluding it would silently shrink the sample
that the accuracy report is computed over. The reader is given the
number and decides what to do with it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_prediction_staleness"
down_revision = "0004_prediction_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("data_staleness_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("predictions", "data_staleness_days")
