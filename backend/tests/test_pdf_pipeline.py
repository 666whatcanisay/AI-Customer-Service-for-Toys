from __future__ import annotations

from pathlib import Path

import fitz

from app.service.document_loader import DocumentLoader
from app.service.vector_store import VectorStore
from conftest import DeterministicEmbeddingFunction


def test_synthetic_pdf_parses_chunks_indexes_and_retrieves(tmp_path: Path):
    knowledge_path = tmp_path / "knowledge_base"
    knowledge_path.mkdir()
    pdf_path = knowledge_path / "synthetic-toy-manual.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 540, 200),
        "Synthetic toy manual. Nebula Fox indicator color is violet. "
        "Nebula Fox uses two AA batteries.",
    )
    document.save(pdf_path)
    document.close()

    pages = DocumentLoader(knowledge_path).load_all_documents()
    assert len(pages) == 1
    assert "Nebula Fox" in pages[0]["text"]

    store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="synthetic_pdf",
        model_name="deterministic",
        chunk_size=100,
        overlap=20,
        embedding_function=DeterministicEmbeddingFunction(),
    )
    try:
        chunk_count = store.build_index(pages)
        assert chunk_count >= 1
        results = store.search("Nebula Fox indicator color violet", top_k=1)
        assert results
        assert results[0]["source_name"] == pdf_path.name
        assert results[0]["page"] == 1
        assert results[0]["chunk_id"]
        assert "violet" in results[0]["content"]
    finally:
        store.close()
