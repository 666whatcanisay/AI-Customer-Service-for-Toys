"""add atomic reply rule snapshot publication evidence

Revision ID: 0021_reply_rule_snapshot_publication_v1
Revises: 0020_reply_rule_governance_v1
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_reply_rule_snapshot_publication_v1"
down_revision = "0020_reply_rule_governance_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_rule_snapshot_publications",
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("snapshot_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_fingerprint", sa.String(64), nullable=True),
        sa.Column("rules_fingerprint", sa.String(64), nullable=True),
        sa.Column("rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publication_receipt_id", sa.String(64), nullable=True),
        sa.Column("generation_token", sa.String(36), nullable=True),
        sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('GENERATING','PUBLISHED','SYNC_FAILED')",
            name="ck_reply_rule_snapshot_publication_status",
        ),
        sa.CheckConstraint(
            "snapshot_revision >= 0",
            name="ck_reply_rule_snapshot_revision_non_negative",
        ),
        sa.CheckConstraint(
            "rule_count >= 0",
            name="ck_reply_rule_snapshot_rule_count_non_negative",
        ),
    )
    op.create_index(
        "ix_reply_rule_snapshot_publications_scope",
        "reply_rule_snapshot_publications",
        ["tenant_id", "platform"],
        unique=True,
    )
    op.create_index(
        "ix_reply_rule_snapshot_publications_status",
        "reply_rule_snapshot_publications",
        ["status", "updated_at"],
    )

    op.create_table(
        "reply_rule_snapshot_publication_receipts",
        sa.Column("publication_receipt_id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), nullable=False, unique=True),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(96), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("snapshot_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("rules_fingerprint", sa.String(64), nullable=False),
        sa.Column("accepted_rule_count", sa.Integer(), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "snapshot_revision >= 1",
            name="ck_reply_rule_snapshot_receipt_revision_positive",
        ),
        sa.CheckConstraint(
            "accepted_rule_count >= 0",
            name="ck_reply_rule_snapshot_receipt_count_non_negative",
        ),
    )
    op.create_index(
        "ix_reply_rule_snapshot_receipts_scope_time",
        "reply_rule_snapshot_publication_receipts",
        ["scope_key", "published_at"],
    )

    op.create_table(
        "reply_rule_snapshot_publication_idempotency",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reply_rule_snapshot_publication_idempotency")
    op.drop_index(
        "ix_reply_rule_snapshot_receipts_scope_time",
        table_name="reply_rule_snapshot_publication_receipts",
    )
    op.drop_table("reply_rule_snapshot_publication_receipts")
    op.drop_index(
        "ix_reply_rule_snapshot_publications_status",
        table_name="reply_rule_snapshot_publications",
    )
    op.drop_index(
        "ix_reply_rule_snapshot_publications_scope",
        table_name="reply_rule_snapshot_publications",
    )
    op.drop_table("reply_rule_snapshot_publications")
