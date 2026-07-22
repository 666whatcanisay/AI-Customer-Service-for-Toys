from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.models.chat import FrozenChatContext
from app.service.rag_service import RAGService
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

        def factory(active_settings: Settings) -> RAGService:
            return service

        with TestClient(create_app(settings=settings, rag_factory=factory)) as client:
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
            assert data["context"] == chat_context.model_dump()
            assert data["sources"][0]["knowledge_version"] == "V0.3.1"
    finally:
        service.close()
