"""SQLAlchemy models for the isolated ingestion and review-staging zone."""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.ingestion.schemas import BatchStatus, ReviewStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32), default="PRODUCT_SKU")
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default=BatchStatus.RECEIVED)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="manual-import")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rows: Mapped[list["ImportRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    staged_items: Mapped[list["StagedProductSku"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_number", name="uq_import_row_batch_source"),
        Index("ix_import_rows_batch_status", "batch_id", "validation_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    source_row_number: Mapped[int] = mapped_column(Integer)
    raw_data_json: Mapped[str] = mapped_column(Text)
    normalized_data_json: Mapped[str] = mapped_column(Text)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)
    validation_status: Mapped[str] = mapped_column(String(16))
    error_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    warning_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped[ImportBatch] = relationship(back_populates="rows")


class StagedProductSku(Base):
    __tablename__ = "staged_product_skus"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_hash", name="uq_staged_batch_row_hash"),
        Index(
            "ix_staged_product_identity",
            "tenant_id",
            "platform",
            "store_code",
            "product_code",
            "sku_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(128))
    product_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    platform_product_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    sku_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    platform_sku_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sku_name: Mapped[str] = mapped_column(String(255))
    specifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applicable_age_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    applicable_age_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    package_contents: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(255))
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)
    review_status: Mapped[str] = mapped_column(
        String(32), default=ReviewStatus.PENDING_REVIEW
    )
    external_system: Mapped[str] = mapped_column(String(32), default="MANUAL_EXCEL")
    external_product_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    external_sku_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    external_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped[ImportBatch] = relationship(back_populates="staged_items")
