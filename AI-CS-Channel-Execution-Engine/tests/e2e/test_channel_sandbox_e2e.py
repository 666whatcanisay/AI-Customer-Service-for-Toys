from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from channel_engine.channel import (
    LedgerExecutionAuthorizationService,
    SandboxChannelAdapter,
    SandboxClock,
    SandboxExecutionAdapter,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import (
    DecisionState,
    EventType,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.policy import ApprovalPolicy
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelInstanceStatus,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
)
from channel_engine.storage.orm import EventRow


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)


def build_sandbox(foundation, outcome: ReceiptOutcome):
    clock = SandboxClock(NOW)
    store = ChannelSessionStore(foundation["uow_factory"])
    credential = CredentialReference(
        credential_ref="vault://sandbox/e2e-store",
        provider="sandbox-vault",
        version="v1",
    )
    provider = FakeCredentialProvider(
        (credential,), lease_ttl=timedelta(minutes=10), clock=clock
    )
    delivery = MessageReliabilityService(
        foundation["uow_factory"], store, clock=clock
    )
    manager = ChannelInstanceManager(store, provider, delivery, clock=clock)
    authorization = LedgerExecutionAuthorizationService(
        foundation["uow_factory"], clock=clock
    )
    adapter = SandboxChannelAdapter(
        store_id="e2e-store",
        authorization_verifier=authorization,
        send_outcome=outcome,
        clock=clock,
    )
    instance = manager.create_instance(
        instance_id="sandbox-e2e-instance",
        platform="sandbox",
        store_id="e2e-store",
        adapter_type="SandboxChannelAdapter",
        credential_ref=credential,
        adapter=adapter,
    )
    started = manager.start_instance(instance.instance_id)
    assert started.instance.status is ChannelInstanceStatus.CONNECTED
    return clock, delivery, manager, adapter, authorization


def drive_to_approved_execution(foundation, outcome: ReceiptOutcome):
    clock, delivery, manager, adapter, authorization = build_sandbox(
        foundation, outcome
    )
    adapter.customer_message_received(
        message_id="sandbox-e2e-message",
        conversation_id="sandbox-e2e-conversation",
        content="Where is my synthetic sandbox order?",
    )
    inbound = manager.poll_messages("sandbox-e2e-instance")
    assert len(inbound) == 1
    intake = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    ).receive(inbound[0].message.to_runtime_message())
    delivery.ack("sandbox-e2e-instance", inbound[0].delivery_id)
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(intake.decision_id, "sandbox-human-operator")
    bridge = SandboxExecutionAdapter(adapter, authorization)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        bridge,
        "sandbox-e2e-worker",
        clock=clock,
    )
    return intake, enqueued, worker, bridge, adapter, delivery


def test_complete_sandbox_message_to_receipt_event_flow(foundation) -> None:
    intake, enqueued, worker, bridge, adapter, delivery = (
        drive_to_approved_execution(foundation, ReceiptOutcome.SUCCESS)
    )

    result = worker.run_once()

    assert result is not None
    assert result.execution_id == enqueued.execution_id
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert bridge.call_count == 1
    assert adapter.send_call_count == 1
    assert delivery.get_cursor("sandbox-e2e-instance").last_acked_sequence == 1
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        execution = repo.get_execution(enqueued.execution_id)
        approval = repo.get_approval_for_decision(intake.decision_id)
        assert uow.session is not None
        events = uow.session.scalars(
            select(EventRow).order_by(EventRow.occurred_at, EventRow.event_id)
        ).all()
        outbox = repo.list_outbox()
    assert approval is not None
    assert execution.state is ExecutionState.SUCCESS
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["mode"] == "SANDBOX_CONTROLLED_EXECUTION"
    assert receipt.details["human_approved"] is True
    assert receipt.details["automatic_reply"] is False
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False
    event_types = {EventType(item.event_type) for item in events}
    assert {
        EventType.MESSAGE_RECEIVED,
        EventType.DECISION_CREATED,
        EventType.DECISION_APPROVED,
        EventType.EXECUTION_STARTED,
        EventType.EXECUTION_SUCCEEDED,
        EventType.RECEIPT_RECORDED,
    }.issubset(event_types)
    assert len(outbox) == len(events)
    assert {item.event_id for item in outbox} == {
        item.event_id for item in events
    }


def test_sandbox_execution_unknown_records_receipt_and_never_retries(
    foundation,
) -> None:
    _intake, enqueued, worker, bridge, adapter, _delivery = (
        drive_to_approved_execution(foundation, ReceiptOutcome.UNKNOWN)
    )

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert bridge.call_count == 1
    assert adapter.send_call_count == 1
    assert worker.run_once() is None
    assert bridge.call_count == 1
    assert adapter.send_call_count == 1
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        assert uow.session is not None
        event_types = {
            EventType(value)
            for value in uow.session.scalars(select(EventRow.event_type)).all()
        }
    assert execution.state is ExecutionState.UNKNOWN
    assert execution.attempt == 1
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.UNKNOWN
    assert receipt.details["error_code"] == "FAKE_CHANNEL_SEND_UNKNOWN"
    assert EventType.EXECUTION_UNKNOWN in event_types
    assert EventType.EXECUTION_SUCCEEDED not in event_types
