"""C Admin review, immutable export, and evaluation evidence endpoints."""

from collections.abc import Iterable

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.trial_governance import (
    TrialActor,
    TrialAuditReason,
    TrialRole,
    get_trial_reason,
    record_trial_audit_event,
    require_trial_roles,
)
from app.database import get_db
from app.errors import AppError
from app.experience_cases.models import (
    CustomerExperienceCase,
    CustomerExperienceCaseExport,
    CustomerExperienceEvaluation,
    utc_now,
)
from app.experience_cases.schemas import (
    ALLOWED_REVIEW_TRANSITIONS,
    AdminExperienceCaseListResponse,
    AdminExperienceCaseResponse,
    AiOptimizationCaseListResponse,
    AiOptimizationCaseResponse,
    CustomerExperienceCaseListResponse,
    EvaluationStatus,
    ExperienceCaseEvaluationCreate,
    ExperienceCaseEvaluationListResponse,
    ExperienceCaseEvaluationResponse,
    ExperienceCaseExportItem,
    ExperienceCaseExportResponse,
    ExperienceCaseReviewStatus,
    ExperienceCaseReviewUpdate,
    ExportContext,
)
from app.experience_cases.service import create_export_snapshot

admin_router = APIRouter(
    prefix="/api/v1/admin/customer-experience-cases", tags=["admin-customer-experience-cases"]
)
ai_optimization_router = APIRouter(prefix="/api/v1/admin/ai-optimization", tags=["ai-optimization"])


