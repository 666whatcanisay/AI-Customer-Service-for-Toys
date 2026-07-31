"""Transactional persistence and read-only projections for the test catalog."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.test_catalog.models import (
    TestConflictRecord,
    TestEvaluationCase,
    TestFaq,
    TestKnowledgePackage,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestSourceEvidence,
    TestStore,
)
from app.test_catalog.parser import (
    EXPECTED_PLATFORM,
    EXPECTED_RESPONSE_MODE,
    EXPECTED_STORE_CODE,
    EXPECTED_TENANT_ID,
    ParsedTestPackage,
    split_array,
)
from app.test_catalog.schemas import (
    AnswerAction,
    EvaluationItem,
    EvaluationResponse,
    KnowledgeType,
    PackageMetadataResponse,
    ProductItem,
    RagExportItem,
    RagExportResponse,
    SkuItem,
    StoreItem,
    TestPackageSummary,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str) -> Any:
    return json.loads(value)


class TestCatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_package(
        self,
        parsed: ParsedTestPackage,
        *,
        original_filename: str,
        imported_by: str,
    ) -> TestKnowledgePackage:
        if self.session.get(TestKnowledgePackage, parsed.package_id) is not None:
            raise AppError(
                "TEST_PACKAGE_ALREADY_IMPORTED",
                "This test package has already been imported",
                status_code=409,
            )
        manifest = parsed.manifest
        rows = parsed.rows
        metadata = rows["00_版本与试点范围"][0]
        package = TestKnowledgePackage(
            package_id=parsed.package_id,
            package_name=str(manifest["package_name"]),
            version=str(manifest["version"]),
            schema_version=str(manifest["schema_version"]),
            tenant_id=EXPECTED_TENANT_ID,
            platform=EXPECTED_PLATFORM,
            store_code=EXPECTED_STORE_CODE,
            response_mode=EXPECTED_RESPONSE_MODE,
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            import_status="IMPORTED_TEST_ONLY",
            original_filename=original_filename,
            zip_sha256=parsed.file_sha256,
            counts_json=_json(parsed.counts),
            imported_by=imported_by.strip()[:128] or "admin-test-import",
        )
        self.session.add(package)
        try:
            store = rows["01_店铺与数据范围"][0]
            self.session.add(
                TestStore(
                    package_id=parsed.package_id,
                    tenant_id=EXPECTED_TENANT_ID,
                    platform=EXPECTED_PLATFORM,
                    store_code=EXPECTED_STORE_CODE,
                    store_name=str(store["store_name"]),
                    trial_enabled=True,
                    knowledge_scope=str(store["knowledge_scope"]),
                    response_mode=EXPECTED_RESPONSE_MODE,
                    allow_auto_send=False,
                    test_data_mode=True,
                    production_usable=False,
                    data_source="TEST",
                    customer_service_status="DISABLED",
                    raw_data_json=_json(store),
                )
            )
            for row in rows["02_商品主表"]:
                self.session.add(
                    TestProduct(
                        product_id=str(row["product_id"]),
                        package_id=parsed.package_id,
                        tenant_id=EXPECTED_TENANT_ID,
                        platform=EXPECTED_PLATFORM,
                        store_code=EXPECTED_STORE_CODE,
                        product_name_official=str(row["product_name_official"]),
                        product_name_display=str(row["product_name_display"]),
                        sales_status=str(row["sales_status"]),
                        age_min=_optional_int(row.get("age_min")),
                        age_max=_optional_int(row.get("age_max")),
                        safety_summary=_optional_text(row.get("safety_summary")),
                        review_status=str(row["review_status"]),
                        publishable=bool(row["publishable"]),
                        customer_service_status="DISABLED",
                        source_ids_json=_json(split_array(row.get("source_ids"))),
                        raw_data_json=_json(row),
                    )
                )
            self.session.flush()
            for row in rows["03_SKU与款式主表"]:
                self.session.add(
                    TestSku(
                        sku_id=str(row["sku_id"]),
                        package_id=parsed.package_id,
                        product_id=str(row["product_id"]),
                        sku_code=str(row["sku_code"]),
                        sku_name_official=str(row["sku_name_official"]),
                        sku_name_display=str(row["sku_name_display"]),
                        relation_type=str(row["relation_type"]),
                        canonical_sku_id=_optional_text(row.get("canonical_sku_id")),
                        reference_sku_id=_optional_text(row.get("reference_sku_id")),
                        component_sku_refs_json=_json(
                            split_array(row.get("component_sku_refs"), pipe_only=True)
                        ),
                        publishable=bool(row["publishable"]),
                        source_ids_json=_json(split_array(row.get("source_ids"))),
                        raw_data_json=_json(row),
                    )
                )
            for row in rows["04_附件与证据索引"]:
                self.session.add(
                    TestSourceEvidence(
                        source_id=str(row["source_id"]),
                        package_id=parsed.package_id,
                        product_id=_optional_text(row.get("product_id")),
                        sku_id=_optional_text(row.get("sku_id")),
                        source_type=str(row["source_type"]),
                        file_name=_optional_text(row.get("file_name")),
                        relative_path=_optional_text(row.get("relative_path")),
                        file_sha256=_optional_text(row.get("file_sha256")),
                        metadata_json=_json(row),
                    )
                )
            for row in rows["05_FAQ与回答策略"]:
                self.session.add(
                    TestFaq(
                        faq_id=str(row["faq_id"]),
                        package_id=parsed.package_id,
                        tenant_id=EXPECTED_TENANT_ID,
                        platform=EXPECTED_PLATFORM,
                        store_code=EXPECTED_STORE_CODE,
                        product_id=_optional_text(row.get("product_id")),
                        sku_id=_optional_text(row.get("sku_id")),
                        canonical_question=str(row["canonical_question"]),
                        recommended_reply=str(row["recommended_reply"]),
                        answer_action=str(row["answer_action"]),
                        risk_level=str(row["risk_level"]),
                        source_ids_json=_json(split_array(row.get("source_ids"))),
                        raw_data_json=_json(row),
                    )
                )
            for row in rows["06_客服安全与权限边界"]:
                self.session.add(
                    TestSafetyRule(
                        rule_id=str(row["rule_id"]),
                        package_id=parsed.package_id,
                        tenant_id=EXPECTED_TENANT_ID,
                        platform=EXPECTED_PLATFORM,
                        store_code=EXPECTED_STORE_CODE,
                        scenario=str(row["scenario"]),
                        rule_type=str(row["rule_type"]),
                        risk_level=str(row["risk_level"]),
                        source_ids_json=_json(split_array(row.get("source_id"))),
                        raw_data_json=_json(row),
                    )
                )
            for row in rows["07_AI评测集"]:
                self.session.add(
                    TestEvaluationCase(
                        case_id=str(row["case_id"]),
                        package_id=parsed.package_id,
                        platform=EXPECTED_PLATFORM,
                        store_code=EXPECTED_STORE_CODE,
                        product_id=_optional_text(row.get("product_id")),
                        sku_id=_optional_text(row.get("sku_id")),
                        raw_data_json=_json(row),
                    )
                )
            for row in rows["08_冲突与待确认事项"]:
                self.session.add(
                    TestConflictRecord(
                        issue_id=str(row["issue_id"]),
                        package_id=parsed.package_id,
                        entity_type=str(row["entity_type"]),
                        entity_id=str(row["entity_id"]),
                        field_name=str(row["field_name"]),
                        decision=_optional_text(row.get("decision")),
                        status=str(row["status"]),
                        raw_data_json=_json(row),
                    )
                )
            self.session.commit()
            self.session.refresh(package)
            return package
        except Exception:
            self.session.rollback()
            raise

    def list_packages(self) -> list[TestKnowledgePackage]:
        return list(
            self.session.scalars(
                select(TestKnowledgePackage).order_by(TestKnowledgePackage.imported_at.desc())
            )
        )

    def package_summary(self, package: TestKnowledgePackage) -> TestPackageSummary:
        return TestPackageSummary(
            package_id=package.package_id,
            package_name=package.package_name,
            version=package.version,
            schema_version=package.schema_version,
            tenant_id=package.tenant_id,
            platform=package.platform,
            store_code=package.store_code,
            test_data_mode=package.test_data_mode,
            production_usable=package.production_usable,
            response_mode=package.response_mode,
            allow_auto_send=package.allow_auto_send,
            import_status=package.import_status,
            original_filename=package.original_filename,
            zip_sha256=package.zip_sha256,
            counts=_loads(package.counts_json),
            imported_at=package.imported_at,
        )

    def list_stores(self) -> list[StoreItem]:
        stores = list(self.session.scalars(select(TestStore).order_by(TestStore.store_code)))
        return [
            StoreItem(
                tenant_id=item.tenant_id,
                platform=item.platform,
                store_code=item.store_code,
                store_name=item.store_name,
                trial_enabled=item.trial_enabled,
                knowledge_scope=item.knowledge_scope,
                response_mode=item.response_mode,
                allow_auto_send=item.allow_auto_send,
                test_data_mode=item.test_data_mode,
                production_usable=item.production_usable,
            )
            for item in stores
        ]

    def list_products(self, store_code: str | None) -> list[ProductItem]:
        query = select(TestProduct).order_by(TestProduct.product_id)
        if store_code is not None:
            query = query.where(TestProduct.store_code == store_code)
        products = list(self.session.scalars(query))
        return [
            ProductItem(
                product_id=item.product_id,
                platform=item.platform,
                store_code=item.store_code,
                product_name_official=item.product_name_official,
                product_name_display=item.product_name_display,
                sales_status=item.sales_status,
                age_min=item.age_min,
                age_max=item.age_max,
                safety_summary=item.safety_summary,
                review_status=item.review_status,
                publishable=item.publishable,
            )
            for item in products
        ]

    def list_skus(self, product_id: str) -> list[SkuItem]:
        if self.session.get(TestProduct, product_id) is None:
            raise AppError("TEST_PRODUCT_NOT_FOUND", "Test product was not found", status_code=404)
        skus = list(
            self.session.scalars(
                select(TestSku)
                .where(TestSku.product_id == product_id)
                .order_by(TestSku.sku_id)
            )
        )
        return [
            SkuItem(
                sku_id=item.sku_id,
                product_id=item.product_id,
                sku_code=item.sku_code,
                sku_name_official=item.sku_name_official,
                sku_name_display=item.sku_name_display,
                relation_type=item.relation_type,
                canonical_sku_id=item.canonical_sku_id,
                reference_sku_id=item.reference_sku_id,
                component_sku_refs=_loads(item.component_sku_refs_json),
                publishable=item.publishable,
            )
            for item in skus
        ]

    def rag_export(self, package_id: str) -> RagExportResponse:
        package = self._get_package(package_id)
        items: list[RagExportItem] = []
        products = list(
            self.session.scalars(
                select(TestProduct)
                .where(TestProduct.package_id == package_id)
                .order_by(TestProduct.product_id)
            )
        )
        for product in products:
            row = _loads(product.raw_data_json)
            items.append(
                RagExportItem(
                    knowledge_id=f"PRODUCT:{product.product_id}",
                    knowledge_type=KnowledgeType.PRODUCT_FACT,
                    tenant_id=package.tenant_id,
                    platform=product.platform,
                    store_code=product.store_code,
                    product_id=product.product_id,
                    sku_id=None,
                    title=product.product_name_display,
                    content=_join_content(
                        row,
                        "product_name_official", "main_selling_points", "play_method",
                        "assembly_summary", "safety_summary",
                    ),
                    answer_action=AnswerAction.CONTROLLED_ANSWER,
                    risk_level="MEDIUM",
                    source_ids=_loads(product.source_ids_json),
                    test_data_mode=True,
                    production_usable=False,
                )
            )
        skus = list(
            self.session.scalars(
                select(TestSku)
                .where(TestSku.package_id == package_id)
                .order_by(TestSku.sku_id)
            )
        )
        for sku in skus:
            row = _loads(sku.raw_data_json)
            items.append(
                RagExportItem(
                    knowledge_id=f"SKU:{sku.sku_id}",
                    knowledge_type=KnowledgeType.SKU_FACT,
                    tenant_id=package.tenant_id,
                    platform=package.platform,
                    store_code=package.store_code,
                    product_id=sku.product_id,
                    sku_id=sku.sku_id,
                    title=sku.sku_name_display,
                    content=_join_content(
                        row,
                        "sku_name_official", "particle_count", "package_type",
                        "assembled_size", "difference_summary", "bundle_specific_notes",
                    ),
                    answer_action=AnswerAction.CONTROLLED_ANSWER,
                    risk_level="MEDIUM" if sku.relation_type != "INDEPENDENT" else "LOW",
                    source_ids=_loads(sku.source_ids_json),
                    test_data_mode=True,
                    production_usable=False,
                )
            )
        faqs = list(
            self.session.scalars(
                select(TestFaq).where(TestFaq.package_id == package_id).order_by(TestFaq.faq_id)
            )
        )
        for faq in faqs:
            items.append(
                RagExportItem(
                    knowledge_id=f"FAQ:{faq.faq_id}",
                    knowledge_type=KnowledgeType.FAQ,
                    tenant_id=faq.tenant_id,
                    platform=faq.platform,
                    store_code=faq.store_code,
                    product_id=faq.product_id,
                    sku_id=faq.sku_id,
                    title=faq.canonical_question,
                    content=faq.recommended_reply,
                    answer_action=AnswerAction(faq.answer_action),
                    risk_level=faq.risk_level,
                    source_ids=_loads(faq.source_ids_json),
                    test_data_mode=True,
                    production_usable=False,
                )
            )
        rules = list(
            self.session.scalars(
                select(TestSafetyRule)
                .where(TestSafetyRule.package_id == package_id)
                .order_by(TestSafetyRule.rule_id)
            )
        )
        for rule in rules:
            row = _loads(rule.raw_data_json)
            items.append(
                RagExportItem(
                    knowledge_id=f"RULE:{rule.rule_id}",
                    knowledge_type=KnowledgeType.SAFETY_RULE,
                    tenant_id=rule.tenant_id,
                    platform=rule.platform,
                    store_code=rule.store_code,
                    product_id=None,
                    sku_id=None,
                    title=rule.scenario,
                    content=_join_content(
                        row, "allowed_action", "fixed_instruction", "forbidden_claim"
                    ),
                    answer_action=_rule_action(rule.rule_type),
                    risk_level=rule.risk_level,
                    source_ids=_loads(rule.source_ids_json),
                    test_data_mode=True,
                    production_usable=False,
                )
            )
        metadata = self._metadata(package).model_dump()
        return RagExportResponse(**metadata, items=items, total=len(items))

    def evaluations(self, package_id: str) -> EvaluationResponse:
        package = self._get_package(package_id)
        cases = list(
            self.session.scalars(
                select(TestEvaluationCase)
                .where(TestEvaluationCase.package_id == package_id)
                .order_by(TestEvaluationCase.case_id)
            )
        )
        items = []
        for case in cases:
            row = _loads(case.raw_data_json)
            items.append(
                EvaluationItem(
                    case_id=case.case_id,
                    case_type=str(row["case_type"]),
                    platform=case.platform,
                    store_code=case.store_code,
                    product_id=case.product_id,
                    sku_id=case.sku_id,
                    customer_question=str(row["customer_question"]),
                    conversation_context=_optional_text(row.get("conversation_context")),
                    expected_action=AnswerAction(str(row["expected_action"])),
                    expected_key_facts=split_array(row.get("expected_key_facts")),
                    forbidden_claims=split_array(row.get("forbidden_claims")),
                    expected_source_ids=split_array(row.get("expected_source_ids")),
                    expected_required_fields=split_array(row.get("expected_required_fields")),
                    risk_level=str(row["risk_level"]),
                    pass_criteria=str(row["pass_criteria"]),
                    expected_response_mode=str(row["expected_response_mode"]),
                    allow_auto_send_expected=bool(row["allow_auto_send_expected"]),
                )
            )
        metadata = self._metadata(package).model_dump()
        return EvaluationResponse(**metadata, items=items, total=len(items))

    def _get_package(self, package_id: str) -> TestKnowledgePackage:
        package = self.session.get(TestKnowledgePackage, package_id)
        if package is None:
            raise AppError(
                "TEST_PACKAGE_NOT_FOUND", "Test knowledge package was not found", status_code=404
            )
        return package

    @staticmethod
    def _metadata(package: TestKnowledgePackage) -> PackageMetadataResponse:
        return PackageMetadataResponse(
            package_id=package.package_id,
            version=package.version,
            schema_version=package.schema_version,
            tenant_id=package.tenant_id,
            platform=package.platform,
            store_code=package.store_code,
            test_data_mode=package.test_data_mode,
            production_usable=package.production_usable,
            response_mode=package.response_mode,
            allow_auto_send=package.allow_auto_send,
        )

    def table_counts(self, package_id: str) -> dict[str, int]:
        tables = {
            "stores": TestStore,
            "products": TestProduct,
            "skus_and_bundles": TestSku,
            "source_records_total": TestSourceEvidence,
            "faqs": TestFaq,
            "safety_rules": TestSafetyRule,
            "evaluation_cases": TestEvaluationCase,
            "issues": TestConflictRecord,
        }
        return {
            name: int(
                self.session.scalar(
                    select(func.count()).select_from(model).where(model.package_id == package_id)
                )
                or 0
            )
            for name, model in tables.items()
        }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _join_content(row: dict[str, Any], *fields: str) -> str:
    parts = [str(row[field]) for field in fields if row.get(field) not in {None, ""}]
    return "；".join(parts)


def _rule_action(rule_type: str) -> AnswerAction:
    return {
        "REALTIME_QUERY_REQUIRED": AnswerAction.REQUIRE_LOOKUP,
        "SUPERVISOR_REQUIRED": AnswerAction.TRANSFER_HUMAN,
        "FORBIDDEN_PROMISE": AnswerAction.TRANSFER_HUMAN,
        "CONFIRM_REQUIRED": AnswerAction.ASK_CLARIFY,
    }.get(rule_type, AnswerAction.CONTROLLED_ANSWER)
