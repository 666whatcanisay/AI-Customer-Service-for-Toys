from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.models import ImportBatch, ImportRow, StagedProductSku
from app.test_catalog.models import (
    TestConflictRecord as ConflictRecordModel,
    TestEvaluationCase as EvaluationCaseModel,
    TestFaq as FaqModel,
    TestKnowledgePackage as KnowledgePackageModel,
    TestProduct as ProductModel,
    TestSafetyRule as SafetyRuleModel,
    TestSku as SkuModel,
    TestSourceEvidence as SourceEvidenceModel,
    TestStore as StoreModel,
)
from app.test_catalog.parser import (
    EXPECTED_COUNTS,
    EXPECTED_SHEET_NAMES,
    SHEET_HEADERS,
)

ZIP_MIME = "application/zip"
PREFLIGHT_URL = "/api/v1/test-data-packages/preflight"
IMPORT_URL = "/api/v1/test-data-packages"
PACKAGE_ID = "PDD-SM-2026-001-TEST"


def _row(sheet: str, **values: object) -> dict[str, object]:
    return {header: values.get(header) for header in SHEET_HEADERS[sheet]}


def _workbook(attachment_hashes: dict[str, str]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    rows: dict[str, list[dict[str, object]]] = {
        "00_版本与试点范围": [
            _row(
                "00_版本与试点范围",
                data_package_id=PACKAGE_ID,
                version="V0.3.1",
                tenant_id="TENANT-PDD-SM-TEST",
                platform="pdd",
                store_code="PDD-SM",
                store_name="汕明测试店",
                package_status="TEST_READY_FOR_IMPORT",
                schema_version="0.3.1-test",
                response_mode_default="SUGGESTION_ONLY",
                allow_auto_send_default=False,
            )
        ],
        "01_店铺与数据范围": [
            _row(
                "01_店铺与数据范围",
                platform="pdd",
                store_code="PDD-SM",
                store_name="汕明测试店",
                trial_enabled=True,
                knowledge_scope="STORE_ONLY",
                response_mode_default="SUGGESTION_ONLY",
                allow_auto_send=False,
            )
        ],
        "02_商品主表": [],
        "03_SKU与款式主表": [],
        "04_附件与证据索引": [],
        "05_FAQ与回答策略": [],
        "06_客服安全与权限边界": [],
        "07_AI评测集": [],
        "08_冲突与待确认事项": [],
    }
    for index in range(1, 6):
        rows["02_商品主表"].append(
            _row(
                "02_商品主表",
                product_id=f"P{index}",
                platform="pdd",
                store_code="PDD-SM",
                product_name_official=f"测试商品 {index}",
                product_name_display=f"测试商品 {index}",
                sales_status="ON_SALE",
                age_min=6,
                age_max=12,
                main_selling_points="测试卖点",
                play_method="测试玩法",
                assembly_summary="测试拼装说明",
                safety_summary="含小颗粒，建议成人陪同",
                source_ids=f"SRC-{index:03d}",
                review_status="TEST_CONFIRMED",
                publishable=True,
            )
        )
    for index in range(1, 19):
        relation = "INDEPENDENT"
        canonical = f"SKU-{index:03d}"
        reference = None
        components = None
        if index in {13, 14}:
            relation = "REFERENCE"
            reference = f"SKU-{index - 12:03d}"
            canonical = reference
        if index == 15:
            relation = "BUNDLE"
            components = "SKU-001|SKU-002"
        rows["03_SKU与款式主表"].append(
            _row(
                "03_SKU与款式主表",
                sku_id=f"SKU-{index:03d}",
                product_id=f"P{((index - 1) % 5) + 1}",
                sku_code=f"S{index:03d}",
                sku_name_official=f"测试 SKU {index}",
                sku_name_display=f"测试 SKU {index}",
                particle_count=100 + index,
                package_type="测试包装",
                difference_summary="测试差异",
                source_ids=f"SRC-{((index - 1) % 35) + 1:03d}",
                review_status="TEST_CONFIRMED",
                relation_type=relation,
                canonical_sku_id=canonical,
                reference_sku_id=reference,
                component_sku_refs=components,
                publishable=True,
            )
        )
    attachment_items = list(attachment_hashes.items())
    for index, (path, digest) in enumerate(attachment_items, start=1):
        rows["04_附件与证据索引"].append(
            _row(
                "04_附件与证据索引",
                source_id=f"SRC-{index:03d}",
                product_id=f"P{((index - 1) % 5) + 1}",
                source_type="TEST_IMAGE",
                file_name=path.rsplit("/", 1)[-1],
                relative_path=path,
                file_sha256=digest,
                evidence_description="测试图片证据",
                review_status="TEST_VERIFIED",
            )
        )
    for index in range(36, 38):
        rows["04_附件与证据索引"].append(
            _row(
                "04_附件与证据索引",
                source_id=f"SRC-{index:03d}",
                source_type="TEST_ASSUMPTION",
                evidence_description="无附件测试证据",
                review_status="TEST_VERIFIED",
            )
        )
    actions = [
        "DIRECT_ANSWER",
        "CONTROLLED_ANSWER",
        "ASK_CLARIFY",
        "REQUIRE_LOOKUP",
        "TRANSFER_HUMAN",
        "REFUSE",
    ]
    for index in range(1, 17):
        rows["05_FAQ与回答策略"].append(
            _row(
                "05_FAQ与回答策略",
                faq_id=f"FAQ-{index:03d}",
                platform="pdd",
                store_code="PDD-SM",
                product_id=f"P{((index - 1) % 5) + 1}",
                canonical_question=f"测试问题 {index}",
                recommended_reply=f"测试回答 {index}",
                answer_action=actions[(index - 1) % len(actions)],
                risk_level="HIGH" if index % 3 == 0 else "LOW",
                source_ids=f"SRC-{((index - 1) % 37) + 1:03d}",
                review_status="TEST_CONFIRMED",
                response_mode="SUGGESTION_ONLY",
                allow_auto_send=False,
                publishable=True,
            )
        )
    rule_types = [
        "REALTIME_QUERY_REQUIRED",
        "SUPERVISOR_REQUIRED",
        "FORBIDDEN_PROMISE",
        "CONFIRM_REQUIRED",
    ]
    for index in range(1, 9):
        rows["06_客服安全与权限边界"].append(
            _row(
                "06_客服安全与权限边界",
                rule_id=f"RULE-{index:03d}",
                platform="pdd",
                store_code="PDD-SM",
                scenario=f"测试场景 {index}",
                rule_type=rule_types[(index - 1) % len(rule_types)],
                risk_level="HIGH",
                allowed_action="仅允许测试建议",
                fixed_instruction="保持测试隔离",
                forbidden_claim="禁止自动发送",
                source_id=f"SRC-{index:03d}",
                review_status="TEST_CONFIRMED",
                response_mode="SUGGESTION_ONLY",
                allow_auto_send=False,
                publishable=True,
            )
        )
    for index in range(1, 29):
        rows["07_AI评测集"].append(
            _row(
                "07_AI评测集",
                case_id=f"CASE-{index:03d}",
                case_type="PRODUCT_FACT",
                platform="pdd",
                store_code="PDD-SM",
                product_id=f"P{((index - 1) % 5) + 1}",
                customer_question=f"评测问题 {index}",
                conversation_context=None,
                expected_action=actions[(index - 1) % len(actions)],
                expected_key_facts="事实一；事实二",
                forbidden_claims="禁止一；禁止二",
                expected_source_ids=f"SRC-{((index - 1) % 37) + 1:03d}",
                expected_required_fields="product_id,sku_id",
                risk_level="HIGH" if index % 2 == 0 else "LOW",
                pass_criteria="符合测试预期",
                review_status="PASSED_FOR_DATA_TEST",
                expected_response_mode="SUGGESTION_ONLY",
                allow_auto_send_expected=False,
            )
        )
    for index in range(1, 14):
        rows["08_冲突与待确认事项"].append(
            _row(
                "08_冲突与待确认事项",
                issue_id=f"ISSUE-{index:03d}",
                entity_type="PRODUCT",
                entity_id=f"P{((index - 1) % 5) + 1}",
                field_name="test_field",
                decision="ACCEPT_TEST_ASSUMPTION",
                status="RESOLVED_FOR_TEST",
            )
        )
    for sheet_name in EXPECTED_SHEET_NAMES:
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(SHEET_HEADERS[sheet_name])
        for item in rows[sheet_name]:
            sheet.append([item[header] for header in SHEET_HEADERS[sheet_name]])
        if sheet_name == "00_版本与试点范围":
            sheet.cell(row=4, column=1, value="测试基线说明行，不属于数据记录")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def make_package(
    *,
    version: str = "V0.3.1",
    test_data_mode: bool = True,
    production_usable: bool = False,
    allow_auto_send: bool = False,
    tamper: bool = False,
    traversal: bool = False,
) -> bytes:
    attachments = {
        f"attachments/P{((index - 1) % 5) + 1}/image-{index:03d}.png": f"image-{index}".encode()
        for index in range(1, 36)
    }
    hashes = {path: sha256(content).hexdigest() for path, content in attachments.items()}
    workbook = _workbook(hashes)
    files = {
        "01_company/company.xlsx": workbook,
        "02_middle/middle.xlsx": workbook,
        **attachments,
    }
    manifest_entries = [
        {
            "relative_path": path,
            "size_bytes": len(content),
            "sha256": sha256(content).hexdigest(),
        }
        for path, content in files.items()
    ]
    manifest = {
        "data_package_id": PACKAGE_ID,
        "package_name": "汕明_AI客服双版本数据包_V0.3.1_测试基线版",
        "version": version,
        "schema_version": "0.3.1-test",
        "package_status": "TEST_READY_FOR_IMPORT",
        "overall_status": "PASS",
        "data_gate": "PASS",
        "import_gate": "PASS_FOR_TEST_ENVIRONMENT",
        "tenant_id": "TENANT-PDD-SM-TEST",
        "test_data_mode": test_data_mode,
        "production_usable": production_usable,
        "response_mode": "SUGGESTION_ONLY",
        "allow_auto_send": allow_auto_send,
        "counts": dict(EXPECTED_COUNTS),
        "workbooks": {
            "company": "01_company/company.xlsx",
            "middle": "02_middle/middle.xlsx",
        },
        "file_count_excluding_manifest": len(manifest_entries),
        "files": manifest_entries,
    }
    if tamper:
        files[next(iter(attachments))] = b"IMAGEXX"
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for path, content in files.items():
            archive.writestr(path, content)
        if traversal:
            archive.writestr("../escape.txt", b"blocked")
    return output.getvalue()


def upload(client: TestClient, content: bytes, url: str = IMPORT_URL):
    return client.post(
        url,
        files={"file": ("shanming-v0.3.1.zip", content, ZIP_MIME)},
        data={"imported_by": "pytest"} if url == IMPORT_URL else None,
    )


def count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_valid_package_preflight_writes_nothing(client: TestClient, session: Session) -> None:
    response = upload(client, make_package(), PREFLIGHT_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_import"] is True
    assert body["package_id"] == PACKAGE_ID
    assert body["worksheets"] == EXPECTED_SHEET_NAMES
    assert body["counts"]["products"] == 5
    assert body["counts"]["skus_and_bundles"] == 18
    assert body["counts"]["image_evidence"] == 35
    assert body["counts"]["faqs"] == 16
    assert body["counts"]["safety_rules"] == 8
    assert body["counts"]["evaluation_cases"] == 28
    assert body["test_data_mode"] is True
    assert body["production_usable"] is False
    assert body["allow_auto_send"] is False
    assert count(session, KnowledgePackageModel) == 0


def test_import_persists_exact_test_counts_without_formal_ingestion(
    client: TestClient, session: Session
) -> None:
    response = upload(client, make_package())

    assert response.status_code == 201, response.text
    assert response.json()["import_status"] == "IMPORTED_TEST_ONLY"
    assert count(session, KnowledgePackageModel) == 1
    assert count(session, StoreModel) == 1
    assert count(session, ProductModel) == 5
    assert count(session, SkuModel) == 18
    assert count(session, SourceEvidenceModel) == 37
    assert count(session, FaqModel) == 16
    assert count(session, SafetyRuleModel) == 8
    assert count(session, EvaluationCaseModel) == 28
    assert count(session, ConflictRecordModel) == 13
    assert count(session, ImportBatch) == 0
    assert count(session, ImportRow) == 0
    assert count(session, StagedProductSku) == 0
    evidence = session.scalars(select(SourceEvidenceModel)).first()
    assert evidence is not None
    assert evidence.relative_path.startswith("attachments/")
    assert len(evidence.file_sha256 or "") == 64
    assert not hasattr(evidence, "content")


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        ({"tamper": True}, "MANIFEST_SHA256_MISMATCH"),
        ({"traversal": True}, "ZIP_PATH_TRAVERSAL"),
        ({"version": "V0.3.0"}, "PACKAGE_VERSION_UNSUPPORTED"),
        ({"test_data_mode": False}, "TEST_DATA_MODE_REQUIRED"),
        ({"production_usable": True}, "PRODUCTION_PACKAGE_REJECTED"),
        ({"allow_auto_send": True}, "AUTO_SEND_REJECTED"),
    ],
)
def test_rejects_unsafe_or_non_test_packages(
    client: TestClient, kwargs: dict[str, object], error_code: str
) -> None:
    response = upload(client, make_package(**kwargs), PREFLIGHT_URL)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == error_code


