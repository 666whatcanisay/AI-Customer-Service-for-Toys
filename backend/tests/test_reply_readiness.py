from __future__ import annotations

import json
import runpy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.reply_readiness.contracts import PddReplyReadinessInputV1
from app.reply_readiness.evaluator import (
    ReplyReadinessEvaluator,
    _PublishedRuntimeSnapshot,
)
from app.reply_router.contracts import (
    ReplyRulePublicationV1,
    ReplyRuleV1,
    canonical_sha256,
)
from app.reply_router.publication_store import ReplyRuleSnapshotStore


def _fixed_rule(
    rule_id: str,
    alias: str,
    reply: str,
) -> ReplyRuleV1:
    scope = {
        "scope_kind": "PRODUCT",
        "tenant_id": "TENANT-READINESS",
        "platform": "pdd",
        "store_code": "STORE-READINESS",
        "product_id": "PRODUCT-READINESS",
        "sku_id": None,
    }
    base = {
        "schema_version": "reply-rule.v1",
        "rule_id": rule_id,
        "rule_version": 1,
        "scope": scope,
        "canonical_question": alias,
        "aliases": [alias],
        "fixed_reply": reply,
        "variable_names": [],
        "action": "DIRECT_ANSWER",
        "risk_level": "LOW",
        "required_context_fields": ["product_id"],
        "prohibited_claims": [],
        "allow_auto_candidate": True,
        "source_materials": [{
            "material_id": f"KMT-{rule_id}",
            "revision": 1,
            "content_sha256": "c" * 64,
            "governance_status": "REVIEWED_VALID",
            "scope": scope,
            "reviewed_by": "pytest",
            "reviewed_at": "2026-08-13T00:00:00Z",
        }],
        "effective_from": "2026-08-13T00:00:00Z",
        "effective_to": None,
        "status": "PUBLISHED",
        "review": {
            "reviewed_by": "pytest",
            "reviewed_at": "2026-08-13T00:00:00Z",
            "review_note": "synthetic approval",
        },
    }
    fingerprint = canonical_sha256({
        key: value
        for key, value in base.items()
        if key not in {"status", "review", "source_materials"}
    })
    return ReplyRuleV1.model_validate_json(
        json.dumps({**base, "content_fingerprint": fingerprint}, ensure_ascii=False)
    )


def _publication(
    store: ReplyRuleSnapshotStore,
    rules: tuple[ReplyRuleV1, ...] = (),
) -> ReplyRulePublicationV1:
    base = {
        "schema_version": "reply-rule-publication.v1",
        "publication_id": "publication-readiness-001",
        "idempotency_key": "publication-readiness-001",
        "tenant_id": "TENANT-READINESS",
        "platform": "pdd",
        "snapshot_revision": 1,
        "rules": rules,
        "produced_by": "pytest",
        "produced_at": datetime(2026, 8, 14, tzinfo=timezone.utc),
    }
    fingerprint = canonical_sha256(
        {
            "tenant_id": base["tenant_id"],
            "platform": base["platform"],
            "snapshot_revision": base["snapshot_revision"],
            "rules": [item.model_dump(mode="json") for item in rules],
        }
    )
    publication = ReplyRulePublicationV1.model_validate(
        {**base, "snapshot_fingerprint": fingerprint}
    )
    store.publish(publication)
    return publication


class _PublishedRuntime:
    def __init__(self, snapshots: list[_PublishedRuntimeSnapshot]) -> None:
        self.snapshots = snapshots
        self.snapshot_calls = 0
        self.query_calls = 0

    def snapshot(self, scope, current_fingerprint):
        del scope, current_fingerprint
        index = min(self.snapshot_calls, len(self.snapshots) - 1)
        self.snapshot_calls += 1
        return self.snapshots[index]

    def query(self, question, context):
        del question, context
        self.query_calls += 1
        return {
            "answer": "建议年龄为6岁以上。",
            "action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "sources": [{
                "source_name": "published synthetic knowledge",
                "chunk_id": "chunk-published-001",
                "distance": 0.1,
                "product_id": "PRODUCT-READINESS",
                "sku_id": None,
                "knowledge_version": "a" * 64,
                "source_ids": ["SOURCE-PUBLISHED-001"],
            }],
            "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
            "required_fields": [],
        }


