from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from channel_engine.storage.orm import (
    PDDWebSocketCheckpointRow,
    PDDWebSocketInboxRow,
)

from .pdd_websocket import (
    PDD_WEBSOCKET_CONTRACT_VERSION,
    PDDWebSocketCheckpoint,
    PDDWebSocketConflict,
    PDDWebSocketInboxRecord,
    PDDWebSocketInboxState,
    PDDWebSocketSyncState,
)
from .protocol import NormalizedMessage


class SqlAlchemyPDDWebSocketStore:
    """Transactional WebSocket inbox, cursor, dedup and ACK checkpoint store."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _initial(stream_id: str) -> PDDWebSocketCheckpoint:
        return PDDWebSocketCheckpoint(stream_id=stream_id, revision=0)

    def load_checkpoint(self, stream_id: str) -> PDDWebSocketCheckpoint:
        with self._session_factory() as session:
            row = session.get(PDDWebSocketCheckpointRow, stream_id)
            if row is None:
                return self._initial(stream_id)
            self._assert_version(row.websocket_contract_version)
            return self._checkpoint_from_row(row)

    def lookup_identity(
        self,
        stream_id: str,
        identity_digest: str,
    ) -> PDDWebSocketInboxRecord | None:
        with self._session_factory() as session:
            row = session.get(PDDWebSocketInboxRow, (stream_id, identity_digest))
            if row is None:
                return None
            self._assert_version(row.websocket_contract_version)
            return self._record_from_row(row)

    def persist_event(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        record: PDDWebSocketInboxRecord,
    ) -> tuple[PDDWebSocketInboxRecord, PDDWebSocketCheckpoint, bool]:
        if record.stream_id != checkpoint.stream_id:
            raise PDDWebSocketConflict(
                "WebSocket inbox record belongs to another stream",
                error_code="PDD_WEBSOCKET_STREAM_MISMATCH",
            )
        duplicate = False
        persisted = record
        try:
            with self._session_factory.begin() as session:
                existing = session.get(
                    PDDWebSocketInboxRow,
                    (record.stream_id, record.identity_digest),
                )
                if existing is not None:
                    self._assert_version(existing.websocket_contract_version)
                    if (
                        existing.payload_fingerprint != record.payload_fingerprint
                        or existing.sequence != record.sequence
                    ):
                        raise PDDWebSocketConflict(
                            "WebSocket identity is bound to different evidence",
                            error_code="PDD_WEBSOCKET_IDENTITY_REUSED",
                        )
                    duplicate = True
                    persisted = record.model_copy(
                        update={
                            "state": PDDWebSocketInboxState(existing.state),
                            "persisted_at": self._aware(existing.persisted_at),
                            "acknowledged_at": (
                                self._aware(existing.acknowledged_at)
                                if existing.acknowledged_at is not None
                                else None
                            ),
                        }
                    )
                    if existing.state == PDDWebSocketInboxState.PERSISTED.value:
                        existing.ack_token = record.ack_token
                updated = self._next_persisted_checkpoint(
                    checkpoint,
                    record,
                    duplicate=duplicate,
                )
                self._cas_checkpoint(session, checkpoint, updated)
                if not duplicate:
                    session.add(self._row_from_record(record))
        except IntegrityError as exc:
            raise PDDWebSocketConflict(
                "WebSocket inbox commit conflicted with another writer",
                error_code="PDD_WEBSOCKET_STORE_CONFLICT",
            ) from exc
        return persisted, updated, duplicate

    def next_pending_ack(
        self,
        stream_id: str,
    ) -> PDDWebSocketInboxRecord | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(PDDWebSocketInboxRow)
                .where(
                    PDDWebSocketInboxRow.stream_id == stream_id,
                    PDDWebSocketInboxRow.state
                    == PDDWebSocketInboxState.PERSISTED.value,
                )
                .order_by(PDDWebSocketInboxRow.sequence)
                .limit(1)
            )
            if row is None:
                return None
            self._assert_version(row.websocket_contract_version)
            return self._record_from_row(row)

    def mark_acknowledged(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        record: PDDWebSocketInboxRecord,
        acknowledged_at: datetime,
    ) -> tuple[PDDWebSocketInboxRecord, PDDWebSocketCheckpoint]:
        if record.stream_id != checkpoint.stream_id:
            raise PDDWebSocketConflict(
                "WebSocket ACK belongs to another stream",
                error_code="PDD_WEBSOCKET_STREAM_MISMATCH",
            )
        acknowledged = record.model_copy(
            update={
                "state": PDDWebSocketInboxState.ACKED,
                "acknowledged_at": acknowledged_at,
            }
        )
        updated = checkpoint.model_copy(
            update={
                "revision": checkpoint.revision + 1,
                "acknowledged_cursor": record.cursor,
                "last_acknowledged_sequence": record.sequence,
                "acknowledged_count": checkpoint.acknowledged_count + 1,
                "sync_state": PDDWebSocketSyncState.IN_SYNC,
                "last_error_code": None,
            }
        )
        try:
            with self._session_factory.begin() as session:
                pending = session.scalar(
                    select(PDDWebSocketInboxRow)
                    .where(
                        PDDWebSocketInboxRow.stream_id == record.stream_id,
                        PDDWebSocketInboxRow.state
                        == PDDWebSocketInboxState.PERSISTED.value,
                    )
                    .order_by(PDDWebSocketInboxRow.sequence)
                    .limit(1)
                )
                if pending is None or pending.identity_digest != record.identity_digest:
                    raise PDDWebSocketConflict(
                        "WebSocket ACK order changed concurrently",
                        error_code="PDD_WEBSOCKET_ACK_ORDER_INVALID",
                    )
                if (
                    checkpoint.last_acknowledged_sequence >= 0
                    and record.sequence != checkpoint.last_acknowledged_sequence + 1
                ):
                    raise PDDWebSocketConflict(
                        "WebSocket ACK sequence contains a gap",
                        error_code="PDD_WEBSOCKET_ACK_ORDER_INVALID",
                    )
                self._cas_checkpoint(session, checkpoint, updated)
                result = session.execute(
                    update(PDDWebSocketInboxRow)
                    .where(
                        PDDWebSocketInboxRow.stream_id == record.stream_id,
                        PDDWebSocketInboxRow.identity_digest
                        == record.identity_digest,
                        PDDWebSocketInboxRow.state
                        == PDDWebSocketInboxState.PERSISTED.value,
                    )
                    .values(
                        state=PDDWebSocketInboxState.ACKED.value,
                        acknowledged_at=acknowledged_at,
                    )
                )
                if result.rowcount != 1:
                    raise PDDWebSocketConflict(
                        "WebSocket inbox ACK state changed concurrently",
                        error_code="PDD_WEBSOCKET_STORE_CONFLICT",
                    )
        except IntegrityError as exc:
            raise PDDWebSocketConflict(
                "WebSocket ACK commit conflicted with another writer",
                error_code="PDD_WEBSOCKET_STORE_CONFLICT",
            ) from exc
        return acknowledged, updated

    def record_failure(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        *,
        error_code: str,
        failed_at: datetime,
        terminal: bool,
    ) -> PDDWebSocketCheckpoint:
        updated = checkpoint.model_copy(
            update={
                "revision": checkpoint.revision + 1,
                "last_received_at": failed_at,
                "sync_state": (
                    PDDWebSocketSyncState.FAILED
                    if terminal
                    else PDDWebSocketSyncState.DEGRADED
                ),
                "last_error_code": error_code,
            }
        )
        try:
            with self._session_factory.begin() as session:
                self._cas_checkpoint(session, checkpoint, updated)
        except IntegrityError as exc:
            raise PDDWebSocketConflict(
                "WebSocket failure checkpoint conflicted",
                error_code="PDD_WEBSOCKET_STORE_CONFLICT",
            ) from exc
        return updated

    @staticmethod
    def _next_persisted_checkpoint(
        checkpoint: PDDWebSocketCheckpoint,
        record: PDDWebSocketInboxRecord,
        *,
        duplicate: bool,
    ) -> PDDWebSocketCheckpoint:
        update_values: dict[str, object] = {
            "revision": checkpoint.revision + 1,
            "duplicate_count": checkpoint.duplicate_count + int(duplicate),
            "received_count": checkpoint.received_count + int(not duplicate),
            "last_received_at": record.persisted_at,
            "sync_state": PDDWebSocketSyncState.IN_SYNC,
            "last_error_code": None,
        }
        if not duplicate:
            update_values.update(
                {
                    "cursor": record.cursor,
                    "last_sequence": record.sequence,
                }
            )
        return checkpoint.model_copy(update=update_values)

    def _cas_checkpoint(
        self,
        session: Session,
        current: PDDWebSocketCheckpoint,
        updated: PDDWebSocketCheckpoint,
    ) -> None:
        existing = session.get(PDDWebSocketCheckpointRow, current.stream_id)
        if existing is None:
            if current.revision != 0:
                raise PDDWebSocketConflict(
                    "WebSocket checkpoint disappeared",
                    error_code="PDD_WEBSOCKET_STORE_CONFLICT",
                )
            session.add(self._row_from_checkpoint(updated))
            session.flush()
            return
        self._assert_version(existing.websocket_contract_version)
        result = session.execute(
            update(PDDWebSocketCheckpointRow)
            .where(
                PDDWebSocketCheckpointRow.stream_id == current.stream_id,
                PDDWebSocketCheckpointRow.revision == current.revision,
            )
            .values(**self._checkpoint_values(updated))
        )
        if result.rowcount != 1:
            raise PDDWebSocketConflict(
                "WebSocket checkpoint revision changed concurrently",
                error_code="PDD_WEBSOCKET_STORE_CONFLICT",
            )

    @staticmethod
    def _checkpoint_values(checkpoint: PDDWebSocketCheckpoint) -> dict[str, object]:
        return {
            "websocket_contract_version": PDD_WEBSOCKET_CONTRACT_VERSION,
            "revision": checkpoint.revision,
            "cursor": checkpoint.cursor,
            "last_sequence": checkpoint.last_sequence,
            "acknowledged_cursor": checkpoint.acknowledged_cursor,
            "last_acknowledged_sequence": checkpoint.last_acknowledged_sequence,
            "received_count": checkpoint.received_count,
            "duplicate_count": checkpoint.duplicate_count,
            "acknowledged_count": checkpoint.acknowledged_count,
            "last_received_at": checkpoint.last_received_at,
            "sync_state": checkpoint.sync_state.value,
            "last_error_code": checkpoint.last_error_code,
        }

    @classmethod
    def _row_from_checkpoint(
        cls,
        checkpoint: PDDWebSocketCheckpoint,
    ) -> PDDWebSocketCheckpointRow:
        return PDDWebSocketCheckpointRow(
            stream_id=checkpoint.stream_id,
            **cls._checkpoint_values(checkpoint),
        )

    @staticmethod
    def _row_from_record(record: PDDWebSocketInboxRecord) -> PDDWebSocketInboxRow:
        return PDDWebSocketInboxRow(
            stream_id=record.stream_id,
            identity_digest=record.identity_digest,
            websocket_contract_version=PDD_WEBSOCKET_CONTRACT_VERSION,
            payload_fingerprint=record.payload_fingerprint,
            sequence=record.sequence,
            cursor=record.cursor,
            ack_token=record.ack_token,
            conversation_id=record.message.conversation_id,
            external_message_id=record.message.external_message_id,
            sender=record.message.sender,
            content=record.message.content,
            message_timestamp=record.message.timestamp,
            state=record.state.value,
            persisted_at=record.persisted_at,
            acknowledged_at=record.acknowledged_at,
        )

    @classmethod
    def _checkpoint_from_row(
        cls,
        row: PDDWebSocketCheckpointRow,
    ) -> PDDWebSocketCheckpoint:
        return PDDWebSocketCheckpoint(
            stream_id=row.stream_id,
            revision=row.revision,
            cursor=row.cursor,
            last_sequence=row.last_sequence,
            acknowledged_cursor=row.acknowledged_cursor,
            last_acknowledged_sequence=row.last_acknowledged_sequence,
            received_count=row.received_count,
            duplicate_count=row.duplicate_count,
            acknowledged_count=row.acknowledged_count,
            last_received_at=(
                cls._aware(row.last_received_at)
                if row.last_received_at is not None
                else None
            ),
            sync_state=PDDWebSocketSyncState(row.sync_state),
            last_error_code=row.last_error_code,
        )

    @classmethod
    def _record_from_row(cls, row: PDDWebSocketInboxRow) -> PDDWebSocketInboxRecord:
        acknowledged_at = (
            cls._aware(row.acknowledged_at)
            if row.acknowledged_at is not None
            else None
        )
        return PDDWebSocketInboxRecord(
            stream_id=row.stream_id,
            identity_digest=row.identity_digest,
            payload_fingerprint=row.payload_fingerprint,
            sequence=row.sequence,
            cursor=row.cursor,
            ack_token=row.ack_token,
            message=NormalizedMessage(
                channel="pdd",
                conversation_id=row.conversation_id,
                external_message_id=row.external_message_id,
                sender=row.sender,
                content=row.content,
                timestamp=cls._aware(row.message_timestamp),
            ),
            state=PDDWebSocketInboxState(row.state),
            persisted_at=cls._aware(row.persisted_at),
            acknowledged_at=acknowledged_at,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _assert_version(version: str) -> None:
        if version != PDD_WEBSOCKET_CONTRACT_VERSION:
            raise PDDWebSocketConflict(
                f"unsupported PDD WebSocket contract version: {version}",
                error_code="PDD_WEBSOCKET_VERSION_UNSUPPORTED",
            )


__all__ = ["SqlAlchemyPDDWebSocketStore"]
