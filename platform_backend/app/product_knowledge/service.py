"""Read-only C business projection for product knowledge operations."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import ImportBatch
from app.knowledge_materials.models import KnowledgeMaterial, KnowledgeQualityAssessment
from app.knowledge_publishing.projection import publication_summary
from app.product_knowledge.schemas import (
    FaqSummary,
    KnowledgeGap,
    KnowledgeGapListItem,
    KnowledgeGapListResponse,
    KnowledgeGapWorkflowStatus,
    KnowledgeAiStatus,
    KnowledgeDataStatus,
    KnowledgeSourceSummary,
    KnowledgeTopicStatus,
    OverviewStats,
    ProductKnowledgeDetail,
    ProductKnowledgeListItem,
    ProductKnowledgeListResponse,
    ProductKnowledgeOverview,
    ProductKnowledgeState,
    ProductOverviewDetail,
    SafetySummary,
    SkuKnowledgeSummary,
    StoreKnowledgeSummary,
    TechnicalDetails,
    TopicCoverage,
)
from app.test_catalog.models import (
    TestFaq,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestSourceEvidence,
    TestStore,
)


BOUNDARY_NOTE = (
    "资料覆盖度与AI知识发布状态分别展示；只有“已发布”才代表知识已进入RAG，"
    "其他资料状态不代表知识已发布到 RAG。"
)
APPROVED_MATERIAL_STATUSES = {"APPROVED_FOR_ANALYSIS", "ANALYZING", "ANALYZED"}
PENDING_MATERIAL_STATUSES = {"RECEIVED", "RECOGNIZED", "REVIEWING"}

PLATFORM_NAMES = {
    "pinduoduo": "拼多多",
    "taobao": "淘宝",
    "tmall": "天猫",
    "jd": "京东",
    "douyin": "抖音",
    "offline": "线下",
}


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if _present(value):
            return value
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        joined = "；".join(str(item).strip() for item in value if _present(item))
        return joined or None
    result = str(value).strip()
    return result or None


def _text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if _present(item)]
    text = str(value).strip()
    if not text:
        return []
    for separator in ("\n", "；", ";", "、", "|"):
        if separator in text:
            return [item.strip(" -•") for item in text.split(separator) if item.strip(" -•")]
    return [text]


def _age_text(product: TestProduct, raw: dict[str, Any]) -> str | None:
    minimum = product.age_min if product.age_min is not None else raw.get("age_min")
    maximum = product.age_max if product.age_max is not None else raw.get("age_max")
    if minimum is None and maximum is None:
        return None
    if minimum is not None and maximum is not None:
        return f"{minimum}—{maximum} 岁"
    if minimum is not None:
        return f"{minimum} 岁及以上"
    return f"{maximum} 岁及以下"


def _platform_name(platform: str) -> str:
    return PLATFORM_NAMES.get(platform.lower(), platform or "未标注平台")


def _material_topic_hints(materials: Iterable[KnowledgeMaterial]) -> set[str]:
    hints: set[str] = set()
    for material in materials:
        if material.material_status not in APPROVED_MATERIAL_STATUSES:
            continue
        template_type = str((material.recognition_summary or {}).get("template_type") or "")
        if template_type in {"AI_FEEDBACK", "KNOWLEDGE_GAP"}:
            continue
        detected = material.recognition_summary.get("detected_fields", [])
        joined = " ".join(str(item).lower() for item in detected)
        if template_type == "FAQ" or material.material_type == "FAQ_SOURCE" or "faq" in joined or "问题" in joined:
            hints.add("faq")
        if template_type == "SAFETY_RULE" or material.material_type == "SAFETY_INSTRUCTION" or "安全" in joined or "材质" in joined:
            hints.add("material_safety")
        if material.material_type == "ASSEMBLY_GUIDE" or "安装" in joined or "拼装" in joined:
            hints.add("usage")
        if template_type == "SKU_DIFFERENCE":
            if any(keyword in joined for keyword in ("颜色款式", "规格区别", "包装区别", "数量区别", "尺寸区别", "玩法区别")):
                hints.add("sku_difference")
            if "颜色款式" in joined:
                hints.add("variants")
        if material.material_type == "PRODUCT_SPEC":
            mapping = {
                "简介": "product_summary",
                "介绍": "product_summary",
                "description": "product_summary",
                "summary": "product_summary",
                "卖点": "selling_points",
                "年龄": "age",
                "包装": "package_contents",
                "使用说明": "usage",
                "常问问题": "faq",
                "安全提醒": "material_safety",
                "材质信息": "material_safety",
                "零件": "parts_count",
                "尺寸": "size",
                "颜色": "variants",
            }
            for keyword, topic in mapping.items():
                if keyword in joined:
                    hints.add(topic)
    return hints


def _pending_material_topic_hints(materials: Iterable[KnowledgeMaterial]) -> set[str]:
    mapping = {
        "商品简介": "product_summary",
        "核心卖点": "selling_points",
        "适用年龄": "age",
        "材质信息": "material_safety",
        "安全提醒": "material_safety",
        "包装内容": "package_contents",
        "使用说明": "usage",
        "客户常问问题": "faq",
        "标准回答": "faq",
        "颜色款式": "variants",
        "规格区别": "sku_difference",
        "包装区别": "sku_difference",
        "数量区别": "sku_difference",
        "尺寸区别": "sku_difference",
        "玩法区别": "sku_difference",
    }
    hints: set[str] = set()
    for material in materials:
        if material.material_status not in PENDING_MATERIAL_STATUSES:
            continue
        detected = material.recognition_summary.get("detected_fields", [])
        for field in detected:
            topic = mapping.get(str(field))
            if topic:
                hints.add(topic)
    return hints


def _topic(
    key: str,
    name: str,
    level: str,
    value: object,
    *,
    partial: bool = False,
    evidence: str | None = None,
) -> TopicCoverage:
    if _present(value):
        status = KnowledgeTopicStatus.PARTIAL if partial else KnowledgeTopicStatus.SUPPORTED
    else:
        status = KnowledgeTopicStatus.MISSING
    return TopicCoverage(
        key=key,
        name=name,
        level=level,
        status=status,
        evidence_summary=evidence if status != KnowledgeTopicStatus.MISSING else None,
    )


def _missing_gap(topic: TopicCoverage) -> KnowledgeGap:
    fallback_map = {
        "age": "当前资料未提供年龄信息，建议人工确认。",
        "sku_difference": "当前资料未说明不同 SKU 的区别，建议人工确认后再回复。",
    }
    return KnowledgeGap(
        key=f"MISSING_{topic.key.upper()}",
        title=f"缺少{topic.name}",
        severity="HIGH" if topic.level == "A" else "MEDIUM",
        description=f"当前商品资料尚不能支持 AI 稳妥回答“{topic.name}”相关问题。",
        recommended_action=f"补充并审核{topic.name}资料。",
        safe_fallback=fallback_map.get(
            topic.key, f"当前资料未提供{topic.name}，建议人工确认。"
        ),
        source="C_COVERAGE_RULE",
    )


class ProductKnowledgeService:
    """Builds a non-persistent business view from current C-owned records."""

    def __init__(self, session: Session):
        self.session = session
        self.stores = list(session.scalars(select(TestStore).order_by(TestStore.store_name)))
        self.products = list(
            session.scalars(select(TestProduct).order_by(TestProduct.product_name_display))
        )
        self.skus = list(session.scalars(select(TestSku).order_by(TestSku.sku_name_display)))
        self.faqs = list(session.scalars(select(TestFaq).order_by(TestFaq.faq_id)))
        self.safety_rules = list(
            session.scalars(select(TestSafetyRule).order_by(TestSafetyRule.rule_id))
        )
        self.source_evidence = list(
            session.scalars(select(TestSourceEvidence).order_by(TestSourceEvidence.source_id))
        )
        all_materials = list(
            session.scalars(
                select(KnowledgeMaterial).order_by(
                    KnowledgeMaterial.material_id, KnowledgeMaterial.revision.desc()
                )
            )
        )
        self.materials = self._latest_materials(all_materials)
        self.assessments = list(
            session.scalars(
                select(KnowledgeQualityAssessment).order_by(
                    KnowledgeQualityAssessment.created_at.desc()
                )
            )
        )

        self.stores_by_scope = {
            (store.package_id, store.store_code): store for store in self.stores
        }
        self.skus_by_product: dict[str, list[TestSku]] = defaultdict(list)
        self.faqs_by_product: dict[str, list[TestFaq]] = defaultdict(list)
        self.faqs_by_sku: dict[str, list[TestFaq]] = defaultdict(list)
        self.materials_by_product: dict[str, list[KnowledgeMaterial]] = defaultdict(list)
        for sku in self.skus:
            self.skus_by_product[sku.product_id].append(sku)
        for faq in self.faqs:
            if faq.product_id:
                self.faqs_by_product[faq.product_id].append(faq)
            if faq.sku_id:
                self.faqs_by_sku[faq.sku_id].append(faq)
        for material in self.materials:
            self.materials_by_product[material.product_id].append(material)

    @staticmethod
    def _latest_materials(materials: list[KnowledgeMaterial]) -> list[KnowledgeMaterial]:
        latest: dict[str, KnowledgeMaterial] = {}
        for material in materials:
            current = latest.get(material.material_id)
            if current is None or material.revision > current.revision:
                latest[material.material_id] = material
        return list(latest.values())

    def overview(self) -> ProductKnowledgeOverview:
        if not self.products and not self.stores:
            return ProductKnowledgeOverview(
                generated_at=datetime.now(timezone.utc),
                has_data=False,
                stats=OverviewStats(),
                stores=[],
                boundary_note=BOUNDARY_NOTE,
            )

        projections = [self._product_projection(product) for product in self.products]
        by_store: dict[tuple[str, str], list[ProductKnowledgeListItem]] = defaultdict(list)
        for product, projection in zip(self.products, projections, strict=True):
            by_store[(product.package_id, product.store_code)].append(projection)

        stores: list[StoreKnowledgeSummary] = []
        for store in self.stores:
            items = by_store.get((store.package_id, store.store_code), [])
            stores.append(self._store_summary(store, items))

        pending_materials = sum(
            material.material_status in PENDING_MATERIAL_STATUSES for material in self.materials
        )
        pending_imports = len(
            list(
                self.session.scalars(
                    select(ImportBatch).where(ImportBatch.status == "READY_FOR_REVIEW")
                )
            )
        )
        return ProductKnowledgeOverview(
            generated_at=datetime.now(timezone.utc),
            has_data=True,
            stats=OverviewStats(
                store_count=len(self.stores),
                product_count=len(projections),
                ai_usable_product_count=sum(item.ai_usable for item in projections),
                gap_count=sum(item.gap_count for item in projections),
                pending_review_count=pending_materials + pending_imports,
            ),
            stores=stores,
            boundary_note=BOUNDARY_NOTE,
        )

    def list_products(self, store_code: str | None = None) -> ProductKnowledgeListResponse:
        products = [
            product for product in self.products if store_code is None or product.store_code == store_code
        ]
        items = [self._product_projection(product) for product in products]
        return ProductKnowledgeListResponse(items=items, total=len(items))

    def list_gaps(
        self,
        *,
        store_code: str | None = None,
        priority: str | None = None,
        workflow_status: KnowledgeGapWorkflowStatus | None = None,
    ) -> KnowledgeGapListResponse:
        items: list[KnowledgeGapListItem] = []
        for product in self.products:
            if store_code and product.store_code != store_code:
                continue
            raw = _json_dict(product.raw_data_json)
            materials = self.materials_by_product.get(product.product_id, [])
            topics = self._coverage(product, raw, materials)
            pending_hints = _pending_material_topic_hints(materials)
            store = self.stores_by_scope.get((product.package_id, product.store_code))
            store_name = store.store_name if store else "未找到店铺名称"
            product_name = product.product_name_display or product.product_name_official
            for topic in topics:
                if topic.status == KnowledgeTopicStatus.SUPPORTED:
                    continue
                base_gap = _missing_gap(topic)
                if topic.status == KnowledgeTopicStatus.PARTIAL:
                    status = KnowledgeGapWorkflowStatus.PENDING_VERIFICATION
                elif topic.key in pending_hints:
                    status = KnowledgeGapWorkflowStatus.IN_PROGRESS
                else:
                    status = KnowledgeGapWorkflowStatus.PENDING
                item_priority = self._gap_priority(topic.key, base_gap.severity)
                items.append(
                    KnowledgeGapListItem(
                        store_name=store_name,
                        product_name=product_name,
                        sku_name="全部SKU",
                        missing_topic=topic.name,
                        occurrence_count=1,
                        impact_level="高" if topic.level == "A" else "中",
                        priority=item_priority,
                        workflow_status=status,
                        description=(
                            base_gap.description
                            if topic.status == KnowledgeTopicStatus.MISSING
                            else f"{topic.name}已有审核资料提示，但仍需核对为可直接使用的结构化事实。"
                        ),
                        recommended_action=base_gap.recommended_action,
                        safe_fallback=base_gap.safe_fallback,
                    )
                )

            material_ids = {material.material_id for material in materials}
            for assessment in self.assessments:
                if assessment.material_id not in material_ids:
                    continue
                for gap in assessment.gaps or []:
                    raw_status = str(gap.get("status") or "OPEN")
                    status_map = {
                        "OPEN": KnowledgeGapWorkflowStatus.PENDING,
                        "ACKNOWLEDGED": KnowledgeGapWorkflowStatus.IN_PROGRESS,
                        "RESOLVED": KnowledgeGapWorkflowStatus.RESOLVED,
                        "DISMISSED": KnowledgeGapWorkflowStatus.RESOLVED,
                    }
                    status = status_map.get(raw_status, KnowledgeGapWorkflowStatus.PENDING)
                    severity = str(gap.get("severity") or "MEDIUM")
                    items.append(
                        KnowledgeGapListItem(
                            store_name=store_name,
                            product_name=product_name,
                            sku_name="全部SKU",
                            missing_topic=str(gap.get("title") or "AI分析发现的知识缺口"),
                            occurrence_count=max(int(gap.get("occurrence_count") or 1), 1),
                            impact_level={"HIGH": "高", "MEDIUM": "中", "LOW": "低"}.get(severity, "中"),
                            priority=self._gap_priority(str(gap.get("gap_code") or ""), severity),
                            workflow_status=status,
                            description=str(gap.get("description") or "已审核资料存在待补充信息。"),
                            recommended_action=str(gap.get("recommended_action") or "补充资料并重新审核。"),
                            safe_fallback="当前资料不足以确认该信息，建议人工确认。",
                        )
                    )
        if priority:
            items = [item for item in items if item.priority == priority]
        if workflow_status:
            items = [item for item in items if item.workflow_status == workflow_status]
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        items.sort(
            key=lambda item: (
                priority_order[item.priority],
                item.store_name,
                item.product_name,
                item.missing_topic,
            )
        )
        return KnowledgeGapListResponse(items=items, total=len(items))

    @staticmethod
    def _gap_priority(topic_key: str, severity: str) -> str:
        normalized = topic_key.lower()
        if "safety" in normalized or "安全" in normalized:
            return "P0"
        if severity == "HIGH":
            return "P1"
        if severity == "MEDIUM":
            return "P2"
        return "P3"

    def detail(self, product_id: str) -> ProductKnowledgeDetail | None:
        product = next((item for item in self.products if item.product_id == product_id), None)
        if product is None:
            return None
        projection = self._product_projection(product)
        raw = _json_dict(product.raw_data_json)
        store = self.stores_by_scope.get((product.package_id, product.store_code))
        materials = self.materials_by_product.get(product.product_id, [])
        topics = self._coverage(product, raw, materials)
        gaps = self._gaps(product, topics, materials)
        skus = self.skus_by_product.get(product.product_id, [])

        sku_names = {
            sku.sku_id: sku.sku_name_display or sku.sku_name_official for sku in skus
        }
        faq_items = [
            FaqSummary(
                question=faq.canonical_question,
                recommended_reply=faq.recommended_reply,
                answer_strategy=faq.answer_action,
                risk_level=faq.risk_level,
                sku_name=sku_names.get(faq.sku_id) if faq.sku_id else None,
            )
            for faq in self.faqs_by_product.get(product.product_id, [])
        ]
        safety_items: list[SafetySummary] = []
        if product.safety_summary:
            safety_items.append(
                SafetySummary(title="商品安全说明", content=product.safety_summary)
            )
        for rule in self.safety_rules:
            if rule.package_id != product.package_id or rule.store_code != product.store_code:
                continue
            rule_raw = _json_dict(rule.raw_data_json)
            content = _text(_first(rule_raw, "fixed_instruction", "allowed_action", "notes"))
            if content:
                safety_items.append(
                    SafetySummary(
                        title=rule.scenario,
                        content=content,
                        risk_level=rule.risk_level,
                        forbidden_claim=_text(
                            _first(rule_raw, "forbidden_claim", "prohibited_promise", "禁止承诺内容")
                        ),
                        handoff_condition=_text(
                            _first(rule_raw, "handoff_condition", "escalation_condition", "必须转人工情况")
                        ),
                    )
                )

        source_items = self._sources(product, skus, materials)
        next_actions = list(dict.fromkeys(gap.recommended_action for gap in gaps))
        return ProductKnowledgeDetail(
            store=self._store_summary(store, [projection])
            if store
            else StoreKnowledgeSummary(
                store_name="未找到店铺名称",
                platform_name=_platform_name(product.platform),
                remarks="",
                product_count=1,
                ai_usable_product_count=int(projection.ai_usable),
                gap_count=projection.gap_count,
                pending_review_count=sum(
                    material.material_status in PENDING_MATERIAL_STATUSES
                    for material in materials
                ),
                technical_details=TechnicalDetails(
                    store_code=product.store_code, platform=product.platform
                ),
            ),
            product=ProductOverviewDetail(
                product_name=projection.product_name,
                product_summary=projection.product_summary,
                core_selling_points=projection.core_selling_points,
                applicable_age=_age_text(product, raw),
                material=_text(_first(raw, "material", "material_safety")),
                package_contents=_text(_first(raw, "package_contents", "packing_list")),
                usage_instructions=_text(
                    _first(raw, "assembly_summary", "play_method", "usage_instructions")
                ),
                data_source=store.data_source if store and store.data_source else "UNKNOWN",
                customer_service_status=product.customer_service_status,
                customer_service_status_updated_at=(
                    product.customer_service_status_updated_at
                ),
                customer_service_status_updated_by=(
                    product.customer_service_status_updated_by
                ),
                technical_details=projection.technical_details,
            ),
            skus=[self._sku_summary(sku) for sku in skus],
            faqs=faq_items,
            safety_information=safety_items,
            sources=source_items,
            coverage_percent=projection.coverage_percent,
            ai_usable=projection.ai_usable,
            knowledge_state=projection.knowledge_state,
            data_status=projection.data_status,
            ai_status=projection.ai_status,
            ai_knowledge=projection.ai_knowledge,
            topic_coverage=topics,
            answerable_topics=projection.answerable_topics,
            missing_topics=projection.missing_topics,
            gaps=gaps,
            next_actions=next_actions,
            boundary_note=BOUNDARY_NOTE,
        )

    def _store_summary(
        self, store: TestStore, items: list[ProductKnowledgeListItem]
    ) -> StoreKnowledgeSummary:
        return StoreKnowledgeSummary(
            store_name=store.store_name,
            platform_name=_platform_name(store.platform),
            remarks=_text(_json_dict(store.raw_data_json).get("remarks")) or "",
            product_count=len(items),
            ai_usable_product_count=sum(item.ai_usable for item in items),
            gap_count=sum(item.gap_count for item in items),
            pending_review_count=sum(
                material.store_code == store.store_code
                and material.material_status in PENDING_MATERIAL_STATUSES
                for material in self.materials
            ),
            technical_details=TechnicalDetails(
                store_code=store.store_code,
                platform=store.platform,
            ),
        )

    def _product_projection(self, product: TestProduct) -> ProductKnowledgeListItem:
        raw = _json_dict(product.raw_data_json)
        materials = self.materials_by_product.get(product.product_id, [])
        topics = self._coverage(product, raw, materials)
        a_topics = [topic for topic in topics if topic.level == "A"]
        supported_units = sum(
            1 if topic.status == KnowledgeTopicStatus.SUPPORTED else 0.5
            if topic.status == KnowledgeTopicStatus.PARTIAL
            else 0
            for topic in a_topics
        )
        coverage = round((supported_units / len(a_topics)) * 100) if a_topics else 0
        topic_map = {topic.key: topic for topic in topics}
        ai_usable = (
            topic_map["product_name"].status == KnowledgeTopicStatus.SUPPORTED
            and (
                topic_map["sku_name"].status == KnowledgeTopicStatus.SUPPORTED
                or topic_map["product_summary"].status
                in {KnowledgeTopicStatus.SUPPORTED, KnowledgeTopicStatus.PARTIAL}
            )
        )
        gaps = self._gaps(product, topics, materials)
        has_high_gap = any(gap.severity == "HIGH" for gap in gaps)
        if coverage >= 80 and not has_high_gap:
            state = ProductKnowledgeState.WELL_COVERED
        elif ai_usable:
            state = ProductKnowledgeState.BASIC_AVAILABLE
        else:
            state = ProductKnowledgeState.NEEDS_COMPLETION
        store = self.stores_by_scope.get((product.package_id, product.store_code))
        description = _text(_first(raw, "product_summary", "description", "product_intro"))
        data_status = self._data_status(product, materials)
        has_safety_source = bool(_json_list(product.source_ids_json)) or any(
            item.material_status in APPROVED_MATERIAL_STATUSES
            and (
                item.material_type == "SAFETY_INSTRUCTION"
                or (item.recognition_summary or {}).get("template_type") == "SAFETY_RULE"
            )
            and (item.recognition_summary or {}).get("high_risk_source_confirmed") is not False
            for item in materials
        )
        ai_status = self._ai_status(
            topics,
            ai_usable=ai_usable,
            coverage=coverage,
            gaps=gaps,
            has_safety_source=has_safety_source,
        )
        return ProductKnowledgeListItem(
            store_name=store.store_name if store else "未找到店铺名称",
            product_name=product.product_name_display or product.product_name_official,
            product_summary=description,
            core_selling_points=_text_list(raw.get("main_selling_points")),
            applicable_age=_age_text(product, raw),
            material_safety=_text(_first(raw, "material", "material_safety")) or product.safety_summary,
            package_contents=_text(_first(raw, "package_contents", "packing_list")),
            faq_count=len(self.faqs_by_product.get(product.product_id, [])),
            sku_names=[
                sku.sku_name_display or sku.sku_name_official
                for sku in self.skus_by_product.get(product.product_id, [])
            ],
            coverage_percent=coverage,
            ai_usable=ai_usable,
            knowledge_state=state,
            data_status=data_status,
            ai_status=ai_status,
            answerable_topics=[
                topic.name for topic in topics if topic.status != KnowledgeTopicStatus.MISSING
            ],
            missing_topics=[
                topic.name for topic in topics if topic.status == KnowledgeTopicStatus.MISSING
            ],
            gap_count=len(gaps),
            data_source=store.data_source if store and store.data_source else "UNKNOWN",
            customer_service_status=product.customer_service_status,
            customer_service_status_updated_at=product.customer_service_status_updated_at,
            customer_service_status_updated_by=product.customer_service_status_updated_by,
            ai_knowledge=publication_summary(self.session, product),
            technical_details=TechnicalDetails(
                store_code=product.store_code,
                platform=product.platform,
                product_id=product.product_id,
                product_code=_text(raw.get("platform_product_id")),
            ),
        )

    @staticmethod
    def _data_status(
        product: TestProduct, materials: list[KnowledgeMaterial]
    ) -> KnowledgeDataStatus:
        if any(item.material_status in PENDING_MATERIAL_STATUSES for item in materials):
            return KnowledgeDataStatus.PENDING_REVIEW
        if product.review_status in {"REVIEWING", "PENDING_REVIEW"}:
            return KnowledgeDataStatus.PENDING_REVIEW
        if product.review_status == "APPROVED" or any(
            item.material_status in APPROVED_MATERIAL_STATUSES for item in materials
        ):
            return KnowledgeDataStatus.APPROVED
        return KnowledgeDataStatus.DRAFT

    @staticmethod
    def _ai_status(
        topics: list[TopicCoverage],
        *,
        ai_usable: bool,
        coverage: int,
        gaps: list[KnowledgeGap],
        has_safety_source: bool,
    ) -> KnowledgeAiStatus:
        topic_map = {topic.key: topic for topic in topics}
        safety = topic_map.get("material_safety")
        if safety is None or safety.status == KnowledgeTopicStatus.MISSING or not has_safety_source:
            return KnowledgeAiStatus.UNCONFIRMED
        core_topics = [topic for topic in topics if topic.level == "A"]
        if coverage >= 80 and all(
            topic.status == KnowledgeTopicStatus.SUPPORTED for topic in core_topics
        ) and not any(gap.severity == "HIGH" for gap in gaps):
            return KnowledgeAiStatus.EFFECTIVE
        if ai_usable:
            return KnowledgeAiStatus.PARTIALLY_AVAILABLE
        return KnowledgeAiStatus.MISSING_KNOWLEDGE

    def _coverage(
        self,
        product: TestProduct,
        raw: dict[str, Any],
        materials: list[KnowledgeMaterial],
    ) -> list[TopicCoverage]:
        skus = self.skus_by_product.get(product.product_id, [])
        sku_raw = [_json_dict(sku.raw_data_json) for sku in skus]
        hints = _material_topic_hints(materials)
        structured_faq = self.faqs_by_product.get(product.product_id, [])
        product_summary = _first(raw, "product_summary", "description", "product_intro")
        material = _first(raw, "material", "material_safety") or product.safety_summary
        usage = _first(raw, "assembly_summary", "play_method", "usage_instructions")
        difference = [data.get("difference_summary") for data in sku_raw if data.get("difference_summary")]
        return [
            _topic("product_name", "商品名称", "A", product.product_name_display),
            _topic("sku_name", "SKU名称", "A", [sku.sku_name_display for sku in skus]),
            _topic(
                "product_summary",
                "商品介绍",
                "A",
                product_summary or ("approved" if "product_summary" in hints else None),
                partial=not _present(product_summary) and "product_summary" in hints,
                evidence="商品结构化资料" if _present(product_summary) else "已审核资料提示",
            ),
            _topic(
                "selling_points",
                "核心卖点",
                "A",
                raw.get("main_selling_points") or ("approved" if "selling_points" in hints else None),
                partial=not _present(raw.get("main_selling_points")) and "selling_points" in hints,
            ),
            _topic(
                "age",
                "适用年龄",
                "A",
                _age_text(product, raw) or ("approved" if "age" in hints else None),
                partial=_age_text(product, raw) is None and "age" in hints,
            ),
            _topic(
                "material_safety",
                "材质与安全",
                "A",
                material or ("approved" if "material_safety" in hints else None),
                partial=not _present(material) and "material_safety" in hints,
            ),
            _topic(
                "package_contents",
                "包装内容",
                "A",
                _first(raw, "package_contents", "packing_list") or ("approved" if "package_contents" in hints else None),
                partial=not _present(_first(raw, "package_contents", "packing_list")) and "package_contents" in hints,
            ),
            _topic(
                "usage",
                "基础使用说明",
                "A",
                usage or ("approved" if "usage" in hints else None),
                partial=not _present(usage) and "usage" in hints,
            ),
            _topic(
                "faq",
                "常见问题",
                "A",
                structured_faq or ("approved" if "faq" in hints else None),
                partial=not structured_faq and "faq" in hints,
            ),
            _topic("parts_count", "零件数量", "B", [data.get("particle_count") for data in sku_raw if data.get("particle_count")]),
            _topic("size", "尺寸", "B", raw.get("assembled_size") or [data.get("assembled_size") for data in sku_raw if data.get("assembled_size")]),
            _topic("difficulty_time", "拼装难度与时间", "B", _first(raw, "assembly_difficulty", "estimated_time")),
            _topic("play", "玩法", "B", raw.get("play_method")),
            _topic("variants", "颜色款式", "B", [data.get("color") or data.get("model_type") for data in sku_raw if data.get("color") or data.get("model_type")]),
            _topic("relations", "组合关系", "B", [sku.relation_type for sku in skus if sku.relation_type and sku.relation_type != "INDEPENDENT"]),
            _topic("sku_difference", "SKU区别", "B", difference),
        ]

    def _gaps(
        self,
        product: TestProduct,
        topics: list[TopicCoverage],
        materials: list[KnowledgeMaterial],
    ) -> list[KnowledgeGap]:
        gaps = [_missing_gap(topic) for topic in topics if topic.status == KnowledgeTopicStatus.MISSING]
        material_ids = {material.material_id for material in materials}
        for assessment in self.assessments:
            if assessment.material_id not in material_ids:
                continue
            for gap in assessment.gaps or []:
                if gap.get("status") != "OPEN":
                    continue
                gaps.append(
                    KnowledgeGap(
                        key=str(gap.get("gap_code") or gap.get("gap_id") or "ASSESSMENT_GAP"),
                        title=str(gap.get("title") or "AI 分析发现资料缺口"),
                        severity=str(gap.get("severity") or "MEDIUM"),
                        description=str(gap.get("description") or "已审核资料存在待补充信息。"),
                        recommended_action=str(gap.get("recommended_action") or "补充资料并重新审核。"),
                        safe_fallback="当前资料不足以确认该信息，建议人工确认。",
                        source="AI_ASSESSMENT",
                    )
                )
        return gaps

    def _sku_summary(self, sku: TestSku) -> SkuKnowledgeSummary:
        raw = _json_dict(sku.raw_data_json)
        difference = _text(_first(raw, "difference_summary", "specification_difference"))
        color_style = _text(_first(raw, "color", "model_type", "color_style"))
        package_difference = _text(_first(raw, "package_difference", "package_type"))
        attributes: list[str] = []
        labels = {
            "color": "颜色",
            "model_type": "款式",
            "package_type": "包装",
            "particle_count": "零件数量",
            "assembled_size": "成品尺寸",
        }
        for key, label in labels.items():
            if _present(raw.get(key)):
                attributes.append(f"{label}：{raw[key]}")
        return SkuKnowledgeSummary(
            sku_name=sku.sku_name_display or sku.sku_name_official,
            color_style=color_style,
            specification_difference=difference,
            package_difference=package_difference,
            faq_count=len(self.faqs_by_sku.get(sku.sku_id, [])),
            difference_confirmed=bool(
                difference and (
                    difference == "已确认无差异" or _present(difference)
                )
            ),
            attributes=attributes,
            technical_details=TechnicalDetails(
                sku_id=sku.sku_id,
                sku_code=sku.sku_code,
            ),
        )

    def _sources(
        self,
        product: TestProduct,
        skus: list[TestSku],
        materials: list[KnowledgeMaterial],
    ) -> list[KnowledgeSourceSummary]:
        sku_ids = {sku.sku_id for sku in skus}
        items: list[KnowledgeSourceSummary] = []
        for source in self.source_evidence:
            if source.package_id != product.package_id:
                continue
            if source.product_id != product.product_id and source.sku_id not in sku_ids:
                continue
            metadata = _json_dict(source.metadata_json)
            items.append(
                KnowledgeSourceSummary(
                    source_name=source.file_name or "已登记资料来源",
                    source_type=source.source_type,
                    review_status=_text(metadata.get("review_status")),
                    technical_details=TechnicalDetails(
                        source_id=source.source_id,
                        content_hash=source.file_sha256,
                    ),
                )
            )
        for material in materials:
            items.append(
                KnowledgeSourceSummary(
                    source_name=material.display_name,
                    source_type=material.material_type,
                    review_status=material.material_status,
                    technical_details=TechnicalDetails(
                        material_id=material.material_id,
                        revision=material.revision,
                        content_hash=material.content_hash,
                    ),
                )
            )
        return items