def _runtime_snapshot(
    *,
    collection: str | None = "published-v1",
    status: str = "PUBLISHED",
    knowledge: str | None = "a" * 64,
    model: str = "d" * 64,
) -> _PublishedRuntimeSnapshot:
    return _PublishedRuntimeSnapshot(
        rag_collection_identity=collection,
        knowledge_publication_status=status,
        knowledge_publication_fingerprint=knowledge,
        model_config_identity=model,
    )


def _debug_payload(
    message: str,
    *,
    rule_fingerprint: str | None = None,
    publication_status: str = "PUBLISHED",
    current_fingerprint: str | None = "a" * 64,
    indexed_fingerprint: str | None = "a" * 64,
    active_collection: str | None = "published-v1",
) -> PddReplyReadinessInputV1:
    question = _question("DEBUG-PUBLISHED", "DEBUG", message)
    question_set_base = {
        "baseline_version": "pdd-published-router-debug.v1",
        "questions": [question],
    }
    return PddReplyReadinessInputV1.model_validate_json(json.dumps({
        "schema_version": "pdd-reply-readiness-input.v1",
        "run_id": "DBG-PUBLISHED-001",
        "test_data_mode": True,
        "production_usable": False,
        "allow_auto_send": False,
        "execution_mode": "PUBLISHED_ROUTER_DEBUG",
        "scope": {
            "tenant_id": "TENANT-READINESS",
            "platform": "pdd",
            "store_code": "STORE-READINESS",
            "product_id": "PRODUCT-READINESS",
            "sku_id": None,
        },
        "question_set": {
            "schema_version": "pdd-reply-readiness-question-set.v1",
            **question_set_base,
            "fingerprint": canonical_sha256(question_set_base),
        },
        "router_build_fingerprint": canonical_sha256(
            {"component": "ReplyRouter", "contract": "reply-router.v1"}
        ),
        "reply_rule_snapshot_fingerprint": rule_fingerprint,
        "publication_state": {
            "status": publication_status,
            "current_fingerprint": current_fingerprint,
            "indexed_fingerprint": indexed_fingerprint,
            "active_collection": active_collection,
        },
        "verified_product": {
            "product_reference": "PRODUCT-READINESS",
            "product_name": "合成积木",
            "attributes": {},
        },
    }, ensure_ascii=False))


def _question(
    question_id: str,
    category: str,
    question: str,
    *,
    risk: str = "LOW",
    action: str = "DIRECT_ANSWER",
    facts: list[str] | None = None,
    realtime: bool = False,
    prohibited: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "pdd-reply-readiness-question.v1",
        "question_id": question_id,
        "category": category,
        "canonical_question": question,
        "aliases": [],
        "policy_risk_floor": risk,
        "expected_action": action,
        "required_fact_keys": facts or [],
        "requires_realtime_lookup": realtime,
        "prohibited_claims": prohibited or [],
        "mandatory": True,
    }


QUESTIONS = [
    _question("PDD-GREETING", "GREETING", "你好"),
    _question(
        "PDD-PARTICLE-COUNT",
        "PRODUCT_FACT",
        "这款有多少颗粒",
        facts=["particle_count"],
    ),
    _question(
        "PDD-FINISHED-SIZE",
        "PRODUCT_FACT",
        "拼好后多大",
        facts=["finished_size"],
    ),
    _question(
        "PDD-INVENTORY",
        "REALTIME_ORDER",
        "现在有货吗",
        risk="HIGH",
        action="REQUIRE_LOOKUP",
        realtime=True,
    ),
    _question(
        "PDD-AUTHENTICITY",
        "AUTHENTICITY",
        "是正品吗",
        risk="HIGH",
        action="TRANSFER_HUMAN",
        facts=["authenticity_evidence"],
        prohibited=["本店所有产品均为正品", "保证正品"],
    ),
]


