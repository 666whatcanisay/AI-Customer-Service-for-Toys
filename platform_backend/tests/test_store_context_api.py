from datetime import datetime, timezone
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.iam.models import User
from app.database import get_db
from app.iam.schemas import RoleName, UserCreateRequest
from app.iam.service import UserService, ensure_default_roles
from app.test_catalog.models import (
    TestKnowledgePackage as KnowledgePackageModel,
    TestProduct as ProductModel,
    TestSku as SkuModel,
    TestStore as StoreModel,
)
from app.main import app
from app.workspace.models import ConversationContextResolution


PASSWORD = "Correct-Horse-42!"


@pytest.fixture
def auth_client(session: Session):
    def override_get_db():
        yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_store(session: Session, code: str) -> StoreModel:
    now = datetime.now(timezone.utc)
    package = KnowledgePackageModel(
        package_id=f"PKG-{code}", package_name=f"{code} package", version="1",
        schema_version="0.3.1-test", tenant_id=f"tenant-{code}", platform="pdd",
        store_code=code, response_mode="SUGGESTION_ONLY", test_data_mode=True,
        production_usable=False, allow_auto_send=False, import_status="IMPORTED_TEST_ONLY",
        original_filename="synthetic.zip", zip_sha256="1" * 64, counts_json="{}",
        imported_by="pytest", imported_at=now,
    )
    store = StoreModel(
        package_id=package.package_id, tenant_id=package.tenant_id, platform="pdd",
        store_code=code, store_name=f"{code} 玩具店", trial_enabled=True,
        knowledge_scope="STORE_PRODUCT_SKU", response_mode="SUGGESTION_ONLY",
        allow_auto_send=False, test_data_mode=True, production_usable=False,
        data_source="TEST", customer_service_status="ENABLED", raw_data_json="{}",
    )
    session.add_all([package, store]); session.commit(); session.refresh(store)
    return store


def _seed_product(
    session: Session, store: StoreModel, product_id: str, official: str, display: str
) -> ProductModel:
    product = ProductModel(
        product_id=product_id, package_id=store.package_id, tenant_id=store.tenant_id,
        platform=store.platform, store_code=store.store_code,
        product_name_official=official, product_name_display=display,
        sales_status="ON_SALE", age_min=3, age_max=12, safety_summary=None,
        review_status="APPROVED", publishable=True, customer_service_status="ENABLED",
        source_ids_json="[]", raw_data_json="{}",
    )
    session.add(product); session.commit()
    return product


def _seed_sku(session: Session, product: ProductModel, sku_id: str, name: str) -> None:
    session.add(SkuModel(
        sku_id=sku_id, package_id=product.package_id, product_id=product.product_id,
        sku_code=sku_id, sku_name_official=name, sku_name_display=name,
        relation_type="VARIANT", canonical_sku_id=None, reference_sku_id=None,
        component_sku_refs_json="[]", publishable=True,
        source_ids_json="[]", raw_data_json="{}",
    )); session.commit()


def _create_user(session: Session, username: str, role: RoleName, bindings=None):
    ensure_default_roles(session)
    return UserService(session).create_user(UserCreateRequest(
        username=username, password=PASSWORD, display_name=username,
        roles=[role], store_bindings=bindings or [],
    ), must_change_password=False)


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_workspace_context_loads_default_and_switches_only_authorized_store(
    auth_client: TestClient, session: Session
) -> None:
    first = _seed_store(session, "STORE-CONTEXT-A")
    second = _seed_store(session, "STORE-CONTEXT-B")
    third = _seed_store(session, "STORE-CONTEXT-C")
    _create_user(session, "support.context", RoleName.CUSTOMER_SERVICE, [
        {"store_id": first.id, "is_default": True},
        {"store_id": second.id, "is_default": False},
    ])
    headers = _login(auth_client, "support.context")

    context = auth_client.get("/api/v1/workspace/context", headers=headers)
    assert context.status_code == 200
    assert context.json()["user_id"]
    assert context.json()["effective_store"]["store_id"] == first.id
    assert {item["store_id"] for item in context.json()["stores"]} == {first.id, second.id}

    switched = auth_client.put(
        "/api/v1/auth/default-store", headers=headers, json={"store_id": second.id}
    )
    assert switched.status_code == 200
    assert next(item for item in switched.json()["stores"] if item["is_default"])["store_id"] == second.id
    switched_back = auth_client.put(
        "/api/v1/auth/default-store", headers=headers, json={"store_id": first.id}
    )
    assert switched_back.status_code == 200
    assert [
        item["store_id"] for item in switched_back.json()["stores"] if item["is_default"]
    ] == [first.id]
    assert auth_client.put(
        "/api/v1/auth/default-store", headers=headers, json={"store_id": third.id}
    ).status_code == 403


