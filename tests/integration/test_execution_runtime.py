from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from channel_engine.channel import ChannelMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    AdapterIdempotencyConflict,
    ExecutionCoordinator,
    ExecutionCommand,
    ExecutionRecovery,
    ExecutionWorker,
    FakeExecutionAdapter,
    LeaseLost,
    to_gateway_execution_receipt,
)
from channel_engine.gateway import Event as GatewayEvent
from channel_engine.models import (
    Conversation,
    Event,
    EventType,
    ExecutionState,
    OutboxState,
    Receipt,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage.orm import OutboxRow


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def enqueue_execution(foundation, suffix: str):
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref=f"runtime-conversation-{suffix}",
            external_message_id=f"runtime-message-{suffix}",
            text=f"runtime request {suffix}",
        )
    )
    coordinator = ExecutionCoordinator(foundation["uow_factory"], ApprovalPolicy())
    return coordinator.approve_and_enqueue(intake.decision_id, "runtime-operator")


def append_outbox_event(foundation, clock: MutableClock, suffix: str) -> str:
    conversation = Conversation(
        channel_name="fake", external_ref=f"outbox-conversation-{suffix}"
    )
    event = Event(
        aggregate_type="Conversation",
        aggregate_id=conversation.conversation_id,
        event_type=EventType.MESSAGE_RECEIVED,
        payload={"suffix": suffix},
        correlation_id=f"outbox-correlation-{suffix}",
        occurred_at=clock(),
    )
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        repo.save_conversation(conversation)
        repo.append_event(event)
    return event.event_id


def test_approval_enqueues_idempotently_before_worker_runs(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="idempotent-runtime-conversation",
            external_message_id="idempotent-runtime-message",
            text="execute once",
        )
    )
    coordinator = ExecutionCoordinator(foundation["uow_factory"], ApprovalPolicy())

    first = coordinator.approve_and_enqueue(intake.decision_id, "operator-one")
    replay = coordinator.approve_and_enqueue(intake.decision_id, "operator-one")

    assert replay == first
    assert first.execution_state is ExecutionState.PENDING
    assert foundation["executor"].call_count == 0

    worker = ExecutionWorker(
        foundation["uow_factory"], foundation["executor"], "idempotent-worker"
    )
    result = worker.run_once()
    assert result is not None
    assert result.execution_state is ExecutionState.SUCCESS
    assert worker.run_once() is None
    assert foundation["executor"].call_count == 1


def test_concurrent_approval_replays_one_durable_execution(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="concurrent-approval-conversation",
            external_message_id="concurrent-approval-message",
            text="approve once",
        )
    )

    def approve(_index: int):
        coordinator = ExecutionCoordinator(
            foundation["uow_factory"], ApprovalPolicy()
        )
        return coordinator.approve_and_enqueue(intake.decision_id, "operator-one")

    with ThreadPoolExecutor(max_workers=4) as pool:
        approvals = list(pool.map(approve, range(4)))

    assert len({approval.approval_id for approval in approvals}) == 1
    assert len({approval.execution_id for approval in approvals}) == 1
    assert all(
        approval.execution_state is ExecutionState.PENDING for approval in approvals
    )


def test_lease_prevents_two_workers_from_executing_same_job(foundation) -> None:
    enqueued = enqueue_execution(foundation, "lease")
    clock = MutableClock()
    adapter = FakeExecutionAdapter()
    first_worker = ExecutionWorker(
        foundation["uow_factory"],
        adapter,
        "lease-worker-one",
        lease_duration=timedelta(seconds=10),
        clock=clock,
    )
    second_worker = ExecutionWorker(
        foundation["uow_factory"],
        adapter,
        "lease-worker-two",
        lease_duration=timedelta(seconds=10),
        clock=clock,
    )

    lease = first_worker.claim_next()
    assert lease is not None
    assert lease.execution.execution_id == enqueued.execution_id
    assert lease.execution.state is ExecutionState.RUNNING
    assert lease.execution.attempt == 1
    assert second_worker.run_once() is None
    assert adapter.call_count == 0

    result = first_worker.process_claim(lease)
    assert result.execution_state is ExecutionState.SUCCESS
    assert adapter.call_count == 1


def test_concurrent_workers_claim_execution_exactly_once(foundation) -> None:
    enqueued = enqueue_execution(foundation, "concurrent")
    adapter = FakeExecutionAdapter()
    workers = [
        ExecutionWorker(
            foundation["uow_factory"], adapter, f"concurrent-worker-{index}"
        )
        for index in range(8)
    ]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda worker: worker.run_once(), workers))

    completed = [result for result in results if result is not None]
    assert len(completed) == 1
    assert completed[0].execution_id == enqueued.execution_id
    assert completed[0].execution_state is ExecutionState.SUCCESS
    assert adapter.call_count == 1

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        execution = repo.get_execution(enqueued.execution_id)
    assert receipt is not None
    assert execution.attempt == 1


