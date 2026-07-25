from fastapi.testclient import TestClient


def _payload(question: str) -> dict[str, object]:
    return {
        "store_code": "PILOT-STORE",
        "product_id": "PILOT-PRODUCT",
        "sku_id": "PILOT-SKU",
        "question": question,
        "ai_answer": "Synthetic pilot AI answer.",
        "final_answer": "Synthetic pilot final answer.",
        "feedback_type": "EDITED_ADOPTED",
        "created_by": "pilot-support",
    }


def _create(client: TestClient, question: str) -> str:
    response = client.post("/api/v1/customer-experience-cases", json=_payload(question))
    assert response.status_code == 201
    return response.json()["case_id"]


def _review(client: TestClient, case_id: str, status: str) -> dict[str, object]:
    response = client.patch(
        f"/api/v1/admin/customer-experience-cases/{case_id}/review",
        json={"review_status": status, "reviewed_by": "pilot-operator"},
    )
    assert response.status_code == 200
    return response.json()


def test_pilot_operation_dashboard_aggregates_existing_case_data_without_writes(client: TestClient) -> None:
    frequent_question = "How should the age range be explained?"
    new_case = _create(client, frequent_question)
    reviewing_case = _create(client, frequent_question)
    approved_case = _create(client, frequent_question)
    evaluated_case = _create(client, "What safety reminder is needed?")

    _review(client, reviewing_case, "REVIEWING")
    _review(client, approved_case, "REVIEWING")
    _review(client, approved_case, "APPROVED")
    _review(client, evaluated_case, "REVIEWING")
    approved = _review(client, evaluated_case, "APPROVED")
    exported = client.get("/api/v1/admin/ai-optimization/cases/export")
    snapshot = next(item for item in exported.json()["items"] if item["case_id"] == evaluated_case)
    evaluation = client.post(
        "/api/v1/admin/ai-optimization/evaluation-results",
        json={
            "case_id": evaluated_case,
            "revision": 1,
            "export_revision": snapshot["export_revision"],
            "content_hash": snapshot["content_hash"],
            "evaluation_run_id": "PILOT-EVAL-1",
            "model_version": "synthetic-model-v1",
            "prompt_version": "synthetic-prompt-v1",
            "result": {"outcome": "PASS"},
            "suggestions": [],
        },
    )
    assert evaluation.status_code == 201

    dashboard = client.get("/api/v1/admin/pilot-operation-dashboard")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["data_mode"] == "TEST_OR_PILOT"
    assert body["official_operation_report"] is False
    assert body["ai_call_measurement"] == "CASE_AI_ANSWER_PROXY"
    assert body["today"] == {
        "ai_call_count": 4,
        "case_submission_count": 4,
        "pending_review_count": 2,
        "approved_case_count": 2,
        "evaluated_case_count": 1,
    }
    assert body["experience_cases"] == {"new": 1, "reviewing": 1, "approved": 2, "evaluated": 1}
    assert body["frequent_questions"][0] == {"question": frequent_question, "case_count": 3}
    assert new_case not in str(body)
    assert approved["case_id"] == evaluated_case
