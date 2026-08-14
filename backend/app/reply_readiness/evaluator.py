from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.chat import FrozenChatContext, VerifiedProductContext
from app.models.knowledge_publication import ProductKnowledgeVisibilityRequest
from app.reply_readiness.contracts import (
    ExpectedAction,
    PddReplyReadinessInputV1,
    PddReplyReadinessItemResultV1,
    PddReplyReadinessPublishedDebugResultV1,
    PddReplyReadinessQuestionV1,
    PddReplyReadinessResultV1,
    ReplyReadinessDependencyUsageV1,
    ReplyReadinessDiagnosticChangeV1,
    ReplyReadinessExecutionMode,
    ReplyReadinessKnowledgeSnapshotV1,
    RiskLevel,
    canonical_sha256,
)
from app.reply_router.contracts import text_sha256
from app.reply_router.publication_store import (
    ReplyRuleSnapshotStore,
    ReplyRuleSnapshotUnavailable,
)
from app.reply_router.router import ReplyRouter
from app.service.ai_capability import PROMPT_HASH, PROMPT_VERSION
from app.service.rag_service import RAGService


_RISK = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
_ROUTER_CONTRACT_FINGERPRINT = canonical_sha256(
    {"component": "ReplyRouter", "contract": "reply-router.v1"}
)


