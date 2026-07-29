"""Acceptance tests for C operation completeness without schema migration."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.test_catalog.models import (
    TestKnowledgePackage as CatalogPackage,
    TestProduct as CatalogProduct,
    TestSku as CatalogSku,
    TestStore as CatalogStore,
)


def test_store_can_be_created_listed_viewed_and_edited_without_client_technical_ids(
    client: TestClient,
    session: Session,
) -> None:
    before_products = session.scalars(select(CatalogProduct)).all()

    created = client.post(
        "/api/v1/admin/operations/stores",
        json={
            "store_name": "星河玩具拼多多旗舰店",
            "platform": "pinduoduo",
            "remarks": "用于受控商品知识运营",
        },
    )

    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["store_name"] == "星河玩具拼多多旗舰店"
    assert payload["platform_name"] == "拼多多"
    assert payload["status_name"] == "正常"
    assert payload["product_count"] == 0
    assert "tenant_id" not in created.text
    assert "store_code" not in created.text
    assert "external_id" not in created.text

    store = session.get(CatalogStore, payload["store_ref"])
    assert store is not None
    assert store.tenant_id.startswith("c-tenant-")
    assert store.store_code.startswith("c-store-")
    package = session.get(CatalogPackage, store.package_id)
    assert package is not None
    assert package.production_usable is False
    assert package.allow_auto_send is False

    listed = client.get("/api/v1/admin/operations/stores")
    viewed = client.get(f"/api/v1/admin/operations/stores/{payload['store_ref']}")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["store_name"] == "星河玩具拼多多旗舰店"
    assert viewed.json()["store_ref"] == payload["store_ref"]
    assert viewed.json()["store_name"] == payload["store_name"]

    updated = client.patch(
        f"/api/v1/admin/operations/stores/{payload['store_ref']}",
        json={
            "store_name": "星河玩具官方旗舰店",
            "platform": "tmall",
            "status": "INACTIVE",
            "remarks": "暂停售后知识维护",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["store_name"] == "星河玩具官方旗舰店"
    assert updated.json()["platform_name"] == "天猫"
    assert updated.json()["status_name"] == "停用"
    assert updated.json()["remarks"] == "暂停售后知识维护"
    assert session.get(CatalogStore, payload["store_ref"]).trial_enabled is False
    assert session.scalars(select(CatalogProduct)).all() == before_products


def test_duplicate_store_name_on_same_platform_is_rejected(
    client: TestClient,
) -> None:
    request = {
        "store_name": "童趣玩具淘宝店",
        "platform": "taobao",
        "remarks": "",
    }
    assert client.post("/api/v1/admin/operations/stores", json=request).status_code == 201

    duplicate = client.post("/api/v1/admin/operations/stores", json=request)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "OPERATION_STORE_DUPLICATE"


def test_product_can_be_created_under_store_and_is_visible_without_becoming_publishable(
    client: TestClient,
    session: Session,
) -> None:
    store_response = client.post(
        "/api/v1/admin/operations/stores",
        json={
            "store_name": "星河玩具拼多多旗舰店",
            "platform": "pinduoduo",
            "remarks": "人工新增商品验收",
        },
    )
    store_ref = store_response.json()["store_ref"]

    created = client.post(
        f"/api/v1/admin/operations/stores/{store_ref}/products",
        json={
            "product_name": "城市消防局机械积木玩具套装",
            "product_summary": "可拼装消防局场景的机械积木套装。",
        },
    )

    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["store_ref"] == store_ref
    assert payload["store_name"] == "星河玩具拼多多旗舰店"
    assert payload["product_name"] == "城市消防局机械积木玩具套装"
    assert payload["product_summary"] == "可拼装消防局场景的机械积木套装。"
    assert payload["data_status"] == "PENDING_REVIEW"
    assert payload["sku_count"] == 0
    assert "tenant_id" not in created.text
    assert "store_code" not in created.text
    assert "external_id" not in created.text

    persisted = session.get(CatalogProduct, payload["product_ref"])
    assert persisted is not None
    assert persisted.product_id.startswith("C-PRODUCT-")
    assert persisted.review_status == "REVIEWING"
    assert persisted.sales_status == "OFF_SALE"
    assert persisted.publishable is False
    assert persisted.source_ids_json == "[]"
    assert "PRODUCT_CREATED" in persisted.raw_data_json
    assert session.scalars(select(CatalogSku)).all() == []

    refreshed_store = client.get(f"/api/v1/admin/operations/stores/{store_ref}")
    assert refreshed_store.json()["product_count"] == 1
    knowledge_products = client.get("/api/v1/admin/product-knowledge/products")
    assert knowledge_products.status_code == 200
    assert knowledge_products.json()["total"] == 1
    assert knowledge_products.json()["items"][0]["product_name"] == payload["product_name"]
    assert knowledge_products.json()["items"][0]["data_status"] == "PENDING_REVIEW"

    duplicate = client.post(
        f"/api/v1/admin/operations/stores/{store_ref}/products",
        json={"product_name": "城市消防局机械积木玩具套装", "product_summary": ""},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "OPERATION_PRODUCT_DUPLICATE"

    identity_override = client.post(
        f"/api/v1/admin/operations/stores/{store_ref}/products",
        json={
            "product_name": "客户端指定身份的商品",
            "product_summary": "",
            "tenant_id": "client-controlled",
            "product_id": "client-controlled",
        },
    )
    assert identity_override.status_code == 422


def test_product_basic_information_update_preserves_identity_and_enters_review(
    client: TestClient,
    session: Session,
) -> None:
    package = CatalogPackage(
        package_id="PKG-OPERATIONS",
        package_name="运营闭环测试包",
        version="1.0",
        schema_version="1.0",
        tenant_id="tenant-server-owned",
        platform="pinduoduo",
        store_code="store-server-owned",
        response_mode="SUGGEST_ONLY",
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=False,
        import_status="IMPORTED",
        original_filename="synthetic.xlsx",
        zip_sha256="d" * 64,
        counts_json="{}",
        imported_by="test",
    )
    store = CatalogStore(
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        store_name="原店铺名称",
        trial_enabled=True,
        knowledge_scope="TEST_ONLY",
        response_mode="SUGGEST_ONLY",
        allow_auto_send=False,
        test_data_mode=True,
        production_usable=False,
        raw_data_json="{}",
    )
    product = CatalogProduct(
        product_id="PRODUCT-IDENTITY-LOCKED",
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        product_name_official="原始商品名称",
        product_name_display="原始商品名称",
        sales_status="ON_SALE",
        age_min=None,
        age_max=None,
        safety_summary=None,
        review_status="APPROVED",
        publishable=True,
        source_ids_json="[]",
        raw_data_json=json.dumps({"product_summary": "原商品简介"}, ensure_ascii=False),
    )
    session.add_all([package, store, product])
    session.commit()

    updated = client.patch(
        "/api/v1/admin/operations/products/PRODUCT-IDENTITY-LOCKED/basic-info",
        json={
            "product_display_name": "城市消防局机械积木玩具套装",
            "product_summary": "可拼装消防局场景的机械积木套装。",
            "store_display_name": "木木小栈拼多多旗舰店",
            "store_remarks": "店铺展示信息已由运营核对",
        },
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["product"]["product_name"] == "城市消防局机械积木玩具套装"
    assert updated.json()["product"]["product_summary"] == "可拼装消防局场景的机械积木套装。"
    assert updated.json()["store"]["store_name"] == "木木小栈拼多多旗舰店"
    assert updated.json()["data_status"] == "PENDING_REVIEW"

    refreshed = client.get(
        "/api/v1/admin/product-knowledge/products/PRODUCT-IDENTITY-LOCKED"
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["product"]["product_name"] == "城市消防局机械积木玩具套装"
    persisted = session.get(CatalogProduct, "PRODUCT-IDENTITY-LOCKED")
    assert persisted is not None
    assert persisted.product_id == "PRODUCT-IDENTITY-LOCKED"
    assert persisted.product_name_official == "原始商品名称"
    assert persisted.review_status == "REVIEWING"
    assert persisted.publishable is False
    assert "PRODUCT_BASIC_INFO_UPDATED" in persisted.raw_data_json

    persisted.review_status = "APPROVED"
    persisted.publishable = True
    session.commit()
    store_only = client.patch(
        "/api/v1/admin/operations/products/PRODUCT-IDENTITY-LOCKED/basic-info",
        json={
            "product_display_name": "城市消防局机械积木玩具套装",
            "product_summary": "可拼装消防局场景的机械积木套装。",
            "store_display_name": "木木小栈玩具旗舰店",
            "store_remarks": "只更新店铺展示信息",
        },
    )
    assert store_only.status_code == 200
    assert store_only.json()["data_status"] == "APPROVED"
    assert session.get(CatalogProduct, "PRODUCT-IDENTITY-LOCKED").publishable is True
