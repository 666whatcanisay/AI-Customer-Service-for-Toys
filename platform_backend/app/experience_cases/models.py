"""Persistence models for governed customer-service experience cases.

Raw case content stays in the platform database.  This module deliberately
does not log questions, answers, or evaluation evidence.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_case_id() -> str:
    """Return a stable, server-generated public identifier for one logical case."""
    return f"CEC-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


class CustomerExperienceCase(Base):
    """A single immutable-on-approval revision of a customer-service case."""

    __tablename__ = "customer_experience_cases"
    __table_args__ = (
        UniqueConstraint("case_id", "revision", name="uq_customer_experience_case_revision"),
        Index(
            "ix_customer_experience_cases_admin_filters",
            "review_status",
            "store_code",
            "product_id",
            "sku_id",
            "created_by",
        ),
        Index("ix_customer_experience_cases_creator", "created_by", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_case_id)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    export_revision: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    redaction_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1-reminder-only")
    evaluation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_EXPORTED")
    latest_evaluation_run_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CustomerExperienceCaseExport(Base):
    """An immutable, governed export snapshot created when a case is approved."""

    __tablename__ = "customer_experience_case_exports"
    __table_args__ = (
        UniqueConstraint("case_record_id", name="uq_customer_experience_case_export_record"),
        UniqueConstraint("export_revision", name="uq_customer_experience_case_export_revision"),
        Index("ix_customer_experience_case_exports_cursor", "case_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_experience_cases.id", ondelete="RESTRICT"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    export_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    redaction_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CustomerExperienceEvaluation(Base):
    """Append-only evidence returned by A for one frozen export snapshot."""

    __tablename__ = "customer_experience_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "revision", "export_revision", "evaluation_run_id",
            name="uq_customer_experience_evaluation_run",
        ),
        Index("ix_customer_experience_evaluations_case", "case_id", "revision", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customer_experience_cases.id", ondelete="RESTRICT"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    export_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    evaluation_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    suggestions_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
