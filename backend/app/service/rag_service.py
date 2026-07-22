from __future__ import annotations

import logging
import json
import re
import time
import urllib.request
import uuid
from dataclasses import replace
from threading import RLock
from typing import Any

from openai import OpenAI

from app.config.settings import Settings
from app.models.chat import FrozenChatContext
from app.service.test_knowledge import (
    PlatformTestKnowledgeClient,
    TestKnowledgeIndex,
)
from app.service.vector_store import VectorStore


logger = logging.getLogger(__name__)
REFUSAL_MESSAGE = "知识库中未找到足够可靠的相关内容，无法回答该问题。"
MODEL_NOT_CONFIGURED_MESSAGE = (
    "大模型尚未配置，当前已完成知识库检索，但暂时无法生成完整回答。"
)
SAFETY_ACTION_MESSAGES = {
    "ASK_CLARIFY": "请补充具体商品规格或 SKU，信息完整后才能继续确认。",
    "REQUIRE_LOOKUP": "该问题需要查询订单或实时系统后才能确认，当前不会直接承诺。",
    "TRANSFER_HUMAN": "该问题需要人工客服处理，已停止自动回答。",
    "REFUSE": "根据测试知识安全规则，无法提供该请求的答案。",
}
ACTION_PRIORITY = {
    "DIRECT_ANSWER": 0,
    "CONTROLLED_ANSWER": 1,
    "ASK_CLARIFY": 2,
    "REQUIRE_LOOKUP": 3,
    "TRANSFER_HUMAN": 4,
    "REFUSE": 5,
}
SAFETY_ACTION_DISTANCE_MARGIN = 0.06


class RAGService:
    def __init__(
        self,
        settings: Settings,
        vector_store: VectorStore | None = None,
        test_vector_store: VectorStore | None = None,
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
        self.test_vector_store = test_vector_store or VectorStore(
            persist_dir=settings.vector_db_path,
            collection_name=settings.test_knowledge_collection_name,
            model_name=settings.embedding_model,
            offline=settings.embedding_offline,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            embedding_function=self.vector_store.embedding_fn,
        )
        self.test_knowledge_index = TestKnowledgeIndex(self.test_vector_store)
        self.platform_client = PlatformTestKnowledgeClient(
            settings.platform_api_base_url,
            settings.platform_api_timeout_seconds,
        )
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

    def close(self) -> None:
        self.test_vector_store.close()
        self.vector_store.close()

    def sync_test_knowledge(self, package_id: str) -> dict[str, Any]:
        package = self.platform_client.fetch_package(package_id)
        return self.test_knowledge_index.sync(package)

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
                "knowledge_version": result.get("knowledge_version"),
                "source_ids": result.get("source_ids") or [],
                "product_id": result.get("product_id"),
                "sku_id": result.get("sku_id"),
            }
            for result in results
        ]

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        context: FrozenChatContext | None = None,
    ) -> dict[str, Any]:
        limit = top_k or self.settings.top_k
        if context is None:
            results = self.vector_store.search(question, top_k=limit)
        else:
            results = self.test_knowledge_index.search(question, context, limit)
        accepted_results = [
            result
            for result in results
            if float(result["distance"]) <= self.settings.rag_distance_threshold
        ]
        if accepted_results:
            selected = accepted_results[0]
            if context is not None:
                minimum_distance = min(
                    float(result["distance"]) for result in accepted_results
                )
                safety_candidates = [
                    accepted_results[0],
                    *[
                        result
                        for result in accepted_results
                        if result.get("knowledge_type") == "SAFETY_RULE"
                        and result.get("answer_action")
                        in {"CONTROLLED_ANSWER", "TRANSFER_HUMAN", "REFUSE"}
                        and float(result["distance"])
                        <= minimum_distance + SAFETY_ACTION_DISTANCE_MARGIN
                    ],
                ]
                selected = max(
                    safety_candidates,
                    key=lambda result: ACTION_PRIORITY.get(
                        result.get("answer_action", "REFUSE"), 5
                    ),
                )
            results = [selected] + [
                result for result in accepted_results if result is not selected
            ]
        top_distance = float(results[0]["distance"]) if results else None
        accepted = bool(accepted_results)
        return {
            "accepted": accepted,
            "threshold": self.settings.rag_distance_threshold,
            "top_distance": top_distance,
            "sources": self._source_items(results),
            "results": results,
        }

    def call_llm(
        self,
        question: str,
        context: str,
        answer_action: str = "DIRECT_ANSWER",
        risk_level: str = "LOW",
    ) -> str:
        if not self.model_configured:
            return MODEL_NOT_CONFIGURED_MESSAGE

        prompt = f"""
你是玩具客服知识助手。
必须严格基于资料回答，不允许编造；资料不足时明确拒答。

资料：
{context[:3000]}

授权动作：{answer_action}
风险等级：{risk_level}

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

    def query(
        self, question: str, context: FrozenChatContext | None = None
    ) -> dict[str, Any]:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        retrieval = self.retrieve(question, context=context)
        results = retrieval.pop("results")

        if not results or not retrieval["accepted"]:
            return {
                "answer": REFUSAL_MESSAGE,
                "action": "REFUSE",
                "sources": [],
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "request_id": request_id,
                "risk_level": "HIGH" if context else None,
                "warnings": ["NO_SCOPED_KNOWLEDGE"] if context else [],
                "required_fields": [],
                "context": context.model_dump() if context else None,
            }

        top_result = results[0]
        answer_action = (
            top_result.get("answer_action", "REFUSE") if context else "ANSWER"
        )
        risk_level = top_result.get("risk_level", "LOW") if context else None
        if context and answer_action in SAFETY_ACTION_MESSAGES:
            answer = SAFETY_ACTION_MESSAGES[answer_action]
        else:
            answer = self.call_llm(
                question,
                self.build_context(results),
                answer_action=answer_action,
                risk_level=risk_level or "LOW",
            )
            if context and "SKU" in question.upper():
                source_skus = {
                    match
                    for result in results
                    for match in re.findall(
                        r"(?<![A-Z0-9-])SKU-[A-Z0-9-]+(?![A-Z0-9-])",
                        result.get("content", "").upper(),
                    )
                }
                missing_skus = sorted(
                    sku for sku in source_skus if sku not in answer.upper()
                )
                if missing_skus:
                    answer = f"{answer}\n来源标识：{', '.join(missing_skus)}"
        return {
            "answer": answer,
            "action": answer_action,
            "sources": retrieval["sources"],
            "model": self.settings.llm_model,
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "request_id": request_id,
            "risk_level": risk_level,
            "warnings": (
                ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"] if context else []
            ),
            "required_fields": (
                ["sku_id"]
                if answer_action == "ASK_CLARIFY"
                else ["order_id"]
                if answer_action == "REQUIRE_LOOKUP"
                else []
            ),
            "context": context.model_dump() if context else None,
        }
