from fastapi.testclient import TestClient


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "display_name": "陈小林",
        "role": "CUSTOMER_SERVICE",
        "store_codes": ["STORE-ONE", "STORE-TWO"],
        "default_store_code": "STORE-ONE",
    }
    payload.update(overrides)
    return payload


def test_admin_can_create_edit_bind_and_disable_customer_user(
    client: TestClient, customer_identity_catalog: None
) -> None:
    created = client.post("/api/v1/admin/customer-users", json=_payload())
    assert created.status_code == 201
    body = created.json()
    assert body["user_id"].startswith("CSU-")
    assert body["status"] == "ACTIVE"
    assert [item["store_code"] for item in body["store_bindings"]] == ["STORE-ONE", "STORE-TWO"]

    user_id = body["user_id"]
    listed = client.get("/api/v1/admin/customer-users")
    assert listed.status_code == 200
    assert user_id in [item["user_id"] for item in listed.json()["items"]]

    updated = client.put(
        f"/api/v1/admin/customer-users/{user_id}",
        json=_payload(display_name="陈小林（夜班）", store_codes=["STORE-TWO"], default_store_code="STORE-TWO"),
    )
    assert updated.status_code == 200
    assert updated.json()["default_store_code"] == "STORE-TWO"
    assert updated.json()["store_bindings"] == [{"store_code": "STORE-TWO", "is_default": True}]

    disabled = client.post(f"/api/v1/admin/customer-users/{user_id}/status", json={"status": "DISABLED"})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    selectable = client.get("/api/v1/customer-identities")
    assert user_id not in [item["user_id"] for item in selectable.json()["items"]]


def test_user_write_rejects_missing_or_unbound_default_store(
    client: TestClient, customer_identity_catalog: None
) -> None:
    invalid = client.post(
        "/api/v1/admin/customer-users",
        json=_payload(default_store_code="UNKNOWN"),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "CUSTOMER_USER_VALIDATION_FAILED"

    missing = client.post(
        "/api/v1/admin/customer-users",
        json=_payload(store_codes=["UNKNOWN"], default_store_code="UNKNOWN"),
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "CUSTOMER_USER_STORE_BINDING_INVALID"


def test_case_and_feedback_reject_unknown_disabled_and_unbound_user(
    client: TestClient, customer_identity_catalog: None
) -> None:
    unknown_case = client.post(
        "/api/v1/customer-experience-cases",
        json={
            "store_code": "STORE-ONE", "product_id": None, "sku_id": None,
            "question": "Q", "ai_answer": "A", "final_answer": "F",
            "feedback_type": "ADOPTED", "created_by": "not-a-user",
        },
    )
    assert unknown_case.status_code == 404
    assert unknown_case.json()["error"]["code"] == "CUSTOMER_USER_NOT_FOUND"

    unbound_feedback = client.post(
        "/api/v1/ai-response-feedback",
        json={
            "store_code": "STORE-TWO", "product_id": None, "sku_id": None,
            "question": "Q", "ai_answer": "A", "final_answer": None, "feedback_type": "FACT_ERROR",
            "feedback_note": None, "created_by": "support-tester", "context": {"store_code": "STORE-TWO"},
        },
        headers={"Idempotency-Key": "identity-unbound"},
    )
    assert unbound_feedback.status_code == 403
    assert unbound_feedback.json()["error"]["code"] == "CUSTOMER_USER_STORE_FORBIDDEN"

    disable = client.post("/api/v1/admin/customer-users/support-tester/status", json={"status": "DISABLED"})
    assert disable.status_code == 200
    disabled_case = client.post(
        "/api/v1/customer-experience-cases",
        json={
            "store_code": "STORE-ONE", "product_id": None, "sku_id": None,
            "question": "Q", "ai_answer": "A", "final_answer": "F",
            "feedback_type": "ADOPTED", "created_by": "support-tester",
        },
    )
    assert disabled_case.status_code == 409
    assert disabled_case.json()["error"]["code"] == "CUSTOMER_USER_DISABLED"
