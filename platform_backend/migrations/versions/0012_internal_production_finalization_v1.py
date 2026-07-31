"""formalize retained initialization-source labels without changing catalog state

Revision ID: 0012_internal_production_finalization_v1
Revises: 0011_product_knowledge_publishing_v1
Create Date: 2026-07-31
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0012_internal_production_finalization_v1"
down_revision = "0011_product_knowledge_publishing_v1"
branch_labels = None
depends_on = None


MIGRATION_VERSION = "internal-production-finalization-v1"
ORIGINAL_SOURCE = "TEST"
FORMAL_SOURCE = "INITIAL_IMPORT"
RETAINED_IMPORT_STATUS = "IMPORTED_TEST_ONLY"
RETAINED_SCHEMA_VERSION = "0.3.1-test"


def upgrade() -> None:
    op.create_table(
        "catalog_source_formalizations",
        sa.Column("store_ref", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.String(96), nullable=False),
        sa.Column("original_data_source", sa.String(16), nullable=False),
        sa.Column("formal_data_source", sa.String(16), nullable=False),
        sa.Column("original_import_status", sa.String(40), nullable=False),
        sa.Column("original_schema_version", sa.String(32), nullable=False),
        sa.Column("migration_version", sa.String(96), nullable=False),
        sa.Column("formalized_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_catalog_source_formalizations_package_id",
        "catalog_source_formalizations",
        ["package_id"],
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    packages = sa.Table(
        "test_knowledge_packages",
        metadata,
        sa.Column("package_id", sa.String(96)),
        sa.Column("import_status", sa.String(40)),
        sa.Column("schema_version", sa.String(32)),
    )
    stores = sa.Table(
        "test_catalog_stores",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("package_id", sa.String(96)),
        sa.Column("data_source", sa.String(16)),
    )
    formalizations = sa.Table(
        "catalog_source_formalizations",
        metadata,
        sa.Column("store_ref", sa.Integer()),
        sa.Column("package_id", sa.String(96)),
        sa.Column("original_data_source", sa.String(16)),
        sa.Column("formal_data_source", sa.String(16)),
        sa.Column("original_import_status", sa.String(40)),
        sa.Column("original_schema_version", sa.String(32)),
        sa.Column("migration_version", sa.String(96)),
        sa.Column("formalized_at", sa.DateTime(timezone=True)),
    )

    eligible = list(
        bind.execute(
            sa.select(
                stores.c.id,
                stores.c.package_id,
                stores.c.data_source,
                packages.c.import_status,
                packages.c.schema_version,
            )
            .select_from(
                stores.join(packages, stores.c.package_id == packages.c.package_id)
            )
            .where(
                stores.c.data_source == ORIGINAL_SOURCE,
                packages.c.import_status == RETAINED_IMPORT_STATUS,
                packages.c.schema_version == RETAINED_SCHEMA_VERSION,
            )
            .order_by(stores.c.id)
        ).mappings()
    )

    now = datetime.now(timezone.utc)
    for row in eligible:
        bind.execute(
            formalizations.insert().values(
                store_ref=row["id"],
                package_id=row["package_id"],
                original_data_source=row["data_source"],
                formal_data_source=FORMAL_SOURCE,
                original_import_status=row["import_status"],
                original_schema_version=row["schema_version"],
                migration_version=MIGRATION_VERSION,
                formalized_at=now,
            )
        )
        bind.execute(
            stores.update()
            .where(stores.c.id == row["id"])
            .values(data_source=FORMAL_SOURCE)
        )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    stores = sa.Table(
        "test_catalog_stores",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("data_source", sa.String(16)),
    )
    formalizations = sa.Table(
        "catalog_source_formalizations",
        metadata,
        sa.Column("store_ref", sa.Integer()),
        sa.Column("original_data_source", sa.String(16)),
        sa.Column("formal_data_source", sa.String(16)),
        sa.Column("migration_version", sa.String(96)),
    )
    rows = bind.execute(
        sa.select(
            formalizations.c.store_ref,
            formalizations.c.original_data_source,
            formalizations.c.formal_data_source,
        ).where(formalizations.c.migration_version == MIGRATION_VERSION)
    ).mappings()
    for row in rows:
        bind.execute(
            stores.update()
            .where(
                stores.c.id == row["store_ref"],
                stores.c.data_source == row["formal_data_source"],
            )
            .values(data_source=row["original_data_source"])
        )

    op.drop_index(
        "ix_catalog_source_formalizations_package_id",
        table_name="catalog_source_formalizations",
    )
    op.drop_table("catalog_source_formalizations")
