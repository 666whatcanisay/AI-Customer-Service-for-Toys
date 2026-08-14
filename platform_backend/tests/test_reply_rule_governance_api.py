from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.knowledge_publishing.ai_client import (
    AiKnowledgePublicationClient,
    AiKnowledgePublicationUnavailable,
)
from app.knowledge_materials.models import KnowledgeMaterial
from app.reply_rules.models import (
    ReplyRule,
    ReplyRuleEvent,
    ReplyRuleSnapshotPublication,
    ReplyRuleSnapshotPublicationReceipt,
)
from app.test_catalog.models import (
    TestKnowledgePackage as CatalogPackage,
    TestProduct as CatalogProduct,
    TestSku as CatalogSku,
    TestStore as CatalogStore,
)


def _seed_scope(session: Session, *, source_status: str = "APPROVED_FOR_ANALYSIS") -> None:
    package = CatalogPackage(
        package_id="PKG-REPLY-RULE",
        package_name="固定回复规则合成测试包",
        version="1.0.0",
        schema_version="1.0",
        tenant_id="TENANT-RULE",
        platform="pdd",
        store_code="STORE-RULE",
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
        store_name="合成规则测试店",
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
        product_id="PRODUCT-RULE",
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
        sku_id="SKU-RULE",
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
    material = KnowledgeMaterial(
        material_id="KMT-REPLY-RULE-SOURCE",
        revision=1,
        store_code=store.store_code,
        product_id=product.product_id,
        sku_id=None,
        material_type="PRODUCT_SPEC",
        display_name="合成材质来源",
        original_filename="synthetic.txt",
        content_hash="sha256:" + "b" * 64,
        recognition_summary={"readable": True},
        analysis_text="材质信息已由测试审核员确认。",
        raw_storage_path="ignored/synthetic/source.txt",
        material_status=source_status,
        submitted_by="pytest",
        reviewed_by="pytest-reviewer",
        reviewed_at=datetime.now(timezone.utc),
        review_note="合成资料审核通过",
    )
    session.add_all([package, store, product, sku, material])
    session.commit()


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "rule_id": "RULE-MATERIAL-001",
        "tenant_id": "TENANT-RULE",
        "platform": "pdd",
        "scope_kind": "PRODUCT",
        "store_code": "STORE-RULE",
        "product_id": "PRODUCT-RULE",
        "sku_id": None,
        "canonical_question": "这个积木是什么材质？",
        "aliases": ["什么材质", "积木材质"],
        "fixed_reply": "这款商品的材质是{material}。",
        "variable_names": ["material"],
        "action": "DIRECT_ANSWER",
        "risk_level": "LOW",
        "required_context_fields": [
            "tenant_id",
            "platform",
            "store_code",
            "product_id",
        ],
        "prohibited_claims": ["绝对安全"],
        "allow_auto_candidate": True,
        "source_material_ids": ["KMT-REPLY-RULE-SOURCE"],
        "source_confirmed": True,
        "high_risk_source_confirmed": False,
        "effective_from": "2026-01-01T00:00:00Z",
        "effective_to": "2027-08-14T00:00:00Z",
        "change_reason": "建立合成固定回复规则",
    }
    payload.update(overrides)
    return payload


def _create_submit_review(
    client: TestClient, payload: dict[str, object] | None = None
) -> tuple[str, dict[str, object]]:
    created = client.post("/api/v1/admin/reply-rules", json=payload or _payload())
    assert created.status_code == 201, created.text
    rule = created.json()
    rule_id = str(rule["rule_id"])
    submitted = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/submit-review",
        json={"reason": "提交独立人工审核"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "IN_REVIEW"
    return rule_id, rule


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


def _approve(client: TestClient, payload: dict[str, object] | None = None) -> str:
    rule_id, _ = _create_submit_review(client, payload)
    approved = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "synthetic independent review"},
    )
    assert approved.status_code == 200, approved.text
    return rule_id


