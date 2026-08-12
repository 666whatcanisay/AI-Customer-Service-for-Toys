"""Authenticated Store context and facade over the unchanged loopback A chat."""

import httpx
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.desktop_agent.schemas import UpstreamExecutionPreparation, UpstreamReplyPolicy
from app.desktop_agent.upstream import (
    ChannelAgentNotConfigured,
    ChannelAgentPermissionInvalid,
    ChannelAgentRequestRejected,
    ChannelAgentResponseInvalid,
    ChannelAgentUnavailable,
    ChannelAgentUpstream,
    get_channel_agent_upstream,
)
from app.errors import AppError
from app.iam.dependencies import (
    Principal, ensure_store_access, require_ai_reply, require_user_manage,
    require_workspace_access, require_customer_service_manage,
)
from app.test_catalog.models import TestProduct, TestSku, TestStore
from app.workspace.schemas import (
    ContextResolutionRequest, ContextResolutionResponse, ResolutionAuditListResponse,
    ResolutionStatus, WorkspaceChatRequest, WorkspaceContextResponse,
    ExecutionPreparationRequest, ReplyPolicyChangeRequest,
)
from app.workspace.service import StoreContextService


router = APIRouter(prefix="/api/v1/workspace", tags=["authenticated-workspace"])
admin_router = APIRouter(
    prefix="/api/v1/admin/store-context", tags=["store-context-audit"]
)


def _validate_scope(session: Session, principal: Principal, context) -> None:
    stores = list(session.scalars(select(TestStore).where(
        TestStore.tenant_id == context.tenant_id,
        TestStore.platform == context.platform,
        TestStore.store_code == context.store_code,
    )))
    permitted = [store for store in stores if principal.all_store_access or store.id in principal.store_ids]
    if len(permitted) != 1:
        raise AppError("AUTHORIZATION_DENIED", "The requested Store is not bound to this account.", status_code=403)
    store = permitted[0]
    ensure_store_access(principal, store.id)
    product = session.get(TestProduct, context.product_id)
    if product is None or product.package_id != store.package_id or product.store_code != store.store_code:
        raise AppError("AUTHORIZATION_DENIED", "The requested Product is outside the bound Store.", status_code=403)
    if context.sku_id is not None:
        sku = session.get(TestSku, context.sku_id)
        if sku is None or sku.package_id != product.package_id or sku.product_id != product.product_id:
            raise AppError("AUTHORIZATION_DENIED", "The requested SKU is outside the bound Store.", status_code=403)


def _authorized_store_code(
    session: Session, principal: Principal, store_id: int
) -> str:
    context = StoreContextService(session).workspace_context(principal)
    store = next((item for item in context.stores if item.store_id == store_id), None)
    if store is None:
        raise AppError(
            "AUTHORIZATION_DENIED",
            "The requested Store is outside the authenticated Workspace scope.",
            status_code=403,
        )
    return store.store_code


def _channel_agent_error(exc: Exception) -> AppError:
    if isinstance(exc, ChannelAgentNotConfigured):
        return AppError(
            "CHANNEL_AGENT_INTEGRATION_NOT_CONFIGURED",
            "Channel Agent integration is not configured.",
            status_code=503,
        )
    if isinstance(exc, ChannelAgentUnavailable):
        return AppError(
            "CHANNEL_AGENT_SERVER_UNREACHABLE",
            "Channel Agent server is unreachable.",
            status_code=503,
        )
    if isinstance(exc, ChannelAgentPermissionInvalid):
        return AppError(
            "CHANNEL_AGENT_OPERATOR_PERMISSION_INVALID",
            "Channel Agent integration permission is invalid.",
            status_code=503,
        )
    if isinstance(exc, ChannelAgentResponseInvalid):
        return AppError(
            "CHANNEL_AGENT_RESPONSE_INVALID",
            "Channel Agent returned an incompatible response.",
            status_code=502,
        )
    return AppError(
        "CHANNEL_AGENT_REQUEST_REJECTED",
        "Channel Agent rejected the integration request.",
        status_code=502,
    )


def _proxy(
    request: Request, method: str, path: str, payload: dict | None = None
) -> JSONResponse:
    settings = request.app.state.settings
    try:
        service_token = settings.internal_service_token()
        response = httpx.request(
            method, f"{settings.ai_service_base_url}{path}", json=payload,
            headers={
                "X-Request-ID": request.state.request_id,
                "X-AI-CS-Service-Token": service_token,
            },
            timeout=settings.ai_service_timeout_seconds,
        )
        content = response.json()
    except (httpx.HTTPError, ValueError):
        raise AppError("AI_SERVICE_UNAVAILABLE", "AI service is unavailable.", status_code=503) from None
    if response.status_code >= 500:
        raise AppError(
            "AI_SERVICE_UNAVAILABLE", "AI service is unavailable.", status_code=503
        )
    if response.status_code >= 400:
        raise AppError(
            "AI_SERVICE_REQUEST_REJECTED",
            "AI service rejected the request.",
            status_code=502,
        )
    if path == "/api/chat":
        warnings = content.get("warnings") or (content.get("data") or {}).get("warnings") or []
        if {"RAG_RUNTIME_ERROR", "LLM_REQUEST_FAILED"}.intersection(warnings):
            raise AppError(
                "AI_SERVICE_UNAVAILABLE",
                "AI reply generation failed.",
                status_code=503,
            )
    return JSONResponse(status_code=response.status_code, content=content)


