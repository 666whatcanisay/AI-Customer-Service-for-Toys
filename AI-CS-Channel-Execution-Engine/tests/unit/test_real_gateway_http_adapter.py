from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from itertools import count

import httpx
import pytest

from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    CONTRACT_VERSION,
    DECISION_PATH,
    GATEWAY_MEDIA_TYPE,
    HEALTH_PATH,
    DecisionRequest,
    GatewayAdapterConfig,
    GatewayContractViolation,
    GatewayEnvironment,
    GatewayEnvironmentError,
    GatewayErrorCode,
    GatewayHealthStatus,
    GatewayRetryPolicy,
    GatewayUnavailable,
    HttpGatewayTransport,
    MockAICSServer,
    MockAICSServerTimeout,
    MockDecisionBehavior,
    MockDecisionMode,
    ProductionGatewayClient,
    ProductionGatewayDisabled,
    validate_gateway_environment,
)


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
HTTP_SECRET = b"real-gateway-http-foundation-secret-32"


def decision_request(**updates: object) -> DecisionRequest:
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "real-http-request-1",
        "idempotency_key": "real-http-decision-1",
        "correlation_id": "real-http-message-1",
        "conversation_id": "real-http-conversation-1",
        "message_id": "real-http-message-1",
        "customer_message": "Please check this order",
        "context": {"channel_name": "fake-pdd"},
        "requested_at": NOW,
    }
    values.update(updates)
    return DecisionRequest.model_validate(values)


def staging_config(**updates: object) -> GatewayAdapterConfig:
    values: dict[str, object] = {
        "environment": GatewayEnvironment.STAGING,
        "base_url": "https://staging.ai-cs.invalid",
        "client_id": "channel-engine",
        "key_id": "staging-key-1",
        "production_enabled": False,
        "timeout_seconds": 15,
    }
    values.update(updates)
    return GatewayAdapterConfig(**values)


