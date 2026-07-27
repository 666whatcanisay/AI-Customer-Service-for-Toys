"""Persistence for aggregate-only customer-efficiency events.

This module deliberately stores no customer-service message, customer identity,
employee identity, store, product, or order data.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_event_id() -> str:
    return f"CEE-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


class CustomerEfficiencyEvent(Base):
    """One idempotently recorded, content-free customer-efficiency event."""

    __tablename__ = "customer_efficiency_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_customer_efficiency_event_id"),
        UniqueConstraint("idempotency_key", name="uq_customer_efficiency_event_idempotency_key"),
        Index("ix_customer_efficiency_event_window", "occurred_at", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_event_id)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
