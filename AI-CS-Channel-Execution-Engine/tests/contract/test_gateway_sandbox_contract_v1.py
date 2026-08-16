from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
import json

import pytest

from channel_engine.gateway import (
    AICSGatewayClient,
    AICSGatewayRequestFailed,
    CONTRACT_VERSION,
    DecisionRequest,
    ErrorEnvelope,
    Event,
    ExecutionReceipt,
    GatewayAggregateType,
    GatewayErrorCode,
    GatewayRequestSigner,
    GatewayRetryPolicy,
    IdempotencyConflict,
    MockAICSServer,
    MockAICSTransport,
    ReceiptError,
)
from channel_engine.gateway.sandbox import (
    SandboxGatewayArtifactServer,
    SandboxGatewayArtifactTransport,
    SandboxGatewayClient,
)
from channel_engine.models import DecisionAction, EventType, ReceiptOutcome


NOW = datetime(2026, 8, 4, 21, 0, tzinfo=timezone.utc)
SECRET = b"gateway-sandbox-contract-secret-32"


def sandbox_client():
    nonce = count(1)
    signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="sandbox-key",
        secret=SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: f"sandbox{next(nonce):016d}",
    )
    decision_server = MockAICSServer(
        {("channel-engine", "sandbox-key"): SECRET},
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
        {("channel-engine", "sandbox-key"): SECRET},
        clock=lambda: NOW,
    )
    client = SandboxGatewayClient(
        decision_client,
        SandboxGatewayArtifactTransport(artifact_server),
        signer,
    )
    return client, decision_server, artifact_server


def request(**updates: object) -> DecisionRequest:
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "sandbox-request-1",
        "idempotency_key": "sandbox-decision-1",
        "correlation_id": "sandbox-correlation-1",
        "conversation_id": "sandbox-conversation-1",
        "message_id": "sandbox-message-1",
        "customer_message": "Synthetic gateway sandbox question",
        "context": {"channel_name": "pdd", "synthetic": True},
        "requested_at": NOW,
    }
    values.update(updates)
    return DecisionRequest.model_validate(values)


def event(**updates: object) -> Event:
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "event_id": "sandbox-event-1",
        "correlation_id": "sandbox-correlation-1",
        "causation_id": "sandbox-decision-1",
        "source": "CHANNEL_ENGINE",
        "event_type": EventType.EXECUTION_SUCCEEDED,
        "aggregate_type": GatewayAggregateType.EXECUTION,
        "aggregate_id": "sandbox-execution-1",
        "payload": {"receipt_id": "sandbox-receipt-1"},
        "occurred_at": NOW,
    }
    values.update(updates)
    return Event.model_validate(values)


def receipt() -> ExecutionReceipt:
    return ExecutionReceipt(
        contract_version=CONTRACT_VERSION,
        receipt_id="sandbox-receipt-1",
        idempotency_key="sandbox-receipt-1",
        correlation_id="sandbox-correlation-1",
        execution_id="sandbox-execution-1",
        decision_id="sandbox-decision-1",
        attempt=1,
        outcome=ReceiptOutcome.UNKNOWN,
        external_reference=None,
        error=ReceiptError(
            code="SANDBOX_OUTCOME_UNKNOWN",
            message="Synthetic execution outcome is unknown",
            retryable=False,
        ),
        reconciliation_required=True,
        details={"real_channel_called": False},
        recorded_at=NOW,
    )


def test_sandbox_client_validates_decision_contract_and_request_idempotency() -> None:
    client, decision_server, _ = sandbox_client()
    first = client.request_decision(request())
    replay = client.request_decision(request())

    assert replay == first
    assert first.contract_version == CONTRACT_VERSION
    assert first.request_id == "sandbox-request-1"
    assert first.action is DecisionAction.SUGGEST_REPLY
    assert first.requires_approval is True
    assert decision_server.decision_compute_count == 1

    with pytest.raises(IdempotencyConflict):
        client.request_decision(
            request(customer_message="Different synthetic logical request")
        )


def test_execution_event_and_receipt_are_schema_validated_and_idempotent() -> None:
    client, _, artifact_server = sandbox_client()

    first_receipt = client.publish_execution_receipt(receipt())
    replay_receipt = client.publish_execution_receipt(receipt())
    first_event = client.publish_execution_event(event())
    replay_event = client.publish_execution_event(event())

    assert first_receipt.replayed is False
    assert replay_receipt.replayed is True
    assert first_event.replayed is False
    assert replay_event.replayed is True
    assert artifact_server.accept_count == 2
    assert artifact_server.replay_count == 2
    assert artifact_server.receipts == (receipt(),)
    assert artifact_server.events == (event(),)


def test_changed_execution_event_with_same_id_returns_error_envelope() -> None:
    client, _, artifact_server = sandbox_client()
    client.publish_execution_event(event())

    with pytest.raises(AICSGatewayRequestFailed) as raised:
        client.publish_execution_event(
            event(payload={"receipt_id": "another-receipt"})
        )

    assert raised.value.status_code == 409
    assert raised.value.envelope.error.code is GatewayErrorCode.IDEMPOTENCY_CONFLICT
    assert (
        ErrorEnvelope.model_validate_json(
            raised.value.envelope.model_dump_json()
        )
        == raised.value.envelope
    )
    assert artifact_server.accept_count == 1
    assert artifact_server.error_count == 1


def test_artifact_route_rejects_schema_version_alias_and_missing_fields() -> None:
    nonce = count(1)
    signer = GatewayRequestSigner(
        client_id="channel-engine",
        key_id="sandbox-key",
        secret=SECRET,
        clock=lambda: NOW,
        nonce_factory=lambda: f"schema{next(nonce):016d}",
    )
    server = SandboxGatewayArtifactServer(
        {("channel-engine", "sandbox-key"): SECRET},
        clock=lambda: NOW,
    )
    transport = SandboxGatewayArtifactTransport(server)

    payloads = []
    schema_alias = event(event_id="schema-alias-event").model_dump(mode="json")
    schema_alias["schema_version"] = schema_alias.pop("contract_version")
    payloads.append(("schema-alias-event", schema_alias))
    missing_field = event(event_id="missing-field-event").model_dump(mode="json")
    missing_field.pop("aggregate_id")
    payloads.append(("missing-field-event", missing_field))

    for event_id, payload in payloads:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        path = f"/gateway/v1/events/{event_id}"
        response = transport.request(
            method="PUT",
            path=path,
            body=body,
            headers=signer.sign(
                body,
                method="PUT",
                path=path,
                request_id=f"publish-{event_id}",
                correlation_id="sandbox-correlation-1",
                idempotency_key=event_id,
                content_type=(
                    "application/vnd.ai-cs.channel-engine.gateway-v1+json"
                ),
            ),
            timeout_seconds=10,
        )
        envelope = ErrorEnvelope.model_validate_json(response.body)
        assert response.status_code == 422
        assert envelope.error.code is GatewayErrorCode.SCHEMA_VALIDATION_FAILED

    assert server.accept_count == 0
    assert server.error_count == 2
