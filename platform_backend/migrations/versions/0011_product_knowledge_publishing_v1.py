"""add product knowledge publishing lifecycle

Revision ID: 0011_product_knowledge_publishing_v1
Revises: 0010_customer_available_catalog_v1
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_product_knowledge_publishing_v1"
down_revision = "0010_customer_available_catalog_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_knowledge_publications",
        sa.Column(
            "product_id",
            sa.String(96),
            sa.ForeignKey("test_catalog_products.product_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_fingerprint", sa.String(64)),
        sa.Column("indexed_fingerprint", sa.String(64)),
        sa.Column("active_collection", sa.String(128)),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("publication_receipt_id", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_product_knowledge_publications_status",
        "product_knowledge_publications",
        ["status"],
    )
    op.create_table(
        "product_knowledge_publication_receipts",
        sa.Column("publication_receipt_id", sa.String(64), primary_key=True),
        sa.Column(
            "product_id",
            sa.String(96),
            sa.ForeignKey("test_catalog_products.product_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("knowledge_fingerprint", sa.String(64), nullable=False),
        sa.Column("active_collection", sa.String(128), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_product_knowledge_publication_receipts_product_time",
        "product_knowledge_publication_receipts",
        ["product_id", "created_at"],
    )
    op.create_table(
        "product_knowledge_publication_idempotency",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("product_knowledge_publication_idempotency")
    op.drop_index(
        "ix_product_knowledge_publication_receipts_product_time",
        table_name="product_knowledge_publication_receipts",
    )
    op.drop_table("product_knowledge_publication_receipts")
    op.drop_index(
        "ix_product_knowledge_publications_status",
        table_name="product_knowledge_publications",
    )
    op.drop_table("product_knowledge_publications")
