"""add customer efficiency aggregate-only events

Revision ID: 0007_p0_customer_efficiency_events
Revises: 0006_mvp_plus_02_ai_feedback_idempotency
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_p0_customer_efficiency_events"
down_revision = "0006_mvp_plus_02_ai_feedback_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_efficiency_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_customer_efficiency_event_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_customer_efficiency_event_idempotency_key"),
    )
    op.create_index(
        "ix_customer_efficiency_event_window",
        "customer_efficiency_events",
        ["occurred_at", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customer_efficiency_event_window", table_name="customer_efficiency_events")
    op.drop_table("customer_efficiency_events")
