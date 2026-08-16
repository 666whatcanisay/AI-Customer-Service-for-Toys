from __future__ import annotations

import json
from itertools import count

import pytest
from sqlalchemy import func, select

import channel_engine.conversation.service as conversation_service_module
import channel_engine.execution.coordinator as coordinator_module
from channel_engine.channel import FakePDDAdapter, FakePDDInboundMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionWorker,
    FakeExecutionAdapter,
    to_gateway_execution_receipt,
)
from channel_engine.gateway import (
    AICSGatewayClient,
    AICSGatewayTimeout,
    Event as GatewayEvent,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    MockAICSServer,
    MockAICSTransport,
    MockDecisionBehavior,
    MockDecisionMode,
)
from channel_engine.models import (
    DecisionState,
    EventType,
    ExecutionState,
    MessageState,
    OutboxState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)
from channel_engine.models.entities import utc_now
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage.orm import (
    ApprovalRow,
    ConversationRow,
    DecisionRow,
    EventRow,
    ExecutionRow,
    MessageRow,
    OutboxRow,
    ReceiptRow,
)


MOCK_SECRET = b"mock-e2e-validation-secret-material-32"

SUCCESS_EVENT_TIMELINE = (
    EventType.MESSAGE_RECEIVED,
    EventType.DECISION_CREATED,
    EventType.DECISION_WAITING_APPROVAL,
    EventType.MESSAGE_COMPLETED,
    EventType.DECISION_APPROVED,
    EventType.EXECUTION_STARTED,
    EventType.EXECUTION_SUCCEEDED,
    EventType.RECEIPT_RECORDED,
)


def build_gateway(
    behavior: MockDecisionBehavior | None = None,
) -> tuple[AICSGatewayClient, MockAICSServer]:
    nonce_sequence = count(1)
    server = MockAICSServer(
        {("channel-engine", "mock-e2e-key"): MOCK_SECRET},
        default_behavior=behavior,
    )
    client = AICSGatewayClient(
        MockAICSTransport(server),
        GatewayRequestSigner(
            client_id="channel-engine",
            key_id="mock-e2e-key",
            secret=MOCK_SECRET,
            nonce_factory=lambda: f"mockee{next(nonce_sequence):016d}",
        ),
        retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=lambda _delay: None,
    )
    return client, server


def customer_message(
    *,
    chat_id: str,
    message_id: str,
    body: str = "Where is my order?",
) -> FakePDDInboundMessage:
    return FakePDDInboundMessage(
        chat_id=chat_id,
        message_id=message_id,
        buyer_id=f"buyer-{chat_id}",
        body=body,
        created_at=utc_now(),
    )


def event_rows(foundation) -> list[EventRow]:
    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        return list(
            uow.session.scalars(
                select(EventRow).order_by(EventRow.occurred_at, EventRow.event_id)
            ).all()
        )


