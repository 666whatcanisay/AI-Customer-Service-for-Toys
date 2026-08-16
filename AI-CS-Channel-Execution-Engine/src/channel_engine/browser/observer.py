from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from threading import RLock
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, Field, model_validator

from channel_engine.channel import NormalizedMessage
from channel_engine.models.entities import new_id, utc_now

from .models import (
    BrowserLoginState,
    BrowserModel,
    BrowserPageContext,
    BrowserSession,
    BrowserSessionState,
)
from .selectors import (
    LocatorEngine,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorRegistry,
)


BROWSER_OBSERVATION_CONTRACT_VERSION = "1.0"


class BrowserObservationMode(StrEnum):
    RECEIVE_ONLY = "RECEIVE_ONLY"


class BrowserObservationMechanism(StrEnum):
    UNDECIDED = "UNDECIDED"
    DOM_SNAPSHOT = "DOM_SNAPSHOT"
    PAGE_INTERNAL_API = "PAGE_INTERNAL_API"
    CDP_EVENT = "CDP_EVENT"
    MUTATION_OBSERVER = "MUTATION_OBSERVER"
    POLLING = "POLLING"
    MOCK_FEED = "MOCK_FEED"


class BrowserPageObserverState(StrEnum):
    DETACHED = "DETACHED"
    ATTACHED = "ATTACHED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class BrowserObservationSyncState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_SYNC = "IN_SYNC"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class RawBrowserMessage(BrowserModel):
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=8_000)
    timestamp: AwareDatetime
    observation_mechanism: BrowserObservationMechanism


class SequencedRawBrowserMessage(RawBrowserMessage):
    source_sequence: int = Field(ge=0)


class BrowserPageReadAttachment(BrowserModel):
    attachment_ref: str = Field(min_length=1, max_length=128)
    page_context_id: str = Field(min_length=1, max_length=128)
    page_generation: int = Field(ge=1)
    selector_contract_id: str = Field(min_length=1, max_length=256)
    selector_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    read_only: bool = True

    @model_validator(mode="after")
    def enforce_read_only(self) -> BrowserPageReadAttachment:
        if not self.read_only:
            raise ValueError("browser observation attachment must be read-only")
        return self


class BrowserPageCapture(BrowserModel):
    attachment_ref: str = Field(min_length=1, max_length=128)
    page_context_id: str = Field(min_length=1, max_length=128)
    page_generation: int = Field(ge=1)
    selector_contract_id: str = Field(min_length=1, max_length=256)
    selector_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    requested_cursor: str | None = Field(default=None, max_length=512)
    next_cursor: str | None = Field(default=None, max_length=512)
    oldest_available_sequence: int | None = Field(default=None, ge=0)
    messages: tuple[SequencedRawBrowserMessage, ...] = Field(max_length=200)
    page_revision: str | None = Field(default=None, max_length=128)
    captured_at: AwareDatetime
    has_more: bool = False

    @model_validator(mode="after")
    def validate_cursor_and_range(self) -> BrowserPageCapture:
        if (self.messages or self.has_more) and self.next_cursor is None:
            raise ValueError("non-empty or paged capture requires next_cursor")
        if self.messages and self.oldest_available_sequence is None:
            raise ValueError("message capture requires oldest available sequence")
        if (
            self.messages
            and self.oldest_available_sequence is not None
            and self.oldest_available_sequence > self.messages[0].source_sequence
        ):
            raise ValueError("oldest sequence cannot exceed the first captured message")
        return self


class BrowserObservedIdentity(BrowserModel):
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
    source_sequence: int = Field(ge=0)


class BrowserObservationCheckpoint(BrowserModel):
    stream_id: str = Field(min_length=1, max_length=255)
    revision: int = Field(ge=0)
    cursor: str | None = Field(default=None, max_length=512)
    last_sequence: int = Field(default=-1, ge=-1)
    selector_contract_id: str | None = Field(default=None, max_length=256)
    selector_fingerprint: str | None = Field(default=None, max_length=64)
    page_generation: int | None = Field(default=None, ge=1)
    accepted_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    last_capture_at: AwareDatetime | None = None
    sync_state: BrowserObservationSyncState = BrowserObservationSyncState.NOT_STARTED
    last_error_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_selector_binding(self) -> BrowserObservationCheckpoint:
        if (self.selector_contract_id is None) != (
            self.selector_fingerprint is None
        ):
            raise ValueError("selector id and fingerprint must be stored together")
        return self


