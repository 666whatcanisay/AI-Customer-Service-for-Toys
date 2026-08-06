from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Callable, Iterable
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.browser.models import BrowserLoginState, BrowserSessionState
from channel_engine.browser.selectors import (
    SelectorContract,
    SelectorContractState,
    draft_pdd_merchant_chat_v1,
)
from channel_engine.channel.pdd_discovery import PDDDiscoveryCapture
from channel_engine.models.entities import new_id, utc_now
from channel_engine.session.models import (
    ChannelInstance,
    ChannelInstanceStatus,
    CredentialReference,
)


PDD_OBSERVATION_MODE_VERSION = "1.0"


class PDDObservationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    observation_mode_version: Literal["1.0"] = PDD_OBSERVATION_MODE_VERSION


class PDDObservationSessionState(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    WAITING_USER = "WAITING_USER"
    CONNECTED = "CONNECTED"
    EXPIRED = "EXPIRED"


class PDDObservationAuditAction(StrEnum):
    SESSION_CHECKED = "SESSION_CHECKED"
    HUMAN_LOGIN_WAIT_STARTED = "HUMAN_LOGIN_WAIT_STARTED"
    STORE_DISCOVERED = "STORE_DISCOVERED"
    PAGE_OBSERVED = "PAGE_OBSERVED"


class PDDObservationError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDObservationSafetyViolation(PDDObservationError):
    pass


class PDDObservationBrowserSession(PDDObservationModel):
    browser_session_id: str = Field(min_length=1, max_length=128)
    browser_state: BrowserSessionState
    login_state: BrowserLoginState
    browser_generation: int = Field(ge=0)
    page_available: bool
    checked_at: AwareDatetime


class PDDObservedStoreIdentity(PDDObservationModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    store_name: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    source_reference: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^observation-ref://[A-Za-z0-9][A-Za-z0-9._:/-]{0,238}$",
    )
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def reject_placeholder(self) -> PDDObservedStoreIdentity:
        lowered = f"{self.store_id} {self.store_name}".casefold()
        if any(
            marker in lowered
            for marker in ("placeholder", "unknown", "must-be-verified", "todo")
        ):
            raise ValueError("store identity cannot be a placeholder")
        return self


class PDDMessageEntryProbe(PDDObservationModel):
    page_available: bool
    entry_present: bool
    candidate_count: int = Field(ge=0)
    selector_state: Literal[SelectorContractState.DRAFT] = SelectorContractState.DRAFT
    message_identity_captured: Literal[False] = False
    conversation_identity_captured: Literal[False] = False
    customer_content_captured: Literal[False] = False
    runtime_delivery_enabled: Literal[False] = False
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_presence(self) -> PDDMessageEntryProbe:
        if self.entry_present != (self.candidate_count > 0):
            raise ValueError("message entry presence and candidate count disagree")
        return self


class PDDObservationSafetySnapshot(PDDObservationModel):
    execution_created: Literal[0] = 0
    receipt_created: Literal[0] = 0
    send_operations: Literal[0] = 0
    browser_write_operations: Literal[0] = 0
    automatic_login_performed: Literal[False] = False
    credential_material_persisted: Literal[False] = False
    customer_content_captured: Literal[False] = False
    selector_activated: Literal[False] = False


class PDDObservationAuditEvent(PDDObservationModel):
    event_id: str = Field(min_length=1, max_length=128)
    action: PDDObservationAuditAction
    state: PDDObservationSessionState
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )
    store_identity_digest: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    occurred_at: AwareDatetime


class PDDObservationStatus(PDDObservationModel):
    state: PDDObservationSessionState
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )
    browser_session_id: str | None = Field(default=None, max_length=128)
    browser_state: BrowserSessionState | None = None
    login_state: BrowserLoginState | None = None
    browser_generation: int = Field(ge=0)
    page_available: bool
    store_discovered: bool
    message_entry_observed: bool
    selector_state: Literal[SelectorContractState.DRAFT] = SelectorContractState.DRAFT
    checked_at: AwareDatetime
    safety: PDDObservationSafetySnapshot


