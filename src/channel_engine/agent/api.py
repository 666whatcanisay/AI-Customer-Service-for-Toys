from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from .dashboard import ChannelAgentDashboard, ChannelAgentDashboardProjector
from .dashboard_ui import CHANNEL_AGENT_DASHBOARD_HTML
from .first_launch import (
    ChannelAgentFirstLaunchService,
    EnvironmentDoctorReport,
    FirstLaunchState,
    FirstLaunchStatusView,
    FirstLaunchTransitionError,
    build_default_first_launch_service,
)
from .first_launch_ui import CHANNEL_AGENT_FIRST_LAUNCH_HTML
from .models import AgentHealth, AgentStatusView, StoreBinding
from .runtime import AgentLifecycleError, AgentStoreBindingError, ChannelAgentService


def create_agent_router(
    service: ChannelAgentService,
    first_launch: ChannelAgentFirstLaunchService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/agent", tags=["channel-agent"])
    dashboard = ChannelAgentDashboardProjector(service)
    launch = first_launch or build_default_first_launch_service(service)

    def first_launch_action(action) -> FirstLaunchStatusView:  # type: ignore[no-untyped-def]
        try:
            return action()
        except FirstLaunchTransitionError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FIRST_LAUNCH_ACTION_UNAVAILABLE",
                    "message": "当前步骤不能执行此操作。",
                },
            ) from exc

    @router.get("", include_in_schema=False)
    def agent_home() -> RedirectResponse:
        destination = (
            "/agent/ui"
            if launch.status().state is FirstLaunchState.READY
            else "/agent/first-launch/ui"
        )
        return RedirectResponse(destination, status_code=307)

    @router.get("/status", response_model=AgentStatusView)
    def agent_status() -> AgentStatusView:
        return service.status()

    @router.get("/health", response_model=AgentHealth)
    def agent_health() -> AgentHealth:
        return service.health()

    @router.get("/dashboard", response_model=ChannelAgentDashboard)
    def agent_dashboard() -> ChannelAgentDashboard:
        return dashboard.snapshot()

    @router.get("/first-launch/status", response_model=FirstLaunchStatusView)
    def first_launch_status() -> FirstLaunchStatusView:
        return launch.status()

    @router.get("/first-launch/doctor", response_model=EnvironmentDoctorReport)
    def first_launch_doctor() -> EnvironmentDoctorReport:
        return launch.doctor()

    @router.post("/first-launch/start", response_model=FirstLaunchStatusView)
    def first_launch_start() -> FirstLaunchStatusView:
        return first_launch_action(launch.start)

    @router.post(
        "/first-launch/browser/reopen",
        response_model=FirstLaunchStatusView,
    )
    def first_launch_reopen_browser() -> FirstLaunchStatusView:
        return first_launch_action(launch.reopen_browser)

    @router.post(
        "/first-launch/login/check",
        response_model=FirstLaunchStatusView,
    )
    def first_launch_check_login() -> FirstLaunchStatusView:
        return first_launch_action(launch.check_login)

    @router.post("/first-launch/reset", response_model=FirstLaunchStatusView)
    def first_launch_reset() -> FirstLaunchStatusView:
        return first_launch_action(launch.reset)

    @router.post("/start", response_model=AgentStatusView)
    def agent_start() -> AgentStatusView:
        try:
            return service.start()
        except AgentLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/stop", response_model=AgentStatusView)
    def agent_stop() -> AgentStatusView:
        try:
            return service.stop()
        except AgentLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/check", response_model=AgentStatusView)
    def agent_check() -> AgentStatusView:
        try:
            return service.check()
        except AgentLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.put("/store", response_model=AgentStatusView)
    def bind_store(binding: StoreBinding) -> AgentStatusView:
        try:
            return service.bind_store(binding)
        except AgentStoreBindingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/store", status_code=status.HTTP_204_NO_CONTENT)
    def unbind_store() -> Response:
        try:
            service.unbind_store()
        except AgentStoreBindingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/ui", response_class=HTMLResponse)
    def agent_ui() -> HTMLResponse:
        return HTMLResponse(
            CHANNEL_AGENT_DASHBOARD_HTML,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/first-launch/ui", response_class=HTMLResponse)
    def first_launch_ui() -> HTMLResponse:
        return HTMLResponse(
            CHANNEL_AGENT_FIRST_LAUNCH_HTML,
            headers={"Cache-Control": "no-store"},
        )

    return router


__all__ = ["create_agent_router"]
