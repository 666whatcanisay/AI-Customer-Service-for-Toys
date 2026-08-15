from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config.settings import Settings
from app.main import create_app
from app.models.chat import FrozenChatContext, VerifiedConversationEntry
from app.service.evaluation import (
    EvaluationCase,
    EvaluationValidationError,
    parse_evaluations,
    render_markdown,
    run_evaluations,
)
from app.service.rag_service import (
    CUSTOMER_ANSWER_MAX_SENTENCES,
    RAGService,
    SAFETY_ACTION_MESSAGES,
)
from app.service.test_knowledge import (
    PlatformTestKnowledgeClient,
    TestKnowledgeValidationError as PackageValidationError,
    parse_test_knowledge_package,
)
from app.service.vector_store import VectorStore
from conftest import DeterministicEmbeddingFunction


FIXTURE_DIR = Path(__file__).parent / "fixtures"
PACKAGE_ID = "PKG-PDD-SM-V031-SYNTHETIC"


def load_json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_rag_sources_canonicalize_blank_optional_sku_scope() -> None:
    service = object.__new__(RAGService)

    sources = service._source_items(
        [
            {
                "source_name": "product-level-source",
                "page": 0,
                "chunk_id": "chunk-product-level",
                "distance": 0.01,
                "content": "product fact",
                "knowledge_version": "v1",
                "source_ids": ["source-1"],
                "product_id": "982904528556",
                "sku_id": "",
            },
            {
                "source_name": "sku-source",
                "page": 1,
                "chunk_id": "chunk-sku",
                "distance": 0.02,
                "content": "sku fact",
                "knowledge_version": "v1",
                "source_ids": ["source-2"],
                "product_id": "982904528556",
                "sku_id": "SKU-EXACT",
            },
        ]
    )

    assert sources[0]["sku_id"] is None
    assert sources[1]["sku_id"] == "SKU-EXACT"


def test_product_fact_topics_keep_answer_and_evidence_on_one_field() -> None:
    results = [
        {"content": 'particle_count: "约500颗"'},
        {"content": 'assembled_size: "成品约20×5×5厘米"'},
        {"content": 'product_scale: "比例约1:20"'},
        {"content": 'package_type: "彩盒包装"'},
        {"content": 'image_material_status: "详情页图片为产品实物拍摄展示"'},
    ]

    assert RAGService._results_for_answer_topics(
        "这款积木大概多少颗？", results
    ) == [results[0]]
    assert RAGService._results_for_answer_topics(
        "拼好以后大概多大？", results
    ) == [results[1]]
    assert RAGService._results_for_answer_topics("这个模型比例是多少？", results) == [
        results[1],
        results[2],
    ]
    assert RAGService._results_for_answer_topics("这款是什么包装？", results) == [
        results[3]
    ]
    assert RAGService._results_for_answer_topics("详情页是实物图吗？", results) == [
        results[4]
    ]


def test_reviewed_structured_product_facts_have_stable_customer_wording() -> None:
    results = [
        {"content": 'particle_count: "约500颗"'},
        {"content": 'assembled_size: "成品约20×5×5厘米"'},
        {"content": 'product_scale: "比例约1:20"'},
        {"content": 'package_type: "彩盒包装"'},
        {"content": 'image_material_status: "详情页图片为产品实物拍摄展示"'},
        {"content": 'ship_origin: "广东汕头"'},
    ]

    assert "500颗" in RAGService._approved_structured_fact_answer(
        "有多少粒", results
    )
    size = RAGService._approved_structured_fact_answer("长度和宽度是多少", results)
    assert size is not None and all(value in size for value in ("20厘米", "5厘米"))
    scale = RAGService._approved_structured_fact_answer("1:1复刻吗", results)
    assert scale is not None and "1:20" in scale and "20厘米" in scale
    assert "1:1" not in scale
    assert "彩盒包装" in RAGService._approved_structured_fact_answer(
        "货柜礼盒是什么", results
    )
    assert "实拍" in RAGService._approved_structured_fact_answer(
        "有拼好的实物图吗", results
    )
    assert "广东汕头" in RAGService._approved_structured_fact_answer(
        "哪里发货", results
    )


def context(product_id: str = "P-Q80", sku_id: str | None = None):
    return FrozenChatContext(
        tenant_id="TENANT-PDD-SM-TEST",
        platform="pdd",
        store_code="PDD-SM",
        product_id=product_id,
        sku_id=sku_id,
    )


