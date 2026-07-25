from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ingestion.models import ImportBatch
from app.test_catalog.models import (
    TestConflictRecord as CatalogConflict,
    TestFaq as CatalogFaq,
    TestKnowledgePackage as CatalogPackage,
    TestProduct as CatalogProduct,
    TestSafetyRule as CatalogSafetyRule,
    TestSku as CatalogSku,
    TestSourceEvidence as CatalogSource,
    TestStore as CatalogStore,
)


def _seed_catalog(session: Session) -> None:
    now = datetime.now(timezone.utc)
    session.add(
        CatalogPackage(
            package_id="PKG-1",
            package_name="Synthetic governance package",
            version="V0.3.1",
            schema_version="0.3.1-test",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code="TEST-STORE",
            response_mode="SUGGESTION_ONLY",
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            import_status="IMPORTED_TEST_ONLY",
            original_filename="governance.zip",
            zip_sha256="a" * 64,
            counts_json="{}",
            imported_by="test",
            imported_at=now,
        )
    )
    session.add(
        CatalogStore(
            package_id="PKG-1",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code="TEST-STORE",
            store_name="Synthetic Store",
            trial_enabled=True,
            knowledge_scope="TEST_ONLY",
            response_mode="SUGGESTION_ONLY",
            allow_auto_send=False,
            test_data_mode=True,
            production_usable=False,
            raw_data_json="{}",
        )
    )
    session.add(
        CatalogProduct(
            product_id="P-1",
            package_id="PKG-1",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code="TEST-STORE",
            product_name_official="Synthetic product",
            product_name_display="Synthetic product",
            sales_status="ACTIVE",
            age_min=3,
            age_max=8,
            safety_summary="Use with adult supervision",
            review_status="TEST_CONFIRMED",
            publishable=False,
            source_ids_json='["SRC-1"]',
            raw_data_json="{}",
        )
    )
    session.add(
        CatalogSku(
            sku_id="SKU-1",
            package_id="PKG-1",
            product_id="P-1",
            sku_code="SKU-1",
            sku_name_official="Synthetic SKU",
            sku_name_display="Synthetic SKU",
            relation_type="REFERENCE",
            canonical_sku_id=None,
            reference_sku_id="SKU-0",
            component_sku_refs_json='["SKU-0"]',
            publishable=False,
            source_ids_json='["SRC-1"]',
            raw_data_json="{}",
        )
    )
    session.add(
        CatalogSource(
            source_id="SRC-1",
            package_id="PKG-1",
            product_id="P-1",
            sku_id="SKU-1",
            source_type="MANUAL",
            file_name="guide.pdf",
            relative_path="C:/private/source/guide.pdf",
            file_sha256="b" * 64,
            metadata_json='{"local_path":"C:/private/source/guide.pdf"}',
        )
    )
    session.add(
        CatalogFaq(
            faq_id="FAQ-1",
            package_id="PKG-1",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code="TEST-STORE",
            product_id="P-1",
            sku_id="SKU-1",
            canonical_question="Is it safe?",
            recommended_reply="Use only as instructed.",
            answer_action="CONTROLLED_ANSWER",
            risk_level="HIGH",
            source_ids_json='["SRC-1"]',
            raw_data_json="{}",
        )
    )
    session.add(
        CatalogSafetyRule(
            rule_id="RULE-1",
            package_id="PKG-1",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code="TEST-STORE",
            scenario="Small parts",
            rule_type="SAFETY",
            risk_level="HIGH",
            source_ids_json='["SRC-1"]',
            raw_data_json=(
                '{"allowed_action":"Use test-only advice",'
                '"forbidden_claim":"Do not promise suitability"}'
            ),
        )
    )
    session.add(
        CatalogConflict(
            issue_id="CONFLICT-1",
            package_id="PKG-1",
            entity_type="PRODUCT",
            entity_id="P-1",
            field_name="age_range",
            decision=None,
            status="PENDING",
            raw_data_json='{"value_a":"3-8","value_b":"4-8","source_ids":["SRC-1"]}',
        )
    )
    session.add(
        ImportBatch(
            tenant_id="TEST-TENANT",
            original_filename="products.xlsx",
            file_sha256="c" * 64,
            status="READY_FOR_REVIEW",
            created_at=now,
        )
    )
    session.commit()