def _payload(
    publication: ReplyRulePublicationV1,
    *,
    records: list[dict[str, str]],
    run_id: str = "RRN-SYNTHETIC-001",
) -> PddReplyReadinessInputV1:
    question_set_base = {
        "baseline_version": "pdd-common-questions.v1",
        "questions": QUESTIONS,
    }
    question_set = {
        "schema_version": "pdd-reply-readiness-question-set.v1",
        **question_set_base,
        "fingerprint": canonical_sha256(question_set_base),
    }
    analysis = json.dumps(
        {"数据记录": records}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return PddReplyReadinessInputV1.model_validate_json(
        json.dumps(
            {
                "schema_version": "pdd-reply-readiness-input.v1",
                "run_id": run_id,
                "test_data_mode": True,
                "production_usable": False,
                "allow_auto_send": False,
                "scope": {
                    "tenant_id": "TENANT-READINESS",
                    "platform": "pdd",
                    "store_code": "STORE-READINESS",
                    "product_id": "PRODUCT-READINESS",
                    "sku_id": "SKU-READINESS",
                },
                "question_set": question_set,
                "knowledge_snapshot": {
                    "material_id": "KMT-READINESS",
                    "revision": 2,
                    "content_hash": "sha256:" + "d" * 64,
                    "material_status": "RECOGNIZED",
                    "template_type": "PRODUCT_KNOWLEDGE",
                    "analysis_text": analysis,
                },
                "reply_rule_snapshot_revision": publication.snapshot_revision,
                "reply_rule_snapshot_fingerprint": publication.snapshot_fingerprint,
                "router_build_fingerprint": canonical_sha256(
                    {"component": "ReplyRouter", "contract": "reply-router.v1"}
                ),
                "sandbox_vector_identity": f"in-memory-replay:{run_id}",
            },
            ensure_ascii=False,
        )
    )


def _source(
    material_id: str,
    template_type: str,
    records: list[dict[str, str]],
    *,
    revision: int = 1,
    sku_id: str | None = None,
    status: str = "ANALYZED",
) -> dict[str, object]:
    return {
        "material_id": material_id,
        "revision": revision,
        "content_hash": "sha256:" + canonical_sha256({"material_id": material_id, "revision": revision}),
        "material_status": status,
        "template_type": template_type,
        "store_code": "STORE-READINESS",
        "product_id": "PRODUCT-READINESS",
        "sku_id": sku_id,
        "analysis_text": json.dumps({"数据记录": records}, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    }


def _payload_with_sources(
    publication: ReplyRulePublicationV1,
    sources: list[dict[str, object]],
    *,
    questions: list[dict[str, object]] | None = None,
    run_id: str = "RRN-SYNTHETIC-MULTI",
) -> PddReplyReadinessInputV1:
    payload = _payload(publication, records=[], run_id=run_id).model_dump(mode="json")
    payload["knowledge_snapshot"] = None
    payload["knowledge_sources"] = sources
    if questions is not None:
        question_set_base = {
            "baseline_version": "pdd-common-questions.v1",
            "questions": questions,
        }
        payload["question_set"] = {
            "schema_version": "pdd-reply-readiness-question-set.v1",
            **question_set_base,
            "fingerprint": canonical_sha256(question_set_base),
        }
    return PddReplyReadinessInputV1.model_validate_json(json.dumps(payload, ensure_ascii=False))


def _items(result) -> dict[str, object]:
    return {item.question_id: item for item in result.items}


def test_complete_consistent_facts_lower_only_eligible_questions(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    evaluator = ReplyReadinessEvaluator(store)

    result = evaluator.evaluate(
        _payload(publication, records=[{"颗粒数量": "1200颗", "成品尺寸": "40cm"}])
    )
    items = _items(result)

    assert items["PDD-GREETING"].effective_risk == "LOW"
    assert items["PDD-PARTICLE-COUNT"].effective_risk == "LOW"
    assert items["PDD-FINISHED-SIZE"].effective_risk == "LOW"
    assert items["PDD-PARTICLE-COUNT"].evidence_bundle_sha256
    assert items["PDD-FINISHED-SIZE"].evidence_bundle_sha256
    assert items["PDD-INVENTORY"].effective_risk == "HIGH"
    assert items["PDD-INVENTORY"].action == "TRANSFER_HUMAN"
    assert items["PDD-AUTHENTICITY"].effective_risk == "HIGH"
    assert "全部正品" not in items["PDD-AUTHENTICITY"].answer_preview
    assert result.result_sha256 == canonical_sha256(
        result.model_dump(mode="json", exclude={"result_sha256"})
    )


@pytest.mark.parametrize(
    ("records", "question_id", "blocker"),
    [
        ([{"成品尺寸": "30cm"}, {"成品尺寸": "40cm"}], "PDD-FINISHED-SIZE", "FACT_CONFLICT_FINISHED_SIZE"),
        ([{"颗粒数量": "估测1200颗"}], "PDD-PARTICLE-COUNT", "FACT_ESTIMATED_PARTICLE_COUNT"),
    ],
)
def test_conflicting_or_estimated_facts_remain_high(
    tmp_path: Path,
    records: list[dict[str, str]],
    question_id: str,
    blocker: str,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    result = ReplyReadinessEvaluator(store).evaluate(
        _payload(publication, records=records)
    )
    item = _items(result)[question_id]

    assert item.effective_risk == "HIGH"
    assert item.action == "TRANSFER_HUMAN"
    assert blocker in item.blocker_codes


def test_reviewed_approximate_fact_is_a_controlled_medium_answer(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    source = _source(
        "KMT-REVIEWED-APPROXIMATE",
        "PRODUCT_KNOWLEDGE",
        [{
            "颗粒数量": "约1000颗",
            "资料来源": "脱敏PDD记录；sha256:267a15bd54208388cbfa01718052e16f400aef4d2da1b68be5f30531bbbe3d24；DOCX:image6.png",
            "来源日期": "2026-08-14",
            "是否人工确认": "是",
            "备注": "约数已审核，仅允许近似回答",
        }],
        status="APPROVED_FOR_ANALYSIS",
    )

    result = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, [source])
    )
    item = _items(result)["PDD-PARTICLE-COUNT"]

    assert item.effective_risk == "MEDIUM"
    assert item.action == "CONTROLLED_ANSWER"
    assert "约1000颗" in item.answer_preview
    assert "具体以实物或实际清点为准" in item.answer_preview
    assert item.blocker_codes == []
    assert item.citation_ids == ["material:KMT-REVIEWED-APPROXIMATE:v1"]


@pytest.mark.parametrize(
    ("status", "confirmation", "source", "note"),
    [
        ("RECOGNIZED", "是", "sha256:267a15bd54208388cbfa01718052e16f400aef4d2da1b68be5f30531bbbe3d24", "约数已审核"),
        ("APPROVED_FOR_ANALYSIS", "否", "sha256:267a15bd54208388cbfa01718052e16f400aef4d2da1b68be5f30531bbbe3d24", "约数已审核"),
        ("APPROVED_FOR_ANALYSIS", "是", "PDD记录", "约数已审核"),
        ("APPROVED_FOR_ANALYSIS", "是", "sha256:267a15bd54208388cbfa01718052e16f400aef4d2da1b68be5f30531bbbe3d24", "普通备注"),
        ("APPROVED_FOR_ANALYSIS", "是", f"sha256:{'a' * 64}", "约数已审核"),
    ],
)
def test_approximate_fact_without_complete_governance_stays_high(
    tmp_path: Path,
    status: str,
    confirmation: str,
    source: str,
    note: str,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    material = _source(
        "KMT-UNVERIFIED-APPROXIMATE",
        "PRODUCT_KNOWLEDGE",
        [{
            "颗粒数量": "约1000颗",
            "资料来源": source,
            "来源日期": "2026-08-14",
            "是否人工确认": confirmation,
            "备注": note,
        }],
        status=status,
    )

    item = _items(ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, [material])
    ))["PDD-PARTICLE-COUNT"]

    assert item.effective_risk == "HIGH"
    assert item.action == "TRANSFER_HUMAN"
    assert "FACT_ESTIMATED_PARTICLE_COUNT" in item.blocker_codes


def test_rule_snapshot_drift_fails_the_entire_run(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    payload = _payload(publication, records=[])
    payload = payload.model_copy(update={"reply_rule_snapshot_fingerprint": "f" * 64})

    with pytest.raises(ValueError, match="snapshot drifted"):
        ReplyReadinessEvaluator(store).evaluate(payload)


def test_internal_http_route_accepts_the_strict_json_contract(api_client, tmp_path: Path) -> None:
    client, _ = api_client
    store = ReplyRuleSnapshotStore(tmp_path / "readiness-snapshots")
    publication = _publication(store)
    payload = _payload(
        publication,
        records=[{"颗粒数量": "1200颗", "成品尺寸": "40cm"}],
        run_id="RRN-SYNTHETIC-HTTP",
    )
    client.app.state.reply_readiness_evaluator = ReplyReadinessEvaluator(store)
    try:
        response = client.post(
            "/api/admin/ai/reply-readiness/evaluate",
            json=payload.model_dump(mode="json"),
        )
    finally:
        delattr(client.app.state, "reply_readiness_evaluator")

    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == "RRN-SYNTHETIC-HTTP"
    assert len(response.json()["items"]) == len(QUESTIONS)


def test_multi_source_facts_faq_and_safety_are_question_scoped(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    questions = [
        _question("PDD-IMAGE-MATCH", "PRODUCT_FACT", "收到的和图片一样吗", risk="MEDIUM", action="CONTROLLED_ANSWER", facts=["image_match_policy"]),
        _question("PDD-COURIER", "FULFILLMENT", "发什么快递", risk="MEDIUM", action="CONTROLLED_ANSWER", facts=["courier_policy"]),
        _question("PDD-STEALTH-PACKAGING", "FULFILLMENT", "可以隐私发货吗", risk="MEDIUM", action="CONTROLLED_ANSWER", facts=["stealth_packaging"]),
        _question("PDD-AUTHENTICITY", "AUTHENTICITY", "是正品吗", risk="HIGH", action="TRANSFER_HUMAN", facts=["authenticity_evidence"]),
        _question("PDD-PACKAGING", "PRODUCT_FACT", "是什么包装", facts=["package_contents"]),
        _question("PDD-INSTALLATION", "PRODUCT_USAGE", "怎么安装", risk="MEDIUM", action="CONTROLLED_ANSWER", facts=["installation"]),
        _question("PDD-PARTICLE-COUNT", "PRODUCT_FACT", "这款有多少颗粒", facts=["particle_count"]),
        _question("PDD-SAFETY-TIP", "PRODUCT_USAGE", "使用时要注意什么"),
    ]
    sources = [
        _source("KMT-PRODUCT", "PRODUCT_KNOWLEDGE", [{
            "图片一致性说明": "展示图为同款实拍，批次色差以实物为准",
            "快递选择策略": "由仓库按地区选择可用快递",
            "隐私包装": "使用无商品名称外箱",
            "品牌授权证据": "授权书编号 SYNTHETIC-001",
            "安装方式": "按说明书步骤拼装",
            "颗粒数量": "1200颗",
        }]),
        _source("KMT-FAQ-PACK", "FAQ", [{
            "关联问题ID": "PDD-PACKAGING",
            "客户常问问题": "是什么包装",
            "标准回答": "亲，这款使用彩盒包装。",
            "风险等级": "低",
            "是否需要人工确认": "否",
        }]),
        _source("KMT-SAFETY-INSTALL", "SAFETY_RULE", [{
            "关联问题ID": "PDD-INSTALLATION",
            "安全提醒": "请由成人陪同安装。",
            "风险等级": "中",
            "禁止承诺内容": "无需成人看护",
        }, {
            "关联问题ID": "PDD-SAFETY-TIP",
            "安全提醒": "请按说明书安全使用。",
            "风险等级": "低",
            "禁止承诺内容": "无需成人看护",
        }]),
        _source("KMT-FAQ-UNRELATED", "FAQ", [{
            "关联问题ID": "PDD-COURIER",
            "标准回答": "亲，快递按仓库规则安排。",
            "风险等级": "中",
        }]),
    ]
    result = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, sources, questions=questions)
    )
    items = _items(result)

    for question_id in ["PDD-IMAGE-MATCH", "PDD-COURIER", "PDD-STEALTH-PACKAGING"]:
        assert items[question_id].missing_fact_keys == []
    assert items["PDD-AUTHENTICITY"].effective_risk == "HIGH"
    assert items["PDD-AUTHENTICITY"].missing_fact_keys == []
    assert items["PDD-PACKAGING"].effective_risk == "LOW"
    assert items["PDD-PACKAGING"].answer_preview == "亲，这款使用彩盒包装。"
    assert items["PDD-PACKAGING"].citation_ids == ["material:KMT-FAQ-PACK:v1"]
    assert items["PDD-SAFETY-TIP"].effective_risk == "LOW"
    assert items["PDD-SAFETY-TIP"].answer_preview == "请按说明书安全使用。"
    assert items["PDD-SAFETY-TIP"].citation_ids == ["material:KMT-SAFETY-INSTALL:v1"]
    assert items["PDD-PARTICLE-COUNT"].citation_ids == ["material:KMT-PRODUCT:v1"]


def test_multi_source_conflict_and_sku_difference_do_not_fake_exact_values(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    sources = [
        _source("KMT-PRODUCT", "PRODUCT_KNOWLEDGE", [{"成品尺寸": "30cm"}]),
        _source("KMT-SKU", "PRODUCT_KNOWLEDGE", [{"成品尺寸": "40cm"}], sku_id="SKU-READINESS"),
        _source("KMT-DIFFERENCE", "SKU_DIFFERENCE", [{"数量区别": "比基础款多200颗", "尺寸区别": "比基础款大10cm"}], sku_id="SKU-READINESS"),
    ]
    result = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, sources)
    )
    items = _items(result)

    assert items["PDD-FINISHED-SIZE"].effective_risk == "HIGH"
    assert "FACT_CONFLICT_FINISHED_SIZE" in items["PDD-FINISHED-SIZE"].blocker_codes
    assert items["PDD-PARTICLE-COUNT"].effective_risk == "HIGH"
    assert "particle_count" in items["PDD-PARTICLE-COUNT"].missing_fact_keys


def test_old_safety_rule_only_constrains_prohibited_claims(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    questions = [_question("PDD-GREETING", "GREETING", "你好")]
    sources = [
        _source("KMT-FAQ", "FAQ", [{"关联问题ID": "PDD-GREETING", "标准回答": "保证正品", "风险等级": "低"}]),
        _source("KMT-OLD-SAFETY", "SAFETY_RULE", [{"安全提醒": "不会主动用于回答", "禁止承诺内容": "保证正品", "风险等级": "低"}]),
    ]
    item = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, sources, questions=questions)
    ).items[0]

    assert item.effective_risk == "HIGH"
    assert item.prohibited_claim_hits == ["保证正品"]
    assert "PROHIBITED_CLAIM_PRESENT" in item.blocker_codes
    assert "material:KMT-OLD-SAFETY:v1" not in item.citation_ids


