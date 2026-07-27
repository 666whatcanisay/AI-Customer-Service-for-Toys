from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _feedback_payload() -> dict[str, object]:
    return {
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "question": "Synthetic question that must not enter the overview.",
        "ai_answer": "Synthetic answer that must not enter the overview.",
        "feedback_type": "MISSING_INFO",
        "final_answer": "Synthetic final answer that must not enter the overview.",
        "created_by": "support-tester",
        "context": {"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE"},
    }


def _record_completed_analysis(client: TestClient, feedback_id: str) -> None:
    confirmed = client.post(
        f"/api/v1/admin/ai-response-feedback/{feedback_id}/confirm",
        json={"confirmed_by": "operations-test-operator", "confirmation_reason": "Synthetic test evidence."},
    )
    assert confirmed.status_code == 200
    snapshot = client.get("/api/v1/admin/ai-quality/badcases").json()["items"][0]
    recorded = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json={
            "feedback_id": snapshot["feedback_id"],
            "revision": snapshot["revision"],
            "content_hash": snapshot["content_hash"],
            "feedback_type": snapshot["feedback_type"],
            "analysis_run_id": "AQR-operations-today",
            "model_version": "synthetic-model-v1",
            "prompt_version": "synthetic-prompt-v1",
            "analysis": {"summary": "Synthetic analysis."},
            "suggestions": [],
        },
    )
    assert recorded.status_code == 201


def test_daily_operations_snapshot_uses_one_utc_window_and_returns_no_content(
    client: TestClient,
) -> None:
    for event_type, key in (("AI_REQUEST", "operations-request"), ("DIRECT_ADOPTION", "operations-direct")):
        response = client.post(
            "/api/v1/customer-efficiency-events",
            json={"event_type": event_type},
            headers={"Idempotency-Key": key},
        )
        assert response.status_code == 201

    case = client.post(
        "/api/v1/customer-experience-cases",
        json={
            "store_code": "STORE-ONE",
            "product_id": "PRODUCT-ONE",
            "sku_id": "SKU-ONE",
            "question": "Synthetic experience question.",
            "ai_answer": "Synthetic experience AI answer.",
            "final_answer": "Synthetic experience final answer.",
            "feedback_type": "EDITED_ADOPTED",
            "created_by": "support-tester",
        },
    )
    assert case.status_code == 201

    completed = client.post(
        "/api/v1/ai-response-feedback",
        json=_feedback_payload(),
        headers={"Idempotency-Key": "operations-completed-feedback"},
    )
    assert completed.status_code == 201
    _record_completed_analysis(client, completed.json()["feedback_id"])
    pending = client.post(
        "/api/v1/ai-response-feedback",
        json=_feedback_payload() | {"question": "Second synthetic question."},
        headers={"Idempotency-Key": "operations-pending-feedback"},
    )
    assert pending.status_code == 201

    response = client.get("/api/v1/admin/operations/today")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"today", "work_queue", "knowledge", "test_data_mode", "production_usable"}
    assert body["today"]["ai_request_count"] == 1
    assert body["today"]["direct_adoption_count"] == 1
    assert body["today"]["adoption_rate"] == 1.0
    assert body["today"]["experience_case_submission_count"] == 1
    assert body["today"]["ai_feedback_submission_count"] == 2
    assert body["today"]["completed_ai_analysis_count"] == 1
    assert body["work_queue"]["pending_experience_review_count"] == 1
    assert body["work_queue"]["pending_ai_analysis_count"] == 1
    assert body["knowledge"] == {
        "store_count": 0,
        "product_count": 0,
        "sku_count": 0,
        "faq_count": 0,
        "safety_rule_count": 0,
        "recent_imported_at": None,
    }
    window_start = datetime.fromisoformat(body["today"]["window_start"].replace("Z", "+00:00"))
    window_end = datetime.fromisoformat(body["today"]["window_end"].replace("Z", "+00:00"))
    assert window_start.tzinfo == timezone.utc
    assert (window_start.hour, window_start.minute, window_start.second) == (0, 0, 0)
    assert window_end > window_start
    assert "Synthetic" not in str(body)
    assert "support-tester" not in str(body)
