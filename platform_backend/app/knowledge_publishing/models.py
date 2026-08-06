from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductKnowledgePublication(Base):
    __tablename__ = "product_knowledge_publications"

    product_id: Mapped[str] = mapped_column(
        ForeignKey("test_catalog_products.product_id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    current_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    indexed_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_receipt_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    generation_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ProductKnowledgePublicationReceipt(Base):
    __tablename__ = "product_knowledge_publication_receipts"
    __table_args__ = (
        Index(
            "ix_product_knowledge_publication_receipts_product_time",
            "product_id",
            "created_at",
        ),
    )

    publication_receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("test_catalog_products.product_id", ondelete="CASCADE")
    )
    knowledge_fingerprint: Mapped[str] = mapped_column(String(64))
    active_collection: Mapped[str] = mapped_column(String(128))
    chunk_count: Mapped[int] = mapped_column(Integer)
    embedding_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    operator: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProductKnowledgePublicationIdempotency(Base):
    __tablename__ = "product_knowledge_publication_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
