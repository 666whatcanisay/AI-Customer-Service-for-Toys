from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

import pytest

from channel_engine.channel import ChannelMessageV1
from channel_engine.execution import FakeExecutionAdapter
from channel_engine.gateway import (
    AICSGatewayClient,
    AICSGatewayTimeout,
    GatewayContractViolation,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    MockAICSServer,
    MockAICSTransport,
)
from channel_engine.gateway.sandbox import (
    GatewaySandboxRuntime,
    GatewaySandboxStage,
    SandboxGatewayArtifactServer,
    SandboxGatewayArtifactTransport,
    SandboxGatewayClient,
    SandboxTransportFault,
    ScriptedSandboxGatewayTransport,
)
from channel_engine.models import (
    DecisionState,
    ExecutionState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)


NOW = datetime(2026, 8, 4, 22, 0, tzinfo=timezone.utc)
SECRET = b"gateway-sandbox-failure-secret-32-bytes"


def build_runtime(
    foundation,
    *,
    faults: tuple[SandboxTransportFault, ...] = (),
    execution_adapter=None,
):
    nonce = count(1)
    signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="sandbox-failure-key",
        secret=SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: f"failure{next(nonce):016d}",
    )
    server = MockAICSServer(
        {("channel-engine", "sandbox-failure-key"): SECRET},
        clock=lambda: NOW,
    )
    base_transport = MockAICSTransport(server)
    scripted = ScriptedSandboxGatewayTransport(base_transport, faults)
    decision_client = AICSGatewayClient(
        scripted,
        signer,
        retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=lambda _delay: None,
    )
    artifact_server = SandboxGatewayArtifactServer(
        {("channel-engine", "sandbox-failure-key"): SECRET},
        clock=lambda: NOW,
    )
    gateway = SandboxGatewayClient(
        decision_client,
        SandboxGatewayArtifactTransport(artifact_server),
        signer,
    )
    adapter = execution_adapter or foundation["executor"]
    runtime = GatewaySandboxRuntime(
        foundation["uow_factory"],
        gateway,
        adapter,
        worker_id="gateway-sandbox-failure-worker",
    )
    return runtime, gateway, server, scripted, artifact_server, adapter


def inbound(suffix: str) -> ChannelMessageV1:
    return ChannelMessageV1(
        message_id=f"sandbox-failure-message-{suffix}",
        channel="pdd",
        store_id="sandbox-store",
        conversation_id=f"sandbox-failure-conversation-{suffix}",
        sender="customer",
        content=f"Synthetic failure scenario {suffix}",
        timestamp=NOW,
    )


def test_gateway_timeout_records_unknown_and_never_creates_execution(foundation) -> None:
    runtime, gateway, server, scripted, artifact_server, _ = build_runtime(
        foundation,
        faults=(
            SandboxTransportFault.TIMEOUT,
            SandboxTransportFault.TIMEOUT,
            SandboxTransportFault.TIMEOUT,
        ),
    )

    with pytest.raises(AICSGatewayTimeout):
        runtime.receive(inbound("timeout"))

    traces = gateway.trace_store.list_traces()
    assert len(traces) == 1
    assert tuple(entry.stage for entry in traces[0].entries) == (
        GatewaySandboxStage.DECISION_REQUESTED,
        GatewaySandboxStage.GATEWAY_UNKNOWN,
    )
    assert traces[0].entries[-1].error_code == "GATEWAY_TIMEOUT_UNKNOWN"
    assert scripted.attempt_count == 3
    assert server.decision_compute_count == 0
    assert foundation["executor"].call_count == 0
    assert artifact_server.accept_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.find_conversation("pdd", "sandbox-failure-conversation-timeout") is None


def test_transient_network_failure_recovers_with_same_request_and_no_auto_execution(
    foundation,
) -> None:
    runtime, gateway, server, scripted, _, _ = build_runtime(
        foundation,
        faults=(
            SandboxTransportFault.NETWORK_FAILURE,
            SandboxTransportFault.PASS_THROUGH,
        ),
    )

    result = runtime.receive(inbound("network-recovery"))

    assert result.decision_state is DecisionState.WAITING_APPROVAL
    assert scripted.attempt_count == 2
    assert server.decision_compute_count == 1
    trace = gateway.trace_store.for_decision(result.decision_id)
    assert trace.entries[-1].stage is GatewaySandboxStage.DECISION_RESOLVED
    assert trace.entries[-1].recovered is True
    assert foundation["executor"].call_count == 0
    with foundation["uow_factory"]() as uow:
        assert (
            uow.require_repository().get_execution_for_decision(result.decision_id)
            is None
        )


def test_invalid_decision_response_fails_contract_and_never_executes(foundation) -> None:
    runtime, gateway, server, _, artifact_server, _ = build_runtime(
        foundation,
        faults=(SandboxTransportFault.INVALID_SUCCESS,),
    )

    with pytest.raises(GatewayContractViolation):
        runtime.receive(inbound("invalid-decision"))

    trace = gateway.trace_store.list_traces()[0]
    assert trace.entries[-1].stage is GatewaySandboxStage.GATEWAY_FAILED
    assert trace.entries[-1].error_code == "GATEWAYCONTRACTVIOLATION"
    assert server.decision_compute_count == 1
    assert foundation["executor"].call_count == 0
    assert artifact_server.accept_count == 0


def test_execution_unknown_produces_one_receipt_event_and_is_never_retried(
    foundation,
) -> None:
    unknown_adapter = FakeExecutionAdapter(outcome=ReceiptOutcome.UNKNOWN)
    runtime, _, _, _, artifact_server, adapter = build_runtime(
        foundation,
        execution_adapter=unknown_adapter,
    )
    intake = runtime.receive(inbound("execution-unknown"))
    enqueued = runtime.approve(
        intake.decision_id,
        approved_by="sandbox-human-operator",
    )

    first = runtime.execute_approved(enqueued.execution_id)
    replay = runtime.execute_approved(enqueued.execution_id)

    assert first.execution_state is ExecutionState.UNKNOWN
    assert first.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert replay.receipt_id == first.receipt_id
    assert replay.event_id == first.event_id
    assert adapter.call_count == 1
    assert artifact_server.accept_count == 2
    assert artifact_server.replay_count == 2
    with foundation["uow_factory"]() as uow:
        execution = uow.require_repository().get_execution(enqueued.execution_id)
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)
