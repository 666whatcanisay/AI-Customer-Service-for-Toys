from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import Lock, RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now

from .execution_boundary import LedgerExecutionAuthorizationService
from .lifecycle import (
    ChannelAuthenticationScheme,
    ChannelCredentialReference,
    ChannelSessionUnavailable,
)
from .pdd_controlled import (
    PDDOutboundRequest,
    PDDOutboundResult,
    PDDOutboundTimeout,
    PDDOutboundTransport,
)
from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    SendAuthorizationVerifier,
)
from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelSendReceipt,
    NormalizedMessage,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PDDProductionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDProductionSafetyError(RuntimeError):
    pass


class PDDCredentialUnavailable(RuntimeError):
    pass


class PDDCredentialRotationError(RuntimeError):
    pass


class PDDObservationLedgerConflict(RuntimeError):
    pass


class PDDProductionObservationError(RuntimeError):
    pass


class PDDCredentialLease(PDDProductionModel):
    """Short-lived, non-secret capability metadata returned by a provider."""

    lease_id: str = Field(
        min_length=1,
        max_length=128,
        repr=False,
        exclude=True,
    )
    credential_id: str = Field(min_length=1, max_length=128)
    credential_version: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=64)
    account_ref: str = Field(min_length=1, max_length=128)
    principal_ref: str = Field(min_length=1, max_length=128)
    auth_scheme: ChannelAuthenticationScheme
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> PDDCredentialLease:
        if self.expires_at <= self.issued_at:
            raise ValueError("credential lease expiry must follow issuance")
        return self


@runtime_checkable
class PDDCredentialProvider(Protocol):
    """Secret-manager boundary; the engine receives only sanitized leases."""

    @property
    def provider_name(self) -> str:
        """Return a non-secret implementation identifier."""

    def acquire(self, reference: ChannelCredentialReference) -> PDDCredentialLease:
        """Resolve a secret reference inside the provider boundary."""

    def release(self, lease: PDDCredentialLease) -> None:
        """Release or revoke the short-lived capability lease."""


class _FakeCredentialRegistration(PDDProductionModel):
    reference: ChannelCredentialReference
    expires_at: AwareDatetime
    revoked: bool = False


class FakePDDCredentialProvider:
    """Secretless provider used for preparation tests; it stores no token value."""

    provider_name = "fake-pdd-secret-reference-provider.v1"

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        lease_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if lease_ttl <= timedelta(0):
            raise ValueError("credential lease TTL must be positive")
        self._clock = clock
        self._lease_ttl = lease_ttl
        self._registrations: dict[
            tuple[str, str], _FakeCredentialRegistration
        ] = {}
        self._active_leases: set[str] = set()
        self._lock = Lock()
        self.acquire_count = 0
        self.release_count = 0
        self.rotation_count = 0
        self.secret_value_access_count = 0

    def register(
        self,
        reference: ChannelCredentialReference,
        *,
        expires_at: datetime,
    ) -> None:
        if reference.provider != "secret-manager":
            raise ValueError("production PDD credentials must use secret-manager")
        expires_at = _as_utc(expires_at)
        if expires_at <= _as_utc(self._clock()):
            raise ValueError("credential registration is already expired")
        with self._lock:
            self._registrations[(reference.credential_id, reference.version)] = (
                _FakeCredentialRegistration(
                    reference=reference,
                    expires_at=expires_at,
                )
            )

    def rotate(
        self,
        current: ChannelCredentialReference,
        replacement: ChannelCredentialReference,
        *,
        expires_at: datetime,
    ) -> None:
        if (
            current.credential_id != replacement.credential_id
            or current.provider != replacement.provider
            or current.account_ref != replacement.account_ref
            or current.auth_scheme is not replacement.auth_scheme
            or current.version == replacement.version
        ):
            raise PDDCredentialRotationError(
                "credential rotation must preserve identity and change version"
            )
        self.register(replacement, expires_at=expires_at)
        with self._lock:
            existing = self._registrations.get(
                (current.credential_id, current.version)
            )
            if existing is not None:
                self._registrations[(current.credential_id, current.version)] = (
                    existing.model_copy(update={"revoked": True})
                )
            self.rotation_count += 1

    def revoke(self, reference: ChannelCredentialReference) -> None:
        with self._lock:
            key = (reference.credential_id, reference.version)
            existing = self._registrations.get(key)
            if existing is None:
                raise PDDCredentialUnavailable("credential reference is not registered")
            self._registrations[key] = existing.model_copy(update={"revoked": True})

    def acquire(self, reference: ChannelCredentialReference) -> PDDCredentialLease:
        now = _as_utc(self._clock())
        with self._lock:
            registration = self._registrations.get(
                (reference.credential_id, reference.version)
            )
            self.acquire_count += 1
            if (
                registration is None
                or registration.reference != reference
                or registration.revoked
                or registration.expires_at <= now
            ):
                raise PDDCredentialUnavailable(
                    "credential reference is missing, revoked, or expired"
                )
            lease_id = new_id("pdd-credential-lease")
            self._active_leases.add(lease_id)
            return PDDCredentialLease(
                lease_id=lease_id,
                credential_id=reference.credential_id,
                credential_version=reference.version,
                provider=reference.provider,
                account_ref=reference.account_ref,
                principal_ref=f"pdd-principal:{reference.account_ref}",
                auth_scheme=reference.auth_scheme,
                issued_at=now,
                expires_at=min(now + self._lease_ttl, registration.expires_at),
            )

    def release(self, lease: PDDCredentialLease) -> None:
        with self._lock:
            if lease.lease_id in self._active_leases:
                self._active_leases.remove(lease.lease_id)
                self.release_count += 1


class PDDProductionSessionState(StrEnum):
    CREATED = "CREATED"
    CONNECTED = "CONNECTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DISCONNECTED = "DISCONNECTED"


