from __future__ import annotations

import logging
import time
from dataclasses import replace
from threading import RLock
from typing import Any

from openai import OpenAI

from app.config.settings import Settings
from app.service.vector_store import VectorStore


logger = logging.getLogger(__name__)
MODEL_NOT_CONFIGURED_MESSAGE = (
    "大模型尚未配置，当前已完成知识库检索，但暂时无法生成完整回答。"
)


class RAGService:
    def __init__(
        self,
        settings: Settings,
        vector_store: VectorStore | None = None,
    ):
        self.settings = settings
        self.vector_store = vector_store or VectorStore(
            persist_dir=settings.vector_db_path,
            collection_name=settings.chroma_collection_name,
            model_name=settings.embedding_model,
            offline=settings.embedding_offline,
        )
        self.client: OpenAI | None = None
        self._configuration_lock = RLock()

        if settings.dashscope_api_key:
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=settings.llm_timeout_seconds,
            )
            logger.info(
                "LLM 客户端已配置: provider=%s model=%s",
                settings.llm_provider,
                settings.llm_model,
            )
        else:
            logger.warning("DASHSCOPE_API_KEY 未配置；本地检索仍可用")

    def configure_model(self, provider: str, model: str, api_key: str) -> None:
        """Apply model configuration in memory without ever logging the secret."""
        new_settings = replace(
            self.settings,
            llm_provider=provider,
            llm_model=model,
            dashscope_api_key=api_key,
        )
        new_client = (
            OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=new_settings.llm_timeout_seconds,
            )
            if api_key
            else None
        )
        with self._configuration_lock:
            self.settings = new_settings
            self.client = new_client
        logger.info(
            "LLM 配置已更新: provider=%s model=%s configured=%s",
            provider,
            model,
            bool(api_key),
        )

    @property
    def model_configured(self) -> bool:
        return self.client is not None and bool(self.settings.dashscope_api_key)

    def warm_up(self) -> None:
        if self.vector_store.get_collection_stats()["total_chunks"] > 0:
            self.vector_store.search("测试", top_k=1)

    def build_context(self, results: list[dict[str, Any]]) -> str:
        context: list[str] = []
        total = 0
        for index, result in enumerate(results):
            block = (
                f"【资料{index + 1}】\n"
                f"来源：{result.get('file', '')} 第{result.get('page', 0)}页\n"
                f"内容：{result.get('content', '')}\n"
            )
            if total + len(block) > 2000:
                break
            context.append(block)
            total += len(block)
        return "\n".join(context)

    def _source_items(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "file": result.get("file", ""),
                "page": int(result.get("page", 0)),
                "distance": float(result.get("distance", 1.0)),
                "content_preview": result.get("content", "")[:100],
            }
            for result in results
        ]

    def retrieve(self, question: str, top_k: int | None = None) -> dict[str, Any]:
        results = self.vector_store.search(
            question,
            top_k=top_k or self.settings.top_k,
        )
        top_distance = float(results[0]["distance"]) if results else None
        accepted = bool(
            results
            and top_distance is not None
            and top_distance <= self.settings.rag_distance_threshold
        )
        return {
            "accepted": accepted,
            "threshold": self.settings.rag_distance_threshold,
            "top_distance": top_distance,
            "sources": self._source_items(results),
            "results": results,
        }

    def call_llm(self, question: str, context: str) -> str:
        if not self.model_configured:
            return MODEL_NOT_CONFIGURED_MESSAGE

        prompt = f"""
你是智慧党建AI助手。
必须严格基于资料回答，不允许编造。

资料：
{context[:3000]}

问题：
{question}

请用中文简洁回答：
"""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": "你是党建知识助手"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            answer = response.choices[0].message.content
            if not answer or not answer.strip():
                return "大模型未返回有效内容，请稍后重试。"
            return answer.strip()
        except Exception:
            logger.exception("大模型请求失败（密钥不会写入日志）")
            return "大模型请求失败，请检查网络和模型配置后重试。"

    def query(self, question: str) -> dict[str, Any]:
        start = time.perf_counter()
        retrieval = self.retrieve(question)
        results = retrieval.pop("results")

        if not results or not retrieval["accepted"]:
            return {
                "answer": "知识库中未找到相关内容",
                "sources": [],
                "model_configured": self.model_configured,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
            }

        answer = self.call_llm(question, self.build_context(results))
        return {
            "answer": answer,
            "sources": retrieval["sources"],
            "model_configured": self.model_configured,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
        }
