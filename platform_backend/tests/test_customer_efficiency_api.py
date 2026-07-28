import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.usefixtures("customer_identity_catalog")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "customer-efficiency.v1",
        "event_type": "AI_REQUEST",
        "operator_id": "support-tester",
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "conversation_id": "local-conversation-1",
        "interaction_id": "local-interaction-1",
        "feedback_id": None,
    }
    payload.update(overrides)
    return payload


def test_efficiency_event_is_bound_to_selected_user_and_replay_safe(client: TestClient) -> None:
    created = client.post(
        "/api/v1/customer-efficiency/events", json=_payload(), headers={"Idempotency-Key": "event-1"}
    )
    assert created.status_code == 201
    assert created.json()["accepted"] is True
    assert created.json()["event_type"] == "AI_REQUEST"

    replay = client.post(
        "/api/v1/customer-efficiency/events", json=_payload(), headers={"Idempotency-Key": "event-1"}
    )
    assert replay.status_code == 200
    assert replay.json() == created.json()

    conflict = client.post(
        "/api/v1/customer-efficiency/events", json=_payload(product_id="OTHER"), headers={"Idempotency-Key": "event-1"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT"

    unsupported = client.post(
        "/api/v1/customer-efficiency/events",
        json=_payload(schema_version="customer-efficiency.v0", interaction_id="local-interaction-unsupported"),
        headers={"Idempotency-Key": "event-unsupported-schema"},
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_SCHEMA_VERSION_UNSUPPORTED"


def test_terminal_event_needs_one_request_and_feedback_must_reference_own_feedback(client: TestClient) -> None:
    terminal = client.post(
        "/api/v1/customer-efficiency/events",
        json=_payload(event_type="AI_REJECT"), headers={"Idempotency-Key": "event-terminal-first"},
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_EVENT_SEQUENCE_INVALID"

    request = client.post(
        "/api/v1/customer-efficiency/events", json=_payload(), headers={"Idempotency-Key": "event-request"}
    )
    assert request.status_code == 201
    rejection = client.post(
        "/api/v1/customer-efficiency/events",
        json=_payload(event_type="AI_REJECT"), headers={"Idempotency-Key": "event-reject"},
    )
    assert rejection.status_code == 201

    second_terminal = client.post(
        "/api/v1/customer-efficiency/events",
        json=_payload(event_type="AI_EDIT_ADOPT"), headers={"Idempotency-Key": "event-second-terminal"},
    )
    assert second_terminal.status_code == 409

    invalid_feedback = client.post(
        "/api/v1/customer-efficiency/events",
        json=_payload(event_type="AI_FEEDBACK_SUBMIT", interaction_id=None, feedback_id="ARF-NOT-OWNED"),
        headers={"Idempotency-Key": "event-feedback-invalid"},
    )
    assert invalid_feedback.status_code == 422
    assert invalid_feedback.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_FEEDBACK_REFERENCE_INVALID"
