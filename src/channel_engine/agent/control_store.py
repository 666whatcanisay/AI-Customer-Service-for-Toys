from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from channel_agent.control_v2 import (
    AgentAssistantEvent,
    AgentAssistantSnapshot,
    AgentCommandEnvelope,
    AgentObservationAck,
    AgentObservationSubmission,
    AgentReceiptAck,
    AgentReceiptSubmission,
)
from channel_engine.storage.orm import (
    ChannelAgentAssistantEventRow,
    ChannelAgentAssistantSnapshotRow,
    ChannelAgentCommandRow,
    ChannelAgentObservationRow,
    ChannelAgentReceiptRow,
    ChannelAgentReplayNonceRow,
)


class AgentControlStoreError(RuntimeError):
    pass


class AgentControlConflict(AgentControlStoreError):
    pass


class SqlAlchemyReplayNonceStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def consume(self, namespace: str, nonce: str, timestamp: int, expires_at: int) -> bool:
        expiry = datetime.fromtimestamp(expires_at, tz=UTC)
        now = datetime.fromtimestamp(timestamp, tz=UTC)
        with self._session_factory() as session:
            try:
                with session.begin():
                    session.execute(
                        delete(ChannelAgentReplayNonceRow).where(
                            ChannelAgentReplayNonceRow.expires_at <= now
                        )
                    )
                    session.add(
                        ChannelAgentReplayNonceRow(
                            namespace=namespace,
                            nonce=nonce,
                            request_timestamp=timestamp,
                            expires_at=expiry,
                        )
                    )
                return True
            except IntegrityError:
                session.rollback()
                return False


