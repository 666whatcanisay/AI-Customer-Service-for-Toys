from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from channel_engine.channel import ChannelMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionRecovery,
    ExecutionWorker,
    FakeExecutionAdapter,
)
from channel_engine.models import ReceiptOutcome
from channel_engine.observability import (
    StructuredEventStatus,
    StructuredEventType,
    TraceStopReason,
)
from channel_engine.observability.service import ObservabilityService
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage.orm import ObservabilityEventRow


def _intake_and_approve(foundation, suffix: str):
    intake = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    ).receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref=f"ops-conversation-{suffix}",
            external_message_id=f"ops-message-{suffix}",
            text=f"private customer text {suffix}",
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(intake.decision_id, "human-operator")
    return intake, enqueued


def test_complete_flow_has_persistent_events_and_resolvable_trace(foundation) -> None:
    intake, enqueued = _intake_and_approve(foundation, "complete")
    result = ExecutionWorker(
        foundation["uow_factory"],
        FakeExecutionAdapter(),
        "ops-worker",
    ).run_once()
    assert result is not None
    service = ObservabilityService(foundation["uow_factory"])

    trace = service.trace(result.receipt_id)
    types = [event.event_type for event in trace.events]

    assert trace.message_id == intake.message_id
    assert trace.conversation_id == intake.conversation_id
    assert trace.decision_id == intake.decision_id
    assert trace.approval_id == enqueued.approval_id
    assert trace.execution_id == enqueued.execution_id
    assert trace.receipt_id == result.receipt_id
    assert trace.why_stopped is TraceStopReason.COMPLETED
    assert StructuredEventType.MESSAGE_RECEIVED in types
    assert StructuredEventType.MESSAGE_NORMALIZED in types
    assert StructuredEventType.DECISION_REQUEST_SENT in types
    assert StructuredEventType.DECISION_CREATED in types
    assert StructuredEventType.APPROVAL_REQUIRED in types
    assert StructuredEventType.APPROVAL_GRANTED in types
    assert StructuredEventType.EXECUTION_STARTED in types
    assert StructuredEventType.EXECUTION_SUCCESS in types
    assert StructuredEventType.RECEIPT_CREATED in types

    # The operator projection never contains the original customer text or
    # identity-bearing domain payload fields.
    with foundation["session_factory"]() as session:
        rows = session.scalars(select(ObservabilityEventRow)).all()
        serialized = json.dumps(
            [row.metadata_json for row in rows], ensure_ascii=False
        ).casefold()
    assert "private customer text" not in serialized
    assert "sender" not in serialized
    assert "cookie" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized


def test_unknown_is_visible_and_never_marked_for_automatic_retry(foundation) -> None:
    intake, enqueued = _intake_and_approve(foundation, "unknown")
    result = ExecutionWorker(
        foundation["uow_factory"],
        FakeExecutionAdapter(outcome=ReceiptOutcome.UNKNOWN),
        "ops-unknown-worker",
    ).run_once()
    assert result is not None
    service = ObservabilityService(foundation["uow_factory"])

    trace = service.trace(enqueued.execution_id)
    ledger = service.executions(limit=10)

    assert trace.message_id == intake.message_id
    assert trace.why_stopped is TraceStopReason.EXECUTION_UNKNOWN
    assert "禁止自动重试" in trace.next_step
    assert ledger[0].state == "UNKNOWN"
    assert ledger[0].receipt_outcome == "UNKNOWN"
    assert ledger[0].automatic_retry_allowed is False


def test_expired_worker_recovery_emits_started_and_completed_events(foundation) -> None:
    now = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    mutable = {"now": now}

    def clock():
        return mutable["now"]

    _, enqueued = _intake_and_approve(foundation, "recovery")
    worker = ExecutionWorker(
        foundation["uow_factory"],
        FakeExecutionAdapter(),
        "crashed-worker",
        lease_duration=timedelta(seconds=5),
        clock=clock,
    )
    lease = worker.claim_next()
    assert lease is not None
    mutable["now"] += timedelta(seconds=6)

    recovered = ExecutionRecovery(
        foundation["uow_factory"], clock=clock
    ).recover_expired()
    trace = ObservabilityService(foundation["uow_factory"]).trace(
        enqueued.execution_id
    )

    assert len(recovered) == 1
    assert StructuredEventType.RECOVERY_STARTED in {
        event.event_type for event in trace.events
    }
    assert StructuredEventType.RECOVERY_COMPLETED in {
        event.event_type for event in trace.events
    }
    assert trace.why_stopped is TraceStopReason.EXECUTION_UNKNOWN


def test_failed_gateway_transaction_still_leaves_redacted_stop_reason(foundation) -> None:
    class UnavailableGateway:
        def decide(self, _request):
            raise RuntimeError("synthetic gateway unavailable")

    service = ConversationService(foundation["uow_factory"], UnavailableGateway())
    try:
        service.receive(
            ChannelMessage(
                channel_name="fake-channel",
                conversation_external_ref="private-conversation-ref",
                external_message_id="private-message-ref",
                text="private failed message",
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("gateway failure was expected")

    observability = ObservabilityService(foundation["uow_factory"])
    failed = observability.events(
        event_type=StructuredEventType.DECISION_REQUEST_SENT,
        status=StructuredEventStatus.UNKNOWN,
    )
    assert failed.count == 1
    trace = observability.trace(failed.items[0].trace_id)
    assert trace.why_stopped is TraceStopReason.MANUAL_INTERVENTION
    assert "保持不执行" in trace.next_step
    serialized = failed.model_dump_json().casefold()
    assert "private failed message" not in serialized
    assert "private-conversation-ref" not in serialized
    assert "private-message-ref" not in serialized
