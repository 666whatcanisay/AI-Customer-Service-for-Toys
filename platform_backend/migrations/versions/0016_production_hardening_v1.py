"""add IAM throttling and knowledge publication concurrency controls

Revision ID: 0016_production_hardening_v1
Revises: 0015_customer_desktop_workflow_v1
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_production_hardening_v1"
down_revision = "0015_customer_desktop_workflow_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempt_buckets",
        sa.Column("bucket_key", sa.String(64), primary_key=True),
        sa.Column("bucket_type", sa.String(16), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_login_attempt_buckets_locked_until",
        "login_attempt_buckets",
        ["locked_until"],
    )

    # Normalize any legacy duplicate defaults before enforcing the invariant.
    op.execute(sa.text(
        "UPDATE user_store_bindings SET is_default = 0 "
        "WHERE is_default = 1 AND id NOT IN ("
        "SELECT MIN(id) FROM user_store_bindings WHERE is_default = 1 GROUP BY user_id"
        ")"
    ))
    op.create_index(
        "uq_user_store_bindings_single_default",
        "user_store_bindings",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
        postgresql_where=sa.text("is_default = true"),
    )

    with op.batch_alter_table("product_knowledge_publications") as batch_op:
        batch_op.add_column(sa.Column("generation_token", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("product_knowledge_publications") as batch_op:
        batch_op.drop_column("generation_started_at")
        batch_op.drop_column("generation_token")
    op.drop_index(
        "uq_user_store_bindings_single_default",
        table_name="user_store_bindings",
    )
    op.drop_index(
        "ix_login_attempt_buckets_locked_until",
        table_name="login_attempt_buckets",
    )
    op.drop_table("login_attempt_buckets")
