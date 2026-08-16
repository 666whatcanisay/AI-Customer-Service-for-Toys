from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from .entities import Decision, Execution, Message, utc_now
from .enums import DecisionState, ExecutionState, MessageState


class InvalidStateTransition(ValueError):
    pass


class UnknownExecutionRequiresReconciliation(RuntimeError):
    pass


StateT = TypeVar("StateT", bound=StrEnum)


def _require_transition(current: StateT, target: StateT, allowed: dict[StateT, set[StateT]]) -> None:
    if target not in allowed.get(current, set()):
        raise InvalidStateTransition(f"invalid transition: {current} -> {target}")


MESSAGE_TRANSITIONS = {
    MessageState.RECEIVED: {MessageState.PROCESSING},
    MessageState.PROCESSING: {MessageState.COMPLETED, MessageState.FAILED},
    MessageState.COMPLETED: set(),
    MessageState.FAILED: set(),
}

DECISION_TRANSITIONS = {
    DecisionState.CREATED: {DecisionState.WAITING_APPROVAL},
    DecisionState.WAITING_APPROVAL: {DecisionState.APPROVED, DecisionState.REJECTED},
    DecisionState.APPROVED: set(),
    DecisionState.REJECTED: set(),
}

EXECUTION_TRANSITIONS = {
    ExecutionState.PENDING: {ExecutionState.RUNNING},
    ExecutionState.RUNNING: {
        ExecutionState.SUCCESS,
        ExecutionState.FAILED,
        ExecutionState.UNKNOWN,
    },
    ExecutionState.SUCCESS: set(),
    ExecutionState.FAILED: set(),
    ExecutionState.UNKNOWN: set(),
}


def transition_message(message: Message, target: MessageState, now: datetime | None = None) -> Message:
    _require_transition(message.state, target, MESSAGE_TRANSITIONS)
    return message.model_copy(update={"state": target, "updated_at": now or utc_now()})


def transition_decision(
    decision: Decision, target: DecisionState, now: datetime | None = None
) -> Decision:
    _require_transition(decision.state, target, DECISION_TRANSITIONS)
    return decision.model_copy(update={"state": target, "updated_at": now or utc_now()})


def transition_execution(
    execution: Execution, target: ExecutionState, now: datetime | None = None
) -> Execution:
    if execution.state is ExecutionState.UNKNOWN:
        raise UnknownExecutionRequiresReconciliation(
            "UNKNOWN execution cannot be retried automatically; reconcile external state first"
        )
    _require_transition(execution.state, target, EXECUTION_TRANSITIONS)
    timestamp = now or utc_now()
    update: dict[str, object] = {"state": target, "updated_at": timestamp}
    if target is ExecutionState.RUNNING:
        update["started_at"] = timestamp
    if target in {ExecutionState.SUCCESS, ExecutionState.FAILED, ExecutionState.UNKNOWN}:
        update["completed_at"] = timestamp
    return execution.model_copy(update=update)


def assert_not_automatic_retry(execution: Execution) -> None:
    if execution.state is ExecutionState.UNKNOWN:
        raise UnknownExecutionRequiresReconciliation(
            "UNKNOWN execution requires manual reconciliation"
        )