def test_old_faq_requires_normalized_exact_question_or_alias_match(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    question = _question("PDD-OLD-FAQ", "PRODUCT_FACT", "是什么包装")
    question["aliases"] = ["包装怎么样"]
    sources = [
        _source("KMT-OLD-FAQ", "FAQ", [{"客户常问问题": "包装 怎么样？", "标准回答": "亲，使用审核彩盒包装。", "风险等级": "低"}]),
        _source("KMT-UNRELATED-FAQ", "FAQ", [{"客户常问问题": "包装里有什么", "标准回答": "不应命中", "风险等级": "低"}]),
    ]
    item = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, sources, questions=[question])
    ).items[0]

    assert item.effective_risk == "LOW"
    assert item.answer_preview == "亲，使用审核彩盒包装。"
    assert item.citation_ids == ["material:KMT-OLD-FAQ:v1"]


def test_c_baseline_all_36_questions_run_through_real_a_evaluator(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    baseline_path = Path(__file__).resolve().parents[2] / "platform_backend" / "app" / "reply_readiness" / "baseline.py"
    baseline = runpy.run_path(str(baseline_path))["BASELINE_QUESTIONS"]
    questions = [
        {"schema_version": "pdd-reply-readiness-question.v1", **dict(item)}
        for item in baseline
    ]
    source = _source("KMT-FULL-36", "PRODUCT_KNOWLEDGE", [{
        "颗粒数量": "1200颗", "成品尺寸": "40cm", "材质信息": "ABS", "商品重量": "1.2kg",
        "安装方式": "按说明书拼装", "包装内容": "积木与说明书", "版本差异": "颜色不同",
        "图片资料状态": "已审核", "视频资料状态": "已审核", "图片一致性说明": "同款实拍",
        "快递选择策略": "仓库按地区安排", "发货地": "浙江", "隐私包装": "无商品名外箱",
        "品牌授权证据": "授权书编号 SYNTHETIC-001",
    }])

    result = ReplyReadinessEvaluator(store).evaluate(
        _payload_with_sources(publication, [source], questions=questions, run_id="RRN-C-BASELINE-36")
    )
    items = _items(result)
    assert len(result.items) == 36
    assert set(items) == {item["question_id"] for item in baseline}
    for protected_id in ["PDD-INVENTORY", "PDD-PRICE", "PDD-REFUND", "PDD-CHANGE-ADDRESS", "PDD-AUTHENTICITY"]:
        assert items[protected_id].effective_risk == "HIGH"


def test_published_debug_fixed_rule_does_not_require_published_knowledge(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(
        store, (_fixed_rule("RULE-GREETING", "你好", "您好，请问有什么可以帮您？"),)
    )
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
    ])
    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload(
            "你好",
            rule_fingerprint=publication.snapshot_fingerprint,
            publication_status="NOT_GENERATED",
            current_fingerprint=None,
            indexed_fingerprint=None,
            active_collection=None,
        )
    )

    assert result.status == "COMPLETED"
    assert result.item is not None
    assert result.item.origin == "FIXED_RULE"
    assert result.item.answer_preview == "您好，请问有什么可以帮您？"
    assert result.rule_references == ["RULE-GREETING:v1"]
    assert result.dependency_usage.reply_rule is True
    assert result.dependency_usage.rag_collection is False
    assert result.dependency_usage.knowledge is False
    assert result.dependency_usage.model is False
    assert runtime.query_calls == 0
    assert result.reply_rule_snapshot_fingerprint == publication.snapshot_fingerprint


