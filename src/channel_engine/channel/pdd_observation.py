from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable
from datetime import datetime
from threading import Lock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import utc_now

from .lifecycle import (
    ChannelAuthenticationBroker,
    ChannelConnectionState,
    ChannelCredentialReference,
    ChannelHeartbeat,
    ChannelHeartbeatProbe,
    ChannelLifecycleManager,
    ChannelSession,
    ChannelSessionUnavailable,
)
from .protocol import AdapterHealth, AdapterHealthStatus, NormalizedMessage


class PDDObservationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDObservedMessage(PDDObservationModel):
    """Minimal platform boundary; no proprietary PDD payload is modeled in V1."""

    platform: Literal["pdd"] = "pdd"
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    timestamp: AwareDatetime


class PDDObservationBatch(PDDObservationModel):
    messages: tuple[PDDObservedMessage, ...] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=255)
    observed_at: AwareDatetime


class PDDObservationError(RuntimeError):
    pass


class PDDObservationUnavailable(PDDObservationError):
    pass


class PDDObservationConflict(PDDObservationError):
    pass


@runtime_checkable
class PDDObservationTransport(Protocol):
    """Receive-only real-platform boundary. It intentionally has no send API."""

    @property
    def transport_name(self) -> str:
        """Stable non-secret implementation name."""

    def open(self, session: ChannelSession) -> None:
        """Open an observation stream using broker-managed authentication."""

    def close(self, session: ChannelSession) -> None:
        """Close the observation stream and release transport state."""

    def heartbeat(self, session: ChannelSession) -> bool:
        """Check whether the receive-only observation stream is healthy."""

    def poll(
        self,
        session: ChannelSession,
        *,
        cursor: str | None,
        limit: int,
    ) -> PDDObservationBatch:
        """Read a bounded batch without acknowledging or mutating platform data."""


@runtime_checkable
class PDDObservationAdapter(Protocol):
    @property
    def channel(self) -> str:
        """Return the normalized channel name `pdd`."""

    def connect(self) -> ChannelSession:
        """Establish a receive-only session."""

    def disconnect(self) -> None:
        """Close the receive-only session."""

    def health_check(self) -> AdapterHealth:
        """Return sanitized observation health."""

    def receive_message(self) -> NormalizedMessage | None:
        """Return one normalized PDD observation, or None."""


class _PDDTransportHeartbeatProbe(ChannelHeartbeatProbe):
    def __init__(self, transport: PDDObservationTransport) -> None:
        self._transport = transport

    def probe(self, session: ChannelSession) -> bool:
        try:
            return self._transport.heartbeat(session)
        except Exception:
            return False


