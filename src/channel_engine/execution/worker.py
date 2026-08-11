from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event as StopEvent

from pydantic import BaseModel, ConfigDict

from channel_engine.control.gate import ExecutionControlGate
from channel_engine.models import (
    Event,
    EventType,
    ExecutionState,
    Receipt,
    ReceiptOutcome,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy, ApprovalRequired
from channel_engine.storage import SqlAlchemyUnitOfWork

from .fake_executor import (
    AdapterOutcomeUnknown,
    ClaimedExecutionAdapter,
    ClaimedExecutionContext,
    ExecutionAdapter,
    ExecutionCommand,
    ExecutionResult,
)
from .queue import ExecutionLease, ExecutionQueue, LeaseLost
from .ownership import WorkerOwnershipRegistry
from .receipt_facts import unknown_receipt_details


class WorkerRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    execution_state: ExecutionState
    receipt_id: str | None
    receipt_outcome: ReceiptOutcome | None
    adapter_called: bool
    lease_lost: bool = False


class ExecutionWorker:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        adapter: ExecutionAdapter,
        worker_id: str,
        *,
        policy: ApprovalPolicy | None = None,
        lease_duration: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = utc_now,
        control_gate: ExecutionControlGate | None = None,
        on_loop_started: Callable[[], object] | None = None,
        on_loop_stopped: Callable[[], object] | None = None,
        ownership_registry: WorkerOwnershipRegistry | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter = adapter
        self._policy = policy or ApprovalPolicy()
        self._clock = clock
        self._on_loop_started = on_loop_started
        self._on_loop_stopped = on_loop_stopped
        self._ownership_registry = ownership_registry
        self.queue = ExecutionQueue(
            uow_factory,
            worker_id,
            lease_duration=lease_duration,
            clock=clock,
            control_gate=control_gate,
        )

    def claim_next(self) -> ExecutionLease | None:
        if self._ownership_registry is not None:
            self._ownership_registry.ensure_owned()
        return self.queue.claim()

    def process_claim(self, lease: ExecutionLease) -> WorkerRunResult:
        lease = self.queue.renew(lease)
        adapter_called = False
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            execution = repo.get_execution(lease.execution.execution_id)
            decision = repo.get_decision(execution.decision_id)
            approval = repo.get_approval_for_decision(execution.decision_id)

        if approval is None:
            result = ExecutionResult(
                outcome=ReceiptOutcome.FAILED,
                error_code="APPROVAL_MISSING",
                details={"mode": "POLICY", "reason": "approval record is missing"},
            )
        else:
            try:
                self._policy.assert_can_execute(decision, approval)
            except ApprovalRequired as exc:
                result = ExecutionResult(
                    outcome=ReceiptOutcome.FAILED,
                    error_code="APPROVAL_REQUIRED",
                    details={"mode": "POLICY", "reason": str(exc)},
                )
            else:
                command = ExecutionCommand(
                    execution_id=execution.execution_id,
                    decision_id=execution.decision_id,
                    proposed_content=decision.proposed_content,
                    idempotency_key=execution.idempotency_key,
                )
                try:
                    adapter_called = True
                    if isinstance(self._adapter, ClaimedExecutionAdapter):
                        result = self._adapter.execute_claimed(
                            command,
                            ClaimedExecutionContext(
                                execution_id=execution.execution_id,
                                decision_id=decision.decision_id,
                                approval_id=approval.approval_id,
                                approved_by=approval.decided_by,
                                worker_id=lease.worker_id,
                                lease_token=lease.lease_token,
                                lease_expires_at=lease.lease_expires_at,
                            ),
                        )
                    else:
                        result = self._adapter.execute(command)
                except AdapterOutcomeUnknown as exc:
                    result = ExecutionResult(
                        outcome=ReceiptOutcome.UNKNOWN,
                        error_code="ADAPTER_NETWORK_UNKNOWN",
                        details=unknown_receipt_details(
                            {
                                "mode": "EXECUTION_ADAPTER",
                                "reason": str(exc),
                            }
                        ),
                    )
                except Exception as exc:
                    result = ExecutionResult(
                        outcome=ReceiptOutcome.UNKNOWN,
                        error_code="ADAPTER_EXCEPTION_UNKNOWN",
                        details=unknown_receipt_details(
                            {
                                "mode": "EXECUTION_ADAPTER",
                                "reason": type(exc).__name__,
                            }
                        ),
                    )

        return self._finalize(lease, result, adapter_called)

    def run_once(self) -> WorkerRunResult | None:
        lease = self.claim_next()
        if lease is None:
            return None
        return self.process_claim(lease)

    def run_execution(self, execution_id: str) -> WorkerRunResult | None:
        """Run one exact approved Execution for a manual, user-triggered action."""

        if self._ownership_registry is not None:
            self._ownership_registry.ensure_owned()
        lease = self.queue.claim_exact(execution_id)
        if lease is None:
            return None
        return self.process_claim(lease)

    def run_until_idle(self, max_items: int = 100) -> list[WorkerRunResult]:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        results: list[WorkerRunResult] = []
        while len(results) < max_items:
            result = self.run_once()
            if result is None:
                break
            results.append(result)
        return results

    def run_forever(
        self,
        stop_event: StopEvent,
        *,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self._on_loop_started is not None:
            self._on_loop_started()
        try:
            while not stop_event.is_set():
                if self.run_once() is None:
                    stop_event.wait(poll_interval_seconds)
        finally:
            if self._ownership_registry is not None:
                self._ownership_registry.release()
            if self._on_loop_stopped is not None:
                self._on_loop_stopped()

    def _finalize(
        self,
        lease: ExecutionLease,
        result: ExecutionResult,
        adapter_called: bool,
    ) -> WorkerRunResult:
        target_state, event_type = {
            ReceiptOutcome.SUCCESS: (
                ExecutionState.SUCCESS,
                EventType.EXECUTION_SUCCEEDED,
            ),
            ReceiptOutcome.FAILED: (
                ExecutionState.FAILED,
                EventType.EXECUTION_FAILED,
            ),
            ReceiptOutcome.UNKNOWN: (
                ExecutionState.UNKNOWN,
                EventType.EXECUTION_UNKNOWN,
            ),
        }[result.outcome]
        now = self._clock()
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            execution = repo.finish_claimed_execution(
                lease.execution.execution_id,
                lease.worker_id,
                lease.lease_token,
                target_state,
                now,
                result.error_code,
            )
            if execution is None:
                current = repo.get_execution(lease.execution.execution_id)
                receipt = repo.get_receipt_for_execution(current.execution_id)
                return WorkerRunResult(
                    execution_id=current.execution_id,
                    execution_state=current.state,
                    receipt_id=receipt.receipt_id if receipt else None,
                    receipt_outcome=receipt.outcome if receipt else None,
                    adapter_called=adapter_called,
                    lease_lost=True,
                )

            decision = repo.get_decision(execution.decision_id)
            receipt_details = dict(result.details)
            if result.outcome is ReceiptOutcome.UNKNOWN:
                receipt_details = unknown_receipt_details(
                    receipt_details,
                    transport_triggered=receipt_details.get("transport_triggered"),
                )
            receipt = Receipt(
                execution_id=execution.execution_id,
                outcome=result.outcome,
                external_reference=result.external_reference,
                details={
                    **receipt_details,
                    "worker_id": lease.worker_id,
                    "attempt": execution.attempt,
                    "error_code": result.error_code,
                },
                recorded_at=now,
            )
            repo.append_receipt(receipt)
            repo.append_event(
                Event(
                    aggregate_type="Execution",
                    aggregate_id=execution.execution_id,
                    event_type=event_type,
                    payload={
                        "receipt_id": receipt.receipt_id,
                        "outcome": receipt.outcome.value,
                        "error_code": result.error_code,
                    },
                    correlation_id=decision.message_id,
                )
            )
            repo.append_event(
                Event(
                    aggregate_type="Receipt",
                    aggregate_id=receipt.receipt_id,
                    event_type=EventType.RECEIPT_RECORDED,
                    payload={"execution_id": execution.execution_id},
                    correlation_id=decision.message_id,
                )
            )
            return WorkerRunResult(
                execution_id=execution.execution_id,
                execution_state=execution.state,
                receipt_id=receipt.receipt_id,
                receipt_outcome=receipt.outcome,
                adapter_called=adapter_called,
            )


__all__ = ["ExecutionWorker", "LeaseLost", "WorkerRunResult"]
