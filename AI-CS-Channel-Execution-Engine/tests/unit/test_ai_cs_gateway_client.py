from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from itertools import count

import pytest

from channel_engine.gateway import (
    AICSGatewayClient,
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    CONTRACT_VERSION,
    DECISION_PATH,
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    GatewayContractViolation,
    GatewayErrorCode,
    GatewayHealthStatus,
    GatewayRiskLevel,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    GatewayTransportResponse,
    GatewayUnavailable,
    IdempotencyConflict,
    MockAICSServer,
    MockAICSTransport,
    MockDecisionBehavior,
    MockDecisionMode,
    canonical_gateway_body,
)
from channel_engine.models import DecisionAction


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
MOCK_SECRET = b"foundation-mock-secret-material-32b"


def decision_request(**updates: object) -> DecisionRequest:
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "client-request-1",
        "idempotency_key": "decision-message-1",
        "correlation_id": "message-1",
        "conversation_id": "conversation-1",
        "message_id": "message-1",
        "customer_message": "Where is my order?",
        "context": {"channel_name": "fake-pdd", "sender": "buyer-1"},
        "requested_at": NOW,
    }
    values.update(updates)
    return DecisionRequest.model_validate(values)


def signer(prefix: str = "noncea") -> GatewayRequestSigner:
    sequence = count(1)
    return GatewayRequestSigner(
        client_id="channel-engine",
        key_id="mock-key-1",
        secret=MOCK_SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: f"{prefix}{next(sequence):016d}",
    )


def test_production_v1_hmac_known_vector() -> None:
    fixed = GatewayRequestSigner(
        client_id="agent-01",
        key_id="key-01",
        secret=b"0123456789abcdef0123456789abcdef",
        clock=lambda: datetime(2026, 8, 5, tzinfo=timezone.utc),
        nonce_factory=lambda: "bm9uY2UtZm9yLXRlc3QtMDAx",
    )
    headers = fixed.sign(
        b'{"contract_version":"1.0"}',
        method="POST",
        path="/gateway/v1/decisions",
        request_id="req-001",
        correlation_id="corr-001",
        idempotency_key="idem-001",
        content_type="application/json",
    )

    assert headers["X-AI-CS-Content-SHA256"] == (
        "84786626e94027a1c329b242d5c4c35eb285e80bd77cebb15c81fdb729c03227"
    )
    assert headers["Authorization"] == (
        "HMAC-SHA256 Credential=agent-01/key-01,"
        "Signature=FYWXv1salDMEWFLncJVmokCssvS0fdTEbhyxOAuC9uc"
    )


def client_for(
    server: MockAICSServer,
    *,
    nonce_prefix: str = "noncea",
    policy: GatewayRetryPolicy | None = None,
    sleeps: list[float] | None = None,
) -> tuple[AICSGatewayClient, MockAICSTransport]:
    transport = MockAICSTransport(server)
    client = AICSGatewayClient(
        transport,
        signer(nonce_prefix),
        retry_policy=policy
        or GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=(sleeps.append if sleeps is not None else lambda _delay: None),
        random_source=lambda: 0.5,
    )
    return client, transport


def mock_server(
    behavior: MockDecisionBehavior | None = None,
) -> MockAICSServer:
    return MockAICSServer(
        {("channel-engine", "mock-key-1"): MOCK_SECRET},
        default_behavior=behavior,
        clock=lambda: NOW,
    )


def test_client_success_health_and_local_idempotent_replay() -> None:
    server = mock_server()
    client, transport = client_for(server)
    request = decision_request()

    response = client.request_decision(request)
    replay = client.decide(request)
    health = client.health_check()

    assert response == replay
    assert response.requires_approval is True
    assert response.gateway_version == "mock-ai-cs.v1"
    assert response.metadata == {
        "mode": "MOCK",
        "real_ai_cs_called": False,
        "automatic_execution_authorized": False,
    }
    assert server.request_count == 1
    assert server.decision_compute_count == 1
    assert client.request_attempt_count == 1
    assert client.cache_replay_count == 1
    assert len(transport.attempts) == 2
    assert transport.attempts[0].path == DECISION_PATH
    assert transport.attempts[0].timeout_seconds == 15
    assert health.status is GatewayHealthStatus.HEALTHY
    assert health.reachable is True
    assert health.real_ai_cs_connected is False
    assert server.health_check_count == 1

    with pytest.raises(IdempotencyConflict):
        client.request_decision(
            decision_request(customer_message="Different request body")
        )
    assert server.request_count == 1


