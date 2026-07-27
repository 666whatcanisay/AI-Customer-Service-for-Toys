"""Versioned C-to-A feedback-case export and A-to-C analysis evidence routes."""

import hashlib
import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
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
from app.ai_feedback.models import AIResponseFeedback, AIResponseFeedbackAnalysis, utc_now
from app.ai_feedback.schemas import (
    AdminAIResponseFeedbackAnalysisResult,
    AdminAIResponseFeedbackAnalysisResultListResponse,
    AdminAIResponseFeedbackConfirmationResponse,
    AIResponseFeedbackAnalysisCreate,
    AIResponseFeedbackAnalysisResponse,
    AIResponseFeedbackConfirmation,
    AIResponseFeedbackExportItem,
    AIResponseFeedbackExportResponse,
    AIResponseFeedbackStatus,
    FeedbackContext,
)
from app.database import get_db
from app.errors import AppError


admin_router = APIRouter(
    prefix="/api/v1/admin/ai-response-feedback", tags=["admin-ai-response-feedback"]
)
ai_quality_router = APIRouter(prefix="/api/v1/admin/ai-quality", tags=["ai-quality"])


def _feedback_or_404(session: Session, feedback_id: str) -> AIResponseFeedback:
    item = session.scalar(
        select(AIResponseFeedback).where(AIResponseFeedback.feedback_id == feedback_id)
    )
    if item is None:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_NOT_FOUND", "AI response feedback was not found.", status_code=404
        )
    return item


