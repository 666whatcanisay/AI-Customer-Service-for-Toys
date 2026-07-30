from io import BytesIO
from datetime import datetime, timezone
import json
import time

from openpyxl import Workbook
from sqlalchemy import func, select

from app.ingestion.models import ImportBatch, ImportReviewRecord, ImportRow
from app.product_knowledge_import.parser import ProductKnowledgeTemplateParser
from app.product_knowledge_import.product_knowledge_mapping import EXPECTED_HEADERS
from app.test_catalog.models import TestProduct as CatalogProduct
from app.test_catalog.models import TestSourceEvidence as SourceEvidence


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def product_knowledge_workbook(
    *,
    store_name: str,
    product_name: str = "积木小屋",
    product_summary: str = "儿童拼装积木玩具。",
    selling_points: str = "拼搭；收纳",
    age: str = "6岁+",
    material: str = "ABS",
    safety: str = "含小零件，建议成人陪同。",
    package_contents: str = "积木；说明书",
    usage: str = "按说明书拼装。",
    play: str = "自由拼搭",
    question: str = "适合几岁？",
    answer_direction: str = "按已确认年龄回答。",
    source_name: str = "包装标签",
    source_date: str = "2026-07-30",
    confirmation: str = "已确认",
    header_row: int = 4,
    field_description_start_row: int = 4,
) -> bytes:
    workbook = Workbook()
    instructions = workbook.active
    instructions.title = "填写说明"
    instructions["A1"] = "商品知识采集模板 V1"

    data = workbook.create_sheet("数据填写")
    data["A1"] = "商品知识采集模板 V1｜数据填写"
    for column, header in enumerate(EXPECTED_HEADERS, start=1):
        data.cell(header_row, column, header)
    values = (
        store_name,
        product_name,
        product_summary,
        selling_points,
        age,
        material,
        safety,
        package_contents,
        usage,
        play,
        question,
        answer_direction,
        source_name,
        source_date,
        confirmation,
        "测试导入",
    )
    for column, value in enumerate(values, start=1):
        data.cell(header_row + 1, column, value)

    example = workbook.create_sheet("示例数据")
    example["A1"] = "商品知识采集模板 V1｜示例数据"
    for column, header in enumerate(EXPECTED_HEADERS, start=1):
        example.cell(header_row, column, header)

    descriptions = workbook.create_sheet("字段说明")
    descriptions.append(["商品知识采集模板 V1｜字段说明"])
    descriptions.append(["固定字段说明"])
    for column, value in enumerate(
        ("字段名称", "字段用途", "是否必填", "知识等级", "AI用途", "填写规则"),
        start=1,
    ):
        descriptions.cell(field_description_start_row - 1, column, value)
    for offset, header in enumerate(EXPECTED_HEADERS):
        row_number = field_description_start_row + offset
        for column, value in enumerate(
            (header, "用途", "选填", "治理", "受控使用", "按模板填写"),
            start=1,
        ):
            descriptions.cell(row_number, column, value)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def create_store(client, name: str = "玩趣乐园积木店-拼多多") -> dict:
    response = client.post(
        "/api/v1/admin/operations/stores",
        json={"store_name": name, "platform": "pinduoduo", "remarks": "R009 测试"},
    )
    assert response.status_code == 201
    return response.json()


def upload(client, store: dict, content: bytes, *, key: str = "upload-key-1"):
    return client.post(
        "/api/v1/admin/product-knowledge-imports",
        data={
            "store_ref": store["store_ref"],
            "template_type": "PRODUCT_KNOWLEDGE",
            "operator": "知识运营",
        },
        files={"file": ("商品知识采集模板V1.xlsx", content, XLSX_MIME)},
        headers={"Idempotency-Key": key},
    )


