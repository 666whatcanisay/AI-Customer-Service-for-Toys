from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from channel_engine.channel import FakePDDAdapter, FakePDDInboundMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionWorker,
    FakeExecutionAdapter,
)
from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    AICSScope,
    CONTRACT_VERSION,
    DECISION_PATH,
    HEALTH_PATH,
    DecisionRequest,
    GatewayAdapterConfig,
    GatewayEnvironment,
    GatewayErrorCode,
    GatewayHealthStatus,
    GatewayRetryPolicy,
    ProductionGatewayClient,
)
from channel_engine.models import (
    DecisionState,
    EventType,
    ExecutionState,
    MessageState,
    OutboxState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)
from channel_engine.models.entities import utc_now
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage.orm import EventRow


CONTROLLED_SECRET = b"controlled-ai-cs-integration-secret-32-bytes"
CONTROLLED_SCOPE = AICSScope(
    tenant_id="TENANT-SYNTHETIC",
    platform="pdd",
    store_code="STORE-SYNTHETIC",
    product_id="PRODUCT-SYNTHETIC",
    sku_id=None,
)


@dataclass(frozen=True, slots=True)
class RealServer:
    base_url: str
    process: subprocess.Popen[str]


@dataclass(slots=True)
class ClientBundle:
    gateway: ProductionGatewayClient
    http_client: httpx.Client
    requests: list[dict[str, object]]
    responses: list[dict[str, object]]

    def close(self) -> None:
        self.gateway.close()
        self.http_client.close()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _redacted_headers(headers: httpx.Headers) -> dict[str, str]:
    selected = {
        name: value
        for name, value in headers.items()
        if name.lower()
        in {
            "authorization",
            "content-type",
            "accept",
            "x-ai-cs-contract-version",
            "x-request-id",
            "x-correlation-id",
            "idempotency-key",
            "idempotency-replayed",
        }
    }
    authorization = selected.get("authorization")
    if authorization and "Signature=" in authorization:
        selected["authorization"] = (
            authorization.split("Signature=", 1)[0] + "Signature=<redacted>"
        )
    return selected


def _client_bundle(
    server: RealServer,
    *,
    secret: bytes = CONTROLLED_SECRET,
    timeout_seconds: float = 2.0,
    max_attempts: int = 1,
) -> ClientBundle:
    requests: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []

    def record_request(request: httpx.Request) -> None:
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "headers": _redacted_headers(request.headers),
                "body": request.content,
            }
        )

    def record_response(response: httpx.Response) -> None:
        response.read()
        responses.append(
            {
                "status_code": response.status_code,
                "path": response.request.url.path,
                "headers": _redacted_headers(response.headers),
                "body": response.content,
            }
        )

    http_client = httpx.Client(
        trust_env=False,
        follow_redirects=False,
        event_hooks={
            "request": [record_request],
            "response": [record_response],
        },
    )
    gateway = ProductionGatewayClient(
        GatewayAdapterConfig(
            environment=GatewayEnvironment.MOCK,
            base_url=server.base_url,
            client_id="channel-engine",
            key_id="controlled-integration-key",
            production_enabled=False,
            timeout_seconds=timeout_seconds,
        ),
        secret,
        http_client=http_client,
        retry_policy=GatewayRetryPolicy(
            max_attempts=max_attempts,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=lambda _delay: None,
    )
    return ClientBundle(gateway, http_client, requests, responses)


def _request(suffix: str, *, include_scope: bool = True) -> DecisionRequest:
    context: dict[str, object] = {"channel_name": "fake-pdd"}
    if include_scope:
        context.update(CONTROLLED_SCOPE.as_gateway_context())
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id=f"controlled-request-{suffix}",
        idempotency_key=f"controlled-decision-{suffix}",
        correlation_id=f"controlled-message-{suffix}",
        conversation_id=f"controlled-conversation-{suffix}",
        message_id=f"controlled-message-{suffix}",
        customer_message="Please draft a controlled response.",
        context=context,
        requested_at=utc_now(),
    )


