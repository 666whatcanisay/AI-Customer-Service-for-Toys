"""Business rules for event capture, issue handling, and knowledge-task verification."""

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customer_feedback_loop.models import (
    AIInteractionEvent,
    AIProblem,
    AIProblemOccurrence,
    KnowledgeOptimizationTask,
    utc_now,
)
from app.customer_feedback_loop.schemas import (
    AdminInteractionEvent,
    AIProblemProjection,
    AIProblemStatus,
    AIProblemStatusUpdate,
    AIProblemType,
    InteractionActionType,
    InteractionEventCreate,
    InteractionEventReceipt,
    InteractionEventStatus,
    KnowledgeTaskCreate,
    KnowledgeTaskProjection,
    KnowledgeTaskStatus,
    KnowledgeTaskStatusUpdate,
    KnowledgeTaskVerification,
    VerificationResult,
)
from app.errors import AppError


_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_IDENTITY = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}[01]\d[0-3]\d{4}[\dXx](?!\d)")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{8,}(?!\d)")
_WHITESPACE = re.compile(r"\s+")
_SUMMARY_LIMIT = 240


def minimize_summary(value: str) -> str:
    """Remove common direct identifiers, normalize whitespace, and cap storage."""
    text = _EMAIL.sub("[邮箱已移除]", value)
    text = _PHONE.sub("[手机号已移除]", text)
    text = _IDENTITY.sub("[身份证号已移除]", text)
    text = _LONG_NUMBER.sub("[长编号已移除]", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:_SUMMARY_LIMIT] or "[摘要已最小化]"