def _content_hash(item: AIResponseFeedback) -> str:
    """Hash the frozen, A-visible feedback content with canonical UTF-8 JSON."""
    canonical = {
        "feedback_id": item.feedback_id,
        "revision": item.revision,
        "store_code": item.store_code,
        "product_id": item.product_id,
        "sku_id": item.sku_id,
        "question": item.question,
        "ai_answer": item.ai_answer,
        "final_answer": item.final_answer,
        "feedback_type": item.feedback_type,
        "feedback_note": item.feedback_note,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _confirmation_response(
    item: AIResponseFeedback,
) -> AdminAIResponseFeedbackConfirmationResponse:
    return AdminAIResponseFeedbackConfirmationResponse(
        feedback_id=item.feedback_id,
        revision=item.revision,
        status=item.status,
        analysis_status=item.analysis_status,
        content_hash=item.content_hash or "",
        confirmed_at=item.confirmed_at or item.created_at,
    )


def _analysis_response(
    item: AIResponseFeedback, analysis: AIResponseFeedbackAnalysis
) -> AIResponseFeedbackAnalysisResponse:
    return AIResponseFeedbackAnalysisResponse(
        feedback_id=item.feedback_id,
        revision=item.revision,
        status=item.status,
        analysis_status=item.analysis_status,
        analysis_run_id=analysis.analysis_run_id,
        model_version=analysis.model_version,
        prompt_version=analysis.prompt_version,
        analysis=analysis.analysis_json,
        suggestions=analysis.suggestions_json,
        recorded_at=analysis.recorded_at,
    )


def _admin_analysis_result(
    item: AIResponseFeedback, analysis: AIResponseFeedbackAnalysis
) -> AdminAIResponseFeedbackAnalysisResult:
    """Project only completed evidence for the internal read-only Admin pool."""
    return AdminAIResponseFeedbackAnalysisResult(
        feedback_id=item.feedback_id,
        revision=item.revision,
        content_hash=analysis.content_hash,
        feedback_type=analysis.feedback_type,
        analysis_run_id=analysis.analysis_run_id,
        analysis_status=item.analysis_status,
        model_version=analysis.model_version,
        prompt_version=analysis.prompt_version,
        analysis=analysis.analysis_json,
        suggestions=analysis.suggestions_json,
        created_at=analysis.recorded_at,
        question=item.question,
        ai_answer=item.ai_answer,
        final_answer=item.final_answer,
    )


def _same_analysis_payload(
    analysis: AIResponseFeedbackAnalysis, payload: AIResponseFeedbackAnalysisCreate
) -> bool:
    return (
        analysis.feedback_id == payload.feedback_id
        and analysis.content_hash == payload.content_hash
        and analysis.feedback_type == payload.feedback_type
        and analysis.analysis_run_id == payload.analysis_run_id
        and analysis.model_version == payload.model_version
        and analysis.prompt_version == payload.prompt_version
        and analysis.analysis_json == payload.analysis
        and analysis.suggestions_json == payload.suggestions
    )


@admin_router.post(
    "/{feedback_id}/confirm", response_model=AdminAIResponseFeedbackConfirmationResponse
)
def confirm_ai_response_feedback(
    feedback_id: str,
    payload: AIResponseFeedbackConfirmation,
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AdminAIResponseFeedbackConfirmationResponse:
    """C-only confirmation freezes v1 content before A can read it."""
    item = _feedback_or_404(session, feedback_id)
    if item.status != AIResponseFeedbackStatus.NEW or item.analysis_status != AIResponseFeedbackStatus.NEW:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_INVALID_STATUS_TRANSITION",
            "Only NEW feedback can be manually confirmed for analysis.",
            status_code=409,
        )
    item.confirmed_by = payload.confirmed_by
    item.confirmed_at = utc_now()
    item.confirmation_reason = payload.confirmation_reason
    item.content_hash = _content_hash(item)
    item.status = AIResponseFeedbackStatus.ANALYZING
    item.analysis_status = AIResponseFeedbackStatus.ANALYZING
    record_trial_audit_event(
        session,
        actor=actor,
        action="AI_FEEDBACK_CONFIRM",
        resource_type="AI_RESPONSE_FEEDBACK",
        resource_id=item.feedback_id,
        outcome="SUCCESS",
        reason=reason,
    )
    session.commit()
    session.refresh(item)
    return _confirmation_response(item)


@ai_quality_router.get("/badcases", response_model=AIResponseFeedbackExportResponse)
def export_confirmed_ai_badcases(
    cursor: str | None = Query(default=None, max_length=64),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> AIResponseFeedbackExportResponse:
    """Read only manually confirmed v1 feedback; GET never changes lifecycle state."""
    statement = select(AIResponseFeedback).where(
        AIResponseFeedback.status == AIResponseFeedbackStatus.ANALYZING,
        AIResponseFeedback.analysis_status == AIResponseFeedbackStatus.ANALYZING,
        AIResponseFeedback.content_hash.is_not(None),
    )
    if cursor:
        statement = statement.where(AIResponseFeedback.feedback_id > cursor)
    rows = session.scalars(statement.order_by(AIResponseFeedback.feedback_id).limit(size + 1)).all()
    page_rows = rows[:size]
    next_cursor = page_rows[-1].feedback_id if len(rows) > size and page_rows else None
    items = [
        AIResponseFeedbackExportItem(
            feedback_id=item.feedback_id,
            revision=item.revision,
            store_code=item.store_code,
            product_id=item.product_id,
            sku_id=item.sku_id,
            question=item.question,
            ai_answer=item.ai_answer,
            final_answer=item.final_answer,
            feedback_type=item.feedback_type,
            feedback_note=item.feedback_note,
            context=FeedbackContext(
                store_code=item.store_code,
                product_id=item.product_id,
                sku_id=item.sku_id,
            ),
            content_hash=item.content_hash or "",
            redaction_version=item.redaction_version,
        )
        for item in page_rows
    ]
    return AIResponseFeedbackExportResponse(items=items, next_cursor=next_cursor)


@ai_quality_router.post(
    "/analysis-results", response_model=AIResponseFeedbackAnalysisResponse, status_code=201
)
def record_ai_response_feedback_analysis(
    payload: AIResponseFeedbackAnalysisCreate,
    response: Response,
    session: Session = Depends(get_db),
) -> AIResponseFeedbackAnalysisResponse:
    """Persist A evidence only; this route never applies suggestions or takes action."""
    item = _feedback_or_404(session, payload.feedback_id)
    if item.revision != payload.revision:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_EXPORT_SNAPSHOT_MISMATCH",
            "The analysis revision does not match the controlled feedback snapshot.",
            status_code=409,
        )

    same_run = session.scalar(
        select(AIResponseFeedbackAnalysis).where(
            AIResponseFeedbackAnalysis.analysis_run_id == payload.analysis_run_id
        )
    )
    if same_run is not None:
        if same_run.feedback_record_id == item.id and _same_analysis_payload(same_run, payload):
            response.status_code = 200
            return _analysis_response(item, same_run)
        raise AppError(
            "AI_RESPONSE_FEEDBACK_ANALYSIS_CONFLICT",
            "analysis_run_id is already associated with different analysis evidence.",
            status_code=409,
        )

    existing = session.scalar(
        select(AIResponseFeedbackAnalysis).where(
            AIResponseFeedbackAnalysis.feedback_record_id == item.id
        )
    )
    if existing is not None:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_ANALYSIS_CONFLICT",
            "This feedback revision already has a successful analysis result.",
            status_code=409,
        )
    if item.status != AIResponseFeedbackStatus.ANALYZING or item.analysis_status != AIResponseFeedbackStatus.ANALYZING:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_NOT_EXPORTABLE",
            "Only manually confirmed feedback can receive analysis evidence.",
            status_code=409,
        )
    if item.content_hash is None:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_NOT_EXPORTABLE",
            "The confirmed feedback does not have a controlled content hash.",
            status_code=409,
        )
    if payload.content_hash != item.content_hash:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_EXPORT_SNAPSHOT_MISMATCH",
            "The analysis content_hash does not match the controlled feedback snapshot.",
            status_code=409,
        )
    if payload.feedback_type != item.feedback_type:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_TYPE_MISMATCH",
            "The analysis feedback_type must match the submitted feedback_type.",
            status_code=409,
        )

    analysis = AIResponseFeedbackAnalysis(
        feedback_record_id=item.id,
        feedback_id=item.feedback_id,
        content_hash=item.content_hash,
        feedback_type=item.feedback_type,
        analysis_run_id=payload.analysis_run_id,
        model_version=payload.model_version,
        prompt_version=payload.prompt_version,
        analysis_json=payload.analysis,
        suggestions_json=payload.suggestions,
    )
    session.add(analysis)
    item.status = AIResponseFeedbackStatus.ANALYZED
    item.analysis_status = AIResponseFeedbackStatus.ANALYZED
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(
            "AI_RESPONSE_FEEDBACK_ANALYSIS_CONFLICT",
            "The analysis result conflicts with an existing successful analysis.",
            status_code=409,
        ) from None
    session.refresh(item)
    session.refresh(analysis)
    return _analysis_response(item, analysis)