def test_existing_internal_evaluate_route_accepts_published_debug_mode(
    api_client,
    tmp_path: Path,
) -> None:
    client, _ = api_client
    store = ReplyRuleSnapshotStore(tmp_path / "published-debug-http")
    publication = _publication(
        store, (_fixed_rule("RULE-GREETING", "你好", "您好，请问有什么可以帮您？"),)
    )
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
    ])
    client.app.state.reply_readiness_evaluator = ReplyReadinessEvaluator(store, runtime)
    try:
        response = client.post(
            "/api/admin/ai/reply-readiness/evaluate",
            json=_debug_payload(
                "你好",
                rule_fingerprint=publication.snapshot_fingerprint,
                publication_status="NOT_GENERATED",
                current_fingerprint=None,
                indexed_fingerprint=None,
                active_collection=None,
            ).model_dump(mode="json"),
        )
    finally:
        delattr(client.app.state, "reply_readiness_evaluator")

    assert response.status_code == 200, response.text
    assert response.json()["simulation_mode"] == "PUBLISHED_ROUTER_DEBUG"
    assert response.json()["item"]["origin"] == "FIXED_RULE"
    assert response.json()["production_usable"] is False
    assert response.json()["allow_auto_send"] is False


def test_published_debug_rag_fails_closed_when_knowledge_is_not_published(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    _publication(store)
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
    ])
    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload(
            "适合几岁",
            publication_status="NOT_GENERATED",
            current_fingerprint=None,
            indexed_fingerprint=None,
            active_collection=None,
        )
    )

    assert result.status == "COMPLETED"
    assert result.item is not None
    assert result.item.effective_risk == "HIGH"
    assert result.item.action == "TRANSFER_HUMAN"
    assert "KNOWLEDGE_NOT_PUBLISHED" in result.item.blocker_codes
    assert result.dependency_usage.rag_collection is True
    assert result.dependency_usage.knowledge is True
    assert result.dependency_usage.model is False
    assert runtime.query_calls == 0


