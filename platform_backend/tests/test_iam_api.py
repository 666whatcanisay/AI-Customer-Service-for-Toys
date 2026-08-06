from datetime import datetime, timezone
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.iam.models import User, UserSession
from app.iam.schemas import RoleName, UserCreateRequest
from app.iam.service import UserService, ensure_default_roles
from app.main import app
from app.test_catalog.models import (
    TestKnowledgePackage as KnowledgePackageModel,
    TestProduct as ProductModel,
    TestStore as StoreModel,
)


PASSWORD = "Correct-Horse-42!"
TEMPORARY_PASSWORD = "TempPass"
REPLACEMENT_PASSWORD = "Replacement-Pass-42!"


@pytest.fixture
def auth_client(session: Session):
    def override_get_db():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_store(
    session: Session, *, package_id: str = "PKG-IAM-1", store_code: str = "STORE-IAM-1"
) -> StoreModel:
    now = datetime.now(timezone.utc)
    package = KnowledgePackageModel(
        package_id=package_id, package_name=f"{store_code} package", version="1",
        schema_version="0.3.1-test", tenant_id=f"tenant-{store_code}", platform="pdd",
        store_code=store_code, response_mode="SUGGESTION_ONLY", test_data_mode=True,
        production_usable=False, allow_auto_send=False, import_status="IMPORTED_TEST_ONLY",
        original_filename="synthetic.zip", zip_sha256="1" * 64, counts_json="{}",
        imported_by="pytest", imported_at=now,
    )
    store = StoreModel(
        package_id=package_id, tenant_id=package.tenant_id, platform="pdd",
        store_code=store_code, store_name=f"{store_code} 玩具店", trial_enabled=True,
        knowledge_scope="STORE_PRODUCT_SKU", response_mode="SUGGESTION_ONLY",
        allow_auto_send=False, test_data_mode=True, production_usable=False,
        data_source="TEST", customer_service_status="ENABLED", raw_data_json="{}",
    )
    session.add_all([package, store])
    session.commit()
    session.refresh(store)
    return store


def _seed_product(session: Session, store: StoreModel, product_id: str = "PRODUCT-IAM-1") -> None:
    session.add(ProductModel(
        product_id=product_id, package_id=store.package_id, tenant_id=store.tenant_id,
        platform=store.platform, store_code=store.store_code,
        product_name_official="身份测试积木", product_name_display="身份测试积木",
        sales_status="ON_SALE", age_min=6, age_max=12, safety_summary=None,
        review_status="APPROVED", publishable=True, customer_service_status="ENABLED",
        source_ids_json="[]", raw_data_json="{}",
    ))
    session.commit()


def _create_user(
    session: Session, username: str, role: RoleName, stores: list[dict] | None = None
):
    ensure_default_roles(session)
    return UserService(session).create_user(UserCreateRequest(
        username=username, password=PASSWORD, display_name=f"{username} display",
        roles=[role], store_bindings=stores or [],
    ), must_change_password=False)


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_uses_password_hash_and_persists_only_token_digest(
    auth_client: TestClient, session: Session
) -> None:
    created = _create_user(session, "admin.one", RoleName.ADMIN)
    user = session.get(User, created.id)
    assert user is not None
    assert user.password_hash.startswith("scrypt$v1$")
    assert PASSWORD not in user.password_hash

    token = _login(auth_client, "ADMIN.ONE")
    stored_session = session.scalar(select(UserSession).where(UserSession.user_id == created.id))
    assert stored_session is not None
    assert stored_session.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored_session.token_hash

    me = auth_client.get("/api/v1/auth/me", headers=_headers(token))
    assert me.status_code == 200
    assert me.json()["user"]["roles"] == ["ADMIN"]
    assert me.json()["user"]["all_store_access"] is True
    assert me.json()["user"]["must_change_password"] is False
    assert "password_hash" not in me.text
    assert "token_hash" not in me.text

    assert auth_client.post(
        "/api/v1/auth/login", json={"username": "admin.one", "password": "wrong"}
    ).status_code == 401
    assert auth_client.get("/api/v1/auth/me").status_code == 401

    assert auth_client.post("/api/v1/auth/logout", headers=_headers(token)).status_code == 204
    expired = auth_client.get("/api/v1/auth/me", headers=_headers(token))
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "SESSION_EXPIRED"