def _message(suffix: str, body: str = "Please draft a controlled response."):
    return FakePDDInboundMessage(
        chat_id=f"controlled-chat-{suffix}",
        message_id=f"controlled-external-message-{suffix}",
        buyer_id=f"controlled-buyer-{suffix}",
        body=body,
        created_at=utc_now(),
    )


@pytest.fixture(scope="module")
def real_ai_cs_server(tmp_path_factory: pytest.TempPathFactory):
    project_root = Path(__file__).resolve().parents[2]
    ai_cs_root = project_root.parent / "AI-CS"
    backend_path = ai_cs_root / "backend"
    python_executable = backend_path / ".venv" / "Scripts" / "python.exe"
    harness = project_root / "tests" / "support" / "ai_cs_gateway_server_harness.py"
    if not python_executable.exists() or not (backend_path / "app").exists():
        pytest.fail("sibling AI-CS Gateway Server runtime is required for controlled E2E")

    port = _free_loopback_port()
    runtime_path = tmp_path_factory.mktemp("controlled-ai-cs-server")
    environment = os.environ.copy()
    environment.update(
        {
            "CONTROLLED_AI_CS_BACKEND": str(backend_path),
            "CONTROLLED_AI_CS_RUNTIME": str(runtime_path),
            "CONTROLLED_AI_CS_HOST": "127.0.0.1",
            "CONTROLLED_AI_CS_PORT": str(port),
            "CONTROLLED_AI_CS_SECRET": CONTROLLED_SECRET.decode("ascii"),
            "CONTROLLED_AI_CS_DELAY_SECONDS": "0.5",
        }
    )
    process = subprocess.Popen(
        [str(python_executable), str(harness)],
        cwd=project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    server = RealServer(f"http://127.0.0.1:{port}", process)
    deadline = time.monotonic() + 15
    startup_health = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            pytest.fail(f"real AI-CS Gateway Server exited during startup: {output}")
        bundle = _client_bundle(server)
        try:
            startup_health = bundle.gateway.health_check()
        finally:
            bundle.close()
        if startup_health.status is GatewayHealthStatus.HEALTHY:
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"real AI-CS Gateway health did not become ready: {startup_health}")

    yield server

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_signed_versioned_health_uses_real_ai_cs_gateway(
    real_ai_cs_server: RealServer,
) -> None:
    anonymous = httpx.get(
        f"{real_ai_cs_server.base_url}{HEALTH_PATH}",
        trust_env=False,
    )
    bundle = _client_bundle(real_ai_cs_server)
    try:
        health = bundle.gateway.health_check()
    finally:
        bundle.close()

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["error_code"] == "AUTHENTICATION_REQUIRED"
    assert health.status is GatewayHealthStatus.HEALTHY
    assert health.service == "ai-cs-gateway"
    assert health.contract_version == CONTRACT_VERSION
    assert health.gateway_version == "ai-cs-gateway.v1"
    assert health.capability_version == "decision.ai-cs-scope.v1"
    assert health.real_ai_cs_connected is True
    request = bundle.requests[-1]
    assert request["method"] == "GET"
    assert request["path"] == HEALTH_PATH
    assert request["body"] == b""
    headers = request["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"].startswith(
        "HMAC-SHA256 Credential=channel-engine/controlled-integration-key"
    )


