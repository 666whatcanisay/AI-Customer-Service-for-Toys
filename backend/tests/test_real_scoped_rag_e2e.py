from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.models.chat import FrozenChatContext
from app.service.rag_service import RAGService
from app.service.iam_authorization import require_operations_identity
from app.service.test_knowledge import parse_test_knowledge_package
from app.service.vector_store import VectorStore


pytestmark = pytest.mark.real_rag
FIXTURE_DIR = Path(__file__).parent / "fixtures"
PACKAGE_ID = "PKG-PDD-SM-V031-SYNTHETIC"


@pytest.mark.skipif(
    os.getenv("RUN_REAL_RAG_E2E") != "1",
    reason="set RUN_REAL_RAG_E2E=1 for local BGE/Chroma/Ollama validation",
)
def test_real_scoped_q80_answer_and_api_smoke(tmp_path: Path):
    base = Settings.from_env()
    internal_service_secret = tmp_path / "internal-service.secret"
    internal_service_token = "real-scoped-rag-internal-service-token-32-bytes"
    internal_service_secret.write_text(internal_service_token, encoding="ascii")
    embedding_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="real_scoped_legacy",
        model_name=base.embedding_model,
        offline=True,
    )
    test_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="real_test_knowledge_v031",
        model_name=base.embedding_model,
        offline=True,
        embedding_function=embedding_store.embedding_fn,
    )
    settings = replace(
        base,
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=tmp_path / "knowledge_base",
        vector_db_path=tmp_path / "vector_db",
        log_dir=tmp_path / "logs",
        llm_provider="ollama",
        llm_model="qwen3.5:9b",
        llm_base_url="http://127.0.0.1:11434",
        llm_timeout_seconds=180,
        llm_max_tokens=256,
        rag_distance_threshold=0.45,
        top_k=3,
        test_knowledge_collection_name="real_test_knowledge_v031",
        active_collection_name="real_test_knowledge_v031",
        internal_service_secret_file=internal_service_secret,
    )
    service = RAGService(
        settings,
        vector_store=embedding_store,
        test_vector_store=test_store,
    )
    try:
        package = parse_test_knowledge_package(
            json.loads(
                (FIXTURE_DIR / "test_knowledge_v031.json").read_text(
                    encoding="utf-8"
                )
            ),
            PACKAGE_ID,
        )
        # Keep the frozen fixture untouched. This test-local evidence mirrors
        # the bounded age fact returned by the real C V0.3.1 package.
        package = replace(
            package,
            items=tuple(
                (
                    replace(
                        item,
                        content="Q80建议6～12岁儿童在成人看护下使用。",
                    )
                    if item.knowledge_id == "K-Q80-FAQ-AGE"
                    else item
                )
                for item in package.items
            ),
        )
        service.test_knowledge_index.sync(package)
        chat_context = FrozenChatContext(
            tenant_id="TENANT-PDD-SM-TEST",
            platform="pdd",
            store_code="PDD-SM",
            product_id="P-Q80",
            sku_id=None,
        )
        question = "Q80磁力积木套装包含多少颗积木？"
        result = service.query(question, chat_context)
        assert result["action"] == "DIRECT_ANSWER"
        assert "80" in result["answer"]
        assert "1688" not in result["answer"]
        assert result["sources"]
        assert all(source["product_id"] == "P-Q80" for source in result["sources"])
        assert all("SRC-1688-PRODUCT" not in source["source_ids"] for source in result["sources"])

        age_result = service.query("这个款式适合几岁的小朋友？", chat_context)
        assert "6～12岁" in age_result["answer"]
        assert not re.search(r"6\s*岁\s*(?:及\s*)?以上", age_result["answer"])
        assert re.search(r"3\s*岁以下", age_result["answer"])
        assert len(
            re.findall(
                r"(?:成人|家长|大人).{0,12}(?:陪同|看护|监护|陪伴)",
                age_result["answer"],
            )
        ) == 1
        assert all(
            term not in age_result["answer"]
            for term in ("资料", "依据摘要", "source_id", "SRC-")
        )
        assert "80颗" not in age_result["answer"]
        assert any(
            "SRC-Q80-SAFETY" in source["source_ids"]
            for source in age_result["sources"]
        )
        print(
            "REPLY_QUALITY_SMOKE="
            + json.dumps(
                {
                    "question": "这个款式适合几岁的小朋友？",
                    "answer": age_result["answer"],
                    "action": age_result["action"],
                    "risk_level": age_result["risk_level"],
                    "source_ids": [
                        source_id
                        for source in age_result["sources"]
                        for source_id in source["source_ids"]
                    ],
                    "model": age_result["model"],
                    "latency_ms": age_result["latency_ms"],
                },
                ensure_ascii=False,
            )
        )

        def factory(active_settings: Settings) -> RAGService:
            return service

        application = create_app(settings=settings, rag_factory=factory)
        application.dependency_overrides[require_operations_identity] = lambda: {
            "id": "real-rag-test-operator",
            "permissions": ["ai_quality.view"],
            "must_change_password": False,
        }
        with TestClient(
            application,
            headers={"X-AI-CS-Service-Token": internal_service_token},
        ) as client:
            for _ in range(100):
                if client.get("/api/status").json().get("ready"):
                    break
                time.sleep(0.01)
            assert client.get("/api/health").status_code == 200
            response = client.post(
                "/api/chat",
                json={
                    "question": question,
                    "context": chat_context.model_dump(),
                },
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["action"] == "DIRECT_ANSWER"
            assert data["context"] == chat_context.model_dump(mode="json")
            assert data["sources"][0]["knowledge_version"] == "V0.3.1"

            admin_response = client.post(
                "/api/admin/ai/modules/ai_customer_service/test",
                json={
                    "question": question,
                    "context": chat_context.model_dump(),
                    "include_diagnostics": True,
                },
            )
            assert admin_response.status_code == 200
            admin_data = admin_response.json()["data"]
            assert admin_data["action"] == "DIRECT_ANSWER"
            assert admin_data["model"] == "qwen3.5:9b"
            assert admin_data["sources"]
            assert admin_data["diagnostics"]["source_count"] >= 1

            metrics_response = client.get("/api/admin/ai/modules/ai_customer_service")
            assert metrics_response.status_code == 200
            assert metrics_response.json()["data"]["call_count"] >= 4
    finally:
        service.close()