def test_verified_multiturn_history_is_rendered_in_order_and_bounded():
    entries = tuple(
        VerifiedConversationEntry(
            message_id=f"message-{index}",
            sender="customer" if index % 2 else "operator",
            content=f"turn-{index}",
            timestamp=f"2026-08-12T02:00:{index:02d}Z",
        )
        for index in range(1, 21)
    )
    value = context().model_copy(update={"recent_conversation": entries})

    rendered = RAGService._recent_conversation_prompt(value)

    lines = rendered.splitlines()
    assert len(lines) == 20
    assert lines[0] == "1. [客户] turn-1"
    assert lines[1] == "2. [客服] turn-2"
    assert lines[-1] == "20. [客服] turn-20"


def test_empty_multiturn_history_is_explicit():
    assert RAGService._recent_conversation_prompt(context()) == "（无历史对话）"


def is_store_guard(result: dict) -> bool:
    return not result["product_id"] and (
        result["knowledge_type"] == "SAFETY_RULE"
        or (
            result["knowledge_type"] == "FAQ"
            and result["risk_level"] == "HIGH"
            and result["answer_action"]
            in {"ASK_CLARIFY", "REQUIRE_LOOKUP", "TRANSFER_HUMAN", "REFUSE"}
        )
    )


@pytest.fixture()
def scoped_service(tmp_path: Path):
    embedding = DeterministicEmbeddingFunction()
    legacy_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="legacy_documents",
        model_name="deterministic",
        embedding_function=embedding,
    )
    test_store = VectorStore(
        persist_dir=tmp_path / "vector_db",
        collection_name="test_knowledge_v031",
        model_name="deterministic",
        embedding_function=embedding,
    )
    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=tmp_path / "knowledge_base",
        vector_db_path=tmp_path / "vector_db",
        log_dir=tmp_path / "logs",
        llm_provider="bailian",
        dashscope_api_key="",
        rag_distance_threshold=0.15,
        top_k=3,
        platform_api_base_url="",
    )
    service = RAGService(
        settings,
        vector_store=legacy_store,
        test_vector_store=test_store,
    )
    package = parse_test_knowledge_package(
        load_json("test_knowledge_v031.json"), PACKAGE_ID
    )
    service.test_knowledge_index.sync(package)
    yield service, package
    service.close()


def test_v031_package_strict_safety_validation():
    payload = load_json("test_knowledge_v031.json")
    package = parse_test_knowledge_package(payload, PACKAGE_ID)
    assert package.tenant_id == "TENANT-PDD-SM-TEST"
    assert package.test_data_mode is True
    assert package.production_usable is False
    assert package.allow_auto_send is False
    assert package.response_mode == "SUGGESTION_ONLY"
    assert package.version == "V0.3.1"
    assert package.schema_version == "0.3.1-test"
    store_safety = [
        item
        for item in package.items
        if item.knowledge_type == "SAFETY_RULE" and not item.product_id
    ]
    assert store_safety
    assert all(not item.sku_id for item in store_safety)
    store_safety_faq = [
        item
        for item in package.items
        if item.knowledge_type == "FAQ" and not item.product_id
    ]
    assert store_safety_faq
    assert all(
        not item.sku_id
        and item.risk_level == "HIGH"
        and item.answer_action
        in {"ASK_CLARIFY", "REQUIRE_LOOKUP", "TRANSFER_HUMAN", "REFUSE"}
        for item in store_safety_faq
    )

    for field, invalid in (
        ("tenant_id", "TENANT-OTHER"),
        ("test_data_mode", False),
        ("production_usable", True),
        ("allow_auto_send", True),
        ("response_mode", "AUTO_SEND"),
    ):
        changed = load_json("test_knowledge_v031.json")
        changed[field] = invalid
        with pytest.raises(PackageValidationError):
            parse_test_knowledge_package(changed, PACKAGE_ID)

    for field, invalid in (
        ("version", "0.3.1-test"),
        ("schema_version", "V0.3.1"),
    ):
        changed = load_json("test_knowledge_v031.json")
        changed[field] = invalid
        with pytest.raises(PackageValidationError):
            parse_test_knowledge_package(changed, PACKAGE_ID)


