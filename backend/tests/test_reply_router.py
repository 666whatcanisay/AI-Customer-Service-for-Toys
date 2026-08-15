from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.models.chat import FrozenChatContext, VerifiedProductContext
from app.reply_router.contracts import (
    ReplyEvidenceBundleV1,
    ReplyRulePublicationV1,
    ReplyRuleV1,
    canonical_sha256,
    text_sha256,
)
from app.reply_router.publication_store import ReplyRuleSnapshotStore
from app.reply_router.router import ReplyRouter


NOW = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)


def _scope(
    *,
    sku_id: str | None = None,
    attributes: dict[str, str] | None = None,
) -> FrozenChatContext:
    product = None
    if attributes is not None:
        product = VerifiedProductContext(
            product_reference="PRODUCT-SYNTHETIC",
            product_name="合成积木",
            sku_reference=sku_id,
            attributes=attributes,
        )
    return FrozenChatContext(
        tenant_id="TENANT-SYNTHETIC",
        platform="pdd",
        store_code="STORE-SYNTHETIC",
        product_id="PRODUCT-SYNTHETIC",
        sku_id=sku_id,
        verified_product=product,
    )


def _turn(message: str, *, turn_id: str = "turn-synthetic-001") -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    cursor = 0
    for ordinal, content in enumerate(message.split("\n"), start=1):
        end = cursor + len(content)
        messages.append(
            {
                "message_id": f"message-{ordinal}",
                "content_sha256": text_sha256(content),
                "range_start": cursor,
                "range_end": end,
            }
        )
        cursor = end + 1
    return {
        "ai_cs_reply_turn": {
            "schema_version": "ai-cs-reply-turn.v1",
            "turn_id": turn_id,
            "aggregate_content_sha256": text_sha256(message),
            "index_unit": "UNICODE_CODE_POINT",
            "aggregation_separator": "\n",
            "messages": messages,
        }
    }


def _rule(
    rule_id: str,
    *,
    scope_kind: str = "PRODUCT",
    alias: str = "什么材质",
    reply: str = "材质为ABS塑料。",
    variable_names: list[str] | None = None,
    required_fields: list[str] | None = None,
    sku_id: str | None = None,
    action: str = "DIRECT_ANSWER",
    risk: str = "LOW",
    allow_auto_candidate: bool = True,
    prohibited_claims: list[str] | None = None,
) -> ReplyRuleV1:
    scope_payload: dict[str, Any] = {
        "scope_kind": scope_kind,
        "tenant_id": "TENANT-SYNTHETIC",
        "platform": "pdd",
        "store_code": None,
        "product_id": None,
        "sku_id": None,
    }
    if scope_kind in {"STORE", "PRODUCT", "SKU"}:
        scope_payload["store_code"] = "STORE-SYNTHETIC"
    if scope_kind in {"PRODUCT", "SKU"}:
        scope_payload["product_id"] = "PRODUCT-SYNTHETIC"
    if scope_kind == "SKU":
        scope_payload["sku_id"] = sku_id or "SKU-SYNTHETIC"
    base = {
        "schema_version": "reply-rule.v1",
        "rule_id": rule_id,
        "rule_version": 1,
        "scope": scope_payload,
        "canonical_question": alias,
        "aliases": [alias],
        "fixed_reply": reply,
        "variable_names": variable_names or [],
        "action": action,
        "risk_level": risk,
        "required_context_fields": required_fields or ["product_id"],
        "prohibited_claims": (
            ["绝对安全"] if prohibited_claims is None else prohibited_claims
        ),
        "allow_auto_candidate": allow_auto_candidate,
        "source_materials": [
            {
                "material_id": f"KMT-{rule_id}",
                "revision": 1,
                "content_sha256": "d" * 64,
                "governance_status": "REVIEWED_VALID",
                "scope": scope_payload,
                "reviewed_by": "operator-synthetic",
                "reviewed_at": "2026-08-13T00:00:00Z",
            }
        ],
        "effective_from": "2026-08-13T00:00:00Z",
        "effective_to": None,
        "status": "PUBLISHED",
        "review": {
            "reviewed_by": "operator-synthetic",
            "reviewed_at": "2026-08-13T00:00:00Z",
            "review_note": "synthetic approval",
        },
    }
    fingerprint = canonical_sha256(
        {
            key: value
            for key, value in base.items()
            if key not in {"status", "review", "source_materials"}
        }
    )
    return ReplyRuleV1.model_validate_json(
        json.dumps({**base, "content_fingerprint": fingerprint}, ensure_ascii=False)
    )


