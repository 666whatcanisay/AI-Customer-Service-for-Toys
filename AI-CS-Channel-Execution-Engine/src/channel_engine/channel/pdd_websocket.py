from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.models.entities import new_id, utc_now

from .protocol import NormalizedMessage


PDD_WEBSOCKET_CONTRACT_VERSION = "1.0"


class PDDWebSocketModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    websocket_contract_version: Literal["1.0"] = PDD_WEBSOCKET_CONTRACT_VERSION


class PDDWebSocketConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class PDDWebSocketInboxState(StrEnum):
    PERSISTED = "PERSISTED"
    ACKED = "ACKED"


class PDDWebSocketSyncState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_SYNC = "IN_SYNC"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class PDDWebSocketSession(PDDWebSocketModel):
    session_id: str = Field(min_length=1, max_length=128)
    connection_ref: str | None = Field(default=None, max_length=128)
    state: PDDWebSocketConnectionState
    generation: int = Field(ge=0)
    connected_at: AwareDatetime | None = None
    last_heartbeat_at: AwareDatetime | None = None
    failure_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_connection(self) -> PDDWebSocketSession:
        connected = self.state in {
            PDDWebSocketConnectionState.CONNECTED,
            PDDWebSocketConnectionState.HEALTHY,
            PDDWebSocketConnectionState.DEGRADED,
        }
        if connected and (self.connection_ref is None or self.connected_at is None):
            raise ValueError("connected WebSocket state requires connection metadata")
        if self.state is PDDWebSocketConnectionState.DISCONNECTED:
            if self.connection_ref is not None:
                raise ValueError("disconnected WebSocket state cannot retain connection")
        return self


class PDDWebSocketHeartbeat(PDDWebSocketModel):
    state: PDDWebSocketConnectionState
    healthy: bool
    checked_at: AwareDatetime
    attempted: bool
    reconnected: bool = False
    failure_code: str | None = Field(default=None, max_length=128)


class PDDWebSocketFrame(PDDWebSocketModel):
    frame_id: str = Field(min_length=1, max_length=128)
    ack_token: str = Field(
        min_length=1,
        max_length=256,
        exclude=True,
        repr=False,
    )
    payload_text: str = Field(
        min_length=1,
        max_length=65_536,
        exclude=True,
        repr=False,
    )
    received_at: AwareDatetime


class PDDWebSocketMessagePayload(PDDWebSocketModel):
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    attributes: dict[str, str] = Field(default_factory=dict)


class PDDWebSocketEvent(PDDWebSocketModel):
    event_type: Literal["message"] = "message"
    sequence: int = Field(ge=0)
    cursor: str = Field(min_length=1, max_length=512)
    message_id: str = Field(min_length=1, max_length=255)
    conversation_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    timestamp: AwareDatetime
    payload: PDDWebSocketMessagePayload


class PDDWebSocketCheckpoint(PDDWebSocketModel):
    stream_id: str = Field(min_length=1, max_length=255)
    revision: int = Field(ge=0)
    cursor: str | None = Field(default=None, max_length=512)
    last_sequence: int = Field(default=-1, ge=-1)
    acknowledged_cursor: str | None = Field(default=None, max_length=512)
    last_acknowledged_sequence: int = Field(default=-1, ge=-1)
    received_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    acknowledged_count: int = Field(default=0, ge=0)
    last_received_at: AwareDatetime | None = None
    sync_state: PDDWebSocketSyncState = PDDWebSocketSyncState.NOT_STARTED
    last_error_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_ack_position(self) -> PDDWebSocketCheckpoint:
        if self.last_acknowledged_sequence > self.last_sequence:
            raise ValueError("acknowledged sequence cannot exceed persisted sequence")
        if (self.acknowledged_cursor is None) != (
            self.last_acknowledged_sequence == -1
        ):
            raise ValueError("acknowledged cursor and sequence must advance together")
        return self


