from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .manager import ChannelRuntimeManager, InvalidRuntimeTransition
from .models import (
    HeartbeatReport,
    RecoveryResult,
    RuntimeComponent,
    RuntimeDashboardStatus,
)


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: RuntimeComponent | None = None


def create_runtime_reliability_router(
    runtime: ChannelRuntimeManager,
) -> APIRouter:
    router = APIRouter(prefix="/runtime/v1", tags=["runtime-reliability"])

    @router.get("/status", response_model=RuntimeDashboardStatus)
    def status() -> RuntimeDashboardStatus:
        return runtime.dashboard()

    @router.post("/start", response_model=RuntimeDashboardStatus)
    def start() -> RuntimeDashboardStatus:
        try:
            runtime.start()
            return runtime.dashboard()
        except InvalidRuntimeTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/stop", response_model=RuntimeDashboardStatus)
    def stop() -> RuntimeDashboardStatus:
        try:
            runtime.stop()
            return runtime.dashboard(refresh=True)
        except InvalidRuntimeTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/heartbeat", response_model=HeartbeatReport)
    def heartbeat() -> HeartbeatReport:
        return runtime.heartbeat()

    @router.post("/recover", response_model=RecoveryResult)
    def recover(payload: RecoveryRequest) -> RecoveryResult:
        try:
            return runtime.recover(payload.component)
        except InvalidRuntimeTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router


__all__ = ["RecoveryRequest", "create_runtime_reliability_router"]
