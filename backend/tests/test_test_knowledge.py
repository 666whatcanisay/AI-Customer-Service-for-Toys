from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config.settings import Settings
from app.main import create_app
from app.models.chat import FrozenChatContext
from app.service.evaluation import parse_evaluations, render_markdown, run_evaluations
from app.service.rag_service import RAGService, SAFETY_ACTION_MESSAGES
from app.service.test_knowledge import (
    PlatformTestKnowledgeClient,
    TestKnowledgeValidationError as PackageValidationError,
    parse_test_knowledge_package,
)
from app.service.vector_store import VectorStore
from conftest import DeterministicEmbeddingFunction


FIXTURE_DIR = Path(__file__).parent / "fixtures"
PACKAGE_ID = "PKG-PDD-SM-V031-SYNTHETIC"


def load_json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def context(product_id: str = "P-Q80", sku_id: str | None = None):
    return FrozenChatContext(
        tenant_id="TENANT-PDD-SM-TEST",
        platform="pdd",
        store_code="PDD-SM",
        product_id=product_id,
        sku_id=sku_id,
    )


@pytest.fixture()
def scoped_service(tmp_path: Path):
    embedding = DeterministicEmbeddingFunction()
    legacy_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="legacy_documents",
        model_name="deterministic",
        embedding_function=embedding,
    )
    test_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="test_knowledge_v031",
        model_name="deterministic",
        embedding_function=embedding,
    )
    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=tmp_path / "knowledge_base",
        vector_db_path=tmp_path / "vector_db",
        log_dir=tmp_path / "logs",
        llm_provider="bailian",
        dashscope_api_key="",
        rag_distance_threshold=0.15,
        top_k=3,
        platform_api_base_url="",
    )
    service = RAGService(
        settings,
        vector_store=legacy_store,
        test_vector_store=test_store,
    )
    package = parse_test_knowledge_package(
        load_json("test_knowledge_v031.json"), PACKAGE_ID
    )
    service.test_knowledge_index.sync(package)
    yield service, package
    service.close()


def test_v031_package_strict_safety_validation():
    payload = load_json("test_knowledge_v031.json")
    package = parse_test_knowledge_package(payload, PACKAGE_ID)
    assert package.tenant_id == "TENANT-PDD-SM-TEST"
    assert package.test_data_mode is True
    assert package.production_usable is False
    assert package.allow_auto_send is False
    assert package.response_mode == "SUGGESTION_ONLY"

    for field, invalid in (
        ("tenant_id", "TENANT-OTHER"),
        ("test_data_mode", False),
        ("production_usable", True),
        ("allow_auto_send", True),
        ("response_mode", "AUTO_SEND"),
    ):
        changed = load_json("test_knowledge_v031.json")
        changed[field] = invalid
        with pytest.raises(PackageValidationError):
            parse_test_knowledge_package(changed, PACKAGE_ID)


def test_sync_is_idempotent_and_metadata_is_complete(scoped_service):
    service, package = scoped_service
    first_count = service.test_vector_store.collection.count()
    result = service.test_knowledge_index.sync(package)
    assert result["synced_items"] == 12
    assert result["collection_count"] == first_count == 12

    stored = service.test_vector_store.collection.get(
        where={"package_id": {"$eq": PACKAGE_ID}},
        include=["metadatas"],
    )
    metadata = stored["metadatas"][0]
    assert {
        "tenant_id",
        "platform",
        "store_code",
        "product_id",
        "sku_id",
        "knowledge_type",
        "answer_action",
        "risk_level",
        "source_ids",
        "package_id",
    } <= metadata.keys()


def test_product_and_sku_scope_filtering_prevents_cross_product(scoped_service):
    service, _ = scoped_service
    product_results = service.test_knowledge_index.search(
        "Q80磁力积木套装包含80颗积木，商品编号为Q80。",
        context(),
        top_k=5,
    )
    assert product_results
    assert all(result["product_id"] == "P-Q80" for result in product_results)
    assert all(result["sku_id"] == "" for result in product_results)
    assert all("1688颗" not in result["content"] for result in product_results)

    sku_results = service.test_knowledge_index.search(
        "SKU-Q80-BLUE是Q80蓝色款，包装主色为蓝色。",
        context(sku_id="SKU-Q80-BLUE"),
        top_k=3,
    )
    assert sku_results[0]["sku_id"] == "SKU-Q80-BLUE"
    assert sku_results[0]["source_ids"] == ["SRC-Q80-SKU-BLUE"]

    sku_safety = service.test_knowledge_index.search(
        "Q80含有小零件，不适合3岁以下儿童；使用时需要成人看护。",
        context(sku_id="SKU-Q80-BLUE"),
        top_k=3,
    )
    assert any(
        result["source_ids"] == ["SRC-Q80-SAFETY"] for result in sku_safety
    )

    other_product = service.test_knowledge_index.search(
        "P-1688豪华积木套装包含1688颗积木。",
        context(product_id="P-1688"),
        top_k=3,
    )
    assert other_product
    assert all(result["product_id"] == "P-1688" for result in other_product)


