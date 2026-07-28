"""add internal-pilot customer identity and privacy-bounded efficiency events

Revision ID: 0007_pilot_user_identity
Revises: 0006_mvp_plus_02_ai_feedback_idempotency
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_pilot_user_identity"
down_revision = "0006_mvp_plus_02_ai_feedback_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("default_store_code", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_customer_users_user_id", "customer_users", ["user_id"])
    op.create_index("ix_customer_users_status", "customer_users", ["status"])
    op.create_index("ix_customer_users_default_store_code", "customer_users", ["default_store_code"])
    op.create_table(
        "customer_user_store_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("customer_user_id", sa.String(36), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["customer_user_id"], ["customer_users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("customer_user_id", "store_code", name="uq_customer_user_store_binding"),
    )
    op.create_index("ix_customer_user_store_bindings_customer_user_id", "customer_user_store_bindings", ["customer_user_id"])
    op.create_index("ix_customer_user_store_bindings_store_code", "customer_user_store_bindings", ["store_code"])
    op.create_table(
        "customer_efficiency_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("operator_id", sa.String(128), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=False),
        sa.Column("product_id", sa.String(128), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("conversation_id", sa.String(128), nullable=True),
        sa.Column("interaction_id", sa.String(128), nullable=True),
        sa.Column("feedback_id", sa.String(64), nullable=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_customer_efficiency_event_id"),
        sa.UniqueConstraint("event_type", "interaction_id", name="uq_customer_efficiency_event_interaction_type"),
    )
    op.create_index("ix_customer_efficiency_event_store_created", "customer_efficiency_events", ["store_code", "created_at"])
    op.create_index("ix_customer_efficiency_event_operator", "customer_efficiency_events", ["operator_id", "created_at"])
    op.create_table(
        "customer_efficiency_event_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_method", sa.String(8), nullable=False),
        sa.Column("request_path", sa.String(128), nullable=False),
        sa.Column("operator_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(80), nullable=False),
        sa.Column("event_record_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_record_id"], ["customer_efficiency_events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "request_method", "request_path", "operator_id", "idempotency_key",
            name="uq_customer_efficiency_event_idempotency_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("customer_efficiency_event_idempotency")
    op.drop_index("ix_customer_efficiency_event_operator", table_name="customer_efficiency_events")
    op.drop_index("ix_customer_efficiency_event_store_created", table_name="customer_efficiency_events")
    op.drop_table("customer_efficiency_events")
    op.drop_index("ix_customer_user_store_bindings_store_code", table_name="customer_user_store_bindings")
    op.drop_index("ix_customer_user_store_bindings_customer_user_id", table_name="customer_user_store_bindings")
    op.drop_table("customer_user_store_bindings")
    op.drop_index("ix_customer_users_default_store_code", table_name="customer_users")
    op.drop_index("ix_customer_users_status", table_name="customer_users")
    op.drop_index("ix_customer_users_user_id", table_name="customer_users")
    op.drop_table("customer_users")
