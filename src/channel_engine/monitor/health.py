from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from channel_engine.config import Settings


class HealthStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    service: str
    environment: str
    real_channel_enabled: bool
    real_gateway_enabled: bool
    browser_execution_enabled: bool
    human_approval_required: bool
    unknown_auto_retry_enabled: bool


def foundation_health(settings: Settings) -> HealthStatus:
    return HealthStatus(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
        real_channel_enabled=settings.real_channel_enabled,
        real_gateway_enabled=settings.real_gateway_enabled,
        browser_execution_enabled=settings.browser_execution_enabled,
        human_approval_required=True,
        unknown_auto_retry_enabled=False,
    )
