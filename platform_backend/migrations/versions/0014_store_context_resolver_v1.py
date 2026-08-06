"""add minimized conversation Store/Product/SKU resolution audit

Revision ID: 0014_store_context_resolver_v1
Revises: 0013_user_management_v1
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_store_context_resolver_v1"
down_revision = "0013_user_management_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_context_resolutions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("conversation_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("product_candidate_ids_json", sa.Text(), nullable=False),
        sa.Column("sku_candidate_ids_json", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_context_resolutions_user_id", "conversation_context_resolutions", ["user_id"])
    op.create_index("ix_context_resolutions_user_time", "conversation_context_resolutions", ["user_id", "created_at"])
    op.create_index("ix_context_resolutions_store_status", "conversation_context_resolutions", ["store_id", "status"])


def downgrade() -> None:
    op.drop_table("conversation_context_resolutions")