def test_admin_user_crud_role_assignment_and_store_binding(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session)
    _create_user(session, "root.admin", RoleName.ADMIN)
    token = _login(auth_client, "root.admin")

    created = auth_client.post("/api/v1/admin/users", headers=_headers(token), json={
        "username": "agent.zhang", "password": PASSWORD, "display_name": "张三",
        "roles": ["CUSTOMER_SERVICE"],
        "store_bindings": [{"store_id": store.id, "is_default": True}],
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["roles"] == ["CUSTOMER_SERVICE"]
    assert body["must_change_password"] is True
    assert body["stores"][0] == {
        "id": body["stores"][0]["id"], "store_id": store.id,
        "store_code": store.store_code, "store_name": store.store_name,
        "platform": "pdd", "is_default": True,
    }
    user_id = body["id"]

    listed = auth_client.get("/api/v1/admin/users", headers=_headers(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 2

    updated = auth_client.patch(
        f"/api/v1/admin/users/{user_id}", headers=_headers(token),
        json={"display_name": "张三（白班）"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "张三（白班）"

    roles = auth_client.put(
        f"/api/v1/admin/users/{user_id}/roles", headers=_headers(token),
        json={"roles": ["OPERATOR"]},
    )
    assert roles.status_code == 200
    assert roles.json()["roles"] == ["OPERATOR"]

    deactivated = auth_client.delete(
        f"/api/v1/admin/users/{user_id}", headers=_headers(token)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "DISABLED"
    assert auth_client.post(
        "/api/v1/auth/login", json={"username": "agent.zhang", "password": PASSWORD}
    ).status_code == 401


def test_rbac_and_store_projection_are_enforced_by_api(
    auth_client: TestClient, session: Session
) -> None:
    first = _seed_store(session, package_id="PKG-IAM-A", store_code="STORE-A")
    _seed_store(session, package_id="PKG-IAM-B", store_code="STORE-B")
    _create_user(
        session, "support.one", RoleName.CUSTOMER_SERVICE,
        [{"store_id": first.id, "is_default": True}],
    )
    _create_user(session, "operator.one", RoleName.OPERATOR)
    support_token = _login(auth_client, "support.one")
    operator_token = _login(auth_client, "operator.one")

    stores = auth_client.get(
        "/api/v1/customer-service/catalog/stores", headers=_headers(support_token)
    )
    assert stores.status_code == 200
    assert [item["store_code"] for item in stores.json()["items"]] == ["STORE-A"]

    denied_store = auth_client.get(
        "/api/v1/customer-service/catalog/products?store_code=STORE-B",
        headers=_headers(support_token),
    )
    assert denied_store.status_code == 403
    assert denied_store.json()["error"]["code"] == "AUTHORIZATION_DENIED"
    assert auth_client.get(
        "/api/v1/admin/users", headers=_headers(support_token)
    ).status_code == 403

    assert auth_client.get(
        "/api/v1/admin/overview", headers=_headers(operator_token)
    ).status_code == 200
    assert auth_client.get(
        "/api/v1/customer-service/catalog/stores", headers=_headers(operator_token)
    ).status_code == 403


def test_workspace_proxy_validates_bound_scope_before_unchanged_chat_forward(
    auth_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _seed_store(session)
    _seed_product(session, store)
    _create_user(
        session, "support.chat", RoleName.CUSTOMER_SERVICE,
        [{"store_id": store.id, "is_default": True}],
    )
    token = _login(auth_client, "support.chat")
    calls: list[tuple[str, str, dict | None]] = []

    def upstream(method: str, url: str, *, json=None, timeout=None):
        calls.append((method, url, json))
        return httpx.Response(200, json={
            "success": True, "message": "ok", "data": {
                "answer": "合成回答", "action": "DIRECT_ANSWER", "risk_level": "LOW",
                "sources": [], "warnings": [], "required_fields": [], "latency_ms": 1,
                "model": "synthetic", "request_id": "req-1", "context": json["context"],
            },
        })

    monkeypatch.setattr("app.workspace.routes.httpx.request", upstream)
    payload = {
        "question": "适合几岁？",
        "context": {
            "tenant_id": store.tenant_id, "platform": store.platform,
            "store_code": store.store_code, "product_id": "PRODUCT-IAM-1", "sku_id": None,
        },
    }
    response = auth_client.post(
        "/api/v1/workspace/ai-replies", headers=_headers(token), json=payload
    )
    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "合成回答"
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/api/chat")
    assert calls[0][2] == payload

    denied = payload | {"context": payload["context"] | {"store_code": "STORE-OTHER"}}
    assert auth_client.post(
        "/api/v1/workspace/ai-replies", headers=_headers(token), json=denied
    ).status_code == 403
    assert len(calls) == 1


def test_internal_username_initial_password_first_change_and_multi_store_selection(
    auth_client: TestClient, session: Session
) -> None:
    first = _seed_store(session, package_id="PKG-IAM-POLICY-A", store_code="STORE-POLICY-A")
    second = _seed_store(session, package_id="PKG-IAM-POLICY-B", store_code="STORE-POLICY-B")
    _create_user(session, "admin.validation", RoleName.ADMIN)
    token = _login(auth_client, "admin.validation")

    response = auth_client.post("/api/v1/admin/users", headers=_headers(token), json={
        "username": "Wa", "password": TEMPORARY_PASSWORD, "display_name": "客服主管",
        "roles": ["CUSTOMER_SERVICE"], "store_bindings": [],
    })
    assert response.status_code == 201, response.text
    assert response.json()["stores"] == []
    assert response.json()["must_change_password"] is True
    assert response.json()["all_store_access"] is False

    login = auth_client.post("/api/v1/auth/login", json={
        "username": "wa", "password": TEMPORARY_PASSWORD,
    })
    assert login.status_code == 200
    temporary_token = login.json()["access_token"]
    blocked = auth_client.get(
        "/api/v1/customer-service/catalog/stores", headers=_headers(temporary_token)
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = auth_client.post(
        "/api/v1/auth/change-password", headers=_headers(temporary_token), json={
            "current_password": TEMPORARY_PASSWORD,
            "new_password": REPLACEMENT_PASSWORD,
        },
    )
    assert changed.status_code == 204
    assert auth_client.get("/api/v1/auth/me", headers=_headers(temporary_token)).status_code == 401
    assert auth_client.post("/api/v1/auth/login", json={
        "username": "Wa", "password": TEMPORARY_PASSWORD,
    }).status_code == 401
    relogin = auth_client.post("/api/v1/auth/login", json={
        "username": "Wa", "password": REPLACEMENT_PASSWORD,
    })
    assert relogin.status_code == 200
    current_token = relogin.json()["access_token"]
    assert relogin.json()["user"]["must_change_password"] is False

    options = auth_client.get("/api/v1/auth/store-options", headers=_headers(current_token))
    assert options.status_code == 200
    assert {item["store_id"] for item in options.json()["items"]} == {first.id, second.id}
    selected = auth_client.put(
        "/api/v1/auth/store-bindings", headers=_headers(current_token),
        json={"store_ids": [first.id, second.id]},
    )
    assert selected.status_code == 200
    assert {item["store_id"] for item in selected.json()["stores"]} == {first.id, second.id}
    assert not any(item["is_default"] for item in selected.json()["stores"])

    visible = auth_client.get(
        "/api/v1/customer-service/catalog/stores", headers=_headers(current_token)
    )
    assert visible.status_code == 200
    assert {item["store_code"] for item in visible.json()["items"]} == {
        first.store_code, second.store_code,
    }

    duplicate = auth_client.post("/api/v1/admin/users", headers=_headers(token), json={
        "username": "wa", "password": TEMPORARY_PASSWORD, "display_name": "重复客服",
        "roles": ["CUSTOMER_SERVICE"], "store_bindings": [],
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "USERNAME_CONFLICT"


def test_chinese_operator_and_admin_receive_all_store_operations_scope(
    auth_client: TestClient, session: Session
) -> None:
    _seed_store(session, package_id="PKG-IAM-OPS", store_code="STORE-OPS")
    _create_user(session, "admin", RoleName.ADMIN)
    _create_user(session, "江", RoleName.OPERATOR)
    admin_token = _login(auth_client, "ADMIN")
    operator_token = _login(auth_client, "江")

    for current_token, expected_role in (
        (admin_token, "ADMIN"), (operator_token, "OPERATOR")
    ):
        me = auth_client.get("/api/v1/auth/me", headers=_headers(current_token))
        assert me.status_code == 200
        assert me.json()["user"]["roles"] == [expected_role]
        assert me.json()["user"]["all_store_access"] is True
        if expected_role == "OPERATOR":
            assert set(me.json()["user"]["permissions"]) == {
                "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
                "ai_quality.view", "store.view", "feedback.view",
            }
        overview = auth_client.get("/api/v1/admin/overview", headers=_headers(current_token))
        assert overview.status_code == 200


def test_invalid_username_and_blank_display_name_fail_validation(
    auth_client: TestClient, session: Session
) -> None:
    _create_user(session, "admin.validation", RoleName.ADMIN)
    token = _login(auth_client, "admin.validation")

    invalid_username = auth_client.post("/api/v1/admin/users", headers=_headers(token), json={
        "username": "bad name", "password": TEMPORARY_PASSWORD, "display_name": "无效账号",
        "roles": ["OPERATOR"], "store_bindings": [],
    })
    assert invalid_username.status_code == 422
    assert invalid_username.json()["error"]["code"] == "VALIDATION_ERROR"

    blank_name = auth_client.post("/api/v1/admin/users", headers=_headers(token), json={
        "username": "blank.display", "password": TEMPORARY_PASSWORD, "display_name": "   ",
        "roles": ["OPERATOR"], "store_bindings": [],
    })
    assert blank_name.status_code == 422
    assert blank_name.json()["error"]["code"] == "VALIDATION_ERROR"