class PDDProductionSession(PDDProductionModel):
    session_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0)
    channel: Literal["pdd"] = "pdd"
    account_ref: str = Field(min_length=1, max_length=128)
    credential_id: str = Field(min_length=1, max_length=128)
    credential_version: str = Field(min_length=1, max_length=64)
    credential_provider: str = Field(min_length=1, max_length=64)
    credential_lease_id: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
    )
    state: PDDProductionSessionState
    created_at: AwareDatetime
    connected_at: AwareDatetime | None = None
    activated_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    last_heartbeat_at: AwareDatetime | None = None
    authenticated: bool = False
    failure_code: str | None = Field(default=None, max_length=128)
    real_platform_connected: bool = False

    @model_validator(mode="after")
    def validate_state(self) -> PDDProductionSession:
        connected = self.state in {
            PDDProductionSessionState.CONNECTED,
            PDDProductionSessionState.ACTIVE,
        }
        if connected and (
            not self.authenticated
            or self.credential_lease_id is None
            or self.connected_at is None
            or self.expires_at is None
        ):
            raise ValueError("connected production session requires a credential lease")
        if self.state is PDDProductionSessionState.ACTIVE and self.activated_at is None:
            raise ValueError("ACTIVE production session requires activation time")
        if self.state in {
            PDDProductionSessionState.CREATED,
            PDDProductionSessionState.DISCONNECTED,
            PDDProductionSessionState.EXPIRED,
        } and self.authenticated:
            raise ValueError("inactive production session cannot be authenticated")
        return self


class PDDProductionHeartbeat(PDDProductionModel):
    session_id: str
    state: PDDProductionSessionState
    healthy: bool
    checked_at: AwareDatetime
    failure_code: str | None = None
    real_platform_contacted: bool = False


class PDDProductionObservedMessage(PDDProductionModel):
    platform: Literal["pdd"] = "pdd"
    offset: int = Field(ge=0)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    timestamp: AwareDatetime


class PDDProductionObservationBatch(PDDProductionModel):
    messages: tuple[PDDProductionObservedMessage, ...] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=255)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_cursor(self) -> PDDProductionObservationBatch:
        if self.messages and self.next_cursor is None:
            raise ValueError("non-empty observation batch requires next_cursor")
        return self


@runtime_checkable
class PDDProductionObservationTransport(Protocol):
    @property
    def transport_name(self) -> str:
        """Return a stable implementation name."""

    @property
    def real_platform_transport(self) -> bool:
        """Declare whether this implementation contacts real PDD."""

    def open(self, session: PDDProductionSession) -> None:
        """Open a session using only sanitized capability metadata."""

    def close(self, session: PDDProductionSession) -> None:
        """Close the observation session."""

    def heartbeat(self, session: PDDProductionSession) -> bool:
        """Return whether the session can become ACTIVE."""

    def poll(
        self,
        session: PDDProductionSession,
        *,
        cursor: str | None,
        after_offset: int,
        limit: int,
    ) -> PDDProductionObservationBatch:
        """Return an ordered batch after the committed checkpoint."""


class PDDProductionObservationActivationGrant(PDDProductionModel):
    """Evidence-bound permission to instantiate a real receive-only transport.

    This is configuration metadata, not a credential and not a network handle.
    The default composition provides no grant.
    """

    grant_id: str = Field(min_length=1, max_length=128)
    transport_name: str = Field(min_length=1, max_length=160)
    selector_contract_id: str = Field(min_length=1, max_length=160)
    selector_evidence_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^evidence-ref://[^\s\r\n]+$",
    )
    selector_synthetic_test_data: Literal[False] = False
    credential_reference_only: Literal[True] = True
    rbac_enforced: Literal[True] = True
    monitoring_enabled: Literal[True] = True
    receive_only: Literal[True] = True
    send_enabled: Literal[False] = False
    issued_by: str = Field(min_length=1, max_length=160)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry(self) -> PDDProductionObservationActivationGrant:
        if self.expires_at <= self.issued_at:
            raise ValueError("PDD observation activation grant must expire")
        return self


class FakePDDProductionObservationTransport:
    transport_name = "fake-pdd-production-observation-transport.v1"
    real_platform_transport = False

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        healthy: bool = True,
        open_unavailable: bool = False,
        poll_unavailable: bool = False,
    ) -> None:
        self._clock = clock
        self.healthy = healthy
        self.open_unavailable = open_unavailable
        self.poll_unavailable = poll_unavailable
        self._batches: deque[PDDProductionObservationBatch] = deque()
        self._open_sessions: set[str] = set()
        self._lock = Lock()
        self.open_count = 0
        self.close_count = 0
        self.heartbeat_count = 0
        self.poll_count = 0
        self.real_platform_call_count = 0
        self.poll_history: list[tuple[str | None, int]] = []

    def enqueue_batch(
        self,
        *messages: PDDProductionObservedMessage,
        next_cursor: str,
        observed_at: datetime | None = None,
    ) -> None:
        batch = PDDProductionObservationBatch(
            messages=tuple(messages),
            next_cursor=next_cursor,
            observed_at=_as_utc(observed_at or self._clock()),
        )
        with self._lock:
            self._batches.append(batch)

    def open(self, session: PDDProductionSession) -> None:
        self.open_count += 1
        if self.open_unavailable:
            raise PDDProductionObservationError(
                "fake production observation open failed"
            )
        with self._lock:
            self._open_sessions.add(session.session_id)

    def close(self, session: PDDProductionSession) -> None:
        self.close_count += 1
        with self._lock:
            self._open_sessions.discard(session.session_id)

    def heartbeat(self, session: PDDProductionSession) -> bool:
        self.heartbeat_count += 1
        with self._lock:
            return self.healthy and session.session_id in self._open_sessions

    def poll(
        self,
        session: PDDProductionSession,
        *,
        cursor: str | None,
        after_offset: int,
        limit: int,
    ) -> PDDProductionObservationBatch:
        self.poll_count += 1
        self.poll_history.append((cursor, after_offset))
        if self.poll_unavailable:
            raise PDDProductionObservationError(
                "fake production observation poll failed"
            )
        with self._lock:
            if session.session_id not in self._open_sessions:
                raise PDDProductionObservationError(
                    "fake production observation session is not open"
                )
            if not self._batches:
                return PDDProductionObservationBatch(
                    messages=(),
                    next_cursor=cursor,
                    observed_at=self._clock(),
                )
            batch = self._batches.popleft()
        if len(batch.messages) > limit:
            raise PDDProductionObservationError(
                "fake production observation batch exceeds requested limit"
            )
        return batch


class PDDObservationSyncStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    SYNCING = "SYNCING"
    IN_SYNC = "IN_SYNC"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class PDDObservationCheckpoint(PDDProductionModel):
    stream_id: str = Field(min_length=1, max_length=255)
    revision: int = Field(ge=0)
    cursor: str | None = Field(default=None, max_length=255)
    offset: int = Field(default=-1, ge=-1)
    accepted_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    last_message_at: AwareDatetime | None = None
    last_sync_at: AwareDatetime | None = None
    sync_status: PDDObservationSyncStatus = PDDObservationSyncStatus.NOT_STARTED
    last_error_code: str | None = Field(default=None, max_length=128)


@runtime_checkable
class PDDObservationLedger(Protocol):
    """CAS checkpoint and durable-dedup boundary for a production store."""

    def load(self, stream_id: str) -> PDDObservationCheckpoint:
        """Load the committed cursor/offset and sync metadata."""

    def lookup_fingerprints(
        self,
        stream_id: str,
        keys: tuple[str, ...],
    ) -> Mapping[str, str]:
        """Return previously committed message fingerprints."""

    def begin_sync(
        self,
        checkpoint: PDDObservationCheckpoint,
        at: datetime,
    ) -> PDDObservationCheckpoint:
        """CAS transition to SYNCING."""

    def commit_batch(
        self,
        checkpoint: PDDObservationCheckpoint,
        *,
        cursor: str | None,
        offset: int,
        fingerprints: Mapping[str, str],
        accepted_increment: int,
        duplicate_increment: int,
        last_message_at: datetime | None,
        synced_at: datetime,
    ) -> PDDObservationCheckpoint:
        """Atomically commit cursor, offset and dedup fingerprints."""

    def fail_sync(
        self,
        checkpoint: PDDObservationCheckpoint,
        *,
        error_code: str,
        failed_at: datetime,
        terminal: bool,
    ) -> PDDObservationCheckpoint:
        """Record a sanitized failure without advancing cursor or offset."""


