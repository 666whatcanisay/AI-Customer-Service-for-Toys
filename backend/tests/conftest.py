from __future__ import annotations

import math
import shutil
import time
from dataclasses import replace
from pathlib import Path

import pytest
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.service.rag_service import RAGService
from app.service.iam_authorization import require_operations_identity
from app.service.vector_store import VectorStore


class DeterministicEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic test embedding that never loads or downloads a model."""

    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        vectors: list[list[float]] = []
        for text in input:
            vector = [0.0] * 128
            for character in text:
                if not character.isspace():
                    vector[ord(character) % len(vector)] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    @staticmethod
    def name() -> str:
        return "deterministic_test_embedding"

    def get_config(self) -> dict[str, str]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, str]):
        del config
        return DeterministicEmbeddingFunction()


@pytest.fixture()
def api_client(tmp_path: Path):
    knowledge_path = tmp_path / "knowledge_base"
    vector_path = tmp_path / "vector_db"
    log_path = tmp_path / "logs"
    knowledge_path.mkdir()
    (knowledge_path / "synthetic-placeholder.pdf").write_bytes(b"test-only")

    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=knowledge_path,
        vector_db_path=vector_path,
        log_dir=log_path,
        llm_provider="bailian",
        llm_model="qwen-turbo",
        dashscope_api_key="",
        active_collection_name="test_documents",
        rag_distance_threshold=0.35,
        top_k=2,
    )
    store = VectorStore(
        persist_dir=vector_path,
        collection_name="test_documents",
        model_name="test-embedding",
        embedding_function=DeterministicEmbeddingFunction(),
    )
    store.build_index(
        [
            {
                "filename": "synthetic-toy-guide.pdf",
                "page_number": 1,
                "text": "星云狐狸玩具的指示灯是紫色，使用两节五号电池。",
            },
            {
                "filename": "synthetic-return-guide.pdf",
                "page_number": 2,
                "text": "合成测试订单可在七天内申请退货。",
            },
        ]
    )

    def factory(active_settings: Settings) -> RAGService:
        return RAGService(active_settings, vector_store=store)

    app = create_app(settings=settings, rag_factory=factory)
    app.dependency_overrides[require_operations_identity] = lambda: {
        "permissions": ["user.manage"]
    }
    with TestClient(app) as client:
        for _ in range(100):
            payload = client.get("/api/status").json()
            if payload.get("ready"):
                break
            time.sleep(0.01)
        assert client.get("/api/status").json()["ready"] is True
        yield client, vector_path

    shutil.rmtree(tmp_path, ignore_errors=True)