def _publish(store: ReplyRuleSnapshotStore, rules: list[ReplyRuleV1]) -> None:
    base = {
        "schema_version": "reply-rule-publication.v1",
        "publication_id": "publication-synthetic-001",
        "idempotency_key": "publication-synthetic-001",
        "tenant_id": "TENANT-SYNTHETIC",
        "platform": "pdd",
        "snapshot_revision": 1,
        "rules": rules,
        "produced_by": "operator-synthetic",
        "produced_at": "2026-08-13T00:01:00Z",
    }
    fingerprint = canonical_sha256(
        {
            "tenant_id": base["tenant_id"],
            "platform": base["platform"],
            "snapshot_revision": base["snapshot_revision"],
            "rules": [item.model_dump(mode="json") for item in rules],
        }
    )
    store.publish(
        ReplyRulePublicationV1.model_validate_json(
            json.dumps(
                {
                    **base,
                    "rules": [item.model_dump(mode="json") for item in rules],
                    "snapshot_fingerprint": fingerprint,
                },
                ensure_ascii=False,
            )
        )
    )


def _rag_result(
    answer: str = "建议年龄为6岁以上。",
    *,
    action: str = "DIRECT_ANSWER",
    risk: str = "LOW",
    product_id: str | None = "PRODUCT-SYNTHETIC",
    warnings: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "action": action,
        "risk_level": risk,
        "sources": sources
        if sources is not None
        else [
            {
                "source_name": "synthetic-product-faq.md",
                "chunk_id": "chunk-synthetic-001",
                "distance": 0.1,
                "product_id": product_id,
                "sku_id": None,
                "knowledge_version": "a" * 64,
                "source_ids": ["SOURCE-SYNTHETIC-001"],
            }
        ],
        "warnings": warnings
        if warnings is not None
        else ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
        "required_fields": [],
    }


def _router(
    tmp_path: Path,
    rag_provider,
    *,
    rules: list[ReplyRuleV1] | None = None,
) -> ReplyRouter:
    store = ReplyRuleSnapshotStore(tmp_path / "reply-rules")
    if rules is not None:
        _publish(store, rules)
    return ReplyRouter(store, rag_provider, clock=lambda: NOW)


def test_fixed_then_rag_composite_preserves_order_and_complete_turn_context(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, FrozenChatContext]] = []

    def rag(question: str, context: FrozenChatContext) -> dict[str, Any]:
        calls.append((question, context))
        return _rag_result()

    router = _router(tmp_path, rag, rules=[_rule("RULE-MATERIAL")])
    message = "这个积木是什么材质？\n适合几岁？"
    result = router.decide(message, _turn(message), _scope())

    assert result["action"] == "DIRECT_ANSWER"
    assert result["answer"] == "材质为ABS塑料。\n建议年龄为6岁以上。"
    assert calls[0][0] == "适合几岁？"
    assert calls[0][1].recent_conversation[-1].content == message
    trace = result["reply_router_trace"]
    assert trace["origin"] == "COMPOSITE"
    assert trace["sub_question_plan"]["split_status"] == "SPLIT_CONFIRMED"
    assert [item["route"] for item in trace["sub_question_plan"]["sub_questions"]] == [
        "FIXED_RULE",
        "RAG",
    ]
    assert [item["ordinal"] for item in trace["segments"]] == [1, 2]
    assert len({item["sub_question_id"] for item in trace["segments"]}) == 2
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(result["reply_evidence_bundle"], ensure_ascii=False)
    )
    bundle.validate_proposed_content(result["answer"])
    assert result["quality_gate_status"] == "PASS"
    assert bundle.reply_origin.value == "COMPOSITE"
    assert {item.source_type.value for item in bundle.sources} == {
        "FIXED_RULE",
        "RAG_KNOWLEDGE",
    }
    fixed_source = next(
        item for item in bundle.sources if item.source_type.value == "FIXED_RULE"
    )
    assert fixed_source.rule_content_fingerprint
    assert fixed_source.rule_snapshot_revision == 1
    assert fixed_source.rule_snapshot_fingerprint
    assert fixed_source.rule_source_materials[0].material_id == "KMT-RULE-MATERIAL"
    serialized = bundle.model_dump_json()
    assert "这个积木是什么材质" not in serialized
    assert "材质为ABS塑料" not in serialized


