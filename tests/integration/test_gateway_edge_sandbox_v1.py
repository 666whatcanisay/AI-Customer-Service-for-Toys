from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

import pytest

from channel_engine.channel import ChannelMessageV1
from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
    FakeExecutionAdapter,
)
from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    CONTRACT_VERSION,
    DecisionRequest,
    GatewayAdapterConfig,
    GatewayEdgeFault,
    GatewayEnvironment,
    GatewayErrorCode,
    GatewayRetryPolicy,
    SandboxGatewayEdgeServer,
)
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayClient,
    GatewayServiceIdentity,
    MockAICSGateway,
)
from channel_engine.gateway.sandbox import GatewaySandboxRuntime
from channel_engine.models import (
    DecisionState,
    ExecutionState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)


NOW = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
SECRET = b"gateway-edge-sandbox-hmac-secret-material-32"
WRONG_SECRET = b"gateway-edge-wrong-hmac-secret-material-32"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="gateway-edge-sandbox-key",
    credential_ref="vault://ai-cs/gateway/edge-sandbox",
)
FAST_RETRY = GatewayRetryPolicy(
    max_attempts=3,
    base_backoff_seconds=0,
    max_backoff_seconds=0,
    jitter_ratio=0,
)


class LeaseRecordingAdapter:
    """Synthetic executor that proves the approval and lease fence reached Adapter."""

    def __init__(self, outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS) -> None:
        self._delegate = FakeExecutionAdapter(outcome=outcome)
        self.claims: list[ClaimedExecutionContext] = []

    @property
    def call_count(self) -> int:
        return self._delegate.call_count

    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        self.claims.append(context)
        return self._delegate.execute(command)


def build_client(
    base_url: str,
    *,
    secret: bytes = SECRET,
    nonce_prefix: str = "edge",
    timeout_seconds: float = 0.5,
) -> GatewayClient:
    nonce = count(1)
    return GatewayClient.from_http(
        GatewayAdapterConfig(
            environment=GatewayEnvironment.MOCK,
            base_url=base_url,
            client_id=IDENTITY.client_id,
            key_id=IDENTITY.key_id,
            timeout_seconds=timeout_seconds,
        ),
        IDENTITY,
        FakeGatewayTokenProvider(
            {IDENTITY.credential_ref: (IDENTITY.key_id, secret)},
            clock=lambda: NOW,
        ),
        decision_retry_policy=FAST_RETRY,
        artifact_retry_policy=FAST_RETRY,
        clock=lambda: NOW,
        nonce_factory=lambda: f"{nonce_prefix}-nonce-{next(nonce):024d}",
        sleeper=lambda _delay: None,
    )


def inbound(suffix: str) -> ChannelMessageV1:
    return ChannelMessageV1(
        message_id=f"gateway-edge-message-{suffix}",
        channel="fake",
        store_id="gateway-edge-synthetic-store",
        conversation_id=f"gateway-edge-conversation-{suffix}",
        sender="customer",
        content=f"Synthetic gateway edge question {suffix}",
        timestamp=NOW,
    )


def decision_request(suffix: str) -> DecisionRequest:
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id=f"gateway-edge-request-{suffix}",
        idempotency_key=f"gateway-edge-idempotency-{suffix}",
        correlation_id=f"gateway-edge-correlation-{suffix}",
        conversation_id=f"gateway-edge-conversation-{suffix}",
        message_id=f"gateway-edge-message-{suffix}",
        customer_message=f"Synthetic gateway request {suffix}",
        context={"channel_name": "fake", "synthetic": True},
        requested_at=NOW,
    )


def test_real_http_hmac_decision_approval_lease_receipt_trace(foundation) -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    adapter = LeaseRecordingAdapter()
    message = inbound("success")

    with SandboxGatewayEdgeServer(server, clock=lambda: NOW) as edge:
        with build_client(edge.base_url) as client:
            health = client.health_check()
            runtime = GatewaySandboxRuntime(
                foundation["uow_factory"],
                client,
                adapter,
                worker_id="gateway-edge-worker",
            )
            intake = runtime.receive(message)

            assert health.reachable is True
            assert intake.decision_state is DecisionState.WAITING_APPROVAL
            assert adapter.call_count == 0
            with foundation["uow_factory"]() as uow:
                assert (
                    uow.require_repository().get_execution_for_decision(
                        intake.decision_id
                    )
                    is None
                )

            enqueued = runtime.approve(
                intake.decision_id,
                approved_by="gateway-edge-human-operator",
            )
            assert enqueued.execution_state is ExecutionState.PENDING
            assert adapter.call_count == 0

            outcome = runtime.execute_approved(enqueued.execution_id)

        requests = edge.requests

    assert outcome.execution_state is ExecutionState.SUCCESS
    assert outcome.receipt_outcome is ReceiptOutcome.SUCCESS
    assert adapter.call_count == 1
    assert len(adapter.claims) == 1
    claim = adapter.claims[0]
    assert claim.approval_id == enqueued.approval_id
    assert claim.execution_id == enqueued.execution_id
    assert claim.worker_id == "gateway-edge-worker"
    assert claim.lease_token
    assert claim.lease_expires_at > datetime.now(timezone.utc)

    trace = outcome.trace
    assert trace.message_id == intake.message_id
    assert trace.decision_id == intake.decision_id
    assert trace.approval_id == enqueued.approval_id
    assert trace.execution_id == enqueued.execution_id
    assert trace.receipt_id == outcome.receipt_id
    assert trace.event_id == outcome.event_id
    assert client.trace_store.for_message(intake.message_id) == trace
    assert client.trace_store.for_approval(enqueued.approval_id) == trace

    assert tuple(item.path for item in requests) == (
        "/gateway/v1/health",
        "/gateway/v1/decisions",
        f"/gateway/v1/execution-receipts/{outcome.receipt_id}",
        f"/gateway/v1/events/{outcome.event_id}",
    )
    assert all(item.authorization_present for item in requests)
    assert server.decision_server.decision_compute_count == 1
    assert server.artifact_server.accept_count == 2
    assert server.artifact_server.receipts[0].receipt_id == outcome.receipt_id
    assert server.artifact_server.events[0].event_id == outcome.event_id


