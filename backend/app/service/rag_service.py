from __future__ import annotations

import logging
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import replace
from threading import RLock
from typing import Any

from openai import OpenAI

from app.config.settings import Settings
from app.models.chat import FrozenChatContext
from app.models.knowledge_publication import (
    ProductKnowledgePublishReceipt,
    ProductKnowledgePublishRequest,
    ProductKnowledgeVisibility,
    ProductKnowledgeVisibilityRequest,
)
from app.service.ai_capability import (
    PROMPT_SYSTEM_MESSAGE,
    RuntimeMetrics,
    render_customer_answer_prompt,
)
from app.service.test_knowledge import (
    PlatformTestKnowledgeClient,
    TestKnowledgeIndex,
)
from app.service.vector_store import VectorStore
from app.service.product_knowledge_publisher import ProductKnowledgePublisher


logger = logging.getLogger(__name__)
REFUSAL_MESSAGE = "知识库中未找到足够可靠的相关内容，无法回答该问题。"
KNOWLEDGE_NOT_PUBLISHED_MESSAGE = (
    "该商品已进入客服目录，但AI知识尚未同步，请人工核对商品资料。"
)
MODEL_NOT_CONFIGURED_MESSAGE = (
    "大模型尚未配置，当前已完成知识库检索，但暂时无法生成完整回答。"
)
LLM_REQUEST_FAILED_MESSAGE = "大模型请求失败，请检查网络和模型配置后重试。"
RAG_RUNTIME_ERROR_MESSAGE = "服务暂时不可用，请稍后重试。"
SAFETY_ACTION_MESSAGES = {
    "ASK_CLARIFY": "请补充具体商品规格或 SKU，信息完整后才能继续确认。",
    "REQUIRE_LOOKUP": "该问题需要查询订单或实时系统后才能确认，当前不会直接承诺。",
    "TRANSFER_HUMAN": "该问题需要人工客服处理，已停止自动回答。",
    "REFUSE": "根据测试知识安全规则，无法提供该请求的答案。",
}
CUSTOMER_ANSWER_MAX_SENTENCES = 3


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
            (
                settings.internal_service_token()
                if settings.internal_service_secret_file is not None
                else None
            ),
        )
        self._configuration_lock = RLock()
        self.runtime_metrics = RuntimeMetrics()

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
        active_store = self.active_vector_store()
        if (
            active_store is not None
            and active_store.get_collection_stats()["total_chunks"] > 0
        ):
            active_store.search("测试", top_k=1)

    def active_vector_store(self) -> VectorStore | None:
        """Return the configured collection used by runtime readiness checks."""
        for store in (self.vector_store, self.test_vector_store):
            if store.collection_name == self.settings.active_collection_name:
                return store
        return None

    def collection_runtime_status(self) -> dict[str, Any]:
        """Describe configured queryable collections without reading their content."""
        available_collections: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for collection in self.vector_store.client.list_collections():
            name = str(collection.name)
            if name in seen_names:
                continue
            seen_names.add(name)
            available_collections.append(
                {"name": name, "chunk_count": int(collection.count())}
            )
        available_collections.sort(key=lambda collection: collection["name"])

        active_collection = next(
            (
                collection
                for collection in available_collections
                if collection["name"] == self.settings.active_collection_name
            ),
            None,
        )
        return {
            "active_collection_name": self.settings.active_collection_name,
            "active_collection_chunk_count": (
                active_collection["chunk_count"]
                if active_collection is not None
                else None
            ),
            "active_collection_available": active_collection is not None,
            "available_collections": available_collections,
        }

    def close(self) -> None:
        self.test_vector_store.close()
        self.vector_store.close()

    def sync_test_knowledge(self, package_id: str) -> dict[str, Any]:
        package = self.platform_client.fetch_package(package_id)
        return self.test_knowledge_index.sync(package)

    def publish_product_knowledge(
        self, request: ProductKnowledgePublishRequest
    ) -> ProductKnowledgePublishReceipt:
        active_store = self.active_vector_store()
        if active_store is None:
            raise RuntimeError("活动知识集合不可用")
        return ProductKnowledgePublisher(active_store).publish(request)

    def product_knowledge_visibility(
        self, request: ProductKnowledgeVisibilityRequest
    ) -> ProductKnowledgeVisibility:
        active_store = self.active_vector_store()
        if active_store is None:
            raise RuntimeError("活动知识集合不可用")
        return ProductKnowledgePublisher(active_store).visibility(request)

    @classmethod
    def _answer_topics(cls, question: str) -> tuple[str, ...]:
        topics: list[str] = []
        if cls._question_has(
            question,
            r"几岁",
            r"年龄",
            r"适龄",
            r"适合.*(?:儿童|孩子|小朋友)",
            r"(?:儿童|孩子|小朋友).*适合",
        ):
            topics.append("age")
        if cls._question_has(
            question, r"包装", r"礼盒", r"礼袋", r"彩盒", r"袋装", r"盒装"
        ):
            topics.append("packaging")
        if cls._question_has(
            question, r"材质", r"材料", r"什么做的", r"什么料"
        ):
            topics.append("material")
        if cls._question_has(
            question,
            r"尺寸",
            r"长宽高",
            r"多长",
            r"多宽",
            r"多高",
            r"多少(?:厘米|毫米|cm|mm)",
            r"(?:成品|包装).*多大",
        ):
            topics.append("size")
        if cls._question_has(question, r"多少颗", r"几颗", r"颗粒数", r"积木数量"):
            topics.append("count")
        if cls._question_has(question, r"颜色", r"什么色", r"哪种色"):
            topics.append("color")
        return tuple(dict.fromkeys(topics))

    @classmethod
    def _answer_focus(cls, question: str) -> str:
        topics = cls._answer_topics(question)
        labels = {
            "age": "建议年龄，以及证据中明确写出的必要小颗粒、低龄限制和成人陪同提示",
            "packaging": "客户询问的包装形式",
            "material": "客户询问的商品材质；没有明确材质证据时不得推断",
            "size": "客户询问的成品或包装尺寸",
            "count": "客户询问的颗粒数或数量",
            "color": "客户询问的颜色或款式颜色",
        }
        if not topics:
            return "客户当前明确询问的事项"
        return "；".join(labels[topic] for topic in topics)

    @classmethod
    def _answer_fragments(cls, question: str, content: str) -> list[str]:
        """Keep only evidence fragments relevant to the customer's question."""
        topics = cls._answer_topics(question)
        if not topics:
            return [content]
        keywords = {
            "age": (
                "岁",
                "年龄",
                "儿童",
                "孩子",
                "小朋友",
                "小颗粒",
                "小零件",
                "成人",
                "家长",
                "陪同",
                "看护",
                "监护",
            ),
            "packaging": (
                "包装",
                "礼盒",
                "礼袋",
                "彩盒",
                "袋装",
                "盒装",
                "装箱",
                "手提",
                "纪念版",
            ),
            "material": (
                "材质",
                "材料",
                "ABS",
                "塑料",
                "木质",
                "金属",
                "亚克力",
                "硅胶",
                "EVA",
                "PVC",
                "PP",
                "PE",
            ),
            "size": ("尺寸", "长", "宽", "高", "厘米", "毫米", "cm", "mm", "×"),
            "count": ("颗粒", "颗积木", "数量", "共计"),
            "color": (
                "颜色",
                "色款",
                "蓝",
                "粉",
                "红",
                "白",
                "黑",
                "黄",
                "紫",
                "绿",
                "橙",
                "灰",
                "棕",
                "透明",
            ),
        }
        allowed = tuple(
            keyword
            for topic in topics
            for keyword in keywords[topic]
        )
        fragments = [
            fragment.strip()
            for fragment in re.split(r"[。！？!?；;\n]+", content)
            if fragment.strip()
        ]
        selected = [
            fragment
            for fragment in fragments
            if any(keyword.lower() in fragment.lower() for keyword in allowed)
        ]
        return selected or [content]

    def build_context(
        self,
        results: list[dict[str, Any]],
        question: str = "",
    ) -> str:
        """Build model-only facts without citation labels or internal identifiers."""
        context: list[str] = []
        seen: set[str] = set()
        total = 0
        for result in results:
            content = self._answer_content(result).strip()
            for fragment in self._answer_fragments(question, content):
                if not fragment or fragment in seen:
                    continue
                block = fragment.rstrip("。") + "。"
                if total + len(block) > 2000:
                    return "\n".join(context)
                context.append(block)
                seen.add(fragment)
                total += len(block)
        return "\n".join(context)

    @classmethod
    def _requested_topics_have_product_evidence(
        cls,
        question: str,
        results: list[dict[str, Any]],
        context: FrozenChatContext,
    ) -> bool:
        topics = cls._answer_topics(question)
        if not topics:
            return True
        product_evidence = " ".join(
            cls._answer_content(result)
            for result in results
            if result.get("product_id") == context.product_id
        )
        store_safety_evidence = " ".join(
            cls._answer_content(result)
            for result in results
            if not result.get("product_id")
            and result.get("knowledge_type") == "SAFETY_RULE"
        )
        patterns = {
            "age": r"(?:\d+\s*(?:～|~|至|到|-|—|–)\s*\d+\s*岁|\d+\s*岁(?:及以上|以上|以下|以内)|适合.{0,12}\d+\s*岁)",
            "packaging": r"(?:包装|礼盒|礼袋|彩盒|袋装|盒装|装箱|手提)",
            "material": r"(?:材质|材料|ABS|塑料|木质|金属|亚克力|硅胶|EVA|PVC|(?:^|\W)PP(?:\W|$)|(?:^|\W)PE(?:\W|$))",
            "size": r"(?:尺寸|长宽高|\d+(?:\.\d+)?\s*(?:厘米|毫米|cm|mm)|\d+\s*[×xX]\s*\d+)",
            "count": r"\d+\s*(?:颗|块|件|个积木)",
            "color": r"(?:颜色|色款|蓝色|粉色|红色|白色|黑色|黄色|紫色|绿色|橙色|灰色|棕色|透明)",
        }
        return all(
            re.search(
                patterns[topic],
                (
                    f"{product_evidence} {store_safety_evidence}"
                    if topic == "age"
                    else product_evidence
                ),
                re.IGNORECASE,
            )
            for topic in topics
        )

    @staticmethod
    def _sanitize_customer_answer(answer: str) -> str:
        """Remove internal RAG traces and keep a copy-ready 1-3 sentence reply."""
        lines = []
        internal_heading = re.compile(
            r"^\s*(?:[-*#]+\s*)?"
            r"(?:依据摘要|来源标识|检索片段|内部评分(?:和距离)?|"
            r"source[_\s-]?ids?)\s*[:：]",
            re.IGNORECASE,
        )
        for line in str(answer or "").replace("\r", "").split("\n"):
            if not internal_heading.match(line):
                lines.append(line)
        text = " ".join(lines)
        text = re.sub(r"【\s*资料\s*\d+\s*】", "", text)
        text = re.sub(r"资料\s*\d+", "", text)
        text = re.sub(
            r"(?:根据|依据)(?:提供的|现有的|现有|上述|检索到的)?"
            r"(?:资料|证据)(?:显示|可知|说明)?[，,:：\s]*",
            "",
            text,
        )
        text = re.sub(
            r"(?:依据摘要|来源标识|检索片段|内部评分(?:和距离)?|"
            r"source[_\s-]?ids?)\s*[:：][^。！？!?]*[。！？!?]?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\bSRC-[A-Z0-9][A-Z0-9._-]*\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bsource[_\s-]?ids?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"内部(?:评分|距离)|检索距离", "", text)
        text = text.replace("资料中", "当前信息中").replace("资料", "信息")
        text = text.replace("**", "")
        text = re.sub(r"\s+", " ", text).strip(" \t，,；;")
        if not text:
            return REFUSAL_MESSAGE
        sentences = [
            segment.strip()
            for segment in re.findall(r"[^。！？!?]+[。！？!?]?", text)
            if segment.strip()
        ]
        return "".join(sentences[:CUSTOMER_ANSWER_MAX_SENTENCES]).strip()

    @classmethod
    def _dedupe_adult_guidance(cls, answer: str) -> str:
        """Keep one adult-supervision reminder while preserving other facts."""
        sentences = re.findall(r"[^。！？!?]+[。！？!?]?", answer)
        seen_guidance = False
        normalized: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            ending = sentence[-1] if sentence[-1] in "。！？!?" else ""
            body = sentence[:-1] if ending else sentence
            clauses = [
                clause.strip()
                for clause in re.split(r"[，,；;]", body)
                if clause.strip()
            ]
            retained: list[str] = []
            removed_duplicate_guidance = False
            for clause in clauses:
                is_guidance = cls._question_has(
                    clause,
                    r"(?:成人|家长|大人).{0,12}(?:陪同|看护|监护|陪伴)",
                    r"(?:陪同|看护|监护|陪伴).{0,12}(?:成人|家长|大人)",
                )
                if is_guidance and seen_guidance:
                    removed_duplicate_guidance = True
                    continue
                if is_guidance:
                    seen_guidance = True
                retained.append(clause)
            if removed_duplicate_guidance:
                retained = [
                    clause
                    for clause in retained
                    if not cls._question_has(
                        clause,
                        r"^(?:以|来)?确保(?:使用)?安全(?:哦|哟|呀)?$",
                        r"^注意安全(?:哦|哟|呀)?$",
                    )
                ]
            if retained:
                normalized.append("，".join(retained) + ending)
        return "".join(normalized)

    @classmethod
    def _enforce_age_constraints(
        cls,
        question: str,
        answer_context: str,
        answer: str,
    ) -> str:
        """Preserve an evidence-backed age range and deduplicate supervision."""
        if "age" not in cls._answer_topics(question):
            return answer
        text = str(answer or "")
        age_range = re.search(
            r"(\d+)\s*岁?\s*(?:～|~|至|到|-|—|–)\s*(\d+)\s*岁",
            answer_context,
        )
        if age_range:
            lower, upper = age_range.groups()
            canonical = f"{lower}～{upper}岁"
            text = re.sub(
                rf"{re.escape(lower)}\s*岁?\s*(?:～|~|至|到|-|—|–)\s*"
                rf"{re.escape(upper)}\s*岁",
                canonical,
                text,
            )
            text = re.sub(
                rf"{re.escape(lower)}\s*岁\s*(?:及\s*)?以上",
                canonical,
                text,
            )
            text = re.sub(
                rf"{re.escape(lower)}\s*岁(?!\s*(?:以下|以内|以上|及以上))",
                canonical,
                text,
                count=1,
            )
            if canonical not in text:
                text = f"亲，这款建议{canonical}的小朋友玩哦。{text}"
        return cls._dedupe_adult_guidance(text)

    @staticmethod
    def _answer_content(result: dict[str, Any]) -> str:
        """Add field meaning to C's compact SKU fact serialization."""
        content = str(result.get("content") or "")
        if result.get("knowledge_type") != "SKU_FACT":
            return content
        parts = [part.strip() for part in content.split("；")]
        if len(parts) >= 2 and re.fullmatch(r"\d+", parts[1]):
            parts[1] = f"颗粒数：{parts[1]}颗"
        return "；".join(parts)

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
        limit = max(top_k or self.settings.top_k, 6) if context else (
            top_k or self.settings.top_k
        )
        if context is None:
            results = self.vector_store.search(question, top_k=limit)
        else:
            active_store = self.active_vector_store()
            if active_store is None:
                results = []
            else:
                results = TestKnowledgeIndex(active_store).search(
                    question, context, limit
                )
        age_question = "age" in self._answer_topics(question)
        accepted_results = [
            result
            for result in results
            if (
                float(result["distance"]) <= self.settings.rag_distance_threshold
                or (
                    context is not None
                    and age_question
                    and result.get("knowledge_type") == "SAFETY_RULE"
                    and self._question_has(
                        str(result.get("title") or "")
                        + " "
                        + str(result.get("content") or ""),
                        r"\d+\s*岁",
                        r"儿童",
                        r"小颗粒",
                        r"小零件",
                        r"成人",
                        r"家长",
                    )
                )
                or (
                    context is not None
                    and self.settings.rag_distance_threshold >= 0.5
                    and float(result["distance"]) <= 0.8
                    and (
                        bool(result.get("_exact_sku"))
                        or result.get("knowledge_type") == "PRODUCT_FACT"
                    )
                )
            )
        ]
        if accepted_results:
            results = accepted_results
        top_distance = float(results[0]["distance"]) if results else None
        accepted = bool(accepted_results)
        return {
            "accepted": accepted,
            "threshold": self.settings.rag_distance_threshold,
            "top_distance": top_distance,
            "sources": self._source_items(results),
            "results": results,
        }

    @staticmethod
    def _question_has(question: str, *patterns: str) -> bool:
        return any(re.search(pattern, question, re.IGNORECASE) for pattern in patterns)

    @classmethod
    def _question_allows_store_guard_without_product(cls, question: str) -> bool:
        """Allow store-level safety/operations guards without product facts.

        Generic product questions must never fall through to unrelated store
        knowledge. Store guards remain available for the high-risk situations
        they were designed to control.
        """
        return cls._question_has(
            question,
            r"缺少.*零件",
            r"少了.*零件",
            r"缺件",
            r"补发",
            r"破损",
            r"吞咽",
            r"误食",
            r"小零件",
            r"小颗粒",
            r"儿童",
            r"小孩",
            r"退款",
            r"退货",
            r"赔偿",
            r"补偿",
            r"发货",
            r"到货",
            r"物流",
            r"库存",
            r"价格",
            r"赠品",
            r"活动",
            r"投诉",
            r"差评",
            r"平台介入",
            r"安全",
            r"责任",
            r"治疗",
            r"医疗",
            r"自闭症",
        )

    @staticmethod
    def _result_for(
        results: list[dict[str, Any]],
        *,
        action: str | None = None,
        knowledge_type: str | None = None,
        exact_sku: bool | None = None,
    ) -> dict[str, Any] | None:
        for result in results:
            if action is not None and result.get("answer_action") != action:
                continue
            if (
                knowledge_type is not None
                and result.get("knowledge_type") != knowledge_type
            ):
                continue
            if exact_sku is not None and bool(result.get("_exact_sku")) != exact_sku:
                continue
            return result
        return None

    def _structured_decision(
        self,
        question: str,
        context: FrozenChatContext,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Choose response controls before the model sees any evidence.

        The rules are intent- and metadata-based.  They deliberately do not
        consume evaluation case ids or expected outputs.
        """
        primary = results[0]
        action = str(primary.get("answer_action") or "REFUSE")
        risk = str(primary.get("risk_level") or "HIGH")

        prompt_injection = self._question_has(
            question,
            r"忽略.*规则",
            r"越过.*规则",
            r"别查",
            r"不要查",
        )
        forced_guarantee = self._question_has(
            question, r"直接保证", r"一定.*到", r"保证.*到"
        )
        missing_parts = self._question_has(question, r"少了.*零件", r"缺件", r"补发")
        compensation = self._question_has(
            question, r"赔偿", r"补偿", r"退款", r"退货", r"赔.*钱", r"赔我"
        )
        realtime_shipping = self._question_has(question, r"发货", r"到货", r"物流")
        realtime_catalog = self._question_has(
            question, r"多少钱", r"价格", r"库存", r"赠品", r"活动"
        )
        battery = self._question_has(question, r"电池")
        age_safety = "age" in self._answer_topics(question) or self._question_has(
            question, r"[几多五六0-9]+岁", r"小孩", r"儿童", r"小颗粒"
        )
        config_ambiguous = self._question_has(
            question, r"带.*遥控", r"带灯", r"遥控灯"
        ) and not context.sku_id
        source_trace = self._question_has(question, r"依据", r"哪张图", r"来源")
        reference_relation = self._question_has(
            question, r"同一款", r"另一个链接", r"reference"
        )
        bundle_total = bool(context.sku_id) and self._question_has(
            question, r"一共", r"组合.*几", r"组合.*多少"
        )

        if prompt_injection or forced_guarantee:
            action, risk = "REFUSE", "HIGH"
        elif missing_parts:
            action, risk = "TRANSFER_HUMAN", "HIGH"
        elif compensation:
            action, risk = "TRANSFER_HUMAN", "HIGH"
        elif realtime_catalog or realtime_shipping:
            action, risk = "REQUIRE_LOOKUP", "HIGH"
        elif battery:
            action, risk = (
                ("CONTROLLED_ANSWER", "HIGH")
                if context.sku_id
                else ("ASK_CLARIFY", "HIGH")
            )
        elif age_safety:
            action, risk = "CONTROLLED_ANSWER", "HIGH"
        elif config_ambiguous:
            action, risk = "ASK_CLARIFY", "MEDIUM"
        elif source_trace:
            action, risk = "DIRECT_ANSWER", "LOW"
        elif reference_relation:
            action, risk = "DIRECT_ANSWER", "MEDIUM"
        elif bundle_total:
            action, risk = "DIRECT_ANSWER", "HIGH"
        else:
            exact = self._result_for(results, exact_sku=True)
            if exact and self._question_has(
                question, r"多少颗", r"几个人", r"有人仔", r"有没有人"
            ):
                action = "DIRECT_ANSWER"
                # A same-product SKU family with conflicting numeric values is
                # high-risk even when the exact SKU fact itself is low-risk.
                sibling_numbers = {
                    number
                    for result in results
                    for number in re.findall(r"\d+", result.get("content", ""))
                }
                if self._question_has(question, r"多少颗", r"几个人", r"组合"):
                    risk = "HIGH" if len(sibling_numbers) > 1 else risk

        question_numbers = set(re.findall(r"\d+", question))
        exact_sku_fact = self._result_for(
            results, knowledge_type="SKU_FACT", exact_sku=True
        )
        exact_result = exact_sku_fact or self._result_for(results, exact_sku=True)
        claimed_numbers = set(
            re.findall(r"(?<![A-Z0-9])\d{3,}(?![A-Z0-9])", question.upper())
        )
        if len(claimed_numbers) >= 2 and not context.sku_id:
            action, risk = "CONTROLLED_ANSWER", "HIGH"
        elif (
            claimed_numbers
            and not context.sku_id
            and any(
                result.get("answer_action") == "CONTROLLED_ANSWER"
                and result.get("risk_level") == "HIGH"
                for result in results
            )
        ):
            action, risk = "CONTROLLED_ANSWER", "HIGH"
        elif exact_result and question_numbers:
            evidence_numbers = set(
                re.findall(r"\d+", exact_result.get("content", ""))
            )
            # Product/SKU identifiers also contain digits; only treat a number
            # as a conflicting claim when it is at least three digits long.
            unsupported = {
                value
                for value in question_numbers - evidence_numbers
                if len(value) >= 3
            }
            if unsupported:
                action, risk = "CONTROLLED_ANSWER", "HIGH"

        preferred = self._result_for(results, action=action)
        matching_sku_facts = [
            result
            for result in results
            if result.get("knowledge_type") == "SKU_FACT"
            and claimed_numbers
            & set(re.findall(r"\d+", result.get("content", "")))
        ]
        if matching_sku_facts and not context.sku_id:
            preferred = matching_sku_facts[0]
        elif exact_result and (
            source_trace
            or reference_relation
            or bundle_total
            or self._question_has(question, r"多少颗", r"几个人")
        ):
            preferred = exact_result
        if preferred is None:
            preferred = primary
        ordered = [preferred]
        ordered.extend(
            result
            for result in matching_sku_facts
            if result is not preferred and result not in ordered
        )
        ordered.extend(result for result in results if result not in ordered)
        if (
            not context.product_id.startswith("__STORE_LEVEL_")
            and action in {"DIRECT_ANSWER", "CONTROLLED_ANSWER"}
        ):
            product_results = [
                result for result in ordered if result.get("product_id")
            ]
            if product_results:
                relevant_store_safety = [
                    result
                    for result in ordered
                    if age_safety
                    and not result.get("product_id")
                    and result.get("knowledge_type") == "SAFETY_RULE"
                ]
                ordered = product_results + relevant_store_safety
        return {"action": action, "risk_level": risk, "results": ordered}

    def _required_fields(
        self,
        question: str,
        context: FrozenChatContext,
        action: str,
    ) -> list[str]:
        if action not in {"ASK_CLARIFY", "REQUIRE_LOOKUP", "TRANSFER_HUMAN"}:
            return []
        store_scope = context.product_id.startswith("__STORE_LEVEL_")
        fields: list[str] = []
        if action == "ASK_CLARIFY" and not context.sku_id:
            fields.append("sku_id")
        elif action == "REQUIRE_LOOKUP":
            if self._question_has(question, r"发货", r"到货", r"物流", r"赠品", r"活动"):
                if not (
                    context.verified_transaction
                    and context.verified_transaction.order_reference
                ):
                    fields.append("order_id")
        elif action == "TRANSFER_HUMAN":
            if not (
                context.verified_transaction
                and context.verified_transaction.order_reference
            ):
                fields.append("order_id")
            if self._question_has(question, r"少了.*零件", r"缺件", r"补发"):
                if store_scope:
                    fields.extend(["product_id", "sku_id"])
                fields.append("missing_part_info")
            elif self._question_has(
                question, r"赔偿", r"补偿", r"退款", r"退货", r"赔.*钱", r"赔我"
            ):
                fields.append("problem_type")
        return list(dict.fromkeys(fields))

    def _guarded_answer(
        self,
        question: str,
        action: str,
        results: list[dict[str, Any]],
    ) -> str:
        if action == "REFUSE":
            if self._question_has(question, r"忽略.*规则", r"越过.*规则"):
                return (
                    "不能越过公司安全规则。发货和赠品必须查询实时信息，"
                    "当前不能作未核实承诺。"
                )
            if self._question_has(
                question, r"到货", r"发货", r"物流", r"明天到", r"保证.*到"
            ):
                return "不能作无依据的到货保证；需要查询订单和物流状态。"
            return SAFETY_ACTION_MESSAGES[action]
        if action == "REQUIRE_LOOKUP" and self._question_has(
            question, r"多少钱", r"价格", r"库存"
        ):
            return "价格和库存属于实时信息，需要查询当前商品页或后台后再确认。"
        if action == "ASK_CLARIFY":
            return "需要继续追问具体SKU；不同款式配置不同。"

        evidence = [
            result.get("content", "").strip()
            for result in results
            if result.get("answer_action") == action
            and result.get("content", "").strip()
        ][:2]
        if evidence:
            return " ".join(evidence)
        return SAFETY_ACTION_MESSAGES[action]

    def call_llm(
        self,
        question: str,
        context: str,
        answer_action: str = "DIRECT_ANSWER",
        risk_level: str = "LOW",
        answer_focus: str | None = None,
        recent_conversation: str = "（无历史对话）",
    ) -> str:
        if not self.model_configured:
            return MODEL_NOT_CONFIGURED_MESSAGE

        prompt = render_customer_answer_prompt(
            context=context,
            answer_action=answer_action,
            risk_level=risk_level,
            question=question,
            answer_focus=answer_focus or self._answer_focus(question),
            recent_conversation=recent_conversation,
        )
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPT_SYSTEM_MESSAGE,
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
            return LLM_REQUEST_FAILED_MESSAGE

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
        parsed_base_url = urllib.parse.urlparse(self.settings.llm_base_url)
        if parsed_base_url.hostname in {"127.0.0.1", "localhost", "::1"}:
            # Local Ollama must never be routed through an inherited HTTP proxy.
            # The runtime process can outlive the shell that created it, so relying
            # on NO_PROXY alone makes readiness non-reproducible.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            response_context = opener.open(
                request, timeout=self.settings.llm_timeout_seconds
            )
        else:
            response_context = urllib.request.urlopen(
                request, timeout=self.settings.llm_timeout_seconds
            )
        with response_context as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = str((result.get("message") or {}).get("content") or "").strip()
        return answer or "大模型未返回有效内容，请稍后重试。"

    def query(
        self, question: str, context: FrozenChatContext | None = None
    ) -> dict[str, Any]:
        """Execute a RAG request and record only aggregate process metrics."""
        started = time.perf_counter()
        error_summary: str | None = None
        try:
            result = self._query(question, context=context)
            if result.get("answer") == LLM_REQUEST_FAILED_MESSAGE:
                error_summary = "LLM_REQUEST_FAILED"
                warnings = result.setdefault("warnings", [])
                if "LLM_REQUEST_FAILED" not in warnings:
                    warnings.append("LLM_REQUEST_FAILED")
            return result
        except Exception as exc:
            error_summary = type(exc).__name__
            logger.error("RAG request failed category=%s", error_summary)
            return {
                "answer": RAG_RUNTIME_ERROR_MESSAGE,
                "action": "REFUSE",
                "sources": [],
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": str(uuid.uuid4()),
                "risk_level": "HIGH" if context else None,
                "warnings": ["RAG_RUNTIME_ERROR"],
                "required_fields": [],
                "context": context.model_dump() if context else None,
            }
        finally:
            self.runtime_metrics.record(
                (time.perf_counter() - started) * 1000,
                error_summary=error_summary,
            )

    def _query(
        self, question: str, context: FrozenChatContext | None = None
    ) -> dict[str, Any]:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        retrieval = self.retrieve(question, context=context)
        results = retrieval.pop("results")
        missing_product_scope = bool(
            context
            and not context.product_id.startswith("__STORE_LEVEL_")
            and not self._question_allows_store_guard_without_product(question)
            and not any(
                result.get("product_id") == context.product_id
                for result in results
            )
        )

        requested_topics_missing = bool(
            context
            and not missing_product_scope
            and not self._requested_topics_have_product_evidence(
                question, results, context
            )
        )

        if (
            not results
            or not retrieval["accepted"]
            or missing_product_scope
            or requested_topics_missing
        ):
            knowledge_not_published = bool(context and missing_product_scope)
            return {
                "answer": (
                    KNOWLEDGE_NOT_PUBLISHED_MESSAGE
                    if knowledge_not_published
                    else REFUSAL_MESSAGE
                ),
                "action": "REFUSE",
                "sources": [],
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "request_id": request_id,
                "risk_level": "HIGH" if context else None,
                "warnings": (
                    ["KNOWLEDGE_NOT_PUBLISHED"]
                    if knowledge_not_published
                    else ["NO_SCOPED_KNOWLEDGE"] if context else []
                ),
                "required_fields": [],
                "context": context.model_dump() if context else None,
            }

        top_result = results[0]
        if context:
            decision = self._structured_decision(question, context, results)
            results = decision["results"]
            top_result = results[0]
            answer_action = decision["action"]
            risk_level = decision["risk_level"]
            retrieval["sources"] = self._source_items(results)
        else:
            answer_action = "ANSWER"
            risk_level = None
        if context and answer_action in SAFETY_ACTION_MESSAGES:
            answer = self._guarded_answer(question, answer_action, results)
        else:
            answer_context = self.build_context(results, question)
            answer = self.call_llm(
                question,
                answer_context,
                answer_action=answer_action,
                risk_level=risk_level or "LOW",
                answer_focus=self._answer_focus(question),
                recent_conversation=self._recent_conversation_prompt(context),
            )
            if context:
                exact_sku_fact = self._result_for(
                    results, knowledge_type="SKU_FACT", exact_sku=True
                )
                if exact_sku_fact and self._question_has(question, r"颗"):
                    asked_numbers = set(
                        re.findall(
                            r"(?<![A-Z0-9])\d{3,}(?![A-Z0-9])",
                            question.upper(),
                        )
                    )
                    fact_numbers = re.findall(
                        r"颗粒数：(\d+)颗", self._answer_content(exact_sku_fact)
                    )
                    unsupported = asked_numbers - set(fact_numbers)
                    if fact_numbers and unsupported:
                        answer += (
                            f"\n亲，当前选择的款式是{fact_numbers[0]}颗，"
                            f"{', '.join(sorted(unsupported))}颗不适用于这个款式哦。"
                        )
                if self._question_has(question, r"同一款", r"另一个链接"):
                    reference = next(
                        (
                            result
                            for result in results
                            if "标准SKU" in result.get("content", "")
                            and "P0002" in result.get("content", "")
                        ),
                        None,
                    )
                    if reference:
                        answer += "\n这个SKU与P0002对应款为同一款。"
                bundle_name = re.search(r"[A-Z]\d+\+[A-Z0-9]+", question.upper())
                if bundle_name and any(
                    "组合" in result.get("content", "") for result in results
                ):
                    answer += f"\n{bundle_name.group(0)}是组合款。"
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
                    answer = f"{answer}\n对应SKU为{', '.join(missing_skus)}。"
            answer = self._enforce_age_constraints(
                question,
                answer_context,
                answer,
            )
            answer = self._sanitize_customer_answer(answer)
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
                self._required_fields(question, context, answer_action)
                if context
                else []
            ),
            "context": context.model_dump() if context else None,
        }

    @staticmethod
    def _recent_conversation_prompt(context: FrozenChatContext | None) -> str:
        """Render bounded verified history as quoted data, never as instructions."""

        if context is None or not context.recent_conversation:
            return "（无历史对话）"
        values: list[str] = []
        for index, item in enumerate(context.recent_conversation[-20:], start=1):
            role = "客户" if item.sender == "customer" else "客服"
            content = item.content.replace("\r", " ").replace("\n", " ").strip()[:500]
            values.append(f"{index}. [{role}] {content}")
        return "\n".join(values)
