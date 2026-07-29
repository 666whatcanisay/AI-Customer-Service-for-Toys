"""add minimum customer feedback loop persistence

Revision ID: 0008_customer_feedback_loop_v1
Revises: 0007_target_mode_v2_knowledge_quality_loop
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_customer_feedback_loop_v1"
down_revision = "0007_target_mode_v2_knowledge_quality_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_interaction_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("store_name", sa.String(256), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(256), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("sku_name", sa.String(256), nullable=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("question_summary", sa.Text(), nullable=False),
        sa.Column("ai_answer_summary", sa.Text(), nullable=False),
        sa.Column("final_answer_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("redaction_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_ai_interaction_event_event_id"),
        sa.UniqueConstraint(
            "created_by", "idempotency_key",
            name="uq_ai_interaction_event_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_ai_interaction_event_scope",
        "ai_interaction_events",
        ["store_code", "product_id", "sku_id", "action_type", "occurred_at"],
    )
    op.create_index(
        "ix_ai_interaction_event_interaction",
        "ai_interaction_events",
        ["interaction_id", "occurred_at"],
    )
    op.create_table(
        "ai_problems",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_id", sa.String(64), nullable=False),
        sa.Column("aggregation_fingerprint", sa.String(80), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("store_name", sa.String(256), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(256), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("sku_name", sa.String(256), nullable=True),
        sa.Column("question_summary", sa.Text(), nullable=False),
        sa.Column("ai_answer_summary", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_changed_by", sa.String(128), nullable=True),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("problem_id", name="uq_ai_problem_problem_id"),
        sa.UniqueConstraint(
            "aggregation_fingerprint", name="uq_ai_problem_aggregation_fingerprint"
        ),
    )
    op.create_index(
        "ix_ai_problem_operations",
        "ai_problems",
        ["status", "issue_type", "store_code", "product_id", "sku_id", "last_seen_at"],
    )
    op.create_table(
        "ai_problem_occurrences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_record_id", sa.String(36), nullable=False),
        sa.Column("event_record_id", sa.String(36), nullable=False),
        sa.Column("feedback_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_record_id"], ["ai_problems.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["event_record_id"], ["ai_interaction_events.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("event_record_id", name="uq_ai_problem_occurrence_event"),
    )
    op.create_index(
        "ix_ai_problem_occurrence_problem",
        "ai_problem_occurrences",
        ["problem_record_id", "created_at"],
    )
    op.create_table(
        "knowledge_optimization_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("problem_record_id", sa.String(36), nullable=False),
        sa.Column("source_problem_id", sa.String(64), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("missing_topic", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("verification_result", sa.String(32), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_record_id"], ["ai_problems.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("task_id", name="uq_knowledge_optimization_task_id"),
        sa.UniqueConstraint(
            "problem_record_id", name="uq_knowledge_optimization_task_problem"
        ),
    )
    op.create_index(
        "ix_knowledge_optimization_task_status",
        "knowledge_optimization_tasks",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_optimization_task_status",
        table_name="knowledge_optimization_tasks",
    )
    op.drop_table("knowledge_optimization_tasks")
    op.drop_index("ix_ai_problem_occurrence_problem", table_name="ai_problem_occurrences")
    op.drop_table("ai_problem_occurrences")
    op.drop_index("ix_ai_problem_operations", table_name="ai_problems")
    op.drop_table("ai_problems")
    op.drop_index(
        "ix_ai_interaction_event_interaction", table_name="ai_interaction_events"
    )
    op.drop_index("ix_ai_interaction_event_scope", table_name="ai_interaction_events")
    op.drop_table("ai_interaction_events")
