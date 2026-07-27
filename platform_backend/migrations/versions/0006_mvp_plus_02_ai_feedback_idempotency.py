"""add AI response feedback B submission idempotency receipts

Revision ID: 0006_mvp_plus_02_ai_feedback_idempotency
Revises: 0005_mvp_plus_02_ai_response_feedback
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_mvp_plus_02_ai_feedback_idempotency"
down_revision = "0005_mvp_plus_02_ai_response_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_response_feedback_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_method", sa.String(8), nullable=False),
        sa.Column("request_path", sa.String(128), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(80), nullable=False),
        sa.Column("feedback_record_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feedback_record_id"], ["ai_response_feedback.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "request_method",
            "request_path",
            "created_by",
            "idempotency_key",
            name="uq_ai_response_feedback_idempotency_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_response_feedback_idempotency")
