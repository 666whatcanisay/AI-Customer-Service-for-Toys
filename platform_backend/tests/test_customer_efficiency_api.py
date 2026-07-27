from datetime import datetime, timezone

from fastapi.testclient import TestClient


WINDOW_START = "2026-07-27T00:00:00Z"
WINDOW_END = "2026-07-28T00:00:00Z"


def _create_event(
    client: TestClient,
    event_type: str,
    key: str,
    occurred_at: str = "2026-07-27T09:00:00Z",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/customer-efficiency-events",
        json={"event_type": event_type, "occurred_at": occurred_at},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()


def test_b_event_write_is_content_free_and_idempotent(client: TestClient) -> None:
    missing_key = client.post(
        "/api/v1/customer-efficiency-events", json={"event_type": "AI_REQUEST"}
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_VALIDATION_FAILED"

    forbidden_content = client.post(
        "/api/v1/customer-efficiency-events",
        json={"event_type": "AI_REQUEST", "question": "Do not store this."},
        headers={"Idempotency-Key": "event-extra-field"},
    )
    assert forbidden_content.status_code == 422
    assert forbidden_content.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_VALIDATION_FAILED"

    created = _create_event(client, "AI_REQUEST", "event-001")
    assert set(created) == {"event_id", "event_type", "occurred_at", "created_at"}
    assert str(created["event_id"]).startswith("CEE-")
    assert created["event_type"] == "AI_REQUEST"
    assert "question" not in created

    replay = client.post(
        "/api/v1/customer-efficiency-events",
        json={"event_type": "AI_REQUEST", "occurred_at": "2026-07-27T09:00:00Z"},
        headers={"Idempotency-Key": "event-001"},
    )
    assert replay.status_code == 200
    assert replay.json() == created

    conflict = client.post(
        "/api/v1/customer-efficiency-events",
        json={"event_type": "NOT_ADOPTED", "occurred_at": "2026-07-27T09:00:00Z"},
        headers={"Idempotency-Key": "event-001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT"


def test_a_and_admin_summaries_aggregate_the_same_explicit_window(client: TestClient) -> None:
    _create_event(client, "AI_REQUEST", "request-1", "2026-07-27T01:00:00Z")
    _create_event(client, "AI_REQUEST", "request-2", "2026-07-27T02:00:00Z")
    _create_event(client, "AI_REQUEST", "request-3", "2026-07-27T03:00:00Z")
    _create_event(client, "AI_REQUEST", "request-4", "2026-07-27T04:00:00Z")
    _create_event(client, "DIRECT_ADOPTION", "direct-1", "2026-07-27T05:00:00Z")
    _create_event(client, "EDITED_ADOPTION", "edited-1", "2026-07-27T06:00:00Z")
    _create_event(client, "NOT_ADOPTED", "not-adopted-1", "2026-07-27T07:00:00Z")
    _create_event(client, "AI_REQUEST", "outside-window", "2026-07-28T00:00:00Z")

    params = {"window_start": WINDOW_START, "window_end": WINDOW_END}
    a_summary = client.get("/api/v1/admin/ai-quality/customer-efficiency/summary", params=params)
    admin_summary = client.get("/api/v1/admin/customer-efficiency/summary", params=params)
    assert a_summary.status_code == 200
    assert admin_summary.status_code == 200
    assert a_summary.json()["summary_version"] == "customer-efficiency.v1"
    assert a_summary.json()["window_start"] == WINDOW_START
    assert a_summary.json()["window_end"] == WINDOW_END
    assert datetime.fromisoformat(a_summary.json()["generated_at"].replace("Z", "+00:00")).tzinfo == timezone.utc
    assert a_summary.json()["ai_request_count"] == 4
    assert a_summary.json()["direct_adoption_count"] == 1
    assert a_summary.json()["edited_adoption_count"] == 1
    assert a_summary.json()["not_adopted_count"] == 1
    assert a_summary.json()["adoption_rate"] == 0.5
    assert admin_summary.json() | {"generated_at": None} == a_summary.json() | {"generated_at": None}
    assert "items" not in a_summary.json()
    assert "employee" not in str(a_summary.json()).lower()


def test_summary_rejects_an_invalid_window_and_returns_zero_for_no_requests(client: TestClient) -> None:
    invalid = client.get(
        "/api/v1/admin/ai-quality/customer-efficiency/summary",
        params={"window_start": WINDOW_END, "window_end": WINDOW_START},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "CUSTOMER_EFFICIENCY_INVALID_WINDOW"

    empty = client.get(
        "/api/v1/admin/customer-efficiency/summary",
        params={"window_start": WINDOW_START, "window_end": WINDOW_END},
    )
    assert empty.status_code == 200
    assert empty.json()["ai_request_count"] == 0
    assert empty.json()["adoption_rate"] == 0.0
