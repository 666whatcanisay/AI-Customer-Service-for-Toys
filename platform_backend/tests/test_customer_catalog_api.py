from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_publishing.canonical import build_canonical_product_knowledge
from app.knowledge_publishing.models import (
    ProductKnowledgePublication,
    ProductKnowledgePublicationReceipt,
)
from app.test_catalog.models import (
    CatalogActivationReceipt,
    TestKnowledgePackage as KnowledgePackageModel,
    TestProduct as ProductModel,
    TestSku as SkuModel,
    TestStore as StoreModel,
)


def _seed_scope(
    session: Session,
    *,
    package_id: str,
    store_code: str,
    data_source: str | None,
    status: str,
    import_status: str = "IMPORTED_TEST_ONLY",
    schema_version: str = "0.3.1-test",
    trial_enabled: bool = True,
) -> StoreModel:
    now = datetime.now(timezone.utc)
    package = KnowledgePackageModel(
        package_id=package_id,
        package_name=f"{store_code} package",
        version="1",
        schema_version=schema_version,
        tenant_id=f"tenant-{store_code}",
        platform="pdd",
        store_code=store_code,
        response_mode="SUGGESTION_ONLY",
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=False,
        import_status=import_status,
        original_filename="synthetic.zip",
        zip_sha256=(package_id.lower().replace("-", "0") + "0" * 64)[:64],
        counts_json="{}",
        imported_by="pytest",
        imported_at=now,
    )
    store = StoreModel(
        package_id=package_id,
        tenant_id=package.tenant_id,
        platform="pdd",
        store_code=store_code,
        store_name=f"{store_code} 测试店",
        trial_enabled=trial_enabled,
        knowledge_scope="STORE_PRODUCT_SKU",
        response_mode="SUGGESTION_ONLY",
        allow_auto_send=False,
        test_data_mode=True,
        production_usable=False,
        data_source=data_source,
        customer_service_status=status,
        raw_data_json="{}",
    )
    session.add_all([package, store])
    session.commit()
    session.refresh(store)
    return store


def _seed_product(
    session: Session,
    store: StoreModel,
    *,
    product_id: str,
    status: str,
    display_name: str = "测试积木",
    publishable: bool = False,
) -> ProductModel:
    product = ProductModel(
        product_id=product_id,
        package_id=store.package_id,
        tenant_id=store.tenant_id,
        platform=store.platform,
        store_code=store.store_code,
        product_name_official=display_name,
        product_name_display=display_name,
        sales_status="OFF_SALE",
        age_min=None,
        age_max=None,
        safety_summary=None,
        review_status="DRAFT",
        publishable=publishable,
        customer_service_status=status,
        source_ids_json="[]",
        raw_data_json="{}",
    )
    session.add(product)
    session.commit()
    return product


def _seed_sku(
    session: Session,
    product: ProductModel,
    *,
    sku_id: str,
    component_refs: str = "[]",
) -> SkuModel:
    sku = SkuModel(
        sku_id=sku_id,
        package_id=product.package_id,
        product_id=product.product_id,
        sku_code=sku_id,
        sku_name_official=f"{sku_id} 款",
        sku_name_display=f"{sku_id} 款",
        relation_type="INDEPENDENT",
        canonical_sku_id=None,
        reference_sku_id=None,
        component_sku_refs_json=component_refs,
        publishable=False,
        source_ids_json="[]",
        raw_data_json="{}",
    )
    session.add(sku)
    session.commit()
    return sku


def _activation(status: str, note: str = "运营已人工确认") -> dict[str, str]:
    return {
        "customer_service_status": status,
        "confirmed_by": "pytest-operator",
        "confirmation_note": note,
    }


