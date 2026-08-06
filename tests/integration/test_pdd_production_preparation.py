from __future__ import annotations

from datetime import timedelta

import pytest

from channel_engine.channel import (
    AdapterHealthStatus,
    PDDObservationSyncStatus,
    PDDOutboundMode,
    PDDProductionExecutionAdapter,
    PDDProductionObservationError,
    PDDProductionObservedMessage,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import ExecutionState, ReceiptOutcome
from channel_engine.policy import ApprovalPolicy

from tests.pdd_production_support import (
    ProductionClock,
    build_production_adapter,
)


def production_message(
    clock: ProductionClock,
    *,
    offset: int,
    message_id: str,
    conversation_id: str = "pdd-production-conversation",
    content: str | None = None,
) -> PDDProductionObservedMessage:
    return PDDProductionObservedMessage(
        platform="pdd",
        offset=offset,
        conversation_id=conversation_id,
        external_message_id=message_id,
        sender="pdd-production-fake-buyer",
        content=content or f"PDD production preparation message {message_id}",
        timestamp=clock() - timedelta(seconds=2),
    )


def activate(adapter) -> None:
    adapter.connect()
    heartbeat = adapter.heartbeat()
    assert heartbeat.healthy is True


def test_message_cursor_offset_dedup_order_latency_and_shared_checkpoint(
    foundation,
) -> None:
    clock = ProductionClock()
    adapter, provider, observation, _outbound, ledger, _authorization = (
        build_production_adapter(foundation, clock)
    )
    first = production_message(clock, offset=10, message_id="message-10")
    second = production_message(clock, offset=11, message_id="message-11")
    observation.enqueue_batch(first, second, next_cursor="cursor-11")
    activate(adapter)

    received_first = adapter.receive_message()
    received_second = adapter.receive_message()

    assert received_first is not None
    assert received_first.external_message_id == "message-10"
    assert received_second is not None
    assert received_second.external_message_id == "message-11"
    checkpoint = ledger.load("pdd:pdd-production-preparation-account")
    assert checkpoint.cursor == "cursor-11"
    assert checkpoint.offset == 11
    assert checkpoint.accepted_count == 2
    assert checkpoint.duplicate_count == 0
    assert checkpoint.sync_status is PDDObservationSyncStatus.IN_SYNC
    assert adapter.health_check().details["last_message_latency_ms"] == 2000

    duplicate = second.model_copy(update={"offset": 12})
    third = production_message(clock, offset=13, message_id="message-13")
    observation.enqueue_batch(duplicate, third, next_cursor="cursor-13")
    received_third = adapter.receive_message()
    assert received_third is not None
    assert received_third.external_message_id == "message-13"
    checkpoint = ledger.load("pdd:pdd-production-preparation-account")
    assert checkpoint.cursor == "cursor-13"
    assert checkpoint.offset == 13
    assert checkpoint.accepted_count == 3
    assert checkpoint.duplicate_count == 1
    assert observation.poll_history[:2] == [(None, -1), ("cursor-11", 11)]

    adapter.disconnect()
    replacement, _provider, _observation, _outbound, _ledger, _authorization = (
        build_production_adapter(
            foundation,
            clock,
            provider=provider,
            observation=observation,
            ledger=ledger,
        )
    )
    fourth = production_message(clock, offset=14, message_id="message-14")
    observation.enqueue_batch(fourth, next_cursor="cursor-14")
    activate(replacement)
    received_fourth = replacement.receive_message()
    assert received_fourth is not None
    assert received_fourth.external_message_id == "message-14"
    assert observation.poll_history[-1] == ("cursor-13", 13)
    assert ledger.load("pdd:pdd-production-preparation-account").offset == 14


def test_out_of_order_batch_fails_without_advancing_cursor(foundation) -> None:
    clock = ProductionClock()
    adapter, _provider, observation, _outbound, ledger, _authorization = (
        build_production_adapter(foundation, clock)
    )
    observation.enqueue_batch(
        production_message(clock, offset=2, message_id="message-2"),
        production_message(clock, offset=1, message_id="message-1"),
        next_cursor="cursor-invalid",
    )
    activate(adapter)

    with pytest.raises(PDDProductionObservationError, match="sync failed"):
        adapter.receive_message()

    checkpoint = ledger.load("pdd:pdd-production-preparation-account")
    assert checkpoint.cursor is None
    assert checkpoint.offset == -1
    assert checkpoint.accepted_count == 0
    assert checkpoint.sync_status is PDDObservationSyncStatus.DEGRADED
    assert checkpoint.last_error_code == "PDD_OBSERVATION_SYNC_FAILED"
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED


def test_production_shaped_adapter_preserves_human_approved_worker_boundary(
    foundation,
) -> None:
    clock = ProductionClock()
    adapter, _provider, observation, outbound, _ledger, authorization = (
        build_production_adapter(foundation, clock)
    )
    observation.enqueue_batch(
        production_message(clock, offset=1, message_id="approved-message"),
        next_cursor="approved-cursor",
    )
    activate(adapter)
    inbound = adapter.receive_message()
    assert inbound is not None
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(inbound)

    bridge = PDDProductionExecutionAdapter(adapter, authorization)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        bridge,
        "pdd-production-preparation-worker",
        clock=clock,
    )
    assert worker.run_once() is None
    assert bridge.call_count == 0
    assert outbound.send_attempt_count == 0

    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-production-human-operator")
    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert bridge.call_count == 1
    assert adapter.send_call_count == 1
    assert outbound.send_attempt_count == 1
    assert outbound.real_platform_call_count == 0
    assert worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None
    assert receipt.details["policy"] == "ALLOW_SEND_MESSAGE"
    assert receipt.details["risk_level"] == "LOW"
    assert receipt.details["automatic_reply"] is False
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["refund_performed"] is False
    assert receipt.details["order_modified"] is False
    assert receipt.details["payment_performed"] is False


@pytest.mark.parametrize(
    "mode",
    [PDDOutboundMode.TIMEOUT, PDDOutboundMode.UNKNOWN],
)
def test_production_preparation_unknown_send_is_terminal_without_retry(
    foundation,
    mode: PDDOutboundMode,
) -> None:
    clock = ProductionClock()
    conversation_id = f"pdd-production-{mode.value.lower()}"
    adapter, _provider, observation, outbound, _ledger, authorization = (
        build_production_adapter(
            foundation,
            clock,
            conversations=frozenset({conversation_id}),
            outbound_mode=mode,
        )
    )
    observation.enqueue_batch(
        production_message(
            clock,
            offset=1,
            message_id=f"{mode.value.lower()}-message",
            conversation_id=conversation_id,
        ),
        next_cursor=f"{mode.value.lower()}-cursor",
    )
    activate(adapter)
    inbound = adapter.receive_message()
    assert inbound is not None
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(inbound)
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-production-human-operator")
    worker = ExecutionWorker(
        foundation["uow_factory"],
        PDDProductionExecutionAdapter(adapter, authorization),
        f"pdd-production-{mode.value.lower()}-worker",
        clock=clock,
    )

    result = worker.run_once()
    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert outbound.send_attempt_count == 1
    assert worker.run_once() is None
    assert outbound.send_attempt_count == 1
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None and receipt.outcome is ReceiptOutcome.UNKNOWN
