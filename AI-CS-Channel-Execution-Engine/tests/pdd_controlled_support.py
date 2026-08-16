from __future__ import annotations

from itertools import count

from channel_engine.channel import (
    ChannelAuthenticationScheme,
    ChannelCredentialReference,
    FakeChannelAuthenticationBroker,
    FakePDDObservationTransport,
    FakePDDOutboundTransport,
    LedgerExecutionAuthorizationService,
    PDDControlledAdapter,
    PDDOutboundMode,
)
from channel_engine.gateway import (
    AICSGatewayClient,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    MockAICSServer,
    MockAICSTransport,
)


MOCK_AI_CS_SECRET = b"pdd-controlled-mock-ai-cs-secret-v1"


def pdd_credential() -> ChannelCredentialReference:
    return ChannelCredentialReference(
        credential_id="secret-manager/pdd/controlled-foundation",
        provider="secret-manager",
        version="controlled-v1",
        account_ref="pdd-controlled-fake-account",
        auth_scheme=ChannelAuthenticationScheme.MANAGED_SESSION,
    )


def mock_ai_cs_gateway() -> tuple[AICSGatewayClient, MockAICSServer]:
    nonce_sequence = count(1)
    server = MockAICSServer(
        {("channel-engine", "pdd-controlled-key"): MOCK_AI_CS_SECRET}
    )
    gateway = AICSGatewayClient(
        MockAICSTransport(server),
        GatewayRequestSigner(
            client_id="channel-engine",
            key_id="pdd-controlled-key",
            secret=MOCK_AI_CS_SECRET,
            nonce_factory=lambda: f"pddcontrolled{next(nonce_sequence):012d}",
        ),
        retry_policy=GatewayRetryPolicy(
            max_attempts=1,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=lambda _delay: None,
    )
    return gateway, server


def controlled_adapter(
    foundation,
    mode: PDDOutboundMode = PDDOutboundMode.SUCCESS,
) -> tuple[
    PDDControlledAdapter,
    LedgerExecutionAuthorizationService,
    FakePDDObservationTransport,
    FakePDDOutboundTransport,
]:
    authorization = LedgerExecutionAuthorizationService(foundation["uow_factory"])
    inbound = FakePDDObservationTransport()
    outbound = FakePDDOutboundTransport(mode)
    adapter = PDDControlledAdapter(
        pdd_credential(),
        FakeChannelAuthenticationBroker(),
        inbound,
        authorization,
        outbound,
    )
    return adapter, authorization, inbound, outbound
