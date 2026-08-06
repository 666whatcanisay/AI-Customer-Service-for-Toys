from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import Lock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, Field, model_validator

from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now

from .execution_boundary import LedgerExecutionAuthorizationService
from .platform import AuthorizedOutboundMessage, ExecutionBoundaryDenied
from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelModel,
    ChannelSendReceipt,
)


PDD_SEND_TRANSPORT_VERSION = "1.0"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PDDSendSafetyError(ExecutionBoundaryDenied):
    """Fail-closed error raised before the HTTP sender can be invoked."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDSendIdempotencyConflict(PDDSendSafetyError):
    pass


class PDDSendSessionUnavailable(PDDSendSafetyError):
    pass


class PDDApprovedExecutionContext(ChannelModel):
    """Worker-issued lease context; deliberately contains no message text."""

    execution_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    approved_by: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=160)
    lease_token: str = Field(min_length=1, max_length=128, repr=False)
    lease_expires_at: AwareDatetime

    @classmethod
    def from_claimed(
        cls,
        context: ClaimedExecutionContext,
    ) -> PDDApprovedExecutionContext:
        return cls(**context.model_dump())


class PDDSendSessionState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"


class PDDSendSession(ChannelModel):
    """Sanitized session metadata. References are opaque; secret values are absent."""

    session_id: str = Field(min_length=1, max_length=128)
    session_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^session-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    cookie_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    state: PDDSendSessionState
    generation: int = Field(ge=1)
    heartbeat_at: AwareDatetime
    expires_at: AwareDatetime


class PDDSendGateDecision(ChannelModel):
    gate_name: str = Field(min_length=1, max_length=128)
    environment: str = Field(min_length=1, max_length=32)
    store_id: str | None = Field(default=None, max_length=128)
    dry_run: bool


@runtime_checkable
class PDDSendSessionProvider(Protocol):
    def current_session(self) -> PDDSendSession:
        """Return sanitized session metadata without resolving credentials."""


@runtime_checkable
class PDDSendPreflightGate(Protocol):
    def authorize_send(
        self,
        context: PDDApprovedExecutionContext,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
    ) -> PDDSendGateDecision:
        """Fail closed or return sanitized safety evidence before sender use."""


class AllowFakePDDSendPreflightGate:
    """Compatibility gate for existing fake-only callers outside production safety."""

    def authorize_send(
        self,
        context: PDDApprovedExecutionContext,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
    ) -> PDDSendGateDecision:
        del context, command, session
        return PDDSendGateDecision(
            gate_name="allow-fake-pdd-send-preflight.v1",
            environment="MOCK",
            dry_run=True,
        )


class FakePDDSendSessionProvider:
    """Mutable test provider that never contains a real account or cookie value."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("PDD send session TTL must be positive")
        self._clock = clock
        now = _as_utc(clock())
        self._session = PDDSendSession(
            session_id="fake-pdd-send-session",
            session_reference="session-ref://pdd/fake/send-session",
            cookie_reference="secret-ref://pdd/fake/cookie-bundle",
            state=PDDSendSessionState.HEALTHY,
            generation=1,
            heartbeat_at=now,
            expires_at=now + ttl,
        )
        self.lookup_count = 0
        self.secret_value_access_count = 0

    def current_session(self) -> PDDSendSession:
        self.lookup_count += 1
        return self._session

    def expire(self) -> None:
        self._session = self._session.model_copy(
            update={
                "state": PDDSendSessionState.EXPIRED,
                "expires_at": _as_utc(self._clock()) - timedelta(microseconds=1),
            }
        )

    def degrade(self) -> None:
        self._session = self._session.model_copy(
            update={"state": PDDSendSessionState.DEGRADED}
        )


class PDDHTTPSendBody(ChannelModel):
    conversation_id: str = Field(min_length=1, max_length=255)
    message_id: str = Field(min_length=1, max_length=255)
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )


