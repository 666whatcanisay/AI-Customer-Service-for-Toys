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
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "CHANNEL_ENGINE_DATABASE_URL",
                "sqlite:///./.runtime/channel-engine.sqlite3",
            ),
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
            environment_profile=load_environment_profile(os.environ),
        )