def test_complete_mock_business_loop_has_consistent_evidence(
    foundation,
    monkeypatch,
) -> None:
    message_states: list[MessageState] = []
    decision_states: list[DecisionState] = []
    original_message_transition = conversation_service_module.transition_message
    original_decision_transition = conversation_service_module.transition_decision

    def observe_message_transition(message, target, now=None):
        if not message_states:
            message_states.append(message.state)
        transitioned = original_message_transition(message, target, now)
        message_states.append(transitioned.state)
        return transitioned

    def observe_decision_transition(decision, target, now=None):
        if not decision_states:
            decision_states.append(decision.state)
        transitioned = original_decision_transition(decision, target, now)
        if not decision_states or decision_states[-1] is not transitioned.state:
            decision_states.append(transitioned.state)
        return transitioned

    monkeypatch.setattr(
        conversation_service_module,
        "transition_message",
        observe_message_transition,
    )
    monkeypatch.setattr(
        conversation_service_module,
        "transition_decision",
        observe_decision_transition,
    )
    monkeypatch.setattr(
        coordinator_module,
        "transition_decision",
        observe_decision_transition,
    )

    gateway, server = build_gateway()
    channel = FakePDDAdapter()
    raw = customer_message(
        chat_id="e2e-success-chat",
        message_id="e2e-success-message",
        body="Please check the delivery status",
    )
    assert channel.enqueue_customer_message(raw) is True
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(foundation["uow_factory"], gateway)

    intake = service.receive(inbound)

    assert message_states == [
        MessageState.RECEIVED,
        MessageState.PROCESSING,
        MessageState.COMPLETED,
    ]
    assert decision_states == [
        DecisionState.CREATED,
        DecisionState.WAITING_APPROVAL,
    ]
    assert intake.message_state is MessageState.COMPLETED
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert server.request_count == 1
    assert server.decision_compute_count == 1
    assert channel.send_call_count == 0

    coordinator = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    )
    enqueued = coordinator.approve_and_enqueue(
        intake.decision_id,
        "mock-e2e-human-operator",
    )
    assert decision_states == [
        DecisionState.CREATED,
        DecisionState.WAITING_APPROVAL,
        DecisionState.APPROVED,
    ]
    assert enqueued.execution_state is ExecutionState.PENDING

    fake_execution = FakeExecutionAdapter(ReceiptOutcome.SUCCESS)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        fake_execution,
        "mock-e2e-success-worker",
    )
    execution_states = [ExecutionState.PENDING]
    lease = worker.claim_next()
    assert lease is not None
    execution_states.append(lease.execution.state)
    result = worker.process_claim(lease)
    execution_states.append(result.execution_state)

    assert execution_states == [
        ExecutionState.PENDING,
        ExecutionState.RUNNING,
        ExecutionState.SUCCESS,
    ]
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert fake_execution.call_count == 1
    assert worker.run_once() is None
    assert channel.send_call_count == 0

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        conversation = repo.find_conversation("fake-pdd", raw.chat_id)
        message = repo.get_message(intake.message_id)
        decision = repo.get_decision(intake.decision_id)
        approval = repo.get_approval_for_decision(intake.decision_id)
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox_before_publish = repo.list_outbox()
    assert conversation is not None
    assert message.conversation_id == conversation.conversation_id
    assert decision.message_id == message.message_id
    assert approval is not None
    assert execution.approval_id == approval.approval_id
    assert receipt is not None
    assert receipt.execution_id == execution.execution_id
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False

    rows = event_rows(foundation)
    rows_by_type = {EventType(row.event_type): row for row in rows}
    assert set(rows_by_type) == set(SUCCESS_EVENT_TIMELINE)
    assert len(rows) == len(SUCCESS_EVENT_TIMELINE)
    event_times = [rows_by_type[event_type].occurred_at for event_type in SUCCESS_EVENT_TIMELINE]
    assert event_times == sorted(event_times)
    assert (
        rows_by_type[EventType.EXECUTION_SUCCEEDED].payload["receipt_id"]
        == receipt.receipt_id
    )
    assert rows_by_type[EventType.RECEIPT_RECORDED].aggregate_id == receipt.receipt_id
    assert rows_by_type[EventType.RECEIPT_RECORDED].payload == {
        "execution_id": execution.execution_id
    }

    outbox_by_event = {item.event_id: item for item in outbox_before_publish}
    assert set(outbox_by_event) == {row.event_id for row in rows}
    assert len(outbox_by_event) == len(rows)
    for row in rows:
        item = outbox_by_event[row.event_id]
        gateway_event = GatewayEvent.model_validate_json(json.dumps(item.payload))
        assert item.outbox_id == f"outbox-{row.event_id}"
        assert item.status is OutboxState.PENDING
        assert item.topic == row.event_type
        assert gateway_event.event_id == row.event_id
        assert gateway_event.event_type.value == row.event_type
        assert gateway_event.aggregate_id == row.aggregate_id
        assert gateway_event.payload == row.payload

    fake_publisher = FakeEventPublisher()
    outbox_publisher = OutboxPublisher(
        foundation["uow_factory"],
        fake_publisher,
        "mock-e2e-publisher",
    )
    publish_results = outbox_publisher.run_until_idle(max_items=20)
    assert len(publish_results) == len(rows)
    assert all(result.status is OutboxState.PUBLISHED for result in publish_results)
    assert {item.event_id for item in fake_publisher.published_events} == {
        row.event_id for row in rows
    }
    for published in fake_publisher.published_events:
        GatewayEvent.model_validate_json(json.dumps(published.payload))
    with foundation["uow_factory"]() as uow:
        published_outbox = uow.require_repository().list_outbox()
    assert all(item.status is OutboxState.PUBLISHED for item in published_outbox)
    assert all(item.attempt_count == 1 for item in published_outbox)