def test_mock_server_replays_across_clients_and_rejects_conflict() -> None:
    server = mock_server()
    first_client, _ = client_for(server, nonce_prefix="noncea")
    replay_client, _ = client_for(server, nonce_prefix="nonceb")
    conflict_client, _ = client_for(server, nonce_prefix="noncec")
    request = decision_request()

    first = first_client.request_decision(request)
    replay = replay_client.request_decision(request)

    assert replay == first
    assert server.request_count == 2
    assert server.decision_compute_count == 1
    assert server.replay_count == 1

    with pytest.raises(AICSGatewayRequestFailed) as raised:
        conflict_client.request_decision(
            decision_request(customer_message="Conflicting payload")
        )
    assert raised.value.status_code == 409
    assert raised.value.envelope.error.code is GatewayErrorCode.IDEMPOTENCY_CONFLICT
    assert raised.value.attempts == 1
    assert server.decision_compute_count == 1


def test_retryable_error_reuses_body_identity_then_succeeds() -> None:
    server = mock_server()
    server.queue_behaviors(
        [
            MockDecisionBehavior(
                MockDecisionMode.ERROR,
                error_code=GatewayErrorCode.SERVICE_UNAVAILABLE,
            )
        ]
    )
    sleeps: list[float] = []
    client, transport = client_for(
        server,
        policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=1,
            max_backoff_seconds=1,
            jitter_ratio=0,
        ),
        sleeps=sleeps,
    )

    response = client.request_decision(decision_request())

    assert response.action is DecisionAction.SUGGEST_REPLY
    assert server.request_count == 2
    assert server.error_count == 1
    assert server.decision_compute_count == 1
    assert client.retry_count == 1
    assert sleeps == [1]
    assert len({attempt.body_sha256 for attempt in transport.attempts}) == 1
    assert len({attempt.request_id for attempt in transport.attempts}) == 1
    assert len({attempt.idempotency_key for attempt in transport.attempts}) == 1
    assert len({attempt.nonce for attempt in transport.attempts}) == 2


def test_rate_limit_retry_respects_retry_after() -> None:
    server = mock_server()
    server.queue_behaviors(
        [
            MockDecisionBehavior(
                MockDecisionMode.ERROR,
                error_code=GatewayErrorCode.RATE_LIMITED,
                retry_after_seconds=7,
            )
        ]
    )
    sleeps: list[float] = []
    client, _ = client_for(server, sleeps=sleeps)

    client.request_decision(decision_request())

    assert sleeps == [7]
    assert client.retry_count == 1


def test_non_retryable_error_preserves_valid_error_envelope() -> None:
    server = mock_server(
        MockDecisionBehavior(
            MockDecisionMode.ERROR,
            error_code=GatewayErrorCode.AUTHORIZATION_DENIED,
        )
    )
    client, _ = client_for(server)

    with pytest.raises(AICSGatewayRequestFailed) as raised:
        client.request_decision(decision_request())

    assert raised.value.status_code == 403
    assert raised.value.envelope.error.retryable is False
    assert raised.value.attempts == 1
    assert server.request_count == 1
    assert client.retry_count == 0


def test_timeout_exhaustion_is_unknown_and_reuses_original_request() -> None:
    server = mock_server(MockDecisionBehavior(MockDecisionMode.TIMEOUT))
    sleeps: list[float] = []
    client, transport = client_for(server, sleeps=sleeps)

    with pytest.raises(AICSGatewayTimeout) as raised:
        client.request_decision(decision_request())

    assert raised.value.attempts == 3
    assert raised.value.outcome_unknown is True
    assert server.request_count == 3
    assert server.timeout_count == 3
    assert server.decision_compute_count == 0
    assert client.retry_count == 2
    assert sleeps == [0, 0]
    assert len({attempt.body_sha256 for attempt in transport.attempts}) == 1
    assert len({attempt.idempotency_key for attempt in transport.attempts}) == 1


def test_timeout_after_commit_is_recovered_by_idempotent_replay() -> None:
    server = mock_server()
    server.queue_behaviors(
        [
            MockDecisionBehavior(
                MockDecisionMode.TIMEOUT,
                commit_before_timeout=True,
            )
        ]
    )
    client, transport = client_for(server)

    response = client.request_decision(decision_request())

    assert response.gateway_version == "mock-ai-cs.v1"
    assert server.request_count == 2
    assert server.timeout_count == 1
    assert server.decision_compute_count == 1
    assert server.replay_count == 1
    assert len(transport.attempts) == 2


class StaticTransport:
    def __init__(self, response: GatewayTransportResponse) -> None:
        self.response = response
        self.call_count = 0

    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        self.call_count += 1
        return self.response


