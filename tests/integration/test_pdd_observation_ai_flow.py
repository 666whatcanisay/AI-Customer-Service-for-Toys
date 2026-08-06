from __future__ import annotations

from itertools import count

from channel_engine.channel import (
    ChannelAuthenticationScheme,
    ChannelCredentialReference,
    FakeChannelAuthenticationBroker,
    FakePDDObservationTransport,
    PDDAdapter,
    PDDObservedMessage,
)
from channel_engine.conversation import ConversationService
from channel_engine.gateway import (
    AICSGatewayClient,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    MockAICSServer,
    MockAICSTransport,
)
from channel_engine.models import DecisionState, MessageState
from channel_engine.models.entities import utc_now


OBSERVATION_SECRET = b"pdd-observation-mock-ai-cs-secret-32-bytes"


def test_pdd_observation_reaches_mock_ai_cs_and_stops_before_approval(
    foundation,
) -> None:
    credential = ChannelCredentialReference(
        credential_id="secret-manager/pdd/mock-observation",
        provider="secret-manager",
        version="mock-observation-v1",
        account_ref="pdd-mock-observation-account",
        auth_scheme=ChannelAuthenticationScheme.MANAGED_SESSION,
    )
    transport = FakePDDObservationTransport()
    adapter = PDDAdapter(
        credential,
        FakeChannelAuthenticationBroker(),
        transport,
    )
    transport.enqueue(
        PDDObservedMessage(
            platform="pdd",
            conversation_id="pdd-ai-observation-conversation",
            external_message_id="pdd-ai-observation-message",
            sender="pdd-ai-observation-buyer",
            content="请提供合成商品的使用说明。",
            timestamp=utc_now(),
        )
    )
    nonce_sequence = count(1)
    server = MockAICSServer(
        {("channel-engine", "pdd-observation-key"): OBSERVATION_SECRET}
    )
    gateway = AICSGatewayClient(
        MockAICSTransport(server),
        GatewayRequestSigner(
            client_id="channel-engine",
            key_id="pdd-observation-key",
            secret=OBSERVATION_SECRET,
            nonce_factory=lambda: f"pddobserve{next(nonce_sequence):014d}",
        ),
        retry_policy=GatewayRetryPolicy(
            max_attempts=1,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=lambda _delay: None,
    )

    adapter.connect()
    inbound = adapter.receive_message()
    assert inbound is not None
    intake = ConversationService(
        foundation["uow_factory"],
        gateway,
    ).receive(inbound)

    assert intake.message_state is MessageState.COMPLETED
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert server.request_count == 1
    assert server.decision_compute_count == 1
    assert foundation["executor"].call_count == 0
    assert not hasattr(adapter, "send_message")
    assert transport.real_platform_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.get_approval_for_decision(intake.decision_id) is None
        assert repo.get_execution_for_decision(intake.decision_id) is None
