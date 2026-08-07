from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONFIG_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$")
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


class AgentConfigError(ValueError):
    """Raised when local Agent configuration is unsafe or invalid."""


class ChannelAgentConfig(BaseModel):
    """Local, credential-free configuration for one Channel Agent node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config_version: Literal["1.0"] = CONFIG_VERSION
    server_url: str = Field(min_length=1, max_length=2048)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_references: tuple[str, ...] = Field(default=(), max_length=32)
    connect_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    heartbeat_interval_seconds: float = Field(default=30.0, ge=0.05, le=300.0)
    log_directory: Path = Path("logs")

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("server_url must be a credential-free HTTP(S) origin")
        return normalized

    @field_validator("agent_id", "device_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if _IDENTIFIER.fullmatch(normalized) is None:
            raise ValueError("identifier must match the Channel Agent V1 format")
        return normalized

    @field_validator("user_reference", "store_reference")
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if _REFERENCE.fullmatch(normalized) is None:
            raise ValueError("reference must match the Channel Agent V1 format")
        return normalized

    @field_validator("store_references")
    @classmethod
    def validate_store_references(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("store references must be unique")
        if any(_REFERENCE.fullmatch(item) is None for item in normalized):
            raise ValueError("store reference must match the Channel Agent V1 format")
        return normalized

    @model_validator(mode="after")
    def validate_binding_references(self) -> "ChannelAgentConfig":
        stores = self.store_references
        if stores and self.store_reference != stores[0]:
            raise ValueError("primary store reference must be the first store reference")
        has_binding = self.user_reference is not None or self.store_reference is not None
        if has_binding and (
            self.user_reference is None or self.store_reference is None
        ):
            raise ValueError("user and store references must be present together")
        return self

    def public_view(self) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "server_url": self.server_url,
            "agent_id": self.agent_id,
            "device_id": self.device_id,
            "user_reference": self.user_reference,
            "store_reference": self.store_reference,
            "store_references": list(self.store_references),
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "log_directory": str(self.log_directory),
            "contains_credentials": False,
        }


def load_agent_config(path: str | Path) -> ChannelAgentConfig:
    source = Path(path)
    if source.suffix.casefold() != ".json":
        raise AgentConfigError("Channel Agent configuration must be JSON")
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise AgentConfigError("Channel Agent configuration cannot be read") from exc
    if len(payload) > 1024 * 1024:
        raise AgentConfigError("Channel Agent configuration exceeds one MiB")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AgentConfigError("Channel Agent configuration is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AgentConfigError("Channel Agent configuration must be one object")
    _reject_sensitive_keys(value)
    try:
        return ChannelAgentConfig.model_validate(value)
    except Exception as exc:
        raise AgentConfigError("Channel Agent configuration validation failed") from exc


def _reject_sensitive_keys(value: object, path: str = "config") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if any(part in key for part in _SENSITIVE_KEY_PARTS):
                raise AgentConfigError(f"sensitive field is forbidden at {path}")
            _reject_sensitive_keys(child, f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")


__all__ = [
    "AgentConfigError",
    "CONFIG_VERSION",
    "ChannelAgentConfig",
    "load_agent_config",
]
