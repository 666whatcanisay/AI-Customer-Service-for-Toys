from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from channel_engine.gateway import (
    CONTRACT_VERSION,
    Event as GatewayEvent,
    GatewayAggregateType,
)
from channel_engine.models import (
    Approval,
    ApprovalState,
    Conversation,
    Decision,
    DecisionState,
    Event,
    Execution,
    ExecutionState,
    Message,
    OutboxState,
    Receipt,
)
from channel_engine.models.entities import new_id, utc_now
from channel_engine.observability.bridge import project_domain_event
from channel_engine.observability.models import StructuredEvent
from channel_engine.observability.repository import ObservabilityRepository

from .orm import (
    ApprovalRow,
    ConversationRow,
    DecisionRow,
    EventRow,
    ExecutionRow,
    MessageRow,
    OutboxRow,
    ReceiptRow,
    RuntimeWorkerOwnerRow,
)
from .versioning import RUNTIME_STORAGE_VERSION, RuntimeStorageVersionError


class RecordNotFound(LookupError):
    pass


class OutboxItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outbox_id: str
    runtime_storage_version: str
    event_id: str
    topic: str
    publish_key: str
    payload: dict[str, Any]
    status: OutboxState
    attempt_count: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    published_at: datetime | None
    last_error: str | None