def _receipt_for(payload: dict[str, object], *, changed: bool = True) -> dict[str, object]:
    rules = payload["rules"]
    assert isinstance(rules, list)
    assert payload["snapshot_fingerprint"] == _canonical_sha256(
        {
            "tenant_id": payload["tenant_id"],
            "platform": payload["platform"],
            "snapshot_revision": payload["snapshot_revision"],
            "rules": rules,
        }
    )
    for rule in rules:
        assert isinstance(rule, dict)
        content = {
            key: value
            for key, value in rule.items()
            if key
            not in {
                "content_fingerprint",
                "status",
                "review",
                "source_materials",
            }
        }
        assert rule["content_fingerprint"] == _canonical_sha256(content)
        assert rule["status"] == "PUBLISHED"
        assert rule["source_materials"] == [
            {
                "material_id": "KMT-REPLY-RULE-SOURCE",
                "revision": 1,
                "content_sha256": "b" * 64,
                "governance_status": "REVIEWED_VALID",
                "scope": {
                    "scope_kind": "PRODUCT",
                    "tenant_id": "TENANT-RULE",
                    "platform": "pdd",
                    "store_code": "STORE-RULE",
                    "product_id": "PRODUCT-RULE",
                    "sku_id": None,
                },
                "reviewed_by": "pytest-reviewer",
                "reviewed_at": rule["source_materials"][0]["reviewed_at"],
            }
        ]
    repository_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "."
    validation = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from app.reply_router.contracts import ReplyRulePublicationV1; "
                "ReplyRulePublicationV1.model_validate_json(sys.stdin.read())"
            ),
        ],
        cwd=repository_root / "backend",
        env=environment,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr
    return {
        "schema_version": "reply-rule-publication-receipt.v1",
        "publication_id": payload["publication_id"],
        "tenant_id": payload["tenant_id"],
        "platform": payload["platform"],
        "snapshot_revision": payload["snapshot_revision"],
        "snapshot_fingerprint": payload["snapshot_fingerprint"],
        "status": "PUBLISHED",
        "changed": changed,
        "accepted_rule_count": len(rules),
        "published_at": "2026-08-14T12:00:00Z",
    }


