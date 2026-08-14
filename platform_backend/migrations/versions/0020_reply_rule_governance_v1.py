"""add governed fixed reply rule versions and lifecycle events

Revision ID: 0020_reply_rule_governance_v1
Revises: 0019_runtime_database_identity_v1
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_reply_rule_governance_v1"
down_revision = "0019_runtime_database_identity_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("store_code", sa.String(96), nullable=True),
        sa.Column("product_id", sa.String(96), nullable=True),
        sa.Column("sku_id", sa.String(128), nullable=True),
        sa.Column("canonical_question", sa.Text(), nullable=False),
        sa.Column("aliases_json", sa.Text(), nullable=False),
        sa.Column("fixed_reply", sa.Text(), nullable=False),
        sa.Column("variable_names_json", sa.Text(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("required_context_fields_json", sa.Text(), nullable=False),
        sa.Column("prohibited_claims_json", sa.Text(), nullable=False),
        sa.Column("allow_auto_candidate", sa.Boolean(), nullable=False),
        sa.Column("source_material_ids_json", sa.Text(), nullable=False),
        sa.Column("source_confirmed", sa.Boolean(), nullable=False),
        sa.Column("high_risk_source_confirmed", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_id", "rule_version", name="uq_reply_rule_version"),
        sa.CheckConstraint(
            "rule_version >= 1", name="ck_reply_rule_version_positive"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','REJECTED','APPROVED','PUBLISHED','WITHDRAWN','EXPIRED')",
            name="ck_reply_rule_status",
        ),
        sa.CheckConstraint(
            "scope_kind IN ('TENANT','STORE','PRODUCT','SKU')",
            name="ck_reply_rule_scope_kind",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW','MEDIUM','HIGH')",
            name="ck_reply_rule_risk_level",
        ),
        sa.CheckConstraint(
            "action IN ('DIRECT_ANSWER','CONTROLLED_ANSWER','ASK_CLARIFY','REQUIRE_LOOKUP','TRANSFER_HUMAN','REFUSE')",
            name="ck_reply_rule_action",
        ),
    )
    op.create_index(
        "ix_reply_rules_scope_status",
        "reply_rules",
        [
            "tenant_id",
            "platform",
            "store_code",
            "product_id",
            "sku_id",
            "status",
        ],
    )
    op.create_index(
        "ix_reply_rules_status_updated", "reply_rules", ["status", "updated_at"]
    )

    op.create_table(
        "reply_rule_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column(
            "rule_record_id",
            sa.String(36),
            sa.ForeignKey("reply_rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("previous_status", sa.String(24), nullable=True),
        sa.Column("next_status", sa.String(24), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED','DRAFT_UPDATED','REVIEW_SUBMITTED','APPROVED','REJECTED','REVISION_CREATED','PUBLISHED','WITHDRAWN','EXPIRED')",
            name="ck_reply_rule_event_type",
        ),
    )
    op.create_index(
        "ix_reply_rule_events_rule_time",
        "reply_rule_events",
        ["rule_id", "rule_version", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reply_rule_events_rule_time", table_name="reply_rule_events"
    )
    op.drop_table("reply_rule_events")
    op.drop_index("ix_reply_rules_status_updated", table_name="reply_rules")
    op.drop_index("ix_reply_rules_scope_status", table_name="reply_rules")
    op.drop_table("reply_rules")