def test_new_product_upload_is_staged_then_approval_applies_formal_knowledge(
    client, session
):
    store = create_store(client)
    content = product_knowledge_workbook(store_name=store["store_name"])

    response = upload(client, store, content)

    assert response.status_code == 201
    batch = response.json()
    assert batch["status"] == "IDENTIFIED_PENDING_REVIEW"
    assert session.scalar(select(func.count()).select_from(CatalogProduct)) == 0

    preflight = client.get(
        f"/api/v1/admin/product-knowledge-imports/{batch['batch_id']}/preflight"
    )
    assert preflight.status_code == 200
    assert preflight.json()["can_review"] is True
    assert preflight.json()["field_validation_result"]["valid"] is True
    assert [item["sheet_name"] for item in preflight.json()["sheet_results"]] == [
        "填写说明",
        "数据填写",
        "示例数据",
        "字段说明",
    ]
    persisted_evidence = json.loads(session.get(ImportBatch, batch["batch_id"]).template_evidence_json)
    assert persisted_evidence["template_metadata"]["instruction_rows"][0][0] == (
        "商品知识采集模板 V1"
    )
    assert persisted_evidence["template_metadata"]["field_mapping_mode"] == (
        "FIXED_CODE_VALIDATED_BY_WORKBOOK"
    )

    preview_response = client.get(
        f"/api/v1/admin/product-knowledge-imports/{batch['batch_id']}/merge-preview"
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["items"][0]
    assert preview["product"]["operation"] == "CREATE"
    changes = {item["field_label"]: item for item in preview["fields"]}
    assert changes["商品简介"]["change_type"] == "ADD"
    assert changes["商品简介"]["merged_value"] == "儿童拼装积木玩具。"

    product = preview["product"]
    review = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch['batch_id']}/change-sets/{product['change_set_id']}/reviews",
        json={
            "decision": "APPROVE",
            "operator": "知识运营",
            "review_note": "来源已核对",
            "expected_base_snapshot_hash": product["base_snapshot_hash"],
            "expected_change_set_version": product["version"],
        },
        headers={"Idempotency-Key": "review-key-1"},
    )

    assert review.status_code == 201
    receipt = review.json()["review_receipt"]
    assert receipt["outcome"] == "APPLIED"
    saved = session.scalar(select(CatalogProduct))
    assert saved is not None
    assert saved.product_name_display == "积木小屋"
    assert saved.age_min == 6
    assert saved.age_max is None
    assert saved.safety_summary == "含小零件，建议成人陪同。"
    assert saved.publishable is False
    assert saved.review_status == "APPROVED"
    assert json.loads(saved.raw_data_json)["material"] == "ABS"
    assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 1
    assert session.get(ImportBatch, batch["batch_id"]).status == "COMPLETED"

    review_replay = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch['batch_id']}/change-sets/{product['change_set_id']}/reviews",
        json={
            "decision": "APPROVE",
            "operator": "知识运营",
            "review_note": "来源已核对",
            "expected_base_snapshot_hash": product["base_snapshot_hash"],
            "expected_change_set_version": product["version"],
        },
        headers={"Idempotency-Key": "review-key-1"},
    )
    assert review_replay.status_code == 200
    assert review_replay.headers["Idempotency-Replayed"] == "true"
    assert review_replay.json()["review_receipt"]["receipt_id"] == receipt["receipt_id"]

    reverse_decision = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch['batch_id']}/change-sets/{product['change_set_id']}/reviews",
        json={
            "decision": "REJECT",
            "operator": "知识运营",
            "review_note": "尝试反向审核",
            "expected_base_snapshot_hash": product["base_snapshot_hash"],
            "expected_change_set_version": product["version"],
        },
        headers={"Idempotency-Key": "reverse-review-key"},
    )
    assert reverse_decision.status_code == 409

    replay = upload(client, store, content)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["batch_id"] == batch["batch_id"]
    assert replay.json()["status"] == "COMPLETED"