def test_fixed_reply_rule_review_version_and_minimized_audit(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    rule_id, created = _create_submit_review(client)
    assert created["status"] == "DRAFT"
    assert created["created_by"] == "00000000-0000-0000-0000-000000000001"
    assert len(created["content_fingerprint"]) == 64

    approved = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "资料范围和固定文案均已复核"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["source_material_evidence"][0]["material_id"] == (
        "KMT-REPLY-RULE-SOURCE"
    )
    assert approved.json()["source_material_evidence"][0]["revision"] == 1
    assert approved.json()["source_material_evidence"][0]["content_sha256"] == (
        "b" * 64
    )

    immutable_payload = _payload()
    immutable_payload.pop("rule_id")
    immutable = client.put(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1",
        json={**immutable_payload, "change_reason": "不应修改审核版本"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "REPLY_RULE_STATE_INVALID"

    revision = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions",
        json={"reason": "创建下一版文案"},
    )
    assert revision.status_code == 201, revision.text
    assert revision.json()["rule_version"] == 2
    assert revision.json()["status"] == "DRAFT"
    assert revision.json()["content_fingerprint"] != created["content_fingerprint"]

    # SQLite and fast test clocks can assign the same timestamp to multiple
    # append-only events.  The API must still expose lifecycle order rather
    # than UUID order so the audit is reproducible.
    session.execute(
        update(ReplyRuleEvent)
        .where(ReplyRuleEvent.rule_id == rule_id)
        .values(occurred_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
    )
    session.commit()
    events = client.get(f"/api/v1/admin/reply-rules/{rule_id}/events")
    assert events.status_code == 200
    assert [item["event_type"] for item in events.json()["items"]] == [
        "CREATED",
        "REVIEW_SUBMITTED",
        "APPROVED",
        "REVISION_CREATED",
    ]
    audit_text = json.dumps(events.json(), ensure_ascii=False)
    assert "这个积木是什么材质" not in audit_text
    assert "这款商品的材质" not in audit_text


def test_review_rejects_unreviewed_or_cross_scope_source(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session, source_status="RECOGNIZED")
    rule_id, _ = _create_submit_review(client)
    rejected = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "尝试越过资料审核"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "REPLY_RULE_SOURCE_NOT_APPROVED"
    row = session.query(ReplyRule).filter_by(rule_id=rule_id, rule_version=1).one()
    assert row.status == "IN_REVIEW"


def test_review_rejects_approved_source_outside_rule_scope(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    material = session.query(KnowledgeMaterial).one()
    material.store_code = "STORE-OUTSIDE-RULE-SCOPE"
    session.commit()
    rule_id, _ = _create_submit_review(client)
    rejected = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "尝试引用跨店铺来源"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "REPLY_RULE_SOURCE_SCOPE_MISMATCH"


def test_review_rejects_source_narrower_than_rule_scope(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    material = session.query(KnowledgeMaterial).one()
    material.sku_id = "SKU-RULE"
    session.commit()
    rule_id, _ = _create_submit_review(client)
    rejected = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "尝试把SKU事实推广到商品"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == (
        "REPLY_RULE_SOURCE_SCOPE_TOO_NARROW"
    )


def test_high_risk_rule_requires_independent_source_confirmation(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    payload = _payload(
        rule_id="RULE-HIGH-RISK-001",
        action="TRANSFER_HUMAN",
        risk_level="HIGH",
        allow_auto_candidate=False,
        high_risk_source_confirmed=False,
    )
    rule_id, _ = _create_submit_review(client, payload)
    rejected = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/review",
        json={"decision": "APPROVE", "reason": "高风险来源尚未二次确认"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "REPLY_RULE_HIGH_RISK_UNCONFIRMED"


def test_schema_rejects_unsafe_auto_candidate_and_placeholder_drift(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    unsafe = client.post(
        "/api/v1/admin/reply-rules",
        json=_payload(
            rule_id="RULE-UNSAFE-001",
            action="REQUIRE_LOOKUP",
            allow_auto_candidate=True,
        ),
    )
    assert unsafe.status_code == 422

    placeholder = client.post(
        "/api/v1/admin/reply-rules",
        json=_payload(
            rule_id="RULE-BAD-VARIABLE-001",
            fixed_reply="这款商品从{unknown_origin}发货。",
            variable_names=["ship_origin"],
        ),
    )
    assert placeholder.status_code == 422


def test_catalog_scope_is_verified_before_persistence(
    client: TestClient, session: Session
) -> None:
    _seed_scope(session)
    response = client.post(
        "/api/v1/admin/reply-rules",
        json=_payload(rule_id="RULE-WRONG-SCOPE", product_id="PRODUCT-NOT-FOUND"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPLY_RULE_SCOPE_INVALID"
    assert session.query(ReplyRule).count() == 0


def test_atomic_snapshot_publication_receipt_replay_and_withdrawal(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_scope(session)
    rule_id = _approve(client)
    calls: list[dict[str, object]] = []

    def publish(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        calls.append(payload)
        return _receipt_for(payload)

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish_reply_rules", publish)
    command = {
        "tenant_id": "TENANT-RULE",
        "platform": "pdd",
        "confirmation_note": "publish reviewed fixed replies",
    }
    published = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-publish-001"},
        json=command,
    )
    assert published.status_code == 200, published.text
    assert published.json()["accepted_rule_count"] == 1
    assert published.json()["snapshot_revision"] == 1
    assert session.query(ReplyRule).filter_by(rule_id=rule_id).one().status == "PUBLISHED"
    assert session.query(ReplyRuleSnapshotPublicationReceipt).count() == 1

    replay = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-publish-001"},
        json=command,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == published.json()
    assert len(calls) == 1

    conflict = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-publish-001"},
        json={**command, "confirmation_note": "different operation"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == (
        "REPLY_RULE_PUBLICATION_IDEMPOTENCY_CONFLICT"
    )

    mismatched_change = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-noop-wrong-change"},
        json={**command, "confirmation_note": "no-op receipt must say unchanged"},
    )
    assert mismatched_change.status_code == 502, mismatched_change.text

    def publish_unchanged(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        calls.append(payload)
        return _receipt_for(payload, changed=False)

    monkeypatch.setattr(
        AiKnowledgePublicationClient, "publish_reply_rules", publish_unchanged
    )
    unchanged = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-noop-002"},
        json={**command, "confirmation_note": "record unchanged snapshot receipt"},
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["changed"] is False
    assert unchanged.json()["snapshot_revision"] == 1

    receipts = client.get(
        "/api/v1/admin/reply-rules/publication-receipts",
        params={"tenant_id": "TENANT-RULE", "platform": "pdd"},
    )
    assert receipts.status_code == 200, receipts.text
    assert receipts.json()["total"] == 2

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish_reply_rules", publish)

    withdrawn = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/1/withdraw",
        headers={"Idempotency-Key": "reply-rules-withdraw-001"},
        json={"reason": "withdraw reviewed fixed reply"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["accepted_rule_count"] == 0
    assert withdrawn.json()["snapshot_revision"] == 2
    assert calls[-1]["rules"] == []
    assert session.query(ReplyRule).filter_by(rule_id=rule_id).one().status == "WITHDRAWN"
    assert session.query(ReplyRuleSnapshotPublicationReceipt).count() == 3

    events = client.get(f"/api/v1/admin/reply-rules/{rule_id}/events")
    audit_text = json.dumps(events.json(), ensure_ascii=False)
    assert "canonical_question" not in audit_text
    assert "fixed_reply" not in audit_text


def test_failed_snapshot_sync_preserves_last_published_revision(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_scope(session)
    rule_id = _approve(client)

    monkeypatch.setattr(
        AiKnowledgePublicationClient,
        "publish_reply_rules",
        lambda _client, payload: _receipt_for(payload),
    )
    first = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-baseline-001"},
        json={
            "tenant_id": "TENANT-RULE",
            "platform": "pdd",
            "confirmation_note": "publish baseline",
        },
    )
    assert first.status_code == 200, first.text
    baseline_fingerprint = first.json()["snapshot_fingerprint"]

    revision = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions",
        json={"reason": "prepare replacement"},
    )
    assert revision.status_code == 201, revision.text
    replacement = _payload(
        fixed_reply="Updated reviewed answer: {material}",
        change_reason="replace approved wording",
    )
    replacement.pop("rule_id")
    updated = client.put(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/2",
        json=replacement,
    )
    assert updated.status_code == 200, updated.text
    submitted = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/2/submit-review",
        json={"reason": "review replacement"},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/v1/admin/reply-rules/{rule_id}/versions/2/review",
        json={"decision": "APPROVE", "reason": "approve replacement"},
    )
    assert approved.status_code == 200, approved.text

    def unavailable(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        del payload
        raise AiKnowledgePublicationUnavailable("synthetic A outage")

    monkeypatch.setattr(
        AiKnowledgePublicationClient, "publish_reply_rules", unavailable
    )
    failed = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-failed-002"},
        json={
            "tenant_id": "TENANT-RULE",
            "platform": "pdd",
            "confirmation_note": "attempt replacement",
        },
    )
    assert failed.status_code == 502, failed.text
    assert failed.json()["error"]["code"] == "REPLY_RULE_PUBLICATION_FAILED"

    state = session.query(ReplyRuleSnapshotPublication).one()
    assert state.status == "SYNC_FAILED"
    assert state.snapshot_revision == 1
    assert state.snapshot_fingerprint == baseline_fingerprint
    assert state.rule_count == 1
    versions = {
        row.rule_version: row.status
        for row in session.query(ReplyRule).filter_by(rule_id=rule_id).all()
    }
    assert versions == {1: "PUBLISHED", 2: "APPROVED"}
    assert session.query(ReplyRuleSnapshotPublicationReceipt).count() == 1

    def wrong_receipt(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        receipt = _receipt_for(payload)
        receipt["snapshot_fingerprint"] = "0" * 64
        return receipt

    monkeypatch.setattr(
        AiKnowledgePublicationClient, "publish_reply_rules", wrong_receipt
    )
    rejected_receipt = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-wrong-receipt-003"},
        json={
            "tenant_id": "TENANT-RULE",
            "platform": "pdd",
            "confirmation_note": "reject mismatched receipt",
        },
    )
    assert rejected_receipt.status_code == 502, rejected_receipt.text
    assert session.query(ReplyRuleSnapshotPublicationReceipt).count() == 1
    state = session.query(ReplyRuleSnapshotPublication).one()
    assert state.snapshot_revision == 1
    assert state.snapshot_fingerprint == baseline_fingerprint

    def type_drift_receipt(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        receipt = _receipt_for(payload)
        receipt["snapshot_revision"] = str(receipt["snapshot_revision"])
        return receipt

    monkeypatch.setattr(
        AiKnowledgePublicationClient, "publish_reply_rules", type_drift_receipt
    )
    type_drift = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-type-drift-004"},
        json={
            "tenant_id": "TENANT-RULE",
            "platform": "pdd",
            "confirmation_note": "reject receipt type coercion",
        },
    )
    assert type_drift.status_code == 502, type_drift.text
    assert session.query(ReplyRuleSnapshotPublicationReceipt).count() == 1

    state.status = "GENERATING"
    state.generation_token = "synthetic-active-lease"
    state.generation_started_at = datetime.now(timezone.utc)
    session.commit()

    def must_not_publish(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        del payload
        raise AssertionError("active lease must block the A call")

    monkeypatch.setattr(
        AiKnowledgePublicationClient, "publish_reply_rules", must_not_publish
    )
    concurrent = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-concurrent-005"},
        json={
            "tenant_id": "TENANT-RULE",
            "platform": "pdd",
            "confirmation_note": "must respect active publication lease",
        },
    )
    assert concurrent.status_code == 409, concurrent.text
    assert concurrent.json()["error"]["code"] == "REPLY_RULE_PUBLICATION_IN_PROGRESS"


def test_newer_source_revision_removes_stale_fixed_rule_from_next_snapshot(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_scope(session)
    rule_id = _approve(client)
    calls: list[dict[str, object]] = []

    def publish(
        _client: AiKnowledgePublicationClient, payload: dict[str, object]
    ) -> dict[str, object]:
        calls.append(payload)
        return _receipt_for(payload)

    monkeypatch.setattr(AiKnowledgePublicationClient, "publish_reply_rules", publish)
    command = {
        "tenant_id": "TENANT-RULE",
        "platform": "pdd",
        "confirmation_note": "publish source-bound baseline",
    }
    baseline = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-source-baseline-001"},
        json=command,
    )
    assert baseline.status_code == 200, baseline.text
    assert calls[-1]["rules"][0]["source_materials"][0]["revision"] == 1

    previous = session.query(KnowledgeMaterial).one()
    session.add(
        KnowledgeMaterial(
            material_id=previous.material_id,
            revision=2,
            store_code=previous.store_code,
            product_id=previous.product_id,
            sku_id=previous.sku_id,
            material_type=previous.material_type,
            display_name="合成材质来源修订版",
            original_filename="synthetic-v2.txt",
            content_hash="sha256:" + "c" * 64,
            recognition_summary={"readable": True},
            analysis_text="修订后的合成资料。",
            raw_storage_path="ignored/synthetic/source-v2.txt",
            material_status="APPROVED_FOR_ANALYSIS",
            submitted_by="pytest",
            reviewed_by="pytest-reviewer-v2",
            reviewed_at=datetime.now(timezone.utc),
            review_note="合成资料第二版审核通过",
        )
    )
    session.commit()

    refreshed = client.post(
        "/api/v1/admin/reply-rules/publications",
        headers={"Idempotency-Key": "reply-rules-source-refresh-002"},
        json={**command, "confirmation_note": "remove stale source binding"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["snapshot_revision"] == 2
    assert refreshed.json()["accepted_rule_count"] == 0
    assert calls[-1]["rules"] == []
    assert session.query(ReplyRule).filter_by(rule_id=rule_id).one().status == (
        "WITHDRAWN"
    )
