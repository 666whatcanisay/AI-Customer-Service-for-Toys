"""Snapshot construction for the frozen experience-case export contract."""

import hashlib
import json

from app.experience_cases.models import CustomerExperienceCase, CustomerExperienceCaseExport


def _snapshot_content(case: CustomerExperienceCase) -> dict[str, object]:
    """The exact governed export content used to calculate the evidence hash.

    ``v1-reminder-only`` is intentionally not an automatic-redaction claim: the
    values are preserved as submitted and operators are reminded upstream to
    remove personal information before submission.
    """
    return {
        "case_id": case.case_id,
        "revision": case.revision,
        "store_code": case.store_code,
        "product_id": case.product_id,
        "sku_id": case.sku_id,
        "question": case.question,
        "ai_answer": case.ai_answer,
        "final_answer": case.final_answer,
        "redaction_version": case.redaction_version,
    }


def create_export_snapshot(case: CustomerExperienceCase) -> CustomerExperienceCaseExport:
    """Freeze a case revision exactly once, without mutating its case content."""
    export_revision = f"{case.case_id}-r{case.revision}-e1"
    encoded = json.dumps(_snapshot_content(case), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"

    case.export_revision = export_revision
    case.content_hash = content_hash
    return CustomerExperienceCaseExport(
        case_record_id=case.id,
        case_id=case.case_id,
        revision=case.revision,
        export_revision=export_revision,
        store_code=case.store_code,
        product_id=case.product_id,
        sku_id=case.sku_id,
        question=case.question,
        ai_answer=case.ai_answer,
        final_answer=case.final_answer,
        content_hash=content_hash,
        redaction_version=case.redaction_version,
    )
