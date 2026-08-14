"""add isolated PDD reply-readiness question extensions and run ledger

Revision ID: 0023_reply_readiness_v1
Revises: 0022_reply_rule_source_evidence_v1
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_reply_readiness_v1"
down_revision = "0022_reply_rule_source_evidence_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_readiness_question_set_extensions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("extension_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=True),
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("change_reason", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("extension_id", "version", name="uq_reply_readiness_extension_version"),
    )
    op.create_index("ix_reply_readiness_extension_scope", "reply_readiness_question_set_extensions", ["scope_kind", "store_code", "product_id", "status"])
    op.create_table(
        "reply_readiness_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=False),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("question_set_fingerprint", sa.String(64), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.String(64), nullable=True),
        sa.Column("material_revision", sa.Integer(), nullable=True),
        sa.Column("material_content_hash", sa.String(80), nullable=True),
        sa.Column("reply_rule_snapshot_revision", sa.Integer(), nullable=False),
        sa.Column("reply_rule_snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("router_build_fingerprint", sa.String(64), nullable=False),
        sa.Column("sandbox_vector_identity", sa.String(255), nullable=False),
        sa.Column("test_data_mode", sa.Boolean(), nullable=False),
        sa.Column("production_usable", sa.Boolean(), nullable=False),
        sa.Column("allow_auto_send", sa.Boolean(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=True),
        sa.Column("failure_code", sa.String(96), nullable=True),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("requested_by", "idempotency_key", name="uq_reply_readiness_run_idempotency"),
    )
    op.create_index("ix_reply_readiness_runs_scope_time", "reply_readiness_runs", ["store_code", "product_id", "sku_id", "requested_at"])
    op.create_index("ix_reply_readiness_runs_status", "reply_readiness_runs", ["status", "requested_at"])


def downgrade() -> None:
    op.drop_index("ix_reply_readiness_runs_status", table_name="reply_readiness_runs")
    op.drop_index("ix_reply_readiness_runs_scope_time", table_name="reply_readiness_runs")
    op.drop_table("reply_readiness_runs")
    op.drop_index("ix_reply_readiness_extension_scope", table_name="reply_readiness_question_set_extensions")
    op.drop_table("reply_readiness_question_set_extensions")
