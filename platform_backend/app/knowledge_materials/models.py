"""C-owned persistence for the frozen knowledge-quality loop v1.

Raw uploads remain in the local controlled runtime directory.  They are not
returned by customer APIs, emitted in logs, or committed to the repository.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_material_id() -> str:
    return f"KMT-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


def new_assessment_id() -> str:
    return f"KQA-{utc_now():%Y%m%d}-{uuid4().hex[:12].upper()}"


class KnowledgeMaterial(Base):
    """One immutable material revision controlled by the C platform."""

    __tablename__ = "knowledge_materials"
    __table_args__ = (
        UniqueConstraint("material_id", "revision", name="uq_knowledge_material_revision"),
        Index(
            "ix_knowledge_material_scope_status",
            "store_code",
            "product_id",
            "sku_id",
            "material_status",
        ),
        Index("ix_knowledge_material_id_revision", "material_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    material_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_material_id)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    material_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    redaction_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v1-reminder-only"
    )
    recognition_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    analysis_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    material_status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    submitted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class KnowledgeMaterialUploadReceipt(Base):
    """Idempotency receipt for a controlled operator upload."""

    __tablename__ = "knowledge_material_upload_receipts"
    __table_args__ = (
        UniqueConstraint(
            "request_method",
            "request_path",
            "submitted_by",
            "idempotency_key",
            name="uq_knowledge_material_upload_idempotency_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_method: Mapped[str] = mapped_column(String(8), nullable=False)
    request_path: Mapped[str] = mapped_column(String(128), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    material_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_materials.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class KnowledgeQualityAssessment(Base):
    """Append-only structured A analysis evidence for an approved material revision."""

    __tablename__ = "knowledge_quality_assessments"
    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_knowledge_quality_assessment_id"),
        UniqueConstraint("material_record_id", name="uq_knowledge_quality_assessment_material_record"),
        UniqueConstraint("analysis_run_id", name="uq_knowledge_quality_assessment_run"),
        Index("ix_knowledge_quality_assessment_material", "material_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(64), nullable=False, default=new_assessment_id)
    material_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_materials.id", ondelete="RESTRICT"), nullable=False
    )
    material_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(160), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    gaps: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
