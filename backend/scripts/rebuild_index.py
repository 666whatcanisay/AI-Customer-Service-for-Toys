from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import get_settings
from app.service.document_loader import DocumentLoader
from app.service.vector_store import VectorStore


def main() -> int:
    settings = get_settings()
    vector_path = settings.vector_db_path.resolve()
    backend_root = settings.backend_root.resolve()

    try:
        with socket.create_connection((settings.host, settings.port), timeout=0.5):
            raise RuntimeError(
                "Rebuild refused: stop the backend with scripts/stop.ps1 first."
            )
    except (ConnectionRefusedError, TimeoutError, OSError):
        pass

    if not vector_path.is_relative_to(backend_root):
        raise RuntimeError("Rebuild refused: VECTOR_DB_PATH must be inside this backend directory.")
    if vector_path.name != "vector_db":
        raise RuntimeError("Rebuild refused: the vector directory name must be vector_db.")

    documents = DocumentLoader(settings.knowledge_base_path).load_all_documents()
    if not documents:
        raise RuntimeError("The knowledge base has no extractable text PDF pages.")

    if vector_path.exists():
        shutil.rmtree(vector_path)
    vector_path.mkdir(parents=True, exist_ok=True)

    store = VectorStore(
        persist_dir=vector_path,
        collection_name=settings.chroma_collection_name,
        model_name=settings.embedding_model,
        offline=settings.embedding_offline,
    )
    chunk_count = store.build_index(documents)
    stats = store.get_collection_stats()
    print(f"Index rebuild complete: pages={len(documents)} chunks={chunk_count}")
    print(f"collection={stats['collection_name']}")
    print(f"vector_db={vector_path}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
