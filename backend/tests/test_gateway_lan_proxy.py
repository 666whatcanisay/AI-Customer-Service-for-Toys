from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.gateway.lan_proxy import (
    GatewayLanProxyConfig,
    create_gateway_lan_proxy_app,
)


def _config(**overrides) -> GatewayLanProxyConfig:
    values = {
        "bind_address": "192.168.1.11",
        "port": 18080,
        "interface_network": "192.168.1.0/24",
        "allowed_networks": ["192.168.1.0/24"],
        "upstream_origin": "http://127.0.0.1:8000",
    }
    values.update(overrides)
    return GatewayLanProxyConfig.build(**values)


def test_gateway_lan_config_rejects_wildcard_public_and_non_loopback_upstream() -> None:
    for address in ("0.0.0.0", "127.0.0.1", "8.8.8.8"):
        with pytest.raises(ValueError, match="private IPv4"):
            _config(bind_address=address)

    with pytest.raises(ValueError, match="private IPv4 CIDRs"):
        _config(allowed_networks=["8.8.8.0/24"])
    with pytest.raises(ValueError, match="loopback HTTP origin"):
        _config(upstream_origin="http://192.168.1.11:8000")
    with pytest.raises(ValueError, match="within the interface network"):
        _config(allowed_networks=["192.168.0.0/16"])


def test_gateway_lan_edge_forwards_raw_signed_request_and_contract_response() -> None:
    observed: dict[str, object] = {}

    def upstream(request: httpx.Request) -> httpx.Response:
        observed.update(
            method=request.method,
            path=request.url.path,
            body=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            200,
            content=b'{"contract_version":"1.0","status":"HEALTHY"}',
            headers={
                "Content-Type": "application/vnd.ai-cs.channel-engine.gateway-v1+json",
                "X-AI-CS-Contract-Version": "1.0",
                "X-Request-ID": "req-001",
                "Server": "must-not-cross-edge",
            },
        )

    app = create_gateway_lan_proxy_app(
        _config(),
        transport=httpx.MockTransport(upstream),
        client_host_resolver=lambda _: "192.168.1.50",
    )
    body = b'{"contract_version":"1.0","message":"hello"}'
    headers = {
        "Authorization": "HMAC-SHA256 Credential=agent/key,Signature=signed",
        "Content-Type": "application/json",
        "Idempotency-Key": "idem-001",
        "X-AI-CS-Content-SHA256": "body-hash",
        "X-AI-CS-Contract-Version": "1.0",
        "X-AI-CS-Nonce": "nonce-001",
        "X-AI-CS-Timestamp": "2026-08-05T00:00:00Z",
        "X-Correlation-ID": "corr-001",
        "X-Request-ID": "req-001",
        "X-Unapproved-Header": "must-not-cross-edge",
    }

    with TestClient(app) as client:
        response = client.post("/gateway/v1/decisions", content=body, headers=headers)

    assert response.status_code == 200
    assert response.content == b'{"contract_version":"1.0","status":"HEALTHY"}'
    assert response.headers["x-ai-cs-contract-version"] == "1.0"
    assert "server" not in response.headers
    assert observed["method"] == "POST"
    assert observed["path"] == "/gateway/v1/decisions"
    assert observed["body"] == body
    forwarded_headers = observed["headers"]
    assert isinstance(forwarded_headers, dict)
    assert forwarded_headers["authorization"] == headers["Authorization"]
    assert forwarded_headers["x-ai-cs-nonce"] == headers["X-AI-CS-Nonce"]
    assert "x-unapproved-header" not in forwarded_headers


def test_gateway_lan_edge_rejects_unapproved_source_path_and_query() -> None:
    upstream_calls = 0

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200, json={"unexpected": True})

    source = {"host": "10.1.2.3"}
    app = create_gateway_lan_proxy_app(
        _config(),
        transport=httpx.MockTransport(upstream),
        client_host_resolver=lambda _: source["host"],
    )

    with TestClient(app) as denied_client:
        denied = denied_client.get(
            "/gateway/v1/health", headers={"X-Forwarded-For": "192.168.1.50"}
        )
    assert denied.status_code == 403
    assert denied.json()["error"]["error_code"] == "AUTHORIZATION_DENIED"

    source["host"] = "192.168.1.50"
    with TestClient(app) as allowed_client:
        hidden_api = allowed_client.post("/api/chat", json={"message": "blocked"})
        unknown_gateway = allowed_client.get("/gateway/v1/openapi")
        trailing_slash = allowed_client.get("/gateway/v1/health/")
        query = allowed_client.get("/gateway/v1/health?debug=true")

    assert hidden_api.status_code == 404
    assert unknown_gateway.status_code == 404
    assert unknown_gateway.json()["error"]["error_code"] == "RESOURCE_NOT_FOUND"
    assert trailing_slash.status_code == 404
    assert trailing_slash.json()["error"]["error_code"] == "RESOURCE_NOT_FOUND"
    assert query.status_code == 400
    assert query.json()["error"]["error_code"] == "INVALID_REQUEST"
    assert upstream_calls == 0


def test_gateway_lan_edge_returns_error_envelope_when_core_is_unavailable() -> None:
    def upstream(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    app = create_gateway_lan_proxy_app(
        _config(),
        transport=httpx.MockTransport(upstream),
        client_host_resolver=lambda _: "192.168.1.50",
    )
    with TestClient(app) as client:
        response = client.get("/gateway/v1/health")

    payload = json.loads(response.content)
    assert response.status_code == 503
    assert payload["contract_version"] == "1.0"
    assert payload["error"]["error_code"] == "SERVICE_UNAVAILABLE"
    assert payload["error"]["retryable"] is True
