from __future__ import annotations

from datetime import datetime, timezone

from channel_engine.gateway import (
    CONTRACT_VERSION,
    ErrorEnvelope,
    GatewayEdgeFault,
    GatewayErrorCode,
    GatewayRequestSigner,
    MockAICSServer,
    SandboxGatewayEdgeServer,
)
from channel_engine.gateway.client import GATEWAY_MEDIA_TYPE
from channel_engine.gateway.contract import DecisionRequest
from channel_engine.gateway.http import (
    GatewayAdapterConfig,
    GatewayEnvironment,
    HttpGatewayTransport,
)


NOW = datetime(2026, 8, 5, 15, 30, tzinfo=timezone.utc)
SECRET = b"gateway-edge-contract-secret-material-32"


def test_gateway_edge_403_is_frozen_error_envelope_over_real_http() -> None:
    server = MockAICSServer(
        {("channel-engine", "edge-contract-key"): SECRET},
        clock=lambda: NOW,
    )
    request = DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id="edge-contract-request",
        idempotency_key="edge-contract-idempotency",
        correlation_id="edge-contract-correlation",
        conversation_id="edge-contract-conversation",
        message_id="edge-contract-message",
        customer_message="Synthetic contract fixture",
        context={"synthetic": True},
        requested_at=NOW,
    )
    body = request.model_dump_json().encode("utf-8")
    signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="edge-contract-key",
        secret=SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: "edge-contract-nonce-00000001",
    )
    headers = signer.sign_decision(
        request,
        body,
        method="POST",
        path="/gateway/v1/decisions",
        content_type=GATEWAY_MEDIA_TYPE,
    )
    headers["Accept"] = GATEWAY_MEDIA_TYPE

    with SandboxGatewayEdgeServer(
        server,
        faults=(GatewayEdgeFault.AUTHORIZATION_DENIED,),
        clock=lambda: NOW,
    ) as edge:
        transport = HttpGatewayTransport(
            GatewayAdapterConfig(
                environment=GatewayEnvironment.MOCK,
                base_url=edge.base_url,
                client_id="channel-engine",
                key_id="edge-contract-key",
            )
        )
        try:
            response = transport.request(
                method="POST",
                path="/gateway/v1/decisions",
                body=body,
                headers=headers,
                timeout_seconds=0.5,
            )
        finally:
            transport.close()

    envelope = ErrorEnvelope.model_validate_json(response.body)
    assert response.status_code == 403
    assert response.headers["x-ai-cs-contract-version"] == CONTRACT_VERSION
    assert envelope.contract_version == CONTRACT_VERSION
    assert envelope.error.code is GatewayErrorCode.AUTHORIZATION_DENIED
    assert envelope.error.request_id == request.request_id
    assert envelope.error.correlation_id == request.correlation_id
    assert envelope.error.retryable is False