class WorkerOwnership(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_storage_version: str
    worker_id: str
    owner_token: str
    acquired_at: datetime
    heartbeat_at: datetime
    lease_expires_at: datetime


class ChannelEngineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_conversation(self, channel_name: str, external_ref: str) -> Conversation | None:
        row = self.session.scalar(
            select(ConversationRow).where(
                ConversationRow.channel_name == channel_name,
                ConversationRow.external_ref == external_ref,
            )
        )
        return self._conversation_from_row(row) if row else None

    def get_conversation(self, conversation_id: str) -> Conversation:
        row = self.session.get(ConversationRow, conversation_id)
        if row is None:
            raise RecordNotFound(f"conversation not found: {conversation_id}")
        return self._conversation_from_row(row)

    def save_conversation(self, item: Conversation) -> None:
        row = self.session.get(ConversationRow, item.conversation_id)
        values = item.model_dump()
        if row is None:
            self.session.add(ConversationRow(**values))
        else:
            self._assign(row, values)

    def save_message(self, item: Message) -> None:
        row = self.session.get(MessageRow, item.message_id)
        values = item.model_dump()
        if row is None:
            self.session.add(MessageRow(**values))
        else:
            self._assign(row, values)

    def find_message(self, conversation_id: str, external_message_id: str) -> Message | None:
        row = self.session.scalar(
            select(MessageRow).where(
                MessageRow.conversation_id == conversation_id,
                MessageRow.external_message_id == external_message_id,
            )
        )
        return Message.model_validate(self._row_dict(row)) if row else None

    def save_decision(self, item: Decision) -> None:
        row = self.session.get(DecisionRow, item.decision_id)
        values = item.model_dump()
        values["requires_approval"] = int(item.requires_approval)
        if row is None:
            self.session.add(DecisionRow(**values))
        else:
            self._assign(row, values)

    def save_approval(self, item: Approval) -> None:
        row = self.session.get(ApprovalRow, item.approval_id)
        values = item.model_dump()
        if row is None:
            self.session.add(ApprovalRow(**values))
        else:
            self._assign(row, values)

    def save_execution(self, item: Execution) -> None:
        row = self.session.get(ExecutionRow, item.execution_id)
        values = item.model_dump()
        if row is None:
            self.session.add(
                ExecutionRow(
                    runtime_storage_version=RUNTIME_STORAGE_VERSION,
                    **values,
                )
            )
        else:
            self._assert_runtime_version(row.runtime_storage_version)
            self._assign(row, values)

    def get_execution_for_decision(self, decision_id: str) -> Execution | None:
        row = self.session.scalar(
            select(ExecutionRow).where(ExecutionRow.decision_id == decision_id)
        )
        if row is None:
            return None
        self._assert_runtime_version(row.runtime_storage_version)
        return Execution.model_validate(self._row_dict(row))

    def claim_pending_execution(
        self,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Execution | None:
        execution_id = self.session.scalar(
            select(ExecutionRow.execution_id)
            .join(
                ApprovalRow,
                ApprovalRow.approval_id == ExecutionRow.approval_id,
            )
            .join(
                DecisionRow,
                DecisionRow.decision_id == ExecutionRow.decision_id,
            )
            .where(ExecutionRow.state == ExecutionState.PENDING.value)
            .where(
                ApprovalRow.state == ApprovalState.APPROVED.value,
                DecisionRow.state == DecisionState.APPROVED.value,
            )
            .order_by(ExecutionRow.created_at, ExecutionRow.execution_id)
            .limit(1)
        )
        if execution_id is None:
            return None

        lease_token = new_id("execution-lease")
        result = self.session.execute(
            update(ExecutionRow)
            .where(
                ExecutionRow.execution_id == execution_id,
                ExecutionRow.state == ExecutionState.PENDING.value,
                ExecutionRow.approval_id.in_(
                    select(ApprovalRow.approval_id).where(
                        ApprovalRow.state == ApprovalState.APPROVED.value
                    )
                ),
                ExecutionRow.decision_id.in_(
                    select(DecisionRow.decision_id).where(
                        DecisionRow.state == DecisionState.APPROVED.value
                    )
                ),
            )
            .values(
                state=ExecutionState.RUNNING.value,
                attempt=ExecutionRow.attempt + 1,
                lease_owner=worker_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                started_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        return self.get_execution(execution_id)

    def claim_pending_execution_by_id(
        self,
        execution_id: str,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Execution | None:
        """Atomically claim one exact Execution without touching another queue item."""

        lease_token = new_id("execution-lease")
        result = self.session.execute(
            update(ExecutionRow)
            .where(
                ExecutionRow.execution_id == execution_id,
                ExecutionRow.state == ExecutionState.PENDING.value,
                ExecutionRow.approval_id.in_(
                    select(ApprovalRow.approval_id).where(
                        ApprovalRow.state == ApprovalState.APPROVED.value
                    )
                ),
                ExecutionRow.decision_id.in_(
                    select(DecisionRow.decision_id).where(
                        DecisionRow.state == DecisionState.APPROVED.value
                    )
                ),
            )
            .values(
                state=ExecutionState.RUNNING.value,
                attempt=ExecutionRow.attempt + 1,
                lease_owner=worker_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                started_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        return self.get_execution(execution_id)

    def renew_execution_lease(
        self,
        execution_id: str,
        worker_id: str,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> bool:
        result = self.session.execute(
            update(ExecutionRow)
            .where(
                ExecutionRow.execution_id == execution_id,
                ExecutionRow.state == ExecutionState.RUNNING.value,
                ExecutionRow.lease_owner == worker_id,
                ExecutionRow.lease_token == lease_token,
                ExecutionRow.lease_expires_at > now,
            )
            .values(lease_expires_at=lease_expires_at, updated_at=now)
        )
        return result.rowcount == 1

    def finish_claimed_execution(
        self,
        execution_id: str,
        worker_id: str,
        lease_token: str,
        target_state: ExecutionState,
        now: datetime,
        error_code: str | None,
    ) -> Execution | None:
        if target_state not in {
            ExecutionState.SUCCESS,
            ExecutionState.FAILED,
            ExecutionState.UNKNOWN,
        }:
            raise ValueError(f"execution target state must be terminal: {target_state}")
        result = self.session.execute(
            update(ExecutionRow)
            .where(
                ExecutionRow.execution_id == execution_id,
                ExecutionRow.state == ExecutionState.RUNNING.value,
                ExecutionRow.lease_owner == worker_id,
                ExecutionRow.lease_token == lease_token,
                ExecutionRow.lease_expires_at > now,
            )
            .values(
                state=target_state.value,
                completed_at=now,
                error_code=error_code,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        return self.get_execution(execution_id)

    def list_expired_running_executions(
        self, now: datetime, limit: int = 100
    ) -> list[Execution]:
        rows = self.session.scalars(
            select(ExecutionRow)
            .where(
                ExecutionRow.state == ExecutionState.RUNNING.value,
                ExecutionRow.lease_expires_at.is_not(None),
                ExecutionRow.lease_expires_at <= now,
            )
            .order_by(ExecutionRow.lease_expires_at, ExecutionRow.execution_id)
            .limit(limit)
        ).all()
        for row in rows:
            self._assert_runtime_version(row.runtime_storage_version)
        return [Execution.model_validate(self._row_dict(row)) for row in rows]

    def expire_execution_lease(
        self,
        execution_id: str,
        lease_token: str,
        now: datetime,
        error_code: str,
    ) -> Execution | None:
        result = self.session.execute(
            update(ExecutionRow)
            .where(
                ExecutionRow.execution_id == execution_id,
                ExecutionRow.state == ExecutionState.RUNNING.value,
                ExecutionRow.lease_token == lease_token,
                ExecutionRow.lease_expires_at <= now,
            )
            .values(
                state=ExecutionState.UNKNOWN.value,
                completed_at=now,
                error_code=error_code,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        return self.get_execution(execution_id)

    def append_receipt(self, item: Receipt) -> None:
        if self.session.get(ReceiptRow, item.receipt_id) is not None:
            raise ValueError(f"receipt already exists: {item.receipt_id}")
        existing_execution_receipt = self.session.scalar(
            select(ReceiptRow.receipt_id).where(
                ReceiptRow.execution_id == item.execution_id
            )
        )
        if existing_execution_receipt is not None:
            raise ValueError(
                f"execution receipt is immutable: {existing_execution_receipt}"
            )
        values = item.model_dump(mode="json")
        values["recorded_at"] = item.recorded_at
        self.session.add(
            ReceiptRow(
                runtime_storage_version=RUNTIME_STORAGE_VERSION,
                **values,
            )
        )

    def append_event(self, item: Event) -> None:
        if self.session.get(EventRow, item.event_id) is not None:
            raise ValueError(f"event already exists: {item.event_id}")
        self.session.add(
            EventRow(
                event_id=item.event_id,
                runtime_storage_version=RUNTIME_STORAGE_VERSION,
                aggregate_type=item.aggregate_type,
                aggregate_id=item.aggregate_id,
                event_type=item.event_type.value,
                payload=item.payload,
                correlation_id=item.correlation_id,
                occurred_at=item.occurred_at,
            )
        )
        gateway_event = GatewayEvent(
            contract_version=CONTRACT_VERSION,
            event_id=item.event_id,
            correlation_id=item.correlation_id,
            causation_id=None,
            source="CHANNEL_ENGINE",
            event_type=item.event_type,
            aggregate_type=GatewayAggregateType(item.aggregate_type),
            aggregate_id=item.aggregate_id,
            payload=item.payload,
            occurred_at=item.occurred_at,
        )
        self.session.add(
            OutboxRow(
                outbox_id=f"outbox-{item.event_id}",
                runtime_storage_version=RUNTIME_STORAGE_VERSION,
                event_id=item.event_id,
                topic=item.event_type.value,
                publish_key=item.event_id,
                payload=gateway_event.model_dump(mode="json"),
                status=OutboxState.PENDING.value,
                attempt_count=0,
                next_attempt_at=item.occurred_at,
                created_at=item.occurred_at,
            )
        )
        operational_event = project_domain_event(item)
        if operational_event is not None:
            self.append_observability_event(operational_event)

    def append_observability_event(self, item: StructuredEvent) -> StructuredEvent:
        """Append a redacted operator event in the caller's transaction."""

        return ObservabilityRepository(self.session).append(item)

    def get_message(self, message_id: str) -> Message:
        row = self.session.get(MessageRow, message_id)
        if row is None:
            raise RecordNotFound(f"message not found: {message_id}")
        return Message.model_validate(self._row_dict(row))

    def get_decision(self, decision_id: str) -> Decision:
        row = self.session.get(DecisionRow, decision_id)
        if row is None:
            raise RecordNotFound(f"decision not found: {decision_id}")
        values = self._row_dict(row)
        values["requires_approval"] = bool(values["requires_approval"])
        return Decision.model_validate(values)

    def find_decision_for_message(self, message_id: str) -> Decision | None:
        row = self.session.scalar(
            select(DecisionRow).where(DecisionRow.message_id == message_id)
        )
        if row is None:
            return None
        values = self._row_dict(row)
        values["requires_approval"] = bool(values["requires_approval"])
        return Decision.model_validate(values)

    def get_approval_for_decision(self, decision_id: str) -> Approval | None:
        row = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.decision_id == decision_id)
        )
        return Approval.model_validate(self._row_dict(row)) if row else None

    def get_execution(self, execution_id: str) -> Execution:
        row = self.session.get(ExecutionRow, execution_id)
        if row is None:
            raise RecordNotFound(f"execution not found: {execution_id}")
        self._assert_runtime_version(row.runtime_storage_version)
        return Execution.model_validate(self._row_dict(row))

    def get_receipt_for_execution(self, execution_id: str) -> Receipt | None:
        row = self.session.scalar(
            select(ReceiptRow).where(ReceiptRow.execution_id == execution_id)
        )
        if row is None:
            return None
        self._assert_runtime_version(row.runtime_storage_version)
        return Receipt.model_validate(self._row_dict(row))

    def acquire_worker_ownership(
        self,
        worker_id: str,
        owner_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> WorkerOwnership | None:
        result = self.session.execute(
            update(RuntimeWorkerOwnerRow)
            .where(
                RuntimeWorkerOwnerRow.worker_id == worker_id,
                RuntimeWorkerOwnerRow.runtime_storage_version
                == RUNTIME_STORAGE_VERSION,
                or_(
                    RuntimeWorkerOwnerRow.owner_token == owner_token,
                    RuntimeWorkerOwnerRow.lease_expires_at <= now,
                ),
            )
            .values(
                runtime_storage_version=RUNTIME_STORAGE_VERSION,
                owner_token=owner_token,
                acquired_at=now,
                heartbeat_at=now,
                lease_expires_at=lease_expires_at,
            )
        )
        if result.rowcount == 1:
            self.session.expire_all()
            row = self.session.get(RuntimeWorkerOwnerRow, worker_id)
            assert row is not None
            return self._worker_ownership_from_row(row)

        if self.session.get(RuntimeWorkerOwnerRow, worker_id) is not None:
            return None

        try:
            with self.session.begin_nested():
                row = RuntimeWorkerOwnerRow(
                    worker_id=worker_id,
                    runtime_storage_version=RUNTIME_STORAGE_VERSION,
                    owner_token=owner_token,
                    acquired_at=now,
                    heartbeat_at=now,
                    lease_expires_at=lease_expires_at,
                )
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            return None
        return self._worker_ownership_from_row(row)

    def renew_worker_ownership(
        self,
        worker_id: str,
        owner_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> WorkerOwnership | None:
        result = self.session.execute(
            update(RuntimeWorkerOwnerRow)
            .where(
                RuntimeWorkerOwnerRow.worker_id == worker_id,
                RuntimeWorkerOwnerRow.runtime_storage_version
                == RUNTIME_STORAGE_VERSION,
                RuntimeWorkerOwnerRow.owner_token == owner_token,
                RuntimeWorkerOwnerRow.lease_expires_at > now,
            )
            .values(heartbeat_at=now, lease_expires_at=lease_expires_at)
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        row = self.session.get(RuntimeWorkerOwnerRow, worker_id)
        assert row is not None
        return self._worker_ownership_from_row(row)

    def release_worker_ownership(self, worker_id: str, owner_token: str) -> bool:
        row = self.session.get(RuntimeWorkerOwnerRow, worker_id)
        if row is None or row.owner_token != owner_token:
            return False
        self._assert_runtime_version(row.runtime_storage_version)
        self.session.delete(row)
        return True

    def list_pending_outbox(self, limit: int = 100) -> list[OutboxItem]:
        rows = self.session.scalars(
            select(OutboxRow)
            .where(OutboxRow.status == OutboxState.PENDING.value)
            .order_by(OutboxRow.created_at)
            .limit(limit)
        ).all()
        return [self._outbox_from_row(row) for row in rows]

    def list_outbox(self, limit: int = 100) -> list[OutboxItem]:
        rows = self.session.scalars(
            select(OutboxRow).order_by(OutboxRow.created_at).limit(limit)
        ).all()
        return [self._outbox_from_row(row) for row in rows]

    def claim_outbox(
        self,
        publisher_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> OutboxItem | None:
        due_pending = and_(
            OutboxRow.status == OutboxState.PENDING.value,
            or_(
                OutboxRow.next_attempt_at.is_(None),
                OutboxRow.next_attempt_at <= now,
            ),
        )
        expired_processing = and_(
            OutboxRow.status == OutboxState.PROCESSING.value,
            OutboxRow.lease_expires_at.is_not(None),
            OutboxRow.lease_expires_at <= now,
        )
        outbox_id = self.session.scalar(
            select(OutboxRow.outbox_id)
            .where(or_(due_pending, expired_processing))
            .order_by(OutboxRow.created_at, OutboxRow.outbox_id)
            .limit(1)
        )
        if outbox_id is None:
            return None

        lease_token = new_id("outbox-lease")
        result = self.session.execute(
            update(OutboxRow)
            .where(
                OutboxRow.outbox_id == outbox_id,
                or_(due_pending, expired_processing),
            )
            .values(
                status=OutboxState.PROCESSING.value,
                attempt_count=func.coalesce(OutboxRow.attempt_count, 0) + 1,
                lease_owner=publisher_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
            )
        )
        if result.rowcount != 1:
            return None
        self.session.expire_all()
        row = self.session.get(OutboxRow, outbox_id)
        assert row is not None
        return self._outbox_from_row(row)

    def complete_outbox_publish(
        self,
        outbox_id: str,
        publisher_id: str,
        lease_token: str,
        published_at: datetime,
    ) -> bool:
        result = self.session.execute(
            update(OutboxRow)
            .where(
                OutboxRow.outbox_id == outbox_id,
                OutboxRow.status == OutboxState.PROCESSING.value,
                OutboxRow.lease_owner == publisher_id,
                OutboxRow.lease_token == lease_token,
                OutboxRow.lease_expires_at > published_at,
            )
            .values(
                status=OutboxState.PUBLISHED.value,
                published_at=published_at,
                last_error=None,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
        )
        return result.rowcount == 1

    def fail_outbox_publish(
        self,
        outbox_id: str,
        publisher_id: str,
        lease_token: str,
        error: str,
        failed_at: datetime,
        next_attempt_at: datetime,
        terminal: bool,
    ) -> bool:
        result = self.session.execute(
            update(OutboxRow)
            .where(
                OutboxRow.outbox_id == outbox_id,
                OutboxRow.status == OutboxState.PROCESSING.value,
                OutboxRow.lease_owner == publisher_id,
                OutboxRow.lease_token == lease_token,
                OutboxRow.lease_expires_at > failed_at,
            )
            .values(
                status=(
                    OutboxState.FAILED.value
                    if terminal
                    else OutboxState.PENDING.value
                ),
                next_attempt_at=next_attempt_at,
                last_error=error[:1_000],
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
        )
        return result.rowcount == 1

    def mark_outbox_published(self, outbox_id: str, published_at: datetime | None = None) -> None:
        row = self.session.get(OutboxRow, outbox_id)
        if row is None:
            raise RecordNotFound(f"outbox item not found: {outbox_id}")
        self._assert_runtime_version(row.runtime_storage_version)
        row.status = OutboxState.PUBLISHED.value
        row.published_at = published_at or utc_now()
        row.last_error = None
        row.lease_owner = None
        row.lease_token = None
        row.lease_expires_at = None

    @staticmethod
    def _assert_runtime_version(version: str) -> None:
        if version != RUNTIME_STORAGE_VERSION:
            raise RuntimeStorageVersionError(
                f"unsupported persisted runtime record version: {version}"
            )

    @staticmethod
    def _assign(row: object, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(row, key, value.value if hasattr(value, "value") else value)

    @staticmethod
    def _row_dict(row: object) -> dict[str, Any]:
        return {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns  # type: ignore[attr-defined]
            if column.name != "runtime_storage_version"
        }

    @staticmethod
    def _conversation_from_row(row: ConversationRow) -> Conversation:
        return Conversation.model_validate(ChannelEngineRepository._row_dict(row))

    @staticmethod
    def _outbox_from_row(row: OutboxRow) -> OutboxItem:
        ChannelEngineRepository._assert_runtime_version(
            row.runtime_storage_version
        )
        return OutboxItem(
            outbox_id=row.outbox_id,
            runtime_storage_version=row.runtime_storage_version,
            event_id=row.event_id,
            topic=row.topic,
            publish_key=row.publish_key,
            payload=row.payload,
            status=OutboxState(row.status),
            attempt_count=row.attempt_count or 0,
            next_attempt_at=row.next_attempt_at,
            lease_owner=row.lease_owner,
            lease_token=row.lease_token,
            lease_expires_at=row.lease_expires_at,
            created_at=row.created_at,
            published_at=row.published_at,
            last_error=row.last_error,
        )

    @staticmethod
    def _worker_ownership_from_row(row: RuntimeWorkerOwnerRow) -> WorkerOwnership:
        ChannelEngineRepository._assert_runtime_version(
            row.runtime_storage_version
        )

        def aware(value: datetime) -> datetime:
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

        return WorkerOwnership(
            runtime_storage_version=row.runtime_storage_version,
            worker_id=row.worker_id,
            owner_token=row.owner_token,
            acquired_at=aware(row.acquired_at),
            heartbeat_at=aware(row.heartbeat_at),
            lease_expires_at=aware(row.lease_expires_at),
        )
