from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.iam.dependencies import Principal, ensure_store_code_access, get_current_principal, require_permission
from app.reply_readiness.ai_client import ReplyReadinessAiClient, ReplyReadinessAiUnavailable
from app.reply_readiness.models import ReplyReadinessRun
from app.reply_readiness.rate_limit import (
    ReplyDebugRateLimiter,
    ReplyDebugRateLimitExceeded,
)
from app.reply_readiness.schemas import (
    PddQuestionSetProjection,
    PddReplyReadinessInputV1,
    PddReplyReadinessPublishedDebugResultV1,
    PddReplyReadinessResultV1,
    QuestionSetExtensionCreate,
    QuestionSetExtensionList,
    QuestionSetExtensionProjection,
    ReplyReadinessDebugRequest,
    ReplyReadinessRunComparison,
    ReplyReadinessRunCreate,
    ReplyReadinessRunList,
    ReplyReadinessRunProjection,
    ReplyReadinessScopeV1,
)
from app.reply_readiness.service import ReplyReadinessService
from app.workspace.service import StoreContextService


admin_router = APIRouter(prefix="/api/v1/admin/reply-readiness", tags=["reply-readiness"])
internal_router = APIRouter(prefix="/api/v1/internal/reply-readiness", tags=["reply-readiness-internal"])
_require_knowledge_manage = require_permission("knowledge.manage")


def _service(session: Session, principal: Principal) -> ReplyReadinessService:
    return ReplyReadinessService(session, principal.user_id)


def _ai_client(request: Request) -> ReplyReadinessAiClient:
    injected = getattr(request.app.state, "reply_readiness_ai_client", None)
    return injected if injected is not None else ReplyReadinessAiClient()


def _debug_rate_limiter(request: Request) -> ReplyDebugRateLimiter:
    limiter = getattr(request.app.state, "reply_debug_rate_limiter", None)
    if not isinstance(limiter, ReplyDebugRateLimiter):
        raise AppError(
            "REPLY_DEBUG_RATE_LIMIT_UNAVAILABLE",
            "正式只读回答调试保护器不可用。",
            status_code=503,
        )
    return limiter


