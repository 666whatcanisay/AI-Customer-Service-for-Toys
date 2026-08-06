from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

import pytest
from pydantic import ValidationError

from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    CONTRACT_VERSION,
    DecisionRequest,
    GatewayContractViolation,
    GatewayErrorCode,
    GatewayRetryPolicy,
    MockDecisionBehavior,
    MockDecisionMode,
)
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayClient,
    GatewayServiceIdentity,
    MockAICSGateway,
    MockAICSGatewayCompatibility,
    MockAICSGatewayTransport,
)


NOW = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
SECRET = b"ai-cs-gateway-integration-contract-secret"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="contract-key",
    credential_ref="vault://ai-cs/gateway/contract-key",
)


def request() -> DecisionRequest:
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id="real-ready-contract-request",
        idempotency_key="real-ready-contract-decision",
        correlation_id="real-ready-contract-correlation",
        conversation_id="real-ready-contract-conversation",
        message_id="real-ready-contract-message",
        customer_message="Synthetic contract compatibility request",
        context={"channel_name": "fake"},
        requested_at=NOW,
    )


def client_for(
    server: MockAICSGateway,
    *,
    signing_secret: bytes = SECRET,
) -> GatewayClient:
    nonce = count(1)
    return GatewayClient(
        MockAICSGatewayTransport(server),
        IDENTITY,
        FakeGatewayTokenProvider(
            {IDENTITY.credential_ref: (IDENTITY.key_id, signing_secret)},
            clock=lambda: NOW,
        ),
        decision_retry_policy=GatewayRetryPolicy(
            max_attempts=1,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        clock=lambda: NOW,
        nonce_factory=lambda: f"contract{next(nonce):016d}",
        sleeper=lambda _delay: None,
    )


def test_contract_uses_frozen_contract_version_not_schema_version_alias() -> None:
    payload = request().model_dump(mode="json")
    payload["schema_version"] = payload.pop("contract_version")

    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(payload)


def test_mock_gateway_normal_response_is_contract_compatible() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    response = client_for(server).request_decision(request())

    assert response.contract_version == CONTRACT_VERSION
    assert response.request_id == request().request_id
    assert response.idempotency_key == request().idempotency_key
    assert response.correlation_id == request().correlation_id
    assert response.requires_approval is True


def test_mock_gateway_incompatible_version_fails_closed() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        compatibility=MockAICSGatewayCompatibility.INCOMPATIBLE_VERSION,
        clock=lambda: NOW,
    )

    with pytest.raises(GatewayContractViolation):
        client_for(server).request_decision(request())


def test_mock_gateway_error_is_valid_error_envelope() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        decision_behavior=MockDecisionBehavior(
            MockDecisionMode.ERROR,
            error_code=GatewayErrorCode.AUTHORIZATION_DENIED,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(AICSGatewayRequestFailed) as raised:
        client_for(server).request_decision(request())

    assert raised.value.status_code == 403
    assert raised.value.envelope.contract_version == CONTRACT_VERSION
    assert raised.value.envelope.error.code is GatewayErrorCode.AUTHORIZATION_DENIED
    assert raised.value.envelope.error.retryable is False


def test_invalid_signature_is_rejected_without_secret_disclosure() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )

    with pytest.raises(AICSGatewayRequestFailed) as raised:
        client_for(
            server,
            signing_secret=b"wrong-ai-cs-gateway-contract-secret-32",
        ).request_decision(request())

    assert raised.value.status_code == 401
    assert raised.value.envelope.error.code is GatewayErrorCode.AUTHENTICATION_FAILED
    serialized = raised.value.envelope.model_dump_json()
    assert SECRET.decode() not in serialized
    assert "wrong-ai-cs-gateway-contract-secret" not in serialized