class PDDWebSocketInboxRecord(PDDWebSocketModel):
    stream_id: str = Field(min_length=1, max_length=255)
    identity_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    payload_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    sequence: int = Field(ge=0)
    cursor: str = Field(min_length=1, max_length=512)
    ack_token: str = Field(
        min_length=1,
        max_length=256,
        exclude=True,
        repr=False,
    )
    message: NormalizedMessage
    state: PDDWebSocketInboxState
    persisted_at: AwareDatetime
    acknowledged_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_ack_state(self) -> PDDWebSocketInboxRecord:
        if (self.state is PDDWebSocketInboxState.ACKED) != (
            self.acknowledged_at is not None
        ):
            raise ValueError("ACKED inbox state requires acknowledged_at")
        return self


class PDDWebSocketAckReceipt(PDDWebSocketModel):
    stream_id: str
    conversation_id: str
    external_message_id: str
    sequence: int = Field(ge=0)
    acknowledged_at: AwareDatetime
    duplicate_ack: bool = False


class PDDWebSocketError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDWebSocketSafetyError(PDDWebSocketError):
    pass


class PDDWebSocketConnectionError(PDDWebSocketError):
    pass


class PDDWebSocketProtocolError(PDDWebSocketError):
    pass


class PDDWebSocketConflict(PDDWebSocketError):
    pass


class PDDWebSocketMissedSequence(PDDWebSocketConflict):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="PDD_WEBSOCKET_SEQUENCE_GAP")


class PDDWebSocketEventParser:
    """Parse the adapter-side canonical V1 envelope, not an assumed PDD wire schema."""

    def parse(self, frame: PDDWebSocketFrame) -> PDDWebSocketEvent:
        try:
            untrusted = json.loads(frame.payload_text)
            if (
                not isinstance(untrusted, dict)
                or untrusted.get("websocket_contract_version")
                != PDD_WEBSOCKET_CONTRACT_VERSION
            ):
                raise ValueError("WebSocket contract version is missing or unsupported")
            return PDDWebSocketEvent.model_validate_json(frame.payload_text)
        except Exception as exc:
            raise PDDWebSocketProtocolError(
                "WebSocket frame does not match the canonical message envelope",
                error_code="PDD_WEBSOCKET_MALFORMED_PAYLOAD",
            ) from exc

    @staticmethod
    def normalize(event: PDDWebSocketEvent) -> NormalizedMessage:
        return NormalizedMessage(
            channel="pdd",
            conversation_id=event.conversation_id,
            external_message_id=event.message_id,
            sender=event.sender,
            content=event.payload.content,
            timestamp=event.timestamp,
        )


@runtime_checkable
class PDDWebSocketClientPort(Protocol):
    @property
    def real_network(self) -> bool:
        """Foundation V1 accepts only false."""

    def connect(
        self,
        *,
        resume_cursor: str | None,
        after_sequence: int,
    ) -> str:
        """Open a connection from the last acknowledged position."""

    def disconnect(self, connection_ref: str) -> None:
        """Close one exact connection."""

    def ping(self, connection_ref: str, timeout_seconds: float) -> bool:
        """Perform one transport heartbeat within the timeout."""

    def receive(
        self,
        connection_ref: str,
        timeout_seconds: float,
    ) -> PDDWebSocketFrame | None:
        """Receive one frame without acknowledging it."""

    def ack(self, connection_ref: str, ack_token: str) -> None:
        """Acknowledge one token previously persisted by the transport."""


