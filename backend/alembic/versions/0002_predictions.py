"""Add the ``predictions`` table for next-session forecasts.

Revision ID: 0002_predictions
Revises: 0001_initial
Create Date: 2026-11-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_predictions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("target_session", sa.Date(), nullable=False),
        sa.Column("reference_close", sa.Float(), nullable=True),
        sa.Column("predicted_close", sa.Float(), nullable=False),
        sa.Column("predicted_return", sa.Float(), nullable=True),
        sa.Column("horizon", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_layer", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_symbol", "predictions", ["symbol"])
    op.create_index("ix_predictions_model_name", "predictions", ["model_name"])
    op.create_index("ix_predictions_target_session", "predictions", ["target_session"])

    # One forecast per (symbol, model, target session). The EOD batch may
    # run more than once for the same session, and the upsert in
    # `PredictionRepository.upsert` relies on this constraint to keep the
    # table to a single row per target.
    op.create_unique_constraint(
        "uq_predictions_symbol_model_session",
        "predictions",
        ["symbol", "model_name", "target_session"],
    )


def downgrade() -> None:
    op.drop_table("predictions")
