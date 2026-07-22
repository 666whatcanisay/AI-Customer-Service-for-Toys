from __future__ import annotations

import os
import json
import time
from dataclasses import replace
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from app.service.document_loader import DocumentLoader
from app.service.rag_service import RAGService, REFUSAL_MESSAGE
from app.service.vector_store import VectorStore


pytestmark = pytest.mark.real_rag


@pytest.mark.skipif(
    os.getenv("RUN_REAL_RAG_E2E") != "1",
    reason="set RUN_REAL_RAG_E2E=1 for local BGE/Chroma/Ollama validation",
)
def test_real_synthetic_pdf_to_qwen_answer_with_citations(tmp_path: Path):
    knowledge_path = tmp_path / "knowledge_base"
    knowledge_path.mkdir()
    pdf_path = knowledge_path / "synthetic-nebula-fox.pdf"
    question = "What color is the Nebula Fox safety indicator?"

    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 540, 220),
        "Synthetic support knowledge. Question: What color is the Nebula Fox "
        "safety indicator? Answer: The Nebula Fox safety indicator is violet. "
        "This document is synthetic test data.",
    )
    document.save(pdf_path)
    document.close()

    pages = DocumentLoader(knowledge_path).load_all_documents()
    assert len(pages) == 1

    base = Settings.from_env()
    store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="real_synthetic_rag",
        model_name=base.embedding_model,
        offline=True,
        chunk_size=300,
        overlap=40,
    )
    try:
        chunk_count = store.build_index(pages)
        assert chunk_count >= 1

        related = store.search(question, top_k=1)
        unrelated_question = "What is the corporate tax rate on Mars?"
        unrelated = store.search(unrelated_question, top_k=1)
        assert related and unrelated
        assert related[0]["distance"] < unrelated[0]["distance"]
        threshold = (related[0]["distance"] + unrelated[0]["distance"]) / 2

        settings = replace(
            base,
            backend_root=tmp_path,
            project_root=tmp_path,
            knowledge_base_path=knowledge_path,
            vector_db_path=tmp_path / "vector_db",
            log_dir=tmp_path / "logs",
            llm_provider="ollama",
            llm_model="qwen3.5:9b",
            llm_base_url="http://127.0.0.1:11434",
            llm_timeout_seconds=180,
            llm_max_tokens=256,
            rag_distance_threshold=threshold,
            top_k=1,
        )
        service = RAGService(settings, vector_store=store)

        retrieval = service.retrieve(question, top_k=1)
        assert retrieval["accepted"] is True
        citation = retrieval["sources"][0]
        assert citation["source_name"] == pdf_path.name
        assert citation["page"] == 1
        assert citation["chunk_id"]
        assert "violet" in citation["excerpt"]

        answer = service.query(question)
        assert answer["action"] == "ANSWER"
        assert answer["model"] == "qwen3.5:9b"
        assert answer["request_id"]
        assert answer["latency_ms"] > 0
        assert answer["sources"]
        assert "violet" in answer["answer"].lower() or "紫" in answer["answer"]

        refusal = service.query(unrelated_question)
        assert refusal["action"] == "REFUSE"
        assert refusal["answer"] == REFUSAL_MESSAGE
        assert refusal["sources"] == []

        print(
            "RAG_EVAL_RECORD="
            + json.dumps(
                {
                    "question": question,
                    "top_k": [
                        {
                            "source_name": citation["source_name"],
                            "page": citation["page"],
                            "chunk_id": citation["chunk_id"],
                            "distance": citation["distance"],
                        }
                    ],
                    "answer": answer["answer"],
                    "action": answer["action"],
                    "model": answer["model"],
                    "latency_ms": answer["latency_ms"],
                    "risk": "synthetic-data-only",
                    "refusal_question": unrelated_question,
                    "refusal_distance": unrelated[0]["distance"],
                    "refusal_action": refusal["action"],
                },
                ensure_ascii=False,
            )
        )

        def factory(active_settings: Settings) -> RAGService:
            return service

        app = create_app(settings=settings, rag_factory=factory)
        with TestClient(app) as client:
            for _ in range(100):
                status = client.get("/api/status").json()
                if status.get("ready"):
                    break
                time.sleep(0.01)
            health = client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["data"]["status"] == "ok"

            api_retrieval = client.post(
                "/api/retrieval/search", json={"query": question, "top_k": 1}
            )
            assert api_retrieval.status_code == 200
            assert api_retrieval.json()["data"]["accepted"] is True

            api_answer = client.post("/api/chat", json={"message": question})
            assert api_answer.status_code == 200
            api_answer_data = api_answer.json()["data"]
            assert {
                "answer",
                "action",
                "sources",
                "model",
                "latency_ms",
                "request_id",
            } <= api_answer_data.keys()
            assert api_answer_data["action"] == "ANSWER"
            assert api_answer_data["sources"][0]["chunk_id"]

            api_refusal = client.post(
                "/api/chat", json={"message": unrelated_question}
            )
            assert api_refusal.status_code == 200
            assert api_refusal.json()["data"]["action"] == "REFUSE"
    finally:
        store.close()