def _admin_response(item: CustomerExperienceCase) -> AdminExperienceCaseResponse:
    return AdminExperienceCaseResponse(
        case_id=item.case_id,
        revision=item.revision,
        source_type=item.source_type,
        store_code=item.store_code,
        product_id=item.product_id,
        sku_id=item.sku_id,
        question=item.question,
        ai_answer=item.ai_answer,
        final_answer=item.final_answer,
        feedback_type=item.feedback_type,
        created_by=item.created_by,
        review_status=item.review_status,
        review_note=item.review_note,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        export_revision=item.export_revision,
        content_hash=item.content_hash,
        redaction_version=item.redaction_version,
        evaluation_status=item.evaluation_status,
        latest_evaluation_run_id=item.latest_evaluation_run_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _evaluation_response(item: CustomerExperienceEvaluation) -> ExperienceCaseEvaluationResponse:
    return ExperienceCaseEvaluationResponse(
        evaluation_run_id=item.evaluation_run_id,
        case_id=item.case_id,
        revision=item.revision,
        export_revision=item.export_revision,
        evaluation_status=EvaluationStatus.EVALUATED,
        model_version=item.model_version,
        prompt_version=item.prompt_version,
        result=item.result_json,
        suggestions=item.suggestions_json,
        recorded_at=item.recorded_at,
    )


def _export_response(item: CustomerExperienceCaseExport) -> ExperienceCaseExportItem:
    return ExperienceCaseExportItem(
        case_id=item.case_id,
        revision=item.revision,
        export_revision=item.export_revision,
        store_code=item.store_code,
        product_id=item.product_id,
        sku_id=item.sku_id,
        question=item.question,
        ai_answer=item.ai_answer,
        final_answer=item.final_answer,
        context=ExportContext(
            store_code=item.store_code,
            product_id=item.product_id,
            sku_id=item.sku_id,
        ),
        content_hash=item.content_hash,
        redaction_version=item.redaction_version,
    )


def _case_or_404(session: Session, case_id: str) -> CustomerExperienceCase:
    item = session.scalar(
        select(CustomerExperienceCase)
        .where(CustomerExperienceCase.case_id == case_id)
        .order_by(CustomerExperienceCase.revision.desc())
    )
    if item is None:
        raise AppError("EXPERIENCE_CASE_NOT_FOUND", "Customer experience case was not found", status_code=404)
    return item


@admin_router.get("", response_model=AdminExperienceCaseListResponse)
def list_admin_experience_cases(
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=128),
    sku_id: str | None = Query(default=None, max_length=128),
    review_status: ExperienceCaseReviewStatus | None = None,
    created_by: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AdminExperienceCaseListResponse:
    statement = select(CustomerExperienceCase)
    if store_code:
        statement = statement.where(CustomerExperienceCase.store_code == store_code)
    if product_id:
        statement = statement.where(CustomerExperienceCase.product_id == product_id)
    if sku_id:
        statement = statement.where(CustomerExperienceCase.sku_id == sku_id)
    if review_status:
        statement = statement.where(CustomerExperienceCase.review_status == review_status)
    if created_by:
        statement = statement.where(CustomerExperienceCase.created_by == created_by)

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(CustomerExperienceCase.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    record_trial_audit_event(
        session,
        actor=actor,
        action="EXPERIENCE_CASE_VIEW",
        resource_type="CUSTOMER_EXPERIENCE_CASE",
        resource_id="collection",
        outcome="SUCCESS",
        reason=reason,
        metadata={"returned_count": len(items)},
    )
    session.commit()
    return AdminExperienceCaseListResponse(
        items=[_admin_response(item) for item in items], total=total, page=page, size=size
    )


@admin_router.get("/{case_id}", response_model=AdminExperienceCaseResponse)
def get_admin_experience_case(
    case_id: str,
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AdminExperienceCaseResponse:
    item = _case_or_404(session, case_id)
    record_trial_audit_event(
        session,
        actor=actor,
        action="EXPERIENCE_CASE_VIEW",
        resource_type="CUSTOMER_EXPERIENCE_CASE",
        resource_id=item.case_id,
        outcome="SUCCESS",
        reason=reason,
    )
    session.commit()
    return _admin_response(item)


@admin_router.patch("/{case_id}/review", response_model=AdminExperienceCaseResponse)
def review_customer_experience_case(
    case_id: str,
    payload: ExperienceCaseReviewUpdate,
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AdminExperienceCaseResponse:
    item = _case_or_404(session, case_id)
    current = ExperienceCaseReviewStatus(item.review_status)

    if current is ExperienceCaseReviewStatus.APPROVED:
        raise AppError(
            "EXPERIENCE_CASE_REVISION_CONFLICT",
            "An approved case revision is immutable and cannot be overwritten.",
            status_code=409,
        )
    if payload.review_status != current:
        if payload.review_status not in ALLOWED_REVIEW_TRANSITIONS[current]:
            raise AppError(
                "EXPERIENCE_CASE_INVALID_STATUS_TRANSITION",
                "The requested review transition is not allowed.",
                status_code=409,
            )
        if not payload.reviewed_by:
            raise AppError(
                "EXPERIENCE_CASE_VALIDATION_FAILED",
                "A test operator identifier is required for a review transition.",
                status_code=422,
            )
        item.review_status = payload.review_status
        item.reviewed_by = payload.reviewed_by
        if payload.review_status in {
            ExperienceCaseReviewStatus.APPROVED,
            ExperienceCaseReviewStatus.REJECTED,
        }:
            item.reviewed_at = utc_now()
    elif payload.reviewed_by:
        item.reviewed_by = payload.reviewed_by

    if "review_note" in payload.model_fields_set:
        item.review_note = payload.review_note

    if item.review_status == ExperienceCaseReviewStatus.APPROVED and item.export_revision is None:
        snapshot = create_export_snapshot(item)
        session.add(snapshot)

    record_trial_audit_event(
        session,
        actor=actor,
        action="EXPERIENCE_CASE_REVIEW",
        resource_type="CUSTOMER_EXPERIENCE_CASE",
        resource_id=item.case_id,
        outcome="SUCCESS",
        reason=reason,
        metadata={"review_status": item.review_status},
    )
    session.commit()
    session.refresh(item)
    return _admin_response(item)


def _decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        case_id, revision_text = cursor.rsplit(":", maxsplit=1)
        revision = int(revision_text)
    except (TypeError, ValueError):
        raise AppError(
            "EXPERIENCE_CASE_VALIDATION_FAILED", "The export cursor is invalid.", status_code=422
        ) from None
    if not case_id or revision < 1:
        raise AppError("EXPERIENCE_CASE_VALIDATION_FAILED", "The export cursor is invalid.", status_code=422)
    return case_id, revision


@ai_optimization_router.get("/cases/export", response_model=ExperienceCaseExportResponse)
def export_approved_experience_cases(
    cursor: str | None = Query(default=None, max_length=200),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> ExperienceCaseExportResponse:
    statement = (
        select(CustomerExperienceCaseExport, CustomerExperienceCase)
        .join(CustomerExperienceCase, CustomerExperienceCase.id == CustomerExperienceCaseExport.case_record_id)
        .where(CustomerExperienceCase.review_status == ExperienceCaseReviewStatus.APPROVED)
        .where(CustomerExperienceCase.evaluation_status != EvaluationStatus.EVALUATED)
    )
    if cursor:
        case_id, revision = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                CustomerExperienceCaseExport.case_id > case_id,
                and_(
                    CustomerExperienceCaseExport.case_id == case_id,
                    CustomerExperienceCaseExport.revision > revision,
                ),
            )
        )

    rows = session.execute(
        statement.order_by(CustomerExperienceCaseExport.case_id, CustomerExperienceCaseExport.revision).limit(size + 1)
    ).all()
    page_rows = rows[:size]
    for _, case in page_rows:
        if case.evaluation_status == EvaluationStatus.NOT_EXPORTED:
            case.evaluation_status = EvaluationStatus.EXPORTED
    if page_rows:
        session.commit()

    items = [_export_response(snapshot) for snapshot, _ in page_rows]
    next_cursor = None
    if len(rows) > size and page_rows:
        last_snapshot, _ = page_rows[-1]
        next_cursor = f"{last_snapshot.case_id}:{last_snapshot.revision}"
    return ExperienceCaseExportResponse(items=items, next_cursor=next_cursor)


@ai_optimization_router.post(
    "/evaluation-results", response_model=ExperienceCaseEvaluationResponse, status_code=201
)
def record_experience_case_evaluation(
    payload: ExperienceCaseEvaluationCreate,
    session: Session = Depends(get_db),
) -> ExperienceCaseEvaluationResponse:
    case = session.scalar(
        select(CustomerExperienceCase).where(
            CustomerExperienceCase.case_id == payload.case_id,
            CustomerExperienceCase.revision == payload.revision,
        )
    )
    if case is None:
        raise AppError("EXPERIENCE_CASE_NOT_FOUND", "Customer experience case was not found", status_code=404)
    if case.review_status != ExperienceCaseReviewStatus.APPROVED or not case.export_revision:
        raise AppError(
            "EXPERIENCE_CASE_NOT_EXPORTABLE",
            "Only an approved case with a frozen export snapshot can receive evaluation evidence.",
            status_code=409,
        )

    snapshot = session.scalar(
        select(CustomerExperienceCaseExport).where(
            CustomerExperienceCaseExport.case_record_id == case.id,
            CustomerExperienceCaseExport.export_revision == case.export_revision,
        )
    )
    if snapshot is None:
        raise AppError(
            "EXPERIENCE_CASE_NOT_EXPORTABLE",
            "The approved case does not have a frozen export snapshot.",
            status_code=409,
        )
    if (
        payload.export_revision != snapshot.export_revision
        or payload.content_hash != snapshot.content_hash
    ):
        case.evaluation_status = EvaluationStatus.WRITEBACK_REJECTED
        session.commit()
        raise AppError(
            "EXPERIENCE_CASE_EXPORT_SNAPSHOT_MISMATCH",
            "The evaluation evidence does not match the approved export snapshot.",
            status_code=409,
        )

    record = CustomerExperienceEvaluation(
        case_record_id=case.id,
        case_id=case.case_id,
        revision=case.revision,
        export_revision=snapshot.export_revision,
        content_hash=snapshot.content_hash,
        evaluation_run_id=payload.evaluation_run_id,
        model_version=payload.model_version,
        prompt_version=payload.prompt_version,
        result_json=payload.result,
        suggestions_json=payload.suggestions,
    )
    session.add(record)
    case.evaluation_status = EvaluationStatus.EVALUATED
    case.latest_evaluation_run_id = payload.evaluation_run_id
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(
            "EXPERIENCE_CASE_REVISION_CONFLICT",
            "Evaluation evidence for this export revision and run already exists.",
            status_code=409,
        ) from None
    session.refresh(record)
    return _evaluation_response(record)


@ai_optimization_router.get("/cases", response_model=AiOptimizationCaseListResponse)
def list_ai_optimization_cases(
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=128),
    sku_id: str | None = Query(default=None, max_length=128),
    evaluation_status: EvaluationStatus | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AiOptimizationCaseListResponse:
    statement = select(CustomerExperienceCase).where(
        CustomerExperienceCase.review_status == ExperienceCaseReviewStatus.APPROVED
    )
    if store_code:
        statement = statement.where(CustomerExperienceCase.store_code == store_code)
    if product_id:
        statement = statement.where(CustomerExperienceCase.product_id == product_id)
    if sku_id:
        statement = statement.where(CustomerExperienceCase.sku_id == sku_id)
    if evaluation_status:
        statement = statement.where(CustomerExperienceCase.evaluation_status == evaluation_status)

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    cases = session.scalars(
        statement.order_by(CustomerExperienceCase.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items: list[AiOptimizationCaseResponse] = []
    for case in cases:
        evaluation = None
        if case.latest_evaluation_run_id:
            record = session.scalar(
                select(CustomerExperienceEvaluation).where(
                    CustomerExperienceEvaluation.case_record_id == case.id,
                    CustomerExperienceEvaluation.evaluation_run_id == case.latest_evaluation_run_id,
                )
            )
            if record is not None:
                evaluation = _evaluation_response(record)
        items.append(
            AiOptimizationCaseResponse(
                case_id=case.case_id,
                revision=case.revision,
                store_code=case.store_code,
                product_id=case.product_id,
                sku_id=case.sku_id,
                question=case.question,
                ai_answer=case.ai_answer,
                final_answer=case.final_answer,
                feedback_type=case.feedback_type,
                export_revision=case.export_revision or "",
                content_hash=case.content_hash or "",
                evaluation_status=case.evaluation_status,
                latest_evaluation_run_id=case.latest_evaluation_run_id,
                latest_evaluation=evaluation,
            )
        )
    record_trial_audit_event(
        session,
        actor=actor,
        action="EXPERIENCE_CASE_EVALUATION_VIEW",
        resource_type="CUSTOMER_EXPERIENCE_CASE",
        resource_id="approved-collection",
        outcome="SUCCESS",
        reason=reason,
        metadata={"returned_count": len(items)},
    )
    session.commit()
    return AiOptimizationCaseListResponse(items=items, total=total, page=page, size=size)


@ai_optimization_router.get(
    "/cases/{case_id}/evaluations", response_model=ExperienceCaseEvaluationListResponse
)
def list_case_evaluations(
    case_id: str,
    revision: int = Query(default=1, ge=1),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> ExperienceCaseEvaluationListResponse:
    case = session.scalar(
        select(CustomerExperienceCase).where(
            CustomerExperienceCase.case_id == case_id,
            CustomerExperienceCase.revision == revision,
        )
    )
    if case is None:
        raise AppError("EXPERIENCE_CASE_NOT_FOUND", "Customer experience case was not found", status_code=404)
    items = session.scalars(
        select(CustomerExperienceEvaluation)
        .where(
            CustomerExperienceEvaluation.case_record_id == case.id,
            CustomerExperienceEvaluation.revision == revision,
        )
        .order_by(CustomerExperienceEvaluation.recorded_at.desc())
    ).all()
    record_trial_audit_event(
        session,
        actor=actor,
        action="EXPERIENCE_CASE_EVALUATION_VIEW",
        resource_type="CUSTOMER_EXPERIENCE_CASE",
        resource_id=case.case_id,
        outcome="SUCCESS",
        reason=reason,
        metadata={"returned_count": len(items)},
    )
    session.commit()
    return ExperienceCaseEvaluationListResponse(
        items=[_evaluation_response(item) for item in items], total=len(items)
    )
