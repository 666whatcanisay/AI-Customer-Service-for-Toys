from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from channel_engine.channel.adapter_foundation import ChannelMessageV1
from channel_engine.channel.protocol import NormalizedMessage
from channel_engine.conversation.service import ConversationService, IntakeResult
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionEnqueued,
    ExecutionWorker,
    WorkerRunResult,
    to_gateway_execution_receipt,
)
from channel_engine.models import (
    EventType,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.models.entities import new_id, utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork

from .auth import (
    GatewayAuthenticationFailed,
    GatewayAuthenticationRequired,
    GatewayContractVersionMismatch,
    GatewayRequestSigner,
    verify_gateway_request,
)
from .client import (
    AICSGatewayClient,
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    GATEWAY_MEDIA_TYPE,
    GatewayContractViolation,
    GatewayTransport,
    GatewayTransportError,
    GatewayTransportResponse,
    GatewayTransportTimeout,
)
from .contract import (
    CONTRACT_VERSION,
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    Event as GatewayEvent,
    ExecutionReceipt as GatewayExecutionReceipt,
    GatewayAggregateType,
    GatewayError,
    GatewayErrorCode,
    RETRYABLE_ERROR_CODES,
)
from .protocol import GatewayUnavailable, IdempotencyConflict


GATEWAY_SANDBOX_INTEGRATION_VERSION = "1.0"
GATEWAY_EVENT_PATH_PREFIX = "/gateway/v1/events/"
GATEWAY_RECEIPT_PATH_PREFIX = "/gateway/v1/execution-receipts/"
GATEWAY_ARTIFACT_TIMEOUT_SECONDS = 10.0
GATEWAY_ARTIFACT_BODY_LIMIT_BYTES = 256 * 1024


class GatewaySandboxModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    sandbox_integration_version: Literal["1.0"] = (
        GATEWAY_SANDBOX_INTEGRATION_VERSION
    )


class GatewaySandboxStage(StrEnum):
    DECISION_REQUESTED = "DECISION_REQUESTED"
    DECISION_RESOLVED = "DECISION_RESOLVED"
    GATEWAY_UNKNOWN = "GATEWAY_UNKNOWN"
    GATEWAY_FAILED = "GATEWAY_FAILED"
    APPROVAL_RECORDED = "APPROVAL_RECORDED"
    EXECUTION_ENQUEUED = "EXECUTION_ENQUEUED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    RECEIPT_PUBLISHED = "RECEIPT_PUBLISHED"
    EXECUTION_EVENT_PUBLISHED = "EXECUTION_EVENT_PUBLISHED"


class GatewaySandboxTraceEntry(GatewaySandboxModel):
    entry_id: str = Field(min_length=1, max_length=128)
    stage: GatewaySandboxStage
    correlation_id: str = Field(min_length=1, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    decision_id: str | None = Field(default=None, max_length=128)
    approval_id: str | None = Field(default=None, max_length=128)
    execution_id: str | None = Field(default=None, max_length=128)
    receipt_id: str | None = Field(default=None, max_length=128)
    event_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=128)
    recovered: bool = False
    occurred_at: AwareDatetime


class GatewaySandboxTrace(GatewaySandboxModel):
    correlation_id: str = Field(min_length=1, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    decision_id: str | None = Field(default=None, max_length=128)
    approval_id: str | None = Field(default=None, max_length=128)
    execution_id: str | None = Field(default=None, max_length=128)
    receipt_id: str | None = Field(default=None, max_length=128)
    event_id: str | None = Field(default=None, max_length=128)
    entries: tuple[GatewaySandboxTraceEntry, ...]


class GatewaySandboxTraceStore:
    """Append-only, metadata-only trace. Message content is never recorded."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._entries: dict[str, list[GatewaySandboxTraceEntry]] = {}
        self._message_index: dict[str, str] = {}
        self._decision_index: dict[str, str] = {}
        self._approval_index: dict[str, str] = {}
        self._execution_index: dict[str, str] = {}
        self._lock = RLock()

    def record(
        self,
        *,
        stage: GatewaySandboxStage,
        correlation_id: str,
        message_id: str | None = None,
        request_id: str | None = None,
        decision_id: str | None = None,
        approval_id: str | None = None,
        execution_id: str | None = None,
        receipt_id: str | None = None,
        event_id: str | None = None,
        error_code: str | None = None,
        recovered: bool = False,
    ) -> GatewaySandboxTraceEntry:
        entry = GatewaySandboxTraceEntry(
            entry_id=new_id("gateway-sandbox-trace"),
            stage=stage,
            correlation_id=correlation_id,
            message_id=message_id,
            request_id=request_id,
            decision_id=decision_id,
            approval_id=approval_id,
            execution_id=execution_id,
            receipt_id=receipt_id,
            event_id=event_id,
            error_code=error_code,
            recovered=recovered,
            occurred_at=_aware(self._clock()),
        )
        with self._lock:
            if message_id is not None:
                existing = self._message_index.get(message_id)
                if existing not in {None, correlation_id}:
                    raise ValueError("message_id is already bound to another trace")
            if decision_id is not None:
                existing = self._decision_index.get(decision_id)
                if existing not in {None, correlation_id}:
                    raise ValueError("decision_id is already bound to another trace")
            if approval_id is not None:
                existing = self._approval_index.get(approval_id)
                if existing not in {None, correlation_id}:
                    raise ValueError("approval_id is already bound to another trace")
            if execution_id is not None:
                existing = self._execution_index.get(execution_id)
                if existing not in {None, correlation_id}:
                    raise ValueError("execution_id is already bound to another trace")
            self._entries.setdefault(correlation_id, []).append(entry)
            if message_id is not None:
                self._message_index[message_id] = correlation_id
            if decision_id is not None:
                self._decision_index[decision_id] = correlation_id
            if approval_id is not None:
                self._approval_index[approval_id] = correlation_id
            if execution_id is not None:
                self._execution_index[execution_id] = correlation_id
        return entry

    def snapshot(self, correlation_id: str) -> GatewaySandboxTrace:
        with self._lock:
            entries = tuple(self._entries.get(correlation_id, ()))
        if not entries:
            raise KeyError(f"gateway sandbox trace not found: {correlation_id}")
        return GatewaySandboxTrace(
            correlation_id=correlation_id,
            message_id=_last_value(entries, "message_id"),
            request_id=_last_value(entries, "request_id"),
            decision_id=_last_value(entries, "decision_id"),
            approval_id=_last_value(entries, "approval_id"),
            execution_id=_last_value(entries, "execution_id"),
            receipt_id=_last_value(entries, "receipt_id"),
            event_id=_last_value(entries, "event_id"),
            entries=entries,
        )

    def for_message(self, message_id: str) -> GatewaySandboxTrace:
        with self._lock:
            correlation_id = self._message_index.get(message_id)
        if correlation_id is None:
            raise KeyError(f"gateway sandbox message trace not found: {message_id}")
        return self.snapshot(correlation_id)

    def for_decision(self, decision_id: str) -> GatewaySandboxTrace:
        with self._lock:
            correlation_id = self._decision_index.get(decision_id)
        if correlation_id is None:
            raise KeyError(f"gateway sandbox decision trace not found: {decision_id}")
        return self.snapshot(correlation_id)

    def for_approval(self, approval_id: str) -> GatewaySandboxTrace:
        with self._lock:
            correlation_id = self._approval_index.get(approval_id)
        if correlation_id is None:
            raise KeyError(f"gateway sandbox approval trace not found: {approval_id}")
        return self.snapshot(correlation_id)

    def for_execution(self, execution_id: str) -> GatewaySandboxTrace:
        with self._lock:
            correlation_id = self._execution_index.get(execution_id)
        if correlation_id is None:
            raise KeyError(f"gateway sandbox execution trace not found: {execution_id}")
        return self.snapshot(correlation_id)

    def list_traces(self) -> tuple[GatewaySandboxTrace, ...]:
        with self._lock:
            correlation_ids = tuple(self._entries)
        return tuple(self.snapshot(item) for item in correlation_ids)


class SandboxTransportFault(StrEnum):
    PASS_THROUGH = "PASS_THROUGH"
    TIMEOUT = "TIMEOUT"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    INVALID_SUCCESS = "INVALID_SUCCESS"


class ScriptedSandboxGatewayTransport:
    """Deterministic fault injector around an in-process GatewayTransport."""

    def __init__(
        self,
        delegate: GatewayTransport,
        faults: Iterable[SandboxTransportFault],
    ) -> None:
        if not isinstance(delegate, GatewayTransport):
            raise TypeError("delegate does not implement GatewayTransport")
        self._delegate = delegate
        self._faults = deque(faults)
        self.attempt_count = 0

    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        self.attempt_count += 1
        fault = (
            self._faults.popleft()
            if self._faults
            else SandboxTransportFault.PASS_THROUGH
        )
        if fault is SandboxTransportFault.TIMEOUT:
            raise GatewayTransportTimeout("sandbox-injected gateway timeout")
        if fault is SandboxTransportFault.NETWORK_FAILURE:
            raise GatewayTransportError("sandbox-injected gateway network failure")
        response = self._delegate.request(
            method=method,
            path=path,
            body=body,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        if fault is SandboxTransportFault.INVALID_SUCCESS and response.status_code == 200:
            return GatewayTransportResponse(
                status_code=200,
                body=b'{"contract_version":"1.0"}',
                headers=response.headers,
            )
        return response


class SandboxArtifactAck(GatewaySandboxModel):
    status_code: Literal[202] = 202
    artifact_id: str = Field(min_length=1, max_length=128)
    replayed: bool


class SandboxGatewayArtifactServer:
    """In-process Contract V1 receiver for Event and ExecutionReceipt only."""

    def __init__(
        self,
        credentials: Mapping[tuple[str, str], bytes],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not credentials:
            raise ValueError("sandbox artifact server requires credentials")
        self._credentials = dict(credentials)
        self._clock = clock
        self._artifacts: dict[tuple[str, str], tuple[str, object]] = {}
        self._nonces: set[tuple[str, str, str]] = set()
        self._lock = RLock()
        self.accept_count = 0
        self.replay_count = 0
        self.error_count = 0

    @property
    def events(self) -> tuple[GatewayEvent, ...]:
        with self._lock:
            return tuple(
                artifact
                for (kind, _), (_, artifact) in self._artifacts.items()
                if kind == "event" and isinstance(artifact, GatewayEvent)
            )

    @property
    def receipts(self) -> tuple[GatewayExecutionReceipt, ...]:
        with self._lock:
            return tuple(
                artifact
                for (kind, _), (_, artifact) in self._artifacts.items()
                if kind == "receipt"
                and isinstance(artifact, GatewayExecutionReceipt)
            )

    def handle_request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        route = _artifact_route(path)
        if route is None:
            return self._error(GatewayErrorCode.RESOURCE_NOT_FOUND, headers)
        if method.upper() != "PUT":
            return self._error(GatewayErrorCode.METHOD_NOT_ALLOWED, headers)
        if len(body) > GATEWAY_ARTIFACT_BODY_LIMIT_BYTES:
            return self._error(GatewayErrorCode.PAYLOAD_TOO_LARGE, headers)
        normalized = {name.lower(): value for name, value in headers.items()}
        content_type = normalized.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != GATEWAY_MEDIA_TYPE:
            return self._error(GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE, headers)
        try:
            authentication = verify_gateway_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
                credentials=self._credentials,
                now=_aware(self._clock()),
            )
        except GatewayAuthenticationRequired:
            return self._error(GatewayErrorCode.AUTHENTICATION_REQUIRED, headers)
        except GatewayContractVersionMismatch:
            return self._error(
                GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION, headers
            )
        except GatewayAuthenticationFailed:
            return self._error(GatewayErrorCode.AUTHENTICATION_FAILED, headers)

        nonce_key = (
            authentication.client_id,
            authentication.key_id,
            authentication.nonce,
        )
        with self._lock:
            if nonce_key in self._nonces:
                return self._error(GatewayErrorCode.AUTHENTICATION_FAILED, headers)
            self._nonces.add(nonce_key)

        kind, artifact_id = route
        try:
            artifact: GatewayEvent | GatewayExecutionReceipt
            if kind == "event":
                artifact = GatewayEvent.model_validate_json(body)
                body_id = artifact.event_id
                idempotency_key = artifact.event_id
            else:
                artifact = GatewayExecutionReceipt.model_validate_json(body)
                body_id = artifact.receipt_id
                idempotency_key = artifact.receipt_id
        except ValidationError:
            return self._error(GatewayErrorCode.SCHEMA_VALIDATION_FAILED, headers)
        if (
            artifact.contract_version != CONTRACT_VERSION
            or body_id != artifact_id
            or normalized.get("idempotency-key") != idempotency_key
            or normalized.get("x-correlation-id") != artifact.correlation_id
        ):
            return self._error(GatewayErrorCode.INVALID_REQUEST, headers)

        fingerprint = hashlib.sha256(body).hexdigest()
        key = (kind, artifact_id)
        with self._lock:
            previous = self._artifacts.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    return self._error(GatewayErrorCode.IDEMPOTENCY_CONFLICT, headers)
                self.replay_count += 1
                replayed = True
            else:
                self._artifacts[key] = (fingerprint, artifact)
                self.accept_count += 1
                replayed = False
        return GatewayTransportResponse(
            status_code=202,
            body=b"",
            headers={
                "X-AI-CS-Contract-Version": CONTRACT_VERSION,
                "X-Request-ID": normalized["x-request-id"],
                "X-Correlation-ID": artifact.correlation_id,
                "Idempotency-Replayed": str(replayed).lower(),
            },
        )

    def _error(
        self,
        code: GatewayErrorCode,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        normalized = {name.lower(): value for name, value in headers.items()}
        self.error_count += 1
        status = {
            GatewayErrorCode.INVALID_REQUEST: 400,
            GatewayErrorCode.AUTHENTICATION_REQUIRED: 401,
            GatewayErrorCode.AUTHENTICATION_FAILED: 401,
            GatewayErrorCode.RESOURCE_NOT_FOUND: 404,
            GatewayErrorCode.METHOD_NOT_ALLOWED: 405,
            GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION: 406,
            GatewayErrorCode.IDEMPOTENCY_CONFLICT: 409,
            GatewayErrorCode.PAYLOAD_TOO_LARGE: 413,
            GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
            GatewayErrorCode.SCHEMA_VALIDATION_FAILED: 422,
        }[code]
        envelope = ErrorEnvelope(
            contract_version=CONTRACT_VERSION,
            error=GatewayError(
                error_id=new_id("gateway-sandbox-error"),
                code=code,
                message=f"Sandbox gateway rejected artifact: {code.value}",
                retryable=code in RETRYABLE_ERROR_CODES,
                request_id=normalized.get("x-request-id"),
                correlation_id=normalized.get("x-correlation-id"),
                details={"mode": "SANDBOX", "real_ai_cs_called": False},
                occurred_at=_aware(self._clock()),
            ),
        )
        return GatewayTransportResponse(
            status_code=status,
            body=envelope.model_dump_json().encode(),
            headers={"X-AI-CS-Contract-Version": CONTRACT_VERSION},
        )


class SandboxGatewayArtifactTransport:
    def __init__(self, server: SandboxGatewayArtifactServer) -> None:
        self._server = server
        self.attempt_count = 0

    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        if timeout_seconds <= 0:
            raise ValueError("artifact timeout must be positive")
        self.attempt_count += 1
        return self._server.handle_request(
            method=method,
            path=path,
            body=body,
            headers=headers,
        )


class SandboxGatewayClient:
    """Decision plus append-only artifact client for fully local validation."""

    def __init__(
        self,
        decision_client: AICSGatewayClient,
        artifact_transport: GatewayTransport,
        signer: GatewayRequestSigner,
        *,
        trace_store: GatewaySandboxTraceStore | None = None,
    ) -> None:
        if not isinstance(artifact_transport, GatewayTransport):
            raise TypeError("artifact transport does not implement GatewayTransport")
        self._decision_client = decision_client
        self._artifact_transport = artifact_transport
        self._signer = signer
        self.trace_store = trace_store or GatewaySandboxTraceStore()

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        return self.request_decision(request)

    def request_decision(self, request: DecisionRequest) -> DecisionResponse:
        validated = _contract_round_trip(request, DecisionRequest)
        self.trace_store.record(
            stage=GatewaySandboxStage.DECISION_REQUESTED,
            correlation_id=validated.correlation_id,
            message_id=validated.message_id,
            request_id=validated.request_id,
        )
        retry_count_before = self._decision_client.retry_count
        try:
            response = self._decision_client.request_decision(validated)
        except AICSGatewayTimeout:
            self.trace_store.record(
                stage=GatewaySandboxStage.GATEWAY_UNKNOWN,
                correlation_id=validated.correlation_id,
                message_id=validated.message_id,
                request_id=validated.request_id,
                error_code="GATEWAY_TIMEOUT_UNKNOWN",
            )
            raise
        except (
            AICSGatewayRequestFailed,
            GatewayContractViolation,
            GatewayUnavailable,
            IdempotencyConflict,
        ) as exc:
            error_code = (
                exc.envelope.error.code.value
                if isinstance(exc, AICSGatewayRequestFailed)
                else type(exc).__name__.upper()
            )
            self.trace_store.record(
                stage=GatewaySandboxStage.GATEWAY_FAILED,
                correlation_id=validated.correlation_id,
                message_id=validated.message_id,
                request_id=validated.request_id,
                error_code=error_code[:128],
            )
            raise
        response = _contract_round_trip(response, DecisionResponse)
        self.trace_store.record(
            stage=GatewaySandboxStage.DECISION_RESOLVED,
            correlation_id=response.correlation_id,
            message_id=validated.message_id,
            request_id=response.request_id,
            decision_id=response.decision_id,
            recovered=self._decision_client.retry_count > retry_count_before,
        )
        return response

    def health_check(self):
        return self._decision_client.health_check()

    def publish_execution_event(self, event: GatewayEvent) -> SandboxArtifactAck:
        validated = _contract_round_trip(event, GatewayEvent)
        if validated.aggregate_type is not GatewayAggregateType.EXECUTION:
            raise GatewayContractViolation(
                "publish_execution_event requires Execution aggregate"
            )
        return self.publish_event(validated)

    def publish_event(self, event: GatewayEvent) -> SandboxArtifactAck:
        validated = _contract_round_trip(event, GatewayEvent)
        ack = self._publish(
            validated,
            artifact_id=validated.event_id,
            path=f"{GATEWAY_EVENT_PATH_PREFIX}{validated.event_id}",
        )
        if validated.aggregate_type is GatewayAggregateType.EXECUTION:
            receipt_id = validated.payload.get("receipt_id")
            self.trace_store.record(
                stage=GatewaySandboxStage.EXECUTION_EVENT_PUBLISHED,
                correlation_id=validated.correlation_id,
                execution_id=validated.aggregate_id,
                receipt_id=receipt_id if isinstance(receipt_id, str) else None,
                event_id=validated.event_id,
            )
        return ack

    def publish_execution_receipt(
        self, receipt: GatewayExecutionReceipt
    ) -> SandboxArtifactAck:
        validated = _contract_round_trip(receipt, GatewayExecutionReceipt)
        ack = self._publish(
            validated,
            artifact_id=validated.receipt_id,
            path=f"{GATEWAY_RECEIPT_PATH_PREFIX}{validated.receipt_id}",
        )
        self.trace_store.record(
            stage=GatewaySandboxStage.RECEIPT_PUBLISHED,
            correlation_id=validated.correlation_id,
            decision_id=validated.decision_id,
            execution_id=validated.execution_id,
            receipt_id=validated.receipt_id,
        )
        return ack

    def send_execution_result(
        self, receipt: GatewayExecutionReceipt
    ) -> SandboxArtifactAck:
        return self.publish_execution_receipt(receipt)

    def _publish(
        self,
        artifact: GatewayEvent | GatewayExecutionReceipt,
        *,
        artifact_id: str,
        path: str,
    ) -> SandboxArtifactAck:
        body = _canonical_model_body(artifact)
        request_id = f"publish-{artifact_id}"
        headers = self._signer.sign(
            body,
            method="PUT",
            path=path,
            request_id=request_id,
            correlation_id=artifact.correlation_id,
            idempotency_key=artifact_id,
            content_type=GATEWAY_MEDIA_TYPE,
        )
        headers["Accept"] = GATEWAY_MEDIA_TYPE
        try:
            response = self._artifact_transport.request(
                method="PUT",
                path=path,
                body=body,
                headers=headers,
                timeout_seconds=GATEWAY_ARTIFACT_TIMEOUT_SECONDS,
            )
        except (GatewayTransportTimeout, GatewayTransportError) as exc:
            raise GatewayUnavailable(
                "sandbox artifact acceptance outcome is unknown"
            ) from exc
        if response.status_code != 202:
            try:
                envelope = ErrorEnvelope.model_validate_json(response.body)
            except ValidationError as exc:
                raise GatewayContractViolation(
                    "sandbox artifact error is not ErrorEnvelope V1"
                ) from exc
            raise AICSGatewayRequestFailed(response.status_code, envelope, 1)
        if response.body:
            raise GatewayContractViolation("202 artifact response body must be empty")
        normalized = {name.lower(): value for name, value in response.headers.items()}
        if (
            normalized.get("x-ai-cs-contract-version") != CONTRACT_VERSION
            or normalized.get("x-request-id") != request_id
            or normalized.get("x-correlation-id") != artifact.correlation_id
            or normalized.get("idempotency-replayed") not in {"true", "false"}
        ):
            raise GatewayContractViolation("artifact response headers are invalid")
        return SandboxArtifactAck(
            artifact_id=artifact_id,
            replayed=normalized["idempotency-replayed"] == "true",
        )


class SandboxExecutionOutcome(GatewaySandboxModel):
    decision_id: str
    execution_id: str
    execution_state: ExecutionState
    receipt_id: str
    receipt_outcome: ReceiptOutcome
    event_id: str
    trace: GatewaySandboxTrace


class GatewaySandboxRuntime:
    """Explicit approval/execution orchestration; intake never auto-executes."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        gateway_client: SandboxGatewayClient,
        execution_adapter,
        *,
        worker_id: str = "gateway-sandbox-worker",
    ) -> None:
        self._uow_factory = uow_factory
        self.gateway_client = gateway_client
        self._conversation = ConversationService(uow_factory, gateway_client)
        self._coordinator = ExecutionCoordinator(uow_factory, ApprovalPolicy())
        self._worker = ExecutionWorker(uow_factory, execution_adapter, worker_id)

    def receive(
        self, message: ChannelMessageV1 | NormalizedMessage
    ) -> IntakeResult:
        runtime_message = (
            message.to_runtime_message()
            if isinstance(message, ChannelMessageV1)
            else message
        )
        return self._conversation.receive(runtime_message)

    def approve(
        self, decision_id: str, *, approved_by: str
    ) -> ExecutionEnqueued:
        trace = self.gateway_client.trace_store.for_decision(decision_id)
        enqueued = self._coordinator.approve_and_enqueue(decision_id, approved_by)
        self.gateway_client.trace_store.record(
            stage=GatewaySandboxStage.APPROVAL_RECORDED,
            correlation_id=trace.correlation_id,
            message_id=trace.message_id,
            request_id=trace.request_id,
            decision_id=decision_id,
            approval_id=enqueued.approval_id,
            execution_id=enqueued.execution_id,
        )
        self.gateway_client.trace_store.record(
            stage=GatewaySandboxStage.EXECUTION_ENQUEUED,
            correlation_id=trace.correlation_id,
            message_id=trace.message_id,
            request_id=trace.request_id,
            decision_id=decision_id,
            approval_id=enqueued.approval_id,
            execution_id=enqueued.execution_id,
        )
        return enqueued

    def execute_approved(self, execution_id: str) -> SandboxExecutionOutcome:
        trace = self.gateway_client.trace_store.for_execution(execution_id)
        self._worker.run_execution(execution_id)
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            execution = repo.get_execution(execution_id)
            decision = repo.get_decision(execution.decision_id)
            receipt = repo.get_receipt_for_execution(execution_id)
        if receipt is None or execution.state not in {
            ExecutionState.SUCCESS,
            ExecutionState.FAILED,
            ExecutionState.UNKNOWN,
        }:
            raise RuntimeError("approved sandbox execution did not produce a receipt")
        expected_state = {
            ReceiptOutcome.SUCCESS: ExecutionState.SUCCESS,
            ReceiptOutcome.FAILED: ExecutionState.FAILED,
            ReceiptOutcome.UNKNOWN: ExecutionState.UNKNOWN,
        }[receipt.outcome]
        if execution.state is not expected_state:
            raise RuntimeError("execution and receipt terminal states disagree")

        terminal_stage, event_type = {
            ExecutionState.SUCCESS: (
                GatewaySandboxStage.EXECUTION_SUCCEEDED,
                EventType.EXECUTION_SUCCEEDED,
            ),
            ExecutionState.FAILED: (
                GatewaySandboxStage.EXECUTION_FAILED,
                EventType.EXECUTION_FAILED,
            ),
            ExecutionState.UNKNOWN: (
                GatewaySandboxStage.EXECUTION_UNKNOWN,
                EventType.EXECUTION_UNKNOWN,
            ),
        }[execution.state]
        self.gateway_client.trace_store.record(
            stage=terminal_stage,
            correlation_id=trace.correlation_id,
            request_id=trace.request_id,
            decision_id=decision.decision_id,
            execution_id=execution.execution_id,
            receipt_id=receipt.receipt_id,
        )
        gateway_receipt = to_gateway_execution_receipt(
            execution,
            receipt,
            trace.correlation_id,
        )
        self.gateway_client.publish_execution_receipt(gateway_receipt)
        event_id = _execution_event_id(execution.execution_id, event_type)
        gateway_event = GatewayEvent(
            contract_version=CONTRACT_VERSION,
            event_id=event_id,
            correlation_id=trace.correlation_id,
            causation_id=decision.decision_id,
            source="CHANNEL_ENGINE",
            event_type=event_type,
            aggregate_type=GatewayAggregateType.EXECUTION,
            aggregate_id=execution.execution_id,
            payload={
                "receipt_id": receipt.receipt_id,
                "outcome": receipt.outcome.value,
            },
            occurred_at=_aware(execution.completed_at or receipt.recorded_at),
        )
        self.gateway_client.publish_execution_event(gateway_event)
        final_trace = self.gateway_client.trace_store.snapshot(trace.correlation_id)
        return SandboxExecutionOutcome(
            decision_id=decision.decision_id,
            execution_id=execution.execution_id,
            execution_state=execution.state,
            receipt_id=receipt.receipt_id,
            receipt_outcome=receipt.outcome,
            event_id=event_id,
            trace=final_trace,
        )


def _contract_round_trip(value, model_type):
    try:
        return model_type.model_validate_json(_canonical_model_body(value))
    except (TypeError, ValueError, ValidationError) as exc:
        raise GatewayContractViolation(
            f"{model_type.__name__} failed Gateway Contract V1"
        ) from exc


def _canonical_model_body(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _artifact_route(path: str) -> tuple[str, str] | None:
    patterns = (
        ("event", GATEWAY_EVENT_PATH_PREFIX),
        ("receipt", GATEWAY_RECEIPT_PATH_PREFIX),
    )
    for kind, prefix in patterns:
        if path.startswith(prefix):
            artifact_id = path[len(prefix) :]
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", artifact_id):
                return kind, artifact_id
    return None


def _execution_event_id(execution_id: str, event_type: EventType) -> str:
    digest = hashlib.sha256(f"{execution_id}:{event_type.value}".encode()).hexdigest()
    return f"gateway-event-{digest[:32]}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _last_value(entries: tuple[GatewaySandboxTraceEntry, ...], field: str):
    return next(
        (
            value
            for entry in reversed(entries)
            if (value := getattr(entry, field)) is not None
        ),
        None,
    )


__all__ = [
    "GATEWAY_ARTIFACT_BODY_LIMIT_BYTES",
    "GATEWAY_ARTIFACT_TIMEOUT_SECONDS",
    "GATEWAY_EVENT_PATH_PREFIX",
    "GATEWAY_RECEIPT_PATH_PREFIX",
    "GATEWAY_SANDBOX_INTEGRATION_VERSION",
    "GatewaySandboxRuntime",
    "GatewaySandboxStage",
    "GatewaySandboxTrace",
    "GatewaySandboxTraceEntry",
    "GatewaySandboxTraceStore",
    "SandboxArtifactAck",
    "SandboxExecutionOutcome",
    "SandboxGatewayArtifactServer",
    "SandboxGatewayArtifactTransport",
    "SandboxGatewayClient",
    "SandboxTransportFault",
    "ScriptedSandboxGatewayTransport",
]
