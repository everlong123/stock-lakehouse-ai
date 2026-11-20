"""Retain forecast versions instead of losing the previous publication."""

from alembic import op
import sqlalchemy as sa

revision = "0006_prediction_revisions"
down_revision = "0005_prediction_staleness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("target_session", sa.Date(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_prediction_revisions_prediction_id", "prediction_revisions", ["prediction_id"])


def downgrade() -> None:
    op.drop_table("prediction_revisions")
