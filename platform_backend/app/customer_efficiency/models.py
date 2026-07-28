"""Immutable, content-free events used only for aggregate efficiency analysis."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_event_id() -> str:
    return f"CEE-{uuid4().hex[:18].upper()}"


class CustomerEfficiencyEvent(Base):
    """C-owned immutable event; deliberately stores no customer or answer content."""

    __tablename__ = "customer_efficiency_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_customer_efficiency_event_id"),
        UniqueConstraint("event_type", "interaction_id", name="uq_customer_efficiency_event_interaction_type"),
        Index("ix_customer_efficiency_event_store_created", "store_code", "created_at"),
        Index("ix_customer_efficiency_event_operator", "operator_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_event_id)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feedback_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CustomerEfficiencyEventIdempotency(Base):
    """Receipt for retry-safe submission of an immutable event."""

    __tablename__ = "customer_efficiency_event_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "request_method", "request_path", "operator_id", "idempotency_key",
            name="uq_customer_efficiency_event_idempotency_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_method: Mapped[str] = mapped_column(String(8), nullable=False)
    request_path: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    event_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_efficiency_events.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