def test_worker_loop_drains_pending_queue(foundation) -> None:
    enqueued = [
        enqueue_execution(foundation, f"worker-loop-{index}") for index in range(3)
    ]
    adapter = FakeExecutionAdapter()
    worker = ExecutionWorker(
        foundation["uow_factory"], adapter, "drain-worker"
    )

    results = worker.run_until_idle(max_items=10)

    assert {result.execution_id for result in results} == {
        item.execution_id for item in enqueued
    }
    assert all(
        result.execution_state is ExecutionState.SUCCESS for result in results
    )
    assert adapter.call_count == 3


def test_fake_adapter_replays_by_idempotency_key_and_rejects_conflict() -> None:
    adapter = FakeExecutionAdapter()
    command = ExecutionCommand(
        execution_id="execution-idempotent",
        decision_id="decision-idempotent",
        proposed_content="approved fake content",
        idempotency_key="execute-decision-idempotent",
    )

    first = adapter.execute(command)
    replay = adapter.execute(command)

    assert replay == first
    assert adapter.call_count == 1
    with pytest.raises(AdapterIdempotencyConflict):
        adapter.execute(
            command.model_copy(update={"proposed_content": "different content"})
        )


@pytest.mark.parametrize(
    ("outcome", "expected_state"),
    [
        (ReceiptOutcome.SUCCESS, ExecutionState.SUCCESS),
        (ReceiptOutcome.FAILED, ExecutionState.FAILED),
        (ReceiptOutcome.UNKNOWN, ExecutionState.UNKNOWN),
    ],
)
def test_every_adapter_outcome_has_one_immutable_receipt(
    foundation, outcome: ReceiptOutcome, expected_state: ExecutionState
) -> None:
    enqueued = enqueue_execution(foundation, f"receipt-{outcome.value.lower()}")
    adapter = FakeExecutionAdapter(outcome=outcome)
    worker = ExecutionWorker(
        foundation["uow_factory"], adapter, f"receipt-worker-{outcome.value.lower()}"
    )

    result = worker.run_once()
    assert result is not None
    assert result.execution_state is expected_state
    assert result.receipt_outcome is outcome

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
    assert receipt is not None
    assert receipt.outcome is outcome
    assert execution.lease_owner is None
    assert execution.lease_token is None
    assert execution.lease_expires_at is None
    gateway_receipt = to_gateway_execution_receipt(
        execution, receipt, f"runtime-correlation-{outcome.value.lower()}"
    )
    assert gateway_receipt.outcome is outcome
    assert gateway_receipt.idempotency_key == receipt.receipt_id
    assert gateway_receipt.reconciliation_required is (
        outcome is ReceiptOutcome.UNKNOWN
    )

    with pytest.raises(ValueError, match="immutable"):
        with foundation["uow_factory"]() as uow:
            uow.require_repository().append_receipt(
                Receipt(
                    execution_id=enqueued.execution_id,
                    outcome=outcome,
                    details={"replacement": True},
                )
            )


def test_worker_crash_is_recovered_as_unknown_without_adapter_retry(foundation) -> None:
    enqueued = enqueue_execution(foundation, "crash")
    clock = MutableClock()
    adapter = FakeExecutionAdapter()
    crashed_worker = ExecutionWorker(
        foundation["uow_factory"],
        adapter,
        "crashed-worker",
        lease_duration=timedelta(seconds=5),
        clock=clock,
    )
    lease = crashed_worker.claim_next()
    assert lease is not None

    recovery = ExecutionRecovery(foundation["uow_factory"], clock=clock)
    assert recovery.recover_expired() == []
    clock.advance(timedelta(seconds=6))
    recovered = recovery.recover_expired()

    assert len(recovered) == 1
    assert recovered[0].execution_id == enqueued.execution_id
    assert recovered[0].execution_state is ExecutionState.UNKNOWN
    assert recovered[0].receipt_outcome is ReceiptOutcome.UNKNOWN
    assert recovery.recover_expired() == []
    assert adapter.call_count == 0

    with pytest.raises(LeaseLost):
        crashed_worker.process_claim(lease)

    replacement_worker = ExecutionWorker(
        foundation["uow_factory"], adapter, "replacement-worker", clock=clock
    )
    assert replacement_worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        execution = uow.require_repository().get_execution(enqueued.execution_id)
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)


def test_network_uncertainty_becomes_unknown_and_is_never_requeued(foundation) -> None:
    enqueued = enqueue_execution(foundation, "network")
    adapter = FakeExecutionAdapter(simulate_network_uncertainty=True)
    worker = ExecutionWorker(
        foundation["uow_factory"], adapter, "network-worker"
    )

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert worker.run_once() is None
    assert adapter.call_count == 1
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None
    assert receipt.details["error_code"] == "ADAPTER_NETWORK_UNKNOWN"


