from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count
import inspect

import pytest

from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    CONTRACT_VERSION,
    DecisionRequest,
    Event,
    ExecutionReceipt,
    GatewayAggregateType,
    GatewayErrorCode,
    GatewayRetryPolicy,
    GatewayTransportTimeout,
    MockDecisionBehavior,
    MockDecisionMode,
    ReceiptError,
)
from channel_engine.gateway.http import (
    GatewayAdapterConfig,
    GatewayEnvironment,
    ProductionGatewayDisabled,
)
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayArtifactOutcomeUnknown,
    GatewayCircuitBreaker,
    GatewayCircuitBreakerPolicy,
    GatewayCircuitOpen,
    GatewayCircuitState,
    GatewayClient,
    GatewayClientInterface,
    GatewayCredentialUnavailable,
    GatewayServiceIdentity,
    GatewaySigningToken,
    MockAICSGateway,
    MockAICSGatewayTransport,
)
from channel_engine.gateway.sandbox import (
    SandboxTransportFault,
    ScriptedSandboxGatewayTransport,
)
from channel_engine.models import DecisionAction, EventType, ReceiptOutcome


NOW = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)
SECRET = b"ai-cs-gateway-integration-unit-secret-32"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="gateway-integration-key",
    credential_ref="vault://ai-cs/gateway/integration-key",
)


def decision_request(suffix: str = "1") -> DecisionRequest:
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id=f"gateway-integration-request-{suffix}",
        idempotency_key=f"gateway-integration-decision-{suffix}",
        correlation_id=f"gateway-integration-correlation-{suffix}",
        conversation_id=f"gateway-integration-conversation-{suffix}",
        message_id=f"gateway-integration-message-{suffix}",
        customer_message=f"Synthetic integration question {suffix}",
        context={"channel_name": "fake", "synthetic": True},
        requested_at=NOW,
    )


def execution_event() -> Event:
    return Event(
        contract_version=CONTRACT_VERSION,
        event_id="gateway-integration-event-1",
        correlation_id="gateway-integration-correlation-1",
        causation_id="gateway-integration-decision-1",
        source="CHANNEL_ENGINE",
        event_type=EventType.EXECUTION_UNKNOWN,
        aggregate_type=GatewayAggregateType.EXECUTION,
        aggregate_id="gateway-integration-execution-1",
        payload={"receipt_id": "gateway-integration-receipt-1"},
        occurred_at=NOW,
    )


def execution_receipt() -> ExecutionReceipt:
    return ExecutionReceipt(
        contract_version=CONTRACT_VERSION,
        receipt_id="gateway-integration-receipt-1",
        idempotency_key="gateway-integration-receipt-1",
        correlation_id="gateway-integration-correlation-1",
        execution_id="gateway-integration-execution-1",
        decision_id="gateway-integration-decision-1",
        attempt=1,
        outcome=ReceiptOutcome.UNKNOWN,
        external_reference=None,
        error=ReceiptError(
            code="EXECUTION_UNKNOWN",
            message="Synthetic result requires reconciliation",
            retryable=False,
        ),
        reconciliation_required=True,
        details={"real_channel_called": False},
        recorded_at=NOW,
    )


