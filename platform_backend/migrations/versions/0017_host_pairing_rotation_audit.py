"""add host pairing rotation reason to desktop workflow audit

Revision ID: 0017_host_pairing_rotation_audit
Revises: 0016_production_hardening_v1
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_host_pairing_rotation_audit"
down_revision = "0016_production_hardening_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("desktop_workflow_audit_events") as batch_op:
        batch_op.add_column(sa.Column("reason", sa.String(512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("desktop_workflow_audit_events") as batch_op:
        batch_op.drop_column("reason")
