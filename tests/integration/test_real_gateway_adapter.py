from __future__ import annotations

from itertools import count

import httpx
import pytest

from channel_engine.channel import FakePDDAdapter, FakePDDInboundMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionWorker
from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    GatewayAdapterConfig,
    GatewayEnvironment,
    GatewayErrorCode,
    GatewayRetryPolicy,
    MockAICSServer,
    MockDecisionBehavior,
    MockDecisionMode,
    ProductionGatewayClient,
)
from channel_engine.models import DecisionState, MessageState
from channel_engine.models.entities import utc_now


HTTP_SECRET = b"real-gateway-integration-secret-32b"


def gateway_over_local_http(
    behavior: MockDecisionBehavior | None = None,
) -> tuple[ProductionGatewayClient, MockAICSServer, httpx.Client]:
    server = MockAICSServer(
        {("channel-engine", "integration-http-key"): HTTP_SECRET},
        default_behavior=behavior,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        result = server.handle_request(
            method=request.method,
            path=request.url.path,
            body=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            result.status_code,
            content=result.body,
            headers=result.headers,
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    nonce_sequence = count(1)
    gateway = ProductionGatewayClient(
        GatewayAdapterConfig(
            environment=GatewayEnvironment.MOCK,
            base_url="http://127.0.0.1:18021",
            client_id="channel-engine",
            key_id="integration-http-key",
        ),
        HTTP_SECRET,
        http_client=http_client,
        retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        nonce_factory=lambda: f"localh{next(nonce_sequence):016d}",
        sleeper=lambda _delay: None,
    )
    return gateway, server, http_client


def test_channel_engine_to_local_http_ai_cs_decision_response(foundation) -> None:
    gateway, server, http_client = gateway_over_local_http()
    channel = FakePDDAdapter()
    channel.enqueue_customer_message(
        FakePDDInboundMessage(
            chat_id="real-gateway-local-chat",
            message_id="real-gateway-local-message",
            buyer_id="real-gateway-local-buyer",
            body="Can you check this order?",
            created_at=utc_now(),
        )
    )
    inbound = channel.receive_message()
    assert inbound is not None
    try:
        intake = ConversationService(foundation["uow_factory"], gateway).receive(
            inbound
        )
    finally:
        gateway.close()
        http_client.close()

    assert intake.message_state is MessageState.COMPLETED
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert server.request_count == 1
    assert server.decision_compute_count == 1
    assert foundation["executor"].call_count == 0
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        decision = uow.require_repository().get_decision(intake.decision_id)
    assert decision.gateway_version == "mock-ai-cs.v1"


def test_local_http_ai_cs_error_rolls_back_and_does_not_execute(foundation) -> None:
    gateway, server, http_client = gateway_over_local_http(
        MockDecisionBehavior(
            MockDecisionMode.ERROR,
            error_code=GatewayErrorCode.AUTHORIZATION_DENIED,
        )
    )
    channel = FakePDDAdapter()
    raw = FakePDDInboundMessage(
        chat_id="real-gateway-error-chat",
        message_id="real-gateway-error-message",
        buyer_id="real-gateway-error-buyer",
        body="This local request returns a contract error",
        created_at=utc_now(),
    )
    channel.enqueue_customer_message(raw)
    inbound = channel.receive_message()
    assert inbound is not None
    try:
        with pytest.raises(AICSGatewayRequestFailed) as raised:
            ConversationService(foundation["uow_factory"], gateway).receive(inbound)
    finally:
        gateway.close()
        http_client.close()

    assert raised.value.envelope.error.code is GatewayErrorCode.AUTHORIZATION_DENIED
    assert raised.value.attempts == 1
    assert server.request_count == 1
    assert foundation["executor"].call_count == 0
    assert channel.send_call_count == 0
    worker = ExecutionWorker(
        foundation["uow_factory"],
        foundation["executor"],
        "real-gateway-error-worker",
    )
    assert worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().find_conversation(
            "fake-pdd",
            raw.chat_id,
        ) is None