class BrowserObservationBatch(BrowserModel):
    """Validated capture staged for durable persistence before cursor ACK.

    The batch deliberately carries normalized messages and identity fingerprints,
    but it does not mutate the browser checkpoint.  A caller must durably persist
    the messages first and only then call ``BrowserPageObserver.commit_batch``.
    """

    batch_id: str = Field(min_length=1, max_length=128)
    stream_id: str = Field(min_length=1, max_length=255)
    checkpoint: BrowserObservationCheckpoint
    attachment_ref: str = Field(min_length=1, max_length=128)
    page_context_id: str = Field(min_length=1, max_length=128)
    page_generation: int = Field(ge=1)
    selector_contract_id: str = Field(min_length=1, max_length=256)
    selector_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    next_cursor: str | None = Field(default=None, max_length=512)
    last_sequence: int = Field(ge=-1)
    messages: tuple[NormalizedMessage, ...] = Field(max_length=200)
    identities: tuple[BrowserObservedIdentity, ...] = Field(max_length=200)
    duplicate_count: int = Field(ge=0)
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def validate_message_identities(self) -> BrowserObservationBatch:
        if len(self.messages) != len(self.identities):
            raise ValueError("staged messages and identities must remain aligned")
        if self.stream_id != self.checkpoint.stream_id:
            raise ValueError("staged batch does not belong to its checkpoint")
        return self


class BrowserPageObserverHeartbeat(BrowserModel):
    stream_id: str = Field(min_length=1, max_length=255)
    observer_state: BrowserPageObserverState
    healthy: bool
    checked_at: AwareDatetime
    page_context_id: str | None = Field(default=None, max_length=128)
    page_generation: int | None = Field(default=None, ge=1)
    login_state: BrowserLoginState
    failure_code: str | None = Field(default=None, max_length=128)
    page_write_operations: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def enforce_observation_only(self) -> BrowserPageObserverHeartbeat:
        if self.page_write_operations != 0 and self.healthy:
            raise ValueError("a browser observer with page writes cannot be healthy")
        return self


@runtime_checkable
class BrowserPageObservationPort(Protocol):
    def observe(
        self,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
    ) -> tuple[RawBrowserMessage, ...]:
        """Return raw messages without exposing DOM selectors to domain code."""


@runtime_checkable
class BrowserMessageExtractor(Protocol):
    def normalize(self, raw: RawBrowserMessage) -> NormalizedMessage:
        """Map a page observation to the Channel Engine six-field message."""


class PDDMessageExtractor:
    def normalize(self, raw: RawBrowserMessage) -> NormalizedMessage:
        return NormalizedMessage(
            channel="pdd",
            conversation_id=raw.conversation_id,
            external_message_id=raw.external_message_id,
            sender=raw.sender,
            content=raw.content,
            timestamp=raw.timestamp,
        )


@runtime_checkable
class ReadOnlyBrowserPageCapturePort(Protocol):
    @property
    def read_only(self) -> bool:
        """Must remain true for the lifetime of the port."""

    @property
    def real_page_transport(self) -> bool:
        """Declare whether the port touches a real browser page."""

    @property
    def page_write_operations(self) -> int:
        """Must remain zero; any non-zero value is a safety failure."""

    def attach(
        self,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
    ) -> BrowserPageReadAttachment:
        """Attach a read-only capture context to one page generation."""

    def capture(
        self,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
        *,
        cursor: str | None,
        after_sequence: int,
        limit: int,
    ) -> BrowserPageCapture:
        """Read one selector-driven page snapshot without page mutation."""

    def heartbeat(self, attachment: BrowserPageReadAttachment) -> bool:
        """Check whether the read attachment remains available."""

    def detach(self, attachment: BrowserPageReadAttachment) -> None:
        """Release local observation resources without touching page state."""


@runtime_checkable
class BrowserObservationStore(Protocol):
    def load(self, stream_id: str) -> BrowserObservationCheckpoint:
        """Load a committed observation cursor."""

    def lookup_identities(
        self,
        stream_id: str,
        identity_digests: tuple[str, ...],
    ) -> Mapping[str, BrowserObservedIdentity]:
        """Load immutable identity fingerprints for deduplication."""

    def commit_capture(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        cursor: str | None,
        last_sequence: int,
        selector_contract_id: str,
        selector_fingerprint: str,
        page_generation: int,
        identities: Sequence[BrowserObservedIdentity],
        accepted_increment: int,
        duplicate_increment: int,
        captured_at: AwareDatetime,
    ) -> BrowserObservationCheckpoint:
        """CAS-commit cursor and fingerprints as one durable operation."""

    def record_failure(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        error_code: str,
        failed_at: AwareDatetime,
        terminal: bool,
    ) -> BrowserObservationCheckpoint:
        """Record a sanitized failure without advancing the cursor."""


class BrowserObservationUnavailable(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BROWSER_OBSERVATION_UNAVAILABLE",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class BrowserObservationConflict(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BROWSER_OBSERVATION_CONFLICT",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class BrowserObservationMissedMessages(BrowserObservationConflict):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="BROWSER_OBSERVATION_MESSAGE_GAP",
        )


class BrowserObservationSelectorMismatch(BrowserObservationConflict):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="BROWSER_OBSERVATION_SELECTOR_MISMATCH",
        )