def test_published_debug_ignores_drift_in_unused_rag_dependencies(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(
        store, (_fixed_rule("RULE-GREETING", "你好", "您好，请问有什么可以帮您？"),)
    )
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection="published-v1", model="d" * 64),
        _runtime_snapshot(
            collection="published-v2", knowledge="e" * 64, model="f" * 64
        ),
    ])
    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload("你好", rule_fingerprint=publication.snapshot_fingerprint)
    )

    assert result.status == "COMPLETED"
    assert result.drifted_dependencies == []
    assert {item.dependency for item in result.diagnostic_changes} == {
        "rag_collection", "knowledge", "model"
    }
    assert runtime.query_calls == 0


def test_published_debug_rag_ignores_unused_rule_snapshot_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    _publication(store)
    runtime = _PublishedRuntime([_runtime_snapshot(), _runtime_snapshot()])
    evaluator = ReplyReadinessEvaluator(store, runtime)
    fingerprints = iter(["1" * 64, "2" * 64])
    monkeypatch.setattr(
        evaluator, "_current_rule_fingerprint", lambda payload: next(fingerprints)
    )

    result = evaluator.evaluate(_debug_payload("适合几岁"))

    assert result.status == "COMPLETED"
    assert result.item is not None and result.item.origin == "RAG"
    assert result.dependency_usage.reply_rule is False
    assert result.dependency_usage.model is True
    assert result.drifted_dependencies == []
    assert [item.dependency for item in result.diagnostic_changes] == ["reply_rule"]
    assert runtime.query_calls == 1