def _request_fingerprint(payload: InteractionEventCreate) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _problem_fingerprint(event: AIInteractionEvent) -> str:
    question_key = minimize_summary(event.question_summary).casefold()
    canonical = "\x1f".join(
        [event.store_code, event.product_id, event.sku_id or "", question_key]
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def event_receipt(event: AIInteractionEvent) -> InteractionEventReceipt:
    return InteractionEventReceipt(
        event_id=event.event_id,
        interaction_id=event.interaction_id,
        status=InteractionEventStatus.RECORDED,
        occurred_at=event.occurred_at,
    )


def admin_event_projection(event: AIInteractionEvent) -> AdminInteractionEvent:
    return AdminInteractionEvent(
        event_id=event.event_id,
        interaction_id=event.interaction_id,
        store_code=event.store_code,
        store_name=event.store_name,
        product_id=event.product_id,
        product_name=event.product_name,
        sku_id=event.sku_id,
        sku_name=event.sku_name,
        action_type=event.action_type,
        occurred_at=event.occurred_at,
        created_by=event.created_by,
    )


def find_idempotent_event(
    session: Session, *, created_by: str, idempotency_key: str
) -> AIInteractionEvent | None:
    return session.scalar(
        select(AIInteractionEvent).where(
            AIInteractionEvent.created_by == created_by,
            AIInteractionEvent.idempotency_key == idempotency_key,
        )
    )


def create_interaction_event(
    session: Session,
    payload: InteractionEventCreate,
    idempotency_key: str,
) -> AIInteractionEvent:
    fingerprint = _request_fingerprint(payload)
    existing = find_idempotent_event(
        session, created_by=payload.created_by, idempotency_key=idempotency_key
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                "AI_INTERACTION_EVENT_IDEMPOTENCY_CONFLICT",
                "Idempotency-Key is already bound to another interaction event.",
                status_code=409,
            )
        return existing

    event = AIInteractionEvent(
        interaction_id=payload.interaction_id.strip(),
        store_code=payload.store_code.strip(),
        store_name=payload.store_name.strip(),
        product_id=payload.product_id.strip(),
        product_name=payload.product_name.strip(),
        sku_id=payload.sku_id.strip() if payload.sku_id else None,
        sku_name=payload.sku_name.strip() if payload.sku_name else None,
        action_type=payload.action_type,
        question_summary=minimize_summary(payload.question_summary),
        ai_answer_summary=minimize_summary(payload.ai_answer_summary),
        final_answer_summary=(
            minimize_summary(payload.final_answer_summary)
            if payload.final_answer_summary
            else None
        ),
        created_by=payload.created_by.strip(),
        redaction_version="feedback-summary-v1",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    session.add(event)
    session.flush()
    if payload.action_type is InteractionActionType.REJECTED:
        _record_problem_occurrence(session, event)
    return event


def _record_problem_occurrence(session: Session, event: AIInteractionEvent) -> AIProblem:
    fingerprint = _problem_fingerprint(event)
    problem = session.scalar(
        select(AIProblem).where(AIProblem.aggregation_fingerprint == fingerprint)
    )
    now = utc_now()
    if problem is None:
        problem = AIProblem(
            aggregation_fingerprint=fingerprint,
            store_code=event.store_code,
            store_name=event.store_name,
            product_id=event.product_id,
            product_name=event.product_name,
            sku_id=event.sku_id,
            sku_name=event.sku_name,
            question_summary=event.question_summary,
            ai_answer_summary=event.ai_answer_summary,
            issue_type=AIProblemType.UNCLASSIFIED,
            occurrence_count=0,
            status=AIProblemStatus.NEW,
            first_seen_at=event.occurred_at,
            last_seen_at=event.occurred_at,
        )
        session.add(problem)
        session.flush()
    elif problem.status in {AIProblemStatus.SOLVED, AIProblemStatus.VERIFIED}:
        problem.status = AIProblemStatus.NEW
        problem.status_changed_by = "system-new-occurrence"
        problem.status_note = "A new rejected interaction reopened this problem."

    problem.occurrence_count += 1
    problem.last_seen_at = now
    problem.ai_answer_summary = event.ai_answer_summary
    problem.updated_at = now
    session.add(
        AIProblemOccurrence(problem_record_id=problem.id, event_record_id=event.id)
    )
    return problem


_FEEDBACK_TYPE_MAP = {
    "FACT_ERROR": AIProblemType.PRODUCT_INFO_ERROR,
    "MISSING_INFO": AIProblemType.KNOWLEDGE_MISSING,
    "STYLE_ISSUE": AIProblemType.EXPRESSION_ISSUE,
    "RISK_ISSUE": AIProblemType.RISK_ISSUE,
    "OTHER": AIProblemType.UNCLASSIFIED,
}


def link_feedback_classification(
    session: Session,
    *,
    interaction_id: str,
    created_by: str,
    feedback_id: str,
    feedback_type: str,
) -> None:
    """Attach the existing optional feedback form to its saved rejection event."""
    event = session.scalar(
        select(AIInteractionEvent)
        .where(
            AIInteractionEvent.interaction_id == interaction_id,
            AIInteractionEvent.created_by == created_by,
            AIInteractionEvent.action_type == InteractionActionType.REJECTED,
        )
        .order_by(AIInteractionEvent.occurred_at.desc())
    )
    if event is None:
        raise AppError(
            "AI_INTERACTION_EVENT_NOT_FOUND",
            "The rejected interaction event must be recorded before its feedback reason.",
            status_code=409,
        )
    occurrence = session.scalar(
        select(AIProblemOccurrence).where(
            AIProblemOccurrence.event_record_id == event.id
        )
    )
    if occurrence is None:
        raise AppError(
            "AI_PROBLEM_OCCURRENCE_NOT_FOUND",
            "The interaction event has no AI-problem occurrence.",
            status_code=409,
        )
    occurrence.feedback_id = feedback_id
    problem = session.get(AIProblem, occurrence.problem_record_id)
    if problem is not None and problem.issue_type == AIProblemType.UNCLASSIFIED:
        problem.issue_type = _FEEDBACK_TYPE_MAP.get(
            str(feedback_type), AIProblemType.UNCLASSIFIED
        )
        problem.updated_at = utc_now()


def task_projection(task: KnowledgeOptimizationTask | None) -> KnowledgeTaskProjection | None:
    if task is None:
        return None
    return KnowledgeTaskProjection(
        task_id=task.task_id,
        source_problem_id=task.source_problem_id,
        store_code=task.store_code,
        product_id=task.product_id,
        sku_id=task.sku_id,
        missing_topic=task.missing_topic,
        status=task.status,
        status_note=task.status_note,
        verification_result=task.verification_result,
        verification_note=task.verification_note,
        verified_by=task.verified_by,
        verified_at=task.verified_at,
        created_by=task.created_by,
        updated_by=task.updated_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def problem_projection(
    session: Session, problem: AIProblem
) -> AIProblemProjection:
    task = session.scalar(
        select(KnowledgeOptimizationTask).where(
            KnowledgeOptimizationTask.problem_record_id == problem.id
        )
    )
    return AIProblemProjection(
        problem_id=problem.problem_id,
        store_code=problem.store_code,
        store_name=problem.store_name,
        product_id=problem.product_id,
        product_name=problem.product_name,
        sku_id=problem.sku_id,
        sku_name=problem.sku_name,
        question_summary=problem.question_summary,
        ai_answer_summary=problem.ai_answer_summary,
        issue_type=problem.issue_type,
        occurrence_count=problem.occurrence_count,
        status=problem.status,
        first_seen_at=problem.first_seen_at,
        last_seen_at=problem.last_seen_at,
        knowledge_task=task_projection(task),
    )


def problem_or_404(session: Session, problem_id: str) -> AIProblem:
    problem = session.scalar(
        select(AIProblem).where(AIProblem.problem_id == problem_id)
    )
    if problem is None:
        raise AppError("AI_PROBLEM_NOT_FOUND", "AI problem was not found.", status_code=404)
    return problem


def task_or_404(session: Session, task_id: str) -> KnowledgeOptimizationTask:
    task = session.scalar(
        select(KnowledgeOptimizationTask).where(
            KnowledgeOptimizationTask.task_id == task_id
        )
    )
    if task is None:
        raise AppError(
            "KNOWLEDGE_OPTIMIZATION_TASK_NOT_FOUND",
            "Knowledge optimization task was not found.",
            status_code=404,
        )
    return task


_PROBLEM_TRANSITIONS = {
    AIProblemStatus.NEW: {AIProblemStatus.CONFIRMED},
    AIProblemStatus.CONFIRMED: {AIProblemStatus.PROCESSING},
    AIProblemStatus.PROCESSING: {AIProblemStatus.SOLVED},
    AIProblemStatus.SOLVED: {AIProblemStatus.VERIFIED},
    AIProblemStatus.VERIFIED: set(),
}


def update_problem_status(
    session: Session, problem: AIProblem, payload: AIProblemStatusUpdate
) -> AIProblem:
    current = AIProblemStatus(problem.status)
    if payload.status not in _PROBLEM_TRANSITIONS[current]:
        raise AppError(
            "AI_PROBLEM_STATUS_TRANSITION_INVALID",
            f"AI problem cannot move from {current} to {payload.status}.",
            status_code=409,
        )
    next_type = payload.issue_type or AIProblemType(problem.issue_type)
    if payload.status is AIProblemStatus.CONFIRMED and next_type is AIProblemType.UNCLASSIFIED:
        raise AppError(
            "AI_PROBLEM_TYPE_REQUIRED",
            "A classified issue_type is required before confirmation.",
            status_code=422,
        )
    if payload.status is AIProblemStatus.VERIFIED:
        task = session.scalar(
            select(KnowledgeOptimizationTask).where(
                KnowledgeOptimizationTask.problem_record_id == problem.id,
                KnowledgeOptimizationTask.status == KnowledgeTaskStatus.VERIFIED,
            )
        )
        if task is None:
            raise AppError(
                "AI_PROBLEM_VERIFICATION_EVIDENCE_REQUIRED",
                "A verified knowledge optimization task is required.",
                status_code=409,
            )
    problem.status = payload.status
    problem.issue_type = next_type
    problem.status_changed_by = payload.operator.strip()
    problem.status_note = payload.note.strip() if payload.note else None
    problem.updated_at = utc_now()
    return problem


def create_knowledge_task(
    session: Session, problem: AIProblem, payload: KnowledgeTaskCreate
) -> KnowledgeOptimizationTask:
    if problem.status not in {AIProblemStatus.CONFIRMED, AIProblemStatus.PROCESSING}:
        raise AppError(
            "AI_PROBLEM_NOT_CONFIRMED",
            "The AI problem must be confirmed before creating a knowledge task.",
            status_code=409,
        )
    existing = session.scalar(
        select(KnowledgeOptimizationTask).where(
            KnowledgeOptimizationTask.problem_record_id == problem.id
        )
    )
    if existing is not None:
        raise AppError(
            "KNOWLEDGE_OPTIMIZATION_TASK_EXISTS",
            "This AI problem already has a knowledge optimization task.",
            status_code=409,
        )
    task = KnowledgeOptimizationTask(
        problem_record_id=problem.id,
        source_problem_id=problem.problem_id,
        store_code=problem.store_code,
        product_id=problem.product_id,
        sku_id=problem.sku_id,
        missing_topic=payload.missing_topic.strip(),
        status=KnowledgeTaskStatus.PENDING,
        created_by=payload.operator.strip(),
        updated_by=payload.operator.strip(),
        status_note=payload.note.strip() if payload.note else None,
    )
    session.add(task)
    problem.status = AIProblemStatus.PROCESSING
    problem.status_changed_by = payload.operator.strip()
    problem.status_note = "Knowledge optimization task created."
    problem.updated_at = utc_now()
    session.flush()
    return task


_TASK_TRANSITIONS = {
    KnowledgeTaskStatus.PENDING: {KnowledgeTaskStatus.IN_PROGRESS},
    KnowledgeTaskStatus.IN_PROGRESS: {KnowledgeTaskStatus.COMPLETED},
    KnowledgeTaskStatus.COMPLETED: set(),
    KnowledgeTaskStatus.VERIFIED: set(),
}


def update_knowledge_task_status(
    session: Session,
    task: KnowledgeOptimizationTask,
    payload: KnowledgeTaskStatusUpdate,
) -> KnowledgeOptimizationTask:
    current = KnowledgeTaskStatus(task.status)
    if payload.status not in _TASK_TRANSITIONS[current]:
        raise AppError(
            "KNOWLEDGE_OPTIMIZATION_TASK_STATUS_TRANSITION_INVALID",
            f"Knowledge task cannot move from {current} to {payload.status}.",
            status_code=409,
        )
    task.status = payload.status
    task.updated_by = payload.operator.strip()
    task.status_note = payload.note.strip() if payload.note else None
    task.updated_at = utc_now()
    problem = session.get(AIProblem, task.problem_record_id)
    if problem is not None:
        problem.status = (
            AIProblemStatus.SOLVED
            if payload.status is KnowledgeTaskStatus.COMPLETED
            else AIProblemStatus.PROCESSING
        )
        problem.status_changed_by = payload.operator.strip()
        problem.status_note = (
            "Knowledge supplement marked complete; verification is pending."
            if payload.status is KnowledgeTaskStatus.COMPLETED
            else "Knowledge supplement is in progress."
        )
        problem.updated_at = utc_now()
    return task


def verify_knowledge_task(
    session: Session,
    task: KnowledgeOptimizationTask,
    payload: KnowledgeTaskVerification,
) -> KnowledgeOptimizationTask:
    if task.status != KnowledgeTaskStatus.COMPLETED:
        raise AppError(
            "KNOWLEDGE_OPTIMIZATION_TASK_NOT_READY_FOR_VERIFICATION",
            "Only a completed knowledge task can be verified.",
            status_code=409,
        )
    now = utc_now()
    task.verification_result = payload.result
    task.verification_note = payload.note.strip()
    task.verified_by = payload.operator.strip()
    task.verified_at = now
    task.updated_by = payload.operator.strip()
    task.updated_at = now
    problem = session.get(AIProblem, task.problem_record_id)
    if payload.result is VerificationResult.IMPROVED:
        task.status = KnowledgeTaskStatus.VERIFIED
        if problem is not None:
            problem.status = AIProblemStatus.VERIFIED
            problem.status_note = "AI improvement was manually rechecked and recorded."
    else:
        task.status = KnowledgeTaskStatus.IN_PROGRESS
        if problem is not None:
            problem.status = AIProblemStatus.PROCESSING
            problem.status_note = "Recheck did not improve; knowledge task returned to processing."
    if problem is not None:
        problem.status_changed_by = payload.operator.strip()
        problem.updated_at = now
    return task