class PDDObservationEvidence(PDDObservationModel):
    channel_instance: ChannelInstance
    page_capture: PDDDiscoveryCapture
    message_entry: PDDMessageEntryProbe
    selector_contract: SelectorContract
    safety: PDDObservationSafetySnapshot
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def enforce_observation_only(self) -> PDDObservationEvidence:
        selector = self.selector_contract
        if (
            selector.state is not SelectorContractState.DRAFT
            or selector.bindings
            or selector.capabilities
            or selector.verified_at is not None
        ):
            raise ValueError("Observation Mode requires an inactive DRAFT selector")
        if self.page_capture.message_candidates:
            raise ValueError("Observation Mode cannot retain message candidate data")
        if self.page_capture.screenshot.captured:
            raise ValueError("Observation Mode retains DOM metadata, not screenshots")
        return self


@runtime_checkable
class PDDObservationPort(Protocol):
    """Read-only real-platform boundary. It intentionally exposes no actions."""

    @property
    def read_only(self) -> bool: ...

    @property
    def real_platform_source(self) -> bool: ...

    @property
    def automatic_login_performed(self) -> bool: ...

    @property
    def page_write_operations(self) -> int: ...

    @property
    def send_operations(self) -> int: ...

    @property
    def credential_material_persisted(self) -> bool: ...

    def session_snapshot(self) -> PDDObservationBrowserSession: ...

    def discover_store_identity(self) -> PDDObservedStoreIdentity: ...

    def capture_metadata(self) -> PDDDiscoveryCapture: ...

    def probe_message_entry(self) -> PDDMessageEntryProbe: ...