def _router_build_fingerprint() -> str:
    app_root = Path(__file__).resolve().parents[1]
    components: dict[str, str] = {}
    for relative_path in (
        "reply_router/router.py",
        "reply_router/contracts.py",
        "reply_router/publication_store.py",
    ):
        path = app_root / relative_path
        try:
            components[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            components[relative_path] = "SOURCE_UNAVAILABLE"
    return canonical_sha256({
        "component": "ReplyRouter",
        "contract": "reply-router.v1",
        "source_components": components,
    })


_ROUTER_BUILD_FINGERPRINT = _router_build_fingerprint()
_FIELD_LABELS = {
    "particle_count": ("颗粒数量",),
    "finished_size": ("成品尺寸",),
    "material": ("材质信息",),
    "weight": ("商品重量",),
    "installation": ("安装方式", "使用说明"),
    "package_contents": ("包装内容",),
    "variant_difference": ("版本差异", "规格区别", "颜色款式", "数量区别", "尺寸区别", "包装区别", "玩法区别"),
    "image_status": ("图片资料状态",),
    "video_status": ("视频资料状态",),
    "image_match_policy": ("图片一致性说明",),
    "courier_policy": ("快递选择策略",),
    "ship_origin": ("发货地",),
    "stealth_packaging": ("隐私包装",),
    "authenticity_evidence": ("品牌授权证据",),
}
_ESTIMATE_MARKERS = ("估测", "估计", "大约", "约", "左右", "可能")
_ACTION_ORDER = {
    ExpectedAction.DIRECT_ANSWER: 1,
    ExpectedAction.CONTROLLED_ANSWER: 2,
    ExpectedAction.ASK_CLARIFY: 3,
    ExpectedAction.REQUIRE_LOOKUP: 4,
    ExpectedAction.TRANSFER_HUMAN: 5,
    ExpectedAction.REFUSE: 6,
}


@dataclass(frozen=True)
class _KnowledgeRecord:
    source: ReplyReadinessKnowledgeSnapshotV1
    values: dict[str, str]


@dataclass(frozen=True)
class _PublishedRuntimeSnapshot:
    rag_collection_identity: str | None
    knowledge_publication_status: str
    knowledge_publication_fingerprint: str | None
    model_config_identity: str


class PublishedReplyReadinessRuntime:
    """Narrow read-only adapter over the already-running production RAG service."""

    def __init__(self, rag: RAGService) -> None:
        self._rag = rag

    def query(self, question: str, context: FrozenChatContext) -> dict[str, Any]:
        return self._rag.query(question, context=context)

    def snapshot(
        self,
        scope: FrozenChatContext,
        current_fingerprint: str | None,
    ) -> _PublishedRuntimeSnapshot:
        collection_identity: str | None = None
        status = "UNAVAILABLE"
        indexed_fingerprint: str | None = None
        try:
            collection = self._rag.collection_runtime_status()
            active_name = collection.get("active_collection_name")
            if isinstance(active_name, str) and active_name.strip():
                collection_identity = active_name.strip()
            visibility = self._rag.product_knowledge_visibility(
                ProductKnowledgeVisibilityRequest(
                    tenant_id=scope.tenant_id,
                    platform=scope.platform,
                    store_code=scope.store_code,
                    product_id=scope.product_id,
                    current_fingerprint=current_fingerprint,
                )
            )
            status = visibility.status.value
            indexed_fingerprint = visibility.indexed_fingerprint
            collection_identity = visibility.active_collection or collection_identity
        except Exception:
            # Fixed-rule debug remains available when the unused RAG visibility
            # capability is unavailable. RAG routes inspect this state and fail closed.
            pass
        settings = self._rag.settings
        model_identity = canonical_sha256(
            {
                "llm_provider": settings.llm_provider,
                "llm_model": settings.llm_model,
                "embedding_model": settings.embedding_model,
                "prompt_version": PROMPT_VERSION,
                "prompt_hash": PROMPT_HASH,
                "llm_temperature": settings.llm_temperature,
                "llm_max_tokens": settings.llm_max_tokens,
                "llm_top_p": settings.llm_top_p,
                "rag_distance_threshold": settings.rag_distance_threshold,
                "top_k": settings.top_k,
            }
        )
        return _PublishedRuntimeSnapshot(
            rag_collection_identity=collection_identity,
            knowledge_publication_status=status,
            knowledge_publication_fingerprint=indexed_fingerprint,
            model_config_identity=model_identity,
        )


class _PublishedRagProvider:
    def __init__(
        self,
        runtime: PublishedReplyReadinessRuntime,
        payload: PddReplyReadinessInputV1,
        initial_runtime: _PublishedRuntimeSnapshot,
    ) -> None:
        self.runtime = runtime
        self.payload = payload
        self.initial_runtime = initial_runtime
        self.invoked = False
        self.query_called = False
        self.blocker_code: str | None = None

    def __call__(
        self, question: str, context: FrozenChatContext
    ) -> dict[str, Any]:
        self.invoked = True
        expected = self.payload.publication_state
        assert expected is not None
        if expected.status != "PUBLISHED":
            self.blocker_code = "KNOWLEDGE_NOT_PUBLISHED"
            return self._manual_result()
        if (
            not expected.current_fingerprint
            or not expected.indexed_fingerprint
            or expected.current_fingerprint != expected.indexed_fingerprint
        ):
            self.blocker_code = "KNOWLEDGE_FINGERPRINT_DRIFT"
            return self._manual_result()
        if (
            self.initial_runtime.knowledge_publication_status != "PUBLISHED"
            or self.initial_runtime.knowledge_publication_fingerprint
            != expected.indexed_fingerprint
        ):
            self.blocker_code = "KNOWLEDGE_FINGERPRINT_DRIFT"
            return self._manual_result()
        if (
            expected.active_collection
            and self.initial_runtime.rag_collection_identity
            != expected.active_collection
        ):
            self.blocker_code = "RAG_COLLECTION_IDENTITY_DRIFT"
            return self._manual_result()
        self.query_called = True
        return self.runtime.query(question, context)

    @staticmethod
    def _manual_result() -> dict[str, Any]:
        return {
            "answer": "当前已发布知识不可用于本次回答，需要人工客服核实。",
            "action": "TRANSFER_HUMAN",
            "risk_level": "HIGH",
            "sources": [],
            "warnings": ["AUTO_SEND_DISABLED"],
            "required_fields": [],
        }


def _extract_records(analysis_text: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(analysis_text)
    except (TypeError, ValueError):
        return []
    records = payload.get("数据记录") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return []
    return [
        {str(key): str(value).strip() for key, value in item.items() if value is not None and str(value).strip()}
        for item in records
        if isinstance(item, dict)
    ]


def _source_id(source: ReplyReadinessKnowledgeSnapshotV1) -> str:
    return f"material:{source.material_id}:v{source.revision}"


def _unique_sources(
    sources: list[ReplyReadinessKnowledgeSnapshotV1],
) -> list[ReplyReadinessKnowledgeSnapshotV1]:
    seen: set[tuple[str, int]] = set()
    result: list[ReplyReadinessKnowledgeSnapshotV1] = []
    for source in sources:
        identity = (source.material_id, source.revision)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(source)
    return result


def _normalize_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_\s]+", "", normalized, flags=re.UNICODE)


def _knowledge_records(sources: list[ReplyReadinessKnowledgeSnapshotV1]) -> list[_KnowledgeRecord]:
    return [
        _KnowledgeRecord(source=source, values=record)
        for source in sources
        for record in _extract_records(source.analysis_text)
    ]


def _facts(
    records: list[_KnowledgeRecord],
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, list[ReplyReadinessKnowledgeSnapshotV1]],
]:
    facts: dict[str, str] = {}
    blockers: dict[str, str] = {}
    fact_sources: dict[str, list[ReplyReadinessKnowledgeSnapshotV1]] = {}
    for key, labels in _FIELD_LABELS.items():
        pairs = [
            (record.values[label], record.source)
            for record in records
            if record.source.template_type == "PRODUCT_KNOWLEDGE"
            or (record.source.template_type == "SKU_DIFFERENCE" and key == "variant_difference")
            for label in labels
            if record.values.get(label)
        ]
        unique = list(dict.fromkeys(value for value, _ in pairs))
        if not unique:
            continue
        joined = "；".join(unique)
        has_size_conflict = key == "finished_size" and bool(
            re.search(r"30\s*(?:cm|厘米)", joined, flags=re.I)
            and re.search(r"40\s*(?:cm|厘米)", joined, flags=re.I)
        )
        if key != "variant_difference" and (len(unique) > 1 or has_size_conflict):
            blockers[key] = "FACT_CONFLICT"
            continue
        if any(marker in joined for marker in _ESTIMATE_MARKERS):
            blockers[key] = "FACT_ESTIMATED"
            continue
        facts[key] = joined if key == "variant_difference" else unique[0]
        fact_sources[key] = _unique_sources([source for _, source in pairs])
    return facts, blockers, fact_sources


