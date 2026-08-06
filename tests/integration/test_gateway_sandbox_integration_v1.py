from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from itertools import count

from channel_engine.browser.selectors import LocatorEngine
from channel_engine.gateway import (
    AICSGatewayClient,
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
)
from channel_engine.models import DecisionState, ExecutionState, ReceiptOutcome
from channel_engine.pdd_adapter import (
    FakePDDAdapter,
    PDD_REQUIRED_OBSERVATION_PURPOSES,
    PDDMessageEnvelope,
    PDDMessageSourceKind,
    PDDPrototypeSessionRuntime,
    PDDRawMetadata,
    PDDSelectorCandidate,
    PDDSelectorGovernance,
    PDDSelectorVerificationEvidence,
)
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
)


NOW = datetime(2026, 8, 4, 21, 30, tzinfo=timezone.utc)
SECRET = b"gateway-sandbox-integration-secret-32"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def selector_token():
    draft = PDDSelectorGovernance.draft("gateway-sandbox-v1")
    candidates = tuple(
        PDDSelectorCandidate(
            purpose=purpose,
            engine_hint=LocatorEngine.MOCK,
            locator_fingerprint=digest(f"sandbox:{purpose.value}"),
            evidence_reference=f"evidence-ref://sandbox/{purpose.value.casefold()}",
            observed_match_count=1,
        )
        for purpose in sorted(
            PDD_REQUIRED_OBSERVATION_PURPOSES,
            key=lambda item: item.value,
        )
    )
    discovery = PDDSelectorGovernance.begin_discovery(
        draft,
        candidates=candidates,
        discovery_reference="discovery-ref://gateway-sandbox/offline",
        discovered_at=NOW,
    )
    verified = PDDSelectorGovernance.verify(
        discovery,
        PDDSelectorVerificationEvidence(
            contract_id=discovery.contract_id,
            contract_fingerprint=discovery.fingerprint(),
            verified_purposes=frozenset(candidate.purpose for candidate in candidates),
            probe_passed=True,
            synthetic_test_data=True,
            evidence_reference="evidence-ref://gateway-sandbox/verified",
            checked_at=NOW,
        ),
    )
    return PDDSelectorGovernance.require_verified(
        verified,
        synthetic_test_data=True,
    )


def fake_pdd_message(foundation):
    token = selector_token()
    reference = CredentialReference(
        credential_ref="vault://gateway-sandbox/fake-pdd-store",
        provider="sandbox-vault",
        version="v1",
    )
    session_store = ChannelSessionStore(foundation["uow_factory"])
    session_manager = ChannelInstanceManager(
        session_store,
        FakeCredentialProvider((reference,)),
        MessageReliabilityService(foundation["uow_factory"], session_store),
    )
    session_runtime = PDDPrototypeSessionRuntime(session_manager)
    created = session_runtime.create(
        store_id="sandbox-pdd-store",
        credential_ref=reference,
        instance_id="gateway-sandbox-pdd-instance",
    )
    adapter = FakePDDAdapter(
        store_id="sandbox-pdd-store",
        selector_token=token,
    )
    adapter.open_session(session_runtime.start(created.instance_id))
    adapter.enqueue_observation(
        PDDMessageEnvelope(
            external_message_id="gateway-sandbox-pdd-message-1",
            sender="customer",
            content="Synthetic PDD question for gateway sandbox",
            timestamp=NOW,
            store_id="sandbox-pdd-store",
            conversation_external_id="gateway-sandbox-pdd-conversation-1",
            raw_metadata=PDDRawMetadata(
                source_kind=PDDMessageSourceKind.SYNTHETIC_FIXTURE,
                source_event_ref_digest=digest("sandbox-source-event"),
                payload_digest=digest("sandbox-payload"),
                cursor_digest=digest("sandbox-cursor"),
                source_sequence=1,
                selector_contract_id=token.contract_id,
                observed_at=NOW,
            ),
        )
    )
    return adapter, adapter.receive_messages()[0]


