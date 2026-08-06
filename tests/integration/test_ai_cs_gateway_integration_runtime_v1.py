from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

import pytest

from channel_engine.channel import ChannelMessageV1
from channel_engine.execution import FakeExecutionAdapter
from channel_engine.gateway import GatewayRetryPolicy
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayClient,
    GatewayServiceIdentity,
    MockAICSGateway,
    MockAICSGatewayTransport,
)
from channel_engine.gateway.sandbox import (
    GatewaySandboxRuntime,
    GatewaySandboxStage,
)
from channel_engine.models import (
    DecisionState,
    ExecutionState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)


NOW = datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc)
SECRET = b"ai-cs-real-ready-runtime-secret-32-bytes"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="real-ready-runtime-key",
    credential_ref="vault://ai-cs/gateway/real-ready-runtime",
)


def build_gateway():
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    nonce = count(1)
    client = GatewayClient(
        MockAICSGatewayTransport(server),
        IDENTITY,
        FakeGatewayTokenProvider(
            {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
            clock=lambda: NOW,
        ),
        decision_retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        artifact_retry_policy=GatewayRetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0,
            max_backoff_seconds=0,
            jitter_ratio=0,
        ),
        clock=lambda: NOW,
        nonce_factory=lambda: f"runtime{next(nonce):016d}",
        sleeper=lambda _delay: None,
    )
    return client, server


def inbound(suffix: str) -> ChannelMessageV1:
    return ChannelMessageV1(
        message_id=f"real-ready-message-{suffix}",
        channel="fake",
        store_id="real-ready-store",
        conversation_id=f"real-ready-conversation-{suffix}",
        sender="customer",
        content=f"Synthetic real-ready gateway message {suffix}",
        timestamp=NOW,
    )


def test_real_ready_gateway_client_full_trace_with_fake_execution(foundation) -> None:
    client, server = build_gateway()
    runtime = GatewaySandboxRuntime(
        foundation["uow_factory"],
        client,
        foundation["executor"],
        worker_id="real-ready-gateway-worker",
    )

    intake = runtime.receive(inbound("success"))

    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert foundation["executor"].call_count == 0
    enqueued = runtime.approve(
        intake.decision_id,
        approved_by="real-ready-human-operator",
    )
    assert enqueued.execution_state is ExecutionState.PENDING
    assert foundation["executor"].call_count == 0

    outcome = runtime.execute_approved(enqueued.execution_id)

    assert outcome.execution_state is ExecutionState.SUCCESS
    assert outcome.receipt_outcome is ReceiptOutcome.SUCCESS
    assert foundation["executor"].call_count == 1
    assert server.decision_server.decision_compute_count == 1
    assert server.artifact_server.accept_count == 2
    assert server.artifact_server.receipts[0].receipt_id == outcome.receipt_id
    assert server.artifact_server.events[0].event_id == outcome.event_id
    assert outcome.trace.request_id is not None
    assert outcome.trace.decision_id == intake.decision_id
    assert outcome.trace.execution_id == enqueued.execution_id
    assert outcome.trace.receipt_id == outcome.receipt_id
    assert outcome.trace.event_id == outcome.event_id
    assert tuple(entry.stage for entry in outcome.trace.entries) == (
        GatewaySandboxStage.DECISION_REQUESTED,
        GatewaySandboxStage.DECISION_RESOLVED,
        GatewaySandboxStage.APPROVAL_RECORDED,
        GatewaySandboxStage.EXECUTION_ENQUEUED,
        GatewaySandboxStage.EXECUTION_SUCCEEDED,
        GatewaySandboxStage.RECEIPT_PUBLISHED,
        GatewaySandboxStage.EXECUTION_EVENT_PUBLISHED,
    )
    assert all(entry.error_code is None for entry in outcome.trace.entries)


def test_unknown_execution_is_published_once_and_never_automatically_retried(
    foundation,
) -> None:
    client, server = build_gateway()
    unknown_adapter = FakeExecutionAdapter(outcome=ReceiptOutcome.UNKNOWN)
    runtime = GatewaySandboxRuntime(
        foundation["uow_factory"],
        client,
        unknown_adapter,
        worker_id="real-ready-unknown-worker",
    )
    intake = runtime.receive(inbound("unknown"))
    enqueued = runtime.approve(
        intake.decision_id,
        approved_by="real-ready-human-operator",
    )

    first = runtime.execute_approved(enqueued.execution_id)
    replay = runtime.execute_approved(enqueued.execution_id)

    assert first.execution_state is ExecutionState.UNKNOWN
    assert first.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert replay.receipt_id == first.receipt_id
    assert replay.event_id == first.event_id
    assert unknown_adapter.call_count == 1
    assert server.artifact_server.accept_count == 2
    assert server.artifact_server.replay_count == 2
    with foundation["uow_factory"]() as uow:
        execution = uow.require_repository().get_execution(enqueued.execution_id)
    with pytest.raises(UnknownExecutionRequiresReconciliation):
        assert_not_automatic_retry(execution)