@pytest.mark.parametrize("knowledge_type", ["PRODUCT_FACT", "SKU_FACT", "FAQ"])
def test_only_strict_store_guards_may_omit_product_id(knowledge_type):
    changed = load_json("test_knowledge_v031.json")
    item = next(
        item for item in changed["items"] if item["knowledge_type"] == knowledge_type
    )
    item["product_id"] = None
    item["sku_id"] = None
    with pytest.raises(PackageValidationError, match="product_id is required"):
        parse_test_knowledge_package(changed, PACKAGE_ID)


def test_sku_fact_requires_sku_id():
    changed = load_json("test_knowledge_v031.json")
    item = next(
        item for item in changed["items"] if item["knowledge_type"] == "SKU_FACT"
    )
    item["sku_id"] = None
    with pytest.raises(PackageValidationError, match="sku_id is required"):
        parse_test_knowledge_package(changed, PACKAGE_ID)


@pytest.mark.parametrize(
    ("risk_level", "answer_action"),
    [("MEDIUM", "REQUIRE_LOOKUP"), ("HIGH", "DIRECT_ANSWER")],
)
def test_empty_product_faq_requires_high_risk_guard_action(
    risk_level, answer_action
):
    changed = load_json("test_knowledge_v031.json")
    item = next(
        item
        for item in changed["items"]
        if item["knowledge_id"] == "K-STORE-GUARD-FAQ"
    )
    item["risk_level"] = risk_level
    item["answer_action"] = answer_action
    with pytest.raises(PackageValidationError, match="product_id is required"):
        parse_test_knowledge_package(changed, PACKAGE_ID)


def test_sync_is_idempotent_and_metadata_is_complete(scoped_service):
    service, package = scoped_service
    first_count = service.test_vector_store.collection.count()
    result = service.test_knowledge_index.sync(package)
    assert result["synced_items"] == 13
    assert result["collection_count"] == first_count == 13

    stored = service.test_vector_store.collection.get(
        where={"package_id": {"$eq": PACKAGE_ID}},
        include=["metadatas"],
    )
    metadata = stored["metadatas"][0]
    assert {
        "tenant_id",
        "platform",
        "store_code",
        "product_id",
        "sku_id",
        "knowledge_type",
        "answer_action",
        "risk_level",
        "source_ids",
        "package_id",
    } <= metadata.keys()


def test_pinduoduo_business_context_reads_historical_pdd_metadata(scoped_service):
    service, _ = scoped_service
    business_context = FrozenChatContext(
        tenant_id="TENANT-PDD-SM-TEST",
        platform="pinduoduo",
        store_code="PDD-SM",
        product_id="P-Q80",
        sku_id=None,
    )

    results = service.test_knowledge_index.search(
        "这个商品适合多大年龄？", business_context, top_k=3
    )

    assert results
    assert all(result["platform"] == "pdd" for result in results)


def test_product_and_sku_scope_filtering_prevents_cross_product(scoped_service):
    service, _ = scoped_service
    product_results = service.test_knowledge_index.search(
        "Q80磁力积木套装包含80颗积木，商品编号为Q80。",
        context(),
        top_k=5,
    )
    assert product_results
    assert all(result["product_id"] in {"", "P-Q80"} for result in product_results)
    assert all(
        result["product_id"] == "P-Q80" or is_store_guard(result)
        for result in product_results
    )
    assert all("1688颗" not in result["content"] for result in product_results)

    sku_results = service.test_knowledge_index.search(
        "SKU-Q80-BLUE是Q80蓝色款，包装主色为蓝色。",
        context(sku_id="SKU-Q80-BLUE"),
        top_k=3,
    )
    assert sku_results[0]["sku_id"] == "SKU-Q80-BLUE"
    assert sku_results[0]["source_ids"] == ["SRC-Q80-SKU-BLUE"]

    sku_safety = service.test_knowledge_index.search(
        "Q80含有小零件，不适合3岁以下儿童；使用时需要成人看护。",
        context(sku_id="SKU-Q80-BLUE"),
        top_k=3,
    )
    assert any(
        result["source_ids"] == ["SRC-Q80-SAFETY"] for result in sku_safety
    )

    other_product = service.test_knowledge_index.search(
        "P-1688豪华积木套装包含1688颗积木。",
        context(product_id="P-1688"),
        top_k=3,
    )
    assert other_product
    assert all(result["product_id"] in {"", "P-1688"} for result in other_product)
    assert all(
        result["product_id"] == "P-1688" or is_store_guard(result)
        for result in other_product
    )


