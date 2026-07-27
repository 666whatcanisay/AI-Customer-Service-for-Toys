"""Regression coverage for the minimal, non-production trial governance boundary."""

from fastapi.testclient import TestClient


def _case_payload() -> dict[str, object]:
    return {
        "store_code": "PILOT-STORE",
        "product_id": None,
        "sku_id": None,
        "question": "Synthetic customer question",
        "ai_answer": "Synthetic AI response",
        "final_answer": "Synthetic support response",
        "feedback_type": "EDITED_ADOPTED",
        "created_by": "support-agent",
    }


def test_trial_role_boundary_and_content_free_audit_foundation(client: TestClient) -> None:
    default_context = client.get("/api/v1/admin/trial-governance")

    assert default_context.status_code == 200, default_context.text
    assert default_context.json()["role"] == "OPERATOR"
    assert default_context.json()["formal_authentication_enabled"] is False
    assert default_context.json()["automatic_redaction_enabled"] is False

    support_headers = {
        "X-Platform-Trial-Actor": "trial-support",
        "X-Platform-Reason": "DAILY_OPERATIONS",
    }
    safe_store_read = client.get("/api/v1/admin/pilot-stores", headers=support_headers)
    forbidden_store_create = client.post(
        "/api/v1/admin/pilot-stores",
        headers=support_headers,
        json={"store_code": "PILOT-STORE", "store_name": "Pilot Store", "platform": "pdd"},
    )

    assert safe_store_read.status_code == 200, safe_store_read.text
    assert forbidden_store_create.status_code == 403
    assert forbidden_store_create.json()["error"]["code"] == "TRIAL_ROLE_FORBIDDEN"

    created = client.post("/api/v1/customer-experience-cases", json=_case_payload())
    assert created.status_code == 201, created.text

    forbidden_case_read = client.get("/api/v1/admin/customer-experience-cases", headers=support_headers)
    assert forbidden_case_read.status_code == 403
    assert forbidden_case_read.json()["error"]["code"] == "TRIAL_ROLE_FORBIDDEN"

    operator_headers = {
        "X-Platform-Trial-Actor": "trial-operator",
        "X-Platform-Reason": "CASE_REVIEW",
    }
    allowed_case_read = client.get("/api/v1/admin/customer-experience-cases", headers=operator_headers)
    assert allowed_case_read.status_code == 200, allowed_case_read.text
    assert allowed_case_read.json()["total"] == 1

    audit = client.get(
        "/api/v1/admin/trial-governance/audit-events",
        headers={
            "X-Platform-Trial-Actor": "trial-admin",
            "X-Platform-Reason": "GOVERNANCE_REVIEW",
        },
    )
    assert audit.status_code == 200, audit.text
    events = audit.json()["items"]
    case_view = next(item for item in events if item["action"] == "EXPERIENCE_CASE_VIEW")
    assert case_view["actor_role"] == "OPERATOR"
    assert case_view["reason_code"] == "CASE_REVIEW"
    assert case_view["resource_id"] == "collection"
    assert case_view["metadata"] == {"returned_count": 1}
    assert "Synthetic customer question" not in audit.text
    assert "Synthetic AI response" not in audit.text
    assert "support-agent" not in audit.text


def test_unknown_trial_actor_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/admin/trial-governance",
        headers={"X-Platform-Trial-Actor": "not-a-trial-actor"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TRIAL_ACTOR_UNKNOWN"
