from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_engine.gateway import (
    CONTRACT_SCHEMA_ID,
    CONTRACT_VERSION,
    AuthenticationMetadata,
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    Event,
    ExecutionReceipt,
    FakeGateway,
    GatewayAggregateType,
    GatewayError,
    GatewayErrorCode,
    GatewayHealth,
    GatewayRiskLevel,
    IdempotencyConflict,
    ReceiptError,
    build_gateway_contract_schema,
)
from channel_engine.models import DecisionAction, EventType, ReceiptOutcome


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "ai-cs-channel-engine-gateway-contract-v1.schema.json"
)
PRODUCTION_V1_SCHEMA_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def decision_request(**updates: object) -> DecisionRequest:
    values: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "gateway-request-1",
        "idempotency_key": "decision-msg-1",
        "correlation_id": "correlation-1",
        "conversation_id": "conv-1",
        "message_id": "msg-1",
        "customer_message": "Where is my order?",
        "context": {"channel_name": "fake-channel", "locale": "en-US"},
        "requested_at": NOW,
    }
    values.update(updates)
    return DecisionRequest.model_validate(values)


def test_checked_in_json_schema_is_canonical_and_complete() -> None:
    checked_in = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert checked_in == build_gateway_contract_schema()
    assert checked_in["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert checked_in["$id"] == CONTRACT_SCHEMA_ID
    assert {
        "DecisionRequest",
        "DecisionResponse",
        "ErrorEnvelope",
        "GatewayHealth",
        "AuthenticationMetadata",
    } <= checked_in["$defs"].keys()
    for definition in (
        "DecisionRequest",
        "DecisionResponse",
        "ErrorEnvelope",
        "GatewayHealth",
        "AuthenticationMetadata",
    ):
        assert checked_in["$defs"][definition]["additionalProperties"] is False
    assert "ExecutionReceipt" not in checked_in["$defs"]
    assert "Event" not in checked_in["$defs"]
    canonical = json.dumps(
        checked_in, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == PRODUCTION_V1_SCHEMA_SHA256


def test_decision_request_is_strict_versioned_and_timezone_aware() -> None:
    request = decision_request()

    assert DecisionRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError):
        request.customer_message = "mutated"  # type: ignore[misc]

    for updates in (
        {"contract_version": "2.0"},
        {"requested_at": datetime(2026, 8, 4, 12, 0)},
        {"customer_message": "   "},
        {"idempotency_key": "contains spaces"},
        {"unexpected": True},
    ):
        with pytest.raises(ValidationError):
            decision_request(**updates)


def test_decision_response_enforces_action_content_and_human_approval() -> None:
    response = DecisionResponse(
        contract_version=CONTRACT_VERSION,
        request_id="gateway-request-1",
        idempotency_key="decision-msg-1",
        correlation_id="correlation-1",
        decision_id="decision-1",
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="A draft reply",
        requires_approval=True,
        risk_level=GatewayRiskLevel.LOW,
        gateway_version="ai-cs-gateway.v1",
        metadata={},
        decided_at=NOW,
    )
    assert DecisionResponse.model_validate_json(response.model_dump_json()) == response

    with pytest.raises(ValidationError):
        DecisionResponse.model_validate(
            {**response.model_dump(), "requires_approval": False}
        )
    with pytest.raises(ValidationError):
        DecisionResponse.model_validate(
            {**response.model_dump(), "proposed_content": None}
        )

    no_action = DecisionResponse.model_validate(
        {
            **response.model_dump(),
            "action": DecisionAction.NO_ACTION,
            "proposed_content": None,
        }
    )
    assert no_action.action is DecisionAction.NO_ACTION


def test_health_and_error_wire_fields_are_frozen() -> None:
    schema = build_gateway_contract_schema()
    health = schema["$defs"]["GatewayHealth"]
    error = schema["$defs"]["GatewayError"]

    assert {"status", "version", "capabilities", "timestamp"}.issubset(
        health["required"]
    )
    assert "error_code" in error["required"]
    assert "code" not in error["properties"]
    assert GatewayHealth.model_config["extra"] == "forbid"


def test_execution_receipt_enforces_terminal_outcome_semantics() -> None:
    success = ExecutionReceipt(
        contract_version=CONTRACT_VERSION,
        receipt_id="receipt-1",
        idempotency_key="receipt-1",
        correlation_id="correlation-1",
        execution_id="execution-1",
        decision_id="decision-1",
        attempt=1,
        outcome=ReceiptOutcome.SUCCESS,
        external_reference="fake-reference-1",
        error=None,
        reconciliation_required=False,
        details={"real_channel_called": False},
        recorded_at=NOW,
    )
    assert ExecutionReceipt.model_validate_json(success.model_dump_json()) == success

    receipt_error = ReceiptError(
        code="CHANNEL_STATE_UNCONFIRMED",
        message="The external result is not known",
        retryable=False,
    )
    unknown = ExecutionReceipt.model_validate(
        {
            **success.model_dump(),
            "outcome": ReceiptOutcome.UNKNOWN,
            "external_reference": None,
            "error": receipt_error,
            "reconciliation_required": True,
        }
    )
    assert unknown.reconciliation_required is True

    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(
            {
                **success.model_dump(),
                "outcome": ReceiptOutcome.UNKNOWN,
                "error": receipt_error,
            }
        )
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(
            {
                **success.model_dump(),
                "outcome": ReceiptOutcome.FAILED,
                "error": None,
            }
        )
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(
            {**success.model_dump(), "idempotency_key": "another-key"}
        )


def test_event_and_authentication_metadata_round_trip() -> None:
    event = Event(
        contract_version=CONTRACT_VERSION,
        event_id="event-1",
        correlation_id="correlation-1",
        causation_id="decision-1",
        source="CHANNEL_ENGINE",
        event_type=EventType.EXECUTION_SUCCEEDED,
        aggregate_type=GatewayAggregateType.EXECUTION,
        aggregate_id="execution-1",
        payload={"receipt_id": "receipt-1"},
        occurred_at=NOW,
    )
    authentication = AuthenticationMetadata(
        contract_version=CONTRACT_VERSION,
        scheme="HMAC-SHA256",
        client_id="channel-engine",
        key_id="key-2026-08",
        timestamp=NOW,
        nonce="n" * 22,
        content_sha256="a" * 64,
        signature="A" * 43,
    )

    assert Event.model_validate_json(event.model_dump_json()) == event
    assert (
        AuthenticationMetadata.model_validate_json(authentication.model_dump_json())
        == authentication
    )
    with pytest.raises(ValidationError):
        AuthenticationMetadata.model_validate(
            {**authentication.model_dump(), "content_sha256": "not-a-hash"}
        )


def test_error_envelope_has_frozen_retry_semantics() -> None:
    envelope = ErrorEnvelope(
        contract_version=CONTRACT_VERSION,
        error=GatewayError(
            error_id="error-1",
            code=GatewayErrorCode.RATE_LIMITED,
            message="Request rate exceeded",
            retryable=True,
            retry_after_seconds=30,
            request_id="gateway-request-1",
            correlation_id="correlation-1",
            details={},
            occurred_at=NOW,
        ),
    )
    assert ErrorEnvelope.model_validate_json(envelope.model_dump_json()) == envelope

    with pytest.raises(ValidationError):
        GatewayError(
            error_id="error-2",
            code=GatewayErrorCode.AUTHENTICATION_FAILED,
            message="Signature is invalid",
            retryable=True,
            request_id=None,
            correlation_id=None,
            occurred_at=NOW,
        )
    with pytest.raises(ValidationError):
        GatewayError(
            error_id="error-3",
            code=GatewayErrorCode.RATE_LIMITED,
            message="Request rate exceeded",
            retryable=True,
            request_id="gateway-request-1",
            correlation_id="correlation-1",
            occurred_at=NOW,
        )


def test_fake_gateway_conforms_and_replays_same_idempotent_response() -> None:
    gateway = FakeGateway()
    request = decision_request()

    first = gateway.decide(request)
    replay = gateway.decide(request)

    assert replay == first
    assert gateway.call_count == 1
    assert first.contract_version == request.contract_version
    assert first.request_id == request.request_id
    assert first.idempotency_key == request.idempotency_key
    assert first.correlation_id == request.correlation_id
    assert first.requires_approval is True
    assert first.metadata["real_ai_cs_called"] is False
    assert DecisionResponse.model_validate_json(first.model_dump_json()) == first

    conflicting_request = request.model_copy(
        update={"customer_message": "A different logical request"}
    )
    with pytest.raises(IdempotencyConflict):
        gateway.decide(conflicting_request)
    assert gateway.call_count == 1


def test_fake_gateway_coalesces_concurrent_idempotent_requests() -> None:
    gateway = FakeGateway()
    request = decision_request()

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(gateway.decide, [request] * 16))

    assert gateway.call_count == 1
    assert all(response == responses[0] for response in responses)