def test_store_safety_reaches_any_product_without_cross_product_facts(scoped_service):
    service, _ = scoped_service
    results = service.test_knowledge_index.search(
        "Q80含有小零件，不适合3岁以下儿童；使用时需要成人看护。",
        context(product_id="P-UNLISTED"),
        top_k=5,
    )
    assert results
    assert any(result["source_ids"] == ["SRC-Q80-SAFETY"] for result in results)
    assert all(is_store_guard(result) for result in results)
    assert all(result["product_id"] == "" for result in results)
    assert all(result["sku_id"] == "" for result in results)
    assert all("SRC-Q80-PRODUCT" not in result["source_ids"] for result in results)
    assert all("SRC-1688-PRODUCT" not in result["source_ids"] for result in results)


def test_store_guarded_faq_reaches_any_product_without_model_downgrade(
    scoped_service, monkeypatch
):
    service, _ = scoped_service

    def model_must_not_run(*args, **kwargs):
        raise AssertionError("store guarded FAQ reached the model")

    monkeypatch.setattr(service, "call_llm", model_must_not_run)
    result = service.query(
        "客户反馈订单缺少零件且缺少订单号、商品与缺件信息时，必须转人工客服处理。",
        context(product_id="P-UNLISTED"),
    )
    assert result["action"] == "TRANSFER_HUMAN"
    assert result["risk_level"] == "HIGH"
    assert any(
        "SRC-STORE-GUARD-FAQ" in source["source_ids"]
        for source in result["sources"]
    )
    assert all(source["product_id"] == "" for source in result["sources"])


def test_faq_reference_and_bundle_retrieval(scoped_service):
    service, _ = scoped_service
    faq = service.test_knowledge_index.search(
        "Q80建议6岁及以上儿童在成人看护下使用。", context(), 1
    )
    assert faq[0]["knowledge_type"] == "FAQ"
    assert faq[0]["source_ids"] == ["SRC-Q80-FAQ-AGE"]

    reference = service.test_knowledge_index.search(
        "SKU-Q80-BLUE为REFERENCE参考款，canonical SKU为SKU-Q80-BASE。",
        context(sku_id="SKU-Q80-BLUE"),
        1,
    )
    assert reference[0]["source_ids"] == ["SRC-Q80-REFERENCE"]

    bundle = service.test_knowledge_index.search(
        "SKU-Q80-BUNDLE为BUNDLE组合款，包含SKU-Q80-BLUE和SKU-Q80-PINK。",
        context(sku_id="SKU-Q80-BUNDLE"),
        1,
    )
    assert bundle[0]["source_ids"] == ["SRC-Q80-BUNDLE"]


def test_all_six_answer_actions_and_safety_actions_bypass_model(
    scoped_service, monkeypatch
):
    service, package = scoped_service
    by_action = {}
    for item in package.items:
        by_action.setdefault(item.answer_action, item)
    assert set(by_action) == {
        "DIRECT_ANSWER",
        "CONTROLLED_ANSWER",
        "ASK_CLARIFY",
        "REQUIRE_LOOKUP",
        "TRANSFER_HUMAN",
        "REFUSE",
    }

    for action in ("DIRECT_ANSWER", "CONTROLLED_ANSWER"):
        item = by_action[action]
        result = service.query(
            item.content,
            context(item.product_id or "P-Q80", item.sku_id or None),
        )
        assert result["action"] == action

    def model_must_not_run(*args, **kwargs):
        raise AssertionError("guarded safety action reached the model")

    monkeypatch.setattr(service, "call_llm", model_must_not_run)
    for action, message in SAFETY_ACTION_MESSAGES.items():
        item = by_action[action]
        result = service.query(
            item.content,
            context(item.product_id or "P-Q80", item.sku_id or None),
        )
        assert result["action"] == action
        assert result["answer"]


def test_nearby_high_risk_boundary_prevents_uncontrolled_direct_answer(
    scoped_service,
):
    service, package = scoped_service
    direct = next(
        item
        for item in package.items
        if item.knowledge_id == "K-Q80-PRODUCT"
    )
    high_boundary = replace(
        direct,
        knowledge_id="K-Q80-HIGH-CONTROLLED-BOUNDARY",
        answer_action="CONTROLLED_ANSWER",
        risk_level="HIGH",
        source_ids=("SRC-Q80-HIGH-CONTROLLED-BOUNDARY",),
    )
    service.test_knowledge_index.sync(
        replace(package, items=package.items + (high_boundary,))
    )

    result = service.query(f"{direct.content} 客户声称是1688颗。", context())

    assert result["action"] == "CONTROLLED_ANSWER"
    assert result["risk_level"] == "HIGH"
    assert any(
        "SRC-Q80-HIGH-CONTROLLED-BOUNDARY" in source["source_ids"]
        for source in result["sources"]
    )


