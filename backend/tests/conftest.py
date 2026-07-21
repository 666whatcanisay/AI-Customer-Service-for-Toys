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
from app.service.vector_store import VectorStore


class DeterministicEmbeddingFunction(EmbeddingFunction[Documents]):
    """Small deterministic test embedding; never downloads or loads the real model."""

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
    (knowledge_path / "test-knowledge.pdf").write_bytes(b"test-only-placeholder")

    base = Settings.from_env()
    settings = replace(
        base,
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=knowledge_path,
        vector_db_path=vector_path,
        log_dir=log_path,
        dashscope_api_key="",
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
                "filename": "党员章程测试.pdf",
                "page_number": 3,
                "text": "党员必须履行学习理论、遵守纪律、联系群众等义务。",
            },
            {
                "filename": "党费规定测试.pdf",
                "page_number": 2,
                "text": "党员应当按照规定按月缴纳党费。",
            },
        ]
    )

    def factory(active_settings: Settings) -> RAGService:
        return RAGService(active_settings, vector_store=store)

    app = create_app(settings=settings, rag_factory=factory)
    with TestClient(app) as client:
        for _ in range(100):
            payload = client.get("/api/status").json()
            if payload.get("ready"):
                break
            time.sleep(0.01)
        assert client.get("/api/status").json()["ready"] is True
        yield client, vector_path

    shutil.rmtree(tmp_path, ignore_errors=True)