def test_client_rejects_invalid_success_schema_and_identity() -> None:
    request = decision_request()
    headers = {
        "X-AI-CS-Contract-Version": CONTRACT_VERSION,
        "X-Request-ID": request.request_id,
        "X-Correlation-ID": request.correlation_id,
        "Idempotency-Replayed": "false",
    }
    invalid_schema = StaticTransport(
        GatewayTransportResponse(200, b'{"contract_version":"1.0"}', headers)
    )
    client = AICSGatewayClient(invalid_schema, signer(), sleeper=lambda _delay: None)
    with pytest.raises(GatewayContractViolation):
        client.request_decision(request)

    wrong_identity = DecisionResponse(
        contract_version=CONTRACT_VERSION,
        request_id="another-request",
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
        decision_id="decision-wrong-identity",
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="Draft",
        requires_approval=True,
        risk_level=GatewayRiskLevel.LOW,
        gateway_version="mock-ai-cs.v1",
        metadata={},
        decided_at=NOW,
    )
    mismatched = StaticTransport(
        GatewayTransportResponse(
            200,
            wrong_identity.model_dump_json().encode("utf-8"),
            headers,
        )
    )
    client = AICSGatewayClient(mismatched, signer(), sleeper=lambda _delay: None)
    with pytest.raises(GatewayContractViolation):
        client.request_decision(request)


def test_client_rejects_non_contract_error_body() -> None:
    transport = StaticTransport(GatewayTransportResponse(503, b"{}", {}))
    client = AICSGatewayClient(transport, signer(), sleeper=lambda _delay: None)

    with pytest.raises(GatewayContractViolation):
        client.request_decision(decision_request())
    assert transport.call_count == 1


def test_mock_server_validates_authentication_and_request_schema() -> None:
    server = mock_server()
    wrong_signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="mock-key-1",
        secret=b"wrong-foundation-secret-material-32",
        clock=lambda: NOW,
        nonce_factory=lambda: "wrongnonce000000000000",
    )
    bad_client = AICSGatewayClient(
        MockAICSTransport(server),
        wrong_signer,
        sleeper=lambda _delay: None,
    )
    with pytest.raises(AICSGatewayRequestFailed) as raised:
        bad_client.request_decision(decision_request())
    assert raised.value.envelope.error.code is GatewayErrorCode.AUTHENTICATION_FAILED
    assert raised.value.attempts == 1

    request = decision_request(request_id="client-request-schema")
    invalid_payload = request.model_dump(mode="json")
    invalid_payload["unexpected"] = True
    invalid_body = json.dumps(invalid_payload, separators=(",", ":")).encode()
    valid_signer = signer("schemax")
    response = MockAICSTransport(server).request(
        method="POST",
        path=DECISION_PATH,
        body=invalid_body,
        headers=valid_signer.sign_decision(
            request,
            invalid_body,
            method="POST",
            path=DECISION_PATH,
        ),
        timeout_seconds=15,
    )
    envelope = ErrorEnvelope.model_validate_json(response.body)
    assert response.status_code == 422
    assert envelope.error.code is GatewayErrorCode.SCHEMA_VALIDATION_FAILED


def test_mock_server_rejects_route_media_auth_version_json_and_nonce_replay() -> None:
    server = mock_server()
    transport = MockAICSTransport(server)
    request = decision_request(request_id="client-request-boundaries")
    body = canonical_gateway_body(request)
    request_signer = signer("bounds")

    cases = (
        transport.request(
            method="POST",
            path="/gateway/v1/missing",
            body=body,
            headers={},
            timeout_seconds=15,
        ),
        transport.request(
            method="GET",
            path=DECISION_PATH,
            body=body,
            headers={},
            timeout_seconds=15,
        ),
        transport.request(
            method="POST",
            path=DECISION_PATH,
            body=b"x" * (64 * 1024 + 1),
            headers={},
            timeout_seconds=15,
        ),
        transport.request(
            method="POST",
            path=DECISION_PATH,
            body=body,
            headers={},
            timeout_seconds=15,
        ),
        transport.request(
            method="POST",
            path=DECISION_PATH,
            body=body,
            headers={"Content-Type": "application/json"},
            timeout_seconds=15,
        ),
    )
    assert [response.status_code for response in cases] == [404, 405, 413, 415, 401]
    assert [
        ErrorEnvelope.model_validate_json(response.body).error.code
        for response in cases
    ] == [
        GatewayErrorCode.RESOURCE_NOT_FOUND,
        GatewayErrorCode.METHOD_NOT_ALLOWED,
        GatewayErrorCode.PAYLOAD_TOO_LARGE,
        GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE,
        GatewayErrorCode.AUTHENTICATION_REQUIRED,
    ]

    version_headers = request_signer.sign_decision(
        request,
        body,
        method="POST",
        path=DECISION_PATH,
    )
    version_headers["X-AI-CS-Contract-Version"] = "2.0"
    version_response = transport.request(
        method="POST",
        path=DECISION_PATH,
        body=body,
        headers=version_headers,
        timeout_seconds=15,
    )
    assert version_response.status_code == 406

    malformed_body = b"{"
    malformed_response = transport.request(
        method="POST",
        path=DECISION_PATH,
        body=malformed_body,
        headers=request_signer.sign_decision(
            request,
            malformed_body,
            method="POST",
            path=DECISION_PATH,
        ),
        timeout_seconds=15,
    )
    assert malformed_response.status_code == 400

    replay_headers = request_signer.sign_decision(
        request,
        body,
        method="POST",
        path=DECISION_PATH,
    )
    first = transport.request(
        method="POST",
        path=DECISION_PATH,
        body=body,
        headers=replay_headers,
        timeout_seconds=15,
    )
    nonce_replay = transport.request(
        method="POST",
        path=DECISION_PATH,
        body=body,
        headers=replay_headers,
        timeout_seconds=15,
    )
    assert first.status_code == 200
    assert nonce_replay.status_code == 401
    assert (
        ErrorEnvelope.model_validate_json(nonce_replay.body).error.code
        is GatewayErrorCode.AUTHENTICATION_FAILED
    )


