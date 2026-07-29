"""C product-knowledge projection and non-fabrication acceptance tests."""

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.config import get_settings
from app.knowledge_materials.models import KnowledgeMaterial, KnowledgeQualityAssessment
from app.test_catalog.models import (
    TestFaq as CatalogFaq,
    TestKnowledgePackage as CatalogPackage,
    TestProduct as CatalogProduct,
    TestSku as CatalogSku,
    TestSourceEvidence as CatalogSourceEvidence,
    TestStore as CatalogStore,
)


def _seed_catalog(session: Session) -> None:
    package = CatalogPackage(
        package_id="PKG-KNOWLEDGE-01",
        package_name="商品知识运营验收包",
        version="1.0.0",
        schema_version="1.0",
        tenant_id="tenant-hidden",
        platform="pinduoduo",
        store_code="mumu-pdd",
        response_mode="SUGGEST_ONLY",
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=False,
        import_status="IMPORTED",
        original_filename="catalog.xlsx",
        zip_sha256="a" * 64,
        counts_json="{}",
        imported_by="tester",
    )
    store = CatalogStore(
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        store_name="木木小栈拼多多旗舰店",
        trial_enabled=True,
        knowledge_scope="TEST_ONLY",
        response_mode="SUGGEST_ONLY",
        allow_auto_send=False,
        test_data_mode=True,
        production_usable=False,
        raw_data_json="{}",
    )
    complete = CatalogProduct(
        product_id="PRODUCT-Q66",
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        product_name_official="Q66城市消防局机械积木玩具套装",
        product_name_display="Q66城市消防局机械积木玩具套装",
        sales_status="ON_SALE",
        age_min=8,
        age_max=14,
        safety_summary="采用合规 ABS 材质，内含小零件，需成人陪同。",
        review_status="APPROVED",
        publishable=True,
        source_ids_json='["SRC-Q66"]',
        raw_data_json=json.dumps(
            {
                "product_summary": "城市消防主题机械积木套装。",
                "main_selling_points": "机械联动；消防场景玩法",
                "material": "ABS 塑料",
                "package_contents": "积木零件、说明书、贴纸",
                "assembly_summary": "按说明书分步骤拼装。",
                "play_method": "可进行消防救援情景游戏。",
                "assembled_size": "32×18×20cm",
            },
            ensure_ascii=False,
        ),
    )
    incomplete = CatalogProduct(
        product_id="PRODUCT-BASIC",
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        product_name_official="城市巡逻车积木",
        product_name_display="城市巡逻车积木",
        sales_status="ON_SALE",
        age_min=None,
        age_max=None,
        safety_summary=None,
        review_status="REVIEWING",
        publishable=False,
        source_ids_json="[]",
        raw_data_json=json.dumps(
            {"product_summary": "可拼装的城市巡逻车模型。"}, ensure_ascii=False
        ),
    )
    luxury_sku = CatalogSku(
        sku_id="SKU-Q66-LUXURY",
        package_id=package.package_id,
        product_id=complete.product_id,
        sku_code="Q66-L",
        sku_name_official="豪华版",
        sku_name_display="豪华版",
        relation_type="INDEPENDENT",
        canonical_sku_id=None,
        reference_sku_id=None,
        component_sku_refs_json="[]",
        publishable=True,
        source_ids_json='["SRC-Q66"]',
        raw_data_json=json.dumps(
            {
                "color": "红色",
                "particle_count": 1280,
                "difference_summary": "含灯光组件和两个人仔。",
            },
            ensure_ascii=False,
        ),
    )
    basic_sku = CatalogSku(
        sku_id="SKU-BASIC",
        package_id=package.package_id,
        product_id=incomplete.product_id,
        sku_code="BASIC-01",
        sku_name_official="标准版",
        sku_name_display="标准版",
        relation_type="INDEPENDENT",
        canonical_sku_id=None,
        reference_sku_id=None,
        component_sku_refs_json="[]",
        publishable=False,
        source_ids_json="[]",
        raw_data_json=json.dumps({"difference_summary": "已确认无差异"}, ensure_ascii=False),
    )
    faq = CatalogFaq(
        faq_id="FAQ-Q66-INTRO",
        package_id=package.package_id,
        tenant_id=package.tenant_id,
        platform=package.platform,
        store_code=package.store_code,
        product_id=complete.product_id,
        sku_id=None,
        canonical_question="这款积木有什么特点？",
        recommended_reply="这是一款消防主题机械积木，支持机械联动玩法。",
        answer_action="DIRECT_ANSWER",
        risk_level="LOW",
        source_ids_json='["SRC-Q66"]',
        raw_data_json="{}",
    )
    source = CatalogSourceEvidence(
        source_id="SRC-Q66",
        package_id=package.package_id,
        product_id=complete.product_id,
        sku_id=None,
        source_type="PRODUCT_MANUAL",
        file_name="Q66商品说明.pdf",
        relative_path="private/raw/Q66商品说明.pdf",
        file_sha256="b" * 64,
        metadata_json=json.dumps({"review_status": "APPROVED"}),
    )
    material = KnowledgeMaterial(
        id="material-record-q66",
        material_id="KMT-Q66",
        revision=1,
        store_code=package.store_code,
        product_id=complete.product_id,
        sku_id=None,
        material_type="PRODUCT_SPEC",
        display_name="Q66商品知识补充资料",
        original_filename="Q66补充资料.xlsx",
        content_hash="c" * 64,
        redaction_version="v1-reminder-only",
        recognition_summary={
            "readable": True,
            "file_extension": ".xlsx",
            "detected_fields": ["商品名称", "核心卖点"],
            "missing_expected_fields": [],
            "privacy_reminder": "测试资料",
        },
        analysis_text="受控资料摘要",
        raw_storage_path="private/uploads/q66.xlsx",
        material_status="ANALYZED",
        submitted_by="operator",
    )
    assessment = KnowledgeQualityAssessment(
        id="assessment-record-q66",
        assessment_id="KQA-Q66",
        material_record_id=material.id,
        material_id=material.material_id,
        revision=1,
        content_hash=material.content_hash,
        analysis_run_id="run-q66",
        model_version="test-model",
        prompt_version="test-prompt",
        overall_status="ANALYZED",
        summary="资料可用，但缺少保养说明。",
        gaps=[
            {
                "gap_id": "KQG-Q66-CARE",
                "gap_code": "CARE_GUIDE_MISSING",
                "severity": "MEDIUM",
                "title": "缺少保养说明",
                "description": "未说明积木清洁方式。",
                "recommended_action": "补充清洁和存放建议。",
                "status": "OPEN",
            }
        ],
    )
    session.add_all(
        [
            package,
            store,
            complete,
            incomplete,
            luxury_sku,
            basic_sku,
            faq,
            source,
            material,
            assessment,
        ]
    )
    session.commit()


