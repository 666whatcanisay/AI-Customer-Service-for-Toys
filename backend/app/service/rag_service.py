from __future__ import annotations

import logging
import json
import time
import urllib.request
import uuid
from dataclasses import replace
from threading import RLock
from typing import Any

from openai import OpenAI

from app.config.settings import Settings
from app.service.vector_store import VectorStore


logger = logging.getLogger(__name__)
REFUSAL_MESSAGE = "知识库中未找到足够可靠的相关内容，无法回答该问题。"
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
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        self.client: OpenAI | None = None
        self._configuration_lock = RLock()

        if settings.llm_provider == "ollama":
            self.client = None
            logger.info("本地 Ollama 已配置: model=%s", settings.llm_model)
        elif settings.dashscope_api_key:
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
            if api_key and provider != "ollama"
            else None
        )
        with self._configuration_lock:
            self.settings = new_settings
            self.client = new_client
        logger.info(
            "LLM 配置已更新: provider=%s model=%s configured=%s",
            provider,
            model,
            provider == "ollama" or bool(api_key),
        )

    @property
    def model_configured(self) -> bool:
        return self.settings.llm_provider == "ollama" or (
            self.client is not None and bool(self.settings.dashscope_api_key)
        )

    def warm_up(self) -> None:
        if self.vector_store.get_collection_stats()["total_chunks"] > 0:
            self.vector_store.search("测试", top_k=1)

    def build_context(self, results: list[dict[str, Any]]) -> str:
        context: list[str] = []
        total = 0
        for index, result in enumerate(results):
            block = (
                f"【资料{index + 1}】\n"
                f"来源：{result.get('source_name', '')} 第{result.get('page', 0)}页\n"
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
                "source_name": result.get("source_name", ""),
                "page": int(result.get("page", 0)),
                "chunk_id": result.get("chunk_id", ""),
                "distance": float(result.get("distance", 1.0)),
                "excerpt": result.get("content", "")[:200],
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
你是玩具客服知识助手。
必须严格基于资料回答，不允许编造；资料不足时明确拒答。

资料：
{context[:3000]}

问题：
{question}

请用中文简洁回答：
"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是玩具客服知识助手。只能依据提供的资料回答，禁止补充资料外事实。",
                },
                {"role": "user", "content": prompt},
            ]
            if self.settings.llm_provider == "ollama":
                return self._call_ollama(messages)
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                top_p=self.settings.llm_top_p,
            )
            answer = response.choices[0].message.content
            if not answer or not answer.strip():
                return "大模型未返回有效内容，请稍后重试。"
            return answer.strip()
        except Exception:
            logger.exception("大模型请求失败（密钥不会写入日志）")
            return "大模型请求失败，请检查网络和模型配置后重试。"

    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps(
            {
                "model": self.settings.llm_model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": self.settings.llm_temperature,
                    "top_p": self.settings.llm_top_p,
                    "num_predict": self.settings.llm_max_tokens,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.llm_base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(
            request, timeout=self.settings.llm_timeout_seconds
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = str((result.get("message") or {}).get("content") or "").strip()
        return answer or "大模型未返回有效内容，请稍后重试。"

    def query(self, question: str) -> dict[str, Any]:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        retrieval = self.retrieve(question)
        results = retrieval.pop("results")

        if not results or not retrieval["accepted"]:
            return {
                "answer": REFUSAL_MESSAGE,
                "action": "REFUSE",
                "sources": [],
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "request_id": request_id,
            }

        answer = self.call_llm(question, self.build_context(results))
        return {
            "answer": answer,
            "action": "ANSWER",
            "sources": retrieval["sources"],
            "model": self.settings.llm_model,
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "request_id": request_id,
        }
