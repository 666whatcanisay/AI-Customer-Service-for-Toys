from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionQueue,
    FakePDDExecutionMode,
    PDDApprovalSandboxError,
    PDDHumanApprovalExecutionSandbox,
)
from channel_engine.models import (
    ApprovalState,
    DecisionState,
    EventType,
    ExecutionState,
    Receipt,
    ReceiptOutcome,
)
from channel_engine.pdd_adapter import (
    FakePDDMessageReader,
    PDDCapturedMessage,
    PDDMessageObservationRuntime,
)
from channel_engine.storage.orm import ApprovalRow, ExecutionRow, ReceiptRow


NOW = datetime(2026, 8, 5, 13, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def waiting_decision(foundation, suffix: str):
    reader = FakePDDMessageReader(
        store_id="pdd-approval-sandbox-store",
        clock=lambda: NOW,
    )
    reader.enqueue(
        PDDCapturedMessage(
            store_id="pdd-approval-sandbox-store",
            conversation_id=f"pdd-approval-conversation-{suffix}",
            external_message_id=f"pdd-approval-message-{suffix}",
            sender="customer",
            content=f"Synthetic sandbox question {suffix}",
            timestamp=NOW,
            captured_at=NOW,
        )
    )
    runtime = PDDMessageObservationRuntime(
        reader,
        ConversationService(foundation["uow_factory"], foundation["gateway"]),
        foundation["uow_factory"],
        clock=lambda: NOW,
    )
    evidence = runtime.observe_once()[0]
    assert evidence.decision_state == "WAITING_APPROVAL"
    return evidence


def row_counts(foundation) -> tuple[int, int, int]:
    with foundation["session_factory"]() as session:
        return (
            len(list(session.scalars(select(ApprovalRow)))),
            len(list(session.scalars(select(ExecutionRow)))),
            len(list(session.scalars(select(ReceiptRow)))),
        )


def outbox_event_types(foundation) -> list[str]:
    with foundation["uow_factory"]() as uow:
        outbox = uow.require_repository().list_outbox()
    return [str(item.payload["event_type"]) for item in outbox]


def test_human_approval_lease_fake_execution_receipt_and_trace_close_the_loop(
    foundation,
) -> None:
    observed = waiting_decision(foundation, "success")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-approval-success-worker",
        clock=lambda: NOW,
    )

    enqueued = sandbox.approve(
        observed.decision_id,
        operator="sandbox-human-operator",
    )
    result = sandbox.execute_decision(observed.decision_id)

    assert enqueued.execution_state is ExecutionState.PENDING
    assert result.receipt_status is ReceiptOutcome.SUCCESS
    assert result.trace.message_id == observed.message_id
    assert result.trace.decision_id == observed.decision_id
    assert result.trace.approval_id == enqueued.approval_id
    assert result.trace.execution_id == enqueued.execution_id
    assert result.trace.receipt_id == result.receipt_id
    assert result.trace.decision_state is DecisionState.APPROVED
    assert result.trace.approval_state is ApprovalState.APPROVED
    assert result.trace.execution_state is ExecutionState.SUCCESS
    assert result.safety.customer_message_sent is False
    assert sandbox.executor.send_attempt_count == 1
    assert sandbox.executor.real_platform_call_count == 0
    assert sandbox.executor.customer_message_send_count == 0

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
    assert receipt is not None
    assert receipt.details["decision_id"] == observed.decision_id
    assert receipt.details["approval_id"] == enqueued.approval_id
    assert receipt.details["authorization_id"] == result.trace.authorization_id
    assert receipt.details["human_approved"] is True
    assert receipt.details["lease_validated"] is True
    assert receipt.details["authorization_validated"] is True
    assert receipt.details["customer_message_sent"] is False
    assert receipt.details["real_platform_called"] is False

    types = outbox_event_types(foundation)
    assert EventType.DECISION_APPROVED.value in types
    assert EventType.EXECUTION_STARTED.value in types
    assert EventType.EXECUTION_SUCCEEDED.value in types
    assert EventType.RECEIPT_RECORDED.value in types

    with pytest.raises(ValidationError, match="frozen"):
        receipt.outcome = ReceiptOutcome.UNKNOWN  # type: ignore[misc]
    with pytest.raises(ValueError, match="immutable"):
        with foundation["uow_factory"]() as uow:
            uow.require_repository().append_receipt(
                Receipt(
                    execution_id=enqueued.execution_id,
                    outcome=ReceiptOutcome.FAILED,
                    details={"reason": "attempted overwrite"},
                )
            )


