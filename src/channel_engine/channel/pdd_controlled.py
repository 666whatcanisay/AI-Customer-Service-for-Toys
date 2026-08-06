from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
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
from .lifecycle import (
    ChannelAuthenticationBroker,
    ChannelCredentialReference,
    ChannelSession,
    ChannelSessionUnavailable,
)
from .pdd_observation import PDDAdapter, PDDObservationTransport
from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    SendAuthorizationVerifier,
)
from .protocol import AdapterHealth, ChannelModel, ChannelSendReceipt


class PDDControlledPolicyDecision(StrEnum):
    ALLOW_SEND_MESSAGE = "ALLOW_SEND_MESSAGE"
    DENY = "DENY"


class PDDControlledSendPolicy:
    """V1 policy allows only a low-risk, human-approved message send."""

    def evaluate(
        self,
        command: AuthorizedOutboundMessage,
    ) -> PDDControlledPolicyDecision:
        authorization = command.authorization
        message = command.message
        if (
            authorization.operation == "SEND_MESSAGE"
            and authorization.execution_risk == "LOW"
            and message.channel == "pdd"
            and bool(message.content.strip())
        ):
            return PDDControlledPolicyDecision.ALLOW_SEND_MESSAGE
        return PDDControlledPolicyDecision.DENY

    def assert_allowed(self, command: AuthorizedOutboundMessage) -> None:
        if self.evaluate(command) is not PDDControlledPolicyDecision.ALLOW_SEND_MESSAGE:
            raise ExecutionBoundaryDenied(
                "PDD policy did not return ALLOW_SEND_MESSAGE"
            )


class PDDOutboundRequest(ChannelModel):
    platform: Literal["pdd"] = "pdd"
    operation: Literal["SEND_MESSAGE"] = "SEND_MESSAGE"
    conversation_id: str = Field(min_length=1, max_length=255)
    execution_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    requested_at: AwareDatetime


class PDDOutboundResult(ChannelModel):
    outcome: ReceiptOutcome
    external_message_id: str | None = Field(default=None, max_length=255)
    error_code: str | None = Field(default=None, max_length=128)
    result_category: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]{0,63}$",
    )
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_outcome(self) -> PDDOutboundResult:
        if self.outcome is ReceiptOutcome.SUCCESS:
            if self.error_code is not None or self.external_message_id is None:
                raise ValueError(
                    "successful PDD result requires external ID and no error"
                )
        elif self.error_code is None:
            raise ValueError("non-success PDD result requires error_code")
        return self


class PDDOutboundTimeout(TimeoutError):
    """The transport cannot prove whether PDD accepted the message."""