def test_published_debug_composite_fails_when_used_collection_drifts(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(
        store,
        (_fixed_rule("RULE-MATERIAL", "什么材质？", "材质为ABS塑料。"),),
    )
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection="published-v1"),
        _runtime_snapshot(collection="published-v2"),
    ])
    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload(
            "什么材质？\n适合几岁？",
            rule_fingerprint=publication.snapshot_fingerprint,
        )
    )

    assert result.status == "FAILED"
    assert result.failure_code == "PRODUCTION_RUNTIME_VERSION_DRIFT"
    assert result.item is None
    assert result.dependency_usage.reply_rule is True
    assert result.dependency_usage.rag_collection is True
    assert result.dependency_usage.knowledge is True
    assert result.dependency_usage.model is True
    assert result.drifted_dependencies == ["rag_collection"]
    assert runtime.query_calls == 1


def test_published_debug_fixed_rule_fails_when_c_and_a_snapshots_differ(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    _publication(
        store, (_fixed_rule("RULE-GREETING", "你好", "您好，请问有什么可以帮您？"),)
    )
    runtime = _PublishedRuntime([
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
        _runtime_snapshot(collection=None, status="UNAVAILABLE", knowledge=None),
    ])

    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload(
            "你好",
            rule_fingerprint="b" * 64,
            publication_status="NOT_GENERATED",
            current_fingerprint=None,
            indexed_fingerprint=None,
            active_collection=None,
        )
    )

    assert result.status == "FAILED"
    assert result.failure_code == "PRODUCTION_RUNTIME_VERSION_DRIFT"
    assert result.item is None
    assert result.drifted_dependencies == ["reply_rule"]
    assert result.diagnostic_changes[0].dependency == "reply_rule"
    assert result.diagnostic_changes[0].before == "b" * 64


