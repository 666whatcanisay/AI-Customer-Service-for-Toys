"""Minimized audit persistence for conversation context resolution."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationContextResolution(Base):
    __tablename__ = "conversation_context_resolutions"
    __table_args__ = (
        Index("ix_context_resolutions_user_time", "user_id", "created_at"),
        Index("ix_context_resolutions_store_status", "store_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"), nullable=True
    )
    conversation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_candidate_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sku_candidate_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
