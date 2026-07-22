"""create C-T02 review-only ingestion tables

Revision ID: 0001_ct02_ingestion
Revises:
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_ct02_ingestion"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("import_type", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_import_batches_tenant_id", "import_batches", ["tenant_id"])
    op.create_index("ix_import_batches_file_sha256", "import_batches", ["file_sha256"])
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
        sa.Column("normalized_data_json", sa.Text(), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("error_codes_json", sa.Text(), nullable=False),
        sa.Column("warning_codes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "source_row_number", name="uq_import_row_batch_source"),
    )
    op.create_index("ix_import_rows_batch_id", "import_rows", ["batch_id"])
    op.create_index("ix_import_rows_row_hash", "import_rows", ["row_hash"])
    op.create_index(
        "ix_import_rows_batch_status", "import_rows", ["batch_id", "validation_status"]
    )
    op.create_table(
        "staged_product_skus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(128), nullable=False),
        sa.Column("product_code", sa.String(128), nullable=True),
        sa.Column("platform_product_id", sa.String(128), nullable=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("sku_code", sa.String(128), nullable=True),
        sa.Column("platform_sku_id", sa.String(128), nullable=True),
        sa.Column("sku_name", sa.String(255), nullable=False),
        sa.Column("specifications", sa.Text(), nullable=True),
        sa.Column("applicable_age_min", sa.Integer(), nullable=True),
        sa.Column("applicable_age_max", sa.Integer(), nullable=True),
        sa.Column("material", sa.String(255), nullable=True),
        sa.Column("package_contents", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("external_system", sa.String(32), nullable=False),
        sa.Column("external_product_id", sa.String(128), nullable=True),
        sa.Column("external_sku_id", sa.String(128), nullable=True),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "row_hash", name="uq_staged_batch_row_hash"),
    )
    op.create_index("ix_staged_product_skus_tenant_id", "staged_product_skus", ["tenant_id"])
    op.create_index("ix_staged_product_skus_batch_id", "staged_product_skus", ["batch_id"])
    op.create_index("ix_staged_product_skus_row_hash", "staged_product_skus", ["row_hash"])
    op.create_index(
        "ix_staged_product_identity",
        "staged_product_skus",
        ["tenant_id", "platform", "store_code", "product_code", "sku_code"],
    )


def downgrade() -> None:
    op.drop_table("staged_product_skus")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