@ai_quality_router.get(
    "/analysis-results", response_model=AdminAIResponseFeedbackAnalysisResultListResponse
)
def list_admin_ai_response_feedback_analysis_results(
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> AdminAIResponseFeedbackAnalysisResultListResponse:
    """Read completed evidence only; this internal Admin view has no lifecycle side effects."""
    statement = (
        select(AIResponseFeedback, AIResponseFeedbackAnalysis)
        .join(
            AIResponseFeedbackAnalysis,
            AIResponseFeedbackAnalysis.feedback_record_id == AIResponseFeedback.id,
        )
        .where(
            AIResponseFeedback.status == AIResponseFeedbackStatus.ANALYZED,
            AIResponseFeedback.analysis_status == AIResponseFeedbackStatus.ANALYZED,
        )
    )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.execute(
        statement.order_by(AIResponseFeedbackAnalysis.recorded_at.desc(), AIResponseFeedback.feedback_id.desc())
    ).all()
    record_trial_audit_event(
        session,
        actor=actor,
        action="AI_FEEDBACK_ANALYSIS_VIEW",
        resource_type="AI_RESPONSE_FEEDBACK",
        resource_id="analyzed-collection",
        outcome="SUCCESS",
        reason=reason,
        metadata={"returned_count": len(rows)},
    )
    session.commit()
    return AdminAIResponseFeedbackAnalysisResultListResponse(
        items=[_admin_analysis_result(item, analysis) for item, analysis in rows], total=total
    )
