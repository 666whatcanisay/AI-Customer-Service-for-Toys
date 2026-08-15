from __future__ import annotations

import hashlib
import json


def publication_payload(*, fingerprint: str, document: str, key: str = "publish-one"):
    return {
        "schema_version": "ai-product-knowledge-publication.v1",
        "idempotency_key": key,
        "tenant_id": "TENANT-PILOT-ONE",
        "platform": "pinduoduo",
        "store_code": "STORE-PILOT-ONE",
        "product_id": "PRODUCT-PILOT-ONE",
        "product_name": "消防积木套装",
        "data_source": "PILOT",
        "knowledge_fingerprint": fingerprint,
        "document": document,
        "source_ids": ["R009-APPROVED-PRODUCT-PILOT-ONE"],
        "operator": "运营测试",
    }


def visibility_payload(fingerprint: str | None):
    return {
        "items": [
            {
                "tenant_id": "TENANT-PILOT-ONE",
                "platform": "pinduoduo",
                "store_code": "STORE-PILOT-ONE",
                "product_id": "PRODUCT-PILOT-ONE",
                "current_fingerprint": fingerprint,
            }
        ]
    }


def test_product_publication_is_incremental_visible_and_queryable(api_client):
    client, _ = api_client
    first_document = "商品名称：消防积木套装\n适用年龄：6岁以上\n材质：ABS"
    first_fingerprint = hashlib.sha256(first_document.encode("utf-8")).hexdigest()

    empty = client.post(
        "/api/admin/ai/knowledge-publications/visibility",
        json=visibility_payload(first_fingerprint),
    )
    assert empty.status_code == 200
    assert empty.json()["items"][0]["status"] == "NOT_GENERATED"

    published = client.post(
        "/api/admin/ai/knowledge-publications/products",
        json=publication_payload(
            fingerprint=first_fingerprint,
            document=first_document,
        ),
    )
    assert published.status_code == 200
    receipt = published.json()
    assert receipt["status"] == "PUBLISHED"
    assert receipt["chunk_count"] == receipt["embedding_count"] >= 1
    assert receipt["publication_receipt_id"].startswith("RAG-")

    visible = client.post(
        "/api/admin/ai/knowledge-publications/visibility",
        json=visibility_payload(first_fingerprint),
    ).json()["items"][0]
    assert visible["status"] == "PUBLISHED"
    assert visible["indexed_fingerprint"] == first_fingerprint
    assert visible["chunk_count"] == visible["embedding_count"]

    retrieval = client.post(
        "/api/retrieval/search",
        json={
            "query": f"消防积木套装\n{first_document}",
            "context": {
                "tenant_id": "TENANT-PILOT-ONE",
                "platform": "pinduoduo",
                "store_code": "STORE-PILOT-ONE",
                "product_id": "PRODUCT-PILOT-ONE",
                "sku_id": None,
            },
        },
    )
    assert retrieval.status_code == 200
    assert retrieval.json()["data"]["accepted"] is True
    assert retrieval.json()["data"]["sources"][0]["product_id"] == "PRODUCT-PILOT-ONE"

    second_document = first_document + "\n玩法：按说明书拼装消防场景"
    second_fingerprint = hashlib.sha256(second_document.encode("utf-8")).hexdigest()
    updated = client.post(
        "/api/admin/ai/knowledge-publications/products",
        json=publication_payload(
            fingerprint=second_fingerprint,
            document=second_document,
            key="publish-two",
        ),
    )
    assert updated.status_code == 200

    stale = client.post(
        "/api/admin/ai/knowledge-publications/visibility",
        json=visibility_payload(first_fingerprint),
    ).json()["items"][0]
    assert stale["status"] == "NEED_RESYNC"
    current = client.post(
        "/api/admin/ai/knowledge-publications/visibility",
        json=visibility_payload(second_fingerprint),
    ).json()["items"][0]
    assert current["status"] == "PUBLISHED"
    assert current["indexed_fingerprint"] == second_fingerprint


def test_publication_endpoints_require_safe_scope(api_client):
    client, _ = api_client
    document = "商品名称：测试商品"
    fingerprint = hashlib.sha256(document.encode("utf-8")).hexdigest()
    payload = publication_payload(fingerprint=fingerprint, document=document)
    payload["store_code"] = "BAD\nSTORE"

    response = client.post(
        "/api/admin/ai/knowledge-publications/products",
        json=payload,
    )
    assert response.status_code == 422


def test_publication_accepts_formalized_initial_import_source(api_client):
    client, _ = api_client
    document = "商品名称：初始化商品\n材质：ABS"
    fingerprint = hashlib.sha256(document.encode("utf-8")).hexdigest()
    payload = publication_payload(fingerprint=fingerprint, document=document)
    payload["data_source"] = "INITIAL_IMPORT"
    payload["product_id"] = "PRODUCT-INITIAL-IMPORT"
    payload["idempotency_key"] = "publish-initial-import"

    response = client.post(
        "/api/admin/ai/knowledge-publications/products",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"


def test_reviewed_approximate_fields_are_published_as_separate_controlled_facts(
    api_client,
):
    client, _ = api_client
    document = json.dumps(
        {
            "schema_version": "c-product-knowledge-document.v1",
            "reviewed_answer_controls": {
                "particle_count": {
                    "controlled_answer_kind": "REVIEWED_APPROXIMATE_FACT",
                    "material_id": "KMT-REVIEWED",
                    "material_revision": 2,
                    "material_content_hash": f"sha256:{'a' * 64}",
                }
            },
            "product": {
                "particle_count": "约500颗",
                "package_type": "彩盒包装",
                "common_customer_questions": ["多少颗粒", "什么包装"],
            },
            "skus": [],
            "faqs": [],
            "safety_rules": [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    fingerprint = hashlib.sha256(document.encode("utf-8")).hexdigest()
    payload = publication_payload(fingerprint=fingerprint, document=document)

    response = client.post(
        "/api/admin/ai/knowledge-publications/products",
        json=payload,
    )

    assert response.status_code == 200
    controlled = client.post(
        "/api/chat",
        json={
            "question": "particle_count: 约500颗",
            "context": {
                "tenant_id": payload["tenant_id"],
                "platform": payload["platform"],
                "store_code": payload["store_code"],
                "product_id": payload["product_id"],
                "sku_id": None,
            },
        },
    ).json()["data"]
    assert controlled["action"] == "CONTROLLED_ANSWER"
    assert controlled["risk_level"] == "MEDIUM"
    assert (
        controlled["sources"][0]["controlled_answer_kind"]
        == "REVIEWED_APPROXIMATE_FACT"
    )

    direct = client.post(
        "/api/chat",
        json={
            "question": "package_type: 彩盒包装",
            "context": {
                "tenant_id": payload["tenant_id"],
                "platform": payload["platform"],
                "store_code": payload["store_code"],
                "product_id": payload["product_id"],
                "sku_id": None,
            },
        },
    ).json()["data"]
    assert direct["action"] == "DIRECT_ANSWER"
    assert direct["risk_level"] == "LOW"
