"""add runtime database identity metadata

Revision ID: 0019_runtime_database_identity_v1
Revises: 0018_store_platform_bindings_v1
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_runtime_database_identity_v1"
down_revision = "0018_store_platform_bindings_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_database_identity",
        sa.Column("database_role", sa.String(32), primary_key=True),
        sa.Column("database_instance_id", sa.String(36), nullable=False, unique=True),
        sa.Column("environment_id", sa.String(128), nullable=False),
        sa.Column("identity_revision", sa.Integer(), nullable=False),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by_source_commit", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restore_generation", sa.Integer(), nullable=False),
        sa.Column("restored_from_backup_epoch", sa.String(128), nullable=True),
        sa.Column("last_restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "database_role = 'PLATFORM'",
            name="ck_runtime_database_identity_platform_role",
        ),
        sa.CheckConstraint(
            "identity_revision >= 1",
            name="ck_runtime_database_identity_revision_positive",
        ),
        sa.CheckConstraint(
            "restore_generation >= 0",
            name="ck_runtime_database_identity_restore_generation_nonnegative",
        ),
    )


def downgrade() -> None:
    op.drop_table("runtime_database_identity")
