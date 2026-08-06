"""add minimized Customer Desktop Workflow audit

Revision ID: 0015_customer_desktop_workflow_v1
Revises: 0014_store_context_resolver_v1
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_customer_desktop_workflow_v1"
down_revision = "0014_store_context_resolver_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "desktop_workflow_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("previous_state", sa.String(160), nullable=True),
        sa.Column("current_state", sa.String(160), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_desktop_workflow_audit_events_actor_user_id", "desktop_workflow_audit_events", ["actor_user_id"])
    op.create_index("ix_desktop_workflow_audit_user_time", "desktop_workflow_audit_events", ["actor_user_id", "occurred_at"])
    op.create_index("ix_desktop_workflow_audit_agent_time", "desktop_workflow_audit_events", ["agent_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("desktop_workflow_audit_events")