def bridge_handler(
    server: MockAICSServer,
    requests: list[httpx.Request],
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        try:
            result = server.handle_request(
                method=request.method,
                path=request.url.path,
                body=request.content,
                headers=dict(request.headers),
            )
        except MockAICSServerTimeout as exc:
            raise httpx.ReadTimeout(
                "local mock AI-CS timed out",
                request=request,
            ) from exc
        return httpx.Response(
            status_code=result.status_code,
            content=result.body,
            headers=result.headers,
            request=request,
        )

    return handler


def http_gateway_client(
    server: MockAICSServer,
    *,
    config: GatewayAdapterConfig | None = None,
    policy: GatewayRetryPolicy | None = None,
) -> tuple[ProductionGatewayClient, httpx.Client, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    http_client = httpx.Client(
        transport=httpx.MockTransport(bridge_handler(server, requests)),
        follow_redirects=False,
    )
    nonce_sequence = count(1)
    gateway = ProductionGatewayClient(
        config or staging_config(),
        HTTP_SECRET,
        http_client=http_client,
        retry_policy=policy,
        clock=lambda: NOW,
        nonce_factory=lambda: f"realgw{next(nonce_sequence):016d}",
        sleeper=lambda _delay: None,
        random_source=lambda: 0.5,
    )
    return gateway, http_client, requests


def test_environment_defaults_to_loopback_mock_and_production_is_locked() -> None:
    default = GatewayAdapterConfig.from_env({})

    assert default.environment is GatewayEnvironment.MOCK
    assert default.base_url == "http://127.0.0.1:18021"
    assert default.production_enabled is False
    assert validate_gateway_environment(default).host == "127.0.0.1"
    assert "secret" not in repr(default).lower()

    production = GatewayAdapterConfig(
        environment=GatewayEnvironment.PRODUCTION,
        base_url="https://ai-cs.production.invalid",
        client_id="channel-engine",
        key_id="production-key-1",
    )
    with pytest.raises(ProductionGatewayDisabled):
        validate_gateway_environment(production)

    explicitly_enabled = GatewayAdapterConfig(
        environment=GatewayEnvironment.PRODUCTION,
        base_url="https://ai-cs.production.invalid",
        client_id="channel-engine",
        key_id="production-key-1",
        production_enabled=True,
    )
    assert validate_gateway_environment(explicitly_enabled).scheme == "https"

    calls = 0

    def no_request_expected(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    local_http = httpx.Client(
        transport=httpx.MockTransport(no_request_expected)
    )
    production_client = ProductionGatewayClient(
        explicitly_enabled,
        HTTP_SECRET,
        http_client=local_http,
    )
    try:
        assert production_client.environment is GatewayEnvironment.PRODUCTION
    finally:
        production_client.close()
        local_http.close()
    assert calls == 0


@pytest.mark.parametrize(
    ("environment", "base_url"),
    [
        (GatewayEnvironment.MOCK, "http://remote-mock.invalid"),
        (GatewayEnvironment.STAGING, "http://staging.ai-cs.invalid"),
        (GatewayEnvironment.STAGING, "https://user:pass@staging.invalid"),
        (GatewayEnvironment.STAGING, "https://staging.invalid/path"),
        (GatewayEnvironment.STAGING, "https://staging.invalid?query=yes"),
        (GatewayEnvironment.STAGING, "https://staging.invalid#fragment"),
    ],
)
def test_environment_rejects_unsafe_base_urls(
    environment: GatewayEnvironment,
    base_url: str,
) -> None:
    config = GatewayAdapterConfig(
        environment=environment,
        base_url=base_url,
        client_id="channel-engine",
        key_id="safe-key-1",
    )
    with pytest.raises(GatewayEnvironmentError):
        validate_gateway_environment(config)


def test_environment_loader_validates_values_without_loading_secrets() -> None:
    staging = GatewayAdapterConfig.from_env(
        {
            "CHANNEL_ENGINE_GATEWAY_ENVIRONMENT": "staging",
            "CHANNEL_ENGINE_GATEWAY_BASE_URL": "https://staging.ai-cs.invalid",
            "CHANNEL_ENGINE_GATEWAY_CLIENT_ID": "staging-client",
            "CHANNEL_ENGINE_GATEWAY_KEY_ID": "staging-key",
            "CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS": "12.5",
            "CHANNEL_ENGINE_GATEWAY_PRODUCTION_ENABLED": "false",
        }
    )
    assert staging.environment is GatewayEnvironment.STAGING
    assert staging.timeout_seconds == 12.5
    assert staging.production_enabled is False

    with pytest.raises(GatewayEnvironmentError):
        GatewayAdapterConfig.from_env(
            {"CHANNEL_ENGINE_GATEWAY_ENVIRONMENT": "unknown"}
        )
    with pytest.raises(GatewayEnvironmentError):
        GatewayAdapterConfig.from_env(
            {"CHANNEL_ENGINE_GATEWAY_PRODUCTION_ENABLED": "maybe"}
        )


@pytest.mark.parametrize(
    "config_values",
    [
        {"environment": "invalid"},
        {"base_url": ""},
        {"client_id": "contains spaces"},
        {"key_id": "contains spaces"},
        {"production_enabled": "true"},
        {"timeout_seconds": 0},
    ],
)
def test_adapter_config_rejects_invalid_values(
    config_values: dict[str, object],
) -> None:
    with pytest.raises(GatewayEnvironmentError):
        GatewayAdapterConfig(**config_values)


def test_production_gateway_client_maps_http_success_auth_and_health() -> None:
    server = MockAICSServer(
        {("channel-engine", "staging-key-1"): HTTP_SECRET},
        clock=lambda: NOW,
    )
    gateway, http_client, requests = http_gateway_client(server)
    try:
        response = gateway.request_decision(decision_request())
        health = gateway.health_check()
    finally:
        gateway.close()
        http_client.close()

    assert gateway.environment is GatewayEnvironment.STAGING
    assert response.requires_approval is True
    assert response.gateway_version == "mock-ai-cs.v1"
    assert server.request_count == 1
    assert len(requests) == 2
    decision_http_request = requests[0]
    assert decision_http_request.method == "POST"
    assert decision_http_request.url.path == DECISION_PATH
    assert decision_http_request.headers["content-type"] == GATEWAY_MEDIA_TYPE
    assert decision_http_request.headers["accept"] == GATEWAY_MEDIA_TYPE
    assert decision_http_request.headers["x-ai-cs-contract-version"] == "1.0"
    assert decision_http_request.headers["x-request-id"] == "real-http-request-1"
    assert decision_http_request.headers["authorization"].startswith(
        "HMAC-SHA256 Credential=channel-engine/staging-key-1,Signature="
    )
    health_http_request = requests[1]
    assert health_http_request.method == "GET"
    assert health_http_request.url.path == HEALTH_PATH
    assert health_http_request.content == b""
    assert "content-type" not in health_http_request.headers
    assert health_http_request.headers["authorization"].startswith(
        "HMAC-SHA256 Credential=channel-engine/staging-key-1,Signature="
    )
    assert health.status is GatewayHealthStatus.HEALTHY
    assert health.service == "mock-ai-cs"
    assert health.contract_version == CONTRACT_VERSION
    assert health.gateway_version == "mock-ai-cs.v1"
    assert health.capability_version == "decision.v1"
    assert health.real_ai_cs_connected is False


def test_http_error_envelope_maps_to_gateway_request_failure() -> None:
    server = MockAICSServer(
        {("channel-engine", "staging-key-1"): HTTP_SECRET},
        default_behavior=MockDecisionBehavior(
            MockDecisionMode.ERROR,
            error_code=GatewayErrorCode.AUTHORIZATION_DENIED,
        ),
        clock=lambda: NOW,
    )
    gateway, http_client, requests = http_gateway_client(server)
    try:
        with pytest.raises(AICSGatewayRequestFailed) as raised:
            gateway.request_decision(decision_request())
    finally:
        gateway.close()
        http_client.close()

    assert raised.value.status_code == 403
    assert raised.value.envelope.error.code is GatewayErrorCode.AUTHORIZATION_DENIED
    assert raised.value.attempts == 1
    assert len(requests) == 1


def test_http_timeout_maps_to_unknown_after_bounded_retries() -> None:
    server = MockAICSServer(
        {("channel-engine", "staging-key-1"): HTTP_SECRET},
        default_behavior=MockDecisionBehavior(MockDecisionMode.TIMEOUT),
        clock=lambda: NOW,
    )
    policy = GatewayRetryPolicy(
        max_attempts=2,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
        jitter_ratio=0,
    )
    gateway, http_client, requests = http_gateway_client(server, policy=policy)
    try:
        with pytest.raises(AICSGatewayTimeout) as raised:
            gateway.request_decision(decision_request())
    finally:
        gateway.close()
        http_client.close()

    assert raised.value.outcome_unknown is True
    assert raised.value.attempts == 2
    assert len(requests) == 2
    assert len({request.content for request in requests}) == 1
    assert len({request.headers["idempotency-key"] for request in requests}) == 1
    assert len({request.headers["x-ai-cs-nonce"] for request in requests}) == 2


def test_http_connect_error_maps_to_gateway_unavailable() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("local connection refused", request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    policy = GatewayRetryPolicy(
        max_attempts=2,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
        jitter_ratio=0,
    )
    gateway = ProductionGatewayClient(
        staging_config(),
        HTTP_SECRET,
        http_client=http_client,
        retry_policy=policy,
        clock=lambda: NOW,
        nonce_factory=lambda: "connecterrornonce00001",
        sleeper=lambda _delay: None,
    )
    try:
        with pytest.raises(GatewayUnavailable):
            gateway.request_decision(decision_request())
    finally:
        gateway.close()
        http_client.close()
    assert attempts == 2


def test_http_schema_and_redirect_fail_closed_without_following_redirects() -> None:
    request_model = decision_request()

    def invalid_schema(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"{}",
            headers={
                "X-AI-CS-Contract-Version": CONTRACT_VERSION,
                "X-Request-ID": request_model.request_id,
                "X-Correlation-ID": request_model.correlation_id,
                "Idempotency-Replayed": "false",
            },
            request=request,
        )

    invalid_client = httpx.Client(transport=httpx.MockTransport(invalid_schema))
    invalid_gateway = ProductionGatewayClient(
        staging_config(),
        HTTP_SECRET,
        http_client=invalid_client,
        clock=lambda: NOW,
        nonce_factory=lambda: "invalidschemanonce0001",
        sleeper=lambda _delay: None,
    )
    try:
        with pytest.raises(GatewayContractViolation):
            invalid_gateway.request_decision(request_model)
    finally:
        invalid_gateway.close()
        invalid_client.close()

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            307,
            headers={"Location": "https://elsewhere.invalid"},
            request=request,
        )

    redirect_client = httpx.Client(transport=httpx.MockTransport(redirect))
    transport = HttpGatewayTransport(staging_config(), client=redirect_client)
    try:
        with pytest.raises(GatewayContractViolation):
            transport.request(
                method="POST",
                path=DECISION_PATH,
                body=b"{}",
                headers={},
                timeout_seconds=15,
            )
    finally:
        transport.close()
        redirect_client.close()


@pytest.mark.parametrize(
    "health_payload",
    [
        {
            "status": "HEALTHY",
            "service": "local-ai-cs",
            "contract_version": "2.0",
            "gateway_version": "local.v1",
            "capability_version": "decision.v1",
            "reachable": True,
            "real_ai_cs_connected": False,
            "checked_at": "2026-08-04T12:00:00Z",
            "details": {},
        },
        {
            "status": "HEALTHY",
            "service": "local-ai-cs",
            "contract_version": "1.0",
            "gateway_version": "local.v1",
            "capability_version": None,
            "reachable": True,
            "real_ai_cs_connected": False,
            "checked_at": "2026-08-04T12:00:00Z",
            "details": {},
        },
    ],
)
def test_health_rejects_contract_or_capability_version(
    health_payload: dict[str, object],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(health_payload).encode(),
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = ProductionGatewayClient(
        staging_config(),
        HTTP_SECRET,
        http_client=http_client,
        clock=lambda: NOW,
        nonce_factory=lambda: "healthchecknonce000001",
        sleeper=lambda _delay: None,
    )
    try:
        health = gateway.health_check()
    finally:
        gateway.close()
        http_client.close()
    assert health.status is GatewayHealthStatus.UNHEALTHY
    assert health.reachable is False


def test_http_transport_rejects_non_contract_path_before_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = HttpGatewayTransport(staging_config(), client=http_client)
    try:
        with pytest.raises(GatewayContractViolation):
            transport.request(
                method="POST",
                path="gateway/v1/decisions?unsafe=true",
                body=b"{}",
                headers={},
                timeout_seconds=15,
            )
    finally:
        transport.close()
        http_client.close()
    assert calls == 0
