from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from channel_engine.control.gate import ExecutionControlBlocked, ExecutionControlGate
from channel_engine.execution import ExecutionEnqueued
from channel_engine.models import (
    Approval,
    ApprovalState,
    DecisionState,
    Event,
    EventType,
    Execution,
    transition_decision,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork

from .models import PilotStoreConfig
from .persistence import PilotPersistenceRepository


class PilotApprovalError(RuntimeError):
    error_code = "PILOT_APPROVAL_DENIED"


class PilotApprovalService:
    """Creates Approval, Execution and Pilot send reservation atomically."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        policy: ApprovalPolicy,
        control_gate: ExecutionControlGate,
        config: PilotStoreConfig,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._control_gate = control_gate
        self._config = config
        self._lock = RLock()

    def approve_and_reserve(
        self,
        decision_id: str,
        approved_by: str,
    ) -> ExecutionEnqueued:
        operator = approved_by.strip()
        if not operator:
            raise PilotApprovalError("Pilot approval requires an operator")
        if not self._config.approval_required or self._config.auto_reply:
            raise PilotApprovalError("Pilot safety configuration is invalid")

        with self._lock, self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            if decision.state is DecisionState.APPROVED:
                approval = repo.get_approval_for_decision(decision_id)
                execution = repo.get_execution_for_decision(decision_id)
                if approval is None or execution is None:
                    raise PilotApprovalError(
                        "approved Pilot Decision requires manual reconciliation"
                    )
                reservation = PilotPersistenceRepository(uow).get_reservation(
                    execution.execution_id
                )
                if reservation is None:
                    raise PilotApprovalError(
                        "approved Pilot Execution has no send reservation"
                    )
                return ExecutionEnqueued(
                    decision_id=decision_id,
                    approval_id=approval.approval_id,
                    execution_id=execution.execution_id,
                    execution_state=execution.state,
                    idempotency_key=execution.idempotency_key,
                )

            try:
                self._control_gate.assert_new_execution_allowed(uow)
            except ExecutionControlBlocked as exc:
                raise PilotApprovalError(
                    "Pilot Execution control gate denied approval"
                ) from exc
            decision = transition_decision(decision, DecisionState.APPROVED)
            approval = Approval(
                decision_id=decision_id,
                state=ApprovalState.APPROVED,
                decided_by=operator,
                reason="PILOT_HUMAN_APPROVED_EXECUTION",
                decided_at=utc_now(),
            )
            execution = Execution(
                decision_id=decision_id,
                approval_id=approval.approval_id,
                idempotency_key=f"execute-{decision_id}",
            )
            self._policy.assert_can_execute(decision, approval)
            conversation = repo.get_conversation(decision.conversation_id)

            repo.save_decision(decision)
            repo.save_approval(approval)
            repo.save_execution(execution)
            PilotPersistenceRepository(uow).reserve_execution(
                execution_id=execution.execution_id,
                store_id=self._config.store_id,
                conversation_id=conversation.external_ref,
                send_limit=self._config.send_limit,
                now=utc_now(),
            )
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision_id,
                    event_type=EventType.DECISION_APPROVED,
                    payload={
                        "approval_id": approval.approval_id,
                        "execution_id": execution.execution_id,
                        "approved_by": operator,
                        "mode": "PDD_SINGLE_STORE_PILOT",
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


__all__ = ["PilotApprovalError", "PilotApprovalService"]
