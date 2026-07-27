"""Persistence for the frozen AI-response feedback lifecycle.

Feedback content is deliberately not logged.  This entity is independent from
customer suggestions and customer experience cases.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_feedback_id() -> str:
    """Return a stable C-generated identifier that B and A cannot choose."""
    return f"ARF-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


class AIResponseFeedback(Base):
    """One de-identified, human-submitted non-adoption feedback record."""

    __tablename__ = "ai_response_feedback"
    __table_args__ = (
        UniqueConstraint("feedback_id", name="uq_ai_response_feedback_feedback_id"),
        Index(
            "ix_ai_response_feedback_admin_filters",
            "status",
            "feedback_type",
            "store_code",
            "product_id",
            "sku_id",
            "created_by",
        ),
        Index("ix_ai_response_feedback_creator", "created_by", "created_at"),
        Index("ix_ai_response_feedback_export", "status", "feedback_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    feedback_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_feedback_id)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    analysis_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    redaction_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v1-reminder-only"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AIResponseFeedbackAnalysis(Base):
    """Append-only A evidence for a feedback record that C already confirmed."""

    __tablename__ = "ai_response_feedback_analyses"
    __table_args__ = (
        UniqueConstraint("feedback_record_id", name="uq_ai_response_feedback_analysis_record"),
        UniqueConstraint("analysis_run_id", name="uq_ai_response_feedback_analysis_run"),
        Index("ix_ai_response_feedback_analysis_feedback", "feedback_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    feedback_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_response_feedback.id", ondelete="RESTRICT"),
        nullable=False,
    )
    feedback_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    analysis_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    suggestions_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AIResponseFeedbackIdempotency(Base):
    """A B submission receipt keyed by the frozen request idempotency scope."""

    __tablename__ = "ai_response_feedback_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "request_method",
            "request_path",
            "created_by",
            "idempotency_key",
            name="uq_ai_response_feedback_idempotency_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_method: Mapped[str] = mapped_column(String(8), nullable=False)
    request_path: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    feedback_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_response_feedback.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