class PDDHTTPSendRequest(ChannelModel):
    contract_version: Literal["1.0"] = PDD_SEND_TRANSPORT_VERSION
    request_id: str = Field(min_length=1, max_length=255)
    endpoint_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^endpoint-ref://[A-Za-z0-9._:/-]+$",
    )
    session_reference: str = Field(repr=False)
    cookie_reference: str = Field(repr=False)
    execution_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=255)
    send_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    body: PDDHTTPSendBody

    @model_validator(mode="after")
    def validate_body_identity(self) -> PDDHTTPSendRequest:
        if self.body.message_id != self.message_id:
            raise ValueError("HTTP body message_id must match request message_id")
        return self


@runtime_checkable
class PDDHTTPRequestBuilder(Protocol):
    @property
    def builder_name(self) -> str:
        """Return a stable request contract implementation name."""

    def build(
        self,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
    ) -> PDDHTTPSendRequest:
        """Map only approved ledger data and opaque session references."""


class ReferencePDDHTTPRequestBuilder:
    """Reference-only builder. It intentionally has no real URL or HTTP client."""

    builder_name = "pdd-http-send-request-builder.v1"

    def __init__(
        self,
        endpoint_reference: str = "endpoint-ref://pdd/send-message/v1",
    ) -> None:
        self.endpoint_reference = endpoint_reference

    @staticmethod
    def message_id(decision_id: str) -> str:
        return f"pdd-outbound:{decision_id}"

    def build(
        self,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
    ) -> PDDHTTPSendRequest:
        authorization = command.authorization
        message = command.message
        message_id = self.message_id(authorization.decision_id)
        return PDDHTTPSendRequest(
            request_id=f"pdd-send:{message.execution_id}",
            endpoint_reference=self.endpoint_reference,
            session_reference=session.session_reference,
            cookie_reference=session.cookie_reference,
            execution_id=message.execution_id,
            decision_id=authorization.decision_id,
            approval_id=authorization.approval_id,
            message_id=message_id,
            send_key=message.idempotency_key,
            body=PDDHTTPSendBody(
                conversation_id=message.conversation_id,
                message_id=message_id,
                content=message.content,
            ),
        )


