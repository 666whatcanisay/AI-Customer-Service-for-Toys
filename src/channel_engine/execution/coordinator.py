from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError

from channel_engine.control.gate import (
    ExecutionControlGate,
    PersistentExecutionControlGate,
)
from channel_engine.models import (
    Approval,
    ApprovalState,
    DecisionState,
    Event,
    EventType,
    Execution,
    ExecutionState,
    transition_decision,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork


class ExecutionEnqueued(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    approval_id: str
    execution_id: str
    execution_state: ExecutionState
    idempotency_key: str


class RejectionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    approval_id: str
    decision_state: DecisionState


class ExecutionCoordinator:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        policy: ApprovalPolicy,
        control_gate: ExecutionControlGate | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._control_gate = control_gate or PersistentExecutionControlGate()

    def approve_and_enqueue(
        self, decision_id: str, approved_by: str
    ) -> ExecutionEnqueued:
        if not approved_by.strip():
            raise ValueError("approved_by is required")
        try:
            return self._approve_and_enqueue_once(decision_id, approved_by.strip())
        except IntegrityError:
            # A concurrent identical approval can win the unique decision/approval/
            # execution constraints. Read back its durable result as the replay.
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                decision = repo.get_decision(decision_id)
                approval = repo.get_approval_for_decision(decision_id)
                execution = repo.get_execution_for_decision(decision_id)
                if (
                    decision.state is DecisionState.APPROVED
                    and approval is not None
                    and approval.state is ApprovalState.APPROVED
                    and execution is not None
                ):
                    return ExecutionEnqueued(
                        decision_id=decision_id,
                        approval_id=approval.approval_id,
                        execution_id=execution.execution_id,
                        execution_state=execution.state,
                        idempotency_key=execution.idempotency_key,
                    )
            raise

    def _approve_and_enqueue_once(
        self, decision_id: str, approved_by: str
    ) -> ExecutionEnqueued:
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            if decision.state is DecisionState.APPROVED:
                existing_approval = repo.get_approval_for_decision(decision_id)
                existing_execution = repo.get_execution_for_decision(decision_id)
                if existing_approval is None or existing_execution is None:
                    raise ValueError(
                        "approved decision has no execution; manual reconciliation required"
                    )
                return ExecutionEnqueued(
                    decision_id=decision_id,
                    approval_id=existing_approval.approval_id,
                    execution_id=existing_execution.execution_id,
                    execution_state=existing_execution.state,
                    idempotency_key=existing_execution.idempotency_key,
                )

            self._control_gate.assert_new_execution_allowed(uow)

            decision = transition_decision(decision, DecisionState.APPROVED)
            approval = Approval(
                decision_id=decision_id,
                state=ApprovalState.APPROVED,
                decided_by=approved_by,
                reason="HUMAN_APPROVED_EXECUTION_QUEUE",
                decided_at=utc_now(),
            )
            execution = Execution(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                idempotency_key=f"execute-{decision_id}",
            )
            self._policy.assert_can_execute(decision, approval)
            repo.save_decision(decision)
            repo.save_approval(approval)
            repo.save_execution(execution)
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision_id,
                    event_type=EventType.DECISION_APPROVED,
                    payload={
                        "approval_id": approval.approval_id,
                        "execution_id": execution.execution_id,
                        "approved_by": approved_by,
                    },
                    correlation_id=decision.message_id,
                )
            )

            return ExecutionEnqueued(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                execution_id=execution.execution_id,
                execution_state=execution.state,
                idempotency_key=execution.idempotency_key,
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
                    payload={
                        "approval_id": approval.approval_id,
                        "rejected_by": rejected_by.strip(),
                    },
                    correlation_id=decision.message_id,
                )
            )
            return RejectionOutcome(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                decision_state=decision.state,
            )
