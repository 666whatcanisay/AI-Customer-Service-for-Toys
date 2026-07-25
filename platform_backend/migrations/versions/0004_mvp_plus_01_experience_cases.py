"""add MVP-PLUS-01 customer experience case center

Revision ID: 0004_mvp_plus_01_experience_cases
Revises: 0003_ct05_customer_suggestions
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_mvp_plus_01_experience_cases"
down_revision = "0003_ct05_customer_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_experience_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("ai_answer", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=False),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("export_revision", sa.String(160), nullable=True),
        sa.Column("content_hash", sa.String(80), nullable=True),
        sa.Column("redaction_version", sa.String(64), nullable=False),
        sa.Column("evaluation_status", sa.String(24), nullable=False),
        sa.Column("latest_evaluation_run_id", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "revision", name="uq_customer_experience_case_revision"),
        sa.UniqueConstraint("export_revision"),
    )
    op.create_index(
        "ix_customer_experience_cases_admin_filters",
        "customer_experience_cases",
        ["review_status", "store_code", "product_id", "sku_id", "created_by"],
    )
    op.create_index(
        "ix_customer_experience_cases_creator",
        "customer_experience_cases",
        ["created_by", "created_at"],
    )

    op.create_table(
        "customer_experience_case_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_record_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("export_revision", sa.String(160), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("ai_answer", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("redaction_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_record_id"], ["customer_experience_cases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("case_record_id", name="uq_customer_experience_case_export_record"),
        sa.UniqueConstraint("export_revision", name="uq_customer_experience_case_export_revision"),
    )
    op.create_index(
        "ix_customer_experience_case_exports_cursor",
        "customer_experience_case_exports",
        ["case_id", "revision"],
    )

    op.create_table(
        "customer_experience_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_record_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("export_revision", sa.String(160), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("evaluation_run_id", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(160), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("suggestions_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_record_id"], ["customer_experience_cases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "case_id", "revision", "export_revision", "evaluation_run_id",
            name="uq_customer_experience_evaluation_run",
        ),
    )
    op.create_index(
        "ix_customer_experience_evaluations_case",
        "customer_experience_evaluations",
        ["case_id", "revision", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_experience_evaluations_case", table_name="customer_experience_evaluations")
    op.drop_table("customer_experience_evaluations")
    op.drop_index("ix_customer_experience_case_exports_cursor", table_name="customer_experience_case_exports")
    op.drop_table("customer_experience_case_exports")
    op.drop_index("ix_customer_experience_cases_creator", table_name="customer_experience_cases")
    op.drop_index("ix_customer_experience_cases_admin_filters", table_name="customer_experience_cases")
    op.drop_table("customer_experience_cases")