class InMemoryBrowserObservationStore:
    """Thread-safe reference store; production-shaped persistence is separate."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, BrowserObservationCheckpoint] = {}
        self._identities: dict[str, dict[str, BrowserObservedIdentity]] = {}
        self._lock = RLock()

    @staticmethod
    def _initial(stream_id: str) -> BrowserObservationCheckpoint:
        return BrowserObservationCheckpoint(stream_id=stream_id, revision=0)

    def load(self, stream_id: str) -> BrowserObservationCheckpoint:
        with self._lock:
            return self._checkpoints.get(stream_id, self._initial(stream_id))

    def lookup_identities(
        self,
        stream_id: str,
        identity_digests: tuple[str, ...],
    ) -> Mapping[str, BrowserObservedIdentity]:
        with self._lock:
            records = self._identities.get(stream_id, {})
            return {
                digest: records[digest]
                for digest in identity_digests
                if digest in records
            }

    def commit_capture(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        cursor: str | None,
        last_sequence: int,
        selector_contract_id: str,
        selector_fingerprint: str,
        page_generation: int,
        identities: Sequence[BrowserObservedIdentity],
        accepted_increment: int,
        duplicate_increment: int,
        captured_at: AwareDatetime,
    ) -> BrowserObservationCheckpoint:
        if last_sequence < checkpoint.last_sequence:
            raise BrowserObservationConflict("observation sequence moved backward")
        with self._lock:
            current = self._checkpoints.get(
                checkpoint.stream_id,
                self._initial(checkpoint.stream_id),
            )
            self._assert_revision(current, checkpoint)
            records = self._identities.setdefault(checkpoint.stream_id, {})
            for identity in identities:
                existing = records.get(identity.identity_digest)
                if existing is not None and existing != identity:
                    raise BrowserObservationConflict(
                        "message identity is already bound to different evidence"
                    )
            records.update(
                {identity.identity_digest: identity for identity in identities}
            )
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "cursor": cursor,
                    "last_sequence": last_sequence,
                    "selector_contract_id": selector_contract_id,
                    "selector_fingerprint": selector_fingerprint,
                    "page_generation": page_generation,
                    "accepted_count": current.accepted_count + accepted_increment,
                    "duplicate_count": current.duplicate_count
                    + duplicate_increment,
                    "last_capture_at": captured_at,
                    "sync_state": BrowserObservationSyncState.IN_SYNC,
                    "last_error_code": None,
                }
            )
            self._checkpoints[checkpoint.stream_id] = updated
            return updated

    def record_failure(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        error_code: str,
        failed_at: AwareDatetime,
        terminal: bool,
    ) -> BrowserObservationCheckpoint:
        with self._lock:
            current = self._checkpoints.get(
                checkpoint.stream_id,
                self._initial(checkpoint.stream_id),
            )
            self._assert_revision(current, checkpoint)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "last_capture_at": failed_at,
                    "sync_state": (
                        BrowserObservationSyncState.FAILED
                        if terminal
                        else BrowserObservationSyncState.DEGRADED
                    ),
                    "last_error_code": error_code,
                }
            )
            self._checkpoints[checkpoint.stream_id] = updated
            return updated

    @staticmethod
    def _assert_revision(
        current: BrowserObservationCheckpoint,
        proposed: BrowserObservationCheckpoint,
    ) -> None:
        if current.revision != proposed.revision:
            raise BrowserObservationConflict(
                "browser observation checkpoint revision changed concurrently"
            )


class FakeReadOnlyBrowserPageCapturePort:
    """Deterministic capture port; it cannot perform a page write or real access."""

    read_only = True
    real_page_transport = False

    def __init__(self) -> None:
        self._captures: deque[BrowserPageCapture] = deque()
        self._attachments: set[str] = set()
        self.healthy = True
        self.attach_count = 0
        self.capture_count = 0
        self.heartbeat_count = 0
        self.detach_count = 0
        self.page_write_operations = 0
        self.capture_history: list[tuple[str | None, int, int]] = []

    def enqueue(self, capture: BrowserPageCapture) -> None:
        self._captures.append(capture)

    def attach(
        self,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
    ) -> BrowserPageReadAttachment:
        self.attach_count += 1
        attachment = BrowserPageReadAttachment(
            attachment_ref=new_id("fake-page-read"),
            page_context_id=page.page_context_id,
            page_generation=page.generation,
            selector_contract_id=selector_contract.contract_id,
            selector_fingerprint=selector_contract.fingerprint(),
            read_only=True,
        )
        self._attachments.add(attachment.attachment_ref)
        return attachment

    def capture(
        self,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
        *,
        cursor: str | None,
        after_sequence: int,
        limit: int,
    ) -> BrowserPageCapture:
        self.capture_count += 1
        self.capture_history.append((cursor, after_sequence, limit))
        if attachment.attachment_ref not in self._attachments or not self.healthy:
            raise BrowserObservationUnavailable(
                "fake read attachment is unavailable",
                error_code="BROWSER_PAGE_ATTACHMENT_UNAVAILABLE",
            )
        if not self._captures:
            return BrowserPageCapture(
                attachment_ref=attachment.attachment_ref,
                page_context_id=page.page_context_id,
                page_generation=page.generation,
                selector_contract_id=selector_contract.contract_id,
                selector_fingerprint=selector_contract.fingerprint(),
                requested_cursor=cursor,
                next_cursor=cursor,
                oldest_available_sequence=None,
                messages=(),
                page_revision=page.page_revision,
                captured_at=utc_now(),
            )
        queued = self._captures.popleft()
        if len(queued.messages) > limit:
            raise BrowserObservationUnavailable(
                "capture exceeded the requested batch limit",
                error_code="BROWSER_OBSERVATION_BATCH_LIMIT_EXCEEDED",
            )
        return queued.model_copy(
            update={
                "attachment_ref": attachment.attachment_ref,
                "page_context_id": page.page_context_id,
                "page_generation": page.generation,
                "selector_contract_id": selector_contract.contract_id,
                "selector_fingerprint": selector_contract.fingerprint(),
                "requested_cursor": cursor,
                "page_revision": page.page_revision,
            }
        )

    def heartbeat(self, attachment: BrowserPageReadAttachment) -> bool:
        self.heartbeat_count += 1
        return self.healthy and attachment.attachment_ref in self._attachments

    def detach(self, attachment: BrowserPageReadAttachment) -> None:
        self.detach_count += 1
        self._attachments.discard(attachment.attachment_ref)


class BrowserPageObserver:
    """Selector-governed, receive-only browser page observation coordinator."""

    mode = BrowserObservationMode.RECEIVE_ONLY

    def __init__(
        self,
        session_provider: Callable[[], BrowserSession],
        page_port: ReadOnlyBrowserPageCapturePort,
        extractor: BrowserMessageExtractor,
        selector_registry: SelectorRegistry,
        store: BrowserObservationStore,
        *,
        stream_id: str,
        batch_limit: int = 100,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(page_port, ReadOnlyBrowserPageCapturePort):
            raise TypeError("page port does not implement the read-only contract")
        if not isinstance(store, BrowserObservationStore):
            raise TypeError("observation store does not implement the contract")
        if not page_port.read_only or page_port.page_write_operations != 0:
            raise ValueError("browser page observation port must be read-only")
        if not stream_id.strip() or len(stream_id) > 255:
            raise ValueError("observation stream id is invalid")
        if not 1 <= batch_limit <= 200:
            raise ValueError("browser observation batch limit must be 1..200")
        self._session_provider = session_provider
        self._page_port = page_port
        self._extractor = extractor
        self._selector_registry = selector_registry
        self._store = store
        self._stream_id = stream_id
        self._batch_limit = batch_limit
        self._clock = clock
        self._attachment: BrowserPageReadAttachment | None = None
        self._state = BrowserPageObserverState.DETACHED
        self._lock = RLock()

    @property
    def state(self) -> BrowserPageObserverState:
        with self._lock:
            return self._state

    def checkpoint(self) -> BrowserObservationCheckpoint:
        return self._store.load(self._stream_id)

    def attach(self) -> BrowserPageReadAttachment:
        with self._lock:
            _session, page, contract = self._require_active_page()
            checkpoint = self._store.load(self._stream_id)
            self._assert_checkpoint_selector(checkpoint, contract)
            if self._attachment is not None:
                if (
                    self._attachment.page_context_id == page.page_context_id
                    and self._attachment.page_generation == page.generation
                    and self._attachment.selector_fingerprint
                    == contract.fingerprint()
                ):
                    self._state = BrowserPageObserverState.ATTACHED
                    return self._attachment
                self._page_port.detach(self._attachment)
            attachment = self._page_port.attach(page, contract)
            self._assert_attachment(attachment, page, contract)
            self._assert_no_page_writes()
            self._attachment = attachment
            self._state = BrowserPageObserverState.ATTACHED
            return attachment

    def detach(self) -> None:
        with self._lock:
            if self._attachment is not None:
                try:
                    self._page_port.detach(self._attachment)
                finally:
                    self._attachment = None
            self._assert_no_page_writes()
            self._state = BrowserPageObserverState.DETACHED

    def heartbeat(self) -> BrowserPageObserverHeartbeat:
        with self._lock:
            now = self._clock()
            session = self._session_provider()
            attachment = self._attachment
            if attachment is None:
                return self._heartbeat_result(
                    now,
                    session,
                    healthy=False,
                    failure_code="BROWSER_OBSERVER_DETACHED",
                    state=BrowserPageObserverState.DETACHED,
                )
            if session.login_state in {
                BrowserLoginState.REQUIRED,
                BrowserLoginState.EXPIRED,
            }:
                self._state = BrowserPageObserverState.DEGRADED
                return self._heartbeat_result(
                    now,
                    session,
                    healthy=False,
                    failure_code="BROWSER_LOGIN_EXPIRED",
                    state=self._state,
                )
            if session.state is not BrowserSessionState.ACTIVE:
                self._state = BrowserPageObserverState.DEGRADED
                return self._heartbeat_result(
                    now,
                    session,
                    healthy=False,
                    failure_code="BROWSER_SESSION_NOT_ACTIVE",
                    state=self._state,
                )
            if (
                session.page_context is None
                or session.page_context.page_context_id
                != attachment.page_context_id
                or session.page_context.generation != attachment.page_generation
            ):
                self._state = BrowserPageObserverState.DEGRADED
                return self._heartbeat_result(
                    now,
                    session,
                    healthy=False,
                    failure_code="BROWSER_PAGE_CONTEXT_CHANGED",
                    state=self._state,
                )
            try:
                contract = self._contract_for(session.page_context)
                self._assert_selector_contract(contract)
                self._assert_checkpoint_selector(
                    self._store.load(self._stream_id), contract
                )
                healthy = self._page_port.heartbeat(attachment)
                self._assert_no_page_writes()
            except Exception:
                healthy = False
            self._state = (
                BrowserPageObserverState.ATTACHED
                if healthy
                else BrowserPageObserverState.DEGRADED
            )
            return self._heartbeat_result(
                now,
                session,
                healthy=healthy,
                failure_code=None if healthy else "BROWSER_PAGE_OBSERVER_UNHEALTHY",
                state=self._state,
            )

    def stage_capture(self) -> BrowserObservationBatch:
        """Capture and validate without advancing the durable browser cursor."""

        with self._lock:
            checkpoint = self._store.load(self._stream_id)
            try:
                _session, page, contract = self._require_active_page()
                attachment = self._require_attachment(page, contract)
                capture = self._page_port.capture(
                    attachment,
                    page,
                    contract,
                    cursor=checkpoint.cursor,
                    after_sequence=checkpoint.last_sequence,
                    limit=self._batch_limit,
                )
                self._assert_no_page_writes()
                normalized, identities, duplicates, last_sequence = (
                    self._validate_capture(
                        checkpoint,
                        attachment,
                        page,
                        contract,
                        capture,
                    )
                )
                self._state = BrowserPageObserverState.ATTACHED
                return BrowserObservationBatch(
                    batch_id=new_id("browser-observation-batch"),
                    stream_id=self._stream_id,
                    checkpoint=checkpoint,
                    attachment_ref=attachment.attachment_ref,
                    page_context_id=page.page_context_id,
                    page_generation=page.generation,
                    selector_contract_id=contract.contract_id,
                    selector_fingerprint=contract.fingerprint(),
                    next_cursor=capture.next_cursor,
                    last_sequence=last_sequence,
                    messages=normalized,
                    identities=identities,
                    duplicate_count=duplicates,
                    captured_at=capture.captured_at,
                )
            except BrowserObservationConflict as exc:
                self._record_failure(checkpoint, exc.error_code, terminal=True)
                self._state = BrowserPageObserverState.FAILED
                raise
            except BrowserObservationUnavailable as exc:
                self._record_failure(checkpoint, exc.error_code, terminal=False)
                self._state = BrowserPageObserverState.DEGRADED
                raise
            except Exception as exc:
                self._record_failure(
                    checkpoint,
                    "BROWSER_OBSERVATION_CAPTURE_FAILED",
                    terminal=False,
                )
                self._state = BrowserPageObserverState.DEGRADED
                raise BrowserObservationUnavailable(
                    "browser page capture failed",
                    error_code="BROWSER_OBSERVATION_CAPTURE_FAILED",
                ) from exc

    def commit_batch(
        self, batch: BrowserObservationBatch
    ) -> BrowserObservationCheckpoint:
        """ACK one staged capture after the caller's message transaction commits."""

        with self._lock:
            if batch.stream_id != self._stream_id:
                raise BrowserObservationConflict(
                    "staged batch belongs to another observation stream",
                    error_code="BROWSER_OBSERVATION_BATCH_STREAM_MISMATCH",
                )
            current = self._store.load(self._stream_id)
            if (
                current.revision == batch.checkpoint.revision + 1
                and current.cursor == batch.next_cursor
                and current.last_sequence == batch.last_sequence
                and current.selector_contract_id == batch.selector_contract_id
                and current.selector_fingerprint == batch.selector_fingerprint
                and current.page_generation == batch.page_generation
            ):
                return current
            if current != batch.checkpoint:
                raise BrowserObservationConflict(
                    "staged batch checkpoint is stale",
                    error_code="BROWSER_OBSERVATION_BATCH_STALE",
                )
            try:
                _session, page, contract = self._require_active_page()
                attachment = self._require_attachment(page, contract)
                if (
                    attachment.attachment_ref != batch.attachment_ref
                    or page.page_context_id != batch.page_context_id
                    or page.generation != batch.page_generation
                    or contract.contract_id != batch.selector_contract_id
                    or contract.fingerprint() != batch.selector_fingerprint
                ):
                    raise BrowserObservationConflict(
                        "staged batch is not bound to the active page",
                        error_code="BROWSER_OBSERVATION_BATCH_CONTEXT_MISMATCH",
                    )
                committed = self._store.commit_capture(
                    current,
                    cursor=batch.next_cursor,
                    last_sequence=batch.last_sequence,
                    selector_contract_id=batch.selector_contract_id,
                    selector_fingerprint=batch.selector_fingerprint,
                    page_generation=batch.page_generation,
                    identities=batch.identities,
                    accepted_increment=len(batch.messages),
                    duplicate_increment=batch.duplicate_count,
                    captured_at=batch.captured_at,
                )
                self._state = BrowserPageObserverState.ATTACHED
                return committed
            except BrowserObservationConflict:
                self._state = BrowserPageObserverState.FAILED
                raise
            except BrowserObservationUnavailable:
                self._state = BrowserPageObserverState.DEGRADED
                raise
            except Exception as exc:
                self._state = BrowserPageObserverState.DEGRADED
                raise BrowserObservationUnavailable(
                    "browser cursor ACK failed",
                    error_code="BROWSER_OBSERVATION_CURSOR_ACK_FAILED",
                ) from exc

    def capture(self) -> tuple[NormalizedMessage, ...]:
        """Compatibility API: stage and immediately commit one capture.

        Reliability-sensitive callers must use ``stage_capture`` followed by
        durable message persistence and ``commit_batch``.
        """

        batch = self.stage_capture()
        self.commit_batch(batch)
        return batch.messages

    def _validate_capture(
        self,
        checkpoint: BrowserObservationCheckpoint,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        contract: SelectorContract,
        capture: BrowserPageCapture,
    ) -> tuple[
        tuple[NormalizedMessage, ...],
        tuple[BrowserObservedIdentity, ...],
        int,
        int,
    ]:
        expected = (
            attachment.attachment_ref,
            page.page_context_id,
            page.generation,
            contract.contract_id,
            contract.fingerprint(),
        )
        actual = (
            capture.attachment_ref,
            capture.page_context_id,
            capture.page_generation,
            capture.selector_contract_id,
            capture.selector_fingerprint,
        )
        if actual != expected:
            raise BrowserObservationConflict(
                "page capture identity does not match its attachment",
                error_code="BROWSER_OBSERVATION_ATTACHMENT_MISMATCH",
            )
        if capture.requested_cursor != checkpoint.cursor:
            raise BrowserObservationConflict(
                "page capture was produced from a stale cursor",
                error_code="BROWSER_OBSERVATION_STALE_CURSOR",
            )
        if page.page_revision is not None and capture.page_revision != page.page_revision:
            raise BrowserObservationConflict(
                "page revision changed during capture",
                error_code="BROWSER_OBSERVATION_PAGE_REVISION_CHANGED",
            )
        sequences = [message.source_sequence for message in capture.messages]
        if any(
            current <= previous
            for previous, current in zip(sequences, sequences[1:])
        ):
            raise BrowserObservationConflict(
                "captured message sequences are not strictly ordered",
                error_code="BROWSER_OBSERVATION_SEQUENCE_ORDER_INVALID",
            )
        if (
            checkpoint.last_sequence >= 0
            and capture.oldest_available_sequence is not None
            and capture.oldest_available_sequence > checkpoint.last_sequence + 1
        ):
            raise BrowserObservationMissedMessages(
                "page history was truncated beyond the committed cursor"
            )

        digests = tuple(self._identity_digest(message) for message in capture.messages)
        existing = self._store.lookup_identities(self._stream_id, digests)
        batch_seen: dict[str, BrowserObservedIdentity] = {}
        accepted: list[NormalizedMessage] = []
        new_identities: list[BrowserObservedIdentity] = []
        duplicates = 0
        for raw, digest in zip(capture.messages, digests):
            if raw.observation_mechanism is BrowserObservationMechanism.UNDECIDED:
                raise BrowserObservationConflict(
                    "captured message has no verified observation mechanism",
                    error_code="BROWSER_OBSERVATION_MECHANISM_UNDECIDED",
                )
            if (
                self._page_port.real_page_transport
                and raw.observation_mechanism is BrowserObservationMechanism.MOCK_FEED
            ):
                raise BrowserObservationConflict(
                    "a real page capture cannot claim the mock observation mechanism",
                    error_code="BROWSER_OBSERVATION_MECHANISM_MISMATCH",
                )
            try:
                normalized = self._extractor.normalize(raw)
            except Exception as exc:
                raise BrowserObservationConflict(
                    "captured message cannot be normalized",
                    error_code="BROWSER_OBSERVATION_MESSAGE_INVALID",
                ) from exc
            identity = BrowserObservedIdentity(
                identity_digest=digest,
                payload_fingerprint=self._payload_fingerprint(normalized),
                source_sequence=raw.source_sequence,
            )
            previous = existing.get(digest, batch_seen.get(digest))
            if previous is not None:
                if previous != identity:
                    raise BrowserObservationConflict(
                        "external browser message id changed payload or sequence",
                        error_code="BROWSER_OBSERVATION_IDENTITY_REUSED",
                    )
                duplicates += 1
                continue
            if raw.source_sequence <= checkpoint.last_sequence:
                raise BrowserObservationMissedMessages(
                    "unknown message appeared behind the committed sequence"
                )
            batch_seen[digest] = identity
            new_identities.append(identity)
            accepted.append(normalized)

        new_sequences = [item.source_sequence for item in new_identities]
        if new_sequences:
            expected_first = (
                checkpoint.last_sequence + 1
                if checkpoint.last_sequence >= 0
                else new_sequences[0]
            )
            if new_sequences != list(
                range(expected_first, expected_first + len(new_sequences))
            ):
                raise BrowserObservationMissedMessages(
                    "captured message sequence contains a gap"
                )
            if capture.next_cursor == checkpoint.cursor:
                raise BrowserObservationConflict(
                    "capture accepted messages without advancing its cursor",
                    error_code="BROWSER_OBSERVATION_CURSOR_NOT_ADVANCED",
                )
        last_sequence = (
            max(checkpoint.last_sequence, *new_sequences)
            if new_sequences
            else checkpoint.last_sequence
        )
        return (
            tuple(accepted),
            tuple(new_identities),
            duplicates,
            last_sequence,
        )

    def _require_active_page(
        self,
    ) -> tuple[BrowserSession, BrowserPageContext, SelectorContract]:
        session = self._session_provider()
        if session.login_state in {
            BrowserLoginState.REQUIRED,
            BrowserLoginState.EXPIRED,
        }:
            raise BrowserObservationUnavailable(
                "browser login is required",
                error_code="BROWSER_LOGIN_EXPIRED",
            )
        if session.state is not BrowserSessionState.ACTIVE or session.page_context is None:
            raise BrowserObservationUnavailable(
                "browser session is not ACTIVE",
                error_code="BROWSER_SESSION_NOT_ACTIVE",
            )
        contract = self._contract_for(session.page_context)
        self._assert_selector_contract(contract)
        return session, session.page_context, contract

    def _contract_for(self, page: BrowserPageContext) -> SelectorContract:
        return self._selector_registry.get(
            page.platform,
            page.page,
            page.selector_contract_version,
        )

    def _assert_selector_contract(self, contract: SelectorContract) -> None:
        if contract.state is not SelectorContractState.VERIFIED:
            raise BrowserObservationSelectorMismatch(
                "selector contract is not verified"
            )
        if SelectorCapability.RECEIVE_MESSAGE not in contract.capabilities:
            raise BrowserObservationSelectorMismatch(
                "selector contract lacks receive-message capability"
            )
        if self._page_port.real_page_transport and any(
            binding.engine is LocatorEngine.MOCK for binding in contract.bindings
        ):
            raise BrowserObservationSelectorMismatch(
                "mock selector bindings cannot be used on a real page"
            )
        if (
            self._page_port.real_page_transport
            and SelectorCapability.SEND_MESSAGE in contract.capabilities
        ):
            raise BrowserObservationSelectorMismatch(
                "real receive-only observation rejects send capability"
            )

    @staticmethod
    def _assert_checkpoint_selector(
        checkpoint: BrowserObservationCheckpoint,
        contract: SelectorContract,
    ) -> None:
        if checkpoint.selector_contract_id is None:
            return
        if (
            checkpoint.selector_contract_id != contract.contract_id
            or checkpoint.selector_fingerprint != contract.fingerprint()
        ):
            raise BrowserObservationSelectorMismatch(
                "committed cursor belongs to a different selector contract"
            )

    @staticmethod
    def _assert_attachment(
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        contract: SelectorContract,
    ) -> None:
        if (
            not attachment.read_only
            or attachment.page_context_id != page.page_context_id
            or attachment.page_generation != page.generation
            or attachment.selector_contract_id != contract.contract_id
            or attachment.selector_fingerprint != contract.fingerprint()
        ):
            raise BrowserObservationConflict(
                "read attachment does not match page and selector context",
                error_code="BROWSER_OBSERVATION_ATTACHMENT_MISMATCH",
            )

    def _require_attachment(
        self,
        page: BrowserPageContext,
        contract: SelectorContract,
    ) -> BrowserPageReadAttachment:
        attachment = self._attachment
        if attachment is None:
            raise BrowserObservationUnavailable(
                "browser page observer is detached",
                error_code="BROWSER_OBSERVER_DETACHED",
            )
        self._assert_attachment(attachment, page, contract)
        return attachment

    def _assert_no_page_writes(self) -> None:
        if not self._page_port.read_only or self._page_port.page_write_operations != 0:
            raise BrowserObservationConflict(
                "browser page observation port performed a write",
                error_code="BROWSER_OBSERVATION_WRITE_DETECTED",
            )

    def _record_failure(
        self,
        checkpoint: BrowserObservationCheckpoint,
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
        except BrowserObservationConflict:
            pass

    def _heartbeat_result(
        self,
        checked_at: AwareDatetime,
        session: BrowserSession,
        *,
        healthy: bool,
        failure_code: str | None,
        state: BrowserPageObserverState,
    ) -> BrowserPageObserverHeartbeat:
        page = session.page_context
        writes = self._page_port.page_write_operations
        if writes != 0:
            healthy = False
            failure_code = "BROWSER_OBSERVATION_WRITE_DETECTED"
            state = BrowserPageObserverState.FAILED
            self._state = state
        return BrowserPageObserverHeartbeat(
            stream_id=self._stream_id,
            observer_state=state,
            healthy=healthy,
            checked_at=checked_at,
            page_context_id=page.page_context_id if page is not None else None,
            page_generation=page.generation if page is not None else None,
            login_state=session.login_state,
            failure_code=failure_code,
            page_write_operations=writes,
        )

    @staticmethod
    def _identity_digest(message: SequencedRawBrowserMessage) -> str:
        return hashlib.sha256(
            f"{message.conversation_id}\0{message.external_message_id}".encode()
        ).hexdigest()

    @staticmethod
    def _payload_fingerprint(message: NormalizedMessage) -> str:
        payload = json.dumps(
            message.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class ReceiveOnlyPageObserver:
    mode = BrowserObservationMode.RECEIVE_ONLY

    def __init__(
        self,
        session_provider,
        page_port: BrowserPageObservationPort,
        extractor: BrowserMessageExtractor,
        selector_registry: SelectorRegistry,
        *,
        dedupe_window: int = 10_000,
    ) -> None:
        if dedupe_window < 1:
            raise ValueError("dedupe window must be positive")
        self._session_provider = session_provider
        self._page_port = page_port
        self._extractor = extractor
        self._selector_registry = selector_registry
        self._pending: deque[RawBrowserMessage] = deque()
        self._seen_payloads: dict[tuple[str, str], tuple[str, str, object]] = {}
        self._seen_order: deque[tuple[str, str]] = deque()
        self._dedupe_window = dedupe_window

    def receive_message(self) -> NormalizedMessage | None:
        if not self._pending:
            self._observe()
        while self._pending:
            raw = self._pending.popleft()
            key = (raw.conversation_id, raw.external_message_id)
            payload = (raw.sender, raw.content, raw.timestamp)
            existing = self._seen_payloads.get(key)
            if existing is not None:
                if existing != payload:
                    raise BrowserObservationConflict(
                        "external browser message id changed payload"
                    )
                continue
            self._remember(key, payload)
            return self._extractor.normalize(raw)
        return None

    def _observe(self) -> None:
        session: BrowserSession = self._session_provider()
        if (
            session.state is not BrowserSessionState.ACTIVE
            or session.page_context is None
        ):
            raise BrowserObservationUnavailable("browser session is not ACTIVE")
        page = session.page_context
        contract = self._selector_registry.get(
            page.platform, page.page, page.selector_contract_version
        )
        if contract.state is not SelectorContractState.VERIFIED:
            raise BrowserObservationUnavailable("selector contract is not verified")
        observations = self._page_port.observe(page, contract)
        self._pending.extend(
            sorted(
                observations,
                key=lambda item: (
                    item.timestamp,
                    item.conversation_id,
                    item.external_message_id,
                ),
            )
        )

    def _remember(
        self,
        key: tuple[str, str],
        payload: tuple[str, str, object],
    ) -> None:
        self._seen_payloads[key] = payload
        self._seen_order.append(key)
        while len(self._seen_order) > self._dedupe_window:
            expired = self._seen_order.popleft()
            self._seen_payloads.pop(expired, None)


class FakeBrowserPageObservationPort:
    """Offline deterministic page feed; no DOM, CDP or browser is touched."""

    def __init__(self) -> None:
        self._batches: deque[tuple[RawBrowserMessage, ...]] = deque()
        self.observe_count = 0
        self.real_page_accessed = False

    def enqueue(self, *messages: RawBrowserMessage) -> None:
        self._batches.append(tuple(messages))

    def observe(
        self,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
    ) -> tuple[RawBrowserMessage, ...]:
        del page, selector_contract
        self.observe_count += 1
        return self._batches.popleft() if self._batches else ()


__all__ = [
    "BROWSER_OBSERVATION_CONTRACT_VERSION",
    "BrowserMessageExtractor",
    "BrowserObservationCheckpoint",
    "BrowserObservationConflict",
    "BrowserObservationMechanism",
    "BrowserObservationMissedMessages",
    "BrowserObservationMode",
    "BrowserObservationSelectorMismatch",
    "BrowserObservationStore",
    "BrowserObservationSyncState",
    "BrowserObservationUnavailable",
    "BrowserObservedIdentity",
    "BrowserPageCapture",
    "BrowserPageObservationPort",
    "BrowserPageObserver",
    "BrowserPageObserverHeartbeat",
    "BrowserPageObserverState",
    "BrowserPageReadAttachment",
    "FakeBrowserPageObservationPort",
    "FakeReadOnlyBrowserPageCapturePort",
    "InMemoryBrowserObservationStore",
    "PDDMessageExtractor",
    "RawBrowserMessage",
    "ReadOnlyBrowserPageCapturePort",
    "ReceiveOnlyPageObserver",
    "SequencedRawBrowserMessage",
]