def sandbox_runtime(foundation):
    nonce = count(1)
    signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="sandbox-integration-key",
        secret=SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: f"integration{next(nonce):016d}",
    )
    decision_server = MockAICSServer(
        {("channel-engine", "sandbox-integration-key"): SECRET},
        clock=lambda: NOW,
    )
    decision_client = AICSGatewayClient(
        MockAICSTransport(decision_server),
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
        {("channel-engine", "sandbox-integration-key"): SECRET},
        clock=lambda: NOW,
    )
    gateway = SandboxGatewayClient(
        decision_client,
        SandboxGatewayArtifactTransport(artifact_server),
        signer,
    )
    return (
        GatewaySandboxRuntime(
            foundation["uow_factory"],
            gateway,
            foundation["executor"],
        ),
        gateway,
        decision_server,
        artifact_server,
    )


def test_fake_pdd_gateway_approval_execution_receipt_event_complete_trace(
    foundation,
) -> None:
    pdd, message = fake_pdd_message(foundation)
    runtime, gateway, decision_server, artifact_server = sandbox_runtime(foundation)

    intake = runtime.receive(message)

    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert foundation["executor"].call_count == 0
    assert not hasattr(pdd, "send_message")
    with foundation["uow_factory"]() as uow:
        assert (
            uow.require_repository().get_execution_for_decision(intake.decision_id)
            is None
        )

    enqueued = runtime.approve(
        intake.decision_id,
        approved_by="sandbox-human-operator",
    )
    assert enqueued.execution_state is ExecutionState.PENDING
    assert foundation["executor"].call_count == 0

    outcome = runtime.execute_approved(enqueued.execution_id)

    assert outcome.execution_state is ExecutionState.SUCCESS
    assert outcome.receipt_outcome is ReceiptOutcome.SUCCESS
    assert foundation["executor"].call_count == 1
    assert decision_server.decision_compute_count == 1
    assert artifact_server.accept_count == 2
    assert len(artifact_server.receipts) == 1
    assert len(artifact_server.events) == 1
    assert artifact_server.events[0].aggregate_id == enqueued.execution_id
    assert artifact_server.events[0].payload["receipt_id"] == outcome.receipt_id

    trace = outcome.trace
    assert trace.request_id == f"decision-request-{intake.message_id}"
    assert trace.decision_id == intake.decision_id
    assert trace.execution_id == enqueued.execution_id
    assert trace.receipt_id == outcome.receipt_id
    assert trace.event_id == outcome.event_id
    stages = tuple(entry.stage for entry in trace.entries)
    assert stages == (
        GatewaySandboxStage.DECISION_REQUESTED,
        GatewaySandboxStage.DECISION_RESOLVED,
        GatewaySandboxStage.APPROVAL_RECORDED,
        GatewaySandboxStage.EXECUTION_ENQUEUED,
        GatewaySandboxStage.EXECUTION_SUCCEEDED,
        GatewaySandboxStage.RECEIPT_PUBLISHED,
        GatewaySandboxStage.EXECUTION_EVENT_PUBLISHED,
    )
    assert all(entry.error_code is None for entry in trace.entries)


def test_duplicate_message_approval_and_execution_do_not_duplicate_side_effects(
    foundation,
) -> None:
    _, message = fake_pdd_message(foundation)
    runtime, _, decision_server, artifact_server = sandbox_runtime(foundation)

    first_intake = runtime.receive(message)
    replay_intake = runtime.receive(message)
    first_enqueued = runtime.approve(
        first_intake.decision_id,
        approved_by="sandbox-human-operator",
    )
    replay_enqueued = runtime.approve(
        replay_intake.decision_id,
        approved_by="sandbox-human-operator",
    )
    first_outcome = runtime.execute_approved(first_enqueued.execution_id)
    replay_outcome = runtime.execute_approved(replay_enqueued.execution_id)

    assert replay_intake == first_intake
    assert replay_enqueued.execution_id == first_enqueued.execution_id
    assert replay_outcome.receipt_id == first_outcome.receipt_id
    assert replay_outcome.event_id == first_outcome.event_id
    assert foundation["executor"].call_count == 1
    assert decision_server.decision_compute_count == 1
    assert artifact_server.accept_count == 2
    assert artifact_server.replay_count == 2