def build_client(
    *,
    server: MockAICSGateway | None = None,
    provider: FakeGatewayTokenProvider | None = None,
    transport=None,
    decision_retry_policy: GatewayRetryPolicy | None = None,
    artifact_retry_policy: GatewayRetryPolicy | None = None,
    circuit_breaker: GatewayCircuitBreaker | None = None,
    clock=lambda: NOW,
):
    active_server = server or MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=clock,
    )
    active_transport = transport or MockAICSGatewayTransport(active_server)
    active_provider = provider or FakeGatewayTokenProvider(
        {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
        clock=clock,
    )
    nonce = count(1)
    client = GatewayClient(
        active_transport,
        IDENTITY,
        active_provider,
        decision_retry_policy=decision_retry_policy,
        artifact_retry_policy=artifact_retry_policy,
        circuit_breaker=circuit_breaker,
        clock=clock,
        nonce_factory=lambda: f"realready{next(nonce):016d}",
        sleeper=lambda _delay: None,
    )
    return client, active_server, active_transport, active_provider


def test_gateway_client_supports_decision_event_receipt_and_health() -> None:
    client, server, _, provider = build_client()

    decision = client.request_decision(decision_request())
    event_ack = client.publish_event(execution_event())
    receipt_ack = client.send_execution_result(execution_receipt())
    health = client.health_check()

    assert isinstance(client, GatewayClientInterface)
    assert client.contract_version == CONTRACT_VERSION
    assert decision.action is DecisionAction.SUGGEST_REPLY
    assert decision.requires_approval is True
    assert event_ack.replayed is False
    assert receipt_ack.replayed is False
    assert health.status.value == "HEALTHY"
    assert server.decision_server.decision_compute_count == 1
    assert server.artifact_server.accept_count == 2
    assert provider.acquire_count == 4


def test_service_identity_and_token_provider_never_render_secret_material() -> None:
    secret_text = SECRET.decode()
    provider = FakeGatewayTokenProvider(
        {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
        clock=lambda: NOW,
    )
    token = provider.acquire(IDENTITY)

    assert "credential_ref" in IDENTITY.model_dump()
    assert "secret" not in IDENTITY.model_dump()
    assert secret_text not in repr(provider)
    assert secret_text not in repr(token)
    assert "<redacted>" in repr(token)
    assert "secret" not in inspect.signature(GatewayClient).parameters
    assert "secret" not in inspect.signature(GatewayClient.from_http).parameters
    with pytest.raises(ValueError, match="embedded secret"):
        GatewayServiceIdentity(
            client_id="channel-engine",
            key_id="key-1",
            credential_ref="vault://gateway/item?token=plaintext",
        )


def test_missing_or_wrong_signing_reference_fails_before_transport() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    transport = MockAICSGatewayTransport(server)
    client, _, _, _ = build_client(
        server=server,
        provider=FakeGatewayTokenProvider({}, clock=lambda: NOW),
        transport=transport,
        decision_retry_policy=GatewayRetryPolicy(max_attempts=1),
    )

    with pytest.raises(GatewayCredentialUnavailable):
        client.request_decision(decision_request("missing-credential"))
    assert transport.attempt_count == 0
    trace = client.trace_store.snapshot(
        "gateway-integration-correlation-missing-credential"
    )
    assert trace.entries[-1].error_code == "GATEWAY_CREDENTIAL_UNAVAILABLE"


class MutableClock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def test_circuit_breaker_opens_then_half_open_probe_recovers() -> None:
    clock = MutableClock()
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        decision_behavior=MockDecisionBehavior(MockDecisionMode.TIMEOUT),
        clock=clock,
    )
    breaker = GatewayCircuitBreaker(
        GatewayCircuitBreakerPolicy(
            failure_threshold=2,
            reset_timeout_seconds=30,
        ),
        clock=clock,
    )
    client, _, transport, _ = build_client(
        server=server,
        decision_retry_policy=GatewayRetryPolicy(max_attempts=1),
        circuit_breaker=breaker,
        clock=clock,
    )

    with pytest.raises(AICSGatewayTimeout):
        client.request_decision(decision_request("timeout-1"))
    with pytest.raises(AICSGatewayTimeout):
        client.request_decision(decision_request("timeout-2"))
    assert breaker.snapshot().state is GatewayCircuitState.OPEN
    attempts_before = transport.attempt_count

    with pytest.raises(GatewayCircuitOpen):
        client.request_decision(decision_request("circuit-open"))
    assert transport.attempt_count == attempts_before

    server.decision_server.queue_behaviors(
        (MockDecisionBehavior(MockDecisionMode.SUCCESS),)
    )
    clock.advance(31)
    recovered = client.request_decision(decision_request("half-open"))

    assert recovered.requires_approval is True
    assert breaker.snapshot().state is GatewayCircuitState.CLOSED
    assert breaker.snapshot().consecutive_failures == 0


def test_artifact_timeout_is_unknown_and_retries_only_same_artifact_id() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    base_transport = MockAICSGatewayTransport(server)
    scripted = ScriptedSandboxGatewayTransport(
        base_transport,
        (
            SandboxTransportFault.TIMEOUT,
            SandboxTransportFault.TIMEOUT,
            SandboxTransportFault.TIMEOUT,
        ),
    )
    client, _, _, _ = build_client(
        server=server,
        transport=scripted,
        artifact_retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
    )

    with pytest.raises(GatewayArtifactOutcomeUnknown) as raised:
        client.publish_event(execution_event())

    assert raised.value.artifact_id == execution_event().event_id
    assert raised.value.attempts == 3
    assert raised.value.outcome_unknown is True
    assert scripted.attempt_count == 3
    assert server.artifact_server.accept_count == 0


class CommitThenTimeoutTransport:
    """Simulate a lost response after the Gateway durably accepted the artifact."""

    def __init__(self, delegate: MockAICSGatewayTransport) -> None:
        self.delegate = delegate
        self.attempt_count = 0

    def request(self, **kwargs):
        self.attempt_count += 1
        response = self.delegate.request(**kwargs)
        if self.attempt_count == 1:
            raise GatewayTransportTimeout("response lost after durable acceptance")
        return response


def test_artifact_retry_after_commit_replays_same_id_without_duplicate_accept() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    transport = CommitThenTimeoutTransport(MockAICSGatewayTransport(server))
    client, _, _, _ = build_client(
        server=server,
        transport=transport,
        artifact_retry_policy=GatewayRetryPolicy(
            max_attempts=2,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
    )

    acknowledgement = client.publish_event(execution_event())

    assert acknowledgement.artifact_id == execution_event().event_id
    assert acknowledgement.replayed is True
    assert transport.attempt_count == 2
    assert server.artifact_server.accept_count == 1
    assert server.artifact_server.replay_count == 1


def test_from_http_keeps_production_default_deny_without_network_access() -> None:
    config = GatewayAdapterConfig(
        environment=GatewayEnvironment.PRODUCTION,
        base_url="https://gateway.example.invalid",
        client_id=IDENTITY.client_id,
        key_id=IDENTITY.key_id,
        production_enabled=False,
    )
    provider = FakeGatewayTokenProvider(
        {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
        clock=lambda: NOW,
    )

    with pytest.raises(ProductionGatewayDisabled):
        GatewayClient.from_http(config, IDENTITY, provider)
