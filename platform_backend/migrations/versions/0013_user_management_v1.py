"""add production user identity, role, Store binding, and opaque sessions

Revision ID: 0013_user_management_v1
Revises: 0012_internal_production_finalization_v1
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_user_management_v1"
down_revision = "0012_internal_production_finalization_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("username_normalized", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username_normalized", name="uq_users_username_normalized"),
    )
    op.create_index("ix_users_username_normalized", "users", ["username_normalized"], unique=True)
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role_name", sa.String(32), nullable=False, unique=True),
    )
    roles = sa.table("roles", sa.column("role_name", sa.String(32)))
    op.bulk_insert(roles, [
        {"role_name": "ADMIN"}, {"role_name": "OPERATOR"},
        {"role_name": "CUSTOMER_SERVICE"},
    ])
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permission_name", sa.String(64), nullable=False, unique=True),
    )
    permissions_by_role = {
        "CUSTOMER_SERVICE": {
            "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
        },
        "OPERATOR": {
            "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
            "ai_quality.view", "store.view", "feedback.view",
        },
        "ADMIN": {
            "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
            "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
            "ai_quality.view", "store.view", "feedback.view", "user.manage",
        },
    }
    permissions = sa.table(
        "permissions", sa.column("permission_name", sa.String(64))
    )
    op.bulk_insert(permissions, [
        {"permission_name": permission_name}
        for permission_name in sorted(set().union(*permissions_by_role.values()))
    ])
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id", sa.Integer(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True,
        ),
    )
    for role_name, permission_names in permissions_by_role.items():
        for permission_name in permission_names:
            op.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                "WHERE roles.role_name = :role_name "
                "AND permissions.permission_name = :permission_name"
            ).bindparams(role_name=role_name, permission_name=permission_name))
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "user_store_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "store_id", name="uq_user_store_binding"),
    )
    op.create_index("ix_user_store_bindings_user_id", "user_store_bindings", ["user_id"])
    op.create_index("ix_user_store_bindings_store_id", "user_store_bindings", ["store_id"])
    op.create_index("ix_user_store_bindings_user_default", "user_store_bindings", ["user_id", "is_default"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_user_active", "user_sessions", ["user_id", "revoked_at"])


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("user_store_bindings")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