def test_single_bad_store_is_partial_and_does_not_empty_valid_catalog(
    client: TestClient, session: Session
) -> None:
    _seed_scope(
        session,
        package_id="PKG-TEST",
        store_code="TEST-OK",
        data_source="TEST",
        status="ENABLED",
    )
    _seed_scope(
        session,
        package_id="PKG-PILOT",
        store_code="PILOT-OFF",
        data_source="PILOT",
        status="DISABLED",
        import_status="MANUAL_CREATED",
        schema_version="c-operation-store.v1",
    )
    _seed_scope(
        session,
        package_id="PKG-BAD",
        store_code="BAD",
        data_source=None,
        status="ENABLED",
        import_status="UNKNOWN",
        schema_version="unknown",
    )

    response = client.get("/api/v1/customer-service/catalog/stores")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "pilot-business-catalog.v1.1"
    assert body["result_status"] == "PARTIAL"
    assert body["total"] == 1
    assert body["items"][0]["store_code"] == "TEST-OK"
    assert body["items"][0]["customer_service_status"] == "ENABLED"
    assert body["warnings"] == [
        {
            "code": "CUSTOMER_SERVICE_SOURCE_UNKNOWN",
            "entity_type": "STORE",
            "count": 1,
            "message": "店铺数据来源无法确认，已隔离该记录。",
        }
    ]


def test_real_empty_catalog_is_complete(client: TestClient, session: Session) -> None:
    _seed_scope(
        session,
        package_id="PKG-OFF",
        store_code="ALL-OFF",
        data_source="PILOT",
        status="DISABLED",
    )

    response = client.get("/api/v1/customer-service/catalog/stores")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "pilot-business-catalog.v1.1",
        "result_status": "COMPLETE",
        "items": [],
        "total": 0,
        "warnings": [],
    }


def test_product_and_sku_visibility_ignore_publishable_and_knowledge_gaps(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-VISIBLE",
        store_code="VISIBLE",
        data_source="TEST",
        status="ENABLED",
    )
    product = _seed_product(
        session, store, product_id="PRODUCT-VISIBLE", status="ENABLED", publishable=False
    )
    _seed_sku(session, product, sku_id="SKU-GOOD")
    _seed_sku(session, product, sku_id="SKU-BAD", component_refs="not-json")

    products = client.get(
        "/api/v1/customer-service/catalog/products", params={"store_code": "VISIBLE"}
    )
    skus = client.get(
        "/api/v1/customer-service/catalog/products/PRODUCT-VISIBLE/skus"
    )

    assert products.status_code == 200
    assert products.json()["items"][0]["knowledge_status"] == "DRAFT"
    assert "publishable" not in products.json()["items"][0]
    assert skus.status_code == 200
    assert skus.json()["result_status"] == "PARTIAL"
    assert [item["sku_id"] for item in skus.json()["items"]] == ["SKU-GOOD"]
    assert skus.json()["items"][0]["customer_service_status"] == "ENABLED"


def test_customer_product_ai_knowledge_projects_receipt_and_chunk_evidence(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-AI-KNOWLEDGE",
        store_code="AI-KNOWLEDGE",
        data_source="PILOT",
        status="ENABLED",
        import_status="MANUAL_CREATED",
        schema_version="c-operation-store.v1",
    )
    product = _seed_product(
        session, store, product_id="PRODUCT-AI-KNOWLEDGE", status="ENABLED"
    )
    path = (
        "/api/v1/customer-service/catalog/products/"
        "PRODUCT-AI-KNOWLEDGE/ai-knowledge"
    )

    not_generated = client.get(path)
    assert not_generated.status_code == 200
    assert not_generated.json()["schema_version"] == (
        "customer-product-ai-knowledge-status.v1"
    )
    assert not_generated.json()["status"] == "NOT_GENERATED"
    assert not_generated.json()["publication_receipt_id"] is None
    assert not_generated.json()["chunk_count"] == 0

    fingerprint = build_canonical_product_knowledge(session, product).fingerprint
    now = datetime.now(timezone.utc)
    receipt = ProductKnowledgePublicationReceipt(
        publication_receipt_id="PUB-CUSTOMER-001",
        product_id=product.product_id,
        knowledge_fingerprint=fingerprint,
        active_collection="test_knowledge_v031",
        chunk_count=3,
        embedding_count=3,
        status="PUBLISHED",
        operator="pytest-operator",
        created_at=now,
    )
    ledger = ProductKnowledgePublication(
        product_id=product.product_id,
        status="PUBLISHED",
        current_fingerprint=fingerprint,
        indexed_fingerprint=fingerprint,
        active_collection="test_knowledge_v031",
        chunk_count=3,
        embedding_count=3,
        publication_receipt_id=receipt.publication_receipt_id,
        published_at=now,
        checked_at=now,
    )
    session.add_all([receipt, ledger])
    session.commit()

    published = client.get(path)
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["embedding_status"] == "COMPLETE"
    assert published.json()["publication_receipt_id"] == "PUB-CUSTOMER-001"
    assert published.json()["chunk_count"] == 3
    assert published.json()["embedding_count"] == 3

    session.delete(receipt)
    session.commit()
    missing_receipt = client.get(path)
    assert missing_receipt.status_code == 200
    assert missing_receipt.json()["status"] == "SYNC_FAILED"
    assert missing_receipt.json()["embedding_status"] == "FAILED"