@runtime_checkable
class PDDWebSocketStore(Protocol):
    def load_checkpoint(self, stream_id: str) -> PDDWebSocketCheckpoint: ...

    def lookup_identity(
        self,
        stream_id: str,
        identity_digest: str,
    ) -> PDDWebSocketInboxRecord | None: ...

    def persist_event(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        record: PDDWebSocketInboxRecord,
    ) -> tuple[PDDWebSocketInboxRecord, PDDWebSocketCheckpoint, bool]: ...

    def next_pending_ack(
        self,
        stream_id: str,
    ) -> PDDWebSocketInboxRecord | None: ...

    def mark_acknowledged(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        record: PDDWebSocketInboxRecord,
        acknowledged_at: AwareDatetime,
    ) -> tuple[PDDWebSocketInboxRecord, PDDWebSocketCheckpoint]: ...

    def record_failure(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        *,
        error_code: str,
        failed_at: AwareDatetime,
        terminal: bool,
    ) -> PDDWebSocketCheckpoint: ...


@runtime_checkable
class PDDWebSocketTransportPort(Protocol):
    def connect(self) -> PDDWebSocketSession: ...

    def disconnect(self) -> PDDWebSocketSession: ...

    def heartbeat(self) -> PDDWebSocketHeartbeat: ...

    def receive(self) -> NormalizedMessage | None: ...

    def ack(self, message: NormalizedMessage) -> PDDWebSocketAckReceipt: ...

    def reconnect(self) -> PDDWebSocketSession: ...


