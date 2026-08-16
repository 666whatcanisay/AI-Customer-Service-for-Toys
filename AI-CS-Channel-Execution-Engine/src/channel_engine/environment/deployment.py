from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import EnvironmentProfile, EnvironmentProfileV1


DEPLOYMENT_MANIFEST_VERSION = "1.0"


class DeploymentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ServiceDependency(DeploymentModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9-]{0,127}$",
    )
    dependency_type: Literal[
        "runtime-store", "ai-cs-gateway", "credential-provider"
    ]
    required: bool = True
    endpoint_reference: str = Field(min_length=1, max_length=256)
    health_endpoint: str | None = Field(default=None, max_length=256)


class HealthEndpoints(DeploymentModel):
    liveness: Literal["/health"] = "/health"
    aggregate_readiness: Literal["/control/v1/health"] = "/control/v1/health"
    control_status: Literal["/control/v1/status"] = "/control/v1/status"


class StagingDeploymentManifest(DeploymentModel):
    manifest_version: Literal["1.0"] = DEPLOYMENT_MANIFEST_VERSION
    name: Literal["channel-engine-staging-v1"] = "channel-engine-staging-v1"
    runtime_config_path: Literal["./runtime-config.json"] = "./runtime-config.json"
    dependencies: tuple[ServiceDependency, ...]
    health: HealthEndpoints = HealthEndpoints()
    startup_order: tuple[str, ...]
    shutdown_order: tuple[str, ...]
    production_deployment_enabled: Literal[False] = False
    real_channel_enabled: Literal[False] = False
    automatic_send_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_order(self) -> StagingDeploymentManifest:
        required = {
            "runtime-store",
            "control-plane",
            "ai-cs-gateway-health",
            "channel-engine-api",
            "execution-worker",
            "outbox-publisher",
        }
        if set(self.startup_order) != required:
            raise ValueError("startup order must contain every staging component once")
        if self.startup_order.index("runtime-store") > self.startup_order.index(
            "channel-engine-api"
        ):
            raise ValueError("runtime store must start before the API")
        if self.startup_order.index("control-plane") > self.startup_order.index(
            "execution-worker"
        ):
            raise ValueError("control plane must start before execution worker")
        if self.shutdown_order != tuple(reversed(self.startup_order)):
            raise ValueError("shutdown order must reverse startup order")
        return self


class StagingRuntimeConfigFile(DeploymentModel):
    runtime: EnvironmentProfileV1

    @model_validator(mode="after")
    def require_staging(self) -> StagingRuntimeConfigFile:
        if self.runtime.profile is not EnvironmentProfile.STAGING:
            raise ValueError("staging runtime config must use staging profile")
        return self


__all__ = [
    "DEPLOYMENT_MANIFEST_VERSION",
    "HealthEndpoints",
    "ServiceDependency",
    "StagingDeploymentManifest",
    "StagingRuntimeConfigFile",
]
