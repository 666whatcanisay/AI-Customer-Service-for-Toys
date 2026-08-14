from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReplyReadinessQuestionSetExtension(Base):
    __tablename__ = "reply_readiness_question_set_extensions"
    __table_args__ = (
        UniqueConstraint("extension_id", "version", name="uq_reply_readiness_extension_version"),
        Index("ix_reply_readiness_extension_scope", "scope_kind", "store_code", "product_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    extension_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    change_reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ReplyReadinessRun(Base):
    __tablename__ = "reply_readiness_runs"
    __table_args__ = (
        UniqueConstraint("requested_by", "idempotency_key", name="uq_reply_readiness_run_idempotency"),
        Index("ix_reply_readiness_runs_scope_time", "store_code", "product_id", "sku_id", "requested_at"),
        Index("ix_reply_readiness_runs_status", "status", "requested_at"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(96), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_code: Mapped[str] = mapped_column(String(96), nullable=False)
    product_id: Mapped[str] = mapped_column(String(96), nullable=False)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question_set_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    material_content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reply_rule_snapshot_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reply_rule_snapshot_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    router_build_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sandbox_vector_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    test_data_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    production_usable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
