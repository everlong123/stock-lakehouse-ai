"""Record the target timestamp, input cutoff and model version per forecast."""

from alembic import op
import sqlalchemy as sa

revision = "0007_forecast_provenance"
down_revision = "0006_prediction_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("target_open_at", sa.DateTime(), nullable=True))
    op.add_column("predictions", sa.Column("input_data_end", sa.DateTime(), nullable=True))
    op.add_column("predictions", sa.Column("model_version", sa.String(64), nullable=True))


def downgrade() -> None:
    for column in ("model_version", "input_data_end", "target_open_at"):
        op.drop_column("predictions", column)
