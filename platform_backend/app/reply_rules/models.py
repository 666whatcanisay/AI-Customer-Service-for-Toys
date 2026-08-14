from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReplyRule(Base):
    """One immutable-after-review version of a governed fixed reply rule."""

    __tablename__ = "reply_rules"
    __table_args__ = (
        UniqueConstraint("rule_id", "rule_version", name="uq_reply_rule_version"),
        Index(
            "ix_reply_rules_scope_status",
            "tenant_id",
            "platform",
            "store_code",
            "product_id",
            "sku_id",
            "status",
        ),
        Index("ix_reply_rules_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(96), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    store_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canonical_question: Mapped[str] = mapped_column(Text, nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False)
    fixed_reply: Mapped[str] = mapped_column(Text, nullable=False)
    variable_names_json: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    required_context_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    prohibited_claims_json: Mapped[str] = mapped_column(Text, nullable=False)
    allow_auto_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_material_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_material_evidence_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    source_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    high_risk_source_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ReplyRuleEvent(Base):
    """Append-only, content-minimized lifecycle evidence."""

    __tablename__ = "reply_rule_events"
    __table_args__ = (
        Index(
            "ix_reply_rule_events_rule_time",
            "rule_id",
            "rule_version",
            "occurred_at",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"RRE-{uuid4().hex.upper()}"
    )
    rule_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reply_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    next_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ReplyRuleSnapshotPublication(Base):
    __tablename__ = "reply_rule_snapshot_publications"
    __table_args__ = (
        Index(
            "ix_reply_rule_snapshot_publications_scope",
            "tenant_id",
            "platform",
            unique=True,
        ),
        Index(
            "ix_reply_rule_snapshot_publications_status", "status", "updated_at"
        ),
        CheckConstraint(
            "status IN ('GENERATING','PUBLISHED','SYNC_FAILED')",
            name="ck_reply_rule_snapshot_publication_status",
        ),
        CheckConstraint(
            "snapshot_revision >= 0",
            name="ck_reply_rule_snapshot_revision_non_negative",
        ),
        CheckConstraint(
            "rule_count >= 0",
            name="ck_reply_rule_snapshot_rule_count_non_negative",
        ),
    )

    scope_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(96), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publication_receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ReplyRuleSnapshotPublicationReceipt(Base):
    __tablename__ = "reply_rule_snapshot_publication_receipts"
    __table_args__ = (
        Index(
            "ix_reply_rule_snapshot_receipts_scope_time",
            "scope_key",
            "published_at",
        ),
        CheckConstraint(
            "snapshot_revision >= 1",
            name="ck_reply_rule_snapshot_receipt_revision_positive",
        ),
        CheckConstraint(
            "accepted_rule_count >= 0",
            name="ck_reply_rule_snapshot_receipt_count_non_negative",
        ),
    )

    publication_receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(96), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rules_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ReplyRuleSnapshotPublicationIdempotency(Base):
    __tablename__ = "reply_rule_snapshot_publication_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
