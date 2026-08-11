from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import HTMLResponse, PlainTextResponse

from channel_agent.identity import AgentIdentity
from channel_engine.agent.node_api import (
    AgentIdentityTransitionError,
    ChannelAgentNodeRegistry,
)
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole
from channel_engine.storage import RecordNotFound

from .actions import OperationsApprovalService
from .models import (
    ApprovalMonitorItem,
    ApprovalReviewDetail,
    ExecutionLedgerItem,
    OpsApprovalActionResult,
    OpsApprovalCommand,
    OpsAgentAdminCommand,
    OpsConsoleSnapshot,
    OpsRuntimeStatus,
    RecoveryRecord,
    StructuredEventPage,
    StructuredEventStatus,
    StructuredEventType,
    WorkflowTrace,
)
from .service import ObservabilityService, TraceNotFound
from .device_admin_client import (
    DeviceAdminClientError,
    DeviceAdminClientPort,
    OperationsBindingTargetList,
    OperationsAdminSessionBroker,
    OperationsDeviceList,
    OperationsDeviceView,
    OperationsEnrollmentGrant,
    OperationsHostPairingCode,
)
from .ui import (
    OPERATIONS_CONSOLE_CSS,
    OPERATIONS_CONSOLE_HTML,
    OPERATIONS_CONSOLE_JS,
)


class OperationsAdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512, repr=False)


class OperationsEnrollmentGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=36, max_length=36)
    store_ids: tuple[int, ...] = Field(min_length=1)
    reason: str = Field(min_length=8, max_length=512)
    confirmation_text: str = Field(min_length=1, max_length=64)


class OperationsHostPairingCodeRotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=8, max_length=512)
    confirmation_text: str = Field(min_length=1, max_length=64)


class OperationsAdminSessionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: bool
    status: str
    username: str | None = None
    display_name: str | None = None
    reason: str | None = None