def test_reference_and_bundle_relations_are_preserved(client: TestClient) -> None:
    assert upload(client, make_package()).status_code == 201

    reference = client.get("/api/v1/test-catalog/products/P3/skus").json()
    all_skus = []
    for product_index in range(1, 6):
        all_skus.extend(
            client.get(f"/api/v1/test-catalog/products/P{product_index}/skus").json()["items"]
        )
    references = [item for item in all_skus if item["relation_type"] == "REFERENCE"]
    bundles = [item for item in all_skus if item["relation_type"] == "BUNDLE"]

    assert reference["total"] >= 1
    assert len(references) == 2
    assert references[0]["reference_sku_id"] in {"SKU-001", "SKU-002"}
    assert len(bundles) == 1
    assert bundles[0]["component_sku_refs"] == ["SKU-001", "SKU-002"]


def test_five_frozen_read_only_interfaces_return_database_data(client: TestClient) -> None:
    assert upload(client, make_package()).status_code == 201

    stores = client.get("/api/v1/test-catalog/stores").json()
    products = client.get(
        "/api/v1/test-catalog/products", params={"store_code": "PDD-SM"}
    ).json()
    skus = client.get("/api/v1/test-catalog/products/P1/skus").json()
    rag = client.get(f"/api/v1/test-knowledge-packages/{PACKAGE_ID}/rag-export").json()
    evaluations = client.get(
        f"/api/v1/test-knowledge-packages/{PACKAGE_ID}/evaluations"
    ).json()

    assert stores["total"] == 1
    assert set(stores["items"][0]) == {
        "tenant_id", "platform", "store_code", "store_name", "trial_enabled",
        "knowledge_scope", "response_mode", "allow_auto_send", "test_data_mode",
        "production_usable",
    }
    assert products["total"] == 5
    assert set(products["items"][0]) == {
        "product_id", "platform", "store_code", "product_name_official",
        "product_name_display", "sales_status", "age_min", "age_max",
        "safety_summary", "review_status", "publishable",
    }
    assert skus["total"] > 0
    assert set(skus["items"][0]) == {
        "sku_id", "product_id", "sku_code", "sku_name_official", "sku_name_display",
        "relation_type", "canonical_sku_id", "reference_sku_id",
        "component_sku_refs", "publishable",
    }
    assert isinstance(skus["items"][0]["component_sku_refs"], list)
    assert rag["total"] == 47
    assert rag["tenant_id"] == "TENANT-PDD-SM-TEST"
    assert rag["test_data_mode"] is True
    assert rag["production_usable"] is False
    assert all(isinstance(item["source_ids"], list) for item in rag["items"])
    assert {item["knowledge_type"] for item in rag["items"]} == {
        "PRODUCT_FACT", "SKU_FACT", "FAQ", "SAFETY_RULE",
    }
    assert set(rag) == {
        "package_id", "version", "schema_version", "tenant_id", "platform",
        "store_code", "test_data_mode", "production_usable", "response_mode",
        "allow_auto_send", "items", "total",
    }
    assert set(rag["items"][0]) == {
        "knowledge_id", "knowledge_type", "tenant_id", "platform", "store_code",
        "product_id", "sku_id", "title", "content", "answer_action", "risk_level",
        "source_ids", "test_data_mode", "production_usable",
    }
    assert evaluations["total"] == 28
    first_case = evaluations["items"][0]
    assert set(evaluations) == {
        "package_id", "version", "schema_version", "tenant_id", "platform",
        "store_code", "test_data_mode", "production_usable", "response_mode",
        "allow_auto_send", "items", "total",
    }
    assert set(first_case) == {
        "case_id", "case_type", "platform", "store_code", "product_id", "sku_id",
        "customer_question", "conversation_context", "expected_action",
        "expected_key_facts", "forbidden_claims", "expected_source_ids",
        "expected_required_fields", "risk_level", "pass_criteria",
        "expected_response_mode", "allow_auto_send_expected",
    }
    assert isinstance(first_case["expected_key_facts"], list)
    assert isinstance(first_case["expected_source_ids"], list)
    assert isinstance(first_case["expected_required_fields"], list)
    assert isinstance(first_case["forbidden_claims"], list)


def test_unknown_package_and_product_use_existing_error_envelope(client: TestClient) -> None:
    package = client.get("/api/v1/test-knowledge-packages/missing/rag-export")
    product = client.get("/api/v1/test-catalog/products/missing/skus")

    assert package.status_code == 404
    assert package.json()["error"]["code"] == "TEST_PACKAGE_NOT_FOUND"
    assert "request_id" in package.json()
    assert product.status_code == 404
    assert product.json()["error"]["code"] == "TEST_PRODUCT_NOT_FOUND"
