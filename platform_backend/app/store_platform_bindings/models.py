"""Independent platform identity bindings for AI-CS stores."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StorePlatformBinding(Base):
    __tablename__ = "store_platform_bindings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')",
            name="ck_store_platform_binding_status",
        ),
        Index(
            "uq_store_platform_binding_active_identity",
            "platform",
            "platform_store_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_store_platform_binding_store_status",
            "store_id",
            "status",
            "created_at",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_catalog_stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_store_id: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_reason: Mapped[str] = mapped_column(String(512), nullable=False)