def test_product_and_sku_resolution_rules_and_minimized_audit(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-MATCH")
    blocks = _seed_product(session, store, "PRODUCT-BLOCKS", "创意积木", "积木")
    dinosaur = _seed_product(session, store, "PRODUCT-DINO", "恐龙积木", "积木")
    _seed_sku(session, blocks, "SKU-RED", "红色款")
    _seed_sku(session, blocks, "SKU-BLUE", "蓝色款")
    _seed_sku(session, dinosaur, "SKU-DINO", "标准款")
    user = _create_user(session, "support.match", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, "support.match")

    ambiguous = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={"conversation": [{"role": "CUSTOMER", "content": "请问这个积木适合几岁？"}]},
    )
    assert ambiguous.status_code == 201
    assert ambiguous.json()["status"] == "PRODUCT_CONFIRMATION_REQUIRED"
    assert {item["product_id"] for item in ambiguous.json()["product_candidates"]} == {
        blocks.product_id, dinosaur.product_id,
    }

    sku_needed = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={
            "conversation": [{"role": "CUSTOMER", "content": "请问这个积木适合几岁？"}],
            "confirmed_product_id": blocks.product_id,
        },
    )
    assert sku_needed.status_code == 201
    assert sku_needed.json()["status"] == "SKU_CONFIRMATION_REQUIRED"
    assert {item["sku_id"] for item in sku_needed.json()["sku_candidates"]} == {"SKU-RED", "SKU-BLUE"}

    sku_auto = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={
            "conversation": [{"role": "CUSTOMER", "content": "创意积木蓝色款有货吗？"}],
            "confirmed_product_id": blocks.product_id,
        },
    )
    assert sku_auto.status_code == 201
    assert sku_auto.json()["status"] == "RESOLVED"
    assert sku_auto.json()["sku"]["sku_id"] == "SKU-BLUE"

    resolved = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={
            "conversation": [{"role": "CUSTOMER", "content": "创意积木蓝色款有货吗？"}],
            "confirmed_product_id": blocks.product_id,
            "confirmed_sku_id": "SKU-BLUE",
        },
    )
    assert resolved.status_code == 201
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["product"]["product_id"] == blocks.product_id
    assert resolved.json()["sku"]["sku_id"] == "SKU-BLUE"

    unknown = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={"conversation": [{"role": "CUSTOMER", "content": "完全无关的问题"}]},
    )
    assert unknown.status_code == 201
    assert unknown.json()["status"] == "UNKNOWN"

    rows = list(session.scalars(select(ConversationContextResolution)))
    assert len(rows) == 5
    assert all(len(row.conversation_hash) == 64 for row in rows)
    assert all("积木" not in row.product_candidate_ids_json for row in rows)
    assert all(row.conversation_hash != hashlib.sha256("请问这个积木适合几岁？".encode()).hexdigest() for row in rows)
    assert not hasattr(rows[0], "conversation")
    assert user.id == rows[0].user_id


