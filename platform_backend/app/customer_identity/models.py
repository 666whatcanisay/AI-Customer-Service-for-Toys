"""Minimal trial identity persistence; this is not an authentication system."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_user_id() -> str:
    return f"CSU-{uuid4().hex[:16].upper()}"


class CustomerUser(Base):
    __tablename__ = "customer_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, default=new_user_id)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", index=True)
    default_store_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CustomerUserStoreBinding(Base):
    __tablename__ = "customer_user_store_bindings"
    __table_args__ = (
        UniqueConstraint("customer_user_id", "store_code", name="uq_customer_user_store_binding"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_user_id: Mapped[str] = mapped_column(
        ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