class InMemoryPDDObservationLedger:
    """Thread-safe test ledger implementing the future persistent-store contract."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, PDDObservationCheckpoint] = {}
        self._fingerprints: dict[str, dict[str, str]] = {}
        self._lock = Lock()

    @staticmethod
    def _initial(stream_id: str) -> PDDObservationCheckpoint:
        return PDDObservationCheckpoint(stream_id=stream_id, revision=0)

    def load(self, stream_id: str) -> PDDObservationCheckpoint:
        with self._lock:
            return self._checkpoints.get(stream_id, self._initial(stream_id))

    def lookup_fingerprints(
        self,
        stream_id: str,
        keys: tuple[str, ...],
    ) -> Mapping[str, str]:
        with self._lock:
            records = self._fingerprints.get(stream_id, {})
            return {key: records[key] for key in keys if key in records}

    def begin_sync(
        self,
        checkpoint: PDDObservationCheckpoint,
        at: datetime,
    ) -> PDDObservationCheckpoint:
        with self._lock:
            current = self._checkpoints.get(
                checkpoint.stream_id,
                self._initial(checkpoint.stream_id),
            )
            self._assert_revision(current, checkpoint)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "sync_status": PDDObservationSyncStatus.SYNCING,
                    "last_sync_at": _as_utc(at),
                    "last_error_code": None,
                }
            )
            self._checkpoints[checkpoint.stream_id] = updated
            return updated

    def commit_batch(
        self,
        checkpoint: PDDObservationCheckpoint,
        *,
        cursor: str | None,
        offset: int,
        fingerprints: Mapping[str, str],
        accepted_increment: int,
        duplicate_increment: int,
        last_message_at: datetime | None,
        synced_at: datetime,
    ) -> PDDObservationCheckpoint:
        if offset < checkpoint.offset:
            raise PDDObservationLedgerConflict("observation offset cannot move backward")
        if accepted_increment < 0 or duplicate_increment < 0:
            raise ValueError("observation counters cannot decrement")
        with self._lock:
            current = self._checkpoints.get(
                checkpoint.stream_id,
                self._initial(checkpoint.stream_id),
            )
            self._assert_revision(current, checkpoint)
            records = self._fingerprints.setdefault(checkpoint.stream_id, {})
            for key, fingerprint in fingerprints.items():
                existing = records.get(key)
                if existing is not None and existing != fingerprint:
                    raise PDDObservationLedgerConflict(
                        "message identity is bound to different content"
                    )
            records.update(fingerprints)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "cursor": cursor,
                    "offset": offset,
                    "accepted_count": current.accepted_count + accepted_increment,
                    "duplicate_count": current.duplicate_count + duplicate_increment,
                    "last_message_at": (
                        _as_utc(last_message_at)
                        if last_message_at is not None
                        else current.last_message_at
                    ),
                    "last_sync_at": _as_utc(synced_at),
                    "sync_status": PDDObservationSyncStatus.IN_SYNC,
                    "last_error_code": None,
                }
            )
            self._checkpoints[checkpoint.stream_id] = updated
            return updated

    def fail_sync(
        self,
        checkpoint: PDDObservationCheckpoint,
        *,
        error_code: str,
        failed_at: datetime,
        terminal: bool,
    ) -> PDDObservationCheckpoint:
        with self._lock:
            current = self._checkpoints.get(
                checkpoint.stream_id,
                self._initial(checkpoint.stream_id),
            )
            self._assert_revision(current, checkpoint)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "last_sync_at": _as_utc(failed_at),
                    "sync_status": (
                        PDDObservationSyncStatus.FAILED
                        if terminal
                        else PDDObservationSyncStatus.DEGRADED
                    ),
                    "last_error_code": error_code,
                }
            )
            self._checkpoints[checkpoint.stream_id] = updated
            return updated

    @staticmethod
    def _assert_revision(
        current: PDDObservationCheckpoint,
        proposed: PDDObservationCheckpoint,
    ) -> None:
        if current.revision != proposed.revision:
            raise PDDObservationLedgerConflict(
                "observation checkpoint revision was concurrently modified"
            )


class PDDProductionSessionManager:
    """Five-state session lifecycle with secret-reference rotation support."""

    def __init__(
        self,
        credential: ChannelCredentialReference,
        credential_provider: PDDCredentialProvider,
        transport: PDDProductionObservationTransport,
        *,
        activation_grant: PDDProductionObservationActivationGrant | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if credential.provider != "secret-manager":
            raise PDDProductionSafetyError(
                "Production PDD adapter requires a secret-manager reference"
            )
        if not isinstance(credential_provider, PDDCredentialProvider):
            raise TypeError("credential provider does not implement the contract")
        if not isinstance(transport, PDDProductionObservationTransport):
            raise TypeError("observation transport does not implement the contract")
        if transport.real_platform_transport:
            if activation_grant is None:
                raise PDDProductionSafetyError(
                    "real PDD transport requires an evidence-bound activation grant"
                )
            self._assert_activation_grant(activation_grant, transport, clock())
        elif activation_grant is not None:
            raise PDDProductionSafetyError(
                "real transport activation grant cannot be attached to a fake transport"
            )
        self.credential = credential
        self.credential_provider = credential_provider
        self.transport = transport
        self.activation_grant = activation_grant
        self._clock = clock
        self._lock = RLock()
        self._lease: PDDCredentialLease | None = None
        self._generation = 0
        self._history = [PDDProductionSessionState.CREATED]
        self._session = self._new_inactive(PDDProductionSessionState.CREATED)

    @property
    def state(self) -> PDDProductionSessionState:
        with self._lock:
            return self._session.state

    @property
    def history(self) -> tuple[PDDProductionSessionState, ...]:
        with self._lock:
            return tuple(self._history)

    def get_session(self) -> PDDProductionSession:
        with self._lock:
            return self._session

    def connect(self) -> PDDProductionSession:
        with self._lock:
            if self._session.state in {
                PDDProductionSessionState.CONNECTED,
                PDDProductionSessionState.ACTIVE,
            }:
                return self._session
            if self.transport.real_platform_transport:
                assert self.activation_grant is not None
                self._assert_activation_grant(
                    self.activation_grant,
                    self.transport,
                    self._clock(),
                )
            lease = self.credential_provider.acquire(self.credential)
            self._assert_lease_identity(lease)
            now = _as_utc(self._clock())
            self._generation += 1
            connected = PDDProductionSession(
                session_id=new_id("pdd-production-session"),
                generation=self._generation,
                account_ref=self.credential.account_ref,
                credential_id=self.credential.credential_id,
                credential_version=lease.credential_version,
                credential_provider=lease.provider,
                credential_lease_id=lease.lease_id,
                state=PDDProductionSessionState.CONNECTED,
                created_at=now,
                connected_at=now,
                expires_at=lease.expires_at,
                authenticated=True,
                real_platform_connected=self.transport.real_platform_transport,
            )
            try:
                self.transport.open(connected)
            except Exception as exc:
                self.credential_provider.release(lease)
                self._lease = None
                self._session = self._new_inactive(
                    PDDProductionSessionState.DISCONNECTED,
                    failure_code="PDD_SESSION_OPEN_FAILED",
                )
                self._history.append(PDDProductionSessionState.DISCONNECTED)
                raise ChannelSessionUnavailable(
                    "PDD production-preparation session could not connect"
                ) from exc
            self._lease = lease
            self._session = connected
            self._history.append(PDDProductionSessionState.CONNECTED)
            return connected

    def heartbeat(self) -> PDDProductionHeartbeat:
        with self._lock:
            session = self._session
            now = _as_utc(self._clock())
            if session.state not in {
                PDDProductionSessionState.CONNECTED,
                PDDProductionSessionState.ACTIVE,
            }:
                raise ChannelSessionUnavailable(
                    "PDD session must be CONNECTED or ACTIVE for heartbeat"
                )
            if session.expires_at is None or _as_utc(session.expires_at) <= now:
                self._expire(now)
                return PDDProductionHeartbeat(
                    session_id=session.session_id,
                    state=PDDProductionSessionState.EXPIRED,
                    healthy=False,
                    checked_at=now,
                    failure_code="PDD_SESSION_EXPIRED",
                    real_platform_contacted=False,
                )
            try:
                healthy = self.transport.heartbeat(session)
            except Exception:
                healthy = False
            if healthy:
                activated_at = session.activated_at or now
                self._session = session.model_copy(
                    update={
                        "state": PDDProductionSessionState.ACTIVE,
                        "activated_at": activated_at,
                        "last_heartbeat_at": now,
                        "failure_code": None,
                    }
                )
                if not self._history or self._history[-1] is not PDDProductionSessionState.ACTIVE:
                    self._history.append(PDDProductionSessionState.ACTIVE)
                return PDDProductionHeartbeat(
                    session_id=session.session_id,
                    state=PDDProductionSessionState.ACTIVE,
                    healthy=True,
                    checked_at=now,
                    real_platform_contacted=self.transport.real_platform_transport,
                )
            self._session = session.model_copy(
                update={
                    "state": PDDProductionSessionState.CONNECTED,
                    "last_heartbeat_at": now,
                    "failure_code": "PDD_SESSION_HEARTBEAT_FAILED",
                }
            )
            if not self._history or self._history[-1] is not PDDProductionSessionState.CONNECTED:
                self._history.append(PDDProductionSessionState.CONNECTED)
            return PDDProductionHeartbeat(
                session_id=session.session_id,
                state=PDDProductionSessionState.CONNECTED,
                healthy=False,
                checked_at=now,
                failure_code="PDD_SESSION_HEARTBEAT_FAILED",
                real_platform_contacted=self.transport.real_platform_transport,
            )

    def require_active(self) -> PDDProductionSession:
        with self._lock:
            now = _as_utc(self._clock())
            if (
                self._session.expires_at is not None
                and _as_utc(self._session.expires_at) <= now
                and self._session.state
                in {
                    PDDProductionSessionState.CONNECTED,
                    PDDProductionSessionState.ACTIVE,
                }
            ):
                self._expire(now)
            if self._session.state is not PDDProductionSessionState.ACTIVE:
                raise ChannelSessionUnavailable(
                    "PDD production session is not ACTIVE"
                )
            return self._session

    def disconnect(self) -> PDDProductionSession:
        with self._lock:
            session = self._session
            if session.state is PDDProductionSessionState.DISCONNECTED:
                return session
            if session.state in {
                PDDProductionSessionState.CONNECTED,
                PDDProductionSessionState.ACTIVE,
            }:
                try:
                    self.transport.close(session)
                except Exception:
                    pass
            self._release_lease()
            self._session = self._new_inactive(
                PDDProductionSessionState.DISCONNECTED
            )
            self._history.append(PDDProductionSessionState.DISCONNECTED)
            return self._session

    def reconnect(self) -> PDDProductionSession:
        self.disconnect()
        self.connect()
        heartbeat = self.heartbeat()
        if not heartbeat.healthy:
            raise ChannelSessionUnavailable(
                "PDD production session recovery did not become ACTIVE"
            )
        return self.get_session()

    def replace_credential(
        self,
        replacement: ChannelCredentialReference,
    ) -> None:
        with self._lock:
            if self._session.state not in {
                PDDProductionSessionState.CREATED,
                PDDProductionSessionState.EXPIRED,
                PDDProductionSessionState.DISCONNECTED,
            }:
                raise PDDCredentialRotationError(
                    "disconnect the PDD session before credential rotation"
                )
            if (
                replacement.provider != "secret-manager"
                or replacement.credential_id != self.credential.credential_id
                or replacement.account_ref != self.credential.account_ref
                or replacement.auth_scheme is not self.credential.auth_scheme
                or replacement.version == self.credential.version
            ):
                raise PDDCredentialRotationError(
                    "replacement must preserve credential identity and change version"
                )
            self._release_lease()
            self.credential = replacement
            self._session = self._new_inactive(self._session.state)

    def _new_inactive(
        self,
        state: PDDProductionSessionState,
        *,
        failure_code: str | None = None,
    ) -> PDDProductionSession:
        return PDDProductionSession(
            session_id=new_id("pdd-production-session"),
            generation=self._generation,
            account_ref=self.credential.account_ref,
            credential_id=self.credential.credential_id,
            credential_version=self.credential.version,
            credential_provider=self.credential.provider,
            state=state,
            created_at=_as_utc(self._clock()),
            authenticated=False,
            failure_code=failure_code,
            real_platform_connected=False,
        )

    def _assert_lease_identity(self, lease: PDDCredentialLease) -> None:
        if (
            lease.credential_id != self.credential.credential_id
            or lease.credential_version != self.credential.version
            or lease.provider != self.credential.provider
            or lease.account_ref != self.credential.account_ref
            or lease.auth_scheme is not self.credential.auth_scheme
        ):
            self.credential_provider.release(lease)
            raise PDDCredentialUnavailable(
                "credential provider returned mismatched lease metadata"
            )

    @staticmethod
    def _assert_activation_grant(
        grant: PDDProductionObservationActivationGrant,
        transport: PDDProductionObservationTransport,
        now: datetime,
    ) -> None:
        if (
            grant.transport_name != transport.transport_name
            or _as_utc(grant.expires_at) <= _as_utc(now)
            or not grant.receive_only
            or grant.send_enabled
        ):
            raise PDDProductionSafetyError(
                "PDD observation activation grant is invalid or expired"
            )

    def _expire(self, now: datetime) -> None:
        session = self._session
        try:
            self.transport.close(session)
        except Exception:
            pass
        self._release_lease()
        self._session = session.model_copy(
            update={
                "state": PDDProductionSessionState.EXPIRED,
                "authenticated": False,
                "last_heartbeat_at": now,
                "failure_code": "PDD_SESSION_EXPIRED",
            }
        )
        self._history.append(PDDProductionSessionState.EXPIRED)

    def _release_lease(self) -> None:
        if self._lease is not None:
            self.credential_provider.release(self._lease)
            self._lease = None


class PDDProductionAction(StrEnum):
    SEND_MESSAGE = "SEND_MESSAGE"
    AUTOMATIC_REPLY = "AUTOMATIC_REPLY"
    REFUND = "REFUND"
    MODIFY_ORDER = "MODIFY_ORDER"
    PAYMENT = "PAYMENT"


class PDDProductionRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PDDProductionPolicyDecision(StrEnum):
    ALLOW_SEND_MESSAGE = "ALLOW_SEND_MESSAGE"
    DENY = "DENY"


class PDDProductionPolicyConfig(PDDProductionModel):
    allowed_account_refs: frozenset[str] = Field(min_length=1)
    allowed_conversation_ids: frozenset[str] = Field(min_length=1)
    allowed_risk_levels: frozenset[PDDProductionRiskLevel] = frozenset(
        {PDDProductionRiskLevel.LOW}
    )
    blocked_actions: frozenset[PDDProductionAction] = frozenset(
        {
            PDDProductionAction.AUTOMATIC_REPLY,
            PDDProductionAction.REFUND,
            PDDProductionAction.MODIFY_ORDER,
            PDDProductionAction.PAYMENT,
        }
    )

    @model_validator(mode="after")
    def validate_guardrails(self) -> PDDProductionPolicyConfig:
        mandatory = {
            PDDProductionAction.AUTOMATIC_REPLY,
            PDDProductionAction.REFUND,
            PDDProductionAction.MODIFY_ORDER,
            PDDProductionAction.PAYMENT,
        }
        if not mandatory.issubset(self.blocked_actions):
            raise ValueError("mandatory high-impact actions must remain blocked")
        if PDDProductionAction.SEND_MESSAGE in self.blocked_actions:
            raise ValueError("SEND_MESSAGE cannot be both allowed and blocked")
        if self.allowed_risk_levels != frozenset({PDDProductionRiskLevel.LOW}):
            raise ValueError("preparation V1 permits only LOW risk")
        return self


class PDDProductionPolicyResult(PDDProductionModel):
    decision: PDDProductionPolicyDecision
    reason_code: str = Field(min_length=1, max_length=128)
    action: PDDProductionAction
    risk_level: PDDProductionRiskLevel
    account_allowed: bool
    conversation_allowed: bool
    blocked_action: bool


class PDDProductionSendPolicy:
    def __init__(self, config: PDDProductionPolicyConfig) -> None:
        self.config = config

    def evaluate(
        self,
        command: AuthorizedOutboundMessage,
        *,
        account_ref: str,
    ) -> PDDProductionPolicyResult:
        try:
            action = PDDProductionAction(command.authorization.operation)
        except ValueError:
            action = PDDProductionAction.AUTOMATIC_REPLY
        try:
            risk = PDDProductionRiskLevel(command.authorization.execution_risk)
        except ValueError:
            risk = PDDProductionRiskLevel.HIGH
        return self.evaluate_action(
            action=action,
            risk_level=risk,
            account_ref=account_ref,
            conversation_id=command.message.conversation_id,
        )

    def evaluate_action(
        self,
        *,
        action: PDDProductionAction,
        risk_level: PDDProductionRiskLevel,
        account_ref: str,
        conversation_id: str,
    ) -> PDDProductionPolicyResult:
        blocked = action in self.config.blocked_actions
        account_allowed = account_ref in self.config.allowed_account_refs
        conversation_allowed = (
            conversation_id in self.config.allowed_conversation_ids
        )
        allowed = (
            action is PDDProductionAction.SEND_MESSAGE
            and not blocked
            and risk_level in self.config.allowed_risk_levels
            and account_allowed
            and conversation_allowed
        )
        if blocked:
            reason = "PDD_ACTION_BLOCKED"
        elif action is not PDDProductionAction.SEND_MESSAGE:
            reason = "PDD_ACTION_NOT_ALLOWED"
        elif risk_level not in self.config.allowed_risk_levels:
            reason = "PDD_RISK_LEVEL_DENIED"
        elif not account_allowed:
            reason = "PDD_ACCOUNT_NOT_ALLOWLISTED"
        elif not conversation_allowed:
            reason = "PDD_CONVERSATION_NOT_ALLOWLISTED"
        else:
            reason = "PDD_SEND_POLICY_ALLOWED"
        return PDDProductionPolicyResult(
            decision=(
                PDDProductionPolicyDecision.ALLOW_SEND_MESSAGE
                if allowed
                else PDDProductionPolicyDecision.DENY
            ),
            reason_code=reason,
            action=action,
            risk_level=risk_level,
            account_allowed=account_allowed,
            conversation_allowed=conversation_allowed,
            blocked_action=blocked,
        )

    def assert_allowed(
        self,
        command: AuthorizedOutboundMessage,
        *,
        account_ref: str,
    ) -> PDDProductionPolicyResult:
        result = self.evaluate(command, account_ref=account_ref)
        if result.decision is not PDDProductionPolicyDecision.ALLOW_SEND_MESSAGE:
            raise ExecutionBoundaryDenied(result.reason_code)
        return result


class ProductionPDDAdapter:
    """Production-shaped adapter locked to non-network preparation transports."""

    channel = "pdd"
    adapter_name = "ProductionPDDAdapterPreparationV1"

    def __init__(
        self,
        credential: ChannelCredentialReference,
        credential_provider: PDDCredentialProvider,
        observation_transport: PDDProductionObservationTransport,
        outbound_transport: PDDOutboundTransport,
        observation_ledger: PDDObservationLedger,
        authorization_verifier: SendAuthorizationVerifier,
        policy: PDDProductionSendPolicy,
        *,
        poll_batch_size: int = 20,
        send_timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= poll_batch_size <= 100:
            raise ValueError("PDD production poll batch size must be 1..100")
        if send_timeout_seconds <= 0:
            raise ValueError("PDD production send timeout must be positive")
        if not isinstance(outbound_transport, PDDOutboundTransport):
            raise TypeError("outbound transport does not implement the contract")
        if outbound_transport.real_platform_transport:
            raise PDDProductionSafetyError(
                "real PDD outbound is disabled in preparation V1"
            )
        if not isinstance(observation_ledger, PDDObservationLedger):
            raise TypeError("observation ledger does not implement the contract")
        self._clock = clock
        self.session_manager = PDDProductionSessionManager(
            credential,
            credential_provider,
            observation_transport,
            clock=clock,
        )
        self.observation_transport = observation_transport
        self.outbound_transport = outbound_transport
        self.observation_ledger = observation_ledger
        self._authorization_verifier = authorization_verifier
        self.policy = policy
        self.poll_batch_size = poll_batch_size
        self.send_timeout_seconds = send_timeout_seconds
        self._stream_id = f"pdd:{credential.account_ref}"
        self._pending: deque[NormalizedMessage] = deque()
        self._receive_lock = Lock()
        self._send_lock = Lock()
        self._send_results: dict[str, tuple[str, ChannelSendReceipt]] = {}
        self.receive_call_count = 0
        self.send_call_count = 0
        self.last_message_latency_ms: int | None = None
        self.max_message_latency_ms: int | None = None

    def connect(self) -> PDDProductionSession:
        return self.session_manager.connect()

    def disconnect(self) -> None:
        self.session_manager.disconnect()

    def heartbeat(self) -> PDDProductionHeartbeat:
        return self.session_manager.heartbeat()

    def reconnect(self) -> PDDProductionSession:
        return self.session_manager.reconnect()

    def rotate_credentials(
        self,
        replacement: ChannelCredentialReference,
    ) -> None:
        self.session_manager.replace_credential(replacement)

    def get_session(self) -> PDDProductionSession:
        return self.session_manager.get_session()

    def receive_message(self) -> NormalizedMessage | None:
        with self._receive_lock:
            self.receive_call_count += 1
            self.session_manager.require_active()
            if self._pending:
                return self._pending.popleft()
            self._synchronize_once()
            return self._pending.popleft() if self._pending else None

    def send_message(
        self,
        command: AuthorizedOutboundMessage,
    ) -> ChannelSendReceipt:
        if not isinstance(command, AuthorizedOutboundMessage):
            raise ExecutionBoundaryDenied(
                "ProductionPDDAdapter rejects a bare outbound message"
            )
        session = self.session_manager.require_active()
        self._authorization_verifier.verify(command)
        policy_result = self.policy.assert_allowed(
            command,
            account_ref=session.account_ref,
        )
        message = command.message
        fingerprint = self._fingerprint(message.model_dump(mode="json"))
        with self._send_lock:
            replay = self._send_results.get(message.idempotency_key)
            if replay is not None:
                original_fingerprint, original_receipt = replay
                if original_fingerprint != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "PDD idempotency key is bound to different content"
                    )
                return original_receipt
            self.send_call_count += 1
            request = PDDOutboundRequest(
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                content=message.content,
                requested_at=message.requested_at,
            )
            try:
                result = self.outbound_transport.send(
                    session,  # type: ignore[arg-type]
                    request,
                    timeout_seconds=self.send_timeout_seconds,
                )
            except PDDOutboundTimeout:
                result = PDDOutboundResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    error_code="PDD_PRODUCTION_PREP_TIMEOUT_UNKNOWN",
                    result_category="TIMEOUT_UNKNOWN",
                    completed_at=self._clock(),
                )
            except ExecutionBoundaryDenied:
                raise
            except Exception:
                result = PDDOutboundResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    error_code="PDD_PRODUCTION_PREP_TRANSPORT_UNKNOWN",
                    result_category="TRANSPORT_EXCEPTION_UNKNOWN",
                    completed_at=self._clock(),
                )
            receipt = ChannelSendReceipt(
                receipt_id=new_id("pdd-production-prep-send-receipt"),
                channel="pdd",
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                external_message_id=result.external_message_id,
                outcome=result.outcome,
                error_code=result.error_code,
                details={
                    "mode": "PRODUCTION_PREPARATION_FAKE",
                    "adapter": self.adapter_name,
                    "policy": policy_result.decision.value,
                    "policy_reason": policy_result.reason_code,
                    "risk_level": policy_result.risk_level.value,
                    "allowlisted_account": policy_result.account_allowed,
                    "allowlisted_conversation": policy_result.conversation_allowed,
                    "blocked_action": policy_result.blocked_action,
                    "authorization_id": command.authorization.authorization_id,
                    "decision_id": command.authorization.decision_id,
                    "approval_id": command.authorization.approval_id,
                    "result_category": result.result_category,
                    "outbound_transport": self.outbound_transport.transport_name,
                    "automatic_reply": False,
                    "real_platform_called": False,
                    "customer_message_sent": False,
                    "refund_performed": False,
                    "order_modified": False,
                    "payment_performed": False,
                },
                recorded_at=result.completed_at,
            )
            self._send_results[message.idempotency_key] = (
                fingerprint,
                receipt,
            )
            return receipt

    def health_check(self) -> AdapterHealth:
        session = self.get_session()
        checkpoint = self.observation_ledger.load(self._stream_id)
        if session.state is PDDProductionSessionState.ACTIVE:
            status = (
                AdapterHealthStatus.DEGRADED
                if checkpoint.sync_status
                in {
                    PDDObservationSyncStatus.DEGRADED,
                    PDDObservationSyncStatus.FAILED,
                }
                else AdapterHealthStatus.HEALTHY
            )
        elif session.state is PDDProductionSessionState.CONNECTED:
            status = AdapterHealthStatus.DEGRADED
        else:
            status = AdapterHealthStatus.UNHEALTHY
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel="pdd",
            status=status,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "mode": "PRODUCTION_PREPARATION",
                "session_state": session.state.value,
                "session_generation": session.generation,
                "credential_provider": session.credential_provider,
                "credential_version": session.credential_version,
                "credential_expires_at": (
                    session.expires_at.isoformat()
                    if session.expires_at is not None
                    else "NONE"
                ),
                "sync_status": checkpoint.sync_status.value,
                "cursor": checkpoint.cursor or "NONE",
                "offset": checkpoint.offset,
                "checkpoint_revision": checkpoint.revision,
                "accepted_message_count": checkpoint.accepted_count,
                "duplicate_message_count": checkpoint.duplicate_count,
                "last_message_latency_ms": self.last_message_latency_ms,
                "max_message_latency_ms": self.max_message_latency_ms,
                "last_sync_at": (
                    checkpoint.last_sync_at.isoformat()
                    if checkpoint.last_sync_at is not None
                    else "NONE"
                ),
                "last_sync_error": checkpoint.last_error_code or "NONE",
                "observation_transport": self.observation_transport.transport_name,
                "outbound_transport": self.outbound_transport.transport_name,
                "send_policy": "ALLOW_SEND_MESSAGE_AFTER_LIVE_LEDGER_CHECK",
                "automatic_reply_enabled": False,
                "real_pdd_observation_enabled": False,
                "real_pdd_send_enabled": False,
                "refund_enabled": False,
                "order_mutation_enabled": False,
                "payment_enabled": False,
            },
        )

    def _synchronize_once(self) -> None:
        session = self.session_manager.require_active()
        checkpoint = self.observation_ledger.load(self._stream_id)
        syncing = self.observation_ledger.begin_sync(checkpoint, self._clock())
        try:
            batch = self.observation_transport.poll(
                session,
                cursor=checkpoint.cursor,
                after_offset=checkpoint.offset,
                limit=self.poll_batch_size,
            )
            accepted, fingerprints, duplicates, next_offset, last_message_at = (
                self._validate_batch(checkpoint, batch)
            )
            self.observation_ledger.commit_batch(
                syncing,
                cursor=batch.next_cursor,
                offset=next_offset,
                fingerprints=fingerprints,
                accepted_increment=len(accepted),
                duplicate_increment=duplicates,
                last_message_at=last_message_at,
                synced_at=batch.observed_at,
            )
        except PDDObservationLedgerConflict:
            try:
                self.observation_ledger.fail_sync(
                    syncing,
                    error_code="PDD_OBSERVATION_LEDGER_CONFLICT",
                    failed_at=self._clock(),
                    terminal=True,
                )
            except PDDObservationLedgerConflict:
                pass
            raise
        except Exception as exc:
            try:
                self.observation_ledger.fail_sync(
                    syncing,
                    error_code="PDD_OBSERVATION_SYNC_FAILED",
                    failed_at=self._clock(),
                    terminal=False,
                )
            except PDDObservationLedgerConflict:
                pass
            raise PDDProductionObservationError(
                "PDD production-preparation observation sync failed"
            ) from exc
        self._pending.extend(accepted)

    def _validate_batch(
        self,
        checkpoint: PDDObservationCheckpoint,
        batch: PDDProductionObservationBatch,
    ) -> tuple[
        tuple[NormalizedMessage, ...],
        dict[str, str],
        int,
        int,
        datetime | None,
    ]:
        offsets = [message.offset for message in batch.messages]
        if any(current <= previous for previous, current in zip(offsets, offsets[1:])):
            raise PDDProductionObservationError(
                "PDD observation offsets are not strictly ordered"
            )
        keys = tuple(self._message_key(message) for message in batch.messages)
        existing = self.observation_ledger.lookup_fingerprints(
            self._stream_id,
            keys,
        )
        accepted: list[NormalizedMessage] = []
        new_fingerprints: dict[str, str] = {}
        duplicates = 0
        next_offset = checkpoint.offset
        last_message_at = checkpoint.last_message_at
        for raw in batch.messages:
            normalized = NormalizedMessage(
                channel="pdd",
                conversation_id=raw.conversation_id,
                external_message_id=raw.external_message_id,
                sender=raw.sender,
                content=raw.content,
                timestamp=raw.timestamp,
            )
            key = self._message_key(raw)
            fingerprint = self._fingerprint(normalized.model_dump(mode="json"))
            previous = existing.get(key, new_fingerprints.get(key))
            if previous is not None:
                if previous != fingerprint:
                    raise PDDProductionObservationError(
                        "PDD message identity was reused with different content"
                    )
                duplicates += 1
            elif raw.offset <= checkpoint.offset:
                raise PDDProductionObservationError(
                    "unrecognized message arrived behind committed offset"
                )
            else:
                accepted.append(normalized)
                new_fingerprints[key] = fingerprint
            next_offset = max(next_offset, raw.offset)
            last_message_at = raw.timestamp
            latency_ms = max(
                0,
                int(
                    (
                        _as_utc(batch.observed_at) - _as_utc(raw.timestamp)
                    ).total_seconds()
                    * 1000
                ),
            )
            self.last_message_latency_ms = latency_ms
            self.max_message_latency_ms = max(
                latency_ms,
                self.max_message_latency_ms or 0,
            )
        return (
            tuple(accepted),
            new_fingerprints,
            duplicates,
            next_offset,
            last_message_at,
        )

    @staticmethod
    def _message_key(message: PDDProductionObservedMessage) -> str:
        return json.dumps(
            [message.conversation_id, message.external_message_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _fingerprint(payload: Mapping[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


class PDDProductionExecutionAdapter:
    """Worker bridge that preserves Decision/Approval/Execution fencing."""

    def __init__(
        self,
        adapter: ProductionPDDAdapter,
        authorization_service: LedgerExecutionAuthorizationService,
    ) -> None:
        self.adapter = adapter
        self.authorization_service = authorization_service
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        raise ExecutionBoundaryDenied(
            "PDD production execution requires claimed execution context"
        )

    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        self.call_count += 1
        if (
            command.execution_id != context.execution_id
            or command.decision_id != context.decision_id
        ):
            return self._denied("PDD_PRODUCTION_EXECUTION_CONTEXT_MISMATCH")
        try:
            authorized = self.authorization_service.issue(
                execution_id=context.execution_id,
                worker_id=context.worker_id,
                execution_lease_token=context.lease_token,
            )
            if (
                authorized.authorization.approval_id != context.approval_id
                or authorized.authorization.approved_by != context.approved_by
                or authorized.message.content != command.proposed_content
                or authorized.message.idempotency_key != command.idempotency_key
            ):
                return self._denied(
                    "PDD_PRODUCTION_EXECUTION_CONTEXT_MISMATCH"
                )
            receipt = self.adapter.send_message(authorized)
        except ExecutionBoundaryDenied:
            return self._denied("PDD_PRODUCTION_SEND_AUTHORIZATION_DENIED")
        except ChannelSessionUnavailable:
            return self._denied("PDD_PRODUCTION_SESSION_UNAVAILABLE")
        return ExecutionResult(
            outcome=receipt.outcome,
            external_reference=receipt.external_message_id,
            error_code=receipt.error_code,
            details={
                "mode": "PDD_PRODUCTION_PREPARATION",
                "channel_receipt_id": receipt.receipt_id,
                "decision_id": authorized.authorization.decision_id,
                "approval_id": authorized.authorization.approval_id,
                "approved_by": authorized.authorization.approved_by,
                "authorization_id": authorized.authorization.authorization_id,
                "policy": receipt.details["policy"],
                "policy_reason": receipt.details["policy_reason"],
                "risk_level": receipt.details["risk_level"],
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "PDD_PRODUCTION_PREPARATION",
                "policy": PDDProductionPolicyDecision.DENY.value,
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
            },
        )


__all__ = [
    "FakePDDCredentialProvider",
    "FakePDDProductionObservationTransport",
    "InMemoryPDDObservationLedger",
    "PDDCredentialLease",
    "PDDCredentialProvider",
    "PDDCredentialRotationError",
    "PDDCredentialUnavailable",
    "PDDObservationCheckpoint",
    "PDDObservationLedger",
    "PDDObservationLedgerConflict",
    "PDDObservationSyncStatus",
    "PDDProductionAction",
    "PDDProductionExecutionAdapter",
    "PDDProductionHeartbeat",
    "PDDProductionObservationBatch",
    "PDDProductionObservationActivationGrant",
    "PDDProductionObservationError",
    "PDDProductionObservationTransport",
    "PDDProductionObservedMessage",
    "PDDProductionPolicyConfig",
    "PDDProductionPolicyDecision",
    "PDDProductionPolicyResult",
    "PDDProductionRiskLevel",
    "PDDProductionSafetyError",
    "PDDProductionSendPolicy",
    "PDDProductionSession",
    "PDDProductionSessionManager",
    "PDDProductionSessionState",
    "ProductionPDDAdapter",
]
