"""bind fixed reply rules to exact reviewed source revisions

Revision ID: 0022_reply_rule_source_evidence_v1
Revises: 0021_reply_rule_snapshot_publication_v1
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_reply_rule_source_evidence_v1"
down_revision = "0021_reply_rule_snapshot_publication_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reply_rules",
        sa.Column(
            "source_material_evidence_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("reply_rules", "source_material_evidence_json")
