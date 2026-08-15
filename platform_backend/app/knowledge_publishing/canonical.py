from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge_materials.models import KnowledgeMaterial
from app.test_catalog.models import (
    TestFaq,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestStore,
)

_REVIEWED_MATERIAL_STATUSES = {
    "APPROVED_FOR_ANALYSIS",
    "ANALYZING",
    "ANALYZED",
}
_APPROXIMATE_PRODUCT_FIELDS = {
    "particle_count": "颗粒数量",
    "assembled_size": "成品尺寸",
    "product_scale": "商品比例",
}
_APPROXIMATE_VALUE_RE = re.compile(r"(?:约|大约|左右|近似|以实际.*为准)")
_REVIEWED_APPROXIMATE_RE = re.compile(r"(?:约数已审核|中风险受控回答|仅允许近似回答)")


PRODUCT_FIELDS = (
    "product_summary",
    "main_selling_points",
    "recommended_age_text",
    "material",
    "particle_count",
    "assembled_size",
    "package_type",
    "product_scale",
    "image_material_status",
    "ship_origin",
    "package_contents",
    "usage_instructions",
    "play_method",
    "common_customer_questions",
    "recommended_answer_direction",
)
SKU_FIELDS = (
    "color_style",
    "specification_difference",
    "package_difference",
    "quantity_difference",
    "size_difference",
    "play_difference",
)


def _json_dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item) not in (None, "", [])]
    return value


