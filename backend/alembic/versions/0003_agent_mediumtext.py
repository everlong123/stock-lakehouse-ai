"""Widen the agent conversation text columns to MEDIUMTEXT.

Revision ID: 0003_agent_mediumtext
Revises: 0002_predictions
Create Date: 2026-11-12

WHY
---
``agent_conversations.tool_result`` stores the full JSON of every tool
call. A walk-forward run over one symbol produces ~70 KB of windows, and
MySQL's ``TEXT`` type caps a column at 65,535 BYTES - so the INSERT failed
with

    (pymysql.err.DataError) (1406, "Data too long for column 'tool_result'")

The request then returned HTTP 500 and, because the failure happened
inside the dependency that commits the session, the whole DB session was
left in a pending-rollback state.

``MEDIUMTEXT`` holds 16 MB, which is comfortably above any tool payload
the agent can produce, and the column is still not a blob - the point of
this table is a readable chat transcript, not a data lake.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003_agent_mediumtext"
down_revision = "0002_predictions"
branch_labels = None
depends_on = None

# Every text column of the table can receive a long tool payload: the
# assistant message quotes the tool result, and `tool_arguments` carries
# the full argument object.
_COLUMNS = ("user_message", "assistant_message", "tool_arguments", "tool_result")


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "agent_conversations",
            column,
            existing_type=sa.Text(),
            type_=mysql.MEDIUMTEXT(),
            existing_nullable=(column != "user_message"),
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column(
            "agent_conversations",
            column,
            existing_type=mysql.MEDIUMTEXT(),
            type_=sa.Text(),
            existing_nullable=(column != "user_message"),
        )
