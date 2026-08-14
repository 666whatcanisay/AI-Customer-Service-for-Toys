"""C-owned routes for the frozen knowledge-quality-loop v1.

These routes govern controlled material metadata and explicit AI evidence only.
They never publish to RAG, alter a Prompt/model, or trigger a customer/business
action.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import AppError
from app.iam.dependencies import Principal, ensure_store_code_access, get_current_principal
from app.knowledge_materials.models import (
    KnowledgeMaterial,
    KnowledgeMaterialUploadReceipt,
    KnowledgeQualityAssessment,
    new_material_id,
    utc_now,
)
from app.knowledge_materials.schemas import (
    CustomerKnowledgeStatusResponse,
    CustomerKnowledgeStatusValue,
    KnowledgeMaterialDetail,
    KnowledgeMaterialDiffResponse,
    KnowledgeMaterialFieldChange,
    KnowledgeMaterialListResponse,
    KnowledgeMaterialReceipt,
    KnowledgeMaterialReview,
    KnowledgeMaterialRevisionListResponse,
    KnowledgeMaterialReviewDecision,
    KnowledgeMaterialStatus,
    KnowledgeMaterialSummary,
    KnowledgeMaterialType,
    KnowledgeTemplateRecognitionSummary,
    KnowledgeTemplateType,
    KnowledgeQualityAnalysisInput,
    KnowledgeQualityAnalysisInputListResponse,
    KnowledgeQualityAnalysisResultCreate,
    KnowledgeQualityAssessmentListResponse,
    KnowledgeQualityAssessmentResponse,
    KnowledgeQualityOverallStatus,
    KnowledgeQualityGap,
    RecognitionSummary,
    gap_as_dict,
)
from app.knowledge_materials.service import (
    content_hash,
    fingerprint_upload,
    recognize_material,
    remove_controlled_upload,
    safe_filename,
    write_controlled_upload,
)
from app.test_catalog.models import TestProduct, TestSku, TestStore


admin_router = APIRouter(prefix="/api/v1/admin/knowledge-materials", tags=["knowledge-materials"])
ai_quality_router = APIRouter(prefix="/api/v1/admin/knowledge-quality", tags=["knowledge-quality"])
customer_router = APIRouter(tags=["customer-knowledge-status"])

_UPLOAD_METHOD = "POST"
_UPLOAD_PATH = "/api/v1/admin/knowledge-materials"
_PREVIEW_LIMIT = 4_000
_TEMPLATE_MATERIAL_TYPE = {
    KnowledgeTemplateType.PRODUCT_KNOWLEDGE: KnowledgeMaterialType.PRODUCT_SPEC,
    KnowledgeTemplateType.SKU_DIFFERENCE: KnowledgeMaterialType.PRODUCT_SPEC,
    KnowledgeTemplateType.FAQ: KnowledgeMaterialType.FAQ_SOURCE,
    KnowledgeTemplateType.SAFETY_RULE: KnowledgeMaterialType.SAFETY_INSTRUCTION,
    KnowledgeTemplateType.AI_FEEDBACK: KnowledgeMaterialType.OTHER,
    KnowledgeTemplateType.KNOWLEDGE_GAP: KnowledgeMaterialType.OTHER,
}
_NON_AI_KNOWLEDGE_TEMPLATES = {
    KnowledgeTemplateType.AI_FEEDBACK.value,
    KnowledgeTemplateType.KNOWLEDGE_GAP.value,
}


def _summary(item: KnowledgeMaterial) -> KnowledgeMaterialSummary:
    return KnowledgeMaterialSummary(
        material_id=item.material_id,
        revision=item.revision,
        store_code=item.store_code,
        product_id=item.product_id,
        sku_id=item.sku_id,
        material_type=item.material_type,
        display_name=item.display_name,
        original_filename=item.original_filename,
        content_hash=item.content_hash,
        redaction_version=item.redaction_version,
        recognition_summary=KnowledgeTemplateRecognitionSummary.model_validate(item.recognition_summary),
        material_status=item.material_status,
        submitted_by=item.submitted_by,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        review_note=item.review_note,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _receipt(item: KnowledgeMaterial) -> KnowledgeMaterialReceipt:
    return KnowledgeMaterialReceipt(
        material_id=item.material_id,
        revision=item.revision,
        content_hash=item.content_hash,
        material_status=item.material_status,
        recognition_summary=KnowledgeTemplateRecognitionSummary.model_validate(item.recognition_summary),
    )


def _assessment_response(item: KnowledgeQualityAssessment) -> KnowledgeQualityAssessmentResponse:
    return KnowledgeQualityAssessmentResponse(
        assessment_id=item.assessment_id,
        material_id=item.material_id,
        revision=item.revision,
        content_hash=item.content_hash,
        analysis_run_id=item.analysis_run_id,
        model_version=item.model_version,
        prompt_version=item.prompt_version,
        overall_status=item.overall_status,
        summary=item.summary,
        gaps=[KnowledgeQualityGap.model_validate(gap) for gap in item.gaps],
        created_at=item.created_at,
    )


def _current_revision(session: Session, material_id: str) -> KnowledgeMaterial | None:
    return session.scalar(
        select(KnowledgeMaterial)
        .where(KnowledgeMaterial.material_id == material_id)
        .order_by(KnowledgeMaterial.revision.desc())
    )


def _material_or_404(session: Session, material_id: str) -> KnowledgeMaterial:
    item = _current_revision(session, material_id)
    if item is None:
        raise AppError("KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "未找到对应的商品资料。", status_code=404)
    return item


def _same_upload_scope(item: KnowledgeMaterial, values: dict[str, str | None]) -> bool:
    base_matches = (
        item.material_id == values["material_id"] if values["material_id"] else True
    ) and all(
        getattr(item, key) == values[key]
        for key in ("store_code", "product_id", "sku_id", "material_type", "display_name")
    )
    return base_matches and (item.recognition_summary or {}).get("template_type") == values.get(
        "template_type"
    )


def _editable_record(item: KnowledgeMaterial) -> dict[str, str] | None:
    summary = item.recognition_summary or {}
    if not summary.get("template_type") or summary.get("record_count") != 1:
        return None
    try:
        payload = json.loads(item.analysis_text)
    except (TypeError, ValueError):
        return None
    records = payload.get("数据记录") if isinstance(payload, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        return None
    return {
        str(key): str(value)
        for key, value in records[0].items()
        if isinstance(key, str) and value is not None
    }


def _revision_or_404(session: Session, material_id: str, revision: int) -> KnowledgeMaterial:
    item = session.scalar(
        select(KnowledgeMaterial).where(
            KnowledgeMaterial.material_id == material_id,
            KnowledgeMaterial.revision == revision,
        )
    )
    if item is None:
        raise AppError(
            "KNOWLEDGE_MATERIAL_REVISION_NOT_FOUND",
            "未找到对应的资料修订版本。",
            status_code=404,
        )
    return item


def _detail(item: KnowledgeMaterial) -> KnowledgeMaterialDetail:
    return KnowledgeMaterialDetail(
        **_summary(item).model_dump(),
        analysis_text_preview=item.analysis_text[:_PREVIEW_LIMIT],
        editable_record=_editable_record(item),
    )


def _template_scope(
    session: Session,
    *,
    store_code: str,
    product_id: str,
    sku_id: str | None,
) -> dict[str, str | None]:
    product = session.get(TestProduct, product_id)
    if product is None or product.store_code != store_code:
        raise AppError(
            "KNOWLEDGE_TEMPLATE_SCOPE_INVALID",
            "页面所选商品不属于当前店铺，请重新选择。",
            status_code=422,
        )
    store = session.scalar(
        select(TestStore).where(
            TestStore.package_id == product.package_id,
            TestStore.store_code == product.store_code,
        )
    )
    if store is None:
        raise AppError(
            "KNOWLEDGE_TEMPLATE_SCOPE_INVALID", "无法确认所选店铺范围。", status_code=422
        )
    sku_name: str | None = None
    if sku_id:
        sku = session.get(TestSku, sku_id)
        if sku is None or sku.product_id != product.product_id:
            raise AppError(
                "KNOWLEDGE_TEMPLATE_SCOPE_INVALID",
                "页面所选SKU不属于当前商品，请重新选择。",
                status_code=422,
            )
        sku_name = sku.sku_name_display or sku.sku_name_official
    return {
        "store_name": store.store_name,
        "product_name": product.product_name_display or product.product_name_official,
        "sku_name": sku_name,
    }


def _same_analysis_payload(
    assessment: KnowledgeQualityAssessment, payload: KnowledgeQualityAnalysisResultCreate
) -> bool:
    return (
        assessment.material_id == payload.material_id
        and assessment.revision == payload.revision
        and assessment.content_hash == payload.content_hash
        and assessment.analysis_run_id == payload.analysis_run_id
        and assessment.model_version == payload.model_version
        and assessment.prompt_version == payload.prompt_version
        and assessment.summary == payload.summary
        and [
            {key: value for key, value in gap.items() if key not in {"gap_id", "status"}}
            for gap in assessment.gaps
        ]
        == [gap.model_dump(mode="json") for gap in payload.gaps]
    )


@admin_router.post("", response_model=KnowledgeMaterialReceipt, status_code=201)
async def upload_knowledge_material(
    response: Response,
    file: UploadFile = File(...),
    store_code: str = Form(..., min_length=1, max_length=96),
    product_id: str = Form(..., min_length=1, max_length=128),
    sku_id: str | None = Form(default=None, max_length=128),
    material_type: KnowledgeMaterialType = Form(...),
    template_type: KnowledgeTemplateType | None = Form(default=None),
    display_name: str = Form(..., min_length=1, max_length=256),
    submitted_by: str = Form(..., min_length=1, max_length=128),
    material_id: str | None = Form(default=None, max_length=64),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
) -> KnowledgeMaterialReceipt:
    """Create an immutable controlled revision and a bounded recognition summary.

    ``material_id`` is an optional C-only correction reference.  When present,
    it creates the next revision instead of changing the approved revision.
    """
    key = idempotency_key.strip()
    if not key:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "Idempotency-Key 不能为空。", status_code=422
        )
    content = await file.read()
    values = {
        "material_id": material_id.strip() if material_id and material_id.strip() else None,
        "store_code": store_code.strip(),
        "product_id": product_id.strip(),
        "sku_id": sku_id.strip() if sku_id and sku_id.strip() else None,
        "material_type": material_type.value,
        "template_type": template_type.value if template_type else None,
        "display_name": display_name.strip(),
        "submitted_by": submitted_by.strip(),
    }
    if not values["store_code"] or not values["product_id"] or not values["display_name"] or not values["submitted_by"]:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "店铺、商品、资料名称和提交人不能为空。", status_code=422
        )
    expected_scope: dict[str, str | None] | None = None
    if template_type is not None:
        if _TEMPLATE_MATERIAL_TYPE[template_type] is not material_type:
            raise AppError(
                "KNOWLEDGE_TEMPLATE_TYPE_MISMATCH",
                "所选模板类型与资料类型不一致，请重新选择。",
                status_code=422,
            )
        expected_scope = _template_scope(
            session,
            store_code=str(values["store_code"]),
            product_id=str(values["product_id"]),
            sku_id=values["sku_id"],
        )
    fingerprint = fingerprint_upload(values, content)
    existing_receipt = session.scalar(
        select(KnowledgeMaterialUploadReceipt).where(
            KnowledgeMaterialUploadReceipt.request_method == _UPLOAD_METHOD,
            KnowledgeMaterialUploadReceipt.request_path == _UPLOAD_PATH,
            KnowledgeMaterialUploadReceipt.submitted_by == values["submitted_by"],
            KnowledgeMaterialUploadReceipt.idempotency_key == key,
        )
    )
    if existing_receipt is not None:
        if existing_receipt.request_fingerprint != fingerprint:
            raise AppError(
                "KNOWLEDGE_MATERIAL_IDEMPOTENCY_CONFLICT",
                "该 Idempotency-Key 已对应另一份资料。",
                status_code=409,
            )
        existing = session.get(KnowledgeMaterial, existing_receipt.material_record_id)
        if existing is None:
            raise AppError(
                "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "历史上传回执缺少资料记录。", status_code=404
            )
        response.status_code = 200
        return _receipt(existing)

    settings = get_settings()
    analysis_text, summary = recognize_material(
        filename=file.filename or "",
        content=content,
        material_type=material_type,
        max_bytes=settings.max_knowledge_material_upload_bytes,
        template_type=template_type,
        expected_scope=expected_scope,
    )
    previous = _current_revision(session, values["material_id"]) if values["material_id"] else None
    if values["material_id"] and previous is None:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "要修正的资料编号不存在。", status_code=422
        )
    if previous is not None and not _same_upload_scope(previous, values):
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "修正资料必须保持相同的业务范围、类型和资料身份。", status_code=422
        )
    next_material_id = previous.material_id if previous is not None else new_material_id()
    next_revision = previous.revision + 1 if previous is not None else 1
    raw_path = write_controlled_upload(
        storage_root=settings.knowledge_material_storage_dir,
        material_id=next_material_id,
        revision=next_revision,
        filename=file.filename or "source",
        content=content,
    )
    item = KnowledgeMaterial(
        material_id=next_material_id,
        revision=next_revision,
        store_code=values["store_code"],
        product_id=values["product_id"],
        sku_id=values["sku_id"],
        material_type=material_type,
        display_name=values["display_name"],
        original_filename=safe_filename(file.filename or "source"),
        content_hash=content_hash(content),
        recognition_summary=summary.model_dump(mode="json"),
        analysis_text=analysis_text,
        raw_storage_path=raw_path,
        material_status=KnowledgeMaterialStatus.RECOGNIZED,
        submitted_by=values["submitted_by"],
    )
    session.add(item)
    session.flush()
    session.add(
        KnowledgeMaterialUploadReceipt(
            request_method=_UPLOAD_METHOD,
            request_path=_UPLOAD_PATH,
            submitted_by=values["submitted_by"],
            idempotency_key=key,
            request_fingerprint=fingerprint,
            material_record_id=item.id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        remove_controlled_upload(item.raw_storage_path)
        raise AppError(
            "KNOWLEDGE_MATERIAL_IDEMPOTENCY_CONFLICT", "资料上传回执发生冲突。", status_code=409
        ) from None
    session.refresh(item)
    return _receipt(item)


@admin_router.get("", response_model=KnowledgeMaterialListResponse)
def list_knowledge_materials(
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=128),
    sku_id: str | None = Query(default=None, max_length=128),
    material_status: KnowledgeMaterialStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> KnowledgeMaterialListResponse:
    statement = select(KnowledgeMaterial)
    if store_code:
        statement = statement.where(KnowledgeMaterial.store_code == store_code)
    if product_id:
        statement = statement.where(KnowledgeMaterial.product_id == product_id)
    if sku_id:
        statement = statement.where(
            (KnowledgeMaterial.sku_id == sku_id) | (KnowledgeMaterial.sku_id.is_(None))
        )
    if material_status:
        statement = statement.where(KnowledgeMaterial.material_status == material_status)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(KnowledgeMaterial.updated_at.desc(), KnowledgeMaterial.material_id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return KnowledgeMaterialListResponse(items=[_summary(item) for item in items], total=total, page=page, size=size)


@admin_router.get("/{material_id}", response_model=KnowledgeMaterialDetail)
def get_knowledge_material(material_id: str, session: Session = Depends(get_db)) -> KnowledgeMaterialDetail:
    return _detail(_material_or_404(session, material_id))


@admin_router.get(
    "/{material_id}/revisions", response_model=KnowledgeMaterialRevisionListResponse
)
def list_knowledge_material_revisions(
    material_id: str, session: Session = Depends(get_db)
) -> KnowledgeMaterialRevisionListResponse:
    items = list(
        session.scalars(
            select(KnowledgeMaterial)
            .where(KnowledgeMaterial.material_id == material_id)
            .order_by(KnowledgeMaterial.revision.desc())
        ).all()
    )
    if not items:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED", "未找到对应的商品资料。", status_code=404
        )
    return KnowledgeMaterialRevisionListResponse(
        material_id=material_id,
        items=[_summary(item) for item in items],
        total=len(items),
    )


@admin_router.get(
    "/{material_id}/revisions/{revision}", response_model=KnowledgeMaterialDetail
)
def get_knowledge_material_revision(
    material_id: str, revision: int, session: Session = Depends(get_db)
) -> KnowledgeMaterialDetail:
    return _detail(_revision_or_404(session, material_id, revision))


@admin_router.get("/{material_id}/diff", response_model=KnowledgeMaterialDiffResponse)
def diff_knowledge_material_revisions(
    material_id: str,
    from_revision: int = Query(ge=1),
    to_revision: int = Query(ge=1),
    session: Session = Depends(get_db),
) -> KnowledgeMaterialDiffResponse:
    before = _revision_or_404(session, material_id, from_revision)
    after = _revision_or_404(session, material_id, to_revision)
    before_fields = _editable_record(before) or {}
    after_fields = _editable_record(after) or {}
    changes = [
        KnowledgeMaterialFieldChange(
            field=field,
            before=before_fields.get(field),
            after=after_fields.get(field),
        )
        for field in sorted(set(before_fields) | set(after_fields))
        if before_fields.get(field) != after_fields.get(field)
    ]
    return KnowledgeMaterialDiffResponse(
        material_id=material_id,
        from_revision=from_revision,
        to_revision=to_revision,
        from_content_hash=before.content_hash,
        to_content_hash=after.content_hash,
        changes=changes,
    )


@admin_router.post("/{material_id}/review", response_model=KnowledgeMaterialSummary)
def review_knowledge_material(
    material_id: str, payload: KnowledgeMaterialReview, session: Session = Depends(get_db)
) -> KnowledgeMaterialSummary:
    item = _material_or_404(session, material_id)
    if item.revision != payload.revision:
        raise AppError(
            "KNOWLEDGE_MATERIAL_REVISION_MISMATCH", "审核版本与当前资料版本不一致。", status_code=409
        )
    if item.material_status != KnowledgeMaterialStatus.RECOGNIZED:
        raise AppError(
            "KNOWLEDGE_MATERIAL_STATE_INVALID", "仅已识别的资料可以进入人工审核。", status_code=409
        )
    item.material_status = KnowledgeMaterialStatus.REVIEWING
    item.reviewed_by = payload.reviewed_by
    item.reviewed_at = utc_now()
    item.review_note = payload.review_note
    item.material_status = (
        KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS
        if payload.decision is KnowledgeMaterialReviewDecision.APPROVE_FOR_ANALYSIS
        else KnowledgeMaterialStatus.REJECTED
    )
    session.commit()
    session.refresh(item)
    return _summary(item)


@ai_quality_router.get("/analysis-inputs", response_model=KnowledgeQualityAnalysisInputListResponse)
def export_approved_knowledge_quality_inputs(
    material_status: KnowledgeMaterialStatus = Query(default=KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> KnowledgeQualityAnalysisInputListResponse:
    if material_status is not KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS:
        raise AppError(
            "KNOWLEDGE_MATERIAL_STATE_INVALID", "只可导出已人工审核通过的资料快照。", status_code=409
        )
    statement = select(KnowledgeMaterial).where(
        KnowledgeMaterial.material_status == KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS
    )
    approved_rows = list(
        session.scalars(
            statement.order_by(KnowledgeMaterial.created_at, KnowledgeMaterial.material_id)
        ).all()
    )
    eligible_rows = [
        item
        for item in approved_rows
        if (item.recognition_summary or {}).get("template_type")
        not in _NON_AI_KNOWLEDGE_TEMPLATES
    ]
    total = len(eligible_rows)
    rows = eligible_rows[(page - 1) * size: page * size]
    return KnowledgeQualityAnalysisInputListResponse(
        items=[
            KnowledgeQualityAnalysisInput(
                material_id=item.material_id,
                revision=item.revision,
                content_hash=item.content_hash,
                store_code=item.store_code,
                product_id=item.product_id,
                sku_id=item.sku_id,
                material_type=item.material_type,
                analysis_text=item.analysis_text,
                recognition_summary=RecognitionSummary(
                    readable=bool(item.recognition_summary.get("readable")),
                    file_extension=str(item.recognition_summary.get("file_extension") or ""),
                    detected_fields=list(item.recognition_summary.get("detected_fields") or []),
                    missing_expected_fields=list(
                        item.recognition_summary.get("missing_expected_fields") or []
                    ),
                    privacy_reminder=str(item.recognition_summary.get("privacy_reminder") or ""),
                ),
            )
            for item in rows
        ],
        total=total,
    )


@ai_quality_router.post(
    "/analysis-results", response_model=KnowledgeQualityAssessmentResponse, status_code=201
)
def record_knowledge_quality_analysis(
    payload: KnowledgeQualityAnalysisResultCreate,
    response: Response,
    session: Session = Depends(get_db),
) -> KnowledgeQualityAssessmentResponse:
    item = session.scalar(
        select(KnowledgeMaterial).where(
            KnowledgeMaterial.material_id == payload.material_id,
            KnowledgeMaterial.revision == payload.revision,
        )
    )
    if item is None or item.content_hash != payload.content_hash:
        raise AppError(
            "KNOWLEDGE_MATERIAL_REVISION_MISMATCH", "分析结果与受控资料快照不匹配。", status_code=409
        )
    same_run = session.scalar(
        select(KnowledgeQualityAssessment).where(
            KnowledgeQualityAssessment.analysis_run_id == payload.analysis_run_id
        )
    )
    if same_run is not None:
        current = _assessment_response(same_run)
        if _same_analysis_payload(same_run, payload):
            response.status_code = 200
            return current
        raise AppError(
            "KNOWLEDGE_MATERIAL_IDEMPOTENCY_CONFLICT", "analysis_run_id 已对应另一份分析结果。", status_code=409
        )
    existing = session.scalar(
        select(KnowledgeQualityAssessment).where(
            KnowledgeQualityAssessment.material_record_id == item.id
        )
    )
    if existing is not None:
        raise AppError(
            "KNOWLEDGE_MATERIAL_STATE_INVALID", "该不可变资料版本已拥有分析结果。", status_code=409
        )
    if item.material_status != KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS:
        raise AppError(
            "KNOWLEDGE_MATERIAL_STATE_INVALID", "只有人工审核通过的资料可以回写分析结果。", status_code=409
        )
    item.material_status = KnowledgeMaterialStatus.ANALYZING
    assessment = KnowledgeQualityAssessment(
        material_record_id=item.id,
        material_id=item.material_id,
        revision=item.revision,
        content_hash=item.content_hash,
        analysis_run_id=payload.analysis_run_id,
        model_version=payload.model_version,
        prompt_version=payload.prompt_version,
        overall_status=KnowledgeQualityOverallStatus.ANALYZED,
        summary=payload.summary,
        gaps=[
            gap_as_dict(
                KnowledgeQualityGap(
                    gap_id=f"KQG-{uuid4().hex[:16].upper()}",
                    status="OPEN",
                    **gap.model_dump(mode="json"),
                )
            )
            for gap in payload.gaps
        ],
    )
    session.add(assessment)
    item.material_status = KnowledgeMaterialStatus.ANALYZED
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(
            "KNOWLEDGE_MATERIAL_IDEMPOTENCY_CONFLICT", "分析结果写入发生冲突。", status_code=409
        ) from None
    session.refresh(assessment)
    return _assessment_response(assessment)


@ai_quality_router.get("/assessments", response_model=KnowledgeQualityAssessmentListResponse)
def list_knowledge_quality_assessments(
    session: Session = Depends(get_db),
) -> KnowledgeQualityAssessmentListResponse:
    """C-owned read-only Admin projection; raw material content is excluded."""
    statement = select(KnowledgeQualityAssessment).order_by(KnowledgeQualityAssessment.created_at.desc())
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(statement).all()
    return KnowledgeQualityAssessmentListResponse(
        items=[_assessment_response(item) for item in rows], total=total
    )


@customer_router.get("/api/v1/customer-knowledge-status", response_model=CustomerKnowledgeStatusResponse)
def get_customer_knowledge_status(
    store_code: str = Query(min_length=1, max_length=96),
    product_id: str = Query(min_length=1, max_length=128),
    sku_id: str | None = Query(default=None, max_length=128),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> CustomerKnowledgeStatusResponse:
    """Return only a compact Chinese scope status for B; never source content."""
    ensure_store_code_access(session, principal, store_code)
    scope = [
        KnowledgeMaterial.store_code == store_code,
        KnowledgeMaterial.product_id == product_id,
    ]
    if sku_id:
        scope.append((KnowledgeMaterial.sku_id == sku_id) | (KnowledgeMaterial.sku_id.is_(None)))
    else:
        scope.append(KnowledgeMaterial.sku_id.is_(None))
    material = session.scalar(
        select(KnowledgeMaterial)
        .where(*scope)
        .order_by(KnowledgeMaterial.updated_at.desc(), KnowledgeMaterial.revision.desc())
    )
    checked_at = datetime.now(timezone.utc)
    if material is None:
        return CustomerKnowledgeStatusResponse(
            status=CustomerKnowledgeStatusValue.NO_APPROVED_MATERIAL,
            summary="当前商品暂无已人工审核的资料；请在回复前人工核对商品信息。",
            last_checked_at=checked_at,
        )
    if material.material_status == KnowledgeMaterialStatus.ANALYZED:
        assessment = session.scalar(
            select(KnowledgeQualityAssessment).where(
                KnowledgeQualityAssessment.material_record_id == material.id
            )
        )
        open_gaps = [gap for gap in (assessment.gaps if assessment else []) if gap.get("status") == "OPEN"]
        if not open_gaps and assessment and assessment.overall_status == KnowledgeQualityOverallStatus.ANALYZED:
            return CustomerKnowledgeStatusResponse(
                status=CustomerKnowledgeStatusValue.READY,
                summary="该商品已有已审核资料并完成质量分析；仍请按现有客服流程人工确认回复。",
                last_checked_at=checked_at,
            )
        return CustomerKnowledgeStatusResponse(
            status=CustomerKnowledgeStatusValue.NEEDS_REVIEW,
            summary="该商品资料存在待补充项；请在回复前人工核对商品信息。",
            last_checked_at=checked_at,
        )
    if material.material_status in {
        KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS,
        KnowledgeMaterialStatus.ANALYZING,
        KnowledgeMaterialStatus.RECOGNIZED,
        KnowledgeMaterialStatus.REVIEWING,
        KnowledgeMaterialStatus.RECEIVED,
    }:
        return CustomerKnowledgeStatusResponse(
            status=CustomerKnowledgeStatusValue.NEEDS_REVIEW,
            summary="该商品资料正在识别、审核或分析；请在回复前人工核对商品信息。",
            last_checked_at=checked_at,
        )
    return CustomerKnowledgeStatusResponse(
        status=CustomerKnowledgeStatusValue.NO_APPROVED_MATERIAL,
        summary="当前商品没有可供参考的已审核资料；请在回复前人工核对商品信息。",
        last_checked_at=checked_at,
    )