def test_fixed_only_never_calls_rag_and_supports_declared_variable(tmp_path: Path) -> None:
    calls: list[str] = []
    router = _router(
        tmp_path,
        lambda question, context: calls.append(question) or _rag_result(),
        rules=[
            _rule(
                "RULE-MATERIAL",
                reply="材质为{material}。",
                variable_names=["material"],
                required_fields=["material"],
            )
        ],
    )
    message = "请问是什么材料？"
    result = router.decide(
        message,
        _turn(message),
        _scope(attributes={"material": "ABS塑料"}),
    )

    assert result["answer"] == "材质为ABS塑料。"
    assert result["reply_router_trace"]["origin"] == "FIXED_RULE"
    assert calls == []


def test_reviewed_medium_fixed_answers_and_clarification_can_pass_quality_gate(
    tmp_path: Path,
) -> None:
    controlled = _router(
        tmp_path / "controlled",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-SAFETY",
                alias="适合几岁",
                reply="建议6岁以上儿童在成人陪同下使用。",
                action="CONTROLLED_ANSWER",
                risk="MEDIUM",
            )
        ],
    )
    controlled_message = "适合几岁？"
    controlled_result = controlled.decide(
        controlled_message, _turn(controlled_message), _scope()
    )
    assert controlled_result["action"] == "CONTROLLED_ANSWER"
    assert controlled_result["quality_gate_status"] == "PASS"

    clarify = _router(
        tmp_path / "clarify",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-ASK-SKU",
                alias="哪个规格",
                reply="请问您选择的是哪个规格？",
                required_fields=["sku_id"],
                action="ASK_CLARIFY",
                risk="MEDIUM",
            )
        ],
    )
    clarify_message = "应该选择哪个规格？"
    clarify_result = clarify.decide(
        clarify_message, _turn(clarify_message), _scope()
    )
    assert clarify_result["action"] == "ASK_CLARIFY"
    assert clarify_result["required_fields"] == ["sku_id"]
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(clarify_result["reply_evidence_bundle"], ensure_ascii=False)
    )
    assert bundle.missing_fields == ("sku_id",)


def test_quality_gate_rejects_non_auto_rule_and_prohibited_commitment(
    tmp_path: Path,
) -> None:
    not_auto = _router(
        tmp_path / "not-auto",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-NOT-AUTO",
                allow_auto_candidate=False,
            )
        ],
    )
    message = "这个商品是什么材质？"
    not_auto_result = not_auto.decide(message, _turn(message), _scope())
    assert not_auto_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_RULE_POLICY_STALE" in not_auto_result["warnings"]

    promise = _router(
        tmp_path / "promise",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-PROMISE",
                reply="保证绝对安全。",
                prohibited_claims=[],
            )
        ],
    )
    promise_result = promise.decide(message, _turn(message), _scope())
    assert promise_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_PROHIBITED_CLAIM" in promise_result["warnings"]


def test_quality_gate_rechecks_rule_snapshot_after_reply_generation(
    tmp_path: Path,
) -> None:
    backing = ReplyRuleSnapshotStore(tmp_path / "reply-rules")
    _publish(backing, [_rule("RULE-MATERIAL")])

    class WithdrawnBeforeQualityGate:
        def __init__(self) -> None:
            self.calls = 0

        def current(self, tenant_id: str, platform: str):
            self.calls += 1
            if self.calls == 1:
                return backing.current(tenant_id, platform)
            return None

    store = WithdrawnBeforeQualityGate()
    router = ReplyRouter(
        store,  # type: ignore[arg-type]
        lambda question, context: pytest.fail("RAG must not be called"),
        clock=lambda: NOW,
    )
    message = "这个商品是什么材质？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_RULE_NOT_CURRENT" in result["warnings"]
    assert store.calls == 2


