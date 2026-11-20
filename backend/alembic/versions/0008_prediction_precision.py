"""Preserve double precision prices and errors in the verification ledger."""

from alembic import op
import sqlalchemy as sa

revision = "0008_prediction_precision"
down_revision = "0007_forecast_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("reference_close", "predicted_close", "predicted_return", "actual_close", "abs_error", "error_pct"):
        op.alter_column("predictions", column, existing_type=sa.Float(), type_=sa.Double(), existing_nullable=column != "predicted_close")


def downgrade() -> None:
    for column in ("reference_close", "predicted_close", "predicted_return", "actual_close", "abs_error", "error_pct"):
        op.alter_column("predictions", column, existing_type=sa.Double(), type_=sa.Float(), existing_nullable=column != "predicted_close")