def test_client_retries_transport_unavailable_and_health_non_200_fails_closed() -> None:
    unavailable_transport = MockAICSTransport(mock_server(), unavailable=True)
    sleeps: list[float] = []
    client = AICSGatewayClient(
        unavailable_transport,
        signer(),
        retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=sleeps.append,
    )
    with pytest.raises(GatewayUnavailable):
        client.request_decision(decision_request())
    assert client.request_attempt_count == 3
    assert client.retry_count == 2
    assert sleeps == [0, 0]

    unhealthy_client, _ = client_for(
        MockAICSServer(
            {("channel-engine", "mock-key-1"): MOCK_SECRET},
            clock=lambda: NOW,
            healthy=False,
        )
    )
    health = unhealthy_client.health_check()
    assert health.status is GatewayHealthStatus.UNHEALTHY
    assert health.details == {"failure_type": "GatewayContractViolation"}


def test_client_rejects_error_status_and_retry_after_mismatch() -> None:
    server = mock_server(
        MockDecisionBehavior(
            MockDecisionMode.ERROR,
            error_code=GatewayErrorCode.RATE_LIMITED,
            retry_after_seconds=7,
        )
    )
    request = decision_request(request_id="client-request-error-mismatch")
    body = canonical_gateway_body(request)
    response = MockAICSTransport(server).request(
        method="POST",
        path=DECISION_PATH,
        body=body,
        headers=signer("errhdr").sign_decision(
            request,
            body,
            method="POST",
            path=DECISION_PATH,
        ),
        timeout_seconds=15,
    )

    bad_status = StaticTransport(
        GatewayTransportResponse(503, response.body, response.headers)
    )
    with pytest.raises(GatewayContractViolation):
        AICSGatewayClient(
            bad_status,
            signer("badsta"),
            sleeper=lambda _delay: None,
        ).request_decision(request)

    bad_retry_headers = dict(response.headers)
    bad_retry_headers["Retry-After"] = "6"
    bad_retry_after = StaticTransport(
        GatewayTransportResponse(429, response.body, bad_retry_headers)
    )
    with pytest.raises(GatewayContractViolation):
        AICSGatewayClient(
            bad_retry_after,
            signer("badret"),
            sleeper=lambda _delay: None,
        ).request_decision(request)


def test_health_check_fails_closed_when_mock_transport_is_unavailable() -> None:
    transport = MockAICSTransport(mock_server(), unavailable=True)
    client = AICSGatewayClient(transport, signer(), sleeper=lambda _delay: None)

    health = client.health_check()

    assert health.status is GatewayHealthStatus.UNHEALTHY
    assert health.reachable is False
    assert health.real_ai_cs_connected is False
    assert health.details == {"failure_type": "GatewayTransportError"}


def test_gateway_retry_policy_cannot_exceed_contract_limit() -> None:
    with pytest.raises(ValueError):
        GatewayRetryPolicy(max_attempts=4)
    with pytest.raises(ValueError):
        GatewayRetryPolicy(base_backoff_seconds=2, max_backoff_seconds=1)
    with pytest.raises(ValueError):
        MockDecisionBehavior(
            MockDecisionMode.SUCCESS,
            commit_before_timeout=True,
        )

    request = decision_request()
    assert DecisionRequest.model_validate_json(canonical_gateway_body(request)) == request
