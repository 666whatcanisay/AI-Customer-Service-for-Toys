from __future__ import annotations

import pytest

from channel_engine.models import (
    Decision,
    DecisionAction,
    DecisionState,
    Execution,
    ExecutionState,
    InvalidStateTransition,
    Message,
    MessageState,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
    transition_decision,
    transition_execution,
    transition_message,
)


def test_message_state_machine() -> None:
    message = Message(
        conversation_id="conv-1",
        external_message_id="external-1",
        content="hello",
    )
    processing = transition_message(message, MessageState.PROCESSING)
    completed = transition_message(processing, MessageState.COMPLETED)

    assert completed.state is MessageState.COMPLETED
    with pytest.raises(InvalidStateTransition):
        transition_message(completed, MessageState.PROCESSING)


def test_decision_state_machine_requires_waiting_approval() -> None:
    decision = Decision(
        conversation_id="conv-1",
        message_id="msg-1",
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="proposal",
        gateway_version="fake.v1",
    )
    with pytest.raises(InvalidStateTransition):
        transition_decision(decision, DecisionState.APPROVED)

    waiting = transition_decision(decision, DecisionState.WAITING_APPROVAL)
    approved = transition_decision(waiting, DecisionState.APPROVED)
    assert approved.state is DecisionState.APPROVED


def test_execution_unknown_is_terminal_and_not_auto_retryable() -> None:
    execution = Execution(
        decision_id="decision-1",
        approval_id="approval-1",
        idempotency_key="execute-1",
    )
    running = transition_execution(execution, ExecutionState.RUNNING)
    unknown = transition_execution(running, ExecutionState.UNKNOWN)

    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(unknown)
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        transition_execution(unknown, ExecutionState.RUNNING)


@pytest.mark.parametrize(
    "terminal",
    [ExecutionState.SUCCESS, ExecutionState.FAILED, ExecutionState.UNKNOWN],
)
def test_execution_terminal_states_cannot_transition(terminal: ExecutionState) -> None:
    execution = Execution(
        decision_id="decision-1",
        approval_id="approval-1",
        idempotency_key="execute-1",
    )
    terminal_execution = transition_execution(
        transition_execution(execution, ExecutionState.RUNNING), terminal
    )
    expected_error = (
        UnknownExecutionRequiresReconciliation
        if terminal is ExecutionState.UNKNOWN
        else InvalidStateTransition
    )
    with pytest.raises(expected_error):
        transition_execution(terminal_execution, ExecutionState.RUNNING)