def test_age_answer_is_copy_ready_and_sources_remain_structured(
    scoped_service, monkeypatch
):
    service, package = scoped_service
    captured = {}
    selected = [
        (
            replace(item, content="Q80建议6～12岁儿童在成人看护下使用。")
            if item.knowledge_id == "K-Q80-FAQ-AGE"
            else item
        )
        for item in package.items
        if item.knowledge_id in {"K-Q80-FAQ-AGE", "K-Q80-SAFETY"}
    ]
    results = [
        {
            "source_name": "synthetic-test-package",
            "page": 0,
            "chunk_id": item.knowledge_id,
            "distance": 0.05,
            "title": item.title,
            "content": item.content,
            "knowledge_type": item.knowledge_type,
            "answer_action": item.answer_action,
            "risk_level": item.risk_level,
            "source_ids": list(item.source_ids),
            "knowledge_version": "V0.3.1",
            "product_id": item.product_id or "",
            "sku_id": item.sku_id or "",
            "_exact_sku": False,
        }
        for item in selected
    ]

    def fixed_retrieval(question, top_k=None, context=None):
        return {
            "accepted": True,
            "threshold": 0.15,
            "top_distance": 0.05,
            "sources": service._source_items(results),
            "results": list(results),
        }

    def customer_reply(question, model_context, **kwargs):
        captured["context"] = model_context
        captured["focus"] = kwargs["answer_focus"]
        return (
            "根据【资料2】亲，这款建议6岁及以上的小朋友在成人看护下玩哦。"
            "产品含小零件，3岁以下儿童不建议使用，建议家长陪同拼装。\n"
            "请家长陪同拼装，确保安全。\n"
            "依据摘要：80颗积木；彩袋包装；约17×8×8.2cm。\n"
            "来源标识：SRC-Q80-FAQ-AGE"
        )

    monkeypatch.setattr(service, "retrieve", fixed_retrieval)
    monkeypatch.setattr(service, "call_llm", customer_reply)
    result = service.query("这个款式适合几岁的小朋友？", context())

    assert result["action"] == "CONTROLLED_ANSWER"
    assert "6～12岁" in result["answer"]
    assert "6岁及以上" not in result["answer"]
    assert "3岁以下" in result["answer"]
    assert len(
        re.findall(
            r"(?:成人|家长|大人).{0,12}(?:陪同|看护|监护|陪伴)",
            result["answer"],
        )
    ) == 1
    assert "确保安全" not in result["answer"]
    assert all(term not in result["answer"] for term in ("资料", "依据摘要", "SRC-"))
    assert all(term not in captured["context"] for term in ("80颗", "彩袋", "17×8"))
    assert "建议年龄" in captured["focus"]
    assert any("SRC-Q80-FAQ-AGE" in source["source_ids"] for source in result["sources"])
    assert any("SRC-Q80-SAFETY" in source["source_ids"] for source in result["sources"])


@pytest.mark.parametrize(
    ("question", "expected", "excluded"),
    [
        ("这款是什么包装？", "大彩盒包装", ("6～12岁", "26×17×16cm")),
        ("成品尺寸多大？", "26×17×16cm", ("1000颗", "大彩盒包装")),
    ],
)
def test_model_context_only_contains_facts_for_current_question(
    scoped_service, monkeypatch, question, expected, excluded
):
    service, _ = scoped_service
    results = [
        {
            "source_name": "synthetic-multi-fact",
            "page": 1,
            "chunk_id": "K-MULTI-FACT",
            "distance": 0.05,
            "title": "多事实商品信息",
            "content": (
                "这款含1000颗积木；采用大彩盒包装；成品约26×17×16cm；"
                "建议6～12岁儿童使用；含小颗粒。"
            ),
            "knowledge_type": "PRODUCT_FACT",
            "answer_action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "source_ids": ["SRC-MULTI-FACT"],
            "knowledge_version": "V0.3.1",
            "product_id": "P-Q80",
            "sku_id": "",
            "_exact_sku": False,
        }
    ]

    def fixed_retrieval(question, top_k=None, context=None):
        return {
            "accepted": True,
            "threshold": 0.15,
            "top_distance": 0.05,
            "sources": service._source_items(results),
            "results": list(results),
        }

    captured = {}

    def focused_reply(question, model_context, **kwargs):
        captured["context"] = model_context
        return f"亲，{model_context}"

    monkeypatch.setattr(service, "retrieve", fixed_retrieval)
    monkeypatch.setattr(service, "call_llm", focused_reply)
    result = service.query(question, context())

    assert expected in result["answer"]
    assert all(term not in result["answer"] for term in excluded)
    assert all(term not in captured["context"] for term in excluded)
    assert result["sources"][0]["source_ids"] == ["SRC-MULTI-FACT"]