def test_missing_approval_is_rejected_before_execution_or_receipt(foundation) -> None:
    observed = waiting_decision(foundation, "missing-approval")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-approval-missing-worker",
        clock=lambda: NOW,
    )

    with pytest.raises(PDDApprovalSandboxError) as raised:
        sandbox.execute_decision(observed.decision_id)

    assert raised.value.error_code == "PDD_SANDBOX_APPROVAL_REQUIRED"
    assert sandbox.executor.call_count == 0
    assert sandbox.executor.send_attempt_count == 0
    assert row_counts(foundation) == (0, 0, 0)


def test_duplicate_human_approval_is_idempotent(foundation) -> None:
    observed = waiting_decision(foundation, "duplicate-approval")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-duplicate-approval-worker",
        clock=lambda: NOW,
    )

    first = sandbox.approve(observed.decision_id, operator="human-operator-01")
    replay = sandbox.approve(observed.decision_id, operator="human-operator-01")

    assert replay == first
    assert row_counts(foundation) == (1, 1, 0)
    assert sandbox.executor.call_count == 0


def test_expired_lease_is_denied_before_fake_send(foundation) -> None:
    clock = MutableClock(NOW)
    observed = waiting_decision(foundation, "expired-lease")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-expired-lease-worker",
        lease_duration=timedelta(seconds=1),
        authorization_ttl=timedelta(seconds=1),
        clock=clock,
    )
    enqueued = sandbox.approve(
        observed.decision_id,
        operator="lease-human-operator",
    )
    lease = ExecutionQueue(
        foundation["uow_factory"],
        "pdd-expired-lease-worker",
        lease_duration=timedelta(seconds=1),
        clock=clock,
    ).claim_exact(enqueued.execution_id)
    assert lease is not None
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        decision = repo.get_decision(observed.decision_id)
        approval = repo.get_approval_for_decision(observed.decision_id)
    assert approval is not None
    clock.now = NOW + timedelta(seconds=2)

    result = sandbox.executor.execute_claimed(
        ExecutionCommand(
            execution_id=enqueued.execution_id,
            decision_id=observed.decision_id,
            proposed_content=decision.proposed_content,
            idempotency_key=enqueued.idempotency_key,
        ),
        ClaimedExecutionContext(
            execution_id=enqueued.execution_id,
            decision_id=observed.decision_id,
            approval_id=enqueued.approval_id,
            approved_by=approval.decided_by or "",
            worker_id=lease.worker_id,
            lease_token=lease.lease_token,
            lease_expires_at=lease.lease_expires_at,
        ),
    )

    assert result.outcome is ReceiptOutcome.FAILED
    assert result.error_code == "PDD_SANDBOX_AUTHORIZATION_DENIED"
    assert sandbox.executor.send_attempt_count == 0
    assert sandbox.executor.real_platform_call_count == 0
    assert row_counts(foundation) == (1, 1, 0)


def test_failed_execution_records_one_failed_receipt(foundation) -> None:
    observed = waiting_decision(foundation, "failed")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-failed-sandbox-worker",
        mode=FakePDDExecutionMode.FAILED,
        clock=lambda: NOW,
    )
    sandbox.approve(observed.decision_id, operator="failure-human-operator")

    result = sandbox.execute_decision(observed.decision_id)

    assert result.trace.execution_state is ExecutionState.FAILED
    assert result.receipt_status is ReceiptOutcome.FAILED
    assert sandbox.executor.send_attempt_count == 1
    assert row_counts(foundation) == (1, 1, 1)
    assert EventType.EXECUTION_FAILED.value in outbox_event_types(foundation)


def test_unknown_execution_replays_receipt_and_never_retries(foundation) -> None:
    observed = waiting_decision(foundation, "unknown")
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-unknown-sandbox-worker",
        mode=FakePDDExecutionMode.UNKNOWN,
        clock=lambda: NOW,
    )
    sandbox.approve(observed.decision_id, operator="unknown-human-operator")

    first = sandbox.execute_decision(observed.decision_id)
    replay = sandbox.execute_decision(observed.decision_id)

    assert first.trace.execution_state is ExecutionState.UNKNOWN
    assert first.receipt_status is ReceiptOutcome.UNKNOWN
    assert first.trace.automatic_retry_allowed is False
    assert replay.replayed is True
    assert replay.adapter_called is False
    assert replay.receipt_id == first.receipt_id
    assert sandbox.executor.call_count == 1
    assert sandbox.executor.send_attempt_count == 1
    assert row_counts(foundation) == (1, 1, 1)
    assert EventType.EXECUTION_UNKNOWN.value in outbox_event_types(foundation)