class PDDWebSocketTransport:
    """Independent, durable, receive-only PDD WebSocket transport foundation."""

    def __init__(
        self,
        client: PDDWebSocketClientPort,
        store: PDDWebSocketStore,
        parser: PDDWebSocketEventParser,
        *,
        stream_id: str,
        heartbeat_interval: timedelta = timedelta(seconds=15),
        heartbeat_timeout_seconds: float = 5.0,
        receive_timeout_seconds: float = 1.0,
        auto_reconnect: bool = True,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(client, PDDWebSocketClientPort):
            raise TypeError("WebSocket client does not implement the client port")
        if not isinstance(store, PDDWebSocketStore):
            raise TypeError("WebSocket store does not implement the store port")
        if client.real_network:
            raise PDDWebSocketSafetyError(
                "real PDD WebSocket network access is disabled in Foundation V1",
                error_code="PDD_WEBSOCKET_REAL_NETWORK_FORBIDDEN",
            )
        if not stream_id.strip() or len(stream_id) > 255:
            raise ValueError("WebSocket stream id is invalid")
        if heartbeat_interval <= timedelta(0):
            raise ValueError("heartbeat interval must be positive")
        if heartbeat_timeout_seconds <= 0 or receive_timeout_seconds <= 0:
            raise ValueError("WebSocket timeouts must be positive")
        self._client = client
        self._store = store
        self._parser = parser
        self._stream_id = stream_id
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._receive_timeout_seconds = receive_timeout_seconds
        self._auto_reconnect = auto_reconnect
        self._clock = clock
        self._lock = RLock()
        self._terminal_failure = False
        self.operation_log: list[str] = []
        self._session = PDDWebSocketSession(
            session_id=new_id("pdd-websocket-session"),
            state=PDDWebSocketConnectionState.DISCONNECTED,
            generation=0,
        )

    def snapshot(self) -> PDDWebSocketSession:
        with self._lock:
            return PDDWebSocketSession.model_validate(self._session.model_dump())

    def connect(self) -> PDDWebSocketSession:
        with self._lock:
            if self._terminal_failure:
                raise PDDWebSocketConnectionError(
                    "terminal WebSocket failure requires a new controlled session",
                    error_code="PDD_WEBSOCKET_TERMINAL_FAILURE",
                )
            if self._session.state in {
                PDDWebSocketConnectionState.CONNECTED,
                PDDWebSocketConnectionState.HEALTHY,
            }:
                return self.snapshot()
            if self._session.state is PDDWebSocketConnectionState.DEGRADED:
                return self.reconnect()
            self._session = self._session.model_copy(
                update={
                    "state": PDDWebSocketConnectionState.CONNECTING,
                    "failure_code": None,
                }
            )
            try:
                self._open_connection()
            except Exception as exc:
                self._session = self._session.model_copy(
                    update={
                        "state": PDDWebSocketConnectionState.FAILED,
                        "connection_ref": None,
                        "failure_code": "PDD_WEBSOCKET_CONNECT_FAILED",
                    }
                )
                raise PDDWebSocketConnectionError(
                    "PDD WebSocket connection failed",
                    error_code="PDD_WEBSOCKET_CONNECT_FAILED",
                ) from exc
            return self.snapshot()

    def disconnect(self) -> PDDWebSocketSession:
        with self._lock:
            connection_ref = self._session.connection_ref
            if connection_ref is not None:
                try:
                    self._client.disconnect(connection_ref)
                except Exception:
                    pass
                finally:
                    self.operation_log.append("disconnect")
            self._session = self._session.model_copy(
                update={
                    "state": PDDWebSocketConnectionState.DISCONNECTED,
                    "connection_ref": None,
                    "failure_code": None,
                }
            )
            return self.snapshot()

    def reconnect(self) -> PDDWebSocketSession:
        with self._lock:
            if self._terminal_failure:
                raise PDDWebSocketConnectionError(
                    "terminal WebSocket failure requires operator intervention",
                    error_code="PDD_WEBSOCKET_TERMINAL_FAILURE",
                )
            old_ref = self._session.connection_ref
            if old_ref is not None:
                try:
                    self._client.disconnect(old_ref)
                except Exception:
                    pass
            try:
                self._open_connection()
                if not self._client.ping(
                    self._require_connection(),
                    self._heartbeat_timeout_seconds,
                ):
                    raise PDDWebSocketConnectionError(
                        "WebSocket heartbeat failed after reconnect",
                        error_code="PDD_WEBSOCKET_HEARTBEAT_TIMEOUT",
                    )
                now = self._clock()
                self._session = self._session.model_copy(
                    update={
                        "state": PDDWebSocketConnectionState.HEALTHY,
                        "last_heartbeat_at": now,
                        "failure_code": None,
                    }
                )
                self.operation_log.append("reconnect")
                return self.snapshot()
            except Exception as exc:
                self._session = self._session.model_copy(
                    update={
                        "state": PDDWebSocketConnectionState.DEGRADED,
                        "failure_code": "PDD_WEBSOCKET_RECONNECT_FAILED",
                    }
                )
                raise PDDWebSocketConnectionError(
                    "PDD WebSocket reconnect failed",
                    error_code="PDD_WEBSOCKET_RECONNECT_FAILED",
                ) from exc

    def heartbeat(self) -> PDDWebSocketHeartbeat:
        with self._lock:
            now = self._clock()
            if self._session.state not in {
                PDDWebSocketConnectionState.CONNECTED,
                PDDWebSocketConnectionState.HEALTHY,
                PDDWebSocketConnectionState.DEGRADED,
            }:
                return PDDWebSocketHeartbeat(
                    state=self._session.state,
                    healthy=False,
                    checked_at=now,
                    attempted=False,
                    failure_code="PDD_WEBSOCKET_NOT_CONNECTED",
                )
            last = self._session.last_heartbeat_at
            due = last is None or now - last >= self._heartbeat_interval
            if not due and self._session.state is PDDWebSocketConnectionState.HEALTHY:
                return PDDWebSocketHeartbeat(
                    state=self._session.state,
                    healthy=True,
                    checked_at=now,
                    attempted=False,
                )
            try:
                healthy = self._client.ping(
                    self._require_connection(),
                    self._heartbeat_timeout_seconds,
                )
            except Exception:
                healthy = False
            if healthy:
                self._session = self._session.model_copy(
                    update={
                        "state": PDDWebSocketConnectionState.HEALTHY,
                        "last_heartbeat_at": now,
                        "failure_code": None,
                    }
                )
                self.operation_log.append("heartbeat")
                return PDDWebSocketHeartbeat(
                    state=PDDWebSocketConnectionState.HEALTHY,
                    healthy=True,
                    checked_at=now,
                    attempted=True,
                )
            self._session = self._session.model_copy(
                update={
                    "state": PDDWebSocketConnectionState.DEGRADED,
                    "last_heartbeat_at": now,
                    "failure_code": "PDD_WEBSOCKET_HEARTBEAT_TIMEOUT",
                }
            )
            if self._auto_reconnect and not self._terminal_failure:
                try:
                    self.reconnect()
                    return PDDWebSocketHeartbeat(
                        state=PDDWebSocketConnectionState.HEALTHY,
                        healthy=True,
                        checked_at=self._clock(),
                        attempted=True,
                        reconnected=True,
                    )
                except PDDWebSocketConnectionError:
                    pass
            return PDDWebSocketHeartbeat(
                state=PDDWebSocketConnectionState.DEGRADED,
                healthy=False,
                checked_at=now,
                attempted=True,
                failure_code="PDD_WEBSOCKET_HEARTBEAT_TIMEOUT",
            )

    def receive(self) -> NormalizedMessage | None:
        with self._lock:
            checkpoint = self._store.load_checkpoint(self._stream_id)
            try:
                connection_ref = self._require_usable_connection()
                frame = self._client.receive(
                    connection_ref,
                    self._receive_timeout_seconds,
                )
            except PDDWebSocketError:
                raise
            except Exception as exc:
                self._degrade("PDD_WEBSOCKET_DISCONNECTED")
                raise PDDWebSocketConnectionError(
                    "PDD WebSocket disconnected during receive",
                    error_code="PDD_WEBSOCKET_DISCONNECTED",
                ) from exc
            if frame is None:
                return None
            self.operation_log.append(f"receive:{frame.frame_id}")
            try:
                event = self._parser.parse(frame)
                message = self._parser.normalize(event)
                record = self._record(frame, event, message)
                existing = self._store.lookup_identity(
                    self._stream_id,
                    record.identity_digest,
                )
                if existing is None:
                    if (
                        checkpoint.last_sequence >= 0
                        and event.sequence != checkpoint.last_sequence + 1
                    ):
                        raise PDDWebSocketMissedSequence(
                            "WebSocket event sequence contains a gap"
                        )
                elif (
                    existing.payload_fingerprint != record.payload_fingerprint
                    or existing.sequence != record.sequence
                ):
                    raise PDDWebSocketConflict(
                        "WebSocket message identity changed payload or sequence",
                        error_code="PDD_WEBSOCKET_IDENTITY_REUSED",
                    )
                persisted, _updated, duplicate = self._store.persist_event(
                    checkpoint,
                    record,
                )
                self.operation_log.append(f"persist:{frame.frame_id}")
                if duplicate and persisted.state is PDDWebSocketInboxState.ACKED:
                    self._client.ack(connection_ref, record.ack_token)
                    self.operation_log.append(f"ack:{frame.frame_id}")
                    return None
                return persisted.message
            except (PDDWebSocketProtocolError, PDDWebSocketConflict) as exc:
                self._terminal_failure = True
                self._record_failure(checkpoint, exc.error_code, terminal=True)
                self._session = self._session.model_copy(
                    update={
                        "state": PDDWebSocketConnectionState.FAILED,
                        "failure_code": exc.error_code,
                    }
                )
                raise
            except Exception as exc:
                self._record_failure(
                    checkpoint,
                    "PDD_WEBSOCKET_RECEIVE_FAILED",
                    terminal=False,
                )
                self._degrade("PDD_WEBSOCKET_RECEIVE_FAILED")
                raise PDDWebSocketError(
                    "PDD WebSocket receive pipeline failed",
                    error_code="PDD_WEBSOCKET_RECEIVE_FAILED",
                ) from exc

    def ack(self, message: NormalizedMessage) -> PDDWebSocketAckReceipt:
        with self._lock:
            if message.channel != "pdd":
                raise PDDWebSocketConflict(
                    "WebSocket ACK requires a PDD message",
                    error_code="PDD_WEBSOCKET_ACK_CHANNEL_MISMATCH",
                )
            digest = self._identity_digest(
                message.conversation_id,
                message.external_message_id,
            )
            record = self._store.lookup_identity(self._stream_id, digest)
            if record is None:
                raise PDDWebSocketConflict(
                    "WebSocket ACK requires a persisted inbox record",
                    error_code="PDD_WEBSOCKET_ACK_BEFORE_PERSIST",
                )
            if record.state is PDDWebSocketInboxState.ACKED:
                assert record.acknowledged_at is not None
                return PDDWebSocketAckReceipt(
                    stream_id=self._stream_id,
                    conversation_id=message.conversation_id,
                    external_message_id=message.external_message_id,
                    sequence=record.sequence,
                    acknowledged_at=record.acknowledged_at,
                    duplicate_ack=True,
                )
            next_pending = self._store.next_pending_ack(self._stream_id)
            if next_pending is None or next_pending.identity_digest != digest:
                raise PDDWebSocketConflict(
                    "WebSocket ACK must follow persisted sequence order",
                    error_code="PDD_WEBSOCKET_ACK_ORDER_INVALID",
                )
            connection_ref = self._require_usable_connection()
            try:
                self._client.ack(connection_ref, record.ack_token)
                self.operation_log.append(f"ack:{record.sequence}")
            except Exception as exc:
                self._degrade("PDD_WEBSOCKET_ACK_FAILED")
                raise PDDWebSocketConnectionError(
                    "PDD WebSocket ACK failed",
                    error_code="PDD_WEBSOCKET_ACK_FAILED",
                ) from exc
            acknowledged_at = self._clock()
            checkpoint = self._store.load_checkpoint(self._stream_id)
            try:
                acknowledged, _updated = self._store.mark_acknowledged(
                    checkpoint,
                    record,
                    acknowledged_at,
                )
            except Exception as exc:
                self._degrade("PDD_WEBSOCKET_ACK_PERSIST_FAILED")
                if isinstance(exc, PDDWebSocketError):
                    raise
                raise PDDWebSocketConflict(
                    "WebSocket ACK was sent but its durable state was not committed",
                    error_code="PDD_WEBSOCKET_ACK_PERSIST_FAILED",
                ) from exc
            assert acknowledged.acknowledged_at is not None
            return PDDWebSocketAckReceipt(
                stream_id=self._stream_id,
                conversation_id=message.conversation_id,
                external_message_id=message.external_message_id,
                sequence=record.sequence,
                acknowledged_at=acknowledged.acknowledged_at,
            )

    def _open_connection(self) -> None:
        checkpoint = self._store.load_checkpoint(self._stream_id)
        connection_ref = self._client.connect(
            resume_cursor=checkpoint.acknowledged_cursor,
            after_sequence=checkpoint.last_acknowledged_sequence,
        )
        now = self._clock()
        self._session = self._session.model_copy(
            update={
                "connection_ref": connection_ref,
                "state": PDDWebSocketConnectionState.CONNECTED,
                "generation": self._session.generation + 1,
                "connected_at": now,
                "failure_code": None,
            }
        )
        self.operation_log.append("connect")

    def _require_connection(self) -> str:
        if self._session.connection_ref is None:
            raise PDDWebSocketConnectionError(
                "PDD WebSocket connection is unavailable",
                error_code="PDD_WEBSOCKET_NOT_CONNECTED",
            )
        return self._session.connection_ref

    def _require_usable_connection(self) -> str:
        if self._session.state not in {
            PDDWebSocketConnectionState.CONNECTED,
            PDDWebSocketConnectionState.HEALTHY,
        }:
            raise PDDWebSocketConnectionError(
                "PDD WebSocket connection is not usable",
                error_code="PDD_WEBSOCKET_NOT_CONNECTED",
            )
        return self._require_connection()

    def _degrade(self, error_code: str) -> None:
        self._session = self._session.model_copy(
            update={
                "state": PDDWebSocketConnectionState.DEGRADED,
                "failure_code": error_code,
            }
        )

    def _record_failure(
        self,
        checkpoint: PDDWebSocketCheckpoint,
        error_code: str,
        *,
        terminal: bool,
    ) -> None:
        try:
            self._store.record_failure(
                checkpoint,
                error_code=error_code,
                failed_at=self._clock(),
                terminal=terminal,
            )
        except PDDWebSocketConflict:
            pass

    def _record(
        self,
        frame: PDDWebSocketFrame,
        event: PDDWebSocketEvent,
        message: NormalizedMessage,
    ) -> PDDWebSocketInboxRecord:
        return PDDWebSocketInboxRecord(
            stream_id=self._stream_id,
            identity_digest=self._identity_digest(
                message.conversation_id,
                message.external_message_id,
            ),
            payload_fingerprint=self._payload_fingerprint(message),
            sequence=event.sequence,
            cursor=event.cursor,
            ack_token=frame.ack_token,
            message=message,
            state=PDDWebSocketInboxState.PERSISTED,
            persisted_at=self._clock(),
        )

    @staticmethod
    def _identity_digest(conversation_id: str, message_id: str) -> str:
        return hashlib.sha256(f"{conversation_id}\0{message_id}".encode()).hexdigest()

    @staticmethod
    def _payload_fingerprint(message: NormalizedMessage) -> str:
        payload = json.dumps(
            message.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class FakePDDWebSocketServer:
    """In-process fake server; it opens no socket and never contacts PDD."""

    def __init__(self, *, clock: Callable[[], AwareDatetime] = utc_now) -> None:
        self._clock = clock
        self._frames: list[tuple[PDDWebSocketFrame, int | None]] = []
        self._connections: dict[str, int] = {}
        self._acknowledged_tokens: set[str] = set()
        self._heartbeat_results: deque[bool | Exception] = deque()
        self._lock = RLock()
        self.available = True
        self.disconnect_next_receive = False
        self.fail_ack = False
        self.connect_history: list[tuple[str | None, int]] = []
        self.ack_history: list[str] = []
        self.ping_timeouts: list[float] = []
        self.receive_timeouts: list[float] = []
        self.operation_log: list[str] = []

    def client(self) -> FakePDDWebSocketClient:
        return FakePDDWebSocketClient(self)

    def enqueue_event(
        self,
        event: PDDWebSocketEvent,
        *,
        ack_token: str | None = None,
    ) -> None:
        token = ack_token or f"ack-{event.sequence}-{event.message_id}"
        frame = PDDWebSocketFrame(
            frame_id=new_id("fake-websocket-frame"),
            ack_token=token,
            payload_text=event.model_dump_json(),
            received_at=self._clock(),
        )
        with self._lock:
            self._frames.append((frame, event.sequence))

    def enqueue_raw(self, payload_text: str, *, ack_token: str) -> None:
        frame = PDDWebSocketFrame(
            frame_id=new_id("fake-websocket-frame"),
            ack_token=ack_token,
            payload_text=payload_text,
            received_at=self._clock(),
        )
        with self._lock:
            self._frames.append((frame, None))

    def enqueue_heartbeat(self, result: bool | Exception) -> None:
        self._heartbeat_results.append(result)

    def _connect(self, resume_cursor: str | None, after_sequence: int) -> str:
        with self._lock:
            if not self.available:
                raise ConnectionError("fake WebSocket server is unavailable")
            start = len(self._frames)
            for index, (frame, sequence) in enumerate(self._frames):
                if sequence is None or sequence > after_sequence:
                    start = index
                    break
                if frame.ack_token not in self._acknowledged_tokens:
                    start = index
                    break
            connection_ref = new_id("fake-websocket-connection")
            self._connections[connection_ref] = start
            self.connect_history.append((resume_cursor, after_sequence))
            self.operation_log.append("connect")
            return connection_ref

    def _disconnect(self, connection_ref: str) -> None:
        with self._lock:
            self._connections.pop(connection_ref, None)
            self.operation_log.append("disconnect")

    def _ping(self, connection_ref: str, timeout_seconds: float) -> bool:
        with self._lock:
            self._require_connection(connection_ref)
            self.ping_timeouts.append(timeout_seconds)
            self.operation_log.append("heartbeat")
            result = self._heartbeat_results.popleft() if self._heartbeat_results else True
            if isinstance(result, Exception):
                raise result
            return result

    def _receive(
        self,
        connection_ref: str,
        timeout_seconds: float,
    ) -> PDDWebSocketFrame | None:
        with self._lock:
            self.receive_timeouts.append(timeout_seconds)
            index = self._require_connection(connection_ref)
            if self.disconnect_next_receive:
                self.disconnect_next_receive = False
                self._connections.pop(connection_ref, None)
                raise ConnectionError("fake WebSocket disconnected")
            if index >= len(self._frames):
                return None
            frame, _sequence = self._frames[index]
            self._connections[connection_ref] = index + 1
            self.operation_log.append(f"receive:{frame.frame_id}")
            return frame

    def _ack(self, connection_ref: str, ack_token: str) -> None:
        with self._lock:
            self._require_connection(connection_ref)
            if self.fail_ack:
                raise ConnectionError("fake WebSocket ACK failed")
            self._acknowledged_tokens.add(ack_token)
            self.ack_history.append(ack_token)
            self.operation_log.append(f"ack:{ack_token}")

    def _require_connection(self, connection_ref: str) -> int:
        if connection_ref not in self._connections:
            raise ConnectionError("fake WebSocket connection is unavailable")
        return self._connections[connection_ref]


class FakePDDWebSocketClient:
    real_network = False

    def __init__(self, server: FakePDDWebSocketServer) -> None:
        self._server = server

    def connect(
        self,
        *,
        resume_cursor: str | None,
        after_sequence: int,
    ) -> str:
        return self._server._connect(resume_cursor, after_sequence)

    def disconnect(self, connection_ref: str) -> None:
        self._server._disconnect(connection_ref)

    def ping(self, connection_ref: str, timeout_seconds: float) -> bool:
        return self._server._ping(connection_ref, timeout_seconds)

    def receive(
        self,
        connection_ref: str,
        timeout_seconds: float,
    ) -> PDDWebSocketFrame | None:
        return self._server._receive(connection_ref, timeout_seconds)

    def ack(self, connection_ref: str, ack_token: str) -> None:
        self._server._ack(connection_ref, ack_token)


__all__ = [
    "PDD_WEBSOCKET_CONTRACT_VERSION",
    "FakePDDWebSocketClient",
    "FakePDDWebSocketServer",
    "PDDWebSocketAckReceipt",
    "PDDWebSocketCheckpoint",
    "PDDWebSocketClientPort",
    "PDDWebSocketConflict",
    "PDDWebSocketConnectionError",
    "PDDWebSocketConnectionState",
    "PDDWebSocketError",
    "PDDWebSocketEvent",
    "PDDWebSocketEventParser",
    "PDDWebSocketFrame",
    "PDDWebSocketHeartbeat",
    "PDDWebSocketInboxRecord",
    "PDDWebSocketInboxState",
    "PDDWebSocketMessagePayload",
    "PDDWebSocketMissedSequence",
    "PDDWebSocketModel",
    "PDDWebSocketProtocolError",
    "PDDWebSocketSafetyError",
    "PDDWebSocketSession",
    "PDDWebSocketStore",
    "PDDWebSocketSyncState",
    "PDDWebSocketTransport",
    "PDDWebSocketTransportPort",
]