@router.get("/context", response_model=WorkspaceContextResponse)
def workspace_context(
    principal: Principal = Depends(require_workspace_access),
    session: Session = Depends(get_db),
) -> WorkspaceContextResponse:
    return StoreContextService(session).workspace_context(principal)


@router.post("/context-resolutions", response_model=ContextResolutionResponse, status_code=201)
def resolve_context(
    request: ContextResolutionRequest,
    principal: Principal = Depends(require_ai_reply),
    session: Session = Depends(get_db),
) -> ContextResolutionResponse:
    return StoreContextService(session).resolve(principal, request)


@router.get("/ai-health")
def ai_health(
    request: Request, _: Principal = Depends(require_ai_reply)
) -> JSONResponse:
    return _proxy(request, "GET", "/api/health")


@router.get("/reply-policy", response_model=UpstreamReplyPolicy)
def reply_policy(
    store_id: int = Query(ge=1),
    principal: Principal = Depends(require_workspace_access),
    session: Session = Depends(get_db),
    upstream: ChannelAgentUpstream = Depends(get_channel_agent_upstream),
) -> UpstreamReplyPolicy:
    store_code = _authorized_store_code(session, principal, store_id)
    try:
        return upstream.get_reply_policy(store_id=store_code)
    except (
        ChannelAgentNotConfigured,
        ChannelAgentUnavailable,
        ChannelAgentPermissionInvalid,
        ChannelAgentResponseInvalid,
        ChannelAgentRequestRejected,
    ) as exc:
        raise _channel_agent_error(exc) from None


@router.put("/reply-policy", response_model=UpstreamReplyPolicy)
def change_reply_policy(
    payload: ReplyPolicyChangeRequest,
    principal: Principal = Depends(require_customer_service_manage),
    session: Session = Depends(get_db),
    upstream: ChannelAgentUpstream = Depends(get_channel_agent_upstream),
) -> UpstreamReplyPolicy:
    store_code = _authorized_store_code(session, principal, payload.store_id)
    try:
        return upstream.set_reply_policy(
            store_id=store_code,
            mode=payload.mode.value,
            expected_revision=payload.expected_revision,
            actor_reference=principal.user_id,
        )
    except (
        ChannelAgentNotConfigured,
        ChannelAgentUnavailable,
        ChannelAgentPermissionInvalid,
        ChannelAgentResponseInvalid,
        ChannelAgentRequestRejected,
    ) as exc:
        raise _channel_agent_error(exc) from None


@router.post(
    "/decisions/{decision_id}/execution-preparations",
    response_model=UpstreamExecutionPreparation,
    status_code=201,
)
def prepare_execution(
    payload: ExecutionPreparationRequest,
    decision_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_ai_reply),
    session: Session = Depends(get_db),
    upstream: ChannelAgentUpstream = Depends(get_channel_agent_upstream),
) -> UpstreamExecutionPreparation:
    store_code = _authorized_store_code(session, principal, payload.store_id)
    try:
        return upstream.prepare_execution(
            decision_id=decision_id,
            store_id=store_code,
            conversation_id=payload.conversation_id,
            customer_reference=payload.customer_reference,
            actor_reference=principal.user_id,
        )
    except (
        ChannelAgentNotConfigured,
        ChannelAgentUnavailable,
        ChannelAgentPermissionInvalid,
        ChannelAgentResponseInvalid,
        ChannelAgentRequestRejected,
    ) as exc:
        raise _channel_agent_error(exc) from None


@router.post("/ai-replies")
def ai_reply(
    payload: WorkspaceChatRequest,
    request: Request,
    principal: Principal = Depends(require_ai_reply),
    session: Session = Depends(get_db),
) -> JSONResponse:
    if payload.resolution_id is not None:
        context = StoreContextService(session).chat_context_for_resolution(
            principal, payload.resolution_id
        )
    else:
        assert payload.context is not None
        context = payload.context
        _validate_scope(session, principal, context)
    return _proxy(request, "POST", "/api/chat", {
        "question": payload.question,
        "context": context.model_dump(),
    })


@admin_router.get("/resolutions", response_model=ResolutionAuditListResponse)
def list_context_resolutions(
    user_id: str | None = Query(default=None, max_length=36),
    status: ResolutionStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(require_user_manage),
    session: Session = Depends(get_db),
) -> ResolutionAuditListResponse:
    return StoreContextService(session).list_audits(
        user_id=user_id, status=status, limit=limit
    )
