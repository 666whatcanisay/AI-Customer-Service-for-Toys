"""Persistence model for customer-service suggestions.

Suggestion descriptions are deliberately not logged by this module.  They are
stored only in the local platform database used by the C-line portal.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerSuggestion(Base):
    __tablename__ = "customer_suggestions"
    __table_args__ = (
        Index("ix_customer_suggestions_admin_filters", "status", "store_code", "module_key"),
        Index("ix_customer_suggestions_reporter", "reporter_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    reporter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reporter_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    store_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    module_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUBMITTED")
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
