from __future__ import annotations

import re
import string
import unicodedata
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.chat import FrozenChatContext, VerifiedConversationEntry
from app.reply_router.contracts import (
    EvidenceSourceType,
    EvidenceSourceV1,
    ProposedContentRangeV1,
    ReplyAction,
    ReplyEvidenceBundleV1,
    ReplyFactV1,
    ReplyOrigin,
    ReplyRiskLevel,
    ReplyRuleV1,
    ReplyRuleStatus,
    ReplyScopeV1,
    ReplySegmentV1,
    ReplyTurnEnvelopeV1,
    ReplyTurnParseStatus,
    RuleScopeKind,
    SourceTextRangeV1,
    SplitStatus,
    SubQuestionPlanV1,
    SubQuestionRoute,
    SubQuestionV1,
    parse_reply_turn_envelope,
    text_sha256,
)
from app.reply_router.publication_store import (
    ReplyRuleSnapshotStore,
    ReplyRuleSnapshotUnavailable,
)


RagProvider = Callable[[str, FrozenChatContext], dict[str, Any]]
Clock = Callable[[], datetime]

_HARD_DELIMITERS = frozenset("。！？?!；;")
_COMMA_DELIMITERS = frozenset("，,")
_SCOPE_PRIORITY = {"TENANT": 1, "STORE": 2, "PRODUCT": 3, "SKU": 4}
_ACTION_PRIORITY = {
    ReplyAction.DIRECT_ANSWER: 1,
    ReplyAction.CONTROLLED_ANSWER: 2,
    ReplyAction.ASK_CLARIFY: 3,
}
_RISK_PRIORITY = {
    ReplyRiskLevel.LOW: 1,
    ReplyRiskLevel.MEDIUM: 2,
    ReplyRiskLevel.HIGH: 3,
}
_SUGGEST_ACTIONS = frozenset(_ACTION_PRIORITY)
_SAFE_RAG_WARNINGS = frozenset({"SUGGESTION_ONLY", "AUTO_SEND_DISABLED"})
_REVIEWED_APPROXIMATE_CONTROL_KIND = "REVIEWED_APPROXIMATE_FACT"
_RAG_FAILURE_WARNINGS = frozenset(
    {
        "RAG_RUNTIME_ERROR",
        "LLM_REQUEST_FAILED",
        "KNOWLEDGE_NOT_PUBLISHED",
        "NO_SCOPED_KNOWLEDGE",
    }
)
_ALLOWED_CLARIFY_FIELDS = frozenset({"product_id", "sku_id"})
_QUALITY_BLOCKED_INTENTS = frozenset(
    {"REALTIME_ORDER", "AUTHENTICITY", "AFTERSALES"}
)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PROHIBITED_AUTO_CLAIMS = (
    re.compile(r"(?:一定|肯定|百分之百|100%|绝对安全|无条件退款|无条件赔付)"),
    re.compile(r"(?<!不)(?:保证|确保).{0,16}(?:发货|到货|送达|退款|赔付|安全)"),
)
_APPROXIMATE_NUMERIC_FACT = re.compile(
    r"(?:估测|估计|大约|约)\s*\d|\d(?:[\d.×xX*乘\s]|厘米|cm|颗|件|个|:){0,16}(?:左右|上下|约)",
    flags=re.I,
)
_APPROVED_SYNONYMS = (
    ("什么材料", "什么材质"),
    ("哪种材料", "什么材质"),
    ("材料", "材质"),
    ("有多少颗", "多少颗"),
    ("颗粒数量", "多少颗"),
    ("从哪里发货", "发货地"),
    ("从哪发货", "发货地"),
    ("发出地", "发货地"),
)
_INTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MATERIAL", (r"材质", r"材料", r"什么料", r"做的")),
    ("PARTICLE_COUNT", (r"多少颗", r"几颗", r"颗粒数", r"积木数量")),
    ("FINISHED_SIZE", (r"尺寸", r"长宽高", r"多大", r"多长", r"多宽", r"多高")),
    ("SHIP_ORIGIN", (r"哪里发货", r"哪发货", r"发货地", r"从哪里寄")),
    ("PRODUCT_NAME", (r"叫什么", r"商品名", r"产品名", r"哪一款")),
    ("AGE", (r"几岁", r"年龄", r"适龄", r"多大孩子", r"儿童.*适合")),
    ("PACKAGING", (r"包装", r"礼盒", r"袋装", r"盒装")),
    ("COLOR", (r"颜色", r"什么色", r"哪种色")),
    (
        "REALTIME_ORDER",
        (
            r"库存",
            r"物流",
            r"快递",
            r"退款",
            r"改地址",
            r"改订单",
            r"付款",
            r"支付",
            r"赔付",
            r"什么时候到",
            r"多久到",
        ),
    ),
    ("AUTHENTICITY", (r"正品", r"真假", r"A货", r"授权")),
    ("AFTERSALES", (r"售后", r"退货", r"换货", r"破损", r"少件", r"补发")),
)
_UNRESOLVED_REFERENCE = re.compile(
    r"(?:前者|后者|上一个|上面那个|刚才那个|另外那个|另一个链接|它们俩)"
)
_SKU_REFERENCE = re.compile(r"(?i)(?<![A-Z0-9])SKU[-_:]?[A-Z0-9-]+")
_PRODUCT_REFERENCE = re.compile(
    r"(?i)(?<![A-Z0-9])(?:PRODUCT[-_:]?[A-Z0-9-]+|P\d{3,})(?![A-Z0-9])"
)


class RouterLocalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReplyRouterSegmentV1(RouterLocalModel):
    schema_version: Literal["reply-router-segment.v1"] = "reply-router-segment.v1"
    segment_id: str = Field(min_length=1, max_length=255)
    ordinal: int = Field(ge=1, le=8)
    sub_question_id: str = Field(min_length=1, max_length=255)
    route: SubQuestionRoute
    answer: str = Field(min_length=1, max_length=8_000)
    action: ReplyAction
    risk_level: ReplyRiskLevel
    source_references: tuple[str, ...] = Field(min_length=1, max_length=32)
    rule_id: str | None = Field(default=None, max_length=255)
    rule_version: int | None = Field(default=None, ge=1)


