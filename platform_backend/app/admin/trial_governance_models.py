"""C-internal, test-only audit records for the pilot operations console."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrialAuditEvent(Base):
    """A content-free action record; it is not an authentication ledger."""

    __tablename__ = "trial_audit_events"
    __table_args__ = (
        Index("ix_trial_audit_events_occurred", "occurred_at", "action"),
        Index("ix_trial_audit_events_actor", "actor_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
