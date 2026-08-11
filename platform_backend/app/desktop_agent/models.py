"""Minimized audit rows for Customer Desktop Workflow V1."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DesktopWorkflowAuditEvent(Base):
    __tablename__ = "desktop_workflow_audit_events"
    __table_args__ = (
        Index("ix_desktop_workflow_audit_user_time", "actor_user_id", "occurred_at"),
        Index("ix_desktop_workflow_audit_agent_time", "agent_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"), nullable=True
    )
    previous_state: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_state: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, default="SUCCESS")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