class AgentControlStore:
    """Transactional Host-side inbox, command queue and immutable Agent receipts."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock=lambda: datetime.now(UTC),  # type: ignore[no-untyped-def]
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def persist_observation(self, value: AgentObservationSubmission) -> AgentObservationAck:
        now = self._clock().astimezone(UTC)
        status = "PERSISTED"
        with self._session_factory() as session:
            try:
                with session.begin():
                    session.add(
                        ChannelAgentObservationRow(
                            observation_id=value.observation_id,
                            agent_id=value.agent_id,
                            device_id=value.device_id,
                            store_id=value.store_id,
                            conversation_id=value.conversation_id,
                            external_message_id=value.external_message_id,
                            source_cursor=value.source_cursor,
                            source_sequence=value.source_sequence,
                            payload_digest=value.payload_digest,
                            payload=value.payload,
                            captured_at=value.captured_at,
                            persisted_at=now,
                            expires_at=now + timedelta(hours=24),
                            forwarded_at=None,
                        )
                    )
                    session.add(
                        ChannelAgentAssistantEventRow(
                            event_id=_event_id("MESSAGE_ACCEPTED", value.observation_id),
                            event_type="MESSAGE_ACCEPTED",
                            agent_id=value.agent_id,
                            device_id=value.device_id,
                            store_id=value.store_id,
                            conversation_id=value.conversation_id,
                            turn_id=None,
                            decision_id=None,
                            status="PERSISTED",
                            event_metadata={
                                "observation_id": value.observation_id,
                                "external_message_id": value.external_message_id,
                                "origin": value.payload.get("origin", "LIVE_PDD"),
                                "contains_customer_content": False,
                            },
                            created_at=now,
                        )
                    )
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(ChannelAgentObservationRow).where(
                        ChannelAgentObservationRow.agent_id == value.agent_id,
                        ChannelAgentObservationRow.store_id == value.store_id,
                        ChannelAgentObservationRow.external_message_id
                        == value.external_message_id,
                    )
                )
                if existing is None:
                    existing = session.get(ChannelAgentObservationRow, value.observation_id)
                if (
                    existing is None
                    or existing.device_id != value.device_id
                    or existing.payload_digest != value.payload_digest
                    or existing.conversation_id != value.conversation_id
                ):
                    raise AgentControlConflict(
                        "duplicate message identity has different content or scope"
                    )
                status = "DUPLICATE"
                now = _aware(existing.persisted_at)
        return AgentObservationAck(
            observation_id=value.observation_id,
            status=status,
            acknowledged_cursor=value.source_cursor,
            persisted_at=now,
        )

    def pending_observations(self, *, limit: int = 100) -> tuple[AgentObservationSubmission, ...]:
        """Read committed Host inbox rows for the background Buffer worker."""

        now = self._clock().astimezone(UTC)
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChannelAgentObservationRow)
                .where(
                    ChannelAgentObservationRow.forwarded_at.is_(None),
                    ChannelAgentObservationRow.expires_at > now,
                )
                .order_by(
                    ChannelAgentObservationRow.persisted_at,
                    ChannelAgentObservationRow.source_sequence,
                    ChannelAgentObservationRow.observation_id,
                )
                .limit(max(1, min(limit, 500)))
            ).all()
            return tuple(
                AgentObservationSubmission(
                    observation_id=row.observation_id,
                    agent_id=row.agent_id,
                    device_id=row.device_id,
                    store_id=row.store_id,
                    conversation_id=row.conversation_id,
                    external_message_id=row.external_message_id,
                    source_cursor=row.source_cursor,
                    source_sequence=row.source_sequence,
                    payload_digest=row.payload_digest,
                    payload=dict(row.payload),
                    captured_at=_aware(row.captured_at),
                )
                for row in rows
            )

    def mark_observation_forwarded(self, observation_id: str) -> None:
        with self._session_factory() as session, session.begin():
            row = session.get(ChannelAgentObservationRow, observation_id)
            if row is None:
                raise AgentControlStoreError("observation does not exist")
            if row.forwarded_at is None:
                row.forwarded_at = self._clock().astimezone(UTC)

    def assistant_scope_for_conversation(
        self,
        store_id: str,
        conversation_id: str,
    ) -> tuple[str, str] | None:
        """Recover Agent/device routing after a Host worker restart."""

        with self._session_factory() as session:
            row = session.scalar(
                select(ChannelAgentObservationRow)
                .where(
                    ChannelAgentObservationRow.store_id == store_id,
                    ChannelAgentObservationRow.conversation_id == conversation_id,
                )
                .order_by(
                    ChannelAgentObservationRow.persisted_at.desc(),
                    ChannelAgentObservationRow.observation_id.desc(),
                )
                .limit(1)
            )
            return None if row is None else (row.agent_id, row.device_id)

    def append_assistant_event(
        self,
        *,
        event_id: str,
        event_type: str,
        agent_id: str,
        device_id: str,
        store_id: str,
        status: str,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        decision_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentAssistantEvent:
        now = self._clock().astimezone(UTC)
        with self._session_factory() as session:
            try:
                with session.begin():
                    row = ChannelAgentAssistantEventRow(
                        event_id=event_id,
                        event_type=event_type,
                        agent_id=agent_id,
                        device_id=device_id,
                        store_id=store_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        decision_id=decision_id,
                        status=status,
                        event_metadata=metadata or {},
                        created_at=now,
                    )
                    session.add(row)
                    session.flush()
                    sequence_id = row.sequence_id
            except IntegrityError:
                session.rollback()
                row = session.scalar(
                    select(ChannelAgentAssistantEventRow).where(
                        ChannelAgentAssistantEventRow.event_id == event_id
                    )
                )
                if row is None:
                    raise AgentControlConflict("assistant event identity conflict")
                sequence_id = row.sequence_id
                if (
                    row.event_type != event_type
                    or row.agent_id != agent_id
                    or row.device_id != device_id
                    or row.store_id != store_id
                    or row.conversation_id != conversation_id
                    or row.turn_id != turn_id
                    or row.decision_id != decision_id
                    or row.status != status
                    or dict(row.event_metadata) != (metadata or {})
                ):
                    raise AgentControlConflict("assistant event identity conflict")
                now = _aware(row.created_at)
        return AgentAssistantEvent(
            event_id=event_id,
            sequence_id=sequence_id,
            event_type=event_type,  # type: ignore[arg-type]
            agent_id=agent_id,
            device_id=device_id,
            store_id=store_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            decision_id=decision_id,
            status=status,
            metadata=metadata or {},
            created_at=now,
        )

    def poll_assistant_events(
        self,
        agent_id: str,
        device_id: str,
        *,
        after_sequence_id: int = 0,
        limit: int = 100,
    ) -> tuple[AgentAssistantEvent, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChannelAgentAssistantEventRow)
                .where(
                    ChannelAgentAssistantEventRow.agent_id == agent_id,
                    ChannelAgentAssistantEventRow.device_id == device_id,
                    ChannelAgentAssistantEventRow.sequence_id > after_sequence_id,
                )
                .order_by(ChannelAgentAssistantEventRow.sequence_id)
                .limit(max(1, min(limit, 100)))
            ).all()
            return tuple(
                AgentAssistantEvent(
                    event_id=row.event_id,
                    sequence_id=row.sequence_id,
                    event_type=row.event_type,  # type: ignore[arg-type]
                    agent_id=row.agent_id,
                    device_id=row.device_id,
                    store_id=row.store_id,
                    conversation_id=row.conversation_id,
                    turn_id=row.turn_id,
                    decision_id=row.decision_id,
                    status=row.status,
                    metadata=dict(row.event_metadata),
                    created_at=_aware(row.created_at),
                )
                for row in rows
            )

    def persist_assistant_snapshot(
        self, value: AgentAssistantSnapshot
    ) -> AgentAssistantSnapshot:
        now = self._clock().astimezone(UTC)
        scope_key = _assistant_scope_key(
            value.agent_id,
            value.device_id,
            value.store_id,
            value.conversation_id,
        )
        with self._session_factory() as session, session.begin():
            row = session.get(ChannelAgentAssistantSnapshotRow, scope_key)
            revision = 1 if row is None else row.revision + 1
            stored = value.model_copy(
                update={
                    "revision": revision,
                    "updated_at": now,
                    "expires_at": now + timedelta(minutes=30),
                }
            )
            payload = stored.model_dump(mode="json")
            if row is None:
                session.add(
                    ChannelAgentAssistantSnapshotRow(
                        scope_key=scope_key,
                        agent_id=stored.agent_id,
                        device_id=stored.device_id,
                        store_id=stored.store_id,
                        conversation_id=stored.conversation_id,
                        revision=revision,
                        snapshot_json=payload,
                        updated_at=now,
                        expires_at=stored.expires_at,
                    )
                )
            else:
                row.revision = revision
                row.snapshot_json = payload
                row.updated_at = now
                row.expires_at = stored.expires_at
            return stored

    def assistant_snapshot(
        self,
        agent_id: str,
        device_id: str,
        *,
        store_id: str | None = None,
        conversation_id: str | None = None,
    ) -> AgentAssistantSnapshot | None:
        now = self._clock().astimezone(UTC)
        statement = select(ChannelAgentAssistantSnapshotRow).where(
            ChannelAgentAssistantSnapshotRow.agent_id == agent_id,
            ChannelAgentAssistantSnapshotRow.device_id == device_id,
            ChannelAgentAssistantSnapshotRow.expires_at > now,
        )
        if store_id is not None:
            statement = statement.where(
                ChannelAgentAssistantSnapshotRow.store_id == store_id
            )
        if conversation_id is not None:
            statement = statement.where(
                ChannelAgentAssistantSnapshotRow.conversation_id == conversation_id
            )
        with self._session_factory() as session:
            row = session.scalar(
                statement.order_by(
                    ChannelAgentAssistantSnapshotRow.updated_at.desc(),
                    ChannelAgentAssistantSnapshotRow.scope_key,
                ).limit(1)
            )
            if row is None:
                return None
            return AgentAssistantSnapshot.model_validate_json(
                json.dumps(row.snapshot_json, ensure_ascii=False, separators=(",", ":"))
            )

    def purge_expired(self) -> dict[str, int]:
        now = self._clock().astimezone(UTC)
        event_cutoff = now - timedelta(hours=24)
        with self._session_factory() as session, session.begin():
            observations = session.execute(
                delete(ChannelAgentObservationRow).where(
                    ChannelAgentObservationRow.expires_at <= now
                )
            ).rowcount
            snapshots = session.execute(
                delete(ChannelAgentAssistantSnapshotRow).where(
                    ChannelAgentAssistantSnapshotRow.expires_at <= now
                )
            ).rowcount
            events = session.execute(
                delete(ChannelAgentAssistantEventRow).where(
                    ChannelAgentAssistantEventRow.created_at <= event_cutoff
                )
            ).rowcount
        return {
            "observations": int(observations or 0),
            "snapshots": int(snapshots or 0),
            "events": int(events or 0),
        }

    def enqueue_command(self, command: AgentCommandEnvelope) -> str:
        with self._session_factory() as session:
            try:
                with session.begin():
                    session.add(
                        ChannelAgentCommandRow(
                            command_id=command.command_id,
                            agent_id=command.agent_id,
                            device_id=command.device_id,
                            store_id=command.store_id,
                            execution_id=command.execution_authorization.execution_id,
                            command_json=command.model_dump(mode="json"),
                            status="PENDING",
                            delivery_attempts=0,
                            issued_at=command.issued_at,
                            expires_at=command.expires_at,
                            delivered_at=None,
                            completed_at=None,
                        )
                    )
                return "QUEUED"
            except IntegrityError:
                session.rollback()
                existing = session.get(ChannelAgentCommandRow, command.command_id)
                if existing is None:
                    existing = session.scalar(
                        select(ChannelAgentCommandRow).where(
                            ChannelAgentCommandRow.execution_id
                            == command.execution_authorization.execution_id
                        )
                    )
                if existing is None or existing.command_json != command.model_dump(mode="json"):
                    raise AgentControlConflict("command identity is bound to different content")
                return "DUPLICATE"

    def poll_command(self, agent_id: str, device_id: str) -> AgentCommandEnvelope | None:
        now = self._clock().astimezone(UTC)
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(ChannelAgentCommandRow)
                .where(
                    ChannelAgentCommandRow.agent_id == agent_id,
                    ChannelAgentCommandRow.device_id == device_id,
                    ChannelAgentCommandRow.status.in_(("PENDING", "DELIVERED")),
                    ChannelAgentCommandRow.expires_at > now,
                )
                .order_by(ChannelAgentCommandRow.issued_at, ChannelAgentCommandRow.command_id)
                .limit(1)
            )
            if row is None:
                return None
            row.status = "DELIVERED"
            row.delivery_attempts += 1
            row.delivered_at = now
            return AgentCommandEnvelope.model_validate_json(
                json.dumps(row.command_json, ensure_ascii=False, separators=(",", ":"))
            )

    def command(self, command_id: str) -> AgentCommandEnvelope | None:
        with self._session_factory() as session:
            row = session.get(ChannelAgentCommandRow, command_id)
            if row is None:
                return None
            return AgentCommandEnvelope.model_validate_json(
                json.dumps(row.command_json, ensure_ascii=False, separators=(",", ":"))
            )

    def persist_receipt(self, value: AgentReceiptSubmission) -> AgentReceiptAck:
        now = self._clock().astimezone(UTC)
        receipt = value.receipt
        command = None
        status = "PERSISTED"
        with self._session_factory() as session:
            command = session.scalar(
                select(ChannelAgentCommandRow).where(
                    ChannelAgentCommandRow.execution_id == receipt.execution_id
                )
            )
            if command is None:
                raise AgentControlConflict("receipt has no issued Agent command")
            if command.agent_id != value.agent_id or command.device_id != value.device_id:
                raise AgentControlConflict("receipt device does not own the command")
            try:
                with session.begin_nested():
                    session.add(
                        ChannelAgentReceiptRow(
                            receipt_id=receipt.receipt_id,
                            execution_id=receipt.execution_id,
                            send_key=receipt.send_key,
                            agent_id=value.agent_id,
                            device_id=value.device_id,
                            store_id=command.store_id,
                            outcome=receipt.outcome,
                            receipt_json=receipt.model_dump(mode="json"),
                            persisted_at=now,
                        )
                    )
                    session.flush()
            except IntegrityError:
                existing = session.get(ChannelAgentReceiptRow, receipt.receipt_id)
                if existing is None:
                    existing = session.scalar(
                        select(ChannelAgentReceiptRow).where(
                            ChannelAgentReceiptRow.execution_id == receipt.execution_id
                        )
                    )
                if existing is None or existing.receipt_json != receipt.model_dump(mode="json"):
                    raise AgentControlConflict("immutable receipt conflicts with persisted result")
                status = "DUPLICATE"
                now = _aware(existing.persisted_at)
            command.status = "COMPLETED"
            command.completed_at = now
            session.commit()
        return AgentReceiptAck(
            receipt_id=receipt.receipt_id,
            status=status,
            persisted_at=now,
        )

    def receipt(self, receipt_id: str) -> dict[str, object] | None:
        with self._session_factory() as session:
            row = session.get(ChannelAgentReceiptRow, receipt_id)
            return None if row is None else dict(row.receipt_json)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _event_id(event_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{event_type}:{source_id}".encode("utf-8")).hexdigest()
    return f"assistant-event:{digest}"


def _assistant_scope_key(
    agent_id: str, device_id: str, store_id: str, conversation_id: str
) -> str:
    value = f"{agent_id}\0{device_id}\0{store_id}\0{conversation_id}"
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "AgentControlConflict",
    "AgentControlStore",
    "AgentControlStoreError",
    "SqlAlchemyReplayNonceStore",
]
