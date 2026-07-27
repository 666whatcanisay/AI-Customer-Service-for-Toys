"""add MVP-PLUS-02 AI response feedback center

Revision ID: 0005_mvp_plus_02_ai_response_feedback
Revises: 0004_mvp_plus_01_experience_cases
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_mvp_plus_02_ai_response_feedback"
down_revision = "0004_mvp_plus_01_experience_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_response_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feedback_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("ai_answer", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("feedback_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("analysis_status", sa.String(16), nullable=False),
        sa.Column("confirmed_by", sa.String(128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_reason", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(80), nullable=True),
        sa.Column("redaction_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("feedback_id", name="uq_ai_response_feedback_feedback_id"),
    )
    op.create_index(
        "ix_ai_response_feedback_admin_filters",
        "ai_response_feedback",
        ["status", "feedback_type", "store_code", "product_id", "sku_id", "created_by"],
    )
    op.create_index(
        "ix_ai_response_feedback_creator", "ai_response_feedback", ["created_by", "created_at"]
    )
    op.create_index(
        "ix_ai_response_feedback_export", "ai_response_feedback", ["status", "feedback_id"]
    )

    op.create_table(
        "ai_response_feedback_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feedback_record_id", sa.String(36), nullable=False),
        sa.Column("feedback_id", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("analysis_run_id", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(160), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=False),
        sa.Column("suggestions_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feedback_record_id"], ["ai_response_feedback.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("feedback_record_id", name="uq_ai_response_feedback_analysis_record"),
        sa.UniqueConstraint("analysis_run_id", name="uq_ai_response_feedback_analysis_run"),
    )
    op.create_index(
        "ix_ai_response_feedback_analysis_feedback",
        "ai_response_feedback_analyses",
        ["feedback_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_response_feedback_analysis_feedback", table_name="ai_response_feedback_analyses"
    )
    op.drop_table("ai_response_feedback_analyses")
    op.drop_index("ix_ai_response_feedback_export", table_name="ai_response_feedback")
    op.drop_index("ix_ai_response_feedback_creator", table_name="ai_response_feedback")
    op.drop_index("ix_ai_response_feedback_admin_filters", table_name="ai_response_feedback")
    op.drop_table("ai_response_feedback")