def test_faq_reference_and_bundle_retrieval(scoped_service):
    service, _ = scoped_service
    faq = service.test_knowledge_index.search(
        "Q80建议6岁及以上儿童在成人看护下使用。", context(), 1
    )
    assert faq[0]["knowledge_type"] == "FAQ"
    assert faq[0]["source_ids"] == ["SRC-Q80-FAQ-AGE"]

    reference = service.test_knowledge_index.search(
        "SKU-Q80-BLUE为REFERENCE参考款，canonical SKU为SKU-Q80-BASE。",
        context(sku_id="SKU-Q80-BLUE"),
        1,
    )
    assert reference[0]["source_ids"] == ["SRC-Q80-REFERENCE"]

    bundle = service.test_knowledge_index.search(
        "SKU-Q80-BUNDLE为BUNDLE组合款，包含SKU-Q80-BLUE和SKU-Q80-PINK。",
        context(sku_id="SKU-Q80-BUNDLE"),
        1,
    )
    assert bundle[0]["source_ids"] == ["SRC-Q80-BUNDLE"]


def test_all_six_answer_actions_and_safety_actions_bypass_model(
    scoped_service, monkeypatch
):
    service, package = scoped_service
    by_action = {}
    for item in package.items:
        by_action.setdefault(item.answer_action, item)
    assert set(by_action) == {
        "DIRECT_ANSWER",
        "CONTROLLED_ANSWER",
        "ASK_CLARIFY",
        "REQUIRE_LOOKUP",
        "TRANSFER_HUMAN",
        "REFUSE",
    }

    for action in ("DIRECT_ANSWER", "CONTROLLED_ANSWER"):
        item = by_action[action]
        result = service.query(item.content, context(item.product_id, item.sku_id))
        assert result["action"] == action

    def model_must_not_run(*args, **kwargs):
        raise AssertionError("guarded safety action reached the model")

    monkeypatch.setattr(service, "call_llm", model_must_not_run)
    for action, message in SAFETY_ACTION_MESSAGES.items():
        item = by_action[action]
        result = service.query(item.content, context(item.product_id, item.sku_id))
        assert result["action"] == action
        assert result["answer"] == message


def test_no_hit_refuses_without_sources(scoped_service):
    service, _ = scoped_service
    result = service.query(
        "火星公司税率与量子发动机维修流程", context(product_id="P-Q80")
    )
    assert result["action"] == "REFUSE"
    assert result["sources"] == []
    assert result["warnings"] == ["NO_SCOPED_KNOWLEDGE"]


def test_chat_and_retrieval_smoke_use_frozen_context(scoped_service):
    service, _ = scoped_service

    def factory(active_settings: Settings) -> RAGService:
        return service

    app = create_app(settings=service.settings, rag_factory=factory)
    with TestClient(app) as client:
        for _ in range(100):
            if client.get("/api/status").json().get("ready"):
                break
            time.sleep(0.01)
        assert client.get("/api/health").status_code == 200
        payload = {
            "question": "Q80磁力积木套装包含80颗积木，商品编号为Q80。",
            "context": context().model_dump(),
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == {
            "answer",
            "action",
            "risk_level",
            "sources",
            "warnings",
            "required_fields",
            "model",
            "latency_ms",
            "request_id",
            "context",
        }
        assert set(data["sources"][0]) == {
            "source_name",
            "page",
            "chunk_id",
            "distance",
            "excerpt",
            "knowledge_version",
            "source_ids",
            "product_id",
            "sku_id",
        }
        retrieval = client.post(
            "/api/retrieval/search",
            json={"query": payload["question"], "context": payload["context"]},
        )
        assert retrieval.status_code == 200
        assert retrieval.json()["data"]["accepted"] is True


def test_invalid_store_context_and_unconfigured_live_sync_are_blocked(api_client):
    client, _ = api_client
    invalid = client.post(
        "/api/chat",
        json={
            "question": "test",
            "context": {
                "tenant_id": "TENANT-PDD-SM-TEST",
                "platform": "pdd",
                "store_code": "OTHER",
                "product_id": "P-Q80",
                "sku_id": "",
            },
        },
    )
    assert invalid.status_code == 422
    missing_context = client.post("/api/chat", json={"question": "test"})
    assert missing_context.status_code == 422
    sync = client.post(f"/api/test-knowledge/sync/{PACKAGE_ID}")
    assert sync.status_code == 503
    assert "ENV_BLOCKED" in sync.text

    with pytest.raises(ValidationError):
        FrozenChatContext(
            tenant_id="TENANT-PDD-SM-TEST",
            platform="pdd",
            store_code="OTHER",
            product_id="P-Q80",
            sku_id=None,
        )


def test_platform_client_uses_frozen_export_path(monkeypatch):
    payload = load_json("test_knowledge_v031.json")
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = PlatformTestKnowledgeClient("http://127.0.0.1:8012", 7)
    package = client.fetch_package(PACKAGE_ID)
    assert package.package_id == PACKAGE_ID
    assert seen == {
        "url": (
            "http://127.0.0.1:8012/api/v1/test-knowledge-packages/"
            f"{PACKAGE_ID}/rag-export"
        ),
        "timeout": 7,
    }


def test_28_evaluations_execute_and_render_reports():
    cases = parse_evaluations(load_json("evaluations_v031.json"), PACKAGE_ID)
    assert len(cases) == 28

    expected = {case.question: case for case in cases}

    def deterministic_query(question, chat_context):
        case = expected[question]
        return {
            "answer": " ".join(case.expected_contains),
            "action": case.expected_action,
            "risk_level": case.expected_risk_level,
            "sources": [
                {
                    "source_ids": list(case.expected_source_ids),
                    "product_id": chat_context.product_id,
                    "sku_id": chat_context.sku_id or "",
                }
            ],
            "required_fields": list(case.expected_required_fields),
            "latency_ms": 1.0,
        }

    report = run_evaluations(cases, deterministic_query)
    assert report["total"] == 28
    assert report["passed"] == 28
    assert report["failed"] == 0
    markdown = render_markdown(report)
    assert "E01" in markdown and "E28" in markdown