def test_customer_answer_sanitizer_removes_internal_traces_and_limits_length():
    answer = RAGService._sanitize_customer_answer(
        "根据【资料1】亲，这款是礼盒装哦。第二句补充说明。第三句说明。"
        "第四句不应保留。\n依据摘要：内部原文。\n"
        "来源标识：SRC-PDD-SM-001\nsource_id: SRC-PDD-SM-002"
    )

    assert all(
        term not in answer
        for term in ("资料", "依据摘要", "来源标识", "source_id", "SRC-")
    )
    sentences = [
        value
        for value in re.findall(r"[^。！？!?]+[。！？!?]?", answer)
        if value.strip()
    ]
    assert len(sentences) == CUSTOMER_ANSWER_MAX_SENTENCES


def test_no_hit_refuses_without_sources(scoped_service):
    service, _ = scoped_service
    result = service.query(
        "火星公司税率与量子发动机维修流程", context(product_id="P-Q80")
    )
    assert result["action"] == "REFUSE"
    assert result["sources"] == []
    assert result["warnings"] == ["NO_SCOPED_KNOWLEDGE"]


def test_unknown_product_refuses_even_when_store_guard_matches(
    scoped_service, monkeypatch
):
    service, _ = scoped_service

    monkeypatch.setattr(
        service,
        "retrieve",
        lambda question, top_k=None, context=None: {
            "accepted": True,
            "threshold": 0.45,
            "top_distance": 0.05,
            "sources": [{"product_id": "", "source_ids": ["STORE-GUARD"]}],
            "results": [
                {
                    "product_id": "",
                    "sku_id": "",
                    "knowledge_type": "FAQ",
                    "answer_action": "REQUIRE_LOOKUP",
                    "risk_level": "HIGH",
                }
            ],
        },
    )

    result = service.query(
        "这个不存在的商品有什么功能？",
        context(product_id="P-UNKNOWN"),
    )

    assert result["action"] == "REFUSE"
    assert result["sources"] == []
    assert result["warnings"] == ["KNOWLEDGE_NOT_PUBLISHED"]


def test_local_ollama_bypasses_environment_proxy(scoped_service, monkeypatch):
    service, _ = scoped_service
    service.settings = replace(
        service.settings,
        llm_provider="ollama",
        llm_base_url="http://127.0.0.1:11434",
        llm_model="qwen3.5:9b",
    )
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {"message": {"content": "OK"}}, ensure_ascii=False
            ).encode("utf-8")

    class FakeOpener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse()

    def fake_build_opener(handler):
        captured["handler"] = handler
        return FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail(
            "loopback Ollama must not use the environment-proxy opener"
        ),
    )

    answer = service._call_ollama(
        [{"role": "user", "content": "只回复 OK"}]
    )

    assert answer == "OK"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert isinstance(captured["handler"], urllib.request.ProxyHandler)


