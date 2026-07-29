"""C-owned persistence for the minimum customer feedback loop.

Only minimized summaries are stored. The source question and answer are never
persisted by this module.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _business_id(prefix: str) -> str:
    return f"{prefix}-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


class AIInteractionEvent(Base):
    """One idempotent customer-service decision about an AI response."""

    __tablename__ = "ai_interaction_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_ai_interaction_event_event_id"),
        UniqueConstraint(
            "created_by",
            "idempotency_key",
            name="uq_ai_interaction_event_idempotency_scope",
        ),
        Index(
            "ix_ai_interaction_event_scope",
            "store_code",
            "product_id",
            "sku_id",
            "action_type",
            "occurred_at",
        ),
        Index("ix_ai_interaction_event_interaction", "interaction_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=lambda: _business_id("AIE")
    )
    interaction_id: Mapped[str] = mapped_column(String(160), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    store_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    question_summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    redaction_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="feedback-summary-v1"
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AIProblem(Base):
    """Aggregated rejected interactions under one product/SKU question key."""

    __tablename__ = "ai_problems"
    __table_args__ = (
        UniqueConstraint("problem_id", name="uq_ai_problem_problem_id"),
        UniqueConstraint("aggregation_fingerprint", name="uq_ai_problem_aggregation_fingerprint"),
        Index(
            "ix_ai_problem_operations",
            "status",
            "issue_type",
            "store_code",
            "product_id",
            "sku_id",
            "last_seen_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    problem_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=lambda: _business_id("AIP")
    )
    aggregation_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    store_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    question_summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False, default="UNCLASSIFIED")
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    status_changed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AIProblemOccurrence(Base):
    """Trace from an aggregate problem to one persisted rejection event."""

    __tablename__ = "ai_problem_occurrences"
    __table_args__ = (
        UniqueConstraint("event_record_id", name="uq_ai_problem_occurrence_event"),
        Index("ix_ai_problem_occurrence_problem", "problem_record_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    problem_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_problems.id", ondelete="RESTRICT"), nullable=False
    )
    event_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_interaction_events.id", ondelete="RESTRICT"), nullable=False
    )
    feedback_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class KnowledgeOptimizationTask(Base):
    """Human-owned instruction to supplement knowledge for one confirmed problem."""

    __tablename__ = "knowledge_optimization_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_knowledge_optimization_task_id"),
        UniqueConstraint("problem_record_id", name="uq_knowledge_optimization_task_problem"),
        Index("ix_knowledge_optimization_task_status", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=lambda: _business_id("KOT")
    )
    problem_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_problems.id", ondelete="RESTRICT"), nullable=False
    )
    source_problem_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    missing_topic: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