def _suggestion_payload() -> dict[str, str]:
    return {
        "reporter_id": "agent-7",
        "reporter_name": "Support agent",
        "store_code": "TEST-STORE",
        "module_key": "customer-chat",
        "category": "workflow",
        "title": "Add a clearer safety reminder",
        "description": "The internal reminder should be easier to find.",
        "frequency": "weekly",
        "urgency": "HIGH",
    }


def test_customer_suggestion_is_persisted_with_a_forced_initial_status(client: TestClient) -> None:
    created = client.post("/api/v1/customer-suggestions", json=_suggestion_payload())

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "SUBMITTED"
    assert body["suggestion_id"] == body["id"]
    assert "internal_note" not in body

    history = client.get("/api/v1/customer-suggestions", params={"reporter_id": "agent-7"})
    assert history.status_code == 200
    assert history.json()["total"] == 1
    history_item = history.json()["items"][0]
    assert history_item["description"] == _suggestion_payload()["description"]
    assert history_item["suggestion_id"] == history_item["id"]


def test_admin_suggestion_lifecycle_only_allows_declared_transitions(client: TestClient) -> None:
    suggestion_id = client.post("/api/v1/customer-suggestions", json=_suggestion_payload()).json()["id"]

    updated = client.patch(
        f"/api/v1/admin/customer-suggestions/{suggestion_id}",
        json={"status": "REVIEWING", "internal_note": "Reviewed by operations."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "REVIEWING"
    assert updated.json()["internal_note"] == "Reviewed by operations."

    invalid = client.patch(
        f"/api/v1/admin/customer-suggestions/{suggestion_id}", json={"status": "SUBMITTED"}
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "SUGGESTION_INVALID_STATUS_TRANSITION"

    disallowed_field = client.patch(
        f"/api/v1/admin/customer-suggestions/{suggestion_id}", json={"title": "not allowed"}
    )
    assert disallowed_field.status_code == 422


def test_admin_suggestion_filters_and_empty_lists_are_stable(client: TestClient) -> None:
    client.post("/api/v1/customer-suggestions", json=_suggestion_payload())

    filtered = client.get(
        "/api/v1/admin/customer-suggestions",
        params={"status": "SUBMITTED", "module_key": "customer-chat", "urgency": "HIGH"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["internal_note"] is None

    empty = client.get("/api/v1/admin/customer-suggestions", params={"store_code": "missing"})
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "page": 1, "size": 20, "total": 0}


def test_admin_read_only_api_projects_real_catalog_data_without_local_paths(
    client: TestClient, session: Session
) -> None:
    _seed_catalog(session)
    client.post("/api/v1/customer-suggestions", json=_suggestion_payload())

    overview = client.get("/api/v1/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["counts"] == {
        "stores": 1,
        "products": 1,
        "skus": 1,
        "faqs": 1,
        "safety_rules": 1,
        "sources": 1,
        "conflicts": 1,
        "import_batches": 2,
        "suggestions": {"submitted": 1, "reviewing": 0, "planned": 0, "done": 0, "rejected": 0},
    }

    assert client.get("/api/v1/admin/stores").json()["items"][0]["product_count"] == 1
    products = client.get("/api/v1/admin/products", params={"store_code": "TEST-STORE"}).json()
    assert products["total"] == 1
    assert products["items"][0]["test_data_mode"] is True
    assert products["items"][0]["production_usable"] is False
    assert client.get("/api/v1/admin/products/P-1").json()["sku_count"] == 1
    assert client.get("/api/v1/admin/products/P-1/skus", params={"relation_type": "REFERENCE"}).json()["total"] == 1
    assert client.get("/api/v1/admin/faqs", params={"risk_level": "HIGH"}).json()["total"] == 1
    assert client.get("/api/v1/admin/safety-rules").json()["items"][0]["forbidden_claim"]

    sources = client.get("/api/v1/admin/sources", params={"product_id": "P-1"}).json()
    assert sources["total"] == 1
    assert sources["items"][0]["relative_path"] is None
    assert "private" not in str(sources)

    conflicts = client.get("/api/v1/admin/conflicts", params={"status": "PENDING"}).json()
    assert conflicts["items"][0]["value_a"] == "3-8"
    assert conflicts["items"][0]["value_b"] == "4-8"
    assert client.get("/api/v1/admin/import-batches").json()["total"] == 2

    assert client.get("/api/v1/admin/products/missing").json()["error"]["code"] == "ADMIN_PRODUCT_NOT_FOUND"
    assert client.get("/api/v1/admin/faqs", params={"store_code": "missing"}).json() == {
        "items": [], "page": 1, "size": 20, "total": 0
    }