def test_age_wording_uses_age_control_instead_of_unrelated_store_guard(
    scoped_service, monkeypatch
):
    service, _ = scoped_service
    results = [
        {
            "file": "store-guard",
            "page": 0,
            "chunk_id": "shipping-guard",
            "distance": 0.01,
            "content": "发货时间需要查询后确认。",
            "product_id": "",
            "sku_id": "",
            "knowledge_type": "FAQ",
            "answer_action": "REQUIRE_LOOKUP",
            "risk_level": "HIGH",
            "source_ids": ["STORE-GUARD"],
        },
        {
            "file": "product-age",
            "page": 0,
            "chunk_id": "product-age",
            "distance": 0.05,
            "content": "Q80适合6～12岁儿童使用。",
            "product_id": "P-Q80",
            "sku_id": "",
            "knowledge_type": "PRODUCT_FACT",
            "answer_action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "source_ids": ["PRODUCT-AGE"],
        },
    ]
    monkeypatch.setattr(
        service,
        "retrieve",
        lambda question, top_k=None, context=None: {
            "accepted": True,
            "threshold": 0.45,
            "top_distance": 0.01,
            "sources": service._source_items(results),
            "results": list(results),
        },
    )
    monkeypatch.setattr(
        service,
        "call_llm",
        lambda question, model_context, **kwargs: model_context,
    )

    result = service.query("商品适合年龄？", context(product_id="P-Q80"))

    assert result["action"] == "CONTROLLED_ANSWER"
    assert result["sources"]
    assert any(source["product_id"] == "P-Q80" for source in result["sources"])
    assert all(
        source["product_id"] in {"", "P-Q80"}
        for source in result["sources"]
    )


def test_missing_material_evidence_refuses_without_model_completion(
    scoped_service, monkeypatch
):
    service, _ = scoped_service
    monkeypatch.setattr(
        service,
        "call_llm",
        lambda *args, **kwargs: pytest.fail(
            "missing material evidence must not reach the model"
        ),
    )

    result = service.query("材质是什么？", context(product_id="P-Q80"))

    assert result["action"] == "REFUSE"
    assert result["sources"] == []
    assert result["warnings"] == ["NO_SCOPED_KNOWLEDGE"]


