from fastapi.testclient import TestClient


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "question": "What safety information is missing?",
        "ai_answer": "This toy is suitable for children aged six to twelve.",
        "feedback_type": "MISSING_INFO",
        "feedback_note": None,
        "final_answer": "It is for ages six to twelve with adult supervision and not for children under three.",
        "created_by": "support-tester",
        "context": {
            "store_code": "STORE-ONE",
            "product_id": "PRODUCT-ONE",
            "sku_id": "SKU-ONE",
        },
    }
    payload.update(overrides)
    return payload


def _create(
    client: TestClient, *, idempotency_key: str = "feedback-submit-001", **overrides: object
) -> dict[str, object]:
    response = client.post(
        "/api/v1/ai-response-feedback",
        json=_payload(**overrides),
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response.status_code == 201
    return response.json()


def _confirm(client: TestClient, feedback_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/admin/ai-response-feedback/{feedback_id}/confirm",
        json={
            "confirmed_by": "operations-test-operator",
            "confirmation_reason": "Synthetic and de-identified test feedback confirmed for analysis.",
        },
    )
    assert response.status_code == 200
    return response.json()


def _analysis_payload(snapshot: dict[str, object], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "feedback_id": snapshot["feedback_id"],
        "revision": snapshot["revision"],
        "content_hash": snapshot["content_hash"],
        "feedback_type": snapshot["feedback_type"],
        "analysis_run_id": "AQR-test-001",
        "model_version": "synthetic-model-v1",
        "prompt_version": "ai-quality-feedback-v1",
        "analysis": {
            "summary": "The reply omitted a lower-age restriction.",
            "analysis_outcome": "NEEDS_REVIEW",
        },
        "suggestions": [
            {
                "category": "PROMPT_HYPOTHESIS",
                "description": "Include the lower-age safety restriction.",
                "evidence_summary": "Synthetic final-answer comparison.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_b_create_requires_idempotency_and_returns_personal_history_projection(client: TestClient) -> None:
    missing_key = client.post("/api/v1/ai-response-feedback", json=_payload())
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_VALIDATION_FAILED"

    forbidden_lifecycle = client.post(
        "/api/v1/ai-response-feedback",
        json={**_payload(), "status": "ANALYZED", "analysis_status": "ANALYZED"},
        headers={"Idempotency-Key": "forbidden-lifecycle"},
    )
    assert forbidden_lifecycle.status_code == 422
    assert forbidden_lifecycle.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_VALIDATION_FAILED"

    created = _create(client)
    assert set(created) == {"feedback_id", "status"}
    assert str(created["feedback_id"]).startswith("ARF-")
    assert created["status"] == "NEW"

    replay = _create(client)
    assert replay == created

    key_conflict = client.post(
        "/api/v1/ai-response-feedback",
        json=_payload(question="A different synthetic question."),
        headers={"Idempotency-Key": "feedback-submit-001"},
    )
    assert key_conflict.status_code == 409
    assert key_conflict.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_IDEMPOTENCY_CONFLICT"

    other = _create(
        client,
        idempotency_key="feedback-submit-002",
        feedback_type="RISK_ISSUE",
        created_by="support-other",
    )
    history = client.get(
        "/api/v1/ai-response-feedback",
        params={"created_by": "support-tester", "feedback_type": "MISSING_INFO", "status": "NEW"},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    projection = history.json()["items"][0]
    assert projection["feedback_id"] == created["feedback_id"]
    assert projection["revision"] == 1
    assert projection["status"] == "NEW"
    assert "question" not in projection
    assert "confirmed_by" not in projection
    assert other["feedback_id"] not in str(history.json())


def test_a_badcases_export_and_writeback_validate_frozen_snapshot_idempotently(client: TestClient) -> None:
    created = _create(client)
    feedback_id = str(created["feedback_id"])

    empty = client.get("/api/v1/admin/ai-quality/badcases")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None}
    old_path = client.get("/api/v1/admin/ai-quality/feedback-cases")
    assert old_path.status_code == 404

    confirmed = _confirm(client, feedback_id)
    assert confirmed["status"] == "ANALYZING"
    assert confirmed["analysis_status"] == "ANALYZING"
    assert confirmed["content_hash"].startswith("sha256:")

    exported = client.get("/api/v1/admin/ai-quality/badcases")
    assert exported.status_code == 200
    assert [item["feedback_id"] for item in exported.json()["items"]] == [feedback_id]
    snapshot = exported.json()["items"][0]
    assert snapshot["revision"] == 1
    assert snapshot["content_hash"] == confirmed["content_hash"]
    assert snapshot["feedback_type"] == "MISSING_INFO"
    assert snapshot["context"] == {
        "store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE"
    }
    assert snapshot["redaction_version"] == "v1-reminder-only"

    wrong_hash = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(snapshot, content_hash="sha256:wrong"),
    )
    assert wrong_hash.status_code == 409
    assert wrong_hash.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_EXPORT_SNAPSHOT_MISMATCH"

    wrong_type = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(snapshot, feedback_type="FACT_ERROR"),
    )
    assert wrong_type.status_code == 409
    assert wrong_type.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_TYPE_MISMATCH"

    recorded = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(snapshot),
    )
    assert recorded.status_code == 201
    assert recorded.json()["status"] == "ANALYZED"
    assert recorded.json()["analysis_run_id"] == "AQR-test-001"

    replay = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(snapshot),
    )
    assert replay.status_code == 200
    assert replay.json() == recorded.json()

    conflict = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(snapshot, analysis={"summary": "Different synthetic evidence."}),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_ANALYSIS_CONFLICT"

    after_analysis = client.get("/api/v1/admin/ai-quality/badcases")
    assert after_analysis.status_code == 200
    assert after_analysis.json() == {"items": [], "next_cursor": None}