class ReplyRouterTraceV1(RouterLocalModel):
    schema_version: Literal["reply-router-trace.v1"] = "reply-router-trace.v1"
    origin: ReplyOrigin | None = None
    sub_question_plan: SubQuestionPlanV1 | None = None
    segments: tuple[ReplyRouterSegmentV1, ...] = Field(default=(), max_length=8)
    blocker_codes: tuple[str, ...] = Field(default=(), max_length=32)


class ReplyQualityGateStatus(StrEnum):
    PASS = "PASS"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class ReplyQualityGateResultV1(RouterLocalModel):
    schema_version: Literal["reply-quality-gate.v1"] = "reply-quality-gate.v1"
    status: ReplyQualityGateStatus
    evidence_bundle: ReplyEvidenceBundleV1 | None = None
    blocker_code: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def result_is_consistent(self) -> "ReplyQualityGateResultV1":
        if self.status is ReplyQualityGateStatus.PASS:
            if self.evidence_bundle is None or self.blocker_code is not None:
                raise ValueError("quality PASS requires only an evidence bundle")
        elif self.evidence_bundle is not None or not self.blocker_code:
            raise ValueError("manual quality result requires only a blocker")
        return self


class _Fragment(RouterLocalModel):
    ordinal: int = Field(ge=1, le=8)
    message_id: str = Field(min_length=1, max_length=255)
    start: int = Field(ge=0, le=8_000)
    end: int = Field(gt=0, le=8_000)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    intent: str = Field(min_length=1, max_length=512)


class _RuleMatch(RouterLocalModel):
    rule: ReplyRuleV1
    alias_length: int = Field(ge=1)


