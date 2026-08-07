from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("channel_name", "external_ref"),)

    conversation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    channel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "external_message_id"),)

    message_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRow(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.message_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    proposed_content: Mapped[str | None] = mapped_column(Text)
    requires_approval: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    gateway_version: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalRow(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    decided_by: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionRow(Base):
    __tablename__ = "executions"
    __table_args__ = (Index("ix_executions_claim", "state", "created_at"),)

    execution_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.approval_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_token: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReceiptRow(Base):
    __tablename__ = "execution_receipts"

    receipt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.execution_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventRow(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ObservabilityEventRow(Base):
    """Append-only, redacted operational event projection.

    This projection is intentionally independent from the frozen Gateway Event
    contract and transactional outbox.  It can therefore evolve for operators
    without changing externally visible protocol payloads.
    """

    __tablename__ = "observability_events"
    __table_args__ = (
        Index("ix_observability_trace_time", "trace_id", "timestamp", "event_id"),
        Index("ix_observability_type_time", "event_type", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    observability_version: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(160), index=True)
    decision_id: Mapped[str | None] = mapped_column(String(128), index=True)
    approval_id: Mapped[str | None] = mapped_column(String(128), index=True)
    execution_id: Mapped[str | None] = mapped_column(String(128), index=True)
    receipt_id: Mapped[str | None] = mapped_column(String(128), index=True)
    store_id: Mapped[str | None] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class OutboxRow(Base):
    __tablename__ = "transactional_outbox"
    __table_args__ = (
        Index("ix_transactional_outbox_claim", "status", "next_attempt_at", "created_at"),
    )

    outbox_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.event_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    publish_key: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_token: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ControlPlaneConfigSnapshotRow(Base):
    __tablename__ = "control_plane_config_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    control_plane_version: Mapped[str] = mapped_column(String(16), nullable=False)
    adapter_config_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    gateway_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)


class ControlPlaneStateRow(Base):
    __tablename__ = "control_plane_state"

    singleton_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    control_plane_version: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kill_switch_state: Mapped[str] = mapped_column(String(32), nullable=False)
    active_config_snapshot_id: Mapped[str | None] = mapped_column(String(128))
    kill_switch_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kill_switch_updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    kill_switch_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)


class ControlPlaneAuditEventRow(Base):
    __tablename__ = "control_plane_audit_events"
    __table_args__ = (
        Index(
            "ix_control_plane_audit_time",
            "timestamp",
            "audit_event_id",
        ),
    )

    audit_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    control_plane_version: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(128))
    before: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class RuntimeStorageMetadataRow(Base):
    __tablename__ = "runtime_storage_metadata"

    singleton_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(String(16), nullable=False)
    initialized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RuntimeWorkerOwnerRow(Base):
    __tablename__ = "runtime_worker_owners"

    worker_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    runtime_storage_version: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_token: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class RuntimeReliabilityStateRow(Base):
    __tablename__ = "runtime_reliability_state"

    runtime_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    reliability_version: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class RuntimeLifecycleEventRow(Base):
    __tablename__ = "runtime_lifecycle_events"
    __table_args__ = (
        Index("ix_runtime_lifecycle_time", "runtime_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    runtime_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reliability_version: Mapped[str] = mapped_column(String(16), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RuntimeHeartbeatRow(Base):
    __tablename__ = "runtime_heartbeats"
    __table_args__ = (
        Index("ix_runtime_heartbeat_cycle", "runtime_id", "cycle_id"),
        Index("ix_runtime_heartbeat_time", "runtime_id", "checked_at"),
    )

    heartbeat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    runtime_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reliability_version: Mapped[str] = mapped_column(String(16), nullable=False)
    cycle_id: Mapped[str] = mapped_column(String(128), nullable=False)
    component: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    health: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    available: Mapped[int] = mapped_column(Integer, nullable=False)
    process_running: Mapped[int | None] = mapped_column(Integer)
    page_available: Mapped[int | None] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[float] = mapped_column(nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RuntimeRecoveryEventRow(Base):
    __tablename__ = "runtime_recovery_events"
    __table_args__ = (
        Index("ix_runtime_recovery_time", "runtime_id", "occurred_at"),
    )

    recovery_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    recovery_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    runtime_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reliability_version: Mapped[str] = mapped_column(String(16), nullable=False)
    component: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ChannelInstanceRow(Base):
    __tablename__ = "channel_instances"
    __table_args__ = (
        UniqueConstraint("platform", "store_id"),
        Index("ix_channel_instance_status", "status"),
    )

    instance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_runtime_version: Mapped[str] = mapped_column(String(16), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(128), nullable=False)
    active_session_id: Mapped[str | None] = mapped_column(String(128))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelRuntimeSessionRow(Base):
    __tablename__ = "channel_runtime_sessions"
    __table_args__ = (
        Index("ix_channel_session_instance", "instance_id", "created_at"),
        Index("ix_channel_session_status", "status"),
    )

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_runtime_version: Mapped[str] = mapped_column(String(16), nullable=False)
    instance_id: Mapped[str] = mapped_column(
        ForeignKey("channel_instances.instance_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_version: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_lease_ref: Mapped[str | None] = mapped_column(String(255))
    heartbeat_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelMessageCursorRow(Base):
    __tablename__ = "channel_message_cursors"

    instance_id: Mapped[str] = mapped_column(
        ForeignKey("channel_instances.instance_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    session_runtime_version: Mapped[str] = mapped_column(String(16), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(String(512))
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_acked_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelMessageInboxRow(Base):
    __tablename__ = "channel_message_inbox"
    __table_args__ = (
        UniqueConstraint("instance_id", "source_sequence"),
        Index(
            "ix_channel_inbox_delivery",
            "instance_id",
            "state",
            "retry_after",
            "source_sequence",
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        ForeignKey("channel_instances.instance_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_runtime_version: Mapped[str] = mapped_column(String(16), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_cursor: Mapped[str] = mapped_column(String(512), nullable=False)
    source_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_reason: Mapped[str | None] = mapped_column(String(128))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    persisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChannelSessionHeartbeatRow(Base):
    __tablename__ = "channel_session_heartbeats"
    __table_args__ = (
        Index("ix_channel_session_heartbeat_time", "instance_id", "checked_at"),
    )

    heartbeat_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_runtime_version: Mapped[str] = mapped_column(String(16), nullable=False)
    cycle_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instance_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128))
    session_status: Mapped[str | None] = mapped_column(String(32))
    adapter_health: Mapped[str] = mapped_column(String(32), nullable=False)
    browser_health: Mapped[str] = mapped_column(String(32), nullable=False)
    gateway_health: Mapped[str] = mapped_column(String(32), nullable=False)
    overall: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BrowserObservationCheckpointRow(Base):
    __tablename__ = "browser_observation_checkpoints"

    stream_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    browser_observation_version: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(512))
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    selector_contract_id: Mapped[str | None] = mapped_column(String(256))
    selector_fingerprint: Mapped[str | None] = mapped_column(String(64))
    page_generation: Mapped[int | None] = mapped_column(Integer)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_capture_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    sync_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128))


class BrowserObservationIdentityRow(Base):
    __tablename__ = "browser_observation_identities"
    __table_args__ = (
        Index("ix_browser_observation_identity_stream", "stream_id"),
    )

    stream_id: Mapped[str] = mapped_column(
        ForeignKey(
            "browser_observation_checkpoints.stream_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    identity_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_observation_version: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sequence: Mapped[int] = mapped_column(Integer, nullable=False)


class PDDWebSocketCheckpointRow(Base):
    __tablename__ = "pdd_websocket_checkpoints"

    stream_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    websocket_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(512))
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    acknowledged_cursor: Mapped[str | None] = mapped_column(String(512))
    last_acknowledged_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    acknowledged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    sync_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128))


class PDDWebSocketInboxRow(Base):
    __tablename__ = "pdd_websocket_inbox"
    __table_args__ = (
        UniqueConstraint("stream_id", "sequence"),
        Index("ix_pdd_websocket_inbox_pending", "stream_id", "state", "sequence"),
    )

    stream_id: Mapped[str] = mapped_column(
        ForeignKey("pdd_websocket_checkpoints.stream_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    identity_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    websocket_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[str] = mapped_column(String(512), nullable=False)
    ack_token: Mapped[str] = mapped_column(String(256), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChannelAgentIdentityRow(Base):
    __tablename__ = "channel_agent_identities"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    user_id: Mapped[str | None] = mapped_column(String(160))
    store_id: Mapped[str | None] = mapped_column(String(160))
    store_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    binding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class PDDProductionSafetyStateRow(Base):
    __tablename__ = "pdd_production_safety_state"

    singleton_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    production_enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False)
    kill_switch_state: Mapped[str] = mapped_column(String(32), nullable=False)
    store_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    store_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)


class PDDStoreAccountRow(Base):
    __tablename__ = "pdd_store_accounts"

    store_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_name: Mapped[str] = mapped_column(String(160), nullable=False)
    credential_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_version: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PDDExecutionStoreBindingRow(Base):
    __tablename__ = "pdd_execution_store_bindings"
    __table_args__ = (
        UniqueConstraint("store_id", "conversation_id", "execution_id"),
    )

    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.execution_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    store_id: Mapped[str] = mapped_column(
        ForeignKey("pdd_store_accounts.store_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bound_by: Mapped[str] = mapped_column(String(160), nullable=False)


class PDDSafetyAuditEventRow(Base):
    __tablename__ = "pdd_safety_audit_events"
    __table_args__ = (
        Index("ix_pdd_safety_audit_time", "timestamp", "audit_event_id"),
    )

    audit_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128), index=True)
    execution_id: Mapped[str | None] = mapped_column(String(128), index=True)
    before: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class PDDSendRateEventRow(Base):
    __tablename__ = "pdd_send_rate_events"
    __table_args__ = (
        Index("ix_pdd_send_rate_store_time", "store_id", "reserved_at"),
        Index(
            "ix_pdd_send_rate_conversation_time",
            "store_id",
            "conversation_id",
            "reserved_at",
        ),
    )

    rate_event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PDDSendTransportReceiptRow(Base):
    __tablename__ = "pdd_send_transport_receipts"

    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.execution_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    safety_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    send_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PDDPilotExecutionReservationRow(Base):
    __tablename__ = "pdd_pilot_execution_reservations"
    __table_args__ = (
        Index("ix_pdd_pilot_store_day", "store_id", "send_day"),
    )

    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.execution_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pilot_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    send_day: Mapped[date] = mapped_column(Date, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PDDPilotEvidenceRow(Base):
    __tablename__ = "pdd_pilot_evidence"
    __table_args__ = (
        Index("ix_pdd_pilot_evidence_time", "recorded_at", "evidence_id"),
    )

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    pilot_contract_version: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    store_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
