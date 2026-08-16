from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from channel_engine.channel import ChannelMessageV1
from channel_engine.models.entities import utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork
from channel_engine.storage.orm import (
    ChannelMessageCursorRow,
    ChannelMessageInboxRow,
)

from .models import (
    CHANNEL_SESSION_RUNTIME_VERSION,
    InboxMessageState,
    InboundEnvelope,
    MessageAck,
    MessageCursor,
    MessageDelivery,
    PersistedMessage,
    RetryMarker,
)
from .persistence import (
    ChannelSessionStore,
    SessionRecordNotFound,
    message_fingerprint,
)


class CursorConflict(ValueError):
    pass


class CursorGapDetected(CursorConflict):
    pass


class MessageDeliveryConflict(ValueError):
    pass


class MessageReliabilityService:
    """Persistent at-least-once inbox: persist, deliver, then ACK."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        store: ChannelSessionStore,
        *,
        max_delivery_attempts: int = 5,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if max_delivery_attempts < 1 or max_delivery_attempts > 100:
            raise ValueError("max_delivery_attempts must be between 1 and 100")
        self._uow_factory = uow_factory
        self._store = store
        self.max_delivery_attempts = max_delivery_attempts
        self._clock = clock

    def persist_batch(
        self,
        instance_id: str,
        messages: Iterable[ChannelMessageV1],
    ) -> tuple[PersistedMessage, ...]:
        cursor = self._store.get_cursor(instance_id)
        envelopes = tuple(
            InboundEnvelope(
                message=message,
                source_cursor=f"engine:{cursor.last_sequence + index}",
                source_sequence=cursor.last_sequence + index,
            )
            for index, message in enumerate(messages, start=1)
        )
        return self.persist(instance_id, envelopes)

    def persist(
        self,
        instance_id: str,
        envelopes: Iterable[InboundEnvelope],
    ) -> tuple[PersistedMessage, ...]:
        instance = self._store.get_instance(instance_id)
        now = self._clock()
        results: list[PersistedMessage] = []
        with self._uow_factory() as uow:
            assert uow.session is not None
            cursor = uow.session.get(ChannelMessageCursorRow, instance_id)
            if cursor is None:
                raise SessionRecordNotFound(instance_id)
            for envelope in envelopes:
                message = envelope.message
                if message.store_id != instance.store_id:
                    raise MessageDeliveryConflict(
                        "message store_id does not match channel instance"
                    )
                if message.channel != instance.platform:
                    raise MessageDeliveryConflict(
                        "message channel does not match instance platform"
                    )
                fingerprint = message_fingerprint(message)
                existing = uow.session.get(
                    ChannelMessageInboxRow,
                    {"instance_id": instance_id, "message_id": message.message_id},
                )
                if existing is not None:
                    if (
                        existing.payload_fingerprint != fingerprint
                        or existing.source_cursor != envelope.source_cursor
                        or existing.source_sequence != envelope.source_sequence
                    ):
                        raise MessageDeliveryConflict(
                            "message identity was reused with different payload or cursor"
                        )
                    results.append(self._persisted(existing, duplicate=True))
                    continue

                occupied = uow.session.scalar(
                    select(ChannelMessageInboxRow.message_id).where(
                        ChannelMessageInboxRow.instance_id == instance_id,
                        ChannelMessageInboxRow.source_sequence
                        == envelope.source_sequence,
                    )
                )
                if occupied is not None:
                    raise CursorConflict(
                        "source sequence is already bound to another message"
                    )
                expected = cursor.last_sequence + 1
                if envelope.source_sequence > expected:
                    raise CursorGapDetected(
                        f"source sequence gap: expected {expected}, "
                        f"received {envelope.source_sequence}"
                    )
                if envelope.source_sequence < expected:
                    raise CursorConflict(
                        "source sequence moved backwards without a known duplicate"
                    )
                delivery_id = self._delivery_id(instance_id, message.message_id)
                row = ChannelMessageInboxRow(
                    instance_id=instance_id,
                    message_id=message.message_id,
                    session_runtime_version=CHANNEL_SESSION_RUNTIME_VERSION,
                    delivery_id=delivery_id,
                    store_id=message.store_id,
                    channel=message.channel,
                    conversation_id=message.conversation_id,
                    sender=message.sender,
                    content=message.content,
                    message_timestamp=message.timestamp,
                    payload_fingerprint=fingerprint,
                    source_cursor=envelope.source_cursor,
                    source_sequence=envelope.source_sequence,
                    state=InboxMessageState.PERSISTED.value,
                    delivery_attempts=0,
                    retry_reason=None,
                    retry_after=None,
                    persisted_at=now,
                    last_delivered_at=None,
                    acknowledged_at=None,
                )
                uow.session.add(row)
                cursor.cursor_value = envelope.source_cursor
                cursor.last_sequence = envelope.source_sequence
                cursor.revision += 1
                cursor.updated_at = now
                uow.session.flush()
                results.append(self._persisted(row, duplicate=False))
        return tuple(results)

    def receive_pending(
        self, instance_id: str, *, limit: int = 100
    ) -> tuple[MessageDelivery, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("delivery limit must be between 1 and 100")
        self._store.get_instance(instance_id)
        now = self._clock()
        deliveries: list[MessageDelivery] = []
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(ChannelMessageInboxRow)
                .where(
                    ChannelMessageInboxRow.instance_id == instance_id,
                    ChannelMessageInboxRow.state == InboxMessageState.PERSISTED.value,
                    or_(
                        ChannelMessageInboxRow.retry_after.is_(None),
                        ChannelMessageInboxRow.retry_after <= now,
                    ),
                )
                .order_by(ChannelMessageInboxRow.source_sequence)
            ).all()
            for row in rows:
                if len(deliveries) >= limit:
                    break
                if row.delivery_attempts >= self.max_delivery_attempts:
                    row.state = InboxMessageState.MANUAL_INTERVENTION.value
                    row.retry_reason = "DELIVERY_BUDGET_EXHAUSTED"
                    row.retry_after = None
                    continue
                row.delivery_attempts += 1
                row.last_delivered_at = now
                marker = (
                    RetryMarker(
                        delivery_id=row.delivery_id,
                        attempt=row.delivery_attempts,
                        reason_code=row.retry_reason,
                        retry_after=row.retry_after,
                    )
                    if row.retry_reason is not None and row.retry_after is not None
                    else None
                )
                row.retry_reason = None
                row.retry_after = None
                deliveries.append(
                    MessageDelivery(
                        instance_id=instance_id,
                        delivery_id=row.delivery_id,
                        message=self._message(row),
                        source_cursor=row.source_cursor,
                        source_sequence=row.source_sequence,
                        delivery_attempt=row.delivery_attempts,
                        retry_marker=marker,
                    )
                )
        return tuple(deliveries)

    def mark_retry(
        self,
        instance_id: str,
        delivery_id: str,
        *,
        reason_code: str,
        retry_after: timedelta = timedelta(seconds=1),
    ) -> RetryMarker:
        if retry_after <= timedelta(0):
            raise ValueError("retry_after must be positive")
        if not reason_code or len(reason_code) > 128 or not reason_code.isupper():
            raise ValueError("reason_code must be a non-empty uppercase code")
        now = self._clock()
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.scalar(
                select(ChannelMessageInboxRow).where(
                    ChannelMessageInboxRow.instance_id == instance_id,
                    ChannelMessageInboxRow.delivery_id == delivery_id,
                )
            )
            if row is None:
                raise SessionRecordNotFound(delivery_id)
            if row.state != InboxMessageState.PERSISTED.value:
                raise MessageDeliveryConflict("only persisted messages can be retried")
            row.retry_reason = reason_code
            row.retry_after = now + retry_after
            return RetryMarker(
                delivery_id=delivery_id,
                attempt=max(1, row.delivery_attempts + 1),
                reason_code=reason_code,
                retry_after=row.retry_after,
            )

    def ack(self, instance_id: str, delivery_id: str) -> MessageAck:
        now = self._clock()
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.scalar(
                select(ChannelMessageInboxRow).where(
                    ChannelMessageInboxRow.instance_id == instance_id,
                    ChannelMessageInboxRow.delivery_id == delivery_id,
                )
            )
            if row is None:
                raise SessionRecordNotFound(delivery_id)
            duplicate = row.state == InboxMessageState.ACKED.value
            if row.state == InboxMessageState.MANUAL_INTERVENTION.value:
                raise MessageDeliveryConflict(
                    "manual-intervention message requires reconciliation before ACK"
                )
            if not duplicate:
                row.state = InboxMessageState.ACKED.value
                row.acknowledged_at = now
                row.retry_reason = None
                row.retry_after = None
            acknowledged_at = row.acknowledged_at or now
            self._advance_ack_cursor(uow.session, instance_id, now)
            return MessageAck(
                ack_id=self._ack_id(delivery_id),
                instance_id=instance_id,
                delivery_id=delivery_id,
                message_id=row.message_id,
                source_sequence=row.source_sequence,
                acknowledged_at=acknowledged_at,
                duplicate=duplicate,
            )

    def get_cursor(self, instance_id: str) -> MessageCursor:
        return self._store.get_cursor(instance_id)

    @staticmethod
    def _advance_ack_cursor(session, instance_id: str, now: datetime) -> None:
        cursor = session.get(ChannelMessageCursorRow, instance_id)
        if cursor is None:
            raise SessionRecordNotFound(instance_id)
        while cursor.last_acked_sequence < cursor.last_sequence:
            next_sequence = cursor.last_acked_sequence + 1
            state = session.scalar(
                select(ChannelMessageInboxRow.state).where(
                    ChannelMessageInboxRow.instance_id == instance_id,
                    ChannelMessageInboxRow.source_sequence == next_sequence,
                )
            )
            if state != InboxMessageState.ACKED.value:
                break
            cursor.last_acked_sequence = next_sequence
            cursor.revision += 1
            cursor.updated_at = now

    @staticmethod
    def _message(row: ChannelMessageInboxRow) -> ChannelMessageV1:
        timestamp = row.message_timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return ChannelMessageV1(
            message_id=row.message_id,
            channel=row.channel,
            store_id=row.store_id,
            conversation_id=row.conversation_id,
            sender=row.sender,
            content=row.content,
            timestamp=timestamp,
        )

    @classmethod
    def _persisted(
        cls, row: ChannelMessageInboxRow, *, duplicate: bool
    ) -> PersistedMessage:
        return PersistedMessage(
            instance_id=row.instance_id,
            delivery_id=row.delivery_id,
            message=cls._message(row),
            source_cursor=row.source_cursor,
            source_sequence=row.source_sequence,
            state=InboxMessageState(row.state),
            persisted_at=row.persisted_at,
            duplicate=duplicate,
        )

    @staticmethod
    def _delivery_id(instance_id: str, message_id: str) -> str:
        digest = hashlib.sha256(f"{instance_id}:{message_id}".encode()).hexdigest()
        return f"delivery-{digest}"

    @staticmethod
    def _ack_id(delivery_id: str) -> str:
        digest = hashlib.sha256(delivery_id.encode()).hexdigest()
        return f"ack-{digest}"


__all__ = [
    "CursorConflict",
    "CursorGapDetected",
    "MessageDeliveryConflict",
    "MessageReliabilityService",
]
