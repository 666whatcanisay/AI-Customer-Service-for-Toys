from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.knowledge_materials.models import KnowledgeMaterial
from app.knowledge_publishing.models import ProductKnowledgePublication
from app.main import app
from app.reply_readiness.ai_client import ReplyReadinessAiUnavailable
from app.reply_readiness.models import ReplyReadinessRun
from app.reply_readiness.rate_limit import ReplyDebugRateLimiter
from app.reply_rules.models import ReplyRuleSnapshotPublication
from app.test_catalog.models import (
    TestKnowledgePackage as CatalogPackage,
    TestProduct as CatalogProduct,
    TestSku as CatalogSku,
    TestStore as CatalogStore,
)
from app.workspace.models import ConversationContextResolution


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _recognition_summary() -> dict[str, object]:
    return {
        "readable": True,
        "file_extension": ".json",
        "detected_fields": ["颗粒数量", "成品尺寸"],
        "missing_expected_fields": [],
        "privacy_reminder": "synthetic fixture only",
        "template_type": "PRODUCT_KNOWLEDGE",
        "template_name": "商品知识资料",
        "record_count": 1,
        "warnings": [],
        "high_risk_source_confirmed": False,
    }


def _analysis(size: str, particles: str) -> str:
    return json.dumps(
        {"数据记录": [{"成品尺寸": size, "颗粒数量": particles, "材质信息": "ABS"}]},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _add_material(
    session: Session,
    *,
    material_id: str,
    revision: int,
    sku_id: str | None,
    status: str,
    size: str,
    particles: str,
) -> KnowledgeMaterial:
    material = KnowledgeMaterial(
        material_id=material_id,
        revision=revision,
        store_code="STORE-READINESS",
        product_id="PRODUCT-READINESS",
        sku_id=sku_id,
        material_type="PRODUCT_SPEC",
        display_name=f"{material_id} v{revision}",
        original_filename="synthetic.json",
        content_hash="sha256:" + hashlib.sha256(f"{material_id}:{revision}".encode()).hexdigest(),
        recognition_summary=_recognition_summary(),
        analysis_text=_analysis(size, particles),
        raw_storage_path=f"ignored/{material_id}/{revision}.json",
        material_status=status,
        submitted_by="pytest",
    )
    session.add(material)
    return material


def _seed(session: Session) -> None:
    package = CatalogPackage(
        package_id="PKG-READINESS",
        package_name="合成回答就绪测试包",
        version="1.0.0",
        schema_version="1.0",
        tenant_id="TENANT-READINESS",
        platform="pdd",
        store_code="STORE-READINESS",
        response_mode="SUGGEST_ONLY",
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=False,
        import_status="IMPORTED",
        original_filename="synthetic.json",
        zip_sha256="a" * 64,
        counts_json="{}",
        imported_by="pytest",
    )
    store = CatalogStore(
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        store_name="合成回答就绪店铺",
        trial_enabled=True,
        knowledge_scope="TEST_ONLY",
        response_mode="SUGGEST_ONLY",
        allow_auto_send=False,
        test_data_mode=True,
        production_usable=False,
        data_source="TEST",
        customer_service_status="ENABLED",
        raw_data_json="{}",
    )
    product = CatalogProduct(
        product_id="PRODUCT-READINESS",
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        product_name_official="合成积木商品",
        product_name_display="合成积木商品",
        sales_status="ON_SALE",
        review_status="APPROVED",
        publishable=True,
        customer_service_status="ENABLED",
        source_ids_json="[]",
        raw_data_json="{}",
    )
    sku = CatalogSku(
        sku_id="SKU-READINESS",
        package_id=package.package_id,
        product_id=product.product_id,
        sku_code="SYNTHETIC-SKU",
        sku_name_official="合成SKU",
        sku_name_display="合成SKU",
        relation_type="INDEPENDENT",
        publishable=True,
        component_sku_refs_json="[]",
        source_ids_json="[]",
        raw_data_json="{}",
    )
    snapshot = ReplyRuleSnapshotPublication(
        scope_key="scope-readiness",
        tenant_id=package.tenant_id,
        platform=package.platform,
        status="PUBLISHED",
        snapshot_revision=3,
        snapshot_fingerprint="b" * 64,
        rules_fingerprint="c" * 64,
        rule_count=0,
        published_at=datetime.now(timezone.utc),
    )
    material_v1 = KnowledgeMaterial(
        material_id="KMT-READINESS",
        revision=1,
        store_code=store.store_code,
        product_id=product.product_id,
        sku_id=sku.sku_id,
        material_type="PRODUCT_SPEC",
        display_name="合成商品资料",
        original_filename="synthetic.json",
        content_hash="sha256:" + "d" * 64,
        recognition_summary=_recognition_summary(),
        analysis_text=_analysis("约30cm", "估测1000颗"),
        raw_storage_path="ignored/synthetic/v1/source.json",
        material_status="RECOGNIZED",
        submitted_by="operator-one",
    )
    material_v2 = KnowledgeMaterial(
        material_id="KMT-READINESS",
        revision=2,
        store_code=store.store_code,
        product_id=product.product_id,
        sku_id=sku.sku_id,
        material_type="PRODUCT_SPEC",
        display_name="合成商品资料",
        original_filename="synthetic.json",
        content_hash="sha256:" + "e" * 64,
        recognition_summary=_recognition_summary(),
        analysis_text=_analysis("40cm", "1200颗"),
        raw_storage_path="ignored/synthetic/v2/source.json",
        material_status="RECOGNIZED",
        submitted_by="operator-two",
    )
    product_material = KnowledgeMaterial(
        material_id="KMT-READINESS-PRODUCT",
        revision=1,
        store_code=store.store_code,
        product_id=product.product_id,
        sku_id=None,
        material_type="PRODUCT_SPEC",
        display_name="合成商品级资料",
        original_filename="synthetic-product.json",
        content_hash="sha256:" + "f" * 64,
        recognition_summary=_recognition_summary(),
        analysis_text=_analysis("35cm", "1100颗"),
        raw_storage_path="ignored/synthetic/product/source.json",
        material_status="RECOGNIZED",
        submitted_by="operator-product",
    )
    session.add_all([package, store, product, sku, snapshot, material_v1, material_v2, product_material])
    session.commit()


class _SyntheticEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        question_set = payload["question_set"]
        assert isinstance(question_set, dict)
        questions = question_set["questions"]
        assert isinstance(questions, list)
        items: list[dict[str, object]] = []
        for raw in questions:
            assert isinstance(raw, dict)
            answer = "需要人工客服核实后处理。"
            items.append(
                {
                    "schema_version": "pdd-reply-readiness-item-result.v1",
                    "question_id": raw["question_id"],
                    "effective_risk": "HIGH",
                    "action": "TRANSFER_HUMAN",
                    "origin": "MANUAL",
                    "answer_preview": answer,
                    "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                    "missing_fact_keys": list(raw.get("required_fact_keys") or []),
                    "blocker_codes": ["SYNTHETIC_MANUAL"],
                    "prohibited_claim_hits": [],
                    "citation_ids": [],
                    "evidence_bundle_sha256": None,
                }
            )
        base = {
            "schema_version": "pdd-reply-readiness-result.v1",
            "run_id": payload["run_id"],
            "status": "COMPLETED",
            "question_set_fingerprint": question_set["fingerprint"],
            "items": items,
        }
        return {**base, "result_sha256": _canonical_sha256(base)}


class _PublishedDebugEvaluator:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def evaluate(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        assert payload["execution_mode"] == "PUBLISHED_ROUTER_DEBUG"
        question_set = payload["question_set"]
        assert isinstance(question_set, dict)
        questions = question_set["questions"]
        assert isinstance(questions, list) and len(questions) == 1
        question = questions[0]
        assert isinstance(question, dict)
        answer = "您好，请问有什么可以帮您？"
        item = {
            "schema_version": "pdd-reply-readiness-item-result.v1",
            "question_id": question["question_id"],
            "effective_risk": "LOW",
            "action": "DIRECT_ANSWER",
            "origin": "FIXED_RULE",
            "answer_preview": answer,
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "missing_fact_keys": [],
            "blocker_codes": [],
            "prohibited_claim_hits": [],
            "citation_ids": ["reply-rule:RULE-GREETING:v1"],
            "evidence_bundle_sha256": "e" * 64,
        }
        base = {
            "schema_version": "pdd-reply-readiness-published-debug-result.v1",
            "simulation_mode": "PUBLISHED_ROUTER_DEBUG",
            "run_id": payload["run_id"],
            "status": "COMPLETED",
            "question_set_fingerprint": question_set["fingerprint"],
            "item": item,
            "failure_code": None,
            "quality_gate_status": "PASS",
            "rule_references": ["RULE-GREETING:v1"],
            "router_build_fingerprint": payload["router_build_fingerprint"],
            "reply_rule_snapshot_fingerprint": payload.get(
                "reply_rule_snapshot_fingerprint"
            ),
            "rag_collection_identity": None,
            "knowledge_publication_fingerprint": None,
            "knowledge_publication_status": "UNAVAILABLE",
            "model_config_identity": "d" * 64,
            "evaluated_at": "2026-08-14T08:00:00Z",
            "dependency_usage": {
                "router": True,
                "reply_rule": True,
                "rag_collection": False,
                "knowledge": False,
                "model": False,
            },
            "diagnostic_changes": [],
            "drifted_dependencies": [],
            "production_usable": False,
            "allow_auto_send": False,
        }
        return {**base, "result_sha256": _canonical_sha256(base)}


def test_history_detail_and_field_diff_are_immutable(client: TestClient, session: Session) -> None:
    _seed(session)

    history = client.get("/api/v1/admin/knowledge-materials/KMT-READINESS/revisions")
    assert history.status_code == 200, history.text
    assert [item["revision"] for item in history.json()["items"]] == [2, 1]

    detail = client.get("/api/v1/admin/knowledge-materials/KMT-READINESS/revisions/1")
    assert detail.status_code == 200, detail.text
    assert detail.json()["editable_record"]["成品尺寸"] == "约30cm"
    assert detail.json()["submitted_by"] == "operator-one"

    diff = client.get(
        "/api/v1/admin/knowledge-materials/KMT-READINESS/diff",
        params={"from_revision": 1, "to_revision": 2},
    )
    assert diff.status_code == 200, diff.text
    changes = {item["field"]: item for item in diff.json()["changes"]}
    assert changes["成品尺寸"] == {"field": "成品尺寸", "before": "约30cm", "after": "40cm"}
    assert changes["颗粒数量"] == {"field": "颗粒数量", "before": "估测1000颗", "after": "1200颗"}


def test_question_set_run_ledger_and_idempotency_are_isolated(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    evaluator = _SyntheticEvaluator()
    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = evaluator
    try:
        question_set = client.get(
            "/api/v1/admin/reply-readiness/question-set",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "sku_id": "SKU-READINESS",
            },
        )
        assert question_set.status_code == 200, question_set.text
        assert len(question_set.json()["questions"]) == 36

        request = {
            "store_code": "STORE-READINESS",
            "product_id": "PRODUCT-READINESS",
            "sku_id": "SKU-READINESS",
            "material_id": "KMT-READINESS",
            "material_revision": 2,
        }
        created = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json=request,
            headers={"Idempotency-Key": "readiness-run-001"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "COMPLETED"
        assert body["question_count"] == 36
        assert body["material_revision"] == 2
        assert body["reply_rule_snapshot_revision"] == 3
        assert body["reply_rule_snapshot_fingerprint"] == "b" * 64
        assert evaluator.calls == 1

        replay = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json=request,
            headers={"Idempotency-Key": "readiness-run-001"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert replay.json()["run_id"] == body["run_id"]
        assert evaluator.calls == 1

        frozen = client.get(f"/api/v1/internal/reply-readiness/runs/{body['run_id']}/input")
        assert frozen.status_code == 200, frozen.text
        assert frozen.json()["test_data_mode"] is True
        assert frozen.json()["production_usable"] is False
        assert frozen.json()["allow_auto_send"] is False
        assert frozen.json()["sandbox_vector_identity"].startswith("in-memory-replay:")
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous


def test_published_debug_uses_explicit_scope_without_writing_ledgers(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    evaluator = _PublishedDebugEvaluator()
    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = evaluator
    before_runs = session.scalar(select(func.count()).select_from(ReplyReadinessRun))
    before_resolutions = session.scalar(
        select(func.count()).select_from(ConversationContextResolution)
    )
    try:
        with (
            patch.object(session, "add", wraps=session.add) as add_spy,
            patch.object(session, "commit", wraps=session.commit) as commit_spy,
        ):
            response = client.post(
                "/api/v1/admin/reply-readiness/debug",
                json={
                    "store_code": "STORE-READINESS",
                    "product_id": "PRODUCT-READINESS",
                    "sku_id": "SKU-READINESS",
                    "customer_message": "你好",
                },
            )
        assert add_spy.call_count == 0
        assert commit_spy.call_count == 0
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulation_mode"] == "PUBLISHED_ROUTER_DEBUG"
    assert body["production_usable"] is False
    assert body["allow_auto_send"] is False
    assert body["item"]["origin"] == "FIXED_RULE"
    assert len(evaluator.payloads) == 1
    frozen = evaluator.payloads[0]
    assert frozen["knowledge_snapshot"] is None
    assert frozen["knowledge_sources"] == []
    assert frozen["sandbox_vector_identity"] is None
    assert frozen["publication_state"] == {
        "status": "NOT_GENERATED",
        "current_fingerprint": None,
        "indexed_fingerprint": None,
        "active_collection": None,
    }
    assert session.scalar(select(func.count()).select_from(ReplyReadinessRun)) == before_runs
    assert session.scalar(
        select(func.count()).select_from(ConversationContextResolution)
    ) == before_resolutions


def test_published_debug_passes_publication_facts_and_rejects_wrong_sku(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    product = session.get(CatalogProduct, "PRODUCT-READINESS")
    assert product is not None
    product.raw_data_json = json.dumps(
        {
            "particle_count": "约500颗",
            "assembled_size": "约20×5×5厘米",
            "ship_origin": "广东汕头",
        },
        ensure_ascii=False,
    )
    session.add(
        ProductKnowledgePublication(
            product_id="PRODUCT-READINESS",
            status="PUBLISHED",
            current_fingerprint="a" * 64,
            indexed_fingerprint="a" * 64,
            active_collection="published-v1",
            chunk_count=3,
            embedding_count=3,
        )
    )
    session.commit()
    evaluator = _PublishedDebugEvaluator()
    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = evaluator
    try:
        valid = client.post(
            "/api/v1/admin/reply-readiness/debug",
            json={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "customer_message": "适合几岁",
            },
        )
        invalid = client.post(
            "/api/v1/admin/reply-readiness/debug",
            json={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "sku_id": "SKU-OUTSIDE",
                "customer_message": "适合几岁",
            },
        )
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous

    assert valid.status_code == 200, valid.text
    assert evaluator.payloads[0]["publication_state"] == {
        "status": "PUBLISHED",
        "current_fingerprint": "a" * 64,
        "indexed_fingerprint": "a" * 64,
        "active_collection": "published-v1",
    }
    assert evaluator.payloads[0]["verified_product"]["attributes"] == {
        "particle_count": "约500颗",
        "finished_size": "约20×5×5厘米",
        "ship_origin": "广东汕头",
    }
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "REPLY_DEBUG_SCOPE_INVALID"
    assert len(evaluator.payloads) == 1


def test_published_debug_rate_limit_returns_429_without_second_ai_call(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    evaluator = _PublishedDebugEvaluator()
    previous_client = getattr(app.state, "reply_readiness_ai_client", None)
    previous_limiter = app.state.reply_debug_rate_limiter
    app.state.reply_readiness_ai_client = evaluator
    app.state.reply_debug_rate_limiter = ReplyDebugRateLimiter(
        attempts_per_window=1,
        window_seconds=60,
        clock=lambda: 100.0,
    )
    payload = {
        "store_code": "STORE-READINESS",
        "product_id": "PRODUCT-READINESS",
        "customer_message": "你好",
    }
    try:
        allowed = client.post("/api/v1/admin/reply-readiness/debug", json=payload)
        blocked = client.post("/api/v1/admin/reply-readiness/debug", json=payload)
    finally:
        app.state.reply_debug_rate_limiter = previous_limiter
        if previous_client is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous_client

    assert allowed.status_code == 200, allowed.text
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.json()["error"]["code"] == "REPLY_DEBUG_RATE_LIMITED"
    assert len(evaluator.payloads) == 1


def test_extension_cannot_lower_global_policy_floor(client: TestClient, session: Session) -> None:
    _seed(session)
    question_set = client.get(
        "/api/v1/admin/reply-readiness/question-set",
        params={"store_code": "STORE-READINESS", "product_id": "PRODUCT-READINESS"},
    ).json()
    authenticity = next(
        item for item in question_set["questions"] if item["question_id"] == "PDD-AUTHENTICITY"
    )
    authenticity["policy_risk_floor"] = "LOW"
    authenticity["expected_action"] = "DIRECT_ANSWER"
    response = client.post(
        "/api/v1/admin/reply-readiness/question-set-extensions",
        json={
            "scope_kind": "PRODUCT",
            "store_code": "STORE-READINESS",
            "product_id": "PRODUCT-READINESS",
            "questions": [authenticity],
            "change_reason": "synthetic attempted relaxation",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REPLY_READINESS_EXTENSION_RELAXED"


def test_sku_evidence_cannot_be_used_for_product_scope(client: TestClient, session: Session) -> None:
    _seed(session)
    response = client.post(
        "/api/v1/admin/reply-readiness/runs",
        json={
            "store_code": "STORE-READINESS",
            "product_id": "PRODUCT-READINESS",
            "material_id": "KMT-READINESS",
            "material_revision": 2,
        },
        headers={"Idempotency-Key": "readiness-cross-sku"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REPLY_READINESS_MATERIAL_SCOPE_MISMATCH"


def test_evaluator_failure_records_failed_without_old_result(client: TestClient, session: Session) -> None:
    _seed(session)

    class UnavailableEvaluator:
        def evaluate(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            raise ReplyReadinessAiUnavailable("synthetic outage")

    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = UnavailableEvaluator()
    try:
        response = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json={"store_code": "STORE-READINESS", "product_id": "PRODUCT-READINESS"},
            headers={"Idempotency-Key": "readiness-failed-run"},
        )
        assert response.status_code == 503, response.text
        listing = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={"store_code": "STORE-READINESS", "product_id": "PRODUCT-READINESS"},
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()["items"][0]["status"] == "FAILED"
        assert listing.json()["items"][0]["result"] is None
        assert listing.json()["items"][0]["failure_code"] == "REPLY_READINESS_EVALUATOR_UNAVAILABLE"
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous


def test_run_history_filters_product_and_exact_sku_without_changing_legacy_list(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    evaluator = _SyntheticEvaluator()
    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = evaluator
    try:
        product_run = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json={"store_code": "STORE-READINESS", "product_id": "PRODUCT-READINESS"},
            headers={"Idempotency-Key": "readiness-product-scope"},
        )
        assert product_run.status_code == 201, product_run.text
        sku_run = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "sku_id": "SKU-READINESS",
            },
            headers={"Idempotency-Key": "readiness-sku-scope"},
        )
        assert sku_run.status_code == 201, sku_run.text

        legacy = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={"store_code": "STORE-READINESS", "product_id": "PRODUCT-READINESS"},
        )
        assert legacy.status_code == 200, legacy.text
        assert {item["sku_id"] for item in legacy.json()["items"]} == {None, "SKU-READINESS"}

        product_only = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "scope_kind": "PRODUCT",
            },
        )
        assert product_only.status_code == 200, product_only.text
        assert [item["sku_id"] for item in product_only.json()["items"]] == [None]

        sku_only = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "scope_kind": "SKU",
                "sku_id": "SKU-READINESS",
            },
        )
        assert sku_only.status_code == 200, sku_only.text
        assert [item["sku_id"] for item in sku_only.json()["items"]] == ["SKU-READINESS"]

        invalid_product = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "scope_kind": "PRODUCT",
                "sku_id": "SKU-READINESS",
            },
        )
        assert invalid_product.status_code == 422, invalid_product.text
        assert invalid_product.json()["error"]["code"] == "REPLY_READINESS_RUN_SCOPE_INVALID"

        invalid_sku = client.get(
            "/api/v1/admin/reply-readiness/runs",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "scope_kind": "SKU",
            },
        )
        assert invalid_sku.status_code == 422, invalid_sku.text
        assert invalid_sku.json()["error"]["code"] == "REPLY_READINESS_RUN_SCOPE_INVALID"

        scoped_materials = client.get(
            "/api/v1/admin/knowledge-materials",
            params={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "sku_id": "SKU-READINESS",
                "size": 100,
            },
        )
        assert scoped_materials.status_code == 200, scoped_materials.text
        assert {item["sku_id"] for item in scoped_materials.json()["items"]} == {
            None,
            "SKU-READINESS",
        }
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous


def test_run_freezes_latest_reviewed_product_and_exact_sku_with_one_draft_overlay(
    client: TestClient, session: Session
) -> None:
    _seed(session)
    _add_material(session, material_id="KMT-AUTO-PRODUCT", revision=1, sku_id=None, status="APPROVED_FOR_ANALYSIS", size="30cm", particles="1000颗")
    product_latest = _add_material(session, material_id="KMT-AUTO-PRODUCT", revision=2, sku_id=None, status="ANALYZED", size="35cm", particles="1100颗")
    _add_material(session, material_id="KMT-AUTO-SKU", revision=1, sku_id="SKU-READINESS", status="APPROVED_FOR_ANALYSIS", size="40cm", particles="1200颗")
    _add_material(session, material_id="KMT-OTHER-SKU", revision=1, sku_id="SKU-OTHER", status="ANALYZED", size="50cm", particles="1500颗")
    _add_material(session, material_id="KMT-REJECTED", revision=1, sku_id=None, status="REJECTED", size="60cm", particles="1600颗")
    _add_material(session, material_id="KMT-OVERLAY", revision=1, sku_id="SKU-READINESS", status="ANALYZED", size="38cm", particles="1180颗")
    overlay = _add_material(session, material_id="KMT-OVERLAY", revision=2, sku_id="SKU-READINESS", status="REVIEWING", size="42cm", particles="1250颗")
    session.commit()

    evaluator = _SyntheticEvaluator()
    previous = getattr(app.state, "reply_readiness_ai_client", None)
    app.state.reply_readiness_ai_client = evaluator
    try:
        created = client.post(
            "/api/v1/admin/reply-readiness/runs",
            json={
                "store_code": "STORE-READINESS",
                "product_id": "PRODUCT-READINESS",
                "sku_id": "SKU-READINESS",
                "material_id": overlay.material_id,
                "material_revision": overlay.revision,
            },
            headers={"Idempotency-Key": "readiness-aggregate-sources"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["knowledge_source_count"] == 3

        frozen = client.get(
            f"/api/v1/internal/reply-readiness/runs/{created.json()['run_id']}/input"
        )
        assert frozen.status_code == 200, frozen.text
        sources = frozen.json()["knowledge_sources"]
        assert [(item["material_id"], item["revision"]) for item in sources] == [
            ("KMT-AUTO-PRODUCT", 2),
            ("KMT-AUTO-SKU", 1),
            ("KMT-OVERLAY", 2),
        ]
        assert all(item["material_id"] not in {"KMT-OTHER-SKU", "KMT-REJECTED"} for item in sources)
        assert frozen.json()["knowledge_snapshot"] is None

        product_latest.analysis_text = _analysis("99cm", "9999颗")
        session.commit()
        frozen_again = client.get(
            f"/api/v1/internal/reply-readiness/runs/{created.json()['run_id']}/input"
        ).json()
        assert frozen_again["knowledge_sources"] == sources
    finally:
        if previous is None:
            delattr(app.state, "reply_readiness_ai_client")
        else:
            app.state.reply_readiness_ai_client = previous


def test_non_draft_overlay_status_fails_closed(client: TestClient, session: Session) -> None:
    _seed(session)
    approved = _add_material(session, material_id="KMT-APPROVED-ONLY", revision=1, sku_id=None, status="ANALYZED", size="35cm", particles="1100颗")
    session.commit()

    response = client.post(
        "/api/v1/admin/reply-readiness/runs",
        json={
            "store_code": "STORE-READINESS",
            "product_id": "PRODUCT-READINESS",
            "material_id": approved.material_id,
            "material_revision": approved.revision,
        },
        headers={"Idempotency-Key": "readiness-approved-is-not-draft"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REPLY_READINESS_MATERIAL_NOT_READY"