def _risk_from_label(value: str | None) -> RiskLevel:
    normalized = (value or "").strip().upper()
    return {
        "低": RiskLevel.LOW,
        "LOW": RiskLevel.LOW,
        "中": RiskLevel.MEDIUM,
        "MEDIUM": RiskLevel.MEDIUM,
        "高": RiskLevel.HIGH,
        "HIGH": RiskLevel.HIGH,
    }.get(normalized, RiskLevel.MEDIUM)


def _question_terms(question: PddReplyReadinessQuestionV1) -> set[str]:
    return {
        normalized
        for value in [question.canonical_question, *question.aliases]
        if (normalized := _normalize_match(value))
    }


def _faq_context(
    question: PddReplyReadinessQuestionV1,
    records: list[_KnowledgeRecord],
) -> tuple[str | None, RiskLevel, bool, list[ReplyReadinessKnowledgeSnapshotV1], list[str]]:
    terms = _question_terms(question)
    matches: list[_KnowledgeRecord] = []
    for record in records:
        if record.source.template_type != "FAQ":
            continue
        answer = record.values.get("标准回答") or record.values.get("推荐回答方向")
        if not answer:
            continue
        related = record.values.get("关联问题ID")
        if related:
            if related == question.question_id:
                matches.append(record)
            continue
        if _normalize_match(record.values.get("客户常问问题", "")) in terms:
            matches.append(record)
    if not matches:
        return None, RiskLevel.LOW, False, [], []
    answers = list(dict.fromkeys(
        (record.values.get("标准回答") or record.values.get("推荐回答方向") or "").strip()
        for record in matches
    ))
    blockers = ["FAQ_ANSWER_CONFLICT"] if len(answers) > 1 else []
    risks = [_risk_from_label(record.values.get("风险等级")) for record in matches]
    manual = any(record.values.get("是否需要人工确认") in {"是", "需要", "需人工确认"} for record in matches)
    sources = _unique_sources([record.source for record in matches])
    return answers[0] if len(answers) == 1 else None, max(risks, key=_RISK.__getitem__), manual, sources, blockers


def _split_claims(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，;；\n]+", value) if item.strip()]


def _safety_context(
    question: PddReplyReadinessQuestionV1,
    records: list[_KnowledgeRecord],
) -> tuple[str | None, RiskLevel, list[ReplyReadinessKnowledgeSnapshotV1], list[str]]:
    safety_records = [record for record in records if record.source.template_type == "SAFETY_RULE"]
    prohibited = list(dict.fromkeys(
        claim
        for record in safety_records
        for claim in _split_claims(record.values.get("禁止承诺内容", ""))
    ))
    matches = [record for record in safety_records if record.values.get("关联问题ID") == question.question_id]
    reminders = list(dict.fromkeys(record.values.get("安全提醒", "").strip() for record in matches if record.values.get("安全提醒")))
    risks = [_risk_from_label(record.values.get("风险等级")) for record in matches]
    sources = _unique_sources([record.source for record in matches])
    return ("；".join(reminders) if reminders else None), (max(risks, key=_RISK.__getitem__) if risks else RiskLevel.LOW), sources, prohibited