class ReplyRouter:
    """Fail-closed fixed-rule/RAG router for the Gateway request path.

    The router consumes Engine's exact turn envelope but never grants send
    authority.  Its successful decisions remain approval-required Gateway V1
    suggestions; every uncertain condition becomes a manual/no-action result.
    """

    def __init__(
        self,
        snapshot_store: ReplyRuleSnapshotStore,
        rag_provider: RagProvider,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._snapshot_store = snapshot_store
        self._rag_provider = rag_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def decide(
        self,
        customer_message: str,
        raw_context: Mapping[str, Any],
        scope: FrozenChatContext,
    ) -> dict[str, Any]:
        parsed = parse_reply_turn_envelope(raw_context, customer_message)
        if parsed.status is not ReplyTurnParseStatus.VALID or parsed.envelope is None:
            return self._manual(parsed.blocker_code or "REPLY_TURN_ENVELOPE_INVALID")

        envelope = parsed.envelope
        fragments, split_blocker = self._split(customer_message, envelope, scope)
        if split_blocker:
            plan = self._plan(
                envelope,
                fragments,
                routes=tuple(SubQuestionRoute.MANUAL for _ in fragments),
                blocker=split_blocker,
            )
            return self._manual(split_blocker, plan=plan)

        try:
            publication = self._snapshot_store.current(scope.tenant_id, scope.platform)
        except ReplyRuleSnapshotUnavailable:
            return self._manual(
                "REPLY_RULE_SNAPSHOT_UNAVAILABLE",
                plan=self._plan(
                    envelope,
                    fragments,
                    routes=tuple(SubQuestionRoute.MANUAL for _ in fragments),
                    blocker="REPLY_RULE_SNAPSHOT_UNAVAILABLE",
                ),
            )

        rules = publication.rules if publication is not None else ()
        routes: list[SubQuestionRoute] = []
        pending: list[tuple[_Fragment, ReplyRuleV1 | None]] = []
        for fragment in fragments:
            text = customer_message[fragment.start : fragment.end]
            matched, blocker = self._match_rule(text, scope, rules)
            if blocker:
                plan = self._plan(
                    envelope,
                    fragments,
                    routes=tuple(SubQuestionRoute.MANUAL for _ in fragments),
                    blocker=blocker,
                )
                return self._manual(blocker, plan=plan)
            if matched is not None:
                rendered, _, render_blocker = self._render_rule(
                    matched.rule, scope
                )
                if (
                    render_blocker is None
                    and rendered is not None
                    and matched.rule.action is ReplyAction.DIRECT_ANSWER
                    and matched.rule.risk_level is ReplyRiskLevel.LOW
                    and _APPROXIMATE_NUMERIC_FACT.search(rendered)
                ):
                    # Legacy fixed rules can predate the reviewed-approximate
                    # evidence policy.  Re-evaluate them through the governed
                    # knowledge path instead of treating an estimate as a
                    # low-risk fixed fact.
                    matched = None
            route = SubQuestionRoute.FIXED_RULE if matched else SubQuestionRoute.RAG
            routes.append(route)
            pending.append((fragment, matched.rule if matched else None))

        plan = self._plan(envelope, fragments, routes=tuple(routes), blocker=None)
        rag_context = self._rag_context(scope, envelope, customer_message)
        if rag_context is None and any(route is SubQuestionRoute.RAG for route in routes):
            return self._manual("REPLY_TURN_CONTEXT_TOO_LARGE", plan=plan)

        segments: list[ReplyRouterSegmentV1] = []
        all_sources: list[dict[str, Any]] = []
        required_fields: list[str] = []
        for fragment, rule in pending:
            question = customer_message[fragment.start : fragment.end]
            sub_question_id = self._sub_question_id(envelope, fragment)
            if rule is not None:
                rendered, missing, blocker = self._render_rule(rule, scope)
                if blocker or rendered is None:
                    return self._manual(
                        blocker or "FIXED_RULE_RENDER_FAILED",
                        plan=plan,
                        required_fields=missing,
                    )
                if rule.action not in _SUGGEST_ACTIONS or rule.risk_level is ReplyRiskLevel.HIGH:
                    return self._manual("FIXED_RULE_REQUIRES_MANUAL", plan=plan)
                if rule.action is ReplyAction.ASK_CLARIFY:
                    for field in rule.required_context_fields:
                        if field not in required_fields:
                            required_fields.append(field)
                source_reference = f"reply-rule:{rule.rule_id}:v{rule.rule_version}"
                source = {
                    "source_name": "published reply rule",
                    "chunk_id": source_reference,
                    "distance": 0.0,
                    "product_id": rule.scope.product_id,
                    "sku_id": rule.scope.sku_id,
                }
                all_sources.append(source)
                segments.append(
                    ReplyRouterSegmentV1(
                        segment_id=f"segment-{fragment.ordinal}",
                        ordinal=fragment.ordinal,
                        sub_question_id=sub_question_id,
                        route=SubQuestionRoute.FIXED_RULE,
                        answer=rendered,
                        action=rule.action,
                        risk_level=rule.risk_level,
                        source_references=(source_reference,),
                        rule_id=rule.rule_id,
                        rule_version=rule.rule_version,
                    )
                )
                continue

            assert rag_context is not None
            try:
                rag_result = self._rag_provider(question, rag_context)
            except Exception:
                return self._manual("RAG_PROVIDER_UNAVAILABLE", plan=plan)
            accepted, blocker = self._validate_rag_result(rag_result, scope)
            if not accepted:
                return self._manual(blocker or "RAG_RESULT_REJECTED", plan=plan)
            rag_sources = rag_result["sources"]
            references = tuple(str(item["chunk_id"]) for item in rag_sources)
            all_sources.extend(dict(item) for item in rag_sources)
            for field in rag_result.get("required_fields", []):
                if field not in required_fields:
                    required_fields.append(field)
            segments.append(
                ReplyRouterSegmentV1(
                    segment_id=f"segment-{fragment.ordinal}",
                    ordinal=fragment.ordinal,
                    sub_question_id=sub_question_id,
                    route=SubQuestionRoute.RAG,
                    answer=rag_result["answer"].strip(),
                    action=ReplyAction(rag_result["action"]),
                    risk_level=ReplyRiskLevel(rag_result["risk_level"]),
                    source_references=references,
                )
            )

        answer = "\n".join(item.answer for item in segments)
        if not answer.strip() or len(answer) > 8_000:
            return self._manual("COMPOSITE_REPLY_SIZE_INVALID", plan=plan)
        unique_sources = {
            str(item["chunk_id"]): item
            for item in all_sources
            if isinstance(item.get("chunk_id"), str)
        }
        if len(unique_sources) > 32:
            return self._manual("COMPOSITE_SOURCE_LIMIT_EXCEEDED", plan=plan)
        action = max((item.action for item in segments), key=_ACTION_PRIORITY.__getitem__)
        risk = max((item.risk_level for item in segments), key=_RISK_PRIORITY.__getitem__)
        routes_used = {item.route for item in segments}
        origin = (
            ReplyOrigin.COMPOSITE
            if len(routes_used) > 1
            else ReplyOrigin.FIXED_RULE
            if SubQuestionRoute.FIXED_RULE in routes_used
            else ReplyOrigin.RAG
        )
        trace = ReplyRouterTraceV1(
            origin=origin,
            sub_question_plan=plan,
            segments=tuple(segments),
        )
        source_items = list(unique_sources.values())
        quality = self._evaluate_quality_gate(
            answer=answer,
            action=action,
            risk_level=risk,
            sources=source_items,
            required_fields=required_fields,
            trace=trace,
            scope=scope,
        )
        if quality.status is not ReplyQualityGateStatus.PASS:
            return self._manual(
                quality.blocker_code or "QUALITY_GATE_FAILED",
                plan=plan,
            )
        assert quality.evidence_bundle is not None
        return {
            "answer": answer,
            "action": action.value,
            "risk_level": risk.value,
            "sources": source_items,
            "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
            "required_fields": required_fields,
            "reply_router_trace": trace.model_dump(mode="json"),
            "quality_gate_status": ReplyQualityGateStatus.PASS.value,
            "reply_evidence_bundle": quality.evidence_bundle.model_dump(mode="json"),
        }

    def _evaluate_quality_gate(
        self,
        *,
        answer: str,
        action: ReplyAction,
        risk_level: ReplyRiskLevel,
        sources: list[dict[str, Any]],
        required_fields: list[str],
        trace: ReplyRouterTraceV1,
        scope: FrozenChatContext,
    ) -> ReplyQualityGateResultV1:
        plan = trace.sub_question_plan
        if (
            trace.origin is None
            or plan is None
            or trace.blocker_codes
            or plan.split_status is SplitStatus.AMBIGUOUS
            or plan.blocker_codes
            or not trace.segments
        ):
            return self._quality_manual("QUALITY_TRACE_INVALID")
        if any(
            item.intent in _QUALITY_BLOCKED_INTENTS
            for item in plan.sub_questions
        ):
            return self._quality_manual("QUALITY_INTENT_REQUIRES_MANUAL")
        if answer != "\n".join(item.answer for item in trace.segments):
            return self._quality_manual("QUALITY_REPLY_TRACE_MISMATCH")
        expected_action = max(
            (item.action for item in trace.segments),
            key=_ACTION_PRIORITY.__getitem__,
        )
        expected_risk = max(
            (item.risk_level for item in trace.segments),
            key=_RISK_PRIORITY.__getitem__,
        )
        if action is not expected_action or risk_level is not expected_risk:
            return self._quality_manual("QUALITY_AGGREGATE_DECISION_MISMATCH")
        if any(pattern.search(answer) for pattern in _PROHIBITED_AUTO_CLAIMS):
            return self._quality_manual("QUALITY_PROHIBITED_CLAIM")
        if (
            action is ReplyAction.DIRECT_ANSWER
            and risk_level is ReplyRiskLevel.LOW
            and _APPROXIMATE_NUMERIC_FACT.search(answer)
        ):
            return self._quality_manual(
                "QUALITY_APPROXIMATE_FACT_REQUIRES_CONTROLLED"
            )

        frozen_scope = self._frozen_evidence_scope(scope)
        source_by_reference = {
            item.get("chunk_id"): item
            for item in sources
            if isinstance(item, dict) and isinstance(item.get("chunk_id"), str)
        }
        try:
            current_publication = self._snapshot_store.current(
                scope.tenant_id, scope.platform
            )
        except ReplyRuleSnapshotUnavailable:
            return self._quality_manual("QUALITY_RULE_SNAPSHOT_UNAVAILABLE")
        rules = (
            current_publication.rules if current_publication is not None else ()
        )
        rule_by_identity = {
            (item.rule_id, item.rule_version): item for item in rules
        }
        evidence_by_identity: dict[
            tuple[str, str, str], EvidenceSourceV1
        ] = {}
        reference_to_source_id: dict[tuple[SubQuestionRoute, str], str] = {}
        expected_clarification_fields: list[str] = []
        now = self._clock().astimezone(timezone.utc)

        for segment in trace.segments:
            if segment.route is SubQuestionRoute.FIXED_RULE:
                if (segment.action, segment.risk_level) not in {
                    (ReplyAction.DIRECT_ANSWER, ReplyRiskLevel.LOW),
                    (ReplyAction.CONTROLLED_ANSWER, ReplyRiskLevel.MEDIUM),
                    (ReplyAction.ASK_CLARIFY, ReplyRiskLevel.MEDIUM),
                }:
                    return self._quality_manual("QUALITY_FIXED_POLICY_REJECTED")
                if segment.rule_id is None or segment.rule_version is None:
                    return self._quality_manual("QUALITY_RULE_IDENTITY_MISSING")
                rule = rule_by_identity.get(
                    (segment.rule_id, segment.rule_version)
                )
                if rule is None:
                    return self._quality_manual("QUALITY_RULE_NOT_CURRENT")
                if (
                    rule.status is not ReplyRuleStatus.PUBLISHED
                    or rule.effective_from.astimezone(timezone.utc) > now
                    or (
                        rule.effective_to is not None
                        and rule.effective_to.astimezone(timezone.utc) <= now
                    )
                    or not self._rule_in_scope(rule, scope)
                    or not rule.scope.contains_frozen_scope(frozen_scope)
                    or not rule.allow_auto_candidate
                    or rule.action is not segment.action
                    or rule.risk_level is not segment.risk_level
                ):
                    return self._quality_manual("QUALITY_RULE_POLICY_STALE")
                rendered, _, blocker = self._render_rule(rule, scope)
                if blocker or rendered != segment.answer:
                    return self._quality_manual("QUALITY_RULE_REPLY_MISMATCH")
                expected_reference = (
                    f"reply-rule:{rule.rule_id}:v{rule.rule_version}"
                )
                if segment.source_references != (expected_reference,):
                    return self._quality_manual("QUALITY_RULE_SOURCE_MISMATCH")
                source_id = self._evidence_id(
                    "fixed",
                    f"{rule.rule_id}:v{rule.rule_version}",
                    current_publication.snapshot_fingerprint,
                )
                evidence = EvidenceSourceV1(
                    source_id=source_id,
                    source_type=EvidenceSourceType.FIXED_RULE,
                    scope=rule.scope,
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    rule_content_fingerprint=rule.content_fingerprint,
                    rule_snapshot_revision=current_publication.snapshot_revision,
                    rule_snapshot_fingerprint=(
                        current_publication.snapshot_fingerprint
                    ),
                    rule_source_materials=rule.source_materials,
                )
                evidence_by_identity[
                    (
                        "fixed",
                        f"{rule.rule_id}:v{rule.rule_version}",
                        current_publication.snapshot_fingerprint,
                    )
                ] = evidence
                reference_to_source_id[
                    (SubQuestionRoute.FIXED_RULE, expected_reference)
                ] = source_id
                if segment.action is ReplyAction.ASK_CLARIFY:
                    for field in rule.required_context_fields:
                        if field not in expected_clarification_fields:
                            expected_clarification_fields.append(field)
                continue

            if segment.route is not SubQuestionRoute.RAG:
                return self._quality_manual("QUALITY_ROUTE_INVALID")
            reviewed_approximate = (
                segment.action is ReplyAction.CONTROLLED_ANSWER
                and segment.risk_level is ReplyRiskLevel.MEDIUM
                and all(
                    source_by_reference.get(reference, {}).get(
                        "controlled_answer_kind"
                    )
                    == _REVIEWED_APPROXIMATE_CONTROL_KIND
                    for reference in segment.source_references
                )
            )
            if (
                not (
                    (
                        segment.action is ReplyAction.DIRECT_ANSWER
                        and segment.risk_level is ReplyRiskLevel.LOW
                    )
                    or reviewed_approximate
                )
                or segment.rule_id is not None
                or segment.rule_version is not None
            ):
                return self._quality_manual("QUALITY_RAG_POLICY_REJECTED")
            for reference in segment.source_references:
                source = source_by_reference.get(reference)
                if source is None:
                    return self._quality_manual("QUALITY_RAG_SOURCE_MISSING")
                fingerprint = source.get("knowledge_version")
                lineage = source.get("source_ids")
                if not isinstance(fingerprint, str) or not _SHA256.fullmatch(
                    fingerprint
                ):
                    return self._quality_manual(
                        "QUALITY_KNOWLEDGE_FINGERPRINT_MISSING"
                    )
                if (
                    not isinstance(lineage, list)
                    or not lineage
                    or len(lineage) > 100
                    or any(
                        not isinstance(item, str)
                        or not item.strip()
                        or item != item.strip()
                        or len(item) > 255
                        or "\r" in item
                        or "\n" in item
                        for item in lineage
                    )
                ):
                    return self._quality_manual("QUALITY_KNOWLEDGE_LINEAGE_INVALID")
                source_scope = self._rag_evidence_scope(source, scope)
                if source_scope is None or not source_scope.contains_frozen_scope(
                    frozen_scope
                ):
                    return self._quality_manual("QUALITY_RAG_SCOPE_INVALID")
                source_id = self._evidence_id("rag", reference, fingerprint)
                evidence = EvidenceSourceV1(
                    source_id=source_id,
                    source_type=EvidenceSourceType.RAG_KNOWLEDGE,
                    scope=source_scope,
                    knowledge_reference=reference,
                    knowledge_publication_fingerprint=fingerprint,
                )
                identity = ("rag", reference, fingerprint)
                existing = evidence_by_identity.get(identity)
                if existing is not None and existing != evidence:
                    return self._quality_manual("QUALITY_SOURCE_IDENTITY_CONFLICT")
                evidence_by_identity[identity] = evidence
                reference_to_source_id[
                    (SubQuestionRoute.RAG, reference)
                ] = source_id

        has_clarification = any(
            item.action is ReplyAction.ASK_CLARIFY for item in trace.segments
        )
        if has_clarification:
            if (
                not expected_clarification_fields
                or required_fields != expected_clarification_fields
                or not set(required_fields).issubset(_ALLOWED_CLARIFY_FIELDS)
            ):
                return self._quality_manual("QUALITY_CLARIFICATION_FIELDS_INVALID")
        elif required_fields:
            return self._quality_manual("QUALITY_MISSING_FIELDS_PRESENT")

        evidence_segments: list[ReplySegmentV1] = []
        evidence_facts: list[ReplyFactV1] = []
        cursor = 0
        for index, segment in enumerate(trace.segments):
            content = segment.answer if index == 0 else f"\n{segment.answer}"
            end = cursor + len(content)
            content_range = ProposedContentRangeV1(
                range_start=cursor,
                range_end=end,
                content_sha256=text_sha256(content),
            )
            try:
                source_ids = tuple(
                    reference_to_source_id[(segment.route, reference)]
                    for reference in segment.source_references
                )
            except KeyError:
                return self._quality_manual("QUALITY_SEGMENT_SOURCE_UNRESOLVED")
            if len(source_ids) != len(set(source_ids)):
                return self._quality_manual("QUALITY_SEGMENT_SOURCE_DUPLICATED")
            evidence_segments.append(
                ReplySegmentV1(
                    segment_id=segment.segment_id,
                    ordinal=segment.ordinal,
                    sub_question_id=segment.sub_question_id,
                    content_range=content_range,
                    action=segment.action,
                    risk_level=segment.risk_level,
                    source_ids=source_ids,
                )
            )
            evidence_facts.append(
                ReplyFactV1(
                    fact_id=f"fact-{segment.ordinal}",
                    segment_id=segment.segment_id,
                    content_range=content_range,
                    source_ids=source_ids,
                )
            )
            cursor = end
        if cursor != len(answer):
            return self._quality_manual("QUALITY_CONTENT_RANGE_MISMATCH")

        try:
            draft = ReplyEvidenceBundleV1.model_construct(
                schema_version="reply-evidence-bundle.v1",
                reply_origin=trace.origin,
                scope=frozen_scope,
                sub_question_plan=plan,
                segments=tuple(evidence_segments),
                sources=tuple(evidence_by_identity.values()),
                facts=tuple(evidence_facts),
                warnings=(),
                missing_fields=tuple(required_fields),
                blocker_codes=(),
                bundle_sha256="0" * 64,
            )
            bundle = ReplyEvidenceBundleV1(
                **draft.model_dump(exclude={"bundle_sha256"}),
                bundle_sha256=draft.expected_bundle_sha256(),
            )
            bundle.validate_proposed_content(answer)
        except (TypeError, ValueError):
            return self._quality_manual("QUALITY_EVIDENCE_INVALID")
        return ReplyQualityGateResultV1(
            status=ReplyQualityGateStatus.PASS,
            evidence_bundle=bundle,
        )

    @staticmethod
    def _quality_manual(blocker: str) -> ReplyQualityGateResultV1:
        return ReplyQualityGateResultV1(
            status=ReplyQualityGateStatus.MANUAL_REQUIRED,
            blocker_code=blocker,
        )

    @staticmethod
    def _evidence_id(source_type: str, reference: str, version: str) -> str:
        identity = "\0".join((source_type, reference, version))
        return f"source-{text_sha256(identity)[:24]}"

    @staticmethod
    def _frozen_evidence_scope(scope: FrozenChatContext) -> ReplyScopeV1:
        if scope.product_id.startswith("__STORE_LEVEL_"):
            return ReplyScopeV1(
                scope_kind=RuleScopeKind.STORE,
                tenant_id=scope.tenant_id,
                platform=scope.platform,
                store_code=scope.store_code,
            )
        if scope.sku_id is not None:
            return ReplyScopeV1(
                scope_kind=RuleScopeKind.SKU,
                tenant_id=scope.tenant_id,
                platform=scope.platform,
                store_code=scope.store_code,
                product_id=scope.product_id,
                sku_id=scope.sku_id,
            )
        return ReplyScopeV1(
            scope_kind=RuleScopeKind.PRODUCT,
            tenant_id=scope.tenant_id,
            platform=scope.platform,
            store_code=scope.store_code,
            product_id=scope.product_id,
        )

    @staticmethod
    def _rag_evidence_scope(
        source: Mapping[str, Any], scope: FrozenChatContext
    ) -> ReplyScopeV1 | None:
        product_id = source.get("product_id")
        sku_id = source.get("sku_id")
        if sku_id is not None:
            if product_id != scope.product_id or sku_id != scope.sku_id:
                return None
            return ReplyScopeV1(
                scope_kind=RuleScopeKind.SKU,
                tenant_id=scope.tenant_id,
                platform=scope.platform,
                store_code=scope.store_code,
                product_id=scope.product_id,
                sku_id=scope.sku_id,
            )
        if product_id is not None:
            if product_id != scope.product_id:
                return None
            return ReplyScopeV1(
                scope_kind=RuleScopeKind.PRODUCT,
                tenant_id=scope.tenant_id,
                platform=scope.platform,
                store_code=scope.store_code,
                product_id=scope.product_id,
            )
        return ReplyScopeV1(
            scope_kind=RuleScopeKind.STORE,
            tenant_id=scope.tenant_id,
            platform=scope.platform,
            store_code=scope.store_code,
        )

    def _split(
        self,
        customer_message: str,
        envelope: ReplyTurnEnvelopeV1,
        scope: FrozenChatContext,
    ) -> tuple[tuple[_Fragment, ...], str | None]:
        if _UNRESOLVED_REFERENCE.search(customer_message):
            return (), "SUB_QUESTION_UNRESOLVED_REFERENCE"
        reference_blocker = self._reference_blocker(customer_message, scope)
        if reference_blocker:
            return (), reference_blocker

        raw_ranges: list[tuple[str, int, int]] = []
        for message in envelope.messages:
            for start, end in self._delimiter_ranges(
                customer_message, message.range_start, message.range_end, _HARD_DELIMITERS
            ):
                comma_ranges = self._delimiter_ranges(
                    customer_message, start, end, _COMMA_DELIMITERS
                )
                if len(comma_ranges) > 1:
                    comma_intents = [
                        self._detect_intents(customer_message[item_start:item_end])
                        for item_start, item_end in comma_ranges
                    ]
                    if (
                        any(len(item) != 1 for item in comma_intents)
                        or len({item[0] for item in comma_intents}) != len(comma_intents)
                    ):
                        return (), "SUB_QUESTION_COMMA_SPLIT_AMBIGUOUS"
                    selected = comma_ranges
                else:
                    selected = [(start, end)]
                raw_ranges.extend((message.message_id, item[0], item[1]) for item in selected)

        if not raw_ranges:
            return (), "SUB_QUESTION_EMPTY"
        if len(raw_ranges) > 8:
            return (), "SUB_QUESTION_LIMIT_EXCEEDED"

        fragments: list[_Fragment] = []
        for ordinal, (message_id, start, end) in enumerate(raw_ranges, start=1):
            content = customer_message[start:end]
            intents = self._detect_intents(content)
            if len(intents) > 1:
                return tuple(fragments), "SUB_QUESTION_MULTIPLE_INTENTS"
            intent = intents[0] if intents else "GENERAL"
            fragments.append(
                _Fragment(
                    ordinal=ordinal,
                    message_id=message_id,
                    start=start,
                    end=end,
                    content_sha256=text_sha256(content),
                    intent=intent,
                )
            )
        if not self._coverage_is_exact(customer_message, fragments):
            return tuple(fragments), "SUB_QUESTION_RANGE_COVERAGE_INVALID"
        return tuple(fragments), None

    @staticmethod
    def _delimiter_ranges(
        text: str,
        start: int,
        end: int,
        delimiters: frozenset[str],
    ) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        cursor = start
        for offset in range(start, end):
            if text[offset] in delimiters:
                ReplyRouter._append_trimmed_range(text, cursor, offset + 1, ranges)
                cursor = offset + 1
        ReplyRouter._append_trimmed_range(text, cursor, end, ranges)
        return ranges

    @staticmethod
    def _append_trimmed_range(
        text: str, start: int, end: int, ranges: list[tuple[int, int]]
    ) -> None:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            ranges.append((start, end))

    @staticmethod
    def _detect_intents(content: str) -> tuple[str, ...]:
        return tuple(
            name
            for name, patterns in _INTENT_PATTERNS
            if any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns)
        )

    @staticmethod
    def _reference_blocker(customer_message: str, scope: FrozenChatContext) -> str | None:
        sku_references = {item.group(0).upper() for item in _SKU_REFERENCE.finditer(customer_message)}
        product_references = {
            item.group(0).upper() for item in _PRODUCT_REFERENCE.finditer(customer_message)
        }
        if len(sku_references) > 1 or len(product_references) > 1:
            return "SUB_QUESTION_MULTIPLE_SCOPE_REFERENCES"
        if sku_references and (
            scope.sku_id is None or next(iter(sku_references)) != scope.sku_id.upper()
        ):
            return "SUB_QUESTION_SKU_SCOPE_MISMATCH"
        if product_references and next(iter(product_references)) != scope.product_id.upper():
            return "SUB_QUESTION_PRODUCT_SCOPE_MISMATCH"
        return None

    @staticmethod
    def _coverage_is_exact(customer_message: str, fragments: list[_Fragment]) -> bool:
        cursor = 0
        for fragment in fragments:
            if fragment.start < cursor:
                return False
            if customer_message[cursor : fragment.start].strip():
                return False
            cursor = fragment.end
        return not customer_message[cursor:].strip()

    def _match_rule(
        self,
        source_text: str,
        scope: FrozenChatContext,
        rules: tuple[ReplyRuleV1, ...],
    ) -> tuple[_RuleMatch | None, str | None]:
        normalized_source = self._normalize_for_match(source_text)
        candidates: list[tuple[int, int, ReplyRuleV1]] = []
        now = self._clock().astimezone(timezone.utc)
        for rule in rules:
            if not self._rule_in_scope(rule, scope):
                continue
            if rule.status is not ReplyRuleStatus.PUBLISHED:
                continue
            if rule.effective_from.astimezone(timezone.utc) > now:
                continue
            if rule.effective_to is not None and rule.effective_to.astimezone(timezone.utc) <= now:
                continue
            aliases = (rule.canonical_question, *rule.aliases)
            matched_lengths = [
                len(normalized)
                for alias in aliases
                if (normalized := self._normalize_for_match(alias))
                and normalized in normalized_source
            ]
            if matched_lengths:
                candidates.append(
                    (
                        _SCOPE_PRIORITY[rule.scope.scope_kind.value],
                        max(matched_lengths),
                        rule,
                    )
                )
        if not candidates:
            return None, None
        best_priority = max(item[0] for item in candidates)
        scoped = [item for item in candidates if item[0] == best_priority]
        best_length = max(item[1] for item in scoped)
        best = [item for item in scoped if item[1] == best_length]
        identities = {(item[2].rule_id, item[2].rule_version) for item in best}
        if len(identities) != 1:
            return None, "FIXED_RULE_MATCH_AMBIGUOUS"
        rule = best[0][2]
        return _RuleMatch(rule=rule, alias_length=best_length), None

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        normalized = "".join(unicodedata.normalize("NFKC", value).split()).casefold()
        for source, target in _APPROVED_SYNONYMS:
            normalized = normalized.replace(source.casefold(), target.casefold())
        return normalized

    @staticmethod
    def _rule_in_scope(rule: ReplyRuleV1, scope: FrozenChatContext) -> bool:
        rule_scope = rule.scope
        if rule_scope.tenant_id != scope.tenant_id or rule_scope.platform != scope.platform:
            return False
        kind = rule_scope.scope_kind.value
        if kind in {"STORE", "PRODUCT", "SKU"} and rule_scope.store_code != scope.store_code:
            return False
        if kind in {"PRODUCT", "SKU"} and rule_scope.product_id != scope.product_id:
            return False
        if kind == "SKU" and rule_scope.sku_id != scope.sku_id:
            return False
        return True

    def _render_rule(
        self, rule: ReplyRuleV1, scope: FrozenChatContext
    ) -> tuple[str | None, list[str], str | None]:
        if rule.action is ReplyAction.ASK_CLARIFY:
            if (
                not rule.required_context_fields
                or not set(rule.required_context_fields).issubset(
                    _ALLOWED_CLARIFY_FIELDS
                )
            ):
                return None, [], "FIXED_RULE_CLARIFICATION_FIELD_INVALID"
            if not any(
                self._clarification_field_missing(field, scope)
                for field in rule.required_context_fields
            ):
                return None, [], "FIXED_RULE_CLARIFICATION_NOT_NEEDED"
            missing: list[str] = []
        else:
            missing = [
                field
                for field in rule.required_context_fields
                if self._context_value(field, scope) is None
            ]
            if missing:
                return None, missing, "FIXED_RULE_REQUIRED_CONTEXT_MISSING"
        try:
            parsed_template = tuple(string.Formatter().parse(rule.fixed_reply))
        except ValueError:
            return None, [], "FIXED_RULE_TEMPLATE_INVALID"
        if any(
            field_name is not None and (format_spec or conversion)
            for _, field_name, format_spec, conversion in parsed_template
        ):
            return None, [], "FIXED_RULE_TEMPLATE_INVALID"
        placeholders = {
            field_name
            for _, field_name, _, _ in parsed_template
            if field_name is not None
        }
        if not placeholders.issubset(set(rule.variable_names)):
            return None, [], "FIXED_RULE_TEMPLATE_VARIABLE_UNDECLARED"
        variables: dict[str, str] = {}
        for name in placeholders:
            value = self._context_value(name, scope)
            if value is None:
                missing.append(name)
            else:
                variables[name] = value
        if missing:
            return None, list(dict.fromkeys(missing)), "FIXED_RULE_VARIABLE_MISSING"
        try:
            rendered = rule.fixed_reply.format_map(variables).strip()
        except (KeyError, ValueError):
            return None, [], "FIXED_RULE_TEMPLATE_INVALID"
        if not rendered or len(rendered) > 8_000:
            return None, [], "FIXED_RULE_REPLY_INVALID"
        normalized = self._normalize_for_match(rendered)
        if any(
            self._normalize_for_match(claim) in normalized
            for claim in rule.prohibited_claims
        ):
            return None, [], "FIXED_RULE_PROHIBITED_CLAIM"
        return rendered, [], None

    @staticmethod
    def _context_value(field: str, scope: FrozenChatContext) -> str | None:
        direct = {
            "tenant_id": scope.tenant_id,
            "platform": scope.platform,
            "store_code": scope.store_code,
            "product_id": scope.product_id,
            "sku_id": scope.sku_id,
        }
        if field in direct:
            return direct[field]
        product = scope.verified_product
        if field == "verified_product":
            return "present" if product is not None else None
        if field in {"product_name", "verified_product.product_name"}:
            return product.product_name if product and product.product_name else None
        attribute_name = field
        prefix = "verified_product.attributes."
        if field.startswith(prefix):
            attribute_name = field[len(prefix) :]
        if attribute_name in {
            "particle_count",
            "finished_size",
            "material",
            "ship_origin",
        }:
            if product is None:
                return None
            value = product.attributes.get(attribute_name)
            return value if value and value.strip() else None
        return None

    @staticmethod
    def _clarification_field_missing(
        field: str, scope: FrozenChatContext
    ) -> bool:
        if field == "product_id":
            return scope.product_id.startswith("__STORE_LEVEL_")
        if field == "sku_id":
            return scope.sku_id is None
        return True

    def _rag_context(
        self,
        scope: FrozenChatContext,
        envelope: ReplyTurnEnvelopeV1,
        customer_message: str,
    ) -> FrozenChatContext | None:
        if len(customer_message) > 2_000:
            return None
        history = (*scope.recent_conversation[-19:], VerifiedConversationEntry(
            message_id=envelope.turn_id,
            sender="customer",
            content=customer_message,
            timestamp=self._clock().astimezone(timezone.utc).isoformat(),
        ))
        return FrozenChatContext.model_validate(
            {
                **scope.model_dump(exclude={"recent_conversation"}),
                "recent_conversation": history,
            }
        )

    @staticmethod
    def _validate_rag_result(
        result: Any, scope: FrozenChatContext
    ) -> tuple[bool, str | None]:
        if not isinstance(result, dict):
            return False, "RAG_RESULT_INVALID"
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip() or len(answer.strip()) > 8_000:
            return False, "RAG_ANSWER_INVALID"
        action = result.get("action")
        risk = result.get("risk_level")
        if action not in {item.value for item in _SUGGEST_ACTIONS}:
            return False, "RAG_ACTION_REQUIRES_MANUAL"
        if risk not in {ReplyRiskLevel.LOW.value, ReplyRiskLevel.MEDIUM.value}:
            return False, "RAG_RISK_REQUIRES_MANUAL"
        warnings = result.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            return False, "RAG_WARNINGS_INVALID"
        if set(warnings) & _RAG_FAILURE_WARNINGS or not set(warnings).issubset(_SAFE_RAG_WARNINGS):
            return False, "RAG_WARNING_REQUIRES_MANUAL"
        required_fields = result.get("required_fields")
        if not isinstance(required_fields, list) or not all(
            isinstance(item, str) for item in required_fields
        ):
            return False, "RAG_REQUIRED_FIELDS_INVALID"
        if len(required_fields) > 32 or any(
            not item or len(item) > 512 for item in required_fields
        ):
            return False, "RAG_REQUIRED_FIELDS_INVALID"
        if action == ReplyAction.ASK_CLARIFY.value:
            if not required_fields or not set(required_fields).issubset(_ALLOWED_CLARIFY_FIELDS):
                return False, "RAG_CLARIFICATION_FIELD_INVALID"
        elif required_fields:
            return False, "RAG_REQUIRED_CONTEXT_MISSING"
        sources = result.get("sources")
        if not isinstance(sources, list):
            return False, "RAG_SOURCES_INVALID"
        if not sources:
            return False, "RAG_SOURCE_MISSING"
        if len(sources) > 32:
            return False, "RAG_SOURCE_LIMIT_EXCEEDED"
        source_ids: set[str] = set()
        controlled_answer_kinds: list[str | None] = []
        for source in sources:
            if not isinstance(source, dict):
                return False, "RAG_SOURCE_INVALID"
            chunk_id = source.get("chunk_id")
            if (
                not isinstance(chunk_id, str)
                or not chunk_id.strip()
                or chunk_id != chunk_id.strip()
                or len(chunk_id.strip()) > 255
            ):
                return False, "RAG_SOURCE_ID_MISSING"
            if chunk_id.strip() in source_ids:
                return False, "RAG_SOURCE_ID_DUPLICATED"
            source_ids.add(chunk_id.strip())
            controlled_answer_kind = source.get("controlled_answer_kind")
            if controlled_answer_kind not in {
                None,
                _REVIEWED_APPROXIMATE_CONTROL_KIND,
            }:
                return False, "RAG_CONTROLLED_ANSWER_KIND_INVALID"
            controlled_answer_kinds.append(controlled_answer_kind)
            product_id = source.get("product_id")
            sku_id = source.get("sku_id")
            if product_id is not None and product_id != scope.product_id:
                return False, "RAG_SOURCE_PRODUCT_SCOPE_MISMATCH"
            if sku_id is not None and sku_id != scope.sku_id:
                return False, "RAG_SOURCE_SKU_SCOPE_MISMATCH"
        if (
            not scope.product_id.startswith("__STORE_LEVEL_")
            and not any(source.get("product_id") == scope.product_id for source in sources)
        ):
            return False, "RAG_SOURCE_PRODUCT_SCOPE_UNPROVEN"
        is_reviewed_approximate = (
            action == ReplyAction.CONTROLLED_ANSWER.value
            and risk == ReplyRiskLevel.MEDIUM.value
            and all(
                item == _REVIEWED_APPROXIMATE_CONTROL_KIND
                for item in controlled_answer_kinds
            )
        )
        if any(controlled_answer_kinds) and not is_reviewed_approximate:
            return False, "RAG_CONTROLLED_ANSWER_KIND_MISMATCH"
        return True, None

    @staticmethod
    def _sub_question_id(
        envelope: ReplyTurnEnvelopeV1, fragment: _Fragment
    ) -> str:
        identity = text_sha256(
            f"{envelope.turn_id}\0{fragment.start}\0{fragment.end}"
        )[:24]
        return f"sub-question-{identity}"

    def _plan(
        self,
        envelope: ReplyTurnEnvelopeV1,
        fragments: tuple[_Fragment, ...],
        *,
        routes: tuple[SubQuestionRoute, ...],
        blocker: str | None,
    ) -> SubQuestionPlanV1:
        ambiguous = blocker is not None
        questions = tuple(
            SubQuestionV1(
                sub_question_id=self._sub_question_id(envelope, fragment),
                ordinal=fragment.ordinal,
                source_ranges=(
                    SourceTextRangeV1(
                        message_id=fragment.message_id,
                        aggregate_start=fragment.start,
                        aggregate_end=fragment.end,
                    ),
                ),
                source_content_sha256=fragment.content_sha256,
                intent=fragment.intent,
                route=(SubQuestionRoute.MANUAL if ambiguous else routes[index]),
                blocker_codes=((blocker,) if ambiguous else ()),
            )
            for index, fragment in enumerate(fragments)
        )
        split_status = (
            SplitStatus.AMBIGUOUS
            if ambiguous
            else SplitStatus.SINGLE
            if len(questions) == 1
            else SplitStatus.SPLIT_CONFIRMED
        )
        return SubQuestionPlanV1(
            schema_version="sub-question-plan.v1",
            turn_id=envelope.turn_id,
            aggregate_content_sha256=envelope.aggregate_content_sha256,
            split_status=split_status,
            sub_questions=questions,
            blocker_codes=((blocker,) if blocker else ()),
        )

    @staticmethod
    def _manual(
        blocker: str,
        *,
        plan: SubQuestionPlanV1 | None = None,
        required_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        safe_blocker = re.sub(r"[^A-Z0-9_]", "_", blocker.upper())[:96]
        trace = ReplyRouterTraceV1(
            sub_question_plan=plan,
            blocker_codes=(safe_blocker,),
        )
        return {
            "answer": "Manual customer-service review is required.",
            "action": ReplyAction.TRANSFER_HUMAN.value,
            "risk_level": ReplyRiskLevel.HIGH.value,
            "sources": [],
            "warnings": [
                "REPLY_ROUTER_MANUAL_REQUIRED",
                f"ROUTER_BLOCKED_{safe_blocker}",
            ],
            "required_fields": required_fields or [],
            "reply_router_trace": trace.model_dump(mode="json"),
        }
