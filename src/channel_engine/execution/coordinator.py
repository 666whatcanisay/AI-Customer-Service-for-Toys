from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from channel_engine.models import (
    Approval,
    ApprovalState,
    DecisionState,
    Event,
    EventType,
    Execution,
    ExecutionState,
    Receipt,
    ReceiptOutcome,
    transition_decision,
    transition_execution,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork

from .fake_executor import ChannelExecutor, ExecutionCommand


class ExecutionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    approval_id: str
    execution_id: str
    execution_state: ExecutionState
    receipt_id: str
    receipt_outcome: ReceiptOutcome


class RejectionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    approval_id: str
    decision_state: DecisionState


class ExecutionCoordinator:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        executor: ChannelExecutor,
        policy: ApprovalPolicy,
    ) -> None:
        self._uow_factory = uow_factory
        self._executor = executor
        self._policy = policy

    def approve_and_execute(self, decision_id: str, approved_by: str) -> ExecutionOutcome:
        if not approved_by.strip():
            raise ValueError("approved_by is required")

        with self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            decision = transition_decision(decision, DecisionState.APPROVED)
            approval = Approval(
                decision_id=decision_id,
                state=ApprovalState.APPROVED,
                decided_by=approved_by.strip(),
                reason="HUMAN_APPROVED_FAKE_EXECUTION",
                decided_at=utc_now(),
            )
            repo.save_decision(decision)
            repo.save_approval(approval)
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision_id,
                    event_type=EventType.DECISION_APPROVED,
                    payload={"approval_id": approval.approval_id, "approved_by": approved_by.strip()},
                    correlation_id=decision.message_id,
                )
            )

            execution = Execution(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                idempotency_key=f"execute-{decision_id}",
            )
            self._policy.assert_can_execute(decision, approval)
            execution = transition_execution(execution, ExecutionState.RUNNING)
            repo.append_event(
                Event(
                    aggregate_type="Execution",
                    aggregate_id=execution.execution_id,
                    event_type=EventType.EXECUTION_STARTED,
                    payload={"decision_id": decision_id},
                    correlation_id=decision.message_id,
                )
            )

            result = self._executor.execute(
                ExecutionCommand(
                    execution_id=execution.execution_id,
                    decision_id=decision_id,
                    proposed_content=decision.proposed_content,
                    idempotency_key=execution.idempotency_key,
                )
            )
            target_state, event_type = {
                ReceiptOutcome.SUCCESS: (
                    ExecutionState.SUCCESS,
                    EventType.EXECUTION_SUCCEEDED,
                ),
                ReceiptOutcome.FAILED: (ExecutionState.FAILED, EventType.EXECUTION_FAILED),
                ReceiptOutcome.UNKNOWN: (ExecutionState.UNKNOWN, EventType.EXECUTION_UNKNOWN),
            }[result.outcome]
            execution = transition_execution(execution, target_state)
            repo.save_execution(execution)
            receipt = Receipt(
                execution_id=execution.execution_id,
                outcome=result.outcome,
                external_reference=result.external_reference,
                details=result.details,
            )
            repo.append_receipt(receipt)
            repo.append_event(
                Event(
                    aggregate_type="Execution",
                    aggregate_id=execution.execution_id,
                    event_type=event_type,
                    payload={"receipt_id": receipt.receipt_id, "outcome": receipt.outcome.value},
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

            return ExecutionOutcome(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                execution_id=execution.execution_id,
                execution_state=execution.state,
                receipt_id=receipt.receipt_id,
                receipt_outcome=receipt.outcome,
            )

    def reject(self, decision_id: str, rejected_by: str, reason: str) -> RejectionOutcome:
        if not rejected_by.strip() or not reason.strip():
            raise ValueError("rejected_by and reason are required")
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            decision = transition_decision(decision, DecisionState.REJECTED)
            approval = Approval(
                decision_id=decision_id,
                state=ApprovalState.REJECTED,
                decided_by=rejected_by.strip(),
                reason=reason.strip(),
                decided_at=utc_now(),
            )
            repo.save_decision(decision)
            repo.save_approval(approval)
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision_id,
                    event_type=EventType.DECISION_REJECTED,
                    payload={"approval_id": approval.approval_id, "rejected_by": rejected_by.strip()},
                    correlation_id=decision.message_id,
                )
            )
            return RejectionOutcome(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                decision_state=decision.state,
            )
