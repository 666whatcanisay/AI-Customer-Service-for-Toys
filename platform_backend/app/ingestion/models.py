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
    __table_args__ = (
        UniqueConstraint(
            "import_type",
            "created_by",
            "idempotency_key",
            name="uq_import_batch_idempotency_scope",
        ),
        Index(
            "ix_import_batches_catalog_scope",
            "store_ref",
            "template_type",
            "status",
        ),
        Index(
            "ix_import_batches_catalog_file",
            "store_ref",
            "template_type",
            "file_sha256",
        ),
        Index("ix_import_batches_created_at", "created_at"),
    )
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
    store_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    store_code_snapshot: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    store_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    platform_snapshot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    template_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    template_evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utc_now, onupdate=utc_now
    )

    rows: Mapped[list["ImportRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    staged_items: Mapped[list["StagedProductSku"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    change_sets: Mapped[list["ImportChangeSet"]] = relationship(
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
    sheet_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    product_identity_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_match_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_product_id: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)

    batch: Mapped[ImportBatch] = relationship(back_populates="rows")


Index(
    "ix_import_rows_batch_product_identity",
    ImportRow.batch_id,
    ImportRow.product_identity_key,
)


class ImportChangeSet(Base):
    __tablename__ = "import_change_sets"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "product_identity_key",
            name="uq_import_change_set_batch_identity",
        ),
        Index("ix_import_change_sets_batch_status", "batch_id", "status"),
        Index("ix_import_change_sets_target_product", "target_product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    source_row_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    product_identity_key: Mapped[str] = mapped_column(String(255))
    product_name: Mapped[str] = mapped_column(String(255))
    target_product_id: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    operation: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(40))
    base_snapshot_hash: Mapped[str] = mapped_column(String(64))
    old_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    incoming_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    merged_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    error_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    warning_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    applied_product_id: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    batch: Mapped[ImportBatch] = relationship(back_populates="change_sets")
    field_changes: Mapped[list["ImportFieldChange"]] = relationship(
        back_populates="change_set", cascade="all, delete-orphan"
    )
    review_records: Mapped[list["ImportReviewRecord"]] = relationship(
        back_populates="change_set"
    )


class ImportFieldChange(Base):
    __tablename__ = "import_field_changes"
    __table_args__ = (
        UniqueConstraint(
            "change_set_id",
            "field_key",
            name="uq_import_field_change_set_field",
        ),
        Index(
            "ix_import_field_changes_set_type",
            "change_set_id",
            "change_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_set_id: Mapped[str] = mapped_column(
        ForeignKey("import_change_sets.id", ondelete="CASCADE"), index=True
    )
    field_key: Mapped[str] = mapped_column(String(128))
    field_label: Mapped[str] = mapped_column(String(128))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    old_value_json: Mapped[str] = mapped_column(Text, default="null")
    incoming_value_json: Mapped[str] = mapped_column(Text, default="null")
    merged_value_json: Mapped[str] = mapped_column(Text, default="null")
    change_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    change_set: Mapped[ImportChangeSet] = relationship(back_populates="field_changes")


class ImportReviewRecord(Base):
    __tablename__ = "import_review_records"
    __table_args__ = (
        UniqueConstraint(
            "change_set_id",
            "reviewed_by",
            "idempotency_key",
            name="uq_import_review_idempotency_scope",
        ),
        Index("ix_import_review_records_batch", "batch_id", "created_at"),
        Index("ix_import_review_records_change_set", "change_set_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), index=True
    )
    change_set_id: Mapped[str] = mapped_column(
        ForeignKey("import_change_sets.id", ondelete="RESTRICT"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(32))
    reviewed_by: Mapped[str] = mapped_column(String(128))
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    expected_base_snapshot_hash: Mapped[str] = mapped_column(String(64))
    observed_base_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expected_change_set_version: Mapped[int] = mapped_column(Integer)
    applied_product_id: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    applied_field_count: Mapped[int] = mapped_column(Integer, default=0)
    before_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    after_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    change_set: Mapped[ImportChangeSet] = relationship(back_populates="review_records")


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
