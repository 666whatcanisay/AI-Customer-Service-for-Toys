"""create C-T02B isolated test catalog tables

Revision ID: 0002_ct02b_test_catalog
Revises: 0001_ct02_ingestion
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_ct02b_test_catalog"
down_revision = "0001_ct02_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_knowledge_packages",
        sa.Column("package_id", sa.String(96), primary_key=True),
        sa.Column("package_name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("response_mode", sa.String(32), nullable=False),
        sa.Column("test_data_mode", sa.Boolean(), nullable=False),
        sa.Column("production_usable", sa.Boolean(), nullable=False),
        sa.Column("allow_auto_send", sa.Boolean(), nullable=False),
        sa.Column("import_status", sa.String(40), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("zip_sha256", sa.String(64), nullable=False),
        sa.Column("counts_json", sa.Text(), nullable=False),
        sa.Column("imported_by", sa.String(128), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_test_knowledge_packages_tenant_id", "test_knowledge_packages", ["tenant_id"])
    op.create_index("ix_test_knowledge_packages_store_code", "test_knowledge_packages", ["store_code"])
    op.create_index("ix_test_knowledge_packages_zip_sha256", "test_knowledge_packages", ["zip_sha256"])

    op.create_table(
        "test_catalog_stores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("store_name", sa.String(255), nullable=False),
        sa.Column("trial_enabled", sa.Boolean(), nullable=False),
        sa.Column("knowledge_scope", sa.String(64), nullable=False),
        sa.Column("response_mode", sa.String(32), nullable=False),
        sa.Column("allow_auto_send", sa.Boolean(), nullable=False),
        sa.Column("test_data_mode", sa.Boolean(), nullable=False),
        sa.Column("production_usable", sa.Boolean(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("package_id", "store_code", name="uq_test_store_package_code"),
    )
    op.create_index("ix_test_catalog_stores_package_id", "test_catalog_stores", ["package_id"])
    op.create_index("ix_test_catalog_stores_tenant_id", "test_catalog_stores", ["tenant_id"])
    op.create_index("ix_test_catalog_stores_store_code", "test_catalog_stores", ["store_code"])

    op.create_table(
        "test_catalog_products",
        sa.Column("product_id", sa.String(96), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_name_official", sa.String(255), nullable=False),
        sa.Column("product_name_display", sa.String(255), nullable=False),
        sa.Column("sales_status", sa.String(32), nullable=False),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column("safety_summary", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(40), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_catalog_products_package_id", "test_catalog_products", ["package_id"])
    op.create_index("ix_test_catalog_products_tenant_id", "test_catalog_products", ["tenant_id"])
    op.create_index("ix_test_catalog_products_store_code", "test_catalog_products", ["store_code"])

    op.create_table(
        "test_catalog_skus",
        sa.Column("sku_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(96), sa.ForeignKey("test_catalog_products.product_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_code", sa.String(128), nullable=False),
        sa.Column("sku_name_official", sa.String(255), nullable=False),
        sa.Column("sku_name_display", sa.String(255), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("canonical_sku_id", sa.String(128), nullable=True),
        sa.Column("reference_sku_id", sa.String(128), nullable=True),
        sa.Column("component_sku_refs_json", sa.Text(), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_catalog_skus_package_id", "test_catalog_skus", ["package_id"])
    op.create_index("ix_test_catalog_skus_product_id", "test_catalog_skus", ["product_id"])

    op.create_table(
        "test_source_evidence",
        sa.Column("source_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("relative_path", sa.String(500), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_source_evidence_package_id", "test_source_evidence", ["package_id"])
    op.create_index("ix_test_source_evidence_product_id", "test_source_evidence", ["product_id"])
    op.create_index("ix_test_source_evidence_sku_id", "test_source_evidence", ["sku_id"])

    op.create_table(
        "test_faqs",
        sa.Column("faq_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("canonical_question", sa.Text(), nullable=False),
        sa.Column("recommended_reply", sa.Text(), nullable=False),
        sa.Column("answer_action", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_faqs_package_id", "test_faqs", ["package_id"])
    op.create_index("ix_test_faqs_tenant_id", "test_faqs", ["tenant_id"])
    op.create_index("ix_test_faqs_store_code", "test_faqs", ["store_code"])

    op.create_table(
        "test_safety_rules",
        sa.Column("rule_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("scenario", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_safety_rules_package_id", "test_safety_rules", ["package_id"])
    op.create_index("ix_test_safety_rules_tenant_id", "test_safety_rules", ["tenant_id"])
    op.create_index("ix_test_safety_rules_store_code", "test_safety_rules", ["store_code"])

    op.create_table(
        "test_evaluation_cases",
        sa.Column("case_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_evaluation_cases_package_id", "test_evaluation_cases", ["package_id"])
    op.create_index("ix_test_evaluation_cases_store_code", "test_evaluation_cases", ["store_code"])

    op.create_table(
        "test_conflict_records",
        sa.Column("issue_id", sa.String(128), primary_key=True),
        sa.Column("package_id", sa.String(96), sa.ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("field_name", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(64), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_test_conflict_records_package_id", "test_conflict_records", ["package_id"])


def downgrade() -> None:
    op.drop_table("test_conflict_records")
    op.drop_table("test_evaluation_cases")
    op.drop_table("test_safety_rules")
    op.drop_table("test_faqs")
    op.drop_table("test_source_evidence")
    op.drop_table("test_catalog_skus")
    op.drop_table("test_catalog_products")
    op.drop_table("test_catalog_stores")
    op.drop_table("test_knowledge_packages")
