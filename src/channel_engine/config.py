from __future__ import annotations

import os
from dataclasses import dataclass, field

from channel_engine.environment import (
    EnvironmentProfile,
    EnvironmentProfileV1,
    default_mock_profile,
    load_environment_profile,
)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = "sqlite:///./.runtime/channel-engine.sqlite3"
    database_binding_path: str | None = None
    database_environment_id: str | None = None
    require_database_identity: bool = False
    service_name: str = "ai-cs-channel-execution-engine"
    environment_profile: EnvironmentProfileV1 = field(
        default_factory=default_mock_profile
    )
    real_channel_enabled: bool = False
    real_gateway_enabled: bool = False
    browser_execution_enabled: bool = False
    execution_worker_id: str = "foundation-execution-worker"
    execution_lease_seconds: int = 30
    worker_ownership_lease_seconds: int = 90
    outbox_publisher_id: str = "foundation-outbox-publisher"
    outbox_max_attempts: int = 5
    agent_operator_session_file: str | None = None
    agent_operator_principal_id: str = "ai-cs-desktop-agent-service"

    def __post_init__(self) -> None:
        if self.browser_execution_enabled:
            raise ValueError("browser execution is disabled in Environment Profile V1")
        if (
            self.environment_profile.profile
            in {EnvironmentProfile.MOCK, EnvironmentProfile.STAGING}
            and self.real_channel_enabled
        ):
            raise ValueError("mock/staging profiles cannot enable a real channel")
        if self.execution_lease_seconds < 1:
            raise ValueError("execution lease must be positive")
        if self.worker_ownership_lease_seconds <= self.execution_lease_seconds:
            raise ValueError("worker ownership lease must exceed execution lease")
        if self.outbox_max_attempts < 1:
            raise ValueError("outbox max attempts must be positive")

    @property
    def environment(self) -> str:
        return self.environment_profile.profile.value

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.getenv("CHANNEL_ENGINE_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("CHANNEL_ENGINE_DATABASE_URL is required")
        require_identity = os.getenv(
            "CHANNEL_ENGINE_REQUIRE_DATABASE_IDENTITY", "true"
        ).strip().casefold() not in {"0", "false", "no", "off"}
        binding_path = os.getenv(
            "CHANNEL_ENGINE_DATABASE_BINDING_PATH", ""
        ).strip() or None
        environment_id = os.getenv(
            "CHANNEL_ENGINE_DATABASE_ENVIRONMENT_ID", ""
        ).strip() or None
        if require_identity and (binding_path is None or environment_id is None):
            raise ValueError(
                "Channel Engine database binding path and environment ID are required"
            )
        return cls(
            database_url=database_url,
            database_binding_path=binding_path,
            database_environment_id=environment_id,
            require_database_identity=require_identity,
            execution_worker_id=os.getenv(
                "CHANNEL_ENGINE_WORKER_ID", "foundation-execution-worker"
            ),
            execution_lease_seconds=int(
                os.getenv("CHANNEL_ENGINE_EXECUTION_LEASE_SECONDS", "30")
            ),
            worker_ownership_lease_seconds=int(
                os.getenv("CHANNEL_ENGINE_WORKER_OWNERSHIP_LEASE_SECONDS", "90")
            ),
            outbox_publisher_id=os.getenv(
                "CHANNEL_ENGINE_OUTBOX_PUBLISHER_ID", "foundation-outbox-publisher"
            ),
            outbox_max_attempts=int(
                os.getenv("CHANNEL_ENGINE_OUTBOX_MAX_ATTEMPTS", "5")
            ),
            agent_operator_session_file=(
                os.getenv("CHANNEL_ENGINE_AGENT_OPERATOR_SESSION_FILE", "").strip()
                or None
            ),
            agent_operator_principal_id=os.getenv(
                "CHANNEL_ENGINE_AGENT_OPERATOR_PRINCIPAL_ID",
                "ai-cs-desktop-agent-service",
            ).strip(),
            environment_profile=load_environment_profile(os.environ),
        )