def test_outbox_publisher_retries_with_backoff_and_publishes_once(foundation) -> None:
    clock = MutableClock()
    event_id = append_outbox_event(foundation, clock, "retry")
    fake_publisher = FakeEventPublisher(failures_before_success=2)
    publisher = OutboxPublisher(
        foundation["uow_factory"],
        fake_publisher,
        "retry-publisher",
        max_attempts=3,
        base_retry_delay=timedelta(seconds=1),
        clock=clock,
    )

    first = publisher.run_once()
    assert first is not None
    assert first.status is OutboxState.PENDING
    assert publisher.run_once() is None

    clock.advance(timedelta(seconds=1))
    second = publisher.run_once()
    assert second is not None
    assert second.status is OutboxState.PENDING

    clock.advance(timedelta(seconds=2))
    third = publisher.run_once()
    assert third is not None
    assert third.status is OutboxState.PUBLISHED
    assert fake_publisher.attempts_for(event_id) == 3
    assert [event.event_id for event in fake_publisher.published_events] == [event_id]
    assert GatewayEvent.model_validate_json(
        json.dumps(fake_publisher.published_events[0].payload)
    )

    with foundation["uow_factory"]() as uow:
        item = uow.require_repository().list_outbox()[0]
    assert item.status is OutboxState.PUBLISHED
    assert item.attempt_count == 3
    assert item.last_error is None


def test_outbox_publisher_stops_after_retry_budget(foundation) -> None:
    clock = MutableClock()
    event_id = append_outbox_event(foundation, clock, "terminal")
    fake_publisher = FakeEventPublisher(failures_before_success=10)
    publisher = OutboxPublisher(
        foundation["uow_factory"],
        fake_publisher,
        "terminal-publisher",
        max_attempts=2,
        base_retry_delay=timedelta(seconds=1),
        clock=clock,
    )

    first = publisher.run_once()
    assert first is not None and first.status is OutboxState.PENDING
    clock.advance(timedelta(seconds=1))
    second = publisher.run_once()
    assert second is not None and second.status is OutboxState.FAILED
    clock.advance(timedelta(hours=1))
    assert publisher.run_once() is None
    assert fake_publisher.attempts_for(event_id) == 2

    with foundation["uow_factory"]() as uow:
        item = uow.require_repository().list_outbox()[0]
    assert item.status is OutboxState.FAILED
    assert item.attempt_count == 2
    assert "FakePublishError" in (item.last_error or "")


def test_expired_outbox_lease_is_reclaimed_idempotently(foundation) -> None:
    clock = MutableClock()
    event_id = append_outbox_event(foundation, clock, "lease")
    with foundation["uow_factory"]() as uow:
        claimed = uow.require_repository().claim_outbox(
            "crashed-publisher",
            clock(),
            clock() + timedelta(seconds=5),
        )
    assert claimed is not None
    assert claimed.status is OutboxState.PROCESSING

    clock.advance(timedelta(seconds=6))
    fake_publisher = FakeEventPublisher()
    replacement = OutboxPublisher(
        foundation["uow_factory"],
        fake_publisher,
        "replacement-publisher",
        clock=clock,
    )
    result = replacement.run_once()

    assert result is not None
    assert result.status is OutboxState.PUBLISHED
    assert result.attempt_count == 2
    assert [event.event_id for event in fake_publisher.published_events] == [event_id]


def test_legacy_outbox_payload_is_normalized_to_gateway_event_v1(foundation) -> None:
    clock = MutableClock()
    event_id = append_outbox_event(foundation, clock, "legacy")
    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        row = uow.session.get(OutboxRow, f"outbox-{event_id}")
        assert row is not None
        wire_payload = row.payload
        row.payload = {
            "event_id": wire_payload["event_id"],
            "event_type": wire_payload["event_type"],
            "aggregate_type": wire_payload["aggregate_type"],
            "aggregate_id": wire_payload["aggregate_id"],
            "payload": wire_payload["payload"],
            "correlation_id": wire_payload["correlation_id"],
            "occurred_at": wire_payload["occurred_at"],
        }

    fake_publisher = FakeEventPublisher()
    publisher = OutboxPublisher(
        foundation["uow_factory"], fake_publisher, "legacy-publisher", clock=clock
    )
    result = publisher.run_once()

    assert result is not None and result.status is OutboxState.PUBLISHED
    published = fake_publisher.published_events[0]
    event = GatewayEvent.model_validate_json(json.dumps(published.payload))
    assert event.contract_version == "1.0"
    assert event.source == "CHANNEL_ENGINE"
