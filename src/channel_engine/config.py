from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = "sqlite:///./.runtime/channel-engine.sqlite3"
    service_name: str = "ai-cs-channel-execution-engine"
    environment: str = "foundation"
    real_channel_enabled: bool = False
    real_gateway_enabled: bool = False
    browser_execution_enabled: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "CHANNEL_ENGINE_DATABASE_URL",
                "sqlite:///./.runtime/channel-engine.sqlite3",
            )
        )
