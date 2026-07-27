"""C-internal trial-store setup records for multi-store operations.

This record contains operational configuration only.  It is not a customer,
employee, order, ERP, or knowledge-content record.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PilotStore(Base):
    """One manually created trial store that may receive a target-bound import."""

    __tablename__ = "pilot_stores"
    __table_args__ = (UniqueConstraint("store_code", name="uq_pilot_stores_store_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    store_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