def test_ai_timeout_rolls_back_engine_state_and_never_executes(foundation) -> None:
    gateway, server = build_gateway(
        MockDecisionBehavior(MockDecisionMode.TIMEOUT)
    )
    channel = FakePDDAdapter()
    raw = customer_message(
        chat_id="e2e-ai-timeout-chat",
        message_id="e2e-ai-timeout-message",
    )
    channel.enqueue_customer_message(raw)
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(foundation["uow_factory"], gateway)

    with pytest.raises(AICSGatewayTimeout) as raised:
        service.receive(inbound)

    assert raised.value.outcome_unknown is True
    assert raised.value.attempts == 3
    assert server.request_count == 3
    assert server.timeout_count == 3
    assert channel.send_call_count == 0
    fake_execution = FakeExecutionAdapter()
    worker = ExecutionWorker(
        foundation["uow_factory"],
        fake_execution,
        "mock-e2e-timeout-worker",
    )
    assert worker.run_once() is None
    assert fake_execution.call_count == 0
    assert event_rows(foundation) == []
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.find_conversation("fake-pdd", raw.chat_id) is None
        assert repo.list_outbox() == []
        assert uow.session is not None
        for row_type in (
            ConversationRow,
            MessageRow,
            DecisionRow,
            ApprovalRow,
            ExecutionRow,
            ReceiptRow,
            EventRow,
            OutboxRow,
        ):
            assert uow.session.scalar(
                select(func.count()).select_from(row_type)
            ) == 0


def test_execution_unknown_records_receipt_and_is_never_retried(foundation) -> None:
    gateway, _server = build_gateway()
    channel = FakePDDAdapter()
    raw = customer_message(
        chat_id="e2e-execution-unknown-chat",
        message_id="e2e-execution-unknown-message",
    )
    channel.enqueue_customer_message(raw)
    inbound = channel.receive_message()
    assert inbound is not None
    intake = ConversationService(foundation["uow_factory"], gateway).receive(inbound)
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "mock-e2e-human-operator")
    uncertain_adapter = FakeExecutionAdapter(simulate_network_uncertainty=True)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        uncertain_adapter,
        "mock-e2e-unknown-worker",
    )

    lease = worker.claim_next()
    assert lease is not None
    assert lease.execution.state is ExecutionState.RUNNING
    result = worker.process_claim(lease)

    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert uncertain_adapter.call_count == 1
    assert worker.run_once() is None
    assert uncertain_adapter.call_count == 1
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        decision = repo.get_decision(intake.decision_id)
    assert execution.state is ExecutionState.UNKNOWN
    assert execution.attempt == 1
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.UNKNOWN
    assert receipt.details["error_code"] == "ADAPTER_NETWORK_UNKNOWN"
    gateway_receipt = to_gateway_execution_receipt(
        execution,
        receipt,
        decision.message_id,
    )
    assert gateway_receipt.reconciliation_required is True
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)

    rows = event_rows(foundation)
    rows_by_type = {EventType(row.event_type): row for row in rows}
    assert EventType.EXECUTION_UNKNOWN in rows_by_type
    assert EventType.EXECUTION_SUCCEEDED not in rows_by_type
    assert (
        rows_by_type[EventType.EXECUTION_UNKNOWN].payload["receipt_id"]
        == receipt.receipt_id
    )
    assert rows_by_type[EventType.RECEIPT_RECORDED].aggregate_id == receipt.receipt_id
    with foundation["uow_factory"]() as uow:
        outbox = uow.require_repository().list_outbox()
    assert {item.event_id for item in outbox} == {row.event_id for row in rows}


