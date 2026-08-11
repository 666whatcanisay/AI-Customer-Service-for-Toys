"""add independent store platform identity bindings

Revision ID: 0018_store_platform_bindings_v1
Revises: 0017_host_pairing_rotation_audit
Create Date: 2026-08-10
"""

from datetime import datetime, timezone
import json
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa


revision = "0018_store_platform_bindings_v1"
down_revision = "0017_host_pairing_rotation_audit"
branch_labels = None
depends_on = None


def _platform(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return {"pdd": "pinduoduo", "拼多多": "pinduoduo"}.get(normalized, normalized)


def upgrade() -> None:
    op.create_table(
        "store_platform_bindings",
        sa.Column("binding_id", sa.String(36), primary_key=True),
        sa.Column(
            "store_id",
            sa.Integer(),
            sa.ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_store_id", sa.String(96), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(128), nullable=True),
        sa.Column("change_reason", sa.String(512), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')",
            name="ck_store_platform_binding_status",
        ),
    )
    op.create_index(
        "ix_store_platform_binding_store_status",
        "store_platform_bindings",
        ["store_id", "status", "created_at"],
    )
    op.create_index(
        "uq_store_platform_binding_active_identity",
        "store_platform_bindings",
        ["platform", "platform_store_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, platform, raw_data_json FROM test_catalog_stores ORDER BY id"
        )
    ).mappings()
    seen: dict[tuple[str, str], int] = {}
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            raw = json.loads(row["raw_data_json"] or "{}")
        except (TypeError, ValueError):
            continue
        platform_store_id = str(raw.get("platform_store_id") or "").strip()
        platform = _platform(raw.get("platform") or row["platform"])
        if not platform_store_id or not platform:
            continue
        identity = (platform, platform_store_id)
        if identity in seen and seen[identity] != row["id"]:
            raise RuntimeError(
                "duplicate active platform store identity requires manual resolution: "
                f"{platform}:{platform_store_id}"
            )
        seen[identity] = row["id"]
        binding_id = str(
            uuid5(
                NAMESPACE_URL,
                f"ai-cs:store-platform-binding:{row['id']}:{platform}:{platform_store_id}",
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO store_platform_bindings (
                    binding_id, store_id, platform, platform_store_id, status,
                    verified_at, verified_by, created_at, revoked_at, revoked_by,
                    change_reason
                ) VALUES (
                    :binding_id, :store_id, :platform, :platform_store_id, 'ACTIVE',
                    :verified_at, 'MIGRATION_FROM_CATALOG_METADATA', :created_at,
                    NULL, NULL, :change_reason
                )
                """
            ),
            {
                "binding_id": binding_id,
                "store_id": row["id"],
                "platform": platform,
                "platform_store_id": platform_store_id,
                "verified_at": now,
                "created_at": now,
                "change_reason": "从已有可靠平台店铺元数据迁移",
            },
        )


def downgrade() -> None:
    op.drop_index(
        "uq_store_platform_binding_active_identity",
        table_name="store_platform_bindings",
    )
    op.drop_index(
        "ix_store_platform_binding_store_status",
        table_name="store_platform_bindings",
    )
    op.drop_table("store_platform_bindings")