def create_observability_router(
    service: ObservabilityService,
    approval_actions: OperationsApprovalService | None = None,
    agent_registry: ChannelAgentNodeRegistry | None = None,
    device_admin_client: DeviceAdminClientPort | None = None,
    admin_sessions: OperationsAdminSessionBroker | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ops", tags=["observability"])

    @router.get("/runtime/status", response_model=OpsRuntimeStatus)
    def runtime_status() -> OpsRuntimeStatus:
        return service.runtime_status()

    @router.get("/events", response_model=StructuredEventPage)
    def events(
        trace_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        event_type: StructuredEventType | None = None,
        status: StructuredEventStatus | None = None,
        store_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        since: datetime | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        newest_first: bool = True,
    ) -> StructuredEventPage:
        return service.events(
            trace_id=trace_id,
            event_type=event_type,
            status=status,
            store_id=store_id,
            since=since,
            limit=limit,
            newest_first=newest_first,
        )

    @router.get("/traces/{identifier}", response_model=WorkflowTrace)
    def trace(
        identifier: Annotated[str, Path(min_length=1, max_length=160)],
    ) -> WorkflowTrace:
        try:
            return service.trace(identifier)
        except TraceNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/executions", response_model=list[ExecutionLedgerItem])
    def executions(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> tuple[ExecutionLedgerItem, ...]:
        return service.executions(limit=limit)

    @router.get("/approvals", response_model=list[ApprovalMonitorItem])
    def approvals(
        waiting_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> tuple[ApprovalMonitorItem, ...]:
        return service.approvals(waiting_only=waiting_only, limit=limit)

    @router.get(
        "/approvals/{decision_id}/review",
        response_model=ApprovalReviewDetail,
    )
    def approval_review(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
    ) -> ApprovalReviewDetail:
        try:
            return service.approval_review(decision_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/approvals/{decision_id}/approve",
        response_model=OpsApprovalActionResult,
    )
    def approve(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
        command: OpsApprovalCommand,
    ) -> OpsApprovalActionResult:
        if approval_actions is None:
            raise HTTPException(
                status_code=503,
                detail="OPERATIONS_APPROVAL_ACTIONS_UNAVAILABLE",
            )
        try:
            return approval_actions.approve(decision_id, command)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/approvals/{decision_id}/reject",
        response_model=OpsApprovalActionResult,
    )
    def reject(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
        command: OpsApprovalCommand,
    ) -> OpsApprovalActionResult:
        if approval_actions is None:
            raise HTTPException(
                status_code=503,
                detail="OPERATIONS_APPROVAL_ACTIONS_UNAVAILABLE",
            )
        try:
            return approval_actions.reject(decision_id, command)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/recoveries", response_model=list[RecoveryRecord])
    def recoveries(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> tuple[RecoveryRecord, ...]:
        return service.recoveries(limit=limit)

    def require_loopback(request: Request) -> None:
        client_host = request.client.host if request.client is not None else ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=403, detail="OPS_LOCALHOST_REQUIRED")

    def require_device_action(
        request: Request,
        intent: str | None,
        expected_intent: str,
    ) -> None:
        require_loopback(request)
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if request.headers.get("origin") != expected_origin:
            raise HTTPException(status_code=403, detail="OPS_SAME_ORIGIN_REQUIRED")
        if intent != expected_intent:
            raise HTTPException(status_code=403, detail="OPS_HUMAN_INTENT_REQUIRED")

    def local_device_admin() -> OperatorPrincipal:
        return OperatorPrincipal(
            principal_id="ops-console-local-admin",
            roles=frozenset({OperatorRole.ADMIN}),
            identity_provider="local-operations-console",
        )

    def resolve_admin_token(session_id: str | None) -> str:
        if admin_sessions is None:
            raise HTTPException(status_code=503, detail="OPS_ADMIN_SESSION_UNAVAILABLE")
        try:
            return admin_sessions.resolve(session_id).access_token
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    def map_local_devices() -> OperationsDeviceList:
        if agent_registry is None:
            raise HTTPException(status_code=503, detail="AGENT_REGISTRY_UNAVAILABLE")
        listing = agent_registry.list_agents(local_device_admin())
        return OperationsDeviceList(
            items=tuple(
                OperationsDeviceView(
                    agent_id=item.identity.agent_id,
                    device_id=item.identity.device_id,
                    agent_version=item.agent_version,
                    hostname=item.hostname,
                    identity_status=item.identity_status,
                    connectivity_status=item.connectivity_status,
                    runtime_status=item.runtime_status,
                    user_reference=item.identity.user_id,
                    authorized_store_ids=item.identity.authorized_stores,
                    active_store_id=item.identity.effective_active_store_id,
                    binding_revision=item.identity.binding_revision,
                    last_heartbeat=item.last_heartbeat,
                    authoritative_source=item.authoritative_source,
                )
                for item in listing.items
            ),
            count=listing.count,
            checked_at=listing.server_time,
            authoritative_source=listing.authoritative_source,
        )

    @router.get("/admin/session", response_model=OperationsAdminSessionStatus)
    def admin_session_status(
        request: Request,
        response: Response,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsAdminSessionStatus:
        """Report admin authentication without exposing the upstream token."""

        require_loopback(request)
        if admin_sessions is None:
            return OperationsAdminSessionStatus(
                authenticated=False,
                status="UNAVAILABLE",
                reason="OPS_ADMIN_SESSION_UNAVAILABLE",
            )
        try:
            session = admin_sessions.resolve(session_id)
        except DeviceAdminClientError as exc:
            if session_id and exc.code in {
                "OPS_ADMIN_SESSION_INVALID",
                "OPS_ADMIN_SESSION_EXPIRED",
            }:
                response.delete_cookie(admin_sessions.cookie_name, path="/ops")
            return OperationsAdminSessionStatus(
                authenticated=False,
                status="SIGNED_OUT",
                reason=exc.code,
            )
        return OperationsAdminSessionStatus(
            authenticated=True,
            status="AUTHENTICATED",
            username=session.username,
            display_name=session.display_name,
        )

    @router.post("/admin/session/login")
    def admin_login(
        payload: OperationsAdminLoginRequest,
        request: Request,
        response: Response,
    ) -> dict[str, str]:
        require_loopback(request)
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if request.headers.get("origin") != expected_origin:
            raise HTTPException(status_code=403, detail="OPS_SAME_ORIGIN_REQUIRED")
        if admin_sessions is None:
            raise HTTPException(status_code=503, detail="OPS_ADMIN_SESSION_UNAVAILABLE")
        try:
            session_id, session = admin_sessions.login(payload.username, payload.password)
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        response.set_cookie(
            admin_sessions.cookie_name,
            session_id,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/ops",
        )
        return {"status": "AUTHENTICATED", "display_name": session.display_name}

    @router.delete("/admin/session")
    def admin_logout(
        request: Request,
        response: Response,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> dict[str, str]:
        require_loopback(request)
        if admin_sessions is not None:
            admin_sessions.logout(session_id)
            response.delete_cookie(admin_sessions.cookie_name, path="/ops")
        return {"status": "SIGNED_OUT"}

    @router.get("/devices", response_model=OperationsDeviceList)
    def devices(
        request: Request,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsDeviceList:
        require_loopback(request)
        if device_admin_client is None:
            return map_local_devices()
        try:
            return device_admin_client.list_devices(resolve_admin_token(session_id))
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @router.get("/devices/binding-targets", response_model=OperationsBindingTargetList)
    def binding_targets(
        request: Request,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsBindingTargetList:
        require_loopback(request)
        if device_admin_client is None:
            raise HTTPException(
                status_code=503,
                detail="AUTHORITATIVE_DEVICE_ADMIN_REQUIRED",
            )
        try:
            return device_admin_client.list_binding_targets(
                resolve_admin_token(session_id)
            )
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @router.post(
        "/devices/host-pairing-code/rotate",
        response_model=OperationsHostPairingCode,
        status_code=201,
    )
    def rotate_host_pairing_code(
        command: OperationsHostPairingCodeRotateRequest,
        request: Request,
        response: Response,
        intent: Annotated[str | None, Header(alias="X-Operator-Intent")] = None,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsHostPairingCode:
        require_device_action(
            request,
            intent,
            "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION",
        )
        if command.confirmation_text != "确认重新生成主机连接码":
            raise HTTPException(
                status_code=409,
                detail="HOST_PAIRING_CODE_ROTATION_CONFIRMATION_INVALID",
            )
        if device_admin_client is None:
            raise HTTPException(
                status_code=503,
                detail="AUTHORITATIVE_DEVICE_ADMIN_REQUIRED",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        try:
            return device_admin_client.rotate_host_pairing_code(
                resolve_admin_token(session_id), command.reason
            )
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @router.post(
        "/devices/{agent_id}/enrollment-grants",
        response_model=OperationsEnrollmentGrant,
        status_code=201,
    )
    def issue_enrollment_grant(
        agent_id: Annotated[str, Path(min_length=1, max_length=128)],
        command: OperationsEnrollmentGrantRequest,
        request: Request,
        response: Response,
        intent: Annotated[str | None, Header(alias="X-Operator-Intent")] = None,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsEnrollmentGrant:
        require_device_action(
            request,
            intent,
            "HUMAN_CONFIRMED_ENROLLMENT_GRANT",
        )
        if command.confirmation_text != "确认生成设备绑定许可":
            raise HTTPException(
                status_code=409,
                detail="ENROLLMENT_GRANT_CONFIRMATION_INVALID",
            )
        if device_admin_client is None:
            raise HTTPException(
                status_code=503,
                detail="AUTHORITATIVE_DEVICE_ADMIN_REQUIRED",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        try:
            return device_admin_client.issue_enrollment_grant(
                resolve_admin_token(session_id),
                agent_id,
                user_id=command.user_id,
                store_ids=command.store_ids,
                reason=command.reason,
            )
        except DeviceAdminClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @router.post("/devices/{agent_id}/unbind", response_model=AgentIdentity)
    def unbind_device(
        agent_id: Annotated[str, Path(min_length=1, max_length=128)],
        command: OpsAgentAdminCommand,
        request: Request,
        intent: Annotated[str | None, Header(alias="X-Operator-Intent")] = None,
    ) -> AgentIdentity:
        require_device_action(request, intent, "HUMAN_CONFIRMED_AGENT_UNBIND")
        if command.confirmation_text != "确认解绑设备":
            raise HTTPException(status_code=409, detail="AGENT_UNBIND_CONFIRMATION_INVALID")
        if agent_registry is None:
            raise HTTPException(status_code=503, detail="AGENT_REGISTRY_UNAVAILABLE")
        try:
            return agent_registry.release_identity(
                agent_id,
                command.reason,
                local_device_admin(),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="AGENT_NOT_REGISTERED") from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="AGENT_UNBIND_DENIED") from exc

    @router.post("/devices/{agent_id}/disable", response_model=OperationsDeviceList)
    def disable_device(
        agent_id: Annotated[str, Path(min_length=1, max_length=128)],
        command: OpsAgentAdminCommand,
        request: Request,
        intent: Annotated[str | None, Header(alias="X-Operator-Intent")] = None,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsDeviceList:
        require_device_action(request, intent, "HUMAN_CONFIRMED_AGENT_DISABLE")
        if command.confirmation_text != "确认禁用设备":
            raise HTTPException(status_code=409, detail="AGENT_DISABLE_CONFIRMATION_INVALID")
        if device_admin_client is not None:
            try:
                return device_admin_client.disable(
                    resolve_admin_token(session_id), agent_id, command.reason
                )
            except DeviceAdminClientError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        if agent_registry is None:
            raise HTTPException(status_code=503, detail="AGENT_REGISTRY_UNAVAILABLE")
        try:
            agent_registry.disable_identity(
                agent_id,
                command.reason,
                local_device_admin(),
            )
            return map_local_devices()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="AGENT_NOT_REGISTERED") from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="AGENT_DISABLE_DENIED") from exc

    @router.post(
        "/devices/{agent_id}/restore-to-registered",
        response_model=OperationsDeviceList,
    )
    def restore_device(
        agent_id: Annotated[str, Path(min_length=1, max_length=128)],
        command: OpsAgentAdminCommand,
        request: Request,
        intent: Annotated[str | None, Header(alias="X-Operator-Intent")] = None,
        session_id: Annotated[
            str | None, Cookie(alias="channel_ops_admin_session")
        ] = None,
    ) -> OperationsDeviceList:
        require_device_action(
            request, intent, "HUMAN_CONFIRMED_AGENT_RESTORE"
        )
        if command.confirmation_text != "确认恢复为待绑定":
            raise HTTPException(
                status_code=409,
                detail="AGENT_RESTORE_CONFIRMATION_INVALID",
            )
        if device_admin_client is not None:
            try:
                return device_admin_client.restore_to_registered(
                    resolve_admin_token(session_id), agent_id, command.reason
                )
            except DeviceAdminClientError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        if agent_registry is None:
            raise HTTPException(status_code=503, detail="AGENT_REGISTRY_UNAVAILABLE")
        try:
            from channel_agent.identity import AgentIdentityRestoreRequest

            agent_registry.restore_identity_to_registered(
                agent_id,
                AgentIdentityRestoreRequest(
                    reason=command.reason,
                    confirmation_phrase="确认恢复为待绑定",
                ),
                local_device_admin(),
            )
            return map_local_devices()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="AGENT_NOT_REGISTERED") from exc
        except (AgentIdentityTransitionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="AGENT_RESTORE_DENIED") from exc

    @router.get("/console/snapshot", response_model=OpsConsoleSnapshot)
    def snapshot() -> OpsConsoleSnapshot:
        return service.snapshot()

    @router.get("/assets/operations-console.css", include_in_schema=False)
    def console_css() -> PlainTextResponse:
        return PlainTextResponse(
            OPERATIONS_CONSOLE_CSS,
            media_type="text/css; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @router.get("/assets/operations-console.js", include_in_schema=False)
    def console_js() -> PlainTextResponse:
        return PlainTextResponse(
            OPERATIONS_CONSOLE_JS,
            media_type="text/javascript; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @router.get("/console", response_class=HTMLResponse, include_in_schema=False)
    def console() -> HTMLResponse:
        return HTMLResponse(
            OPERATIONS_CONSOLE_HTML,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            },
        )

    return router


__all__ = ["create_observability_router"]