def _reviewed_approximate_controls(
    session: Session,
    product: TestProduct,
    raw: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return only human-reviewed approximate facts that match product data.

    Knowledge materials are immutable revisions.  Only the latest revision of
    each material can authorize a control marker, and the marker is accepted
    only when both the material body and its review note explicitly describe
    the approximate-value constraint.  This keeps ordinary imported text from
    silently upgrading itself into reviewed evidence.
    """

    rows = list(
        session.scalars(
            select(KnowledgeMaterial)
            .where(
                KnowledgeMaterial.store_code == product.store_code,
                KnowledgeMaterial.product_id == product.product_id,
                KnowledgeMaterial.sku_id.is_(None),
            )
            .order_by(KnowledgeMaterial.material_id, KnowledgeMaterial.revision.desc())
        )
    )
    latest: dict[str, KnowledgeMaterial] = {}
    for row in rows:
        latest.setdefault(row.material_id, row)

    controls: dict[str, dict[str, Any]] = {}
    for material in latest.values():
        if material.material_status not in _REVIEWED_MATERIAL_STATUSES:
            continue
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", material.content_hash or ""):
            continue
        try:
            body = json.loads(material.analysis_text or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(body, dict):
            continue

        review_text = " ".join(
            value
            for value in (material.review_note, material.analysis_text)
            if isinstance(value, str)
        )
        if not _REVIEWED_APPROXIMATE_RE.search(review_text):
            continue

        facts = body.get("facts")
        fact_map = facts if isinstance(facts, dict) else {}
        records = body.get("数据记录")
        record = records[0] if isinstance(records, list) and records else {}
        if not isinstance(record, dict):
            record = {}
        if record and str(record.get("是否人工确认") or "").strip() != "是":
            continue

        for field_name, display_name in _APPROXIMATE_PRODUCT_FIELDS.items():
            product_value = _clean(raw.get(field_name))
            material_value = _clean(
                fact_map.get(field_name) or record.get(display_name)
            )
            if (
                not isinstance(product_value, str)
                or not isinstance(material_value, str)
                or product_value != material_value
                or not _APPROXIMATE_VALUE_RE.search(product_value)
            ):
                continue
            controls[field_name] = {
                "controlled_answer_kind": "REVIEWED_APPROXIMATE_FACT",
                "material_id": material.material_id,
                "material_revision": material.revision,
                "material_content_hash": material.content_hash,
            }
    return controls


@dataclass(frozen=True, slots=True)
class CanonicalProductKnowledge:
    tenant_id: str
    platform: str
    store_code: str
    product_id: str
    product_name: str
    data_source: str
    document: str
    fingerprint: str
    source_ids: tuple[str, ...]


def build_canonical_product_knowledge(
    session: Session, product: TestProduct
) -> CanonicalProductKnowledge:
    store = session.scalar(
        select(TestStore).where(
            TestStore.package_id == product.package_id,
            TestStore.store_code == product.store_code,
        )
    )
    data_source = (
        store.data_source
        if store is not None
        and store.data_source in {"TEST", "INITIAL_IMPORT", "PILOT"}
        else "UNKNOWN"
    )
    raw = _json_dict(product.raw_data_json)
    reviewed_controls = _reviewed_approximate_controls(session, product, raw)
    skus = list(
        session.scalars(
            select(TestSku)
            .where(TestSku.product_id == product.product_id)
            .order_by(TestSku.sku_id)
        )
    )
    faqs = list(
        session.scalars(
            select(TestFaq)
            .where(TestFaq.product_id == product.product_id)
            .order_by(TestFaq.faq_id)
        )
    )
    safety_rules = list(
        session.scalars(
            select(TestSafetyRule)
            .where(
                TestSafetyRule.package_id == product.package_id,
                TestSafetyRule.store_code == product.store_code,
            )
            .order_by(TestSafetyRule.rule_id)
        )
    )

    canonical: dict[str, Any] = {
        "schema_version": "c-product-knowledge-document.v1",
        "tenant_id": product.tenant_id,
        "platform": product.platform,
        "store_code": product.store_code,
        "product_id": product.product_id,
        "product_name": product.product_name_display or product.product_name_official,
        "reviewed_answer_controls": reviewed_controls,
        "product": {
            "age_min": product.age_min,
            "age_max": product.age_max,
            "safety_summary": _clean(product.safety_summary),
            **{
                key: _clean(raw.get(key))
                for key in PRODUCT_FIELDS
                if _clean(raw.get(key)) not in (None, "", [])
            },
        },
        "skus": [
            {
                "sku_id": sku.sku_id,
                "sku_name": sku.sku_name_display or sku.sku_name_official,
                **{
                    key: _clean(_json_dict(sku.raw_data_json).get(key))
                    for key in SKU_FIELDS
                    if _clean(_json_dict(sku.raw_data_json).get(key))
                    not in (None, "", [])
                },
            }
            for sku in skus
        ],
        "faqs": [
            {
                "question": faq.canonical_question,
                "recommended_reply": faq.recommended_reply,
                "answer_action": faq.answer_action,
                "risk_level": faq.risk_level,
                "sku_id": faq.sku_id,
            }
            for faq in faqs
        ],
        "safety_rules": [
            {
                "scenario": rule.scenario,
                "risk_level": rule.risk_level,
                "content": {
                    key: _clean(value)
                    for key, value in _json_dict(rule.raw_data_json).items()
                    if key
                    in {
                        "fixed_instruction",
                        "allowed_action",
                        "notes",
                        "forbidden_claim",
                        "prohibited_promise",
                        "handoff_condition",
                        "escalation_condition",
                    }
                    and _clean(value) not in (None, "", [])
                },
            }
            for rule in safety_rules
        ],
    }
    serialized = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    try:
        raw_source_ids = json.loads(product.source_ids_json or "[]")
    except (TypeError, ValueError):
        raw_source_ids = []
    source_ids = tuple(
        dict.fromkeys(
            [
                *[str(item).strip() for item in raw_source_ids if str(item).strip()],
                *[
                    (
                        f"C-REVIEWED-MATERIAL:{control['material_id']}:"
                        f"r{control['material_revision']}:"
                        f"{control['material_content_hash']}"
                    )
                    for control in reviewed_controls.values()
                ],
                f"C-APPROVED-PRODUCT:{product.product_id}",
            ]
        )
    )
    return CanonicalProductKnowledge(
        tenant_id=product.tenant_id,
        platform=product.platform,
        store_code=product.store_code,
        product_id=product.product_id,
        product_name=product.product_name_display or product.product_name_official,
        data_source=data_source,
        document=serialized,
        fingerprint=fingerprint,
        source_ids=source_ids,
    )
