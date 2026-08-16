from __future__ import annotations

from datetime import datetime, timezone

from channel_engine.gateway import SandboxGatewayEdgeServer
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayServiceIdentity,
    MockAICSGateway,
)


NOW = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
SECRET = b"gateway-edge-security-secret-material-32"


def test_edge_evidence_and_credential_repr_do_not_expose_sensitive_values() -> None:
    identity = GatewayServiceIdentity(
        client_id="channel-engine",
        key_id="gateway-edge-security-key",
        credential_ref="vault://ai-cs/gateway/edge-security",
    )
    provider = FakeGatewayTokenProvider(
        {identity.credential_ref: (identity.key_id, SECRET)},
        clock=lambda: NOW,
    )
    server = MockAICSGateway(
        {(identity.client_id, identity.key_id): SECRET},
        clock=lambda: NOW,
    )

    with SandboxGatewayEdgeServer(server, clock=lambda: NOW) as edge:
        assert edge.base_url.startswith("http://127.0.0.1:")

    rendered = repr(provider)
    assert SECRET.decode("utf-8") not in rendered
    assert "material=<redacted>" in rendered
    assert set(provider.__dict__) == {"_tokens", "_ttl", "_clock", "acquire_count"}


def test_edge_request_schema_cannot_store_auth_value_or_payload() -> None:
    from channel_engine.gateway.edge import GatewayEdgeRequest

    fields = set(GatewayEdgeRequest.model_fields)
    assert "authorization" not in fields
    assert "headers" not in fields
    assert "body" not in fields
    assert "payload" not in fields
    assert "customer_message" not in fields
    assert "authorization_present" in fields
