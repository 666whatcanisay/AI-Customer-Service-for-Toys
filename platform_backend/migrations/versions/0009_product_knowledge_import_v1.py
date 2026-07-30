"""add review-gated product knowledge import

Revision ID: 0009_product_knowledge_import_v1
Revises: 0008_customer_feedback_loop_v1
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_product_knowledge_import_v1"
down_revision = "0008_customer_feedback_loop_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.add_column(sa.Column("store_ref", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("store_code_snapshot", sa.String(96), nullable=True))
        batch_op.add_column(sa.Column("store_name_snapshot", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("platform_snapshot", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("file_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("template_type", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("template_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("parser_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("request_fingerprint", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("template_evidence_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_storage_path", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint(
            "uq_import_batch_idempotency_scope",
            ["import_type", "created_by", "idempotency_key"],
        )
        batch_op.create_index(
            "ix_import_batches_catalog_scope",
            ["store_ref", "template_type", "status"],
        )
        batch_op.create_index(
            "ix_import_batches_catalog_file",
            ["store_ref", "template_type", "file_sha256"],
        )
        batch_op.create_index("ix_import_batches_created_at", ["created_at"])

    with op.batch_alter_table("import_rows") as batch_op:
        batch_op.add_column(sa.Column("sheet_name", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("product_identity_key", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("product_match_type", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("target_product_id", sa.String(96), nullable=True))
        batch_op.create_index(
            "ix_import_rows_batch_product_identity",
            ["batch_id", "product_identity_key"],
        )

    op.create_table(
        "import_change_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row_ids_json", sa.Text(), nullable=False),
        sa.Column("product_identity_key", sa.String(255), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("target_product_id", sa.String(96), nullable=True),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("base_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("old_snapshot_json", sa.Text(), nullable=False),
        sa.Column("incoming_snapshot_json", sa.Text(), nullable=False),
        sa.Column("merged_snapshot_json", sa.Text(), nullable=False),
        sa.Column("error_codes_json", sa.Text(), nullable=False),
        sa.Column("warning_codes_json", sa.Text(), nullable=False),
        sa.Column("applied_product_id", sa.String(96), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "batch_id",
            "product_identity_key",
            name="uq_import_change_set_batch_identity",
        ),
    )
    op.create_index("ix_import_change_sets_batch_id", "import_change_sets", ["batch_id"])
    op.create_index(
        "ix_import_change_sets_batch_status",
        "import_change_sets",
        ["batch_id", "status"],
    )
    op.create_index(
        "ix_import_change_sets_target_product",
        "import_change_sets",
        ["target_product_id"],
    )

    op.create_table(
        "import_field_changes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "change_set_id",
            sa.String(36),
            sa.ForeignKey("import_change_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(128), nullable=False),
        sa.Column("field_label", sa.String(128), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("old_value_json", sa.Text(), nullable=False),
        sa.Column("incoming_value_json", sa.Text(), nullable=False),
        sa.Column("merged_value_json", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "change_set_id",
            "field_key",
            name="uq_import_field_change_set_field",
        ),
    )
    op.create_index(
        "ix_import_field_changes_change_set_id",
        "import_field_changes",
        ["change_set_id"],
    )
    op.create_index(
        "ix_import_field_changes_set_type",
        "import_field_changes",
        ["change_set_id", "change_type"],
    )

    op.create_table(
        "import_review_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("import_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "change_set_id",
            sa.String(36),
            sa.ForeignKey("import_change_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("expected_base_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("observed_base_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("expected_change_set_version", sa.Integer(), nullable=False),
        sa.Column("applied_product_id", sa.String(96), nullable=True),
        sa.Column("applied_field_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("before_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("after_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "change_set_id",
            "reviewed_by",
            "idempotency_key",
            name="uq_import_review_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_import_review_records_batch_id", "import_review_records", ["batch_id"]
    )
    op.create_index(
        "ix_import_review_records_change_set_id",
        "import_review_records",
        ["change_set_id"],
    )
    op.create_index(
        "ix_import_review_records_batch",
        "import_review_records",
        ["batch_id", "created_at"],
    )
    op.create_index(
        "ix_import_review_records_change_set",
        "import_review_records",
        ["change_set_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_review_records_change_set", table_name="import_review_records")
    op.drop_index("ix_import_review_records_batch", table_name="import_review_records")
    op.drop_index("ix_import_review_records_change_set_id", table_name="import_review_records")
    op.drop_index("ix_import_review_records_batch_id", table_name="import_review_records")
    op.drop_table("import_review_records")

    op.drop_index("ix_import_field_changes_set_type", table_name="import_field_changes")
    op.drop_index("ix_import_field_changes_change_set_id", table_name="import_field_changes")
    op.drop_table("import_field_changes")

    op.drop_index("ix_import_change_sets_target_product", table_name="import_change_sets")
    op.drop_index("ix_import_change_sets_batch_status", table_name="import_change_sets")
    op.drop_index("ix_import_change_sets_batch_id", table_name="import_change_sets")
    op.drop_table("import_change_sets")

    with op.batch_alter_table("import_rows") as batch_op:
        batch_op.drop_index("ix_import_rows_batch_product_identity")
        batch_op.drop_column("target_product_id")
        batch_op.drop_column("product_match_type")
        batch_op.drop_column("product_identity_key")
        batch_op.drop_column("sheet_name")

    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.drop_index("ix_import_batches_created_at")
        batch_op.drop_index("ix_import_batches_catalog_file")
        batch_op.drop_index("ix_import_batches_catalog_scope")
        batch_op.drop_constraint("uq_import_batch_idempotency_scope", type_="unique")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("version")
        batch_op.drop_column("source_storage_path")
        batch_op.drop_column("template_evidence_json")
        batch_op.drop_column("request_fingerprint")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("parser_version")
        batch_op.drop_column("template_version")
        batch_op.drop_column("template_type")
        batch_op.drop_column("file_size_bytes")
        batch_op.drop_column("platform_snapshot")
        batch_op.drop_column("store_name_snapshot")
        batch_op.drop_column("store_code_snapshot")
        batch_op.drop_column("store_ref")