def test_duplicate_message_recovers_same_decision_without_new_events(foundation) -> None:
    gateway, server = build_gateway()
    channel = FakePDDAdapter()
    raw = customer_message(
        chat_id="e2e-duplicate-message-chat",
        message_id="e2e-duplicate-message",
    )
    assert channel.enqueue_customer_message(raw) is True
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(foundation["uow_factory"], gateway)
    first = service.receive(inbound)

    assert channel.enqueue_customer_message(raw) is False
    replay = service.receive(channel.normalize_message(raw))

    assert replay == first
    assert server.request_count == 1
    assert server.decision_compute_count == 1
    assert gateway.cache_replay_count == 0
    assert channel.send_call_count == 0
    rows = event_rows(foundation)
    assert [row.event_type for row in rows].count(EventType.MESSAGE_RECEIVED.value) == 1
    assert [row.event_type for row in rows].count(EventType.DECISION_CREATED.value) == 1
    assert len(rows) == 4
    with foundation["uow_factory"]() as uow:
        outbox = uow.require_repository().list_outbox()
        assert uow.session is not None
        message_count = uow.session.scalar(
            select(func.count()).select_from(MessageRow)
        )
        decision_count = uow.session.scalar(
            select(func.count()).select_from(DecisionRow)
        )
    assert message_count == 1
    assert decision_count == 1
    assert len(outbox) == 4
    assert len({item.event_id for item in outbox}) == 4


def test_duplicate_approval_creates_one_execution_and_one_receipt(foundation) -> None:
    gateway, _server = build_gateway()
    channel = FakePDDAdapter()
    raw = customer_message(
        chat_id="e2e-duplicate-approval-chat",
        message_id="e2e-duplicate-approval-message",
    )
    channel.enqueue_customer_message(raw)
    inbound = channel.receive_message()
    assert inbound is not None
    intake = ConversationService(foundation["uow_factory"], gateway).receive(inbound)
    coordinator = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    )

    first = coordinator.approve_and_enqueue(
        intake.decision_id,
        "mock-e2e-human-operator",
    )
    replay = coordinator.approve_and_enqueue(
        intake.decision_id,
        "mock-e2e-human-operator",
    )

    assert replay == first
    fake_execution = FakeExecutionAdapter()
    worker = ExecutionWorker(
        foundation["uow_factory"],
        fake_execution,
        "mock-e2e-duplicate-approval-worker",
    )
    completed = worker.run_once()
    assert completed is not None
    assert completed.execution_state is ExecutionState.SUCCESS
    assert worker.run_once() is None
    assert fake_execution.call_count == 1
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution_for_decision(intake.decision_id)
        approval = repo.get_approval_for_decision(intake.decision_id)
        receipt = repo.get_receipt_for_execution(first.execution_id)
        assert uow.session is not None
        approval_count = uow.session.scalar(
            select(func.count()).select_from(ApprovalRow)
        )
        execution_count = uow.session.scalar(
            select(func.count()).select_from(ExecutionRow)
        )
        receipt_count = uow.session.scalar(
            select(func.count()).select_from(ReceiptRow)
        )
    assert execution is not None
    assert approval is not None
    assert execution.execution_id == first.execution_id
    assert approval.approval_id == first.approval_id
    assert execution.attempt == 1
    assert receipt is not None
    assert approval_count == 1
    assert execution_count == 1
    assert receipt_count == 1
    rows = event_rows(foundation)
    event_types = [row.event_type for row in rows]
    assert event_types.count(EventType.DECISION_APPROVED.value) == 1
    assert event_types.count(EventType.EXECUTION_STARTED.value) == 1
    assert event_types.count(EventType.EXECUTION_SUCCEEDED.value) == 1
    assert event_types.count(EventType.RECEIPT_RECORDED.value) == 1
