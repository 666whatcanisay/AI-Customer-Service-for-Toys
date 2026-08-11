"""Independent platform-store identity management acceptance tests."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.store_platform_bindings.models import StorePlatformBinding
from app.test_catalog.models import (
    TestKnowledgePackage as CatalogPackage,
    TestStore as CatalogStore,
)


def _create_store(client: TestClient, name: str, platform: str = "pinduoduo") -> dict:
    response = client.post(
        "/api/v1/admin/operations/stores",
        json={"store_name": name, "platform": platform, "remarks": "平台身份绑定测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_platform_binding_is_independent_audited_and_reusable_after_revocation(
    client: TestClient,
    session: Session,
) -> None:
    first = _create_store(client, "玩具乐园积木店")
    second = _create_store(client, "同名无关展示店", "taobao")
    create_payload = {
        "platform": "pdd",
        "platform_store_id": "328616090",
        "change_reason": "管理员依据PDD只读页面人工核对",
        "confirmation_phrase": "确认绑定平台店铺",
    }

    created = client.post(
        f"/api/v1/admin/operations/stores/{first['store_ref']}/platform-bindings",
        json=create_payload,
    )

    assert created.status_code == 201, created.text
    binding = created.json()
    assert binding["store_name"] == "玩具乐园积木店"
    assert binding["platform"] == "pinduoduo"
    assert binding["platform_store_id"] == "328616090"
    assert binding["status"] == "ACTIVE"
    assert binding["verified_by"] == "00000000-0000-0000-0000-000000000001"
    assert binding["verified_at"]

    duplicate = client.post(
        f"/api/v1/admin/operations/stores/{second['store_ref']}/platform-bindings",
        json=create_payload,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "PLATFORM_STORE_ALREADY_BOUND"

    revoked = client.post(
        f"/api/v1/admin/operations/stores/{first['store_ref']}/platform-bindings/{binding['binding_id']}/revoke",
        json={
            "change_reason": "平台账号变更，保留原绑定历史记录",
            "confirmation_phrase": "确认撤销平台店铺绑定",
        },
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "REVOKED"
    assert revoked.json()["revoked_by"] == "00000000-0000-0000-0000-000000000001"

    reused = client.post(
        f"/api/v1/admin/operations/stores/{second['store_ref']}/platform-bindings",
        json={**create_payload, "change_reason": "旧绑定撤销后重新人工核对归属"},
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["store_id"] == second["store_ref"]

    history = client.get(
        f"/api/v1/admin/operations/stores/{first['store_ref']}/platform-bindings"
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["status"] == "REVOKED"
    assert session.get(StorePlatformBinding, binding["binding_id"]) is not None


def test_store_name_update_keeps_identity_and_updates_operation_package_label(
    client: TestClient,
    session: Session,
) -> None:
    created = _create_store(client, "玩趣乐园积木店")
    store = session.get(CatalogStore, created["store_ref"])
    assert store is not None
    store_code = store.store_code
    package_id = store.package_id

    updated = client.patch(
        f"/api/v1/admin/operations/stores/{created['store_ref']}",
        json={
            "store_name": "玩具乐园积木店",
            "platform": "pinduoduo",
            "status": "ACTIVE",
            "remarks": "修正文档录入时的店铺显示名称",
        },
    )

    assert updated.status_code == 200, updated.text
    session.expire_all()
    persisted = session.get(CatalogStore, created["store_ref"])
    package = session.get(CatalogPackage, package_id)
    assert persisted is not None and package is not None
    assert persisted.store_code == store_code
    assert persisted.store_name == "玩具乐园积木店"
    assert package.package_name == "玩具乐园积木店 · 运营建档"
