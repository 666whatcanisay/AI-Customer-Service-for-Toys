from __future__ import annotations

# Execution-owned sandbox; kept outside the receive-only PDD prototype package.
import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from threading import Lock, RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from channel_engine.channel import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    LedgerExecutionAuthorizationService,
)
from channel_engine.models import (
    ApprovalState,
    DecisionState,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork

from .coordinator import ExecutionCoordinator, ExecutionEnqueued
from .fake_executor import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from .worker import ExecutionWorker

PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX_VERSION = "1.0"


class PDDApprovalSandboxModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    sandbox_contract_version: Literal["1.0"] = (
        PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX_VERSION
    )


class PDDApprovalSandboxError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class FakePDDExecutionMode(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PDDApprovalSandboxSafetySnapshot(PDDApprovalSandboxModel):
    fake_executor: Literal[True] = True
    real_pdd_connected: Literal[False] = False
    real_platform_called: Literal[False] = False
    customer_message_sent: Literal[False] = False
    automatic_approval: Literal[False] = False
    automatic_reply: Literal[False] = False
    refund_performed: Literal[False] = False
    order_modified: Literal[False] = False
    payment_performed: Literal[False] = False


class PDDApprovalExecutionTrace(PDDApprovalSandboxModel):
    message_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    receipt_id: str | None = Field(default=None, max_length=128)
    authorization_id: str | None = Field(default=None, max_length=128)
    decision_state: DecisionState
    approval_state: ApprovalState
    execution_state: ExecutionState
    receipt_status: ReceiptOutcome | None = None
    automatic_retry_allowed: bool
    customer_message_sent: Literal[False] = False


class PDDApprovalExecutionResult(PDDApprovalSandboxModel):
    trace: PDDApprovalExecutionTrace
    receipt_id: str = Field(min_length=1, max_length=128)
    receipt_status: ReceiptOutcome
    adapter_called: bool
    replayed: bool = False
    safety: PDDApprovalSandboxSafetySnapshot


class FakePDDExecutor:
    """Lease-fenced fake sender; it can never deliver a customer message."""

    real_platform_transport = False
    customer_message_sent = False

    def __init__(
        self,
        authorization_service: LedgerExecutionAuthorizationService,
        mode: FakePDDExecutionMode = FakePDDExecutionMode.SUCCESS,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._authorization_service = authorization_service
        self.mode = mode
        self._clock = clock
        self._results: dict[str, tuple[str, ExecutionResult]] = {}
        self._lock = Lock()
        self.call_count = 0
        self.send_attempt_count = 0
        self.duplicate_send_count = 0
        self.real_platform_call_count = 0
        self.customer_message_send_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        del command
        raise ExecutionBoundaryDenied(
            "FakePDDExecutor requires a worker-owned execution lease"
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
            return self._denied("PDD_SANDBOX_EXECUTION_CONTEXT_MISMATCH")
        try:
            authorized = self._authorization_service.issue(
                execution_id=context.execution_id,
                worker_id=context.worker_id,
                execution_lease_token=context.lease_token,
            )
            self._authorization_service.verify(authorized)
        except ExecutionBoundaryDenied:
            return self._denied("PDD_SANDBOX_AUTHORIZATION_DENIED")
        if (
            authorized.authorization.decision_id != command.decision_id
            or authorized.authorization.approval_id != context.approval_id
            or authorized.authorization.approved_by != context.approved_by
            or authorized.message.content != command.proposed_content
            or authorized.message.idempotency_key != command.idempotency_key
        ):
            return self._denied("PDD_SANDBOX_AUTHORIZATION_MISMATCH")
        return self.send_message(authorized)

    def send_message(self, command: AuthorizedOutboundMessage) -> ExecutionResult:
        """Simulate SEND_MESSAGE from a verified capability, never from bare text."""

        if not isinstance(command, AuthorizedOutboundMessage):
            raise ExecutionBoundaryDenied(
                "FakePDDExecutor rejects bare outbound content"
            )
        self._authorization_service.verify(command)
        fingerprint = self._fingerprint(command)
        key = command.message.idempotency_key
        with self._lock:
            replay = self._results.get(key)
            if replay is not None:
                previous_fingerprint, previous_result = replay
                if previous_fingerprint != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "PDD sandbox idempotency key is bound to another command"
                    )
                self.duplicate_send_count += 1
                return previous_result

            self.send_attempt_count += 1
            result = self._result(command)
            self._results[key] = (fingerprint, result)
            return result

    def _result(self, command: AuthorizedOutboundMessage) -> ExecutionResult:
        outcome = ReceiptOutcome(self.mode.value)
        error_code = {
            FakePDDExecutionMode.SUCCESS: None,
            FakePDDExecutionMode.FAILED: "PDD_SANDBOX_FAKE_SEND_FAILED",
            FakePDDExecutionMode.UNKNOWN: "PDD_SANDBOX_FAKE_SEND_UNKNOWN",
        }[self.mode]
        authorization = command.authorization
        return ExecutionResult(
            outcome=outcome,
            external_reference=(
                f"pdd-sandbox-operation-{authorization.execution_id}"
                if outcome is ReceiptOutcome.SUCCESS
                else None
            ),
            error_code=error_code,
            details={
                "mode": "PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX",
                # Keep the frozen/shared receipt vocabulary while preserving
                # the stronger internal fact that this is the offline PDD
                # simulation used by release acceptance.
                "transport_kind": "SYNTHETIC_PDD",
                "evidence_transport_kind": "SIMULATED_PDD",
                "simulation_only": True,
                "external_side_effect": False,
                "decision_id": authorization.decision_id,
                "approval_id": authorization.approval_id,
                "authorization_id": authorization.authorization_id,
                "approved_by": authorization.approved_by,
                "human_approved": True,
                "lease_validated": True,
                "authorization_validated": True,
                "real_platform_called": False,
                "customer_message_sent": False,
                "automatic_approval": False,
                "automatic_reply": False,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
                "automatic_retry_allowed": False,
                "reconciliation_required": outcome is ReceiptOutcome.UNKNOWN,
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX",
                "transport_kind": "SYNTHETIC_PDD",
                "evidence_transport_kind": "SIMULATED_PDD",
                "simulation_only": True,
                "external_side_effect": False,
                "human_approved": False,
                "lease_validated": False,
                "authorization_validated": False,
                "real_platform_called": False,
                "customer_message_sent": False,
                "automatic_approval": False,
                "automatic_reply": False,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
                "automatic_retry_allowed": False,
            },
        )

    @staticmethod
    def _fingerprint(command: AuthorizedOutboundMessage) -> str:
        authorization = command.authorization
        payload = {
            "message": command.message.model_dump(mode="json"),
            "decision_id": authorization.decision_id,
            "approval_id": authorization.approval_id,
            "execution_id": authorization.execution_id,
            "approved_by": authorization.approved_by,
            "operation": authorization.operation,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


class PDDHumanApprovalExecutionSandbox:
    """Manual-only orchestration over the durable execution ledger."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        worker_id: str,
        mode: FakePDDExecutionMode = FakePDDExecutionMode.SUCCESS,
        lease_duration: timedelta = timedelta(seconds=30),
        authorization_ttl: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("PDD approval sandbox worker_id is required")
        self._uow_factory = uow_factory
        self._clock = clock
        self._coordinator = ExecutionCoordinator(uow_factory, ApprovalPolicy())
        self.authorization_service = LedgerExecutionAuthorizationService(
            uow_factory,
            authorization_ttl=authorization_ttl,
            clock=clock,
        )
        self.executor = FakePDDExecutor(
            self.authorization_service,
            mode,
            clock=clock,
        )
        self._worker = ExecutionWorker(
            uow_factory,
            self.executor,
            worker_id.strip(),
            lease_duration=lease_duration,
            clock=clock,
        )
        self._lock = RLock()

    def approve(
        self,
        decision_id: str,
        *,
        operator: str,
    ) -> ExecutionEnqueued:
        """Create or replay one explicit human Approval and pending Execution."""

        with self._lock:
            return self._coordinator.approve_and_enqueue(decision_id, operator)

    def execute_approved(self, execution_id: str) -> PDDApprovalExecutionResult:
        """Execute one exact approved item; there is no automatic queue drain."""

        with self._lock:
            worker_result = self._worker.run_execution(execution_id)
            if worker_result is not None:
                trace = self.trace(execution_id)
                return self._result_from_trace(
                    trace,
                    adapter_called=worker_result.adapter_called,
                    replayed=False,
                )

            trace = self.trace(execution_id)
            if trace.receipt_id is not None and trace.receipt_status is not None:
                return self._result_from_trace(
                    trace,
                    adapter_called=False,
                    replayed=True,
                )
            raise PDDApprovalSandboxError(
                "execution is not pending or requires manual reconciliation",
                error_code="PDD_SANDBOX_EXECUTION_NOT_CLAIMABLE",
            )

    def execute_decision(self, decision_id: str) -> PDDApprovalExecutionResult:
        """Resolve an explicitly approved Decision; never creates an Approval."""

        with self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            approval = repo.get_approval_for_decision(decision_id)
            execution = repo.get_execution_for_decision(decision_id)
        if (
            decision.state is not DecisionState.APPROVED
            or approval is None
            or approval.state is not ApprovalState.APPROVED
            or execution is None
            or execution.approval_id != approval.approval_id
        ):
            raise PDDApprovalSandboxError(
                "explicit human Approval is required before sandbox execution",
                error_code="PDD_SANDBOX_APPROVAL_REQUIRED",
            )
        return self.execute_approved(execution.execution_id)

    def trace(self, execution_id: str) -> PDDApprovalExecutionTrace:
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            execution = repo.get_execution(execution_id)
            decision = repo.get_decision(execution.decision_id)
            approval = repo.get_approval_for_decision(decision.decision_id)
            if approval is None or approval.approval_id != execution.approval_id:
                raise PDDApprovalSandboxError(
                    "execution approval trace is missing",
                    error_code="PDD_SANDBOX_APPROVAL_TRACE_MISSING",
                )
            receipt = repo.get_receipt_for_execution(execution_id)
        authorization_id = None
        if receipt is not None:
            raw_authorization = receipt.details.get("authorization_id")
            if isinstance(raw_authorization, str):
                authorization_id = raw_authorization
        return PDDApprovalExecutionTrace(
            message_id=decision.message_id,
            decision_id=decision.decision_id,
            approval_id=approval.approval_id,
            execution_id=execution.execution_id,
            receipt_id=(receipt.receipt_id if receipt is not None else None),
            authorization_id=authorization_id,
            decision_state=decision.state,
            approval_state=approval.state,
            execution_state=execution.state,
            receipt_status=(receipt.outcome if receipt is not None else None),
            automatic_retry_allowed=False,
        )

    def safety_snapshot(self) -> PDDApprovalSandboxSafetySnapshot:
        if (
            self.executor.real_platform_call_count != 0
            or self.executor.customer_message_send_count != 0
            or self.executor.customer_message_sent
        ):
            raise PDDApprovalSandboxError(
                "fake PDD executor crossed the sandbox boundary",
                error_code="PDD_SANDBOX_ISOLATION_BREACHED",
            )
        return PDDApprovalSandboxSafetySnapshot()

    def _result_from_trace(
        self,
        trace: PDDApprovalExecutionTrace,
        *,
        adapter_called: bool,
        replayed: bool,
    ) -> PDDApprovalExecutionResult:
        if trace.receipt_id is None or trace.receipt_status is None:
            raise PDDApprovalSandboxError(
                "terminal sandbox execution has no receipt",
                error_code="PDD_SANDBOX_RECEIPT_MISSING",
            )
        return PDDApprovalExecutionResult(
            trace=trace,
            receipt_id=trace.receipt_id,
            receipt_status=trace.receipt_status,
            adapter_called=adapter_called,
            replayed=replayed,
            safety=self.safety_snapshot(),
        )


__all__ = [
    "PDD_HUMAN_APPROVAL_EXECUTION_SANDBOX_VERSION",
    "FakePDDExecutionMode",
    "FakePDDExecutor",
    "PDDApprovalExecutionResult",
    "PDDApprovalExecutionTrace",
    "PDDApprovalSandboxError",
    "PDDApprovalSandboxSafetySnapshot",
    "PDDHumanApprovalExecutionSandbox",
]