def test_customer_product_ai_knowledge_does_not_expose_disabled_products(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-AI-KNOWLEDGE-OFF",
        store_code="AI-KNOWLEDGE-OFF",
        data_source="PILOT",
        status="ENABLED",
    )
    product = _seed_product(
        session, store, product_id="PRODUCT-AI-KNOWLEDGE-OFF", status="DISABLED"
    )

    response = client.get(
        f"/api/v1/customer-service/catalog/products/{product.product_id}/ai-knowledge"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CUSTOMER_SERVICE_ENTITY_NOT_FOUND"


def test_operator_activation_receipts_idempotency_and_parent_blocking(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-ACT",
        store_code="PILOT-ACT",
        data_source="PILOT",
        status="DISABLED",
        import_status="MANUAL_CREATED",
        schema_version="c-operation-store.v1",
    )
    product = _seed_product(
        session, store, product_id="PRODUCT-ACT", status="DISABLED"
    )
    product.review_status = "APPROVED"
    session.commit()
    product_url = "/api/v1/admin/operations/products/PRODUCT-ACT/customer-service-status"
    store_url = f"/api/v1/admin/operations/stores/{store.id}/customer-service-status"

    blocked = client.put(
        product_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "product-before-store"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CUSTOMER_SERVICE_STORE_NOT_ENABLED"

    enabled_store = client.put(
        store_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "enable-store"},
    )
    replayed = client.put(
        store_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "enable-store"},
    )
    conflict = client.put(
        store_url,
        json=_activation("DISABLED", "另一请求"),
        headers={"Idempotency-Key": "enable-store"},
    )
    assert enabled_store.status_code == 200
    assert enabled_store.json()["changed"] is True
    receipt_id = enabled_store.json()["activation_receipt"]["activation_receipt_id"]
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.json()["activation_receipt"]["activation_receipt_id"] == receipt_id
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ACTIVATION_IDEMPOTENCY_CONFLICT"

    enabled_product = client.put(
        product_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "enable-product"},
    )
    assert enabled_product.status_code == 200
    assert enabled_product.json()["activation_receipt"]["entity_type"] == "PRODUCT"
    visible = client.get(
        "/api/v1/customer-service/catalog/products",
        params={"store_code": store.store_code},
    )
    assert [item["product_id"] for item in visible.json()["items"]] == [product.product_id]

    disabled_store = client.put(
        store_url,
        json=_activation("DISABLED"),
        headers={"Idempotency-Key": "disable-store"},
    )
    assert disabled_store.status_code == 200
    session.refresh(product)
    assert product.customer_service_status == "ENABLED"
    assert client.get(
        "/api/v1/customer-service/catalog/products",
        params={"store_code": store.store_code},
    ).json()["items"] == []

    reenabled_store = client.put(
        store_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "reenable-store"},
    )
    assert reenabled_store.status_code == 200
    assert client.get(
        "/api/v1/customer-service/catalog/products",
        params={"store_code": store.store_code},
    ).json()["total"] == 1

    no_change = client.put(
        store_url,
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "already-enabled"},
    )
    assert no_change.json()["changed"] is False
    assert no_change.json()["activation_receipt"] is None
    assert session.scalar(
        select(CatalogActivationReceipt).where(
            CatalogActivationReceipt.activation_receipt_id == receipt_id
        )
    ) is not None
    history = client.get(
        "/api/v1/admin/operations/activation-receipts",
        params={"entity_type": "STORE", "entity_ref": str(store.id)},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 3
    assert client.get(
        f"/api/v1/admin/operations/activation-receipts/{receipt_id}"
    ).json()["activation_receipt_id"] == receipt_id


def test_single_invalid_product_does_not_hide_valid_product(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-PARTIAL",
        store_code="PARTIAL",
        data_source="TEST",
        status="ENABLED",
    )
    _seed_product(session, store, product_id="GOOD", status="ENABLED")
    _seed_product(
        session, store, product_id="BAD", status="ENABLED", display_name=""
    )
    bad = session.get(ProductModel, "BAD")
    assert bad is not None
    bad.product_name_official = ""
    session.commit()

    response = client.get(
        "/api/v1/customer-service/catalog/products",
        params={"store_code": store.store_code},
    )

    assert response.status_code == 200
    assert response.json()["result_status"] == "PARTIAL"
    assert [item["product_id"] for item in response.json()["items"]] == ["GOOD"]


def test_unknown_source_cannot_be_enabled(client: TestClient, session: Session) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-UNKNOWN",
        store_code="UNKNOWN",
        data_source=None,
        status="DISABLED",
        import_status="UNKNOWN",
        schema_version="unknown",
    )
    response = client.put(
        f"/api/v1/admin/operations/stores/{store.id}/customer-service-status",
        json=_activation("ENABLED"),
        headers={"Idempotency-Key": "unknown-source"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CUSTOMER_SERVICE_ENTITY_QUARANTINED"


def test_batch_enable_only_approved_products_and_isolate_failures(
    client: TestClient, session: Session
) -> None:
    store = _seed_scope(
        session,
        package_id="PKG-BATCH",
        store_code="BATCH",
        data_source="PILOT",
        status="ENABLED",
        import_status="MANUAL_CREATED",
        schema_version="c-operation-store.v1",
    )
    approved = _seed_product(
        session, store, product_id="BATCH-APPROVED", status="DISABLED"
    )
    approved.review_status = "APPROVED"
    draft = _seed_product(session, store, product_id="BATCH-DRAFT", status="DISABLED")
    draft.review_status = "DRAFT"
    session.commit()

    payload = {
        "product_ids": [approved.product_id, draft.product_id, "BATCH-MISSING"],
        "confirmed_by": "pytest-operator",
        "confirmation_note": "批量启用已审核商品",
    }
    first = client.post(
        "/api/v1/admin/operations/products/customer-service-status:batch",
        json=payload,
        headers={"Idempotency-Key": "batch-enable-001"},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["result_status"] == "PARTIAL"
    assert body["changed_count"] == 1
    assert body["failed_count"] == 2
    assert body["items"][0]["status"] == "CHANGED"
    assert body["items"][0]["activation_receipt"]["entity_ref"] == approved.product_id
    assert body["items"][1]["error_code"] == "CUSTOMER_SERVICE_PRODUCT_NOT_APPROVED"
    assert body["items"][2]["error_code"] == "CUSTOMER_SERVICE_ENTITY_NOT_FOUND"

    session.refresh(approved)
    session.refresh(draft)
    assert approved.customer_service_status == "ENABLED"
    assert draft.customer_service_status == "DISABLED"

    replay = client.post(
        "/api/v1/admin/operations/products/customer-service-status:batch",
        json=payload,
        headers={"Idempotency-Key": "batch-enable-001"},
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == body
