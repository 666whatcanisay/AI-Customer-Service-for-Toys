"""add content-free trial governance audit events

Revision ID: 0009_pilot_trial_governance
Revises: 0008_pilot_store_center
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_pilot_trial_governance"
down_revision = "0008_pilot_store_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trial_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_trial_audit_events_occurred", "trial_audit_events", ["occurred_at", "action"], unique=False
    )
    op.create_index(
        "ix_trial_audit_events_actor", "trial_audit_events", ["actor_id", "occurred_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trial_audit_events_actor", table_name="trial_audit_events")
    op.drop_index("ix_trial_audit_events_occurred", table_name="trial_audit_events")
    op.drop_table("trial_audit_events")
