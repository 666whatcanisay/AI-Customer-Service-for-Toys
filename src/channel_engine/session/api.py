from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .heartbeat import SessionHeartbeatScheduler
from .manager import ChannelInstanceManager
from .models import ChannelInstanceView, SessionHeartbeatReport
from .persistence import SessionRecordNotFound


def create_channel_session_router(
    manager: ChannelInstanceManager,
    scheduler: SessionHeartbeatScheduler,
) -> APIRouter:
    router = APIRouter(prefix="/session-runtime/v1", tags=["channel-session-runtime"])

    @router.get("/instances", response_model=list[ChannelInstanceView])
    def list_instances() -> list[ChannelInstanceView]:
        return list(manager.list_views())

    @router.get("/instances/{instance_id}", response_model=ChannelInstanceView)
    def get_instance(instance_id: str) -> ChannelInstanceView:
        try:
            return manager.view(instance_id)
        except SessionRecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/heartbeat", response_model=SessionHeartbeatReport)
    def heartbeat() -> SessionHeartbeatReport:
        return scheduler.run_once()

    return router


__all__ = ["create_channel_session_router"]