def _filled_public_template(filename: str, row: dict[str, object]) -> bytes:
    template_path = Path(__file__).resolve().parents[2] / "admin_web" / "public" / "templates" / filename
    workbook = load_workbook(template_path)
    worksheet = workbook["数据填写"]
    header_row = next(
        index for index in range(1, 31)
        if "店铺名称" in [worksheet.cell(index, column).value for column in range(1, worksheet.max_column + 1)]
    )
    headers = [worksheet.cell(header_row, column).value for column in range(1, worksheet.max_column + 1)]
    for column, header in enumerate(headers, start=1):
        worksheet.cell(header_row + 1, column).value = row.get(str(header), "")
    payload = BytesIO()
    workbook.save(payload)
    workbook.close()
    return payload.getvalue()


def test_overview_uses_source_data_and_hides_tenant(client: TestClient, session: Session) -> None:
    _seed_catalog(session)

    response = client.get("/api/v1/admin/product-knowledge/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["store_count"] == 1
    assert payload["stats"]["product_count"] == 2
    assert payload["stores"][0]["store_name"] == "木木小栈拼多多旗舰店"
    assert "tenant_id" not in response.text
    assert payload["boundary_note"].endswith("不代表知识已发布到 RAG。")


def test_overview_returns_no_statistics_when_catalog_is_empty(client: TestClient) -> None:
    response = client.get("/api/v1/admin/product-knowledge/overview")

    assert response.status_code == 200
    assert response.json()["has_data"] is False
    assert all(value is None for value in response.json()["stats"].values())


def test_detail_covers_intro_age_and_sku_difference_scenarios(
    client: TestClient, session: Session
) -> None:
    _seed_catalog(session)

    response = client.get("/api/v1/admin/product-knowledge/products/PRODUCT-Q66")

    assert response.status_code == 200
    payload = response.json()
    topic_status = {item["key"]: item["status"] for item in payload["topic_coverage"]}
    assert topic_status["product_summary"] == "SUPPORTED"
    assert topic_status["age"] == "SUPPORTED"
    assert topic_status["sku_difference"] == "SUPPORTED"
    assert payload["product"]["applicable_age"] == "8—14 岁"
    assert payload["skus"][0]["sku_name"] == "豪华版"
    assert any(item["question"] == "这款积木有什么特点？" for item in payload["faqs"])
    assert any(item["key"] == "CARE_GUIDE_MISSING" for item in payload["gaps"])
    assert "private/raw" not in response.text
    assert "raw_storage_path" not in response.text


def test_incomplete_product_remains_usable_but_never_invents_age(
    client: TestClient, session: Session
) -> None:
    _seed_catalog(session)

    response = client.get("/api/v1/admin/product-knowledge/products/PRODUCT-BASIC")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_usable"] is True
    assert payload["product"]["applicable_age"] is None
    age_gap = next(item for item in payload["gaps"] if item["key"] == "MISSING_AGE")
    assert age_gap["safe_fallback"] == "当前资料未提供年龄信息，建议人工确认。"


def test_unknown_product_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/admin/product-knowledge/products/NOT-FOUND")

    assert response.status_code == 404


def test_v2_separates_data_status_ai_status_and_gap_workflow(
    client: TestClient, session: Session
) -> None:
    _seed_catalog(session)

    complete = client.get("/api/v1/admin/product-knowledge/products/PRODUCT-Q66").json()
    incomplete = client.get("/api/v1/admin/product-knowledge/products/PRODUCT-BASIC").json()
    gaps = client.get("/api/v1/admin/product-knowledge/gaps").json()

    assert complete["data_status"] == "APPROVED"
    assert complete["ai_status"] == "EFFECTIVE"
    assert incomplete["ai_status"] == "UNCONFIRMED"
    assert incomplete["skus"][0]["specification_difference"] == "已确认无差异"
    assert incomplete["skus"][0]["difference_confirmed"] is True
    age_gap = next(
        item for item in gaps["items"]
        if item["product_name"] == "城市巡逻车积木" and item["missing_topic"] == "适用年龄"
    )
    assert age_gap["workflow_status"] == "PENDING"
    assert age_gap["priority"] == "P1"
    assert all("product_id" not in item for item in gaps["items"])


def test_chinese_product_template_is_scope_checked_and_recognized(
    client: TestClient, session: Session, tmp_path, monkeypatch
) -> None:
    _seed_catalog(session)
    monkeypatch.setenv("PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR", str(tmp_path / "controlled"))
    get_settings.cache_clear()
    content = _filled_public_template(
        "商品知识采集模板V1.xlsx",
        {
            "店铺名称": "木木小栈拼多多旗舰店",
            "商品名称": "Q66城市消防局机械积木玩具套装",
            "商品简介": "消防主题机械积木。",
            "核心卖点": "机械联动",
            "适用年龄": "8—14岁",
            "材质信息": "ABS",
            "安全提醒": "含小零件，需成人陪同。",
            "包装内容": "积木、说明书",
            "使用说明": "按说明书拼装。",
            "客户常问问题": "适合几岁？",
            "资料来源": "商品说明书第2页",
            "来源日期": "2026-07-20",
            "是否人工确认": "是",
        },
    )
    try:
        response = client.post(
            "/api/v1/admin/knowledge-materials",
            data={
                "store_code": "mumu-pdd",
                "product_id": "PRODUCT-Q66",
                "material_type": "PRODUCT_SPEC",
                "template_type": "PRODUCT_KNOWLEDGE",
                "display_name": "Q66商品知识补充",
                "submitted_by": "运营测试",
            },
            files={"file": ("商品知识采集模板V1.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Idempotency-Key": "template-product-001"},
        )
        assert response.status_code == 201, response.text
        summary = response.json()["recognition_summary"]
        assert summary["template_type"] == "PRODUCT_KNOWLEDGE"
        assert summary["record_count"] == 1
        assert "适用年龄" in summary["detected_fields"]
        assert "资料来源" in summary["detected_fields"]
    finally:
        get_settings.cache_clear()


def test_feedback_template_can_be_reviewed_but_is_never_exported_as_ai_knowledge(
    client: TestClient, session: Session, tmp_path, monkeypatch
) -> None:
    _seed_catalog(session)
    monkeypatch.setenv("PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR", str(tmp_path / "controlled"))
    get_settings.cache_clear()
    row = {
        "问题时间": "2026-07-20T10:00:00",
        "店铺名称": "木木小栈拼多多旗舰店",
        "商品名称": "Q66城市消防局机械积木玩具套装",
        "SKU名称": "全部SKU",
        "客户问题": "豪华版和标准版有什么区别？",
        "AI回答结果": "未说明灯光组件差异。",
        "客服处理结果": "依据商品说明书人工补充。",
        "反馈分类": "SKU错误",
        "问题严重程度": "中",
        "建议补充内容": "补充SKU差异知识。",
        "处理状态": "确认缺口",
        "是否已去除敏感信息": "已去除",
        "备注": "不含客户身份信息",
    }
    try:
        created = client.post(
            "/api/v1/admin/knowledge-materials",
            data={
                "store_code": "mumu-pdd",
                "product_id": "PRODUCT-Q66",
                "material_type": "OTHER",
                "template_type": "AI_FEEDBACK",
                "display_name": "Q66客服AI问题反馈",
                "submitted_by": "运营测试",
            },
            files={"file": ("客服AI问题反馈.json", json.dumps(row, ensure_ascii=False).encode("utf-8"), "application/json")},
            headers={"Idempotency-Key": "template-feedback-001"},
        )
        assert created.status_code == 201, created.text
        reviewed = client.post(
            f"/api/v1/admin/knowledge-materials/{created.json()['material_id']}/review",
            json={
                "revision": 1,
                "decision": "APPROVE_FOR_ANALYSIS",
                "reviewed_by": "运营审核员",
                "review_note": "已确认内容完成去标识化，仅用于C端问题闭环。",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["material_status"] == "APPROVED_FOR_ANALYSIS"
        exported = client.get("/api/v1/admin/knowledge-quality/analysis-inputs")
        assert exported.status_code == 200
        assert exported.json()["total"] == 0
    finally:
        get_settings.cache_clear()
