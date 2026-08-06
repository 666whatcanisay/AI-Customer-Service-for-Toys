from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from channel_engine.storage import RecordNotFound

from .actions import OperationsApprovalService
from .models import (
    ApprovalMonitorItem,
    ApprovalReviewDetail,
    ExecutionLedgerItem,
    OpsApprovalActionResult,
    OpsApprovalCommand,
    OpsConsoleSnapshot,
    OpsRuntimeStatus,
    RecoveryRecord,
    StructuredEventPage,
    StructuredEventStatus,
    StructuredEventType,
    WorkflowTrace,
)
from .service import ObservabilityService, TraceNotFound
from .ui import (
    OPERATIONS_CONSOLE_CSS,
    OPERATIONS_CONSOLE_HTML,
    OPERATIONS_CONSOLE_JS,
)


def create_observability_router(
    service: ObservabilityService,
    approval_actions: OperationsApprovalService | None = None,
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