def test_chat_and_retrieval_smoke_use_frozen_context(scoped_service, tmp_path):
    service, _ = scoped_service
    internal_secret = tmp_path / "internal-service.secret"
    internal_token = "test-internal-service-token-32-bytes-minimum"
    internal_secret.write_text(internal_token, encoding="utf-8")
    test_settings = replace(
        service.settings, internal_service_secret_file=internal_secret
    )

    def factory(active_settings: Settings) -> RAGService:
        return service

    app = create_app(settings=test_settings, rag_factory=factory)
    with TestClient(app, headers={"X-AI-CS-Service-Token": internal_token}) as client:
        for _ in range(100):
            if client.get("/api/status").json().get("ready"):
                break
            time.sleep(0.01)
        assert client.get("/api/health").status_code == 200
        payload = {
            "question": "Q80磁力积木套装包含80颗积木，商品编号为Q80。",
            "context": context().model_dump(),
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == {
            "answer",
            "action",
            "risk_level",
            "sources",
            "warnings",
            "required_fields",
            "model",
            "latency_ms",
            "request_id",
            "context",
        }
        assert set(data["sources"][0]) == {
            "source_name",
            "page",
            "chunk_id",
            "distance",
            "excerpt",
            "knowledge_version",
            "source_ids",
            "product_id",
            "sku_id",
        }
        retrieval = client.post(
            "/api/retrieval/search",
            json={"query": payload["question"], "context": payload["context"]},
        )
        assert retrieval.status_code == 200
        assert retrieval.json()["data"]["accepted"] is True


def test_catalog_store_context_is_accepted_and_unsafe_context_is_blocked(api_client):
    client, _ = api_client
    invalid = client.post(
        "/api/chat",
        json={
            "question": "test",
            "context": {
                "tenant_id": "TENANT-PDD-SM-TEST",
                "platform": "pdd",
                "store_code": "OTHER",
                "product_id": "P-Q80",
                "sku_id": "",
            },
        },
    )
    assert invalid.status_code == 200
    assert invalid.json()["warnings"] == ["KNOWLEDGE_NOT_PUBLISHED"]
    missing_context = client.post("/api/chat", json={"question": "test"})
    assert missing_context.status_code == 422
    sync = client.post(f"/api/test-knowledge/sync/{PACKAGE_ID}")
    assert sync.status_code == 503
    assert "ENV_BLOCKED" in sync.text

    accepted = FrozenChatContext(
        tenant_id="TENANT-PILOT",
        platform="pinduoduo",
        store_code="OTHER",
        product_id="P-Q80",
        sku_id=None,
    )
    assert accepted.store_code == "OTHER"

    with pytest.raises(ValidationError):
        FrozenChatContext(
            tenant_id="TENANT-PDD-SM-TEST",
            platform="pdd",
            store_code="OTHER\nSTORE",
            product_id="P-Q80",
            sku_id=None,
        )


def test_platform_client_uses_frozen_export_path(monkeypatch):
    payload = load_json("test_knowledge_v031.json")
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = PlatformTestKnowledgeClient("http://127.0.0.1:8012", 7)
    package = client.fetch_package(PACKAGE_ID)
    assert package.package_id == PACKAGE_ID
    assert seen == {
        "url": (
            "http://127.0.0.1:8012/api/v1/test-knowledge-packages/"
            f"{PACKAGE_ID}/rag-export"
        ),
        "timeout": 7,
    }


def test_28_evaluations_execute_and_render_reports():
    cases = parse_evaluations(load_json("evaluations_v031.json"), PACKAGE_ID)
    assert len(cases) == 28
    assert all(not case.store_scope for case in cases)

    expected = {case.question: case for case in cases}

    def deterministic_query(question, chat_context):
        case = expected[question]
        return {
            "answer": " ".join(case.expected_contains),
            "action": case.expected_action,
            "risk_level": case.expected_risk_level,
            "sources": [
                {
                    "source_ids": list(case.expected_source_ids),
                    "product_id": chat_context.product_id,
                    "sku_id": chat_context.sku_id or "",
                }
            ],
            "required_fields": list(case.expected_missing_fields),
            "latency_ms": 1.0,
        }

    report = run_evaluations(cases, deterministic_query)
    assert report["total"] == 28
    assert report["passed"] == 28
    assert report["failed"] == 0
    markdown = render_markdown(report)
    assert "E01" in markdown and "E28" in markdown


def test_required_fields_mean_only_still_missing_fields():
    direct = EvaluationCase(
        case_id="DIRECT",
        question="Q80有多少颗？",
        context=context(sku_id="SKU-Q80-BLUE"),
        expected_action="DIRECT_ANSWER",
        expected_source_ids=(),
        expected_contains=(),
        forbidden_contains=(),
        expected_required_fields=("product_id", "sku_id"),
        expected_risk_level="LOW",
        store_scope=False,
    )
    assert direct.expected_missing_fields == ()

    store_transfer = replace(
        direct,
        case_id="STORE",
        context=context(product_id="__STORE_LEVEL_EVALUATION__"),
        expected_action="TRANSFER_HUMAN",
        expected_required_fields=("order_id", "product_id", "sku_id"),
        store_scope=True,
    )
    assert store_transfer.expected_missing_fields == (
        "order_id",
        "product_id",
        "sku_id",
    )


def test_evaluator_accepts_grounded_synonyms_but_reports_scope_metadata_gaps():
    semantic_case = EvaluationCase(
        case_id="SEMANTIC",
        question="能同时拼吗？",
        context=context(),
        expected_action="DIRECT_ANSWER",
        expected_source_ids=("SRC-OK",),
        expected_contains=("共用零件", "不能同时拼"),
        forbidden_contains=(),
        expected_required_fields=(),
        expected_risk_level="LOW",
        store_scope=False,
    )

    def semantic_query(question, chat_context):
        return {
            "answer": "两种造型共用同一套零件，所以无法同时组装。",
            "action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "required_fields": [],
            "sources": [
                {
                    "source_ids": ["SRC-OK"],
                    "product_id": chat_context.product_id,
                    "sku_id": "",
                    "excerpt": "两种造型共用同一套零件，不能同时组装。",
                }
            ],
        }

    semantic = run_evaluations([semantic_case], semantic_query)
    assert semantic["passed"] == 1
    assert "evaluator_semantic_error_corrected" in semantic["records"][0][
        "diagnostic_categories"
    ]

    metadata_case = replace(
        semantic_case,
        case_id="METADATA",
        expected_source_ids=("SRC-TEST",),
        expected_contains=("ABS塑料",),
    )
    metadata = run_evaluations(
        [metadata_case],
        semantic_query,
        available_source_ids={"SRC-OK", "SRC-TEST"},
        source_catalog={
            "SRC-TEST": [
                {
                    "product_id": "P-OTHER",
                    "sku_id": "",
                    "knowledge_type": "PRODUCT_FACT",
                }
            ]
        },
    )
    assert metadata["passed"] == 0
    assert "metadata_loss" in metadata["records"][0]["failure_classes"]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [("version", "0.3.1-test"), ("schema_version", "V0.3.1")],
)
def test_evaluations_strictly_separate_version_and_schema(field, invalid):
    payload = load_json("evaluations_v031.json")
    payload[field] = invalid
    with pytest.raises(EvaluationValidationError):
        parse_evaluations(payload, PACKAGE_ID)
