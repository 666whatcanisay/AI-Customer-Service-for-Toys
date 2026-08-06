from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.knowledge_publishing.ai_client import AiKnowledgePublicationClient
from app.knowledge_publishing.models import ProductKnowledgePublication
from app.errors import AppError
from app.knowledge_publishing.schemas import ProductKnowledgePublishCommand
from app.knowledge_publishing.service import ProductKnowledgePublishingService
from tests.test_customer_catalog_api import _seed_product, _seed_scope


def _approved_product(
    session: Session,
    *,
    product_id: str = "PRODUCT-PUBLISH",
    data_source: str = "PILOT",
):
    store = _seed_scope(
        session,
        package_id=f"PKG-{product_id}",
        store_code=f"STORE-{product_id}",
        data_source=data_source,
        status="ENABLED",
        import_status="MANUAL_CREATED",
        schema_version="c-operation-store.v1",
    )
    product = _seed_product(
        session,
        store,
        product_id=product_id,
        status="DISABLED",
        display_name="发布测试积木",
    )
    product.review_status = "APPROVED"
    product.raw_data_json = '{"material":"ABS","recommended_age_text":"6岁+"}'
    session.commit()
    return product


def _publish_result(payload: dict) -> dict:
    return {
        "schema_version": "ai-product-knowledge-publication.v1",
        "publication_receipt_id": "RAG-RECEIPT-001",
        "status": "PUBLISHED",
        "product_id": payload["product_id"],
        "knowledge_fingerprint": payload["knowledge_fingerprint"],
        "active_collection": "isolated-r006-1",
        "chunk_count": 2,
        "embedding_count": 2,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def test_publish_is_approved_only_incremental_and_idempotent(
    client: TestClient, session: Session, monkeypatch
) -> None:
    product = _approved_product(session)
    monkeypatch.setattr(AiKnowledgePublicationClient, "publish", lambda self, payload: _publish_result(payload))

    before = client.get("/api/v1/admin/product-knowledge/products").json()["items"][0]
    assert before["ai_knowledge"]["status"] == "NOT_GENERATED"
    assert before["ai_knowledge"]["chunk_count"] == 0

    url = f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publications"
    command = {"operator": "pytest-operator", "confirmation_note": "人工确认发布"}
    first = client.post(url, json=command, headers={"Idempotency-Key": "publish-product-001"})
    assert first.status_code == 200
    body = first.json()
    assert body["changed"] is True
    assert body["ai_knowledge"]["status"] == "PUBLISHED"
    assert body["ai_knowledge"]["chunk_count"] == 2
    assert body["ai_knowledge"]["embedding_count"] == 2
    assert body["publication_receipt"]["publication_receipt_id"] == "RAG-RECEIPT-001"

    replay = client.post(url, json=command, headers={"Idempotency-Key": "publish-product-001"})
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    receipts = client.get(
        f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publication-receipts"
    ).json()
    assert receipts["total"] == 1

    product.raw_data_json = '{"material":"ABS","recommended_age_text":"8岁+"}'
    session.commit()
    changed = client.get("/api/v1/admin/product-knowledge/products").json()["items"][0]
    assert changed["ai_knowledge"]["status"] == "NEED_RESYNC"
    assert changed["ai_knowledge"]["indexed_fingerprint"] != changed["ai_knowledge"]["current_fingerprint"]


def test_publish_accepts_formalized_initial_import_source(
    client: TestClient, session: Session, monkeypatch
) -> None:
    product = _approved_product(
        session,
        product_id="PRODUCT-INITIAL-IMPORT",
        data_source="INITIAL_IMPORT",
    )
    captured: dict = {}

    def publish(self, payload):
        captured.update(payload)
        return _publish_result(payload)

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish", publish)
    response = client.post(
        f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publications",
        json={"operator": "pytest-operator", "confirmation_note": "人工确认发布"},
        headers={"Idempotency-Key": "publish-initial-import"},
    )

    assert response.status_code == 200
    assert captured["data_source"] == "INITIAL_IMPORT"


def test_publish_rejects_unapproved_and_records_sync_failure(
    client: TestClient, session: Session, monkeypatch
) -> None:
    product = _approved_product(session, product_id="PRODUCT-FAIL")
    url = f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publications"
    command = {"operator": "pytest-operator", "confirmation_note": "人工确认发布"}

    product.review_status = "DRAFT"
    session.commit()
    blocked = client.post(url, json=command, headers={"Idempotency-Key": "unapproved"})
    assert blocked.status_code == 409

    product.review_status = "APPROVED"
    session.commit()

    def fail_publish(self, payload):
        from app.knowledge_publishing.ai_client import AiKnowledgePublicationUnavailable

        raise AiKnowledgePublicationUnavailable("isolated failure")

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish", fail_publish)
    failed = client.post(url, json=command, headers={"Idempotency-Key": "publish-failure"})
    assert failed.status_code == 502
    row = session.get(ProductKnowledgePublication, product.product_id)
    assert row is not None
    assert row.status == "SYNC_FAILED"
    assert row.chunk_count == 0


def test_concurrent_publication_cannot_overwrite_the_product_lease(
    client: TestClient, session: Session, monkeypatch
) -> None:
    product = _approved_product(session, product_id="PRODUCT-CONCURRENT")
    observed: list[str] = []

    def publish(self, payload):
        with pytest.raises(AppError) as blocked:
            ProductKnowledgePublishingService(
                session, ai_client=self, lease_seconds=300
            ).publish(
                product.product_id,
                ProductKnowledgePublishCommand(
                    operator="competing-operator",
                    confirmation_note="并发发布应被阻止",
                ),
                "publish-concurrent-second",
            )
        observed.append(blocked.value.code)
        return _publish_result(payload)

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish", publish)
    response = client.post(
        f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publications",
        json={"operator": "first-operator", "confirmation_note": "首次发布"},
        headers={"Idempotency-Key": "publish-concurrent-first"},
    )

    assert response.status_code == 200
    assert observed == ["AI_KNOWLEDGE_PUBLISH_IN_PROGRESS"]
    row = session.get(ProductKnowledgePublication, product.product_id)
    assert row is not None
    assert row.status == "PUBLISHED"
    assert row.generation_token is None
    assert row.generation_started_at is None


def test_visibility_check_reconciles_product_level_evidence(
    client: TestClient, session: Session, monkeypatch
) -> None:
    product = _approved_product(session, product_id="PRODUCT-CHECK")

    def visibility(self, payload):
        item = payload["items"][0]
        return {
            "schema_version": "ai-product-knowledge-visibility.v1",
            "items": [
                {
                    "product_id": item["product_id"],
                    "status": "PUBLISHED",
                    "current_fingerprint": item["current_fingerprint"],
                    "indexed_fingerprint": item["current_fingerprint"],
                    "active_collection": "isolated-r006-1",
                    "chunk_count": 3,
                    "embedding_count": 3,
                }
            ],
        }

    monkeypatch.setattr(AiKnowledgePublicationClient, "visibility", visibility)
    response = client.post(
        f"/api/v1/admin/product-knowledge/products/{product.product_id}/ai-publication-checks",
        json={"operator": "pytest-operator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_knowledge"]["status"] == "PUBLISHED"
    assert body["ai_knowledge"]["chunk_count"] == 3
    assert body["ai_knowledge"]["embedding_count"] == 3
