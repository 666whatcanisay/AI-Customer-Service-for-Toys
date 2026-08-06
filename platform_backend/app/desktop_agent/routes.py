"""Authenticated Customer Desktop Workflow V1 API."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.desktop_agent.schemas import (
    DesktopAgentStatusResponse,
    DesktopBindingGrantRequest,
    DesktopBindingGrantResponse,
    DesktopWorkflowAuditListResponse,
)
from app.desktop_agent.service import DesktopAgentService, DesktopWorkflowAuditService
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
from app.iam.dependencies import Principal, require_user_manage, require_workspace_access


router = APIRouter(prefix="/api/v1/workspace/desktop-agent", tags=["customer-desktop-workflow"])
admin_router = APIRouter(prefix="/api/v1/admin/desktop-workflow", tags=["desktop-workflow-audit"])


def _upstream_error(exc: Exception) -> AppError:
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


@router.get("", response_model=DesktopAgentStatusResponse)
def desktop_agent_status(
    response: Response,
    store_id: int = Query(ge=1),
    principal: Principal = Depends(require_workspace_access),
    session: Session = Depends(get_db),
    upstream: ChannelAgentUpstream = Depends(get_channel_agent_upstream),
) -> DesktopAgentStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return DesktopAgentService(session, upstream).status(principal, store_id)
    except (
        ChannelAgentNotConfigured, ChannelAgentUnavailable,
        ChannelAgentPermissionInvalid, ChannelAgentResponseInvalid,
        ChannelAgentRequestRejected,
    ) as exc:
        raise _upstream_error(exc) from None


@router.post("/binding-grants", response_model=DesktopBindingGrantResponse, status_code=201)
def issue_desktop_binding_grant(
    request: DesktopBindingGrantRequest,
    response: Response,
    principal: Principal = Depends(require_workspace_access),
    session: Session = Depends(get_db),
    upstream: ChannelAgentUpstream = Depends(get_channel_agent_upstream),
) -> DesktopBindingGrantResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return DesktopAgentService(session, upstream).issue_grant(principal, request)
    except (
        ChannelAgentNotConfigured, ChannelAgentUnavailable,
        ChannelAgentPermissionInvalid, ChannelAgentResponseInvalid,
        ChannelAgentRequestRejected,
    ) as exc:
        raise _upstream_error(exc) from None


@admin_router.get("/audit", response_model=DesktopWorkflowAuditListResponse)
def desktop_workflow_audit(
    response: Response,
    user_id: str | None = Query(default=None, min_length=36, max_length=36),
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(require_user_manage),
    session: Session = Depends(get_db),
) -> DesktopWorkflowAuditListResponse:
    response.headers["Cache-Control"] = "no-store"
    return DesktopWorkflowAuditService(session).list(user_id=user_id, limit=limit)