def test_real_template_layout_is_detected_and_optional_governance_fields_are_defaulted(
    client, session
):
    store = create_store(client)
    content = product_knowledge_workbook(
        store_name=store["store_name"],
        source_date="",
        confirmation="",
        header_row=5,
        field_description_start_row=5,
    )

    parsed = ProductKnowledgeTemplateParser().parse(
        content,
        max_rows=100,
        imported_at=datetime(2026, 7, 30, 9, 15, tzinfo=timezone.utc),
    )
    assert parsed.field_validation_result["valid"] is True
    assert parsed.template_metadata["detected_header_rows"] == {
        "数据填写": 5,
        "示例数据": 5,
    }
    assert parsed.template_metadata["field_description_start_row"] == 5
    assert parsed.products[0].source_date == "2026-07-30"
    assert parsed.products[0].source_date_origin == "SYSTEM_IMPORT_DATE"
    assert parsed.products[0].human_confirmation is None

    response = upload(client, store, content, key="real-template-layout")
    assert response.status_code == 201
    batch_id = response.json()["batch_id"]
    assert response.json()["status"] == "IDENTIFIED_PENDING_REVIEW"
    batch = session.get(ImportBatch, batch_id)
    row = session.scalar(select(ImportRow).where(ImportRow.batch_id == batch_id))
    normalized = json.loads(row.normalized_data_json)
    assert normalized["source_date"] == batch.created_at.date().isoformat()
    assert normalized["source_date_origin"] == "SYSTEM_IMPORT_DATE"
    assert normalized["human_confirmation"] is None

    preview = client.get(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview"
    ).json()["items"][0]
    change_set = preview["product"]
    approved = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set['change_set_id']}/reviews",
        json={
            "decision": "APPROVE",
            "operator": "知识运营",
            "review_note": "系统人工审核通过",
            "expected_base_snapshot_hash": change_set["base_snapshot_hash"],
            "expected_change_set_version": change_set["version"],
        },
        headers={"Idempotency-Key": "real-template-review"},
    )
    assert approved.status_code == 201
    saved = session.scalar(select(CatalogProduct))
    assert saved.review_status == "APPROVED"
    assert session.get(ImportBatch, batch_id).status == "COMPLETED"


def test_existing_product_merge_keeps_blank_fields_and_reject_writes_no_formal_data(
    client, session
):
    store = create_store(client)
    created = client.post(
        f"/api/v1/admin/operations/stores/{store['store_ref']}/products",
        json={"product_name": "积木小屋", "product_summary": "旧简介"},
    )
    assert created.status_code == 201
    product = session.get(CatalogProduct, created.json()["product_ref"])
    raw = json.loads(product.raw_data_json)
    raw["material"] = "ABS"
    product.raw_data_json = json.dumps(raw, ensure_ascii=False)
    session.commit()

    content = product_knowledge_workbook(
        store_name=store["store_name"],
        product_summary="新简介",
        material="",
    )
    response = upload(client, store, content, key="existing-upload")
    assert response.status_code == 201
    batch_id = response.json()["batch_id"]
    preview = client.get(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview"
    ).json()["items"][0]
    fields = {item["field_label"]: item for item in preview["fields"]}
    assert preview["product"]["operation"] == "UPDATE"
    assert fields["商品名称"]["change_type"] == "NO_CHANGE"
    assert fields["商品简介"]["change_type"] == "UPDATE"
    assert fields["材质信息"]["change_type"] == "KEEP"
    assert fields["材质信息"]["merged_value"] == "ABS"

    change_set = preview["product"]
    rejected = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set['change_set_id']}/reviews",
        json={
            "decision": "REJECT",
            "operator": "知识运营",
            "review_note": "资料来源待复核",
            "expected_base_snapshot_hash": change_set["base_snapshot_hash"],
            "expected_change_set_version": change_set["version"],
        },
        headers={"Idempotency-Key": "reject-key"},
    )
    assert rejected.status_code == 201
    assert rejected.json()["review_receipt"]["outcome"] == "REJECTED"
    session.refresh(product)
    assert json.loads(product.raw_data_json)["product_summary"] == "旧简介"
    assert session.scalar(select(func.count()).select_from(ImportReviewRecord)) == 1


