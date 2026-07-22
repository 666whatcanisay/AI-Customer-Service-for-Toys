from __future__ import annotations

import logging
import os
import hashlib
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


logger = logging.getLogger(__name__)
os.environ.setdefault("USE_TF", "0")


class EmbeddingModelUnavailable(RuntimeError):
    pass


class LocalEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        offline: bool = True,
    ):
        self._model_name = model_name
        self._offline = offline

        model_path = Path(model_name).expanduser()
        is_local_path = model_path.exists()
        load_target = str(model_path.resolve()) if is_local_path else model_name

        if offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"

        load_source = "本地目录" if is_local_path else (
            "Hugging Face 本地缓存（离线模式）" if offline else "模型仓库/本地缓存"
        )
        logger.info("加载 Embedding 模型: %s；来源: %s", model_name, load_source)

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(
                model_name_or_path=load_target,
                local_files_only=offline,
                device="cpu",
            )
        except Exception as exc:
            if offline:
                raise EmbeddingModelUnavailable(
                    "本地未找到 Embedding 模型缓存。请联网预下载模型，"
                    "或将 EMBEDDING_MODEL 指向本地模型目录后重试。"
                ) from exc
            raise EmbeddingModelUnavailable(
                "Embedding 模型加载失败，请检查模型名称和网络连接。"
            ) from exc

        logger.info("Embedding 模型加载完成: %s", model_name)

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(
            input,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    @staticmethod
    def name() -> str:
        return "local_sentence_transformer"

    def get_config(self) -> dict[str, Any]:
        return {"model_name": self._model_name, "offline": self._offline}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "LocalEmbeddingFunction":
        return LocalEmbeddingFunction(
            model_name=config.get("model_name", "BAAI/bge-small-zh-v1.5"),
            offline=bool(config.get("offline", True)),
        )


class VectorStore:
    def __init__(
        self,
        persist_dir: str | Path,
        collection_name: str = "documents",
        model_name: str = "BAAI/bge-small-zh-v1.5",
        chunk_size: int = 500,
        overlap: int = 100,
        offline: bool = True,
        embedding_function: EmbeddingFunction[Documents] | None = None,
    ):
        self.persist_dir = Path(persist_dir).resolve()
        self.collection_name = collection_name
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.overlap = overlap
        if overlap >= chunk_size:
            raise ValueError("chunk overlap must be smaller than chunk size")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.client = chromadb.PersistentClient(path=str(self.persist_dir))
            self.embedding_fn = embedding_function or LocalEmbeddingFunction(
                model_name=model_name,
                offline=offline,
            )
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        except EmbeddingModelUnavailable:
            raise
        except Exception as exc:
            raise RuntimeError("ChromaDB 初始化失败，请检查向量库目录。") from exc

    def chunk_text(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        text_length = len(text)
        chinese_separators = ["\n", "。", "？", "！", "；", "；", "、", ".", "?", "!"]

        while start < text_length:
            end = start + self.chunk_size
            if end < text_length:
                best_end = end
                for separator in chinese_separators:
                    position = text.rfind(separator, start, end)
                    if position != -1 and position > start + self.chunk_size // 2:
                        best_end = position + 1
                        break
                end = best_end

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.overlap
            if start < 0:
                start = 0

        return chunks

    def build_index(self, documents: list[dict[str, Any]]) -> int:
        all_chunks: list[str] = []
        all_metadata: list[dict[str, Any]] = []
        all_ids: list[str] = []

        for document in documents:
            text = document.get("text", "")
            filename = document.get("filename", "")
            page_number = document.get("page_number", 0)
            for index, chunk in enumerate(self.chunk_text(text)):
                chunk_id = hashlib.sha256(
                    f"{filename}\n{page_number}\n{index}\n{chunk}".encode("utf-8")
                ).hexdigest()
                all_ids.append(chunk_id)
                all_chunks.append(chunk)
                all_metadata.append(
                    {
                        "file": filename,
                        "page": page_number,
                        "chunk_id": chunk_id,
                        "content": chunk[:100] + "..." if len(chunk) > 100 else chunk,
                    }
                )

        if all_chunks:
            self.collection.upsert(
                documents=all_chunks,
                metadatas=all_metadata,
                ids=all_ids,
            )
            logger.info(
                "索引写入完成: pages=%s chunks=%s",
                len(documents),
                len(all_chunks),
            )
        return len(all_chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        count = self.collection.count()
        if count == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, count),
        )
        search_results: list[dict[str, Any]] = []
        for index in range(len(results["ids"][0])):
            metadata = results["metadatas"][0][index]
            search_results.append(
                {
                    "source_name": metadata["file"],
                    "page": metadata["page"],
                    "chunk_id": metadata.get("chunk_id", results["ids"][0][index]),
                    "content": results["documents"][0][index],
                    "distance": float(results["distances"][0][index]),
                }
            )
        return search_results

    def get_collection_stats(self) -> dict[str, Any]:
        return {
            "total_chunks": self.collection.count(),
            "collection_name": self.collection_name,
            "model_name": self.model_name,
            "vector_db_path": str(self.persist_dir),
        }

    def close(self) -> None:
        try:
            system = getattr(self.client, "_system", None)
        except KeyError:
            system = None
        if system is not None:
            try:
                system.stop()
            except Exception:
                logger.debug("Chroma system was already stopped", exc_info=True)
        try:
            from chromadb.api.client import SharedSystemClient

            SharedSystemClient.clear_system_cache()
        except Exception:
            logger.debug("Unable to clear Chroma shared cache", exc_info=True)