def _turn(question: str, run_id: str, question_id: str) -> dict[str, Any]:
    return {
        "ai_cs_reply_turn": {
            "schema_version": "ai-cs-reply-turn.v1",
            "turn_id": f"{run_id}:{question_id}",
            "aggregate_content_sha256": text_sha256(question),
            "index_unit": "UNICODE_CODE_POINT",
            "aggregation_separator": "\n",
            "messages": [
                {
                    "message_id": f"synthetic:{question_id}",
                    "content_sha256": text_sha256(question),
                    "range_start": 0,
                    "range_end": len(question),
                }
            ],
        }
    }


def _answer(
    question: PddReplyReadinessQuestionV1,
    facts: Mapping[str, str],
    faq_answer: str | None = None,
    safety_answer: str | None = None,
) -> str:
    if faq_answer:
        answer = faq_answer
        if safety_answer and safety_answer not in answer:
            answer = f"{answer}；{safety_answer}"
        return answer
    if question.category == "GREETING":
        return "亲，您好，请问有什么可以帮您？"
    if question.category == "AFFIRMATION":
        return "好的，亲。"
    if question.category == "THANKS":
        return "不客气，亲。"
    if question.required_fact_keys:
        values = [facts[key] for key in question.required_fact_keys]
        if question.question_id == "PDD-PARTICLE-COUNT":
            return f"亲，这款商品的颗粒数量是{values[0]}。"
        if question.question_id == "PDD-FINISHED-SIZE":
            return f"亲，这款商品拼好后的成品尺寸是{values[0]}。"
        if question.question_id == "PDD-MATERIAL":
            return f"亲，这款商品的材质是{values[0]}。"
        if question.question_id == "PDD-SHIP-ORIGIN":
            return f"亲，这款商品从{values[0]}发货。"
        answer = f"亲，当前已确认的信息是：{'；'.join(values)}。"
        if safety_answer and safety_answer not in answer:
            answer = f"{answer}{safety_answer}"
        return answer
    if safety_answer:
        return safety_answer
    return "亲，已收到您的问题。"