def test_quality_gate_requires_governed_rag_fingerprint_and_lineage(
    tmp_path: Path,
) -> None:
    missing_fingerprint = _rag_result()
    missing_fingerprint["sources"][0].pop("knowledge_version")
    router = _router(tmp_path / "fingerprint", lambda question, context: missing_fingerprint)
    message = "包装是什么样？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert (
        "ROUTER_BLOCKED_QUALITY_KNOWLEDGE_FINGERPRINT_MISSING"
        in result["warnings"]
    )

    missing_lineage = _rag_result()
    missing_lineage["sources"][0]["source_ids"] = []
    lineage_router = _router(
        tmp_path / "lineage", lambda question, context: missing_lineage
    )
    lineage_result = lineage_router.decide(message, _turn(message), _scope())
    assert lineage_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_KNOWLEDGE_LINEAGE_INVALID" in lineage_result[
        "warnings"
    ]


def test_quality_gate_rejects_medium_rag_and_realtime_fixed_intent(
    tmp_path: Path,
) -> None:
    medium_rag = _router(
        tmp_path / "medium-rag",
        lambda question, context: _rag_result(
            "请在成人陪同下使用。",
            action="CONTROLLED_ANSWER",
            risk="MEDIUM",
        ),
    )
    age_message = "适合几岁？"
    medium_result = medium_rag.decide(
        age_message, _turn(age_message), _scope()
    )
    assert medium_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_RAG_POLICY_REJECTED" in medium_result[
        "warnings"
    ]

    realtime = _router(
        tmp_path / "realtime",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-REALTIME",
                alias="什么时候到",
                reply="请以订单页面信息为准。",
            )
        ],
    )
    realtime_message = "什么时候到？"
    realtime_result = realtime.decide(
        realtime_message, _turn(realtime_message), _scope()
    )
    assert realtime_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_QUALITY_INTENT_REQUIRES_MANUAL" in realtime_result[
        "warnings"
    ]


def test_quality_gate_allows_only_governed_reviewed_approximate_rag(
    tmp_path: Path,
) -> None:
    reviewed = _rag_result(
        "成品长度约40厘米，具体以实物或实际清点为准。",
        action="CONTROLLED_ANSWER",
        risk="MEDIUM",
    )
    reviewed["sources"][0][
        "controlled_answer_kind"
    ] = "REVIEWED_APPROXIMATE_FACT"
    reviewed_router = _router(
        tmp_path / "reviewed-approximate", lambda question, context: reviewed
    )
    message = "成品有多长？"
    reviewed_result = reviewed_router.decide(
        message, _turn(message), _scope()
    )
    assert reviewed_result["action"] == "CONTROLLED_ANSWER"
    assert reviewed_result["risk_level"] == "MEDIUM"
    assert reviewed_result["quality_gate_status"] == "PASS"

    invalid = _rag_result(
        "成品长度约40厘米。",
        action="CONTROLLED_ANSWER",
        risk="MEDIUM",
    )
    invalid["sources"][0]["controlled_answer_kind"] = "UNREVIEWED_ESTIMATE"
    invalid_router = _router(
        tmp_path / "invalid-approximate", lambda question, context: invalid
    )
    invalid_result = invalid_router.decide(message, _turn(message), _scope())
    assert invalid_result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_RAG_CONTROLLED_ANSWER_KIND_INVALID" in invalid_result[
        "warnings"
    ]


def test_legacy_low_risk_approximate_fixed_rule_uses_governed_rag(
    tmp_path: Path,
) -> None:
    rag_result = _rag_result(
        "颗粒数量约1000颗，具体以实物或实际清点为准。",
        action="CONTROLLED_ANSWER",
        risk="MEDIUM",
    )
    rag_result["sources"][0][
        "controlled_answer_kind"
    ] = "REVIEWED_APPROXIMATE_FACT"
    router = _router(
        tmp_path,
        lambda question, context: rag_result,
        rules=[
            _rule(
                "RULE-LEGACY-APPROXIMATE",
                alias="多少颗",
                reply="这款约1000颗。",
            )
        ],
    )
    message = "多少颗？"

    result = router.decide(message, _turn(message), _scope())

    assert result["action"] == "CONTROLLED_ANSWER"
    assert result["risk_level"] == "MEDIUM"
    assert result["reply_router_trace"]["origin"] == "RAG"


