"""add C-owned customer available catalog projection state

Revision ID: 0010_customer_available_catalog_v1
Revises: 0009_product_knowledge_import_v1
Create Date: 2026-07-31
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0010_customer_available_catalog_v1"
down_revision = "0009_product_knowledge_import_v1"
branch_labels = None
depends_on = None

POLICY_VERSION = "legacy-compat-control-v1.1@1fccb41"
SOURCE_BASELINE = "1fccb41c0b9d17f193a2924f1cf12d9c2111a53f"


def _receipt(
    receipts: sa.Table,
    *,
    entity_type: str,
    entity_ref: str,
    data_source: str,
    status: str,
    now: datetime,
) -> dict[str, object]:
    return {
        "activation_receipt_id": f"ACT-{uuid4().hex}",
        "entity_type": entity_type,
        "entity_ref": entity_ref,
        "data_source": data_source,
        "previous_status": None,
        "customer_service_status": status,
        "activation_source": "LEGACY_INITIALIZATION",
        "confirmed_by": "SYSTEM_MIGRATION",
        "confirmation_note": f"Initialized by {POLICY_VERSION}",
        "confirmed_at": now,
    }


def upgrade() -> None:
    with op.batch_alter_table("test_catalog_stores") as batch_op:
        batch_op.add_column(sa.Column("data_source", sa.String(16), nullable=True))
        batch_op.add_column(
            sa.Column(
                "customer_service_status",
                sa.String(16),
                nullable=False,
                server_default="DISABLED",
            )
        )
        batch_op.add_column(
            sa.Column("customer_service_status_updated_at", sa.DateTime(timezone=True))
        )
        batch_op.add_column(
            sa.Column("customer_service_status_updated_by", sa.String(128))
        )
        batch_op.create_index(
            "ix_catalog_stores_customer_service_projection",
            ["customer_service_status", "data_source", "store_code"],
        )

    with op.batch_alter_table("test_catalog_products") as batch_op:
        batch_op.add_column(
            sa.Column(
                "customer_service_status",
                sa.String(16),
                nullable=False,
                server_default="DISABLED",
            )
        )
        batch_op.add_column(
            sa.Column("customer_service_status_updated_at", sa.DateTime(timezone=True))
        )
        batch_op.add_column(
            sa.Column("customer_service_status_updated_by", sa.String(128))
        )
        batch_op.create_index(
            "ix_catalog_products_customer_service_projection",
            ["store_code", "customer_service_status", "product_id"],
        )

    op.create_table(
        "catalog_activation_receipts",
        sa.Column("activation_receipt_id", sa.String(64), primary_key=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_ref", sa.String(128), nullable=False),
        sa.Column("data_source", sa.String(16), nullable=False),
        sa.Column("previous_status", sa.String(16)),
        sa.Column("customer_service_status", sa.String(16), nullable=False),
        sa.Column("activation_source", sa.String(32), nullable=False),
        sa.Column("confirmed_by", sa.String(128), nullable=False),
        sa.Column("confirmation_note", sa.String(500), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_catalog_activation_receipts_entity_time",
        "catalog_activation_receipts",
        ["entity_type", "entity_ref", "confirmed_at"],
    )
    op.create_table(
        "catalog_activation_idempotency",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "catalog_activation_initializations",
        sa.Column("policy_version", sa.String(96), primary_key=True),
        sa.Column("source_baseline", sa.String(64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=False),
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    packages = sa.Table(
        "test_knowledge_packages", metadata,
        sa.Column("package_id", sa.String),
        sa.Column("import_status", sa.String),
        sa.Column("schema_version", sa.String),
    )
    stores = sa.Table(
        "test_catalog_stores", metadata,
        sa.Column("id", sa.Integer),
        sa.Column("package_id", sa.String),
        sa.Column("store_code", sa.String),
        sa.Column("data_source", sa.String),
        sa.Column("customer_service_status", sa.String),
        sa.Column("customer_service_status_updated_at", sa.DateTime(timezone=True)),
        sa.Column("customer_service_status_updated_by", sa.String),
    )
    products = sa.Table(
        "test_catalog_products", metadata,
        sa.Column("product_id", sa.String),
        sa.Column("package_id", sa.String),
        sa.Column("store_code", sa.String),
        sa.Column("customer_service_status", sa.String),
        sa.Column("customer_service_status_updated_at", sa.DateTime(timezone=True)),
        sa.Column("customer_service_status_updated_by", sa.String),
    )
    receipts = sa.Table(
        "catalog_activation_receipts", metadata,
        sa.Column("activation_receipt_id", sa.String),
        sa.Column("entity_type", sa.String),
        sa.Column("entity_ref", sa.String),
        sa.Column("data_source", sa.String),
        sa.Column("previous_status", sa.String),
        sa.Column("customer_service_status", sa.String),
        sa.Column("activation_source", sa.String),
        sa.Column("confirmed_by", sa.String),
        sa.Column("confirmation_note", sa.String),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    initializations = sa.Table(
        "catalog_activation_initializations", metadata,
        sa.Column("policy_version", sa.String),
        sa.Column("source_baseline", sa.String),
        sa.Column("manifest_json", sa.Text),
        sa.Column("initialized_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    counts = {
        "test_stores_enabled": 0,
        "test_products_enabled": 0,
        "pilot_stores_disabled": 0,
        "pilot_products_disabled": 0,
        "quarantined_stores": 0,
    }
    rows = bind.execute(
        sa.select(
            stores.c.id,
            stores.c.package_id,
            stores.c.store_code,
            packages.c.import_status,
            packages.c.schema_version,
        ).select_from(
            stores.join(packages, stores.c.package_id == packages.c.package_id)
        )
    ).mappings()
    for row in rows:
        source: str | None = None
        status = "DISABLED"
        if (
            row["import_status"] == "IMPORTED_TEST_ONLY"
            and row["schema_version"] == "0.3.1-test"
        ):
            source, status = "TEST", "ENABLED"
            counts["test_stores_enabled"] += 1
        elif (
            row["import_status"] == "MANUAL_CREATED"
            and row["schema_version"] == "c-operation-store.v1"
        ):
            source = "PILOT"
            counts["pilot_stores_disabled"] += 1
        else:
            counts["quarantined_stores"] += 1

        bind.execute(
            stores.update().where(stores.c.id == row["id"]).values(
                data_source=source,
                customer_service_status=status,
                customer_service_status_updated_at=now if source else None,
                customer_service_status_updated_by="SYSTEM_MIGRATION" if source else None,
            )
        )
        product_rows = list(
            bind.execute(
                sa.select(products.c.product_id).where(
                    products.c.package_id == row["package_id"],
                    products.c.store_code == row["store_code"],
                )
            ).mappings()
        )
        bind.execute(
            products.update().where(
                products.c.package_id == row["package_id"],
                products.c.store_code == row["store_code"],
            ).values(
                customer_service_status=status if source else "DISABLED",
                customer_service_status_updated_at=now if source else None,
                customer_service_status_updated_by="SYSTEM_MIGRATION" if source else None,
            )
        )
        if source:
            bind.execute(
                receipts.insert().values(
                    **_receipt(
                        receipts,
                        entity_type="STORE",
                        entity_ref=str(row["id"]),
                        data_source=source,
                        status=status,
                        now=now,
                    )
                )
            )
            for product_row in product_rows:
                bind.execute(
                    receipts.insert().values(
                        **_receipt(
                            receipts,
                            entity_type="PRODUCT",
                            entity_ref=str(product_row["product_id"]),
                            data_source=source,
                            status=status,
                            now=now,
                        )
                    )
                )
            counts[
                "test_products_enabled" if source == "TEST" else "pilot_products_disabled"
            ] += len(product_rows)

    bind.execute(
        initializations.insert().values(
            policy_version=POLICY_VERSION,
            source_baseline=SOURCE_BASELINE,
            manifest_json=json.dumps(counts, sort_keys=True, separators=(",", ":")),
            initialized_at=now,
        )
    )


def downgrade() -> None:
    op.drop_table("catalog_activation_initializations")
    op.drop_table("catalog_activation_idempotency")
    op.drop_index(
        "ix_catalog_activation_receipts_entity_time",
        table_name="catalog_activation_receipts",
    )
    op.drop_table("catalog_activation_receipts")
    with op.batch_alter_table("test_catalog_products") as batch_op:
        batch_op.drop_index("ix_catalog_products_customer_service_projection")
        batch_op.drop_column("customer_service_status_updated_by")
        batch_op.drop_column("customer_service_status_updated_at")
        batch_op.drop_column("customer_service_status")
    with op.batch_alter_table("test_catalog_stores") as batch_op:
        batch_op.drop_index("ix_catalog_stores_customer_service_projection")
        batch_op.drop_column("customer_service_status_updated_by")
        batch_op.drop_column("customer_service_status_updated_at")
        batch_op.drop_column("customer_service_status")
        batch_op.drop_column("data_source")