def _blockers(result: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    trace = result.get("reply_router_trace")
    if isinstance(trace, dict):
        for value in trace.get("blocker_codes") or []:
            if isinstance(value, str):
                values.append(value)
        plan = trace.get("sub_question_plan")
        if isinstance(plan, dict):
            for value in plan.get("blocker_codes") or []:
                if isinstance(value, str):
                    values.append(value)
    for value in result.get("warnings") or []:
        if isinstance(value, str) and value.startswith("ROUTER_BLOCKED_"):
            values.append(value.removeprefix("ROUTER_BLOCKED_"))
    return list(dict.fromkeys(values))


class ReplyReadinessEvaluator:
    """Run the real ReplyRouter with an in-memory, non-publishing RAG provider."""

    def __init__(
        self,
        snapshot_store: ReplyRuleSnapshotStore,
        published_runtime: PublishedReplyReadinessRuntime | None = None,
        *,
        clock: Any | None = None,
    ) -> None:
        self.snapshot_store = snapshot_store
        self.published_runtime = published_runtime
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(
        self, payload: PddReplyReadinessInputV1
    ) -> PddReplyReadinessResultV1 | PddReplyReadinessPublishedDebugResultV1:
        if payload.execution_mode is ReplyReadinessExecutionMode.PUBLISHED_ROUTER_DEBUG:
            return self._evaluate_published_debug(payload)
        if not payload.test_data_mode or payload.production_usable or payload.allow_auto_send:
            raise ValueError("reply-readiness input must be isolated and non-sending")
        if payload.router_build_fingerprint != _ROUTER_CONTRACT_FINGERPRINT:
            raise ValueError("reply-readiness router build drifted")
        publication = self.snapshot_store.current(payload.scope.tenant_id, payload.scope.platform)
        if (
            publication.snapshot_revision != payload.reply_rule_snapshot_revision
            or publication.snapshot_fingerprint != payload.reply_rule_snapshot_fingerprint
        ):
            raise ValueError("reply-readiness rule snapshot drifted")
        sources = payload.knowledge_sources or ([payload.knowledge_snapshot] if payload.knowledge_snapshot else [])
        seen_material_ids: set[str] = set()
        for source in sources:
            if source.material_id in seen_material_ids:
                raise ValueError("reply-readiness knowledge material revision duplicated")
            seen_material_ids.add(source.material_id)
            if source.material_status not in {
                "RECOGNIZED", "REVIEWING", "APPROVED_FOR_ANALYSIS", "ANALYZING", "ANALYZED",
            }:
                raise ValueError("reply-readiness knowledge status is not usable")
            if source.template_type not in {
                "PRODUCT_KNOWLEDGE", "SKU_DIFFERENCE", "FAQ", "SAFETY_RULE",
            }:
                raise ValueError("reply-readiness knowledge template is not usable")
            if source.store_code and source.store_code != payload.scope.store_code:
                raise ValueError("reply-readiness knowledge store scope drifted")
            if source.product_id and source.product_id != payload.scope.product_id:
                raise ValueError("reply-readiness knowledge product scope drifted")
            if source.sku_id and source.sku_id != payload.scope.sku_id:
                raise ValueError("reply-readiness knowledge SKU scope drifted")
        records = _knowledge_records(sources)
        facts, fact_blockers, fact_sources = _facts(records)
        scope = FrozenChatContext(
            tenant_id=payload.scope.tenant_id,
            platform=payload.scope.platform,
            store_code=payload.scope.store_code,
            product_id=payload.scope.product_id,
            sku_id=payload.scope.sku_id,
            verified_product=VerifiedProductContext(
                product_reference=payload.scope.product_id,
                sku_reference=payload.scope.sku_id,
                attributes=facts,
            ),
        )
        items: list[PddReplyReadinessItemResultV1] = []
        for question in payload.question_set.questions:
            faq_answer, faq_risk, faq_manual, faq_sources, faq_blockers = _faq_context(question, records)
            safety_answer, safety_risk, safety_sources, safety_prohibited = _safety_context(question, records)
            missing = [] if faq_answer else [key for key in question.required_fact_keys if key not in facts]
            local_blockers = [
                f"{fact_blockers[key]}_{key.upper()}"
                for key in question.required_fact_keys
                if key in fact_blockers
            ]
            local_blockers.extend(faq_blockers)
            relevant_sources = _unique_sources([
                *[source for key in question.required_fact_keys for source in fact_sources.get(key, [])],
                *faq_sources,
                *safety_sources,
            ])
            knowledge_risk = max([faq_risk, safety_risk], key=_RISK.__getitem__)

            def sandbox_rag(_: str, __: Mapping[str, Any]) -> dict[str, Any]:
                if question.requires_realtime_lookup or question.policy_risk_floor is RiskLevel.HIGH:
                    return {
                        "answer": "需要核对当前订单或实时页面后由人工客服处理。",
                        "action": question.expected_action.value,
                        "risk_level": "HIGH",
                        "sources": [],
                        "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
                        "required_fields": [],
                    }
                if missing or local_blockers:
                    return {
                        "answer": "当前资料不足，需要人工客服核实后回复。",
                        "action": "TRANSFER_HUMAN",
                        "risk_level": "HIGH",
                        "sources": [],
                        "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
                        "required_fields": [],
                    }
                action = question.expected_action
                required_fields: list[str] = []
                if knowledge_risk is RiskLevel.HIGH:
                    action = ExpectedAction.TRANSFER_HUMAN
                elif faq_manual and _ACTION_ORDER[action] < _ACTION_ORDER[ExpectedAction.CONTROLLED_ANSWER]:
                    action = ExpectedAction.CONTROLLED_ANSWER
                if action is ExpectedAction.ASK_CLARIFY:
                    if payload.scope.sku_id is None:
                        required_fields = ["sku_id"]
                    else:
                        action = ExpectedAction.CONTROLLED_ANSWER
                source_rows = [
                    {
                        "source_name": "reply-readiness governed replay",
                        "chunk_id": _source_id(source),
                        "distance": 0.0,
                        "product_id": source.product_id or payload.scope.product_id,
                        "sku_id": source.sku_id,
                        "knowledge_version": source.content_hash.removeprefix("sha256:"),
                        "source_ids": [_source_id(source)],
                    }
                    for source in relevant_sources
                ]
                if not source_rows:
                    source_rows = [{
                        "source_name": "reply-readiness policy baseline",
                        "chunk_id": f"rr:{payload.run_id}:{question.question_id}:policy",
                        "distance": 0.0,
                        "product_id": payload.scope.product_id,
                        "sku_id": payload.scope.sku_id,
                        "knowledge_version": payload.question_set.fingerprint,
                        "source_ids": [f"policy:{question.question_id}"],
                    }]
                return {
                    "answer": _answer(question, facts, faq_answer, safety_answer),
                    "action": action.value,
                    "risk_level": max([question.policy_risk_floor, knowledge_risk], key=_RISK.__getitem__).value,
                    "sources": source_rows,
                    "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
                    "required_fields": required_fields,
                }

            result = ReplyRouter(self.snapshot_store, sandbox_rag).decide(
                question.canonical_question,
                _turn(question.canonical_question, payload.run_id, question.question_id),
                scope,
            )
            actual_action_value = str(result.get("action") or "TRANSFER_HUMAN")
            try:
                actual_action = ExpectedAction(actual_action_value)
            except ValueError:
                actual_action = ExpectedAction.TRANSFER_HUMAN
            try:
                actual_risk = RiskLevel(str(result.get("risk_level") or "HIGH"))
            except ValueError:
                actual_risk = RiskLevel.HIGH
            router_blockers = _blockers(result)
            all_blockers = list(dict.fromkeys([*local_blockers, *router_blockers]))
            trace = result.get("reply_router_trace")
            origin = str(trace.get("origin") or "MANUAL") if isinstance(trace, dict) else "MANUAL"
            evidence = result.get("reply_evidence_bundle")
            evidence_hash = None
            if isinstance(evidence, dict):
                bundle_hash = evidence.get("bundle_sha256")
                if isinstance(bundle_hash, str) and re.fullmatch(r"[a-f0-9]{64}", bundle_hash):
                    evidence_hash = bundle_hash
            if origin == "FIXED_RULE" and evidence_hash and not local_blockers:
                missing = []
            effective = max(
                [
                    question.policy_risk_floor,
                    actual_risk,
                    knowledge_risk,
                    RiskLevel.HIGH if missing or all_blockers else RiskLevel.LOW,
                ],
                key=_RISK.__getitem__,
            )
            answer = str(result.get("answer") or "").strip()
            if actual_action in {ExpectedAction.TRANSFER_HUMAN, ExpectedAction.REQUIRE_LOOKUP, ExpectedAction.REFUSE}:
                answer = "需要人工客服核实后处理。"
            prohibited_claims = list(dict.fromkeys([*question.prohibited_claims, *safety_prohibited]))
            prohibited_hits = [claim for claim in prohibited_claims if claim and claim in answer]
            if prohibited_hits:
                effective = RiskLevel.HIGH
                all_blockers.append("PROHIBITED_CLAIM_PRESENT")
            citation_ids = [
                str(item["chunk_id"])
                for item in result.get("sources") or []
                if isinstance(item, dict) and isinstance(item.get("chunk_id"), str)
            ]
            items.append(PddReplyReadinessItemResultV1(
                schema_version="pdd-reply-readiness-item-result.v1",
                question_id=question.question_id,
                effective_risk=effective,
                action=actual_action,
                origin=origin,
                answer_preview=answer,
                answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                missing_fact_keys=missing,
                blocker_codes=list(dict.fromkeys(all_blockers)),
                prohibited_claim_hits=prohibited_hits,
                citation_ids=list(dict.fromkeys(citation_ids)),
                evidence_bundle_sha256=evidence_hash,
            ))
        base = {
            "schema_version": "pdd-reply-readiness-result.v1",
            "run_id": payload.run_id,
            "status": "COMPLETED",
            "question_set_fingerprint": payload.question_set.fingerprint,
            "items": [item.model_dump(mode="json") for item in items],
        }
        return PddReplyReadinessResultV1(
            schema_version="pdd-reply-readiness-result.v1",
            run_id=payload.run_id,
            status="COMPLETED",
            question_set_fingerprint=payload.question_set.fingerprint,
            items=items,
            result_sha256=canonical_sha256(base),
        )

    def _evaluate_published_debug(
        self, payload: PddReplyReadinessInputV1
    ) -> PddReplyReadinessPublishedDebugResultV1:
        if not payload.test_data_mode or payload.production_usable or payload.allow_auto_send:
            raise ValueError("published router debug must remain non-sending")
        if self.published_runtime is None:
            raise ValueError("published router debug runtime is unavailable")
        question = payload.question_set.questions[0]
        scope = FrozenChatContext(
            tenant_id=payload.scope.tenant_id,
            platform=payload.scope.platform,
            store_code=payload.scope.store_code,
            product_id=payload.scope.product_id,
            sku_id=payload.scope.sku_id,
            verified_product=payload.verified_product,
        )
        before_rule = self._current_rule_fingerprint(payload)
        before_runtime = self.published_runtime.snapshot(
            scope, payload.publication_state.current_fingerprint
        )
        provider = _PublishedRagProvider(
            self.published_runtime, payload, before_runtime
        )
        router_result = ReplyRouter(self.snapshot_store, provider).decide(
            question.canonical_question,
            _turn(question.canonical_question, payload.run_id, question.question_id),
            scope,
        )
        after_rule = self._current_rule_fingerprint(payload)
        after_runtime = self.published_runtime.snapshot(
            scope, payload.publication_state.current_fingerprint
        )
        origin, planned_routes = self._debug_origin_and_routes(router_result)
        router_blockers = _blockers(router_result)
        usage = ReplyReadinessDependencyUsageV1(
            router=True,
            reply_rule=(
                origin in {"FIXED_RULE", "COMPOSITE"}
                or "FIXED_RULE" in planned_routes
                or any(code.startswith("REPLY_RULE_") for code in router_blockers)
            ),
            rag_collection=provider.invoked,
            knowledge=provider.invoked,
            model=provider.query_called,
        )
        changes = self._runtime_changes(
            payload.reply_rule_snapshot_fingerprint,
            before_rule,
            after_rule,
            before_runtime,
            after_runtime,
        )
        drifted = [
            item.dependency
            for item in changes
            if getattr(usage, item.dependency)
        ]
        rule_references = self._rule_references(router_result)
        if drifted:
            return self._debug_result(
                payload=payload,
                status="FAILED",
                item=None,
                failure_code="PRODUCTION_RUNTIME_VERSION_DRIFT",
                quality_gate_status="MANUAL",
                rule_references=rule_references,
                rule_fingerprint=after_rule,
                runtime=after_runtime,
                usage=usage,
                changes=changes,
                drifted=drifted,
            )
        item = self._debug_item(question, router_result, provider, after_runtime)
        return self._debug_result(
            payload=payload,
            status="COMPLETED",
            item=item,
            failure_code=None,
            quality_gate_status=(
                "PASS"
                if router_result.get("quality_gate_status") == "PASS"
                and item.effective_risk is not RiskLevel.HIGH
                else "MANUAL"
            ),
            rule_references=rule_references,
            rule_fingerprint=after_rule,
            runtime=after_runtime,
            usage=usage,
            changes=changes,
            drifted=[],
        )

    def _current_rule_fingerprint(
        self, payload: PddReplyReadinessInputV1
    ) -> str | None:
        try:
            return self.snapshot_store.current(
                payload.scope.tenant_id, payload.scope.platform
            ).snapshot_fingerprint
        except ReplyRuleSnapshotUnavailable:
            return None

    @staticmethod
    def _debug_origin_and_routes(
        result: Mapping[str, Any]
    ) -> tuple[str, set[str]]:
        trace = result.get("reply_router_trace")
        if not isinstance(trace, dict):
            return "MANUAL", set()
        origin = str(trace.get("origin") or "MANUAL")
        routes: set[str] = set()
        plan = trace.get("sub_question_plan")
        if isinstance(plan, dict):
            for item in plan.get("sub_questions") or []:
                if isinstance(item, dict) and isinstance(item.get("route"), str):
                    routes.add(item["route"])
        return origin, routes

    @staticmethod
    def _runtime_changes(
        expected_rule: str | None,
        before_rule: str | None,
        after_rule: str | None,
        before: _PublishedRuntimeSnapshot,
        after: _PublishedRuntimeSnapshot,
    ) -> list[ReplyReadinessDiagnosticChangeV1]:
        rule_change = (
            (before_rule, after_rule)
            if before_rule != after_rule
            else (expected_rule, after_rule)
        )
        values = {
            "reply_rule": rule_change,
            "rag_collection": (
                before.rag_collection_identity,
                after.rag_collection_identity,
            ),
            "knowledge": (
                f"{before.knowledge_publication_status}:{before.knowledge_publication_fingerprint or '-'}",
                f"{after.knowledge_publication_status}:{after.knowledge_publication_fingerprint or '-'}",
            ),
            "model": (before.model_config_identity, after.model_config_identity),
        }
        return [
            ReplyReadinessDiagnosticChangeV1(
                dependency=dependency, before=before_value, after=after_value
            )
            for dependency, (before_value, after_value) in values.items()
            if before_value != after_value
        ]

    @staticmethod
    def _rule_references(result: Mapping[str, Any]) -> list[str]:
        evidence = result.get("reply_evidence_bundle")
        if not isinstance(evidence, dict):
            return []
        references: list[str] = []
        for source in evidence.get("sources") or []:
            if not isinstance(source, dict) or source.get("source_type") != "FIXED_RULE":
                continue
            rule_id = source.get("rule_id")
            version = source.get("rule_version")
            if isinstance(rule_id, str) and isinstance(version, int):
                references.append(f"{rule_id}:v{version}")
        return list(dict.fromkeys(references))

    @staticmethod
    def _debug_item(
        question: PddReplyReadinessQuestionV1,
        result: Mapping[str, Any],
        provider: _PublishedRagProvider,
        runtime: _PublishedRuntimeSnapshot,
    ) -> PddReplyReadinessItemResultV1:
        try:
            action = ExpectedAction(str(result.get("action") or "TRANSFER_HUMAN"))
        except ValueError:
            action = ExpectedAction.TRANSFER_HUMAN
        try:
            risk = RiskLevel(str(result.get("risk_level") or "HIGH"))
        except ValueError:
            risk = RiskLevel.HIGH
        blockers = _blockers(result)
        if provider.blocker_code:
            blockers.append(provider.blocker_code)
        origin, _ = ReplyReadinessEvaluator._debug_origin_and_routes(result)
        sources = [item for item in result.get("sources") or [] if isinstance(item, dict)]
        if origin in {"RAG", "COMPOSITE"} and provider.query_called:
            versions = {
                str(item.get("knowledge_version"))
                for item in sources
                if isinstance(item.get("knowledge_version"), str)
            }
            expected = runtime.knowledge_publication_fingerprint
            if not expected or versions != {expected}:
                blockers.append("KNOWLEDGE_FINGERPRINT_DRIFT")
        if blockers:
            action = ExpectedAction.TRANSFER_HUMAN
            risk = RiskLevel.HIGH
            origin = "MANUAL"
        answer = str(result.get("answer") or "").strip()
        if action in {
            ExpectedAction.TRANSFER_HUMAN,
            ExpectedAction.REQUIRE_LOOKUP,
            ExpectedAction.REFUSE,
        }:
            answer = "不会自动回复，需要人工客服核实后处理。"
        evidence = result.get("reply_evidence_bundle")
        evidence_hash = None
        if isinstance(evidence, dict):
            value = evidence.get("bundle_sha256")
            if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                evidence_hash = value
        citation_ids = [
            str(item["chunk_id"])
            for item in sources
            if isinstance(item.get("chunk_id"), str)
        ]
        required_fields = [
            str(item)
            for item in result.get("required_fields") or []
            if isinstance(item, str)
        ]
        return PddReplyReadinessItemResultV1(
            schema_version="pdd-reply-readiness-item-result.v1",
            question_id=question.question_id,
            effective_risk=risk,
            action=action,
            origin=origin,
            answer_preview=answer,
            answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            missing_fact_keys=list(dict.fromkeys(required_fields)),
            blocker_codes=list(dict.fromkeys(blockers)),
            prohibited_claim_hits=[],
            citation_ids=list(dict.fromkeys(citation_ids)),
            evidence_bundle_sha256=evidence_hash if not blockers else None,
        )

    def _debug_result(
        self,
        *,
        payload: PddReplyReadinessInputV1,
        status: str,
        item: PddReplyReadinessItemResultV1 | None,
        failure_code: str | None,
        quality_gate_status: str,
        rule_references: list[str],
        rule_fingerprint: str | None,
        runtime: _PublishedRuntimeSnapshot,
        usage: ReplyReadinessDependencyUsageV1,
        changes: list[ReplyReadinessDiagnosticChangeV1],
        drifted: list[str],
    ) -> PddReplyReadinessPublishedDebugResultV1:
        evaluated_at = self.clock().astimezone(timezone.utc)
        base = {
            "schema_version": "pdd-reply-readiness-published-debug-result.v1",
            "simulation_mode": "PUBLISHED_ROUTER_DEBUG",
            "run_id": payload.run_id,
            "status": status,
            "question_set_fingerprint": payload.question_set.fingerprint,
            "item": item,
            "failure_code": failure_code,
            "quality_gate_status": quality_gate_status,
            "rule_references": rule_references,
            "router_build_fingerprint": _ROUTER_BUILD_FINGERPRINT,
            "reply_rule_snapshot_fingerprint": rule_fingerprint,
            "rag_collection_identity": runtime.rag_collection_identity,
            "knowledge_publication_fingerprint": (
                runtime.knowledge_publication_fingerprint
            ),
            "knowledge_publication_status": runtime.knowledge_publication_status,
            "model_config_identity": runtime.model_config_identity,
            "evaluated_at": evaluated_at,
            "dependency_usage": usage,
            "diagnostic_changes": changes,
            "drifted_dependencies": drifted,
            "production_usable": False,
            "allow_auto_send": False,
        }
        unvalidated = PddReplyReadinessPublishedDebugResultV1.model_construct(
            **base, result_sha256="0" * 64
        )
        result_sha256 = canonical_sha256(
            unvalidated.model_dump(mode="json", exclude={"result_sha256"})
        )
        return PddReplyReadinessPublishedDebugResultV1(
            **base, result_sha256=result_sha256
        )