def test_unique_product_without_sku_auto_resolves_and_injects_unchanged_a_context(
    auth_client: TestClient, session: Session, monkeypatch
) -> None:
    store = _seed_store(session, "STORE-UNIQUE")
    product = _seed_product(session, store, "PRODUCT-UNIQUE", "唯一玩具", "唯一玩具")
    _create_user(session, "support.unique", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, "support.unique")
    resolved = auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=headers,
        json={"conversation": [{"role": "CUSTOMER", "content": "适合几岁？"}]},
    )
    assert resolved.status_code == 201
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["sku"] is None

    calls = []
    def upstream(method: str, url: str, *, json=None, headers=None, timeout=None):
        assert headers and headers["X-Request-ID"]
        calls.append(json)
        return httpx.Response(200, json={
            "success": True, "message": "ok", "data": {
                "answer": "合成回复", "action": "DIRECT_ANSWER", "risk_level": "LOW",
                "sources": [], "warnings": [], "required_fields": [], "latency_ms": 1,
                "model": "synthetic", "request_id": "req-context", "context": json["context"],
            },
        })
    monkeypatch.setattr("app.workspace.routes.httpx.request", upstream)
    answer = auth_client.post("/api/v1/workspace/ai-replies", headers=headers, json={
        "question": "适合几岁？", "resolution_id": resolved.json()["resolution_id"],
    })
    assert answer.status_code == 200
    assert calls == [{
        "question": "适合几岁？",
        "context": {
            "tenant_id": store.tenant_id, "platform": store.platform,
            "store_code": store.store_code, "product_id": product.product_id, "sku_id": None,
        },
    }]


@pytest.mark.parametrize("warning", ["RAG_RUNTIME_ERROR", "LLM_REQUEST_FAILED"])
def test_workspace_never_returns_operational_rag_failures_as_http_200(
    auth_client: TestClient,
    session: Session,
    monkeypatch,
    warning: str,
) -> None:
    store = _seed_store(session, f"STORE-RAG-{warning}")
    product = _seed_product(
        session, store, f"PRODUCT-{warning}", "错误状态玩具", "错误状态玩具"
    )
    _create_user(session, f"support.{warning.lower()}", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    headers = _login(auth_client, f"support.{warning.lower()}")

    def upstream(method: str, url: str, *, json=None, headers=None, timeout=None):
        del method, url, json, headers, timeout
        return httpx.Response(200, json={
            "success": True,
            "message": "ok",
            "warnings": [warning],
            "data": {"answer": "must-not-be-rendered", "warnings": [warning]},
        })

    monkeypatch.setattr("app.workspace.routes.httpx.request", upstream)
    response = auth_client.post(
        "/api/v1/workspace/ai-replies",
        headers=headers,
        json={
            "question": "错误时不能回答",
            "context": {
                "tenant_id": store.tenant_id,
                "platform": store.platform,
                "store_code": store.store_code,
                "product_id": product.product_id,
                "sku_id": None,
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_SERVICE_UNAVAILABLE"
    assert "must-not-be-rendered" not in response.text


def test_admin_can_view_identifier_only_resolution_audit_and_support_cannot(
    auth_client: TestClient, session: Session
) -> None:
    store = _seed_store(session, "STORE-AUDIT")
    _seed_product(session, store, "PRODUCT-AUDIT", "审计玩具", "审计玩具")
    support = _create_user(session, "support.audit", RoleName.CUSTOMER_SERVICE, [
        {"store_id": store.id, "is_default": True}
    ])
    _create_user(session, "admin.audit", RoleName.ADMIN)
    support_headers = _login(auth_client, "support.audit")
    admin_headers = _login(auth_client, "admin.audit")
    assert auth_client.post(
        "/api/v1/workspace/context-resolutions", headers=support_headers,
        json={"conversation": [{"role": "CUSTOMER", "content": "审计玩具怎么用？"}]},
    ).status_code == 201

    denied = auth_client.get("/api/v1/admin/store-context/resolutions", headers=support_headers)
    assert denied.status_code == 403
    audit = auth_client.get("/api/v1/admin/store-context/resolutions", headers=admin_headers)
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    item = audit.json()["items"][0]
    assert item["user_id"] == support.id
    assert "conversation" not in item
    assert "conversation_hash" not in item
