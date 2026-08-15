"""Regression coverage for the frozen knowledge-quality loop C provider."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.knowledge_materials.models import KnowledgeMaterial


def _upload(
    client: TestClient,
    *,
    idempotency_key: str = "knowledge-material-001",
    content: bytes = (
        "适用年龄：6-12岁\n安全提示：含小颗粒，建议成人陪同。\n"
        "包装清单：积木、说明书。"
    ).encode("utf-8"),
    material_id: str | None = None,
) -> dict[str, object]:
    data = {
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "material_type": "PRODUCT_SPEC",
        "display_name": "去标识化商品规格",
        "submitted_by": "operations-tester",
    }
    if material_id:
        data["material_id"] = material_id
    response = client.post(
        "/api/v1/admin/knowledge-materials",
        data=data,
        files={"file": ("product-spec.txt", content, "text/plain")},
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response.status_code == 201
    return response.json()


def _analysis_payload(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "material_id": snapshot["material_id"],
        "revision": snapshot["revision"],
        "content_hash": snapshot["content_hash"],
        "analysis_run_id": "KQA-test-run-001",
        "model_version": "qwen3.5:9b",
        "prompt_version": "knowledge-quality-v1",
        "summary": "商品规格已覆盖年龄与安全提示，但运营仍需补充包装规格的来源确认。",
        "gaps": [
            {
                "gap_code": "PACKAGING_SOURCE_CONFIRMATION",
                "severity": "MEDIUM",
                "title": "包装规格来源待核对",
                "description": "资料中未说明包装规格的来源版本。",
                "recommended_action": "运营核对包装清单来源后上传新的资料版本。",
            }
        ],
    }


def test_recorded_pdd_legacy_metadata_has_read_only_compatible_projection(
    client: TestClient, session
) -> None:
    material = KnowledgeMaterial(
        material_id="KMT-PDD-LEGACY",
        revision=1,
        store_code="STORE-ONE",
        product_id="PRODUCT-ONE",
        sku_id=None,
        material_type="PRODUCT_SPEC",
        display_name="脱敏PDD商品资料",
        original_filename="recorded-pdd.json",
        content_hash="sha256:" + "a" * 64,
        recognition_summary={
            "template_type": "PRODUCT_KNOWLEDGE",
            "detected_fields": ["颗粒数量"],
            "missing_expected_fields": [],
            "record_count": 1,
            "privacy_filtered": True,
            "source_origin": "RECORDED_PDD_20260814",
            "reference_answer_visible_to_ai": False,
            "scope_requirement": "PRODUCT_ONLY",
        },
        analysis_text='{"facts":{"particle_count":"约1000颗"}}',
        raw_storage_path="controlled/legacy/source.json",
        material_status="APPROVED_FOR_ANALYSIS",
        submitted_by="operations-tester",
    )
    session.add(material)
    session.commit()

    response = client.get(
        "/api/v1/admin/knowledge-materials",
        params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE"},
    )

    assert response.status_code == 200
    summary = response.json()["items"][0]["recognition_summary"]
    assert summary["readable"] is True
    assert summary["file_extension"] == ".json"
    assert summary["template_type"] == "PRODUCT_KNOWLEDGE"
    assert "source_origin" not in summary
    assert material.recognition_summary["source_origin"] == "RECORDED_PDD_20260814"


def test_unknown_malformed_knowledge_metadata_fails_with_controlled_error(
    client: TestClient, session
) -> None:
    session.add(
        KnowledgeMaterial(
            material_id="KMT-UNKNOWN-LEGACY",
            revision=1,
            store_code="STORE-ONE",
            product_id="PRODUCT-ONE",
            sku_id=None,
            material_type="PRODUCT_SPEC",
            display_name="未知来源资料",
            original_filename="unknown.json",
            content_hash="sha256:" + "b" * 64,
            recognition_summary={"template_type": "PRODUCT_KNOWLEDGE"},
            analysis_text="{}",
            raw_storage_path="controlled/unknown/source.json",
            material_status="RECOGNIZED",
            submitted_by="operations-tester",
        )
    )
    session.commit()

    response = client.get(
        "/api/v1/admin/knowledge-materials",
        params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "KNOWLEDGE_MATERIAL_METADATA_INCOMPATIBLE"


def test_known_legacy_source_with_invalid_field_types_returns_controlled_error(
    client: TestClient, session
) -> None:
    session.add(
        KnowledgeMaterial(
            material_id="KMT-KNOWN-LEGACY-MALFORMED",
            revision=1,
            store_code="STORE-ONE",
            product_id="PRODUCT-ONE",
            sku_id=None,
            material_type="PRODUCT_SPEC",
            display_name="已知来源但字段损坏的资料",
            original_filename="legacy.json",
            content_hash="sha256:" + "c" * 64,
            recognition_summary={
                "template_type": "PRODUCT_KNOWLEDGE",
                "detected_fields": {"not": "a-list"},
                "missing_expected_fields": [],
                "record_count": 1,
                "privacy_filtered": True,
                "source_origin": "RECORDED_PDD_20260814",
            },
            analysis_text="{}",
            raw_storage_path="controlled/legacy/source.json",
            material_status="RECOGNIZED",
            submitted_by="operations-tester",
        )
    )
    session.commit()

    response = client.get(
        "/api/v1/admin/knowledge-materials",
        params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "KNOWLEDGE_MATERIAL_METADATA_INCOMPATIBLE"


def test_controlled_material_lifecycle_export_writeback_and_customer_projection(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR", str(tmp_path / "controlled"))
    get_settings.cache_clear()
    try:
        created = _upload(client)
        assert created["material_id"].startswith("KMT-")
        assert created["revision"] == 1
        assert created["material_status"] == "RECOGNIZED"
        assert created["recognition_summary"]["detected_fields"]

        replay = client.post(
            "/api/v1/admin/knowledge-materials",
            data={
                "store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE",
                "material_type": "PRODUCT_SPEC", "display_name": "去标识化商品规格", "submitted_by": "operations-tester",
            },
            files={"file": ("product-spec.txt", "适用年龄：6-12岁\n安全提示：含小颗粒，建议成人陪同。\n包装清单：积木、说明书。".encode("utf-8"), "text/plain")},
            headers={"Idempotency-Key": "knowledge-material-001"},
        )
        assert replay.status_code == 200
        assert replay.json() == created

        conflict = client.post(
            "/api/v1/admin/knowledge-materials",
            data={
                "store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE",
                "material_type": "PRODUCT_SPEC", "display_name": "去标识化商品规格", "submitted_by": "operations-tester",
            },
            files={"file": ("product-spec.txt", "不同资料".encode("utf-8"), "text/plain")},
            headers={"Idempotency-Key": "knowledge-material-001"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "KNOWLEDGE_MATERIAL_IDEMPOTENCY_CONFLICT"

        listing = client.get("/api/v1/admin/knowledge-materials")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert "analysis_text" not in listing.json()["items"][0]
        detail = client.get(f"/api/v1/admin/knowledge-materials/{created['material_id']}")
        assert detail.status_code == 200
        assert "analysis_text_preview" in detail.json()
        assert "raw_storage_path" not in detail.json()
        assert list((tmp_path / "controlled").rglob("source.txt"))

        customer_before = client.get(
            "/api/v1/customer-knowledge-status",
            params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE"},
        )
        assert customer_before.status_code == 200
        assert customer_before.json()["status"] == "NEEDS_REVIEW"
        assert "analysis_text" not in customer_before.text

        reviewed = client.post(
            f"/api/v1/admin/knowledge-materials/{created['material_id']}/review",
            json={
                "revision": 1,
                "decision": "APPROVE_FOR_ANALYSIS",
                "reviewed_by": "operations-reviewer",
                "review_note": "已确认是去标识化商品资料，可用于质量分析。",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["material_status"] == "APPROVED_FOR_ANALYSIS"

        exports = client.get("/api/v1/admin/knowledge-quality/analysis-inputs")
        assert exports.status_code == 200
        assert exports.json()["total"] == 1
        snapshot = exports.json()["items"][0]
        assert snapshot["material_id"] == created["material_id"]
        assert set(snapshot["recognition_summary"]) == {
            "readable", "file_extension", "detected_fields", "missing_expected_fields", "privacy_reminder"
        }
        assert "适用年龄" in snapshot["analysis_text"]

        recorded = client.post(
            "/api/v1/admin/knowledge-quality/analysis-results", json=_analysis_payload(snapshot)
        )
        assert recorded.status_code == 201, recorded.text
        assert recorded.json()["overall_status"] == "ANALYZED"
        assert recorded.json()["gaps"][0]["status"] == "OPEN"
        assert recorded.json()["gaps"][0]["gap_id"].startswith("KQG-")

        replay_analysis = client.post(
            "/api/v1/admin/knowledge-quality/analysis-results", json=_analysis_payload(snapshot)
        )
        assert replay_analysis.status_code == 200
        assert replay_analysis.json() == recorded.json()

        admin_pool = client.get("/api/v1/admin/knowledge-quality/assessments")
        assert admin_pool.status_code == 200
        assert admin_pool.json()["total"] == 1
        assert "analysis_text" not in admin_pool.text

        customer_after = client.get(
            "/api/v1/customer-knowledge-status",
            params={"store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "sku_id": "SKU-ONE"},
        )
        assert customer_after.status_code == 200
        assert customer_after.json()["status"] == "NEEDS_REVIEW"

        correction = _upload(
            client,
            idempotency_key="knowledge-material-002",
            material_id=str(created["material_id"]),
            content="适用年龄：6-12岁\n安全提示：成人陪同。\n包装清单：已确认包装来源。".encode("utf-8"),
        )
        assert correction["material_id"] == created["material_id"]
        assert correction["revision"] == 2
        old_revision = client.post(
            f"/api/v1/admin/knowledge-materials/{created['material_id']}/review",
            json={
                "revision": 1, "decision": "APPROVE_FOR_ANALYSIS", "reviewed_by": "operations-reviewer", "review_note": "重复审核",
            },
        )
        assert old_revision.status_code == 409
        assert old_revision.json()["error"]["code"] == "KNOWLEDGE_MATERIAL_REVISION_MISMATCH"
    finally:
        get_settings.cache_clear()


def test_material_intake_rejects_possible_personal_identifiers_without_storing_source(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR", str(tmp_path / "controlled"))
    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/admin/knowledge-materials",
            data={
                "store_code": "STORE-ONE", "product_id": "PRODUCT-ONE", "material_type": "PRODUCT_SPEC",
                "display_name": "不合规资料", "submitted_by": "operations-tester",
            },
            files={"file": ("unsafe.txt", "客服电话 13800138000".encode("utf-8"), "text/plain")},
            headers={"Idempotency-Key": "knowledge-material-pii"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "KNOWLEDGE_MATERIAL_VALIDATION_FAILED"
        assert not (tmp_path / "controlled").exists()
    finally:
        get_settings.cache_clear()
