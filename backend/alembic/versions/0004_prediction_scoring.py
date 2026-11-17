"""Add the scoring columns to ``predictions``.

Revision ID: 0004_prediction_scoring
Revises: 0003_agent_mediumtext
Create Date: 2026-11-13

WHY
---
The ``predictions`` table had only ONE direction in time: it stored what the
model FORECAST, and nothing about what actually happened. The nightly EOD
batch wrote a forecast for the next session and stopped there.

That made the system's real-world accuracy unmeasurable. The MAE/MAPE shown
on the forecasting page are computed on a historical hold-out split - a
backtest. They answer "how accurate was this model on sessions that had
already happened", not "how accurate were the forecasts this system
actually published".

The missing piece is a CLOSED LOOP:

    forecast  ──►  the session happens  ──►  score against the real close

    (Gold, yesterday)      (Gold, today)         (stored, permanently)

WHY ONE MIGRATION AND NOT A NEW TABLE
-------------------------------------
The forecast and its outcome describe the SAME event - one forecast for one
(symbol, model, target session). Splitting them across two tables would
mean joining them on every read and would allow a forecast to exist with
no outcome, or an outcome with no forecast. Keeping them in one row makes
the pair atomic: the outcome columns are NULL until the session happens,
and they are filled in by the scoring pass.

WHY THESE EXACT COLUMNS
-----------------------
``actual_close``
    The real closing price of the target session, read from Gold. NULL
    until that session has been ingested.

``abs_error``
    ``|predicted_close - actual_close|``. Stored (not only computed) so the
    aggregate queries do not have to recompute it, and so the number that
    is displayed is the number that was stored.

``error_pct``
    The error as a fraction of the reference close, so it is comparable
    across symbols with wildly different price scales (AAPL at 340, VCB
    at 53,500). Stored as a fraction, not a percentage, to match
    ``predicted_return``.

``direction_correct``
    1 when the forecast and the actual move agree in DIRECTION, 0 when
    they disagree, NULL when the reference close is unavailable (the
    direction of a move is undefined without a starting point).

    This is the metric that matters most for a forecaster, because it is
    the only one that does not depend on the price scale at all.

``scored_at``
    When the outcome was written. It is what makes the row auditable: the
    reader can see that the score was produced by a real session, not
    invented.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_prediction_scoring"
down_revision = "0003_agent_mediumtext"
branch_labels = None
depends_on = None

# The columns are added as NULLABLE. Every existing row already has a
# forecast, and the sessions they point at have already happened - but
# they were never scored, because the scoring loop did not exist when
# they were written. The scoring pass fills them in for the rows it can
# reach; the rest stay NULL, which means "not scored" rather than
# "scored as zero".
_COLUMNS = (
    ("actual_close", sa.Float()),
    ("abs_error", sa.Float()),
    ("error_pct", sa.Float()),
    ("direction_correct", sa.Integer()),
    ("scored_at", sa.DateTime()),
)


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        op.add_column("predictions", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name, _column_type in reversed(_COLUMNS):
        op.drop_column("predictions", name)
