import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.usefixtures("customer_identity_catalog")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "question": "What age range is appropriate?",
        "ai_answer": "The assistant suggested ages six through twelve.",
        "final_answer": "This item is suitable for ages six through twelve with adult supervision.",
        "feedback_type": "EDITED_ADOPTED",
        "created_by": "support-tester",
    }
    payload.update(overrides)
    return payload


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/customer-experience-cases", json=_payload(**overrides))
    assert response.status_code == 201
    return response.json()


def _review(client: TestClient, case_id: str, review_status: str, note: str = "Reviewed.") -> dict[str, object]:
    response = client.patch(
        f"/api/v1/admin/customer-experience-cases/{case_id}/review",
        json={
            "review_status": review_status,
            "review_note": note,
            "reviewed_by": "operations-test-operator",
        },
    )
    assert response.status_code == 200
    return response.json()


def _approve(client: TestClient, case_id: str) -> dict[str, object]:
    _review(client, case_id, "REVIEWING", "Started review.")
    return _review(client, case_id, "APPROVED", "Approved for controlled evaluation.")


def test_customer_submission_forces_governance_values_and_hides_internal_fields(client: TestClient) -> None:
    rejected = client.post(
        "/api/v1/customer-experience-cases",
        json={**_payload(), "review_status": "APPROVED", "review_note": "not allowed"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "EXPERIENCE_CASE_VALIDATION_FAILED"

    created = _create(client)
    assert created["case_id"].startswith("CEC-")
    assert created["revision"] == 1
    assert created["review_status"] == "NEW"
    assert "review_note" not in created

    history = client.get(
        "/api/v1/customer-experience-cases",
        params={"created_by": "support-tester", "review_status": "NEW"},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    projection = history.json()["items"][0]
    assert projection["case_id"] == created["case_id"]
    assert projection["review_status"] == "NEW"
    assert "question" not in projection
    assert "reviewed_by" not in projection


def test_admin_filters_review_state_machine_and_approved_immutability(client: TestClient) -> None:
    first = _create(client)
    second = _create(client, store_code="STORE-TWO", created_by="support-other")
    case_id = str(first["case_id"])

    filtered = client.get(
        "/api/v1/admin/customer-experience-cases",
        params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE", "created_by": "support-tester"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["case_id"] == case_id
    assert second["case_id"] != case_id

    invalid = client.patch(
        f"/api/v1/admin/customer-experience-cases/{case_id}/review",
        json={"review_status": "APPROVED", "reviewed_by": "operations-test-operator"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "EXPERIENCE_CASE_INVALID_STATUS_TRANSITION"

    reviewing = _review(client, case_id, "REVIEWING", "Examining the customer-service context.")
    assert reviewing["review_status"] == "REVIEWING"
    assert reviewing["reviewed_by"] == "operations-test-operator"

    approved = _review(client, case_id, "APPROVED", "Approved for controlled evaluation.")
    assert approved["review_status"] == "APPROVED"
    assert approved["reviewed_at"] is not None
    assert approved["export_revision"].endswith("-r1-e1")
    assert approved["content_hash"].startswith("sha256:")

    overwrite = client.patch(
        f"/api/v1/admin/customer-experience-cases/{case_id}/review",
        json={"review_status": "APPROVED", "review_note": "overwrite", "reviewed_by": "operations-test-operator"},
    )
    assert overwrite.status_code == 409
    assert overwrite.json()["error"]["code"] == "EXPERIENCE_CASE_REVISION_CONFLICT"


def test_export_only_contains_approved_snapshots_and_evaluation_requires_a_match(client: TestClient) -> None:
    new_case = _create(client, created_by="new-submitter")
    reviewing_case = _create(client, created_by="review-submitter")
    _review(client, str(reviewing_case["case_id"]), "REVIEWING")

    no_exports = client.get("/api/v1/admin/ai-optimization/cases/export")
    assert no_exports.status_code == 200
    assert no_exports.json() == {"items": [], "next_cursor": None}

    approved_case = _create(client, created_by="approved-submitter")
    approved = _approve(client, str(approved_case["case_id"]))
    exported = client.get("/api/v1/admin/ai-optimization/cases/export")
    assert exported.status_code == 200
    assert exported.json()["next_cursor"] is None
    assert [item["case_id"] for item in exported.json()["items"]] == [approved_case["case_id"]]
    snapshot = exported.json()["items"][0]
    assert snapshot["revision"] == 1
    assert snapshot["question"] == _payload()["question"]
    assert snapshot["content_hash"] == approved["content_hash"]
    assert snapshot["context"] == {"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE"}
    assert new_case["case_id"] not in str(exported.json())
    assert reviewing_case["case_id"] not in str(exported.json())

    mismatch = client.post(
        "/api/v1/admin/ai-optimization/evaluation-results",
        json={
            "case_id": approved_case["case_id"],
            "revision": 1,
            "export_revision": snapshot["export_revision"],
            "content_hash": "sha256:wrong",
            "evaluation_run_id": "AEC-run-1",
            "model_version": "synthetic-model-v1",
            "prompt_version": "synthetic-prompt-v1",
            "result": {"outcome": "NEEDS_REVIEW"},
            "suggestions": [{"category": "PROMPT_HYPOTHESIS", "description": "Keep age-range context."}],
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "EXPERIENCE_CASE_EXPORT_SNAPSHOT_MISMATCH"

    recorded = client.post(
        "/api/v1/admin/ai-optimization/evaluation-results",
        json={
            "case_id": approved_case["case_id"],
            "revision": 1,
            "export_revision": snapshot["export_revision"],
            "content_hash": snapshot["content_hash"],
            "evaluation_run_id": "AEC-run-1",
            "model_version": "synthetic-model-v1",
            "prompt_version": "synthetic-prompt-v1",
            "result": {"outcome": "NEEDS_REVIEW", "summary": "Synthetic evaluation evidence."},
            "suggestions": [{"category": "PROMPT_HYPOTHESIS", "description": "Keep age-range context."}],
        },
    )
    assert recorded.status_code == 201
    assert recorded.json()["evaluation_status"] == "EVALUATED"
    assert recorded.json()["evaluation_run_id"] == "AEC-run-1"

    pool = client.get("/api/v1/admin/ai-optimization/cases", params={"evaluation_status": "EVALUATED"})
    assert pool.status_code == 200
    assert pool.json()["total"] == 1
    assert pool.json()["items"][0]["latest_evaluation"]["result"]["outcome"] == "NEEDS_REVIEW"

    evidence = client.get(
        f"/api/v1/admin/ai-optimization/cases/{approved_case['case_id']}/evaluations",
        params={"revision": 1},
    )
    assert evidence.status_code == 200
    assert evidence.json()["total"] == 1
    assert evidence.json()["items"][0]["suggestions"][0]["category"] == "PROMPT_HYPOTHESIS"