class PDDObservationModeRuntime:
    """Pre-integration observe mode: login, store, DOM and entry metadata only."""

    def __init__(
        self,
        port: PDDObservationPort,
        credential_reference: CredentialReference,
        *,
        allow_synthetic_test_port: bool = False,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(port, PDDObservationPort):
            raise TypeError("port does not implement PDDObservationPort")
        if not port.real_platform_source and not allow_synthetic_test_port:
            raise ValueError("Observation Mode requires a real read-only platform port")
        self._port = port
        self._credential_reference = credential_reference
        self._clock = clock
        self._state = PDDObservationSessionState.AUTH_REQUIRED
        self._reason_code = "PDD_OBSERVATION_AUTH_REQUIRED"
        self._session: PDDObservationBrowserSession | None = None
        self._store: PDDObservedStoreIdentity | None = None
        self._instance: ChannelInstance | None = None
        self._entry_observed = False
        self._events: list[PDDObservationAuditEvent] = []
        self._lock = RLock()
        self._assert_safe_port()

    def start(self) -> PDDObservationStatus:
        with self._lock:
            self._apply_session(self._port.session_snapshot(), preserve_wait=False)
            return self.status()

    def begin_human_login_wait(self) -> PDDObservationStatus:
        with self._lock:
            if self._state not in {
                PDDObservationSessionState.AUTH_REQUIRED,
                PDDObservationSessionState.WAITING_USER,
                PDDObservationSessionState.EXPIRED,
            }:
                raise PDDObservationError(
                    "human login wait is not available in the current state",
                    error_code="PDD_OBSERVATION_LOGIN_WAIT_INVALID_STATE",
                )
            self._state = PDDObservationSessionState.WAITING_USER
            self._reason_code = "PDD_OBSERVATION_WAITING_FOR_HUMAN_LOGIN"
            self._append_audit(PDDObservationAuditAction.HUMAN_LOGIN_WAIT_STARTED)
            self._assert_safe_port()
            return self.status()

    def check_session(self) -> PDDObservationStatus:
        with self._lock:
            self._apply_session(self._port.session_snapshot(), preserve_wait=True)
            return self.status()

    def discover_store(self) -> ChannelInstance:
        with self._lock:
            if self._state is not PDDObservationSessionState.CONNECTED:
                raise PDDObservationError(
                    "store discovery requires a human-authenticated session",
                    error_code="PDD_OBSERVATION_STORE_REQUIRES_LOGIN",
                )
            if self._instance is not None:
                return self._instance
            identity = self._port.discover_store_identity()
            now = self._clock()
            instance = ChannelInstance(
                instance_id=new_id("channel-instance"),
                platform="pdd",
                store_id=identity.store_id,
                status=ChannelInstanceStatus.CONNECTED,
                adapter_type="pdd-observation-mode.v1",
                active_session_id=None,
                created_at=now,
                updated_at=now,
            )
            self._store = identity
            self._instance = instance
            self._append_audit(
                PDDObservationAuditAction.STORE_DISCOVERED,
                store_identity_digest=hashlib.sha256(
                    identity.store_id.encode("utf-8")
                ).hexdigest(),
            )
            self._assert_safe_port()
            return instance

    def observe_page(self) -> PDDObservationEvidence:
        with self._lock:
            if (
                self._state is not PDDObservationSessionState.CONNECTED
                or self._instance is None
            ):
                raise PDDObservationError(
                    "page observation requires a discovered connected store",
                    error_code="PDD_OBSERVATION_STORE_NOT_DISCOVERED",
                )
            capture = self._port.capture_metadata()
            entry = self._port.probe_message_entry()
            self._validate_capture(capture, entry)
            selector = draft_pdd_merchant_chat_v1()
            evidence = PDDObservationEvidence(
                channel_instance=self._instance,
                page_capture=capture,
                message_entry=entry,
                selector_contract=selector,
                safety=self.safety_snapshot(),
                observed_at=self._clock(),
            )
            self._entry_observed = entry.entry_present
            self._append_audit(PDDObservationAuditAction.PAGE_OBSERVED)
            self._assert_safe_port()
            return evidence

    def status(self) -> PDDObservationStatus:
        with self._lock:
            session = self._session
            return PDDObservationStatus(
                state=self._state,
                reason_code=self._reason_code,
                browser_session_id=(session.browser_session_id if session else None),
                browser_state=(session.browser_state if session else None),
                login_state=(session.login_state if session else None),
                browser_generation=(session.browser_generation if session else 0),
                page_available=(session.page_available if session else False),
                store_discovered=self._instance is not None,
                message_entry_observed=self._entry_observed,
                checked_at=self._clock(),
                safety=self.safety_snapshot(),
            )

    def audit_events(self) -> tuple[PDDObservationAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def safety_snapshot(self) -> PDDObservationSafetySnapshot:
        self._assert_safe_port()
        return PDDObservationSafetySnapshot()

    def _apply_session(
        self,
        session: PDDObservationBrowserSession,
        *,
        preserve_wait: bool,
    ) -> None:
        self._session = session
        if session.login_state is BrowserLoginState.EXPIRED or (
            session.browser_state is BrowserSessionState.EXPIRED
        ):
            self._state = PDDObservationSessionState.EXPIRED
            self._reason_code = "PDD_OBSERVATION_SESSION_EXPIRED"
        elif (
            session.browser_state is BrowserSessionState.ACTIVE
            and session.login_state is BrowserLoginState.AUTHENTICATED
            and session.page_available
        ):
            self._state = PDDObservationSessionState.CONNECTED
            self._reason_code = "PDD_OBSERVATION_SESSION_CONNECTED"
        elif preserve_wait and self._state is PDDObservationSessionState.WAITING_USER:
            self._reason_code = "PDD_OBSERVATION_WAITING_FOR_HUMAN_LOGIN"
        else:
            self._state = PDDObservationSessionState.AUTH_REQUIRED
            self._reason_code = "PDD_OBSERVATION_AUTH_REQUIRED"
        self._append_audit(PDDObservationAuditAction.SESSION_CHECKED)
        self._assert_safe_port()

    def _validate_capture(
        self,
        capture: PDDDiscoveryCapture,
        entry: PDDMessageEntryProbe,
    ) -> None:
        if self._session is None:
            raise PDDObservationSafetyViolation(
                "browser session evidence is missing",
                error_code="PDD_OBSERVATION_SESSION_EVIDENCE_MISSING",
            )
        if (
            capture.session.browser_session_id
            != self._session.browser_session_id
            or capture.session.login_state is not BrowserLoginState.AUTHENTICATED
            or capture.session.browser_state is not BrowserSessionState.ACTIVE
            or not capture.session.page_available
            or not entry.page_available
        ):
            raise PDDObservationSafetyViolation(
                "page evidence is not bound to the active authenticated session",
                error_code="PDD_OBSERVATION_SESSION_EVIDENCE_MISMATCH",
            )
        if capture.message_candidates or capture.screenshot.captured:
            raise PDDObservationSafetyViolation(
                "page capture contains unnecessary customer or screenshot data",
                error_code="PDD_OBSERVATION_DATA_MINIMIZATION_FAILED",
            )

    def _assert_safe_port(self) -> None:
        if (
            not self._port.read_only
            or self._port.automatic_login_performed
            or self._port.page_write_operations != 0
            or self._port.send_operations != 0
            or self._port.credential_material_persisted
        ):
            raise PDDObservationSafetyViolation(
                "PDD observation port violated the read-only boundary",
                error_code="PDD_OBSERVATION_PORT_UNSAFE",
            )

    def _append_audit(
        self,
        action: PDDObservationAuditAction,
        *,
        store_identity_digest: str | None = None,
    ) -> None:
        self._events.append(
            PDDObservationAuditEvent(
                event_id=new_id("pdd-observation-audit"),
                action=action,
                state=self._state,
                reason_code=self._reason_code,
                store_identity_digest=store_identity_digest,
                occurred_at=self._clock(),
            )
        )


class FakePDDObservationPort:
    """Synthetic protocol double; no browser control, customer payload or send API."""

    read_only = True
    real_platform_source = False
    automatic_login_performed = False
    credential_material_persisted = False

    def __init__(
        self,
        sessions: Iterable[PDDObservationBrowserSession],
        store_identity: PDDObservedStoreIdentity,
        captures: Iterable[PDDDiscoveryCapture],
        message_entries: Iterable[PDDMessageEntryProbe],
        *,
        page_write_operations: int = 0,
        send_operations: int = 0,
    ) -> None:
        self._sessions = deque(sessions)
        self._store_identity = store_identity
        self._captures = deque(captures)
        self._message_entries = deque(message_entries)
        self.page_write_operations = page_write_operations
        self.send_operations = send_operations
        self.session_check_count = 0
        self.store_discovery_count = 0
        self.capture_count = 0
        self.message_entry_probe_count = 0

    def session_snapshot(self) -> PDDObservationBrowserSession:
        self.session_check_count += 1
        if not self._sessions:
            raise PDDObservationError(
                "synthetic session snapshot unavailable",
                error_code="PDD_OBSERVATION_SESSION_UNAVAILABLE",
            )
        return self._sessions.popleft()

    def discover_store_identity(self) -> PDDObservedStoreIdentity:
        self.store_discovery_count += 1
        return self._store_identity

    def capture_metadata(self) -> PDDDiscoveryCapture:
        self.capture_count += 1
        if not self._captures:
            raise PDDObservationError(
                "synthetic page capture unavailable",
                error_code="PDD_OBSERVATION_CAPTURE_UNAVAILABLE",
            )
        return self._captures.popleft()

    def probe_message_entry(self) -> PDDMessageEntryProbe:
        self.message_entry_probe_count += 1
        if not self._message_entries:
            raise PDDObservationError(
                "synthetic message entry probe unavailable",
                error_code="PDD_OBSERVATION_ENTRY_PROBE_UNAVAILABLE",
            )
        return self._message_entries.popleft()


__all__ = [
    "PDD_OBSERVATION_MODE_VERSION",
    "FakePDDObservationPort",
    "PDDMessageEntryProbe",
    "PDDObservationAuditAction",
    "PDDObservationAuditEvent",
    "PDDObservationBrowserSession",
    "PDDObservationError",
    "PDDObservationEvidence",
    "PDDObservationModeRuntime",
    "PDDObservationPort",
    "PDDObservationSafetySnapshot",
    "PDDObservationSafetyViolation",
    "PDDObservationSessionState",
    "PDDObservationStatus",
    "PDDObservedStoreIdentity",
]