def test_real_http_duplicate_decision_replays_original_result() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    request = decision_request("duplicate")
    with SandboxGatewayEdgeServer(server, clock=lambda: NOW) as edge:
        with build_client(edge.base_url, nonce_prefix="first") as first_client:
            first = first_client.request_decision(request)
        with build_client(edge.base_url, nonce_prefix="second") as second_client:
            replay = second_client.request_decision(request)
        requests = edge.requests

    assert replay == first
    assert server.decision_server.decision_compute_count == 1
    assert server.decision_server.replay_count == 1
    assert len(requests) == 2
    assert requests[0].idempotency_key == requests[1].idempotency_key
    assert all(item.status_code == 200 for item in requests)


def test_real_http_timeout_is_unknown_and_never_creates_execution(foundation) -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    faults = [GatewayEdgeFault.TIMEOUT] * FAST_RETRY.max_attempts
    message = inbound("timeout")
    with SandboxGatewayEdgeServer(
        server,
        faults=faults,
        timeout_delay_seconds=0.08,
        clock=lambda: NOW,
    ) as edge:
        with build_client(edge.base_url, timeout_seconds=0.02) as client:
            adapter = LeaseRecordingAdapter()
            runtime = GatewaySandboxRuntime(
                foundation["uow_factory"],
                client,
                adapter,
            )
            with pytest.raises(AICSGatewayTimeout) as captured:
                runtime.receive(message)
            traces = client.trace_store.list_traces()
            assert len(traces) == 1
            trace = traces[0]
        requests = edge.requests

    assert captured.value.attempts == 3
    assert captured.value.outcome_unknown is True
    assert len(requests) == 3
    assert all(item.status_code is None for item in requests)
    assert trace.entries[-1].error_code == "GATEWAY_TIMEOUT_UNKNOWN"
    assert trace.decision_id is None
    assert trace.execution_id is None
    assert adapter.call_count == 0


@pytest.mark.parametrize(
    ("fault", "expected_status", "expected_code"),
    (
        (
            GatewayEdgeFault.AUTHORIZATION_DENIED,
            403,
            GatewayErrorCode.AUTHORIZATION_DENIED,
        ),
    ),
)
def test_real_http_authorization_error_is_contract_envelope_and_not_retried(
    fault: GatewayEdgeFault,
    expected_status: int,
    expected_code: GatewayErrorCode,
) -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    request = decision_request(expected_code.value.casefold())
    with SandboxGatewayEdgeServer(
        server,
        faults=(fault,),
        clock=lambda: NOW,
    ) as edge:
        with build_client(edge.base_url) as client:
            with pytest.raises(AICSGatewayRequestFailed) as captured:
                client.request_decision(request)
        requests = edge.requests

    assert captured.value.status_code == expected_status
    assert captured.value.envelope.error.code is expected_code
    assert captured.value.attempts == 1
    assert len(requests) == 1
    assert server.decision_server.decision_compute_count == 0


def test_real_http_invalid_signature_returns_401_without_retry() -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    request = decision_request("invalid-signature")
    with SandboxGatewayEdgeServer(server, clock=lambda: NOW) as edge:
        with build_client(edge.base_url, secret=WRONG_SECRET) as client:
            with pytest.raises(AICSGatewayRequestFailed) as captured:
                client.request_decision(request)
        requests = edge.requests

    assert captured.value.status_code == 401
    assert (
        captured.value.envelope.error.code
        is GatewayErrorCode.AUTHENTICATION_FAILED
    )
    assert captured.value.attempts == 1
    assert len(requests) == 1
    assert server.decision_server.decision_compute_count == 0


def test_real_http_unknown_execution_receipt_is_replayed_not_reexecuted(
    foundation,
) -> None:
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    adapter = LeaseRecordingAdapter(outcome=ReceiptOutcome.UNKNOWN)
    with SandboxGatewayEdgeServer(server, clock=lambda: NOW) as edge:
        with build_client(edge.base_url) as client:
            runtime = GatewaySandboxRuntime(
                foundation["uow_factory"],
                client,
                adapter,
                worker_id="gateway-edge-unknown-worker",
            )
            intake = runtime.receive(inbound("unknown"))
            enqueued = runtime.approve(
                intake.decision_id,
                approved_by="gateway-edge-human-operator",
            )
            first = runtime.execute_approved(enqueued.execution_id)
            replay = runtime.execute_approved(enqueued.execution_id)

    assert first.execution_state is ExecutionState.UNKNOWN
    assert first.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert replay.receipt_id == first.receipt_id
    assert replay.event_id == first.event_id
    assert adapter.call_count == 1
    assert len(adapter.claims) == 1
    assert server.artifact_server.accept_count == 2
    assert server.artifact_server.replay_count == 2
    with foundation["uow_factory"]() as uow:
        execution = uow.require_repository().get_execution(enqueued.execution_id)
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)
