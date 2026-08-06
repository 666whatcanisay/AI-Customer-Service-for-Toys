from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import AgentEnvironment, StoreBinding


CHANNEL_AGENT_CONFIG_VERSION = "1.0"
_MAX_CONFIG_BYTES = 1_048_576


class AgentConfigError(ValueError):
    pass


class AgentConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class AgentServerConfig(AgentConfigModel):
    server_url: str = Field(min_length=1, max_length=512)
    agent_token_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("agent server_url must be absolute HTTP(S)")
        if parsed.username or parsed.password:
            raise ValueError("agent server_url cannot embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("agent server_url cannot contain query or fragment")
        return value.rstrip("/")


class AgentBrowserConfig(AgentConfigModel):
    chrome_path: Path
    profile_root: Path

    @field_validator("chrome_path", "profile_root")
    @classmethod
    def require_absolute_paths(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("browser paths must be absolute")
        return value

    @model_validator(mode="after")
    def reject_default_profile(self) -> AgentBrowserConfig:
        normalized = str(self.profile_root).replace("\\", "/").casefold().rstrip("/")
        forbidden_suffixes = (
            "/google/chrome/user data",
            "/chromium/user data",
        )
        if normalized.endswith(forbidden_suffixes):
            raise ValueError("agent cannot use the user default Chrome profile")
        return self


class AgentChannelConfig(AgentConfigModel):
    platform: Literal["pdd"] = "pdd"
    credential_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    store_binding: StoreBinding | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> AgentChannelConfig:
        if (
            self.store_binding is not None
            and self.credential_reference is not None
            and self.store_binding.credential_reference != self.credential_reference
        ):
            raise ValueError("channel credential reference must match store binding")
        return self


class AgentSafetyConfig(AgentConfigModel):
    runtime_mode: AgentEnvironment = AgentEnvironment.MOCK
    dry_run: bool = True
    kill_switch: bool = False

    @model_validator(mode="after")
    def validate_mode(self) -> AgentSafetyConfig:
        if self.runtime_mode in {
            AgentEnvironment.MOCK,
            AgentEnvironment.STAGING,
            AgentEnvironment.PILOT,
        }:
            if not self.dry_run:
                raise ValueError("MOCK and STAGING Agent modes must remain dry-run")
        return self


class ChannelAgentConfig(AgentConfigModel):
    config_version: Literal["1.0"] = CHANNEL_AGENT_CONFIG_VERSION
    node_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    node_name: str = Field(min_length=1, max_length=160)
    agent_version: str = Field(
        default="1.0.0",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
    )
    server: AgentServerConfig
    browser: AgentBrowserConfig
    channel: AgentChannelConfig
    safety: AgentSafetyConfig = AgentSafetyConfig()

    @model_validator(mode="after")
    def validate_environment(self) -> ChannelAgentConfig:
        parsed = urlsplit(self.server.server_url)
        if self.safety.runtime_mode is AgentEnvironment.MOCK:
            if parsed.hostname.casefold() not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("MOCK Agent server must use loopback")
        elif self.safety.runtime_mode is AgentEnvironment.PILOT:
            if parsed.hostname.casefold() not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("PILOT Agent server must use loopback")
        elif parsed.scheme != "https":
            raise ValueError("STAGING and PRODUCTION Agent server requires HTTPS")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


def default_channel_agent_config() -> ChannelAgentConfig:
    runtime_root = (Path.cwd() / ".runtime").resolve()
    chrome_path = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome_path.is_absolute():
        chrome_path = (runtime_root / "system-chrome-placeholder.exe").resolve()
    return ChannelAgentConfig(
        node_id="channel-agent-local-node",
        node_name="AI-CS Channel Agent Local Node",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/channel-agent/mock-token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=chrome_path,
            profile_root=(runtime_root / "channel-agent-browser-profiles").resolve(),
        ),
        channel=AgentChannelConfig(),
        safety=AgentSafetyConfig(),
    )


def load_channel_agent_config(path: str | Path) -> ChannelAgentConfig:
    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() != ".json":
        raise AgentConfigError("Channel Agent config must be one typed JSON document")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise AgentConfigError("Channel Agent config cannot be read") from exc
    if len(raw) > _MAX_CONFIG_BYTES:
        raise AgentConfigError("Channel Agent config exceeds one MiB")
    try:
        return ChannelAgentConfig.model_validate_json(raw)
    except Exception as exc:
        raise AgentConfigError("Channel Agent config validation failed") from exc


__all__ = [
    "CHANNEL_AGENT_CONFIG_VERSION",
    "AgentBrowserConfig",
    "AgentChannelConfig",
    "AgentConfigError",
    "AgentSafetyConfig",
    "AgentServerConfig",
    "ChannelAgentConfig",
    "default_channel_agent_config",
    "load_channel_agent_config",
]
