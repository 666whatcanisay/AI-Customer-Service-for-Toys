from __future__ import annotations

from itertools import count

import pytest

from channel_engine.channel import FakePDDAdapter, FakePDDInboundMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.gateway import (
    AICSGatewayClient,
    AICSGatewayTimeout,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    MockAICSServer,
    MockAICSTransport,
    MockDecisionBehavior,
    MockDecisionMode,
)
from channel_engine.models import DecisionState, ExecutionState, ReceiptOutcome
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy


MOCK_SECRET = b"integration-mock-secret-material-32"


def gateway_client(
    behavior: MockDecisionBehavior | None = None,
) -> tuple[AICSGatewayClient, MockAICSServer]:
    nonce_sequence = count(1)
    server = MockAICSServer(
        {("channel-engine", "integration-key"): MOCK_SECRET},
        default_behavior=behavior,
    )
    client = AICSGatewayClient(
        MockAICSTransport(server),
        GatewayRequestSigner(
            client_id="channel-engine",
            key_id="integration-key",
            secret=MOCK_SECRET,
            nonce_factory=lambda: f"intgwy{next(nonce_sequence):016d}",
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


def test_fake_channel_to_mock_ai_cs_to_execution_receipt(foundation) -> None:
    client, server = gateway_client()
    channel = FakePDDAdapter()
    channel.enqueue_customer_message(
        FakePDDInboundMessage(
            chat_id="gateway-flow-chat-1",
            message_id="gateway-flow-message-1",
            buyer_id="gateway-flow-buyer-1",
            body="Please help with this order",
            created_at=utc_now(),
        )
    )
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(foundation["uow_factory"], client)

    intake = service.receive(inbound)

    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert foundation["executor"].call_count == 0
    assert channel.send_call_count == 0
    assert server.request_count == 1
    assert server.decision_compute_count == 1

    coordinator = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    )
    enqueued = coordinator.approve_and_enqueue(
        intake.decision_id,
        "integration-human-operator",
    )
    assert enqueued.execution_state is ExecutionState.PENDING
    assert foundation["executor"].call_count == 0

    worker = ExecutionWorker(
        foundation["uow_factory"],
        foundation["executor"],
        "gateway-integration-worker",
    )
    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert foundation["executor"].call_count == 1
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        decision = repo.get_decision(intake.decision_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
    assert decision.gateway_version == "mock-ai-cs.v1"
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False


def test_gateway_timeout_never_creates_execution_or_auto_sends(foundation) -> None:
    client, server = gateway_client(
        MockDecisionBehavior(MockDecisionMode.TIMEOUT)
    )
    channel = FakePDDAdapter()
    raw = FakePDDInboundMessage(
        chat_id="gateway-timeout-chat",
        message_id="gateway-timeout-message",
        buyer_id="gateway-timeout-buyer",
        body="This decision request will time out",
        created_at=utc_now(),
    )
    channel.enqueue_customer_message(raw)
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(foundation["uow_factory"], client)

    with pytest.raises(AICSGatewayTimeout):
        service.receive(inbound)

    assert server.request_count == 3
    assert server.timeout_count == 3
    assert foundation["executor"].call_count == 0
    assert channel.send_call_count == 0
    worker = ExecutionWorker(
        foundation["uow_factory"],
        foundation["executor"],
        "gateway-timeout-worker",
    )
    assert worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        conversation = uow.require_repository().find_conversation(
            "fake-pdd",
            "gateway-timeout-chat",
        )
    assert conversation is None