def test_store_scope_mismatch_persists_preflight_failure_without_formal_write(client, session):
    store = create_store(client)
    response = upload(
        client,
        store,
        product_knowledge_workbook(store_name="其他店铺"),
        key="scope-mismatch",
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PREFLIGHT_FAILED"
    preflight = client.get(
        f"/api/v1/admin/product-knowledge-imports/{response.json()['batch_id']}/preflight"
    ).json()
    assert preflight["can_review"] is False
    issue = next(
        item
        for item in preflight["field_validation_result"]["issues"]
        if item["code"] == "STORE_SCOPE_MISMATCH"
    )
    assert "当前选择店铺" in issue["message"]
    assert "Excel 数据所属店铺" in issue["message"]
    assert session.scalar(select(func.count()).select_from(CatalogProduct)) == 0


def test_existing_product_approval_updates_nonblank_fields_and_preserves_blank_fields(
    client, session
):
    store = create_store(client)
    created = client.post(
        f"/api/v1/admin/operations/stores/{store['store_ref']}/products",
        json={"product_name": "积木小屋", "product_summary": "旧简介"},
    ).json()
    product = session.get(CatalogProduct, created["product_ref"])
    raw = json.loads(product.raw_data_json)
    raw["material"] = "ABS"
    raw["package_contents"] = "旧包装"
    product.raw_data_json = json.dumps(raw, ensure_ascii=False)
    session.commit()

    response = upload(
        client,
        store,
        product_knowledge_workbook(
            store_name=store["store_name"],
            product_summary="新简介",
            material="",
            package_contents="礼盒",
        ),
        key="merge-approval-upload",
    )
    batch_id = response.json()["batch_id"]
    preview = client.get(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/merge-preview"
    ).json()["items"][0]
    change_set = preview["product"]
    approved = client.post(
        f"/api/v1/admin/product-knowledge-imports/{batch_id}/change-sets/{change_set['change_set_id']}/reviews",
        json={
            "decision": "APPROVE",
            "operator": "知识运营",
            "review_note": "核对通过",
            "expected_base_snapshot_hash": change_set["base_snapshot_hash"],
            "expected_change_set_version": change_set["version"],
        },
        headers={"Idempotency-Key": "merge-approval-review"},
    )
    assert approved.status_code == 201
    session.refresh(product)
    merged = json.loads(product.raw_data_json)
    assert merged["product_summary"] == "新简介"
    assert merged["material"] == "ABS"
    assert merged["package_contents"] == "礼盒"


def test_other_templates_are_explicitly_unavailable(client):
    store = create_store(client)
    response = client.post(
        "/api/v1/admin/product-knowledge-imports",
        data={
            "store_ref": store["store_ref"],
            "template_type": "FAQ",
            "operator": "知识运营",
        },
        files={
            "file": (
                "客服FAQ知识采集模板V1.xlsx",
                product_knowledge_workbook(store_name=store["store_name"]),
                XLSX_MIME,
            )
        },
        headers={"Idempotency-Key": "unsupported-template"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "该模板导入功能暂未开放"


def test_missing_product_name_is_blocked_before_formal_write(client, session):
    store = create_store(client)
    response = upload(
        client,
        store,
        product_knowledge_workbook(
            store_name=store["store_name"],
            product_name="",
        ),
        key="missing-product-name",
    )

    assert response.status_code == 201
    assert response.json()["status"] == "PREFLIGHT_FAILED"
    preflight = client.get(
        f"/api/v1/admin/product-knowledge-imports/{response.json()['batch_id']}/preflight"
    ).json()
    missing = [
        issue
        for issue in preflight["field_validation_result"]["issues"]
        if issue["code"] == "REQUIRED_FIELD_MISSING"
    ]
    assert any(issue["field"] == "商品名称" for issue in missing)
    assert session.scalar(select(func.count()).select_from(CatalogProduct)) == 0


def test_parser_handles_100_rows_within_stability_budget():
    class Cell:
        def __init__(self, value):
            self.value = value

    class SyntheticSheet:
        max_row = 105

        def cell(self, row, column):
            if row <= 5:
                return Cell(None)
            values = {
                1: "玩趣乐园积木店-拼多多",
                2: f"稳定性批量商品-{row - 5:03d}",
                3: "100 条纯代码解析稳定性样例",
                14: "2026-07-30",
            }
            return Cell(values.get(column, ""))

    parser = ProductKnowledgeTemplateParser()
    started = time.perf_counter()
    products, issues = parser._parse_data_rows(
        SyntheticSheet(),
        header_row=5,
        max_rows=100,
        system_import_date="2026-07-30",
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert len(products) == 100
    assert not any(issue["code"] == "ROW_LIMIT_EXCEEDED" for issue in issues)
    assert elapsed_ms < 1000