def test_low_risk_rag_cannot_hide_an_approximate_numeric_fact(
    tmp_path: Path,
) -> None:
    router = _router(
        tmp_path,
        lambda question, context: _rag_result("这款约1000颗。"),
    )
    message = "多少颗？"

    result = router.decide(message, _turn(message), _scope())

    assert result["action"] == "TRANSFER_HUMAN"
    assert (
        "ROUTER_BLOCKED_QUALITY_APPROXIMATE_FACT_REQUIRES_CONTROLLED"
        in result["warnings"]
    )


def test_tenant_rule_evidence_is_a_valid_ancestor_of_product_scope(
    tmp_path: Path,
) -> None:
    router = _router(
        tmp_path,
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-TENANT-MATERIAL",
                scope_kind="TENANT",
                reply="本店该类商品使用审核材质说明。",
            )
        ],
    )
    message = "这个商品是什么材质？"
    result = router.decide(message, _turn(message), _scope())
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(result["reply_evidence_bundle"], ensure_ascii=False)
    )
    assert bundle.scope.scope_kind.value == "PRODUCT"
    assert bundle.sources[0].scope.scope_kind.value == "TENANT"
    bundle.validate_proposed_content(result["answer"])


def test_clear_unmatched_question_uses_rag(tmp_path: Path) -> None:
    questions: list[str] = []
    router = _router(
        tmp_path,
        lambda question, context: questions.append(question) or _rag_result("盒装。"),
    )
    message = "包装是什么样？"
    result = router.decide(message, _turn(message), _scope())

    assert result["answer"] == "盒装。"
    assert result["reply_router_trace"]["origin"] == "RAG"
    assert questions == [message]


def test_quality_evidence_hash_is_deterministic_for_same_governed_input(
    tmp_path: Path,
) -> None:
    router = _router(tmp_path, lambda question, context: _rag_result("盒装。"))
    message = "包装是什么样？"
    first = router.decide(message, _turn(message), _scope())
    second = router.decide(message, _turn(message), _scope())
    assert first["reply_evidence_bundle"] == second["reply_evidence_bundle"]
    assert first["reply_evidence_bundle"]["bundle_sha256"] == second[
        "reply_evidence_bundle"
    ]["bundle_sha256"]


def test_scope_priority_and_longest_alias_are_deterministic(tmp_path: Path) -> None:
    router = _router(
        tmp_path,
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule("RULE-TENANT", scope_kind="TENANT", alias="材质", reply="租户回答"),
            _rule("RULE-PRODUCT-SHORT", alias="材质", reply="商品短回答"),
            _rule("RULE-PRODUCT-LONG", alias="什么材质", reply="商品长回答"),
            _rule(
                "RULE-SKU",
                scope_kind="SKU",
                alias="材质",
                reply="SKU回答",
                sku_id="SKU-SYNTHETIC",
            ),
        ],
    )
    message = "这个商品是什么材质？"
    result = router.decide(
        message, _turn(message), _scope(sku_id="SKU-SYNTHETIC")
    )
    assert result["answer"] == "SKU回答"

    product_router = _router(
        tmp_path / "product-only",
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule("RULE-PRODUCT-SHORT", alias="材质", reply="商品短回答"),
            _rule("RULE-PRODUCT-LONG", alias="什么材质", reply="商品长回答"),
        ],
    )
    product_result = product_router.decide(message, _turn(message), _scope())
    assert product_result["answer"] == "商品长回答"


def test_tied_fixed_rules_fail_closed_without_rag(tmp_path: Path) -> None:
    calls: list[str] = []
    router = _router(
        tmp_path,
        lambda question, context: calls.append(question) or _rag_result(),
        rules=[
            _rule("RULE-A", alias="什么材质", reply="回答A"),
            _rule("RULE-B", alias="什么材质", reply="回答B"),
        ],
    )
    message = "这个商品是什么材质？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_FIXED_RULE_MATCH_AMBIGUOUS" in result["warnings"]
    assert calls == []