def test_real_decision_approval_fake_execution_receipt_and_event_evidence(
    real_ai_cs_server: RealServer,
    foundation,
) -> None:
    bundle = _client_bundle(real_ai_cs_server)
    channel = FakePDDAdapter()
    raw = _message("success")
    assert channel.enqueue_customer_message(raw) is True
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(
        foundation["uow_factory"],
        bundle.gateway,
        decision_context_provider=lambda _inbound: (
            CONTROLLED_SCOPE.as_gateway_context()
        ),
    )
    try:
        intake = service.receive(inbound)
    finally:
        bundle.close()

    decision_exchange = next(
        response
        for response in bundle.responses
        if response["path"] == DECISION_PATH
    )
    wire_response = json.loads(decision_exchange["body"])
    decision_request = next(
        request for request in bundle.requests if request["path"] == DECISION_PATH
    )
    wire_request = json.loads(decision_request["body"])

    assert wire_response["decision_id"] == intake.decision_id
    assert wire_response["proposed_content"] == intake.proposed_content
    assert wire_response["metadata"]["risk_level"] == "LOW"
    assert wire_response["metadata"]["ai_cs_action"] == "CONTROLLED_ANSWER"
    assert wire_response["action"] == "SUGGEST_REPLY"
    assert wire_response["requires_approval"] is True
    assert intake.message_state is MessageState.COMPLETED
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert channel.send_call_count == 0

    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "controlled-human-operator")
    assert enqueued.execution_state is ExecutionState.PENDING
    fake_execution = FakeExecutionAdapter(ReceiptOutcome.SUCCESS)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        fake_execution,
        "controlled-integration-worker",
    )
    lease = worker.claim_next()
    assert lease is not None
    assert lease.execution.state is ExecutionState.RUNNING
    worker_result = worker.process_claim(lease)
    assert worker_result.execution_state is ExecutionState.SUCCESS
    assert worker_result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert fake_execution.call_count == 1
    assert channel.send_call_count == 0

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        decision = repo.get_decision(intake.decision_id)
        approval = repo.get_approval_for_decision(intake.decision_id)
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        assert uow.session is not None
        events = list(
            uow.session.scalars(
                select(EventRow).order_by(EventRow.occurred_at, EventRow.event_id)
            ).all()
        )
    assert approval is not None
    assert receipt is not None
    assert decision.state is DecisionState.APPROVED
    assert execution.state is ExecutionState.SUCCESS
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False

    publisher = FakeEventPublisher()
    publish_results = OutboxPublisher(
        foundation["uow_factory"],
        publisher,
        "controlled-integration-publisher",
    ).run_until_idle(max_items=20)
    assert len(publish_results) == len(events)
    assert all(result.status is OutboxState.PUBLISHED for result in publish_results)
    assert len(publisher.published_events) == len(events)

    evidence = {
        "request": {
            "method": decision_request["method"],
            "path": decision_request["path"],
            "headers": decision_request["headers"],
            "body": wire_request,
        },
        "response": {
            "status_code": decision_exchange["status_code"],
            "headers": decision_exchange["headers"],
            "decision_id": wire_response["decision_id"],
            "reply_draft": wire_response["proposed_content"],
            "risk_level": wire_response["metadata"]["risk_level"],
            "action": wire_response["action"],
            "requires_approval": wire_response["requires_approval"],
        },
        "decision": decision.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "payload": event.payload,
                "correlation_id": event.correlation_id,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in events
        ],
    }
    print("CONTROLLED_EVIDENCE_JSON=" + json.dumps(evidence, ensure_ascii=False))


def test_real_ai_cs_timeout_rolls_back_and_never_executes(
    real_ai_cs_server: RealServer,
    foundation,
) -> None:
    bundle = _client_bundle(
        real_ai_cs_server,
        timeout_seconds=0.05,
        max_attempts=1,
    )
    channel = FakePDDAdapter()
    channel.enqueue_customer_message(
        _message("timeout", "__CONTROLLED_AI_CS_TIMEOUT__")
    )
    inbound = channel.receive_message()
    assert inbound is not None
    service = ConversationService(
        foundation["uow_factory"],
        bundle.gateway,
        decision_context_provider=lambda _inbound: (
            CONTROLLED_SCOPE.as_gateway_context()
        ),
    )
    try:
        with pytest.raises(AICSGatewayTimeout) as raised:
            service.receive(inbound)
    finally:
        bundle.close()

    assert raised.value.attempts == 1
    fake_execution = FakeExecutionAdapter()
    assert (
        ExecutionWorker(
            foundation["uow_factory"],
            fake_execution,
            "controlled-timeout-worker",
        ).run_once()
        is None
    )
    assert fake_execution.call_count == 0
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().find_conversation(
            "fake-pdd",
            "controlled-chat-timeout",
        ) is None
    time.sleep(0.6)