class PDDAdapter:
    """Observation-only PDD adapter with no outbound capability."""

    channel = "pdd"
    adapter_name = "PDDAdapterObservationV1"

    def __init__(
        self,
        credential: ChannelCredentialReference,
        authentication_broker: ChannelAuthenticationBroker,
        transport: PDDObservationTransport,
        *,
        poll_batch_size: int = 20,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= poll_batch_size <= 100:
            raise ValueError("PDD observation poll batch size must be 1..100")
        if not isinstance(transport, PDDObservationTransport):
            raise TypeError("transport does not implement PDDObservationTransport")
        self.transport = transport
        self.poll_batch_size = poll_batch_size
        self._clock = clock
        self.lifecycle = ChannelLifecycleManager(
            self.channel,
            credential,
            authentication_broker,
            _PDDTransportHeartbeatProbe(transport),
            clock=clock,
            real_platform_connection=False,
        )
        self._transport_session_id: str | None = None
        self._cursor: str | None = None
        self._pending: deque[NormalizedMessage] = deque()
        self._fingerprints: dict[tuple[str, str], str] = {}
        self._lock = Lock()
        self._receive_lock = Lock()
        self.receive_call_count = 0
        self.observed_message_count = 0
        self.duplicate_message_count = 0
        self._last_receive_error: str | None = None

    @property
    def observation_cursor(self) -> str | None:
        with self._lock:
            return self._cursor

    def connect(self) -> ChannelSession:
        session = self.lifecycle.connect()
        with self._lock:
            if self._transport_session_id == session.session_id:
                return session
        try:
            self.transport.open(session)
        except Exception as exc:
            self.lifecycle.disconnect()
            raise PDDObservationUnavailable(
                "PDD observation transport could not be opened"
            ) from exc
        with self._lock:
            self._transport_session_id = session.session_id
            self._last_receive_error = None
        return session

    def disconnect(self) -> None:
        session = self.lifecycle.get_session()
        failure: Exception | None = None
        if session is not None:
            try:
                self.transport.close(session)
            except Exception as exc:
                failure = exc
        self.lifecycle.disconnect()
        with self._lock:
            self._transport_session_id = None
        if failure is not None:
            raise PDDObservationUnavailable(
                "PDD observation transport could not be closed cleanly"
            ) from failure

    def reconnect(self) -> ChannelSession:
        self.disconnect()
        return self.connect()

    def heartbeat(self) -> ChannelHeartbeat:
        return self.lifecycle.heartbeat()

    def get_session(self) -> ChannelSession | None:
        return self.lifecycle.get_session()

    def health_check(self) -> AdapterHealth:
        connection = self.lifecycle.connection
        session = self.get_session()
        status = {
            ChannelConnectionState.CONNECTED: AdapterHealthStatus.HEALTHY,
            ChannelConnectionState.DEGRADED: AdapterHealthStatus.DEGRADED,
        }.get(connection.state, AdapterHealthStatus.UNHEALTHY)
        with self._lock:
            cursor_present = self._cursor is not None
            pending_count = len(self._pending)
            last_receive_error = self._last_receive_error
        if status is AdapterHealthStatus.HEALTHY and last_receive_error is not None:
            status = AdapterHealthStatus.DEGRADED
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=status,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "mode": "OBSERVATION_FOUNDATION",
                "platform": "pdd",
                "transport": self.transport.transport_name,
                "connection_state": connection.state.value,
                "authenticated_session": bool(
                    session is not None and session.authenticated
                ),
                "cursor_present": cursor_present,
                "pending_message_count": pending_count,
                "observed_message_count": self.observed_message_count,
                "duplicate_message_count": self.duplicate_message_count,
                "last_receive_error": last_receive_error or "NONE",
                "credential_provider": self.lifecycle.credential.provider,
                "credential_version": self.lifecycle.credential.version,
                "receive_enabled": True,
                "send_enabled": False,
                "automatic_reply_enabled": False,
                "real_pdd_connected": False,
            },
        )

    def receive_message(self) -> NormalizedMessage | None:
        with self._receive_lock:
            return self._receive_message_once()

    def _receive_message_once(self) -> NormalizedMessage | None:
        session = self._require_active_session()
        with self._lock:
            self.receive_call_count += 1
            if self._pending:
                return self._pending.popleft()
            cursor = self._cursor
        try:
            batch = self.transport.poll(
                session,
                cursor=cursor,
                limit=self.poll_batch_size,
            )
        except Exception as exc:
            with self._lock:
                self._last_receive_error = "PDD_OBSERVATION_POLL_FAILED"
            try:
                self.lifecycle.heartbeat()
            except Exception:
                pass
            raise PDDObservationUnavailable(
                "PDD observation poll failed"
            ) from exc
        if len(batch.messages) > self.poll_batch_size:
            with self._lock:
                self._last_receive_error = "PDD_OBSERVATION_BATCH_LIMIT_EXCEEDED"
            raise PDDObservationConflict(
                "PDD observation transport exceeded the requested batch limit"
            )

        accepted: list[NormalizedMessage] = []
        pending_fingerprints: dict[tuple[str, str], str] = {}
        for raw in batch.messages:
            normalized = self.map_message(raw)
            key = (
                normalized.conversation_id,
                normalized.external_message_id,
            )
            fingerprint = self._fingerprint(normalized)
            existing = pending_fingerprints.get(key, self._fingerprints.get(key))
            if existing is not None:
                if existing != fingerprint:
                    with self._lock:
                        self._last_receive_error = "PDD_MESSAGE_ID_CONFLICT"
                    raise PDDObservationConflict(
                        "PDD external_message_id was reused with different content"
                    )
                self.duplicate_message_count += 1
                continue
            pending_fingerprints[key] = fingerprint
            accepted.append(normalized)

        with self._lock:
            self._fingerprints.update(pending_fingerprints)
            self._pending.extend(accepted)
            self._cursor = batch.next_cursor
            self.observed_message_count += len(accepted)
            self._last_receive_error = None
            return self._pending.popleft() if self._pending else None

    def map_message(self, raw: PDDObservedMessage) -> NormalizedMessage:
        if raw.platform != "pdd":
            raise PDDObservationConflict("PDD adapter received another platform")
        return NormalizedMessage(
            channel=raw.platform,
            conversation_id=raw.conversation_id,
            external_message_id=raw.external_message_id,
            sender=raw.sender,
            content=raw.content,
            timestamp=raw.timestamp,
        )

    def _require_active_session(self) -> ChannelSession:
        session = self.get_session()
        connection = self.lifecycle.connection
        with self._lock:
            opened = self._transport_session_id == (
                session.session_id if session is not None else None
            )
        if (
            session is None
            or not opened
            or connection.state is not ChannelConnectionState.CONNECTED
            or session.expires_at <= self._clock()
        ):
            raise ChannelSessionUnavailable(
                "PDD receive requires a healthy observation session"
            )
        return session

    @staticmethod
    def _fingerprint(message: NormalizedMessage) -> str:
        return hashlib.sha256(
            json.dumps(
                message.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


class FakePDDObservationTransport:
    """In-memory receive-only transport for contract tests; no PDD connection."""

    transport_name = "fake-pdd-observation-transport.v1"

    def __init__(
        self,
        *,
        healthy: bool = True,
        open_unavailable: bool = False,
        poll_unavailable: bool = False,
        close_unavailable: bool = False,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.healthy = healthy
        self.open_unavailable = open_unavailable
        self.poll_unavailable = poll_unavailable
        self.close_unavailable = close_unavailable
        self._clock = clock
        self._messages: deque[PDDObservedMessage] = deque()
        self._open_sessions: set[str] = set()
        self._cursor_sequence = 0
        self._lock = Lock()
        self.open_count = 0
        self.close_count = 0
        self.heartbeat_count = 0
        self.poll_count = 0
        self.real_platform_call_count = 0

    def enqueue(self, *messages: PDDObservedMessage) -> None:
        with self._lock:
            self._messages.extend(messages)

    def open(self, session: ChannelSession) -> None:
        self.open_count += 1
        if self.open_unavailable:
            raise PDDObservationUnavailable("fake PDD observation open failed")
        with self._lock:
            self._open_sessions.add(session.session_id)

    def close(self, session: ChannelSession) -> None:
        self.close_count += 1
        with self._lock:
            self._open_sessions.discard(session.session_id)
        if self.close_unavailable:
            raise PDDObservationUnavailable("fake PDD observation close failed")

    def heartbeat(self, session: ChannelSession) -> bool:
        self.heartbeat_count += 1
        with self._lock:
            return self.healthy and session.session_id in self._open_sessions

    def poll(
        self,
        session: ChannelSession,
        *,
        cursor: str | None,
        limit: int,
    ) -> PDDObservationBatch:
        del cursor
        self.poll_count += 1
        if self.poll_unavailable:
            raise PDDObservationUnavailable("fake PDD observation poll failed")
        with self._lock:
            if session.session_id not in self._open_sessions:
                raise PDDObservationUnavailable(
                    "fake PDD observation session is not open"
                )
            messages = tuple(
                self._messages.popleft()
                for _ in range(min(limit, len(self._messages)))
            )
            if messages:
                self._cursor_sequence += 1
            next_cursor = (
                f"fake-pdd-cursor-{self._cursor_sequence}"
                if self._cursor_sequence
                else None
            )
        return PDDObservationBatch(
            messages=messages,
            next_cursor=next_cursor,
            observed_at=self._clock(),
        )


__all__ = [
    "FakePDDObservationTransport",
    "PDDAdapter",
    "PDDObservationAdapter",
    "PDDObservationBatch",
    "PDDObservationConflict",
    "PDDObservationError",
    "PDDObservationTransport",
    "PDDObservationUnavailable",
    "PDDObservedMessage",
]
