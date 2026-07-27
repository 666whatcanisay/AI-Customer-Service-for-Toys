"""add C-internal trial store setup and target-bound import metadata

Revision ID: 0008_pilot_store_center
Revises: 0007_p0_customer_efficiency_events
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_pilot_store_center"
down_revision = "0007_p0_customer_efficiency_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pilot_stores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("store_name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_code", name="uq_pilot_stores_store_code"),
    )
    op.create_index("ix_pilot_stores_store_code", "pilot_stores", ["store_code"], unique=False)
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.add_column(sa.Column("target_store_code", sa.String(96), nullable=True))
        batch_op.create_index("ix_import_batches_target_store_code", ["target_store_code"])


def downgrade() -> None:
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.drop_index("ix_import_batches_target_store_code")
        batch_op.drop_column("target_store_code")
    op.drop_index("ix_pilot_stores_store_code", table_name="pilot_stores")
    op.drop_table("pilot_stores")
