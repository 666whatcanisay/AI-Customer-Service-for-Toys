"""add C-T05 customer suggestion workflow

Revision ID: 0003_ct05_customer_suggestions
Revises: 0002_ct02b_test_catalog
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_ct05_customer_suggestions"
down_revision = "0002_ct02b_test_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reporter_id", sa.String(64), nullable=False),
        sa.Column("reporter_name", sa.String(128), nullable=True),
        sa.Column("store_code", sa.String(96), nullable=True),
        sa.Column("module_key", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=True),
        sa.Column("urgency", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_suggestions_admin_filters",
        "customer_suggestions",
        ["status", "store_code", "module_key"],
    )
    op.create_index(
        "ix_customer_suggestions_reporter",
        "customer_suggestions",
        ["reporter_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_suggestions_reporter", table_name="customer_suggestions")
    op.drop_index("ix_customer_suggestions_admin_filters", table_name="customer_suggestions")
    op.drop_table("customer_suggestions")