@pytest.mark.parametrize(
    ("message", "blocker"),
    [
        ("材质和尺寸分别是多少？", "SUB_QUESTION_MULTIPLE_INTENTS"),
        ("前者适合几岁？", "SUB_QUESTION_UNRESOLVED_REFERENCE"),
        ("SKU-OTHER是什么材质？", "SUB_QUESTION_SKU_SCOPE_MISMATCH"),
        ("材质，多少钱？", "SUB_QUESTION_COMMA_SPLIT_AMBIGUOUS"),
    ],
)
def test_ambiguous_split_or_scope_reference_routes_whole_turn_to_manual(
    tmp_path: Path, message: str, blocker: str
) -> None:
    calls: list[str] = []
    router = _router(
        tmp_path,
        lambda question, context: calls.append(question) or _rag_result(),
        rules=[_rule("RULE-MATERIAL")],
    )
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert f"ROUTER_BLOCKED_{blocker}" in result["warnings"]
    assert calls == []


def test_missing_or_invalid_turn_envelope_fails_closed_without_rag(tmp_path: Path) -> None:
    calls: list[str] = []
    router = _router(
        tmp_path,
        lambda question, context: calls.append(question) or _rag_result(),
    )
    message = "适合几岁？"
    missing = router.decide(message, {}, _scope())
    invalid_context = _turn(message)
    invalid_context["ai_cs_reply_turn"]["aggregate_content_sha256"] = "0" * 64
    invalid = router.decide(message, invalid_context, _scope())

    assert missing["action"] == invalid["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_REPLY_TURN_ENVELOPE_MISSING" in missing["warnings"]
    assert "ROUTER_BLOCKED_REPLY_TURN_AGGREGATE_HASH_MISMATCH" in invalid["warnings"]
    assert calls == []


def test_fixed_template_missing_context_fails_closed(tmp_path: Path) -> None:
    router = _router(
        tmp_path,
        lambda question, context: pytest.fail("RAG must not be called"),
        rules=[
            _rule(
                "RULE-MATERIAL",
                reply="材质为{material}。",
                variable_names=["material"],
            )
        ],
    )
    message = "是什么材质？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert result["required_fields"] == ["material"]


@pytest.mark.parametrize(
    "rag_result",
    [
        _rag_result(action="REFUSE", risk="HIGH", sources=[]),
        _rag_result(warnings=["RAG_RUNTIME_ERROR"]),
        _rag_result(product_id="PRODUCT-OTHER"),
        _rag_result(product_id=None),
        _rag_result(sources=[]),
        _rag_result(
            sources=[
                {
                    "chunk_id": "chunk-duplicated",
                    "product_id": "PRODUCT-SYNTHETIC",
                    "sku_id": None,
                },
                {
                    "chunk_id": "chunk-duplicated",
                    "product_id": "PRODUCT-SYNTHETIC",
                    "sku_id": None,
                },
            ]
        ),
    ],
)
def test_unsafe_or_unscoped_rag_result_fails_closed(
    tmp_path: Path, rag_result: dict[str, Any]
) -> None:
    router = _router(tmp_path, lambda question, context: rag_result)
    message = "包装是什么样？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert result["risk_level"] == "HIGH"
    assert result["sources"] == []


def test_rag_provider_exception_fails_closed(tmp_path: Path) -> None:
    def unavailable(question: str, context: FrozenChatContext) -> dict[str, Any]:
        raise RuntimeError("synthetic provider failure")

    router = _router(tmp_path, unavailable)
    message = "包装是什么样？"
    result = router.decide(message, _turn(message), _scope())
    assert result["action"] == "TRANSFER_HUMAN"
    assert "ROUTER_BLOCKED_RAG_PROVIDER_UNAVAILABLE" in result["warnings"]


def test_hard_delimiter_split_has_exact_non_overlapping_ranges(tmp_path: Path) -> None:
    answers = iter([_rag_result("回答一。"), _rag_result("回答二。")])
    router = _router(tmp_path, lambda question, context: next(answers))
    message = "包装是什么样？颜色有哪些？"
    result = router.decide(message, _turn(message), _scope())
    plan = result["reply_router_trace"]["sub_question_plan"]
    ranges = [item["source_ranges"][0] for item in plan["sub_questions"]]
    assert [(item["aggregate_start"], item["aggregate_end"]) for item in ranges] == [
        (0, 7),
        (7, 13),
    ]
    assert result["answer"] == "回答一。\n回答二。"