class PDDHTTPResponseState(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCONFIRMED = "UNCONFIRMED"


class PDDHTTPSendResponse(ChannelModel):
    request_id: str = Field(min_length=1, max_length=255)
    http_status: int = Field(ge=100, le=599)
    state: PDDHTTPResponseState
    trigger_accepted: bool
    external_message_id: str | None = Field(default=None, max_length=255)
    platform_error_code: str | None = Field(default=None, max_length=128)
    received_at: AwareDatetime

    @model_validator(mode="after")
    def validate_response_state(self) -> PDDHTTPSendResponse:
        if self.state is PDDHTTPResponseState.CONFIRMED:
            if (
                not self.trigger_accepted
                or self.external_message_id is None
                or self.platform_error_code is not None
            ):
                raise ValueError("confirmed response requires accepted trigger and ID")
        elif self.state is PDDHTTPResponseState.REJECTED:
            if self.trigger_accepted or self.platform_error_code is None:
                raise ValueError("rejected response must prove trigger was not accepted")
        elif not self.trigger_accepted or self.platform_error_code is None:
            raise ValueError("unconfirmed response requires a possibly accepted trigger")
        return self


class PDDHTTPSendTimeout(TimeoutError):
    def __init__(self, message: str, *, trigger_may_have_occurred: bool) -> None:
        super().__init__(message)
        self.trigger_may_have_occurred = trigger_may_have_occurred


@runtime_checkable
class PDDHTTPSender(Protocol):
    @property
    def sender_name(self) -> str:
        """Return a stable implementation name."""

    @property
    def real_platform_transport(self) -> bool:
        """Declare whether this sender can contact a real platform."""

    def send(
        self,
        request: PDDHTTPSendRequest,
        *,
        timeout_seconds: float,
    ) -> PDDHTTPSendResponse:
        """Send one pre-built request or raise a phase-aware timeout."""


class FakePDDHTTPSenderMode(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    PRE_TRIGGER_TIMEOUT = "PRE_TRIGGER_TIMEOUT"


class FakePDDHTTPSender:
    sender_name = "fake-pdd-http-sender.v1"
    real_platform_transport = False

    def __init__(
        self,
        mode: FakePDDHTTPSenderMode = FakePDDHTTPSenderMode.SUCCESS,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.mode = mode
        self._clock = clock
        self.send_count = 0
        self.trigger_count = 0
        self.real_platform_call_count = 0
        self.requests: list[PDDHTTPSendRequest] = []

    def send(
        self,
        request: PDDHTTPSendRequest,
        *,
        timeout_seconds: float,
    ) -> PDDHTTPSendResponse:
        if timeout_seconds <= 0:
            raise ValueError("PDD HTTP send timeout must be positive")
        self.send_count += 1
        self.requests.append(request)
        now = _as_utc(self._clock())
        if self.mode is FakePDDHTTPSenderMode.PRE_TRIGGER_TIMEOUT:
            raise PDDHTTPSendTimeout(
                "fake timeout before trigger",
                trigger_may_have_occurred=False,
            )
        if self.mode is FakePDDHTTPSenderMode.TIMEOUT:
            self.trigger_count += 1
            raise PDDHTTPSendTimeout(
                "fake timeout after trigger",
                trigger_may_have_occurred=True,
            )
        if self.mode is FakePDDHTTPSenderMode.FAILED:
            return PDDHTTPSendResponse(
                request_id=request.request_id,
                http_status=422,
                state=PDDHTTPResponseState.REJECTED,
                trigger_accepted=False,
                platform_error_code="FAKE_PDD_HTTP_REJECTED",
                received_at=now,
            )
        self.trigger_count += 1
        if self.mode is FakePDDHTTPSenderMode.UNKNOWN:
            return PDDHTTPSendResponse(
                request_id=request.request_id,
                http_status=202,
                state=PDDHTTPResponseState.UNCONFIRMED,
                trigger_accepted=True,
                platform_error_code="FAKE_PDD_CONFIRMATION_MISSING",
                received_at=now,
            )
        return PDDHTTPSendResponse(
            request_id=request.request_id,
            http_status=200,
            state=PDDHTTPResponseState.CONFIRMED,
            trigger_accepted=True,
            external_message_id=f"fake-pdd-http:{request.message_id}",
            received_at=now,
        )


class PDDParsedSendResult(ChannelModel):
    outcome: ReceiptOutcome
    trigger_state: Literal[
        "NOT_TRIGGERED", "TRIGGERED_CONFIRMED", "TRIGGERED_UNCONFIRMED"
    ]
    result_category: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    external_message_id: str | None = None
    error_code: str | None = None
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_result(self) -> PDDParsedSendResult:
        if self.outcome is ReceiptOutcome.SUCCESS:
            if self.external_message_id is None or self.error_code is not None:
                raise ValueError("successful send requires external ID and no error")
        elif self.error_code is None:
            raise ValueError("non-success send requires an error code")
        if (
            self.trigger_state == "TRIGGERED_UNCONFIRMED"
            and self.outcome is not ReceiptOutcome.UNKNOWN
        ):
            raise ValueError("unconfirmed trigger must map to UNKNOWN")
        return self


class PDDHTTPResponseParser:
    parser_name = "pdd-http-send-response-parser.v1"

    def parse(
        self,
        request: PDDHTTPSendRequest,
        response: PDDHTTPSendResponse,
    ) -> PDDParsedSendResult:
        if response.request_id != request.request_id:
            return PDDParsedSendResult(
                outcome=ReceiptOutcome.UNKNOWN,
                trigger_state="TRIGGERED_UNCONFIRMED",
                result_category="RESPONSE_ID_MISMATCH",
                error_code="PDD_HTTP_RESPONSE_ID_MISMATCH_UNKNOWN",
                completed_at=response.received_at,
            )
        if response.state is PDDHTTPResponseState.CONFIRMED:
            return PDDParsedSendResult(
                outcome=ReceiptOutcome.SUCCESS,
                trigger_state="TRIGGERED_CONFIRMED",
                result_category="HTTP_CONFIRMED",
                external_message_id=response.external_message_id,
                completed_at=response.received_at,
            )
        if response.state is PDDHTTPResponseState.REJECTED:
            return PDDParsedSendResult(
                outcome=ReceiptOutcome.FAILED,
                trigger_state="NOT_TRIGGERED",
                result_category="HTTP_REJECTED",
                error_code=response.platform_error_code or "PDD_HTTP_REJECTED",
                completed_at=response.received_at,
            )
        return PDDParsedSendResult(
            outcome=ReceiptOutcome.UNKNOWN,
            trigger_state="TRIGGERED_UNCONFIRMED",
            result_category="HTTP_UNCONFIRMED",
            error_code=(
                response.platform_error_code or "PDD_HTTP_UNCONFIRMED_UNKNOWN"
            ),
            completed_at=response.received_at,
        )


class PDDSendReceiptRecord(ChannelModel):
    contract_version: Literal["1.0"] = PDD_SEND_TRANSPORT_VERSION
    execution_id: str
    decision_id: str
    approval_id: str
    message_id: str
    send_key: str
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: ChannelSendReceipt


@runtime_checkable
class PDDSendReceiptStore(Protocol):
    def get_by_execution_id(self, execution_id: str) -> PDDSendReceiptRecord | None:
        """Return an immutable original result for execution replay."""

    def find_any(
        self,
        *,
        execution_id: str,
        message_id: str,
        send_key: str,
    ) -> PDDSendReceiptRecord | None:
        """Find any receipt bound to one of the three idempotency identities."""

    def append(self, record: PDDSendReceiptRecord) -> PDDSendReceiptRecord:
        """Append once; return the exact original on an identical replay."""


class InMemoryPDDSendReceiptStore:
    """Thread-safe append-only fake store used by the V1 foundation."""

    def __init__(self) -> None:
        self._by_execution: dict[str, PDDSendReceiptRecord] = {}
        self._by_message: dict[str, PDDSendReceiptRecord] = {}
        self._by_send_key: dict[str, PDDSendReceiptRecord] = {}
        self._lock = Lock()

    def get_by_execution_id(self, execution_id: str) -> PDDSendReceiptRecord | None:
        with self._lock:
            return self._by_execution.get(execution_id)

    def find_any(
        self,
        *,
        execution_id: str,
        message_id: str,
        send_key: str,
    ) -> PDDSendReceiptRecord | None:
        with self._lock:
            matches = {
                id(item): item
                for item in (
                    self._by_execution.get(execution_id),
                    self._by_message.get(message_id),
                    self._by_send_key.get(send_key),
                )
                if item is not None
            }
            if not matches:
                return None
            if len(matches) != 1:
                raise PDDSendIdempotencyConflict(
                    "PDD send identities resolve to different receipts",
                    error_code="PDD_SEND_IDENTITY_SPLIT_BRAIN",
                )
            return next(iter(matches.values()))

    def append(self, record: PDDSendReceiptRecord) -> PDDSendReceiptRecord:
        with self._lock:
            existing_items = {
                id(item): item
                for item in (
                    self._by_execution.get(record.execution_id),
                    self._by_message.get(record.message_id),
                    self._by_send_key.get(record.send_key),
                )
                if item is not None
            }
            if existing_items:
                if len(existing_items) != 1:
                    raise PDDSendIdempotencyConflict(
                        "PDD send identities resolve to different receipts",
                        error_code="PDD_SEND_IDENTITY_SPLIT_BRAIN",
                    )
                existing = next(iter(existing_items.values()))
                if existing != record:
                    raise PDDSendIdempotencyConflict(
                        "PDD send identity was reused with different evidence",
                        error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
                    )
                return existing
            self._by_execution[record.execution_id] = record
            self._by_message[record.message_id] = record
            self._by_send_key[record.send_key] = record
            return record


class PDDSendTransport:
    """Approval/lease-fenced PDD send orchestrator over an injected HTTP port."""

    transport_name = "pdd-controlled-send-transport.v1"

    def __init__(
        self,
        authorization_service: LedgerExecutionAuthorizationService,
        session_provider: PDDSendSessionProvider,
        sender: PDDHTTPSender,
        *,
        request_builder: PDDHTTPRequestBuilder | None = None,
        response_parser: PDDHTTPResponseParser | None = None,
        receipt_store: PDDSendReceiptStore | None = None,
        safety_gate: PDDSendPreflightGate | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("PDD send timeout must be positive")
        if not isinstance(session_provider, PDDSendSessionProvider):
            raise TypeError("session provider does not implement PDDSendSessionProvider")
        if not isinstance(sender, PDDHTTPSender):
            raise TypeError("sender does not implement PDDHTTPSender")
        selected_gate = safety_gate or AllowFakePDDSendPreflightGate()
        if sender.real_platform_transport and not bool(
            getattr(selected_gate, "allow_real_platform_transport", False)
        ):
            raise PDDSendSafetyError(
                "real PDD sender requires an explicit Pilot safety gate",
                error_code="PDD_REAL_SEND_FORBIDDEN",
            )
        self.authorization_service = authorization_service
        self.session_provider = session_provider
        self.sender = sender
        self.request_builder = request_builder or ReferencePDDHTTPRequestBuilder()
        self.response_parser = response_parser or PDDHTTPResponseParser()
        self.safety_gate = selected_gate
        gate_receipt_store = getattr(self.safety_gate, "receipt_store", None)
        self.receipt_store = (
            receipt_store
            or gate_receipt_store
            or InMemoryPDDSendReceiptStore()
        )
        self.timeout_seconds = timeout_seconds
        self._clock = clock
        self._send_lock = Lock()
        self.send_call_count = 0
        self.replay_count = 0

    def validate_session(self) -> PDDSendSession:
        session = self.session_provider.current_session()
        now = _as_utc(self._clock())
        if session.state is PDDSendSessionState.EXPIRED or _as_utc(
            session.expires_at
        ) <= now:
            raise PDDSendSessionUnavailable(
                "PDD send session is expired",
                error_code="PDD_SEND_SESSION_EXPIRED",
            )
        if session.state is not PDDSendSessionState.HEALTHY:
            raise PDDSendSessionUnavailable(
                "PDD send session is not healthy",
                error_code="PDD_SEND_SESSION_UNHEALTHY",
            )
        return session

    def health_check(self) -> AdapterHealth:
        try:
            session = self.validate_session()
        except PDDSendSessionUnavailable as exc:
            status = AdapterHealthStatus.UNHEALTHY
            session_state = "UNAVAILABLE"
            error_code: str | None = exc.error_code
        else:
            status = AdapterHealthStatus.HEALTHY
            session_state = session.state.value
            error_code = None
        return AdapterHealth(
            adapter_name="PDDSendTransportV1",
            channel="pdd",
            status=status,
            checked_at=_as_utc(self._clock()),
            real_platform_connected=(
                self.sender.real_platform_transport
                and status is AdapterHealthStatus.HEALTHY
            ),
            details={
                "contract_version": PDD_SEND_TRANSPORT_VERSION,
                "mode": (
                    "CONTROLLED_PILOT_HTTP_SEND"
                    if self.sender.real_platform_transport
                    else "CONTROLLED_FAKE_HTTP_SEND"
                ),
                "session_state": session_state,
                "error_code": error_code,
                "sender": self.sender.sender_name,
                "real_pdd_send_enabled": self.sender.real_platform_transport,
                "automatic_reply_enabled": False,
            },
        )

    def send_message(
        self,
        context: PDDApprovedExecutionContext,
    ) -> ChannelSendReceipt:
        if not isinstance(context, PDDApprovedExecutionContext):
            raise PDDSendSafetyError(
                "PDD send transport rejects bare text and untyped commands",
                error_code="PDD_APPROVED_EXECUTION_CONTEXT_REQUIRED",
            )
        with self._send_lock:
            replay = self.receipt_store.get_by_execution_id(context.execution_id)
            if replay is not None:
                self._assert_context_replay(context, replay)
                self.replay_count += 1
                return replay.receipt

            now = _as_utc(self._clock())
            if _as_utc(context.lease_expires_at) <= now:
                raise PDDSendSafetyError(
                    "approved execution context lease is expired",
                    error_code="PDD_EXECUTION_LEASE_EXPIRED",
                )
            try:
                command = self.authorization_service.issue(
                    execution_id=context.execution_id,
                    worker_id=context.worker_id,
                    execution_lease_token=context.lease_token,
                )
                self.authorization_service.verify(command)
            except ExecutionBoundaryDenied as exc:
                raise PDDSendSafetyError(
                    "live ledger denied PDD send authorization",
                    error_code="PDD_SEND_AUTHORIZATION_DENIED",
                ) from exc
            self._assert_authorized_context(context, command)

            try:
                session = self.validate_session()
            except PDDSendSessionUnavailable as exc:
                return self._record_pre_trigger_failure(
                    command,
                    error_code=exc.error_code,
                    result_category="SESSION_VALIDATION_FAILED",
                )
            permit = self.safety_gate.authorize_send(context, command, session)
            request = self.request_builder.build(command, session)
            fingerprint = self._fingerprint(request)
            existing = self.receipt_store.find_any(
                execution_id=request.execution_id,
                message_id=request.message_id,
                send_key=request.send_key,
            )
            if existing is not None:
                self._assert_request_replay(request, fingerprint, existing)
                self.replay_count += 1
                return existing.receipt

            self.send_call_count += 1
            try:
                response = self.sender.send(
                    request,
                    timeout_seconds=self.timeout_seconds,
                )
                result = self.response_parser.parse(request, response)
            except PDDHTTPSendTimeout as exc:
                result = PDDParsedSendResult(
                    outcome=(
                        ReceiptOutcome.UNKNOWN
                        if exc.trigger_may_have_occurred
                        else ReceiptOutcome.FAILED
                    ),
                    trigger_state=(
                        "TRIGGERED_UNCONFIRMED"
                        if exc.trigger_may_have_occurred
                        else "NOT_TRIGGERED"
                    ),
                    result_category=(
                        "TIMEOUT_AFTER_TRIGGER"
                        if exc.trigger_may_have_occurred
                        else "TIMEOUT_BEFORE_TRIGGER"
                    ),
                    error_code=(
                        "PDD_SEND_TIMEOUT_UNKNOWN"
                        if exc.trigger_may_have_occurred
                        else "PDD_SEND_PRE_TRIGGER_TIMEOUT"
                    ),
                    completed_at=_as_utc(self._clock()),
                )
            except Exception:
                result = PDDParsedSendResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    trigger_state="TRIGGERED_UNCONFIRMED",
                    result_category="SENDER_EXCEPTION_UNKNOWN",
                    error_code="PDD_SEND_TRANSPORT_EXCEPTION_UNKNOWN",
                    completed_at=_as_utc(self._clock()),
                )
            return self._record(command, request, fingerprint, result, permit)

    def _record_pre_trigger_failure(
        self,
        command: AuthorizedOutboundMessage,
        *,
        error_code: str,
        result_category: str,
    ) -> ChannelSendReceipt:
        message = command.message
        message_id = ReferencePDDHTTPRequestBuilder.message_id(
            command.authorization.decision_id
        )
        fingerprint = self._logical_fingerprint(
            execution_id=message.execution_id,
            decision_id=command.authorization.decision_id,
            approval_id=command.authorization.approval_id,
            message_id=message_id,
            send_key=message.idempotency_key,
            conversation_id=message.conversation_id,
            content=message.content,
        )
        result = PDDParsedSendResult(
            outcome=ReceiptOutcome.FAILED,
            trigger_state="NOT_TRIGGERED",
            result_category=result_category,
            error_code=error_code,
            completed_at=_as_utc(self._clock()),
        )
        return self._append_record(
            command,
            message_id=message_id,
            send_key=message.idempotency_key,
            fingerprint=fingerprint,
            result=result,
            permit=PDDSendGateDecision(
                gate_name="session-validation.v1",
                environment="UNKNOWN",
                dry_run=True,
            ),
            sender_called=False,
        )

    def _record(
        self,
        command: AuthorizedOutboundMessage,
        request: PDDHTTPSendRequest,
        fingerprint: str,
        result: PDDParsedSendResult,
        permit: PDDSendGateDecision,
    ) -> ChannelSendReceipt:
        return self._append_record(
            command,
            message_id=request.message_id,
            send_key=request.send_key,
            fingerprint=fingerprint,
            result=result,
            permit=permit,
            sender_called=True,
        )

    def _append_record(
        self,
        command: AuthorizedOutboundMessage,
        *,
        message_id: str,
        send_key: str,
        fingerprint: str,
        result: PDDParsedSendResult,
        permit: PDDSendGateDecision,
        sender_called: bool,
    ) -> ChannelSendReceipt:
        authorization = command.authorization
        message = command.message
        receipt = ChannelSendReceipt(
            receipt_id=new_id("pdd-send-transport-receipt"),
            channel="pdd",
            conversation_id=message.conversation_id,
            execution_id=message.execution_id,
            idempotency_key=send_key,
            external_message_id=result.external_message_id,
            outcome=result.outcome,
            error_code=result.error_code,
            details={
                "contract_version": PDD_SEND_TRANSPORT_VERSION,
                "mode": (
                    "CONTROLLED_PILOT_HTTP_SEND"
                    if self.sender.real_platform_transport
                    else "CONTROLLED_FAKE_HTTP_SEND"
                ),
                "decision_id": authorization.decision_id,
                "approval_id": authorization.approval_id,
                "approved_by": authorization.approved_by,
                "authorization_id": authorization.authorization_id,
                "message_id": message_id,
                "send_key": send_key,
                "result_category": result.result_category,
                "trigger_state": result.trigger_state,
                "sender": self.sender.sender_name,
                "request_builder": self.request_builder.builder_name,
                "safety_gate": permit.gate_name,
                "environment": permit.environment,
                "store_id": permit.store_id,
                "dry_run": permit.dry_run,
                "human_approval_required": True,
                "automatic_retry_allowed": False,
                "reconciliation_required": result.outcome is ReceiptOutcome.UNKNOWN,
                "real_platform_called": (
                    sender_called and self.sender.real_platform_transport
                ),
                "customer_message_sent": (
                    sender_called
                    and self.sender.real_platform_transport
                    and result.outcome is ReceiptOutcome.SUCCESS
                    and result.trigger_state == "TRIGGERED_CONFIRMED"
                ),
                "automatic_reply": False,
                "refund_performed": False,
                "order_modified": False,
            },
            recorded_at=result.completed_at,
        )
        record = PDDSendReceiptRecord(
            execution_id=message.execution_id,
            decision_id=authorization.decision_id,
            approval_id=authorization.approval_id,
            message_id=message_id,
            send_key=send_key,
            request_fingerprint=fingerprint,
            receipt=receipt,
        )
        return self.receipt_store.append(record).receipt

    @staticmethod
    def _assert_authorized_context(
        context: PDDApprovedExecutionContext,
        command: AuthorizedOutboundMessage,
    ) -> None:
        authorization = command.authorization
        if (
            authorization.execution_id != context.execution_id
            or authorization.decision_id != context.decision_id
            or authorization.approval_id != context.approval_id
            or authorization.approved_by != context.approved_by
            or authorization.worker_id != context.worker_id
            or authorization.execution_lease_token != context.lease_token
        ):
            raise PDDSendSafetyError(
                "approved execution context does not match live authorization",
                error_code="PDD_APPROVED_CONTEXT_MISMATCH",
            )

    @staticmethod
    def _assert_context_replay(
        context: PDDApprovedExecutionContext,
        record: PDDSendReceiptRecord,
    ) -> None:
        if (
            context.execution_id != record.execution_id
            or context.decision_id != record.decision_id
            or context.approval_id != record.approval_id
        ):
            raise PDDSendIdempotencyConflict(
                "execution replay context differs from the original receipt",
                error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
            )

    @staticmethod
    def _assert_request_replay(
        request: PDDHTTPSendRequest,
        fingerprint: str,
        record: PDDSendReceiptRecord,
    ) -> None:
        if (
            request.execution_id != record.execution_id
            or request.decision_id != record.decision_id
            or request.approval_id != record.approval_id
            or request.message_id != record.message_id
            or request.send_key != record.send_key
            or fingerprint != record.request_fingerprint
        ):
            raise PDDSendIdempotencyConflict(
                "execution_id, message_id or send_key was reused",
                error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
            )

    @classmethod
    def _fingerprint(cls, request: PDDHTTPSendRequest) -> str:
        return cls._logical_fingerprint(
            execution_id=request.execution_id,
            decision_id=request.decision_id,
            approval_id=request.approval_id,
            message_id=request.message_id,
            send_key=request.send_key,
            conversation_id=request.body.conversation_id,
            content=request.body.content,
        )

    @staticmethod
    def _logical_fingerprint(**values: object) -> str:
        return hashlib.sha256(
            json.dumps(
                values,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


class PDDControlledSendExecutionAdapter:
    """ExecutionWorker bridge for the no-bare-text send transport."""

    def __init__(self, transport: PDDSendTransport) -> None:
        self.transport = transport
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        raise PDDSendSafetyError(
            "PDD controlled send requires claimed execution context",
            error_code="PDD_CLAIMED_EXECUTION_REQUIRED",
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
            return self._denied("PDD_EXECUTION_CONTEXT_MISMATCH")
        try:
            receipt = self.transport.send_message(
                PDDApprovedExecutionContext.from_claimed(context)
            )
        except PDDSendSafetyError as exc:
            return self._denied(exc.error_code)
        return ExecutionResult(
            outcome=receipt.outcome,
            external_reference=receipt.external_message_id,
            error_code=receipt.error_code,
            details={
                **receipt.details,
                "channel_receipt_id": receipt.receipt_id,
                "execution_command_verified": True,
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "PDD_CONTROLLED_SEND_TRANSPORT",
                "human_approval_required": True,
                "manual_review_required": "REVIEW_REQUIRED" in error_code,
                "automatic_retry_allowed": False,
                "real_platform_called": False,
                "customer_message_sent": False,
                "automatic_reply": False,
                "refund_performed": False,
                "order_modified": False,
            },
        )


__all__ = [
    "PDD_SEND_TRANSPORT_VERSION",
    "FakePDDHTTPSender",
    "FakePDDHTTPSenderMode",
    "FakePDDSendSessionProvider",
    "AllowFakePDDSendPreflightGate",
    "InMemoryPDDSendReceiptStore",
    "PDDApprovedExecutionContext",
    "PDDControlledSendExecutionAdapter",
    "PDDHTTPRequestBuilder",
    "PDDHTTPResponseParser",
    "PDDHTTPResponseState",
    "PDDHTTPSendBody",
    "PDDHTTPSendRequest",
    "PDDHTTPSendResponse",
    "PDDHTTPSendTimeout",
    "PDDHTTPSender",
    "PDDParsedSendResult",
    "PDDSendIdempotencyConflict",
    "PDDSendGateDecision",
    "PDDSendPreflightGate",
    "PDDSendReceiptRecord",
    "PDDSendReceiptStore",
    "PDDSendSafetyError",
    "PDDSendSession",
    "PDDSendSessionProvider",
    "PDDSendSessionState",
    "PDDSendSessionUnavailable",
    "PDDSendTransport",
    "ReferencePDDHTTPRequestBuilder",
]
