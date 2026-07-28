"""add controlled knowledge material and quality assessment lifecycle

Revision ID: 0007_target_mode_v2_knowledge_quality_loop
Revises: 0006_mvp_plus_02_ai_feedback_idempotency
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_target_mode_v2_knowledge_quality_loop"
down_revision = "0006_mvp_plus_02_ai_feedback_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_materials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("material_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("material_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("original_filename", sa.String(256), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("redaction_version", sa.String(64), nullable=False),
        sa.Column("recognition_summary", sa.JSON(), nullable=False),
        sa.Column("analysis_text", sa.Text(), nullable=False),
        sa.Column("raw_storage_path", sa.String(1024), nullable=False),
        sa.Column("material_status", sa.String(32), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("material_id", "revision", name="uq_knowledge_material_revision"),
    )
    op.create_index(
        "ix_knowledge_material_scope_status",
        "knowledge_materials",
        ["store_code", "product_id", "sku_id", "material_status"],
    )
    op.create_index("ix_knowledge_material_id_revision", "knowledge_materials", ["material_id", "revision"])
    op.create_table(
        "knowledge_material_upload_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_method", sa.String(8), nullable=False),
        sa.Column("request_path", sa.String(128), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(80), nullable=False),
        sa.Column("material_record_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_record_id"], ["knowledge_materials.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "request_method", "request_path", "submitted_by", "idempotency_key",
            name="uq_knowledge_material_upload_idempotency_scope",
        ),
    )
    op.create_table(
        "knowledge_quality_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(64), nullable=False),
        sa.Column("material_record_id", sa.String(36), nullable=False),
        sa.Column("material_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("analysis_run_id", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(160), nullable=False),
        sa.Column("overall_status", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_record_id"], ["knowledge_materials.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_id", name="uq_knowledge_quality_assessment_id"),
        sa.UniqueConstraint("material_record_id", name="uq_knowledge_quality_assessment_material_record"),
        sa.UniqueConstraint("analysis_run_id", name="uq_knowledge_quality_assessment_run"),
    )
    op.create_index(
        "ix_knowledge_quality_assessment_material",
        "knowledge_quality_assessments",
        ["material_id", "revision"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_quality_assessment_material", table_name="knowledge_quality_assessments")
    op.drop_table("knowledge_quality_assessments")
    op.drop_table("knowledge_material_upload_receipts")
    op.drop_index("ix_knowledge_material_id_revision", table_name="knowledge_materials")
    op.drop_index("ix_knowledge_material_scope_status", table_name="knowledge_materials")
    op.drop_table("knowledge_materials")