def test_real_ai_cs_rejects_invalid_signature_and_schema_mismatch(
    real_ai_cs_server: RealServer,
) -> None:
    invalid_signature = _client_bundle(
        real_ai_cs_server,
        secret=b"wrong-controlled-integration-secret-32-bytes",
    )
    try:
        with pytest.raises(AICSGatewayRequestFailed) as signature_error:
            invalid_signature.gateway.request_decision(_request("bad-signature"))
    finally:
        invalid_signature.close()
    assert signature_error.value.status_code == 401
    assert (
        signature_error.value.envelope.error.code
        is GatewayErrorCode.AUTHENTICATION_FAILED
    )
    assert signature_error.value.attempts == 1

    invalid_schema = _client_bundle(real_ai_cs_server)
    try:
        with pytest.raises(AICSGatewayRequestFailed) as schema_error:
            invalid_schema.gateway.request_decision(
                _request("missing-ai-cs-scope", include_scope=False)
            )
    finally:
        invalid_schema.close()
    assert schema_error.value.status_code == 422
    assert (
        schema_error.value.envelope.error.code
        is GatewayErrorCode.SCHEMA_VALIDATION_FAILED
    )
    assert schema_error.value.envelope.error.details == {
        "field": "context.ai_cs_scope"
    }


def test_real_ai_cs_duplicate_request_replays_server_decision(
    real_ai_cs_server: RealServer,
) -> None:
    request = _request("server-replay")
    first = _client_bundle(real_ai_cs_server)
    second = _client_bundle(real_ai_cs_server)
    try:
        original = first.gateway.request_decision(request)
        replay = second.gateway.request_decision(request)
    finally:
        first.close()
        second.close()

    assert replay == original
    assert first.responses[-1]["headers"]["idempotency-replayed"] == "false"
    assert second.responses[-1]["headers"]["idempotency-replayed"] == "true"
    assert len(first.requests) == len(second.requests) == 1


def test_unknown_execution_from_real_decision_is_not_retried(
    real_ai_cs_server: RealServer,
    foundation,
) -> None:
    bundle = _client_bundle(real_ai_cs_server)
    channel = FakePDDAdapter()
    channel.enqueue_customer_message(_message("unknown"))
    inbound = channel.receive_message()
    assert inbound is not None
    try:
        intake = ConversationService(
            foundation["uow_factory"],
            bundle.gateway,
            decision_context_provider=lambda _inbound: (
                CONTROLLED_SCOPE.as_gateway_context()
            ),
        ).receive(inbound)
    finally:
        bundle.close()
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "controlled-human-operator")
    adapter = FakeExecutionAdapter(simulate_network_uncertainty=True)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        adapter,
        "controlled-unknown-worker",
    )
    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert adapter.call_count == 1
    assert worker.run_once() is None
    assert adapter.call_count == 1
    assert channel.send_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        assert uow.session is not None
        event_types = set(
            uow.session.scalars(select(EventRow.event_type)).all()
        )
    assert receipt is not None
    assert execution.state is ExecutionState.UNKNOWN
    assert execution.attempt == 1
    assert receipt.outcome is ReceiptOutcome.UNKNOWN
    assert receipt.details["error_code"] == "ADAPTER_NETWORK_UNKNOWN"
    assert EventType.EXECUTION_UNKNOWN.value in event_types
    assert EventType.EXECUTION_SUCCEEDED.value not in event_types
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)
