from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.test_catalog.models import (
    TestFaq,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestStore,
)


PRODUCT_FIELDS = (
    "product_summary",
    "main_selling_points",
    "recommended_age_text",
    "material",
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
                    if _clean(_json_dict(sku.raw_data_json).get(key)) not in (None, "", [])
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
                *[
                    str(item).strip()
                    for item in raw_source_ids
                    if str(item).strip()
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