def test_published_debug_rag_only_reports_unused_expected_rule_mismatch(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    _publication(store)
    runtime = _PublishedRuntime([_runtime_snapshot(), _runtime_snapshot()])

    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload("适合几岁", rule_fingerprint="b" * 64)
    )

    assert result.status == "COMPLETED"
    assert result.item is not None and result.item.origin == "RAG"
    assert result.dependency_usage.reply_rule is False
    assert result.drifted_dependencies == []
    assert [item.dependency for item in result.diagnostic_changes] == ["reply_rule"]


def test_published_debug_composite_fails_on_expected_rule_mismatch(
    tmp_path: Path,
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    _publication(
        store,
        (_fixed_rule("RULE-MATERIAL", "什么材质？", "材质为ABS塑料。"),),
    )
    runtime = _PublishedRuntime([_runtime_snapshot(), _runtime_snapshot()])

    result = ReplyReadinessEvaluator(store, runtime).evaluate(
        _debug_payload("什么材质？\n适合几岁？", rule_fingerprint="b" * 64)
    )

    assert result.status == "FAILED"
    assert result.item is None
    assert result.dependency_usage.reply_rule is True
    assert result.dependency_usage.rag_collection is True
    assert result.drifted_dependencies == ["reply_rule"]
    assert runtime.query_calls == 1


@pytest.mark.parametrize("status", ["REJECTED", "ANALYSIS_FAILED"])
def test_unusable_knowledge_status_fails_closed(tmp_path: Path, status: str) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "snapshots")
    publication = _publication(store)
    payload = _payload_with_sources(
        publication,
        [_source("KMT-BLOCKED", "PRODUCT_KNOWLEDGE", [{"颗粒数量": "1200颗"}], status=status)],
    )
    with pytest.raises(ValueError, match="status is not usable"):
        ReplyReadinessEvaluator(store).evaluate(payload)