class PDDOutboundMode(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"


@runtime_checkable
class PDDOutboundTransport(Protocol):
    """Controlled send port. V1 provides only a fake implementation."""

    @property
    def transport_name(self) -> str:
        """Return a stable, non-secret implementation name."""

    @property
    def real_platform_transport(self) -> bool:
        """Declare whether the implementation can contact a real platform."""

    def send(
        self,
        session: ChannelSession,
        request: PDDOutboundRequest,
        *,
        timeout_seconds: float,
    ) -> PDDOutboundResult:
        """Perform one idempotent send attempt or report unknown outcome."""


class FakePDDOutboundTransport:
    """In-memory fake sender. It never calls PDD or delivers a customer message."""

    transport_name = "fake-pdd-outbound-transport.v1"
    real_platform_transport = False

    def __init__(
        self,
        mode: PDDOutboundMode = PDDOutboundMode.SUCCESS,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.mode = mode
        self._clock = clock
        self._results: dict[str, tuple[str, PDDOutboundResult]] = {}
        self._lock = Lock()
        self.send_attempt_count = 0
        self.simulated_accept_count = 0
        self.duplicate_send_count = 0
        self.real_platform_call_count = 0

    def send(
        self,
        session: ChannelSession,
        request: PDDOutboundRequest,
        *,
        timeout_seconds: float,
    ) -> PDDOutboundResult:
        if not session.authenticated:
            raise ChannelSessionUnavailable("PDD outbound session is not authenticated")
        if timeout_seconds <= 0:
            raise ValueError("PDD outbound timeout must be positive")
        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            replay = self._results.get(request.idempotency_key)
            if replay is not None:
                original_fingerprint, original_result = replay
                if original_fingerprint != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "PDD idempotency key is bound to another outbound payload"
                    )
                self.duplicate_send_count += 1
                return original_result
            self.send_attempt_count += 1
            if self.mode is PDDOutboundMode.TIMEOUT:
                raise PDDOutboundTimeout(
                    "fake PDD timeout; acceptance outcome is unknown"
                )
            result = self._result(request)
            self._results[request.idempotency_key] = (fingerprint, result)
            if result.outcome is ReceiptOutcome.SUCCESS:
                self.simulated_accept_count += 1
            return result

    def _result(self, request: PDDOutboundRequest) -> PDDOutboundResult:
        if self.mode is PDDOutboundMode.SUCCESS:
            return PDDOutboundResult(
                outcome=ReceiptOutcome.SUCCESS,
                external_message_id=f"fake-pdd-controlled-{request.execution_id}",
                error_code=None,
                result_category="FAKE_ACCEPTED",
                completed_at=self._clock(),
            )
        if self.mode is PDDOutboundMode.FAILED:
            return PDDOutboundResult(
                outcome=ReceiptOutcome.FAILED,
                error_code="FAKE_PDD_SEND_REJECTED",
                result_category="FAKE_REJECTED",
                completed_at=self._clock(),
            )
        return PDDOutboundResult(
            outcome=ReceiptOutcome.UNKNOWN,
            error_code="FAKE_PDD_SEND_UNKNOWN",
            result_category="FAKE_UNKNOWN",
            completed_at=self._clock(),
        )


class PDDControlledAdapter(PDDAdapter):
    """PDD observation adapter plus a human-approved, ledger-guarded send port."""

    adapter_name = "PDDControlledAdapterV1"

    def __init__(
        self,
        credential: ChannelCredentialReference,
        authentication_broker: ChannelAuthenticationBroker,
        observation_transport: PDDObservationTransport,
        authorization_verifier: SendAuthorizationVerifier,
        outbound_transport: PDDOutboundTransport,
        *,
        policy: PDDControlledSendPolicy | None = None,
        send_timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if send_timeout_seconds <= 0:
            raise ValueError("PDD send timeout must be positive")
        if not isinstance(outbound_transport, PDDOutboundTransport):
            raise TypeError("outbound transport does not implement PDDOutboundTransport")
        super().__init__(
            credential,
            authentication_broker,
            observation_transport,
            clock=clock,
        )
        self._authorization_verifier = authorization_verifier
        self.outbound_transport = outbound_transport
        self.policy = policy or PDDControlledSendPolicy()
        self.send_timeout_seconds = send_timeout_seconds
        self._clock = clock
        self._send_results: dict[
            str, tuple[str, ChannelSendReceipt]
        ] = {}
        self._send_lock = Lock()
        self.send_call_count = 0

    def send_message(
        self,
        command: AuthorizedOutboundMessage,
    ) -> ChannelSendReceipt:
        if not isinstance(command, AuthorizedOutboundMessage):
            raise ExecutionBoundaryDenied(
                "PDD controlled send rejects a bare outbound message"
            )
        session = self._require_active_session()
        self._authorization_verifier.verify(command)
        self.policy.assert_allowed(command)
        message = command.message
        fingerprint = hashlib.sha256(
            json.dumps(
                message.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self._send_lock:
            replay = self._send_results.get(message.idempotency_key)
            if replay is not None:
                original_fingerprint, original_receipt = replay
                if original_fingerprint != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "PDD send idempotency key was reused with different content"
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
                    session,
                    request,
                    timeout_seconds=self.send_timeout_seconds,
                )
            except PDDOutboundTimeout:
                result = PDDOutboundResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    error_code="PDD_SEND_TIMEOUT_UNKNOWN",
                    result_category="TIMEOUT_UNKNOWN",
                    completed_at=self._clock(),
                )
            except ExecutionBoundaryDenied:
                raise
            except Exception:
                result = PDDOutboundResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    error_code="PDD_SEND_TRANSPORT_EXCEPTION_UNKNOWN",
                    result_category="TRANSPORT_EXCEPTION_UNKNOWN",
                    completed_at=self._clock(),
                )
            receipt = ChannelSendReceipt(
                receipt_id=new_id("pdd-controlled-send-receipt"),
                channel="pdd",
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                external_message_id=result.external_message_id,
                outcome=result.outcome,
                error_code=result.error_code,
                details={
                    "mode": "CONTROLLED_FAKE_SEND",
                    "adapter": self.adapter_name,
                    "policy": PDDControlledPolicyDecision.ALLOW_SEND_MESSAGE.value,
                    "authorization_id": command.authorization.authorization_id,
                    "approval_id": command.authorization.approval_id,
                    "result_category": result.result_category,
                    "outbound_transport": self.outbound_transport.transport_name,
                    "human_approval_required": True,
                    "automatic_reply": False,
                    "real_platform_called": False,
                    "customer_message_sent": False,
                    "refund_performed": False,
                    "order_modified": False,
                },
                recorded_at=result.completed_at,
            )
            self._send_results[message.idempotency_key] = (
                fingerprint,
                receipt,
            )
            return receipt

    def health_check(self) -> AdapterHealth:
        base = super().health_check()
        return base.model_copy(
            update={
                "adapter_name": self.adapter_name,
                "details": {
                    **base.details,
                    "mode": "CONTROLLED_SEND_FOUNDATION",
                    "controlled_send_enabled": True,
                    "send_enabled": True,
                    "automatic_reply_enabled": False,
                    "send_policy": (
                        PDDControlledPolicyDecision.ALLOW_SEND_MESSAGE.value
                    ),
                    "outbound_transport": self.outbound_transport.transport_name,
                    "real_pdd_send_enabled": False,
                },
            }
        )


class PDDControlledExecutionAdapter:
    """Maps a claimed Execution into an authorized PDD send and Worker result."""

    def __init__(
        self,
        adapter: PDDControlledAdapter,
        authorization_service: LedgerExecutionAuthorizationService,
    ) -> None:
        self.adapter = adapter
        self.authorization_service = authorization_service
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        """Reject execution that did not originate from a claimed Worker lease."""
        raise ExecutionBoundaryDenied(
            "PDD controlled execution requires claimed execution context"
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
                return self._denied("PDD_EXECUTION_CONTEXT_MISMATCH")
            receipt = self.adapter.send_message(authorized)
        except ExecutionBoundaryDenied:
            return self._denied("PDD_SEND_AUTHORIZATION_DENIED")
        except ChannelSessionUnavailable:
            return self._denied("PDD_SESSION_UNAVAILABLE")
        return ExecutionResult(
            outcome=receipt.outcome,
            external_reference=receipt.external_message_id,
            error_code=receipt.error_code,
            details={
                "mode": "PDD_CONTROLLED_EXECUTION",
                "channel_receipt_id": receipt.receipt_id,
                "decision_id": authorized.authorization.decision_id,
                "approval_id": authorized.authorization.approval_id,
                "approved_by": authorized.authorization.approved_by,
                "authorization_id": authorized.authorization.authorization_id,
                "policy": PDDControlledPolicyDecision.ALLOW_SEND_MESSAGE.value,
                "human_approved": True,
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
                "result_category": receipt.details["result_category"],
                "outbound_transport": receipt.details["outbound_transport"],
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "PDD_CONTROLLED_EXECUTION",
                "policy": PDDControlledPolicyDecision.DENY.value,
                "human_approved": False,
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
            },
        )

__all__ = [
    "FakePDDOutboundTransport",
    "PDDControlledAdapter",
    "PDDControlledExecutionAdapter",
    "PDDControlledPolicyDecision",
    "PDDControlledSendPolicy",
    "PDDOutboundMode",
    "PDDOutboundRequest",
    "PDDOutboundResult",
    "PDDOutboundTimeout",
    "PDDOutboundTransport",
]