@admin_router.get("/question-set", response_model=PddQuestionSetProjection)
def get_effective_question_set(
    store_code: str = Query(min_length=1, max_length=96),
    product_id: str = Query(min_length=1, max_length=96),
    sku_id: str | None = Query(default=None, max_length=128),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> PddQuestionSetProjection:
    ensure_store_code_access(session, principal, store_code)
    service = _service(session, principal)
    return service.effective_question_set(service.scope(store_code, product_id, sku_id))


@admin_router.post("/question-set-extensions", response_model=QuestionSetExtensionProjection, status_code=201)
def create_question_set_extension(
    payload: QuestionSetExtensionCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> QuestionSetExtensionProjection:
    ensure_store_code_access(session, principal, payload.store_code)
    return _service(session, principal).create_extension(payload)


@admin_router.get("/question-set-extensions", response_model=QuestionSetExtensionList)
def list_question_set_extensions(
    store_code: str = Query(min_length=1, max_length=96),
    product_id: str | None = Query(default=None, max_length=96),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> QuestionSetExtensionList:
    ensure_store_code_access(session, principal, store_code)
    return _service(session, principal).list_extensions(store_code, product_id)


@admin_router.post("/runs", response_model=ReplyReadinessRunProjection, status_code=201)
def create_reply_readiness_run(
    payload: ReplyReadinessRunCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyReadinessRunProjection:
    ensure_store_code_access(session, principal, payload.store_code)
    service = _service(session, principal)
    row, replayed = service.prepare_run(payload, idempotency_key.strip())
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
        return service.projection(row)
    service.mark_running(row)
    try:
        result = _ai_client(request).evaluate(service.input_for(row).model_dump(mode="json"))
        return service.record_result(row, result)
    except (ReplyReadinessAiUnavailable, ValueError, TypeError) as exc:
        service.mark_failed(row, "REPLY_READINESS_EVALUATOR_UNAVAILABLE")
        raise AppError(
            "REPLY_READINESS_EVALUATOR_UNAVAILABLE",
            "隔离回答评测器不可用，本次运行已失败且没有复用旧结果。",
            status_code=503,
        ) from exc


@admin_router.post(
    "/debug", response_model=PddReplyReadinessPublishedDebugResultV1
)
def debug_published_reply(
    payload: ReplyReadinessDebugRequest,
    request: Request,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> PddReplyReadinessPublishedDebugResultV1:
    ensure_store_code_access(session, principal, payload.store_code)
    context = StoreContextService(session).chat_context_for_explicit_scope(
        principal,
        store_code=payload.store_code,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
    )
    frozen_input = _service(session, principal).debug_input(
        scope=ReplyReadinessScopeV1(**context.model_dump()),
        customer_message=payload.customer_message,
    )
    try:
        with _debug_rate_limiter(request).acquire(
            principal.user_id, payload.store_code
        ):
            raw = _ai_client(request).evaluate(frozen_input.model_dump(mode="json"))
            return PddReplyReadinessPublishedDebugResultV1.model_validate(raw)
    except ReplyDebugRateLimitExceeded as exc:
        raise AppError(
            "REPLY_DEBUG_RATE_LIMITED",
            "单条回答调试过于频繁，请稍后重试。",
            status_code=429,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except (ReplyReadinessAiUnavailable, ValueError, TypeError) as exc:
        raise AppError(
            "REPLY_DEBUG_EVALUATOR_UNAVAILABLE",
            "正式只读回答调试服务暂时不可用，请稍后手动重试。",
            status_code=503,
        ) from exc


@admin_router.get("/runs", response_model=ReplyReadinessRunList)
def list_reply_readiness_runs(
    store_code: str = Query(min_length=1, max_length=96),
    product_id: str = Query(min_length=1, max_length=96),
    scope_kind: Literal["PRODUCT", "SKU"] | None = Query(default=None),
    sku_id: str | None = Query(default=None, max_length=128),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyReadinessRunList:
    ensure_store_code_access(session, principal, store_code)
    service = _service(session, principal)
    if scope_kind == "PRODUCT" and sku_id:
        raise AppError(
            "REPLY_READINESS_RUN_SCOPE_INVALID",
            "商品级运行筛选不能携带SKU。",
            status_code=422,
        )
    if scope_kind == "SKU" and not sku_id:
        raise AppError(
            "REPLY_READINESS_RUN_SCOPE_INVALID",
            "SKU级运行筛选必须指定SKU。",
            status_code=422,
        )
    if scope_kind is not None:
        service.scope(store_code, product_id, sku_id if scope_kind == "SKU" else None)
    return service.list_runs(store_code, product_id, scope_kind=scope_kind, sku_id=sku_id)


@admin_router.get("/runs/{run_id}", response_model=ReplyReadinessRunProjection)
def get_reply_readiness_run(
    run_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyReadinessRunProjection:
    result = _service(session, principal).get(run_id)
    ensure_store_code_access(session, principal, result.store_code)
    return result


@admin_router.get("/runs/{run_id}/compare", response_model=ReplyReadinessRunComparison)
def compare_reply_readiness_runs(
    run_id: str,
    baseline_run_id: str = Query(min_length=1, max_length=64),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyReadinessRunComparison:
    service = _service(session, principal)
    candidate = service.get(run_id)
    ensure_store_code_access(session, principal, candidate.store_code)
    return service.compare(baseline_run_id, run_id)


@internal_router.get("/runs/{run_id}/input", response_model=PddReplyReadinessInputV1)
def get_internal_run_input(run_id: str, session: Session = Depends(get_db)) -> PddReplyReadinessInputV1:
    row = session.get(ReplyReadinessRun, run_id)
    if row is None:
        raise AppError("REPLY_READINESS_RUN_NOT_FOUND", "未找到评测运行。", status_code=404)
    return ReplyReadinessService(session, "internal-ai").input_for(row)


@internal_router.post("/runs/{run_id}/result", response_model=ReplyReadinessRunProjection)
def record_internal_run_result(
    run_id: str,
    payload: PddReplyReadinessResultV1,
    session: Session = Depends(get_db),
) -> ReplyReadinessRunProjection:
    row = session.get(ReplyReadinessRun, run_id)
    if row is None:
        raise AppError("REPLY_READINESS_RUN_NOT_FOUND", "未找到评测运行。", status_code=404)
    return ReplyReadinessService(session, "internal-ai").record_result(row, payload.model_dump(mode="json"))
    ReplyReadinessDebugRequest,
