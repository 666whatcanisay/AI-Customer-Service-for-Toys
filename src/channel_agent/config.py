from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .observation_stages import ObservationStage


CONFIG_VERSION = "2.0"
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

    config_version: Literal["1.0", "2.0"] = CONFIG_VERSION
    control_protocol_version: Literal["2.1"] = "2.1"
    server_url: str = Field(min_length=1, max_length=2048)
    host_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    device_credential_reference: str | None = Field(
        default=None, min_length=1, max_length=512
    )
    server_ca_certificate_path: Path | None = None
    runtime_mode: Literal["MOCK", "SIMULATOR", "STAGING", "PRODUCTION"] = "MOCK"
    development_profile: Literal["STANDARD", "OFFLINE_REPLAY"] = "STANDARD"
    user_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_references: tuple[str, ...] = Field(default=(), max_length=32)
    connect_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    heartbeat_interval_seconds: float = Field(default=30.0, ge=0.05, le=300.0)
    desktop_ui_enabled: bool = True
    desktop_ui_port: int = Field(default=0, ge=0, le=65535)
    ai_cs_platform_url: str | None = None
    ai_cs_platform_proxy_mode: Literal["DIRECT_API", "SAME_ORIGIN_GATEWAY"] = "DIRECT_API"
    ai_cs_ca_certificate_path: Path | None = None
    browser_enabled: bool = False
    pdd_login_observation_enabled: bool = False
    pdd_login_url: str | None = None
    pdd_customer_service_url: str | None = None
    customer_assistant_enabled: bool = False
    message_observation_enabled: bool = False
    observation_stage: ObservationStage = ObservationStage.DISABLED
    observer_mode: Literal["OBSERVE_ONLY", "CONTROLLED_SEND"] = "OBSERVE_ONLY"
    pdd_observation_evidence_path: Path | None = None
    pdd_replay_fixture_path: Path | None = None
    pdd_replay_platform_store_id: str | None = Field(
        default=None, min_length=1, max_length=160
    )
    conversation_buffer_window_seconds: float = Field(default=4.0, ge=1.0, le=30.0)
    manual_approval_required: bool = True
    auto_reply_enabled: bool = False
    real_send_enabled: bool = False
    real_platform_activation_allowed: bool = False
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

    @field_validator("ai_cs_platform_url")
    @classmethod
    def validate_ai_cs_platform_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.scheme != "https" and not loopback)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "ai_cs_platform_url must be a credential-free HTTPS origin "
                "or a loopback HTTP origin"
            )
        return normalized

    @field_validator("agent_id", "device_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if _IDENTIFIER.fullmatch(normalized) is None:
            raise ValueError("identifier must match the Channel Agent V1 format")
        return normalized

    @field_validator("host_id")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if _IDENTIFIER.fullmatch(normalized) is None:
            raise ValueError("host identifier is invalid")
        return normalized

    @field_validator("device_credential_reference")
    @classmethod
    def validate_device_credential_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "wincred"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("device credential must be an opaque wincred reference")
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
        offline_replay = self.development_profile == "OFFLINE_REPLAY"
        stores = self.store_references
        if stores and self.store_reference != stores[0]:
            raise ValueError("primary store reference must be the first store reference")
        has_binding = self.user_reference is not None or self.store_reference is not None
        if has_binding and (
            self.user_reference is None or self.store_reference is None
        ):
            raise ValueError("user and store references must be present together")
        if offline_replay:
            if self.runtime_mode not in {"MOCK", "SIMULATOR"}:
                raise ValueError("OFFLINE_REPLAY requires MOCK or SIMULATOR runtime")
            if self.browser_enabled or self.pdd_login_observation_enabled:
                raise ValueError("OFFLINE_REPLAY forbids browser and PDD login access")
            if self.pdd_login_url is not None or self.pdd_customer_service_url is not None:
                raise ValueError("OFFLINE_REPLAY forbids live PDD URLs")
            if self.pdd_replay_fixture_path is None:
                raise ValueError("OFFLINE_REPLAY requires a sanitized replay fixture")
            if self.pdd_replay_platform_store_id is None:
                raise ValueError("OFFLINE_REPLAY requires a synthetic platform store id")
        elif self.pdd_replay_fixture_path is not None or self.pdd_replay_platform_store_id is not None:
            raise ValueError("PDD replay inputs require OFFLINE_REPLAY")
        if self.pdd_login_observation_enabled:
            if not self.browser_enabled:
                raise ValueError("PDD login observation requires browser_enabled")
            if self.pdd_login_url is None:
                raise ValueError("PDD login observation requires pdd_login_url")
            if self.pdd_customer_service_url is None:
                raise ValueError(
                    "PDD login observation requires pdd_customer_service_url"
                )
        if (
            self.customer_assistant_enabled
            and not offline_replay
            and not self.pdd_login_observation_enabled
        ):
            raise ValueError(
                "customer assistant requires PDD login observation and browser runtime"
            )
        if self.message_observation_enabled and not self.customer_assistant_enabled:
            raise ValueError(
                "message observation requires the customer assistant and PDD browser runtime"
            )
        if self.message_observation_enabled and self.observation_stage is ObservationStage.DISABLED:
            raise ValueError("message observation requires an explicit observation stage")
        if (
            self.message_observation_enabled
            and not offline_replay
            and self.pdd_observation_evidence_path is None
        ):
            raise ValueError(
                "message observation requires a verified selector evidence file"
            )
        if self.observer_mode != "OBSERVE_ONLY":
            raise ValueError(
                "ChannelAgent 2.0.0rc5 only permits OBSERVE_ONLY; controlled send "
                "requires a separate safety-gated release"
            )
        if not self.manual_approval_required:
            raise ValueError("customer assistant cannot disable manual approval")
        if self.auto_reply_enabled:
            raise ValueError("automatic reply is forbidden")
        if self.real_send_enabled:
            raise ValueError("real send requires a separate production activation grant")
        if self.real_platform_activation_allowed:
            raise ValueError("real platform activation cannot be enabled by local config")
        return self

    @field_validator("pdd_login_url")
    @classmethod
    def validate_pdd_login_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "mms.pinduoduo.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/login")
        ):
            raise ValueError(
                "pdd_login_url must be a credential-free official PDD login URL"
            )
        return normalized

    @field_validator("pdd_customer_service_url")
    @classmethod
    def validate_pdd_customer_service_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "mms.pinduoduo.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.path != "/chat-merchant/index.html"
            or parsed.fragment not in {"", "/"}
        ):
            raise ValueError(
                "pdd_customer_service_url must be the credential-free official "
                "PDD customer service URL"
            )
        return normalized

    def public_view(self) -> dict[str, object]:
        return {
            "config_version": self.config_version,
            "control_protocol_version": self.control_protocol_version,
            "server_url": self.server_url,
            "host_id": self.host_id,
            "agent_id": self.agent_id,
            "device_id": self.device_id,
            "device_credential_reference": self.device_credential_reference,
            "server_ca_certificate_configured": (
                self.server_ca_certificate_path is not None
            ),
            "runtime_mode": self.runtime_mode,
            "development_profile": self.development_profile,
            "user_reference": self.user_reference,
            "store_reference": self.store_reference,
            "store_references": list(self.store_references),
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "desktop_ui_enabled": self.desktop_ui_enabled,
            "desktop_ui_port": self.desktop_ui_port,
            "ai_cs_platform_url": self.ai_cs_platform_url,
            "ai_cs_platform_proxy_mode": self.ai_cs_platform_proxy_mode,
            "ai_cs_ca_certificate_configured": self.ai_cs_ca_certificate_path is not None,
            "browser_enabled": self.browser_enabled,
            "pdd_login_observation_enabled": self.pdd_login_observation_enabled,
            "pdd_login_url": self.pdd_login_url,
            "pdd_customer_service_url": self.pdd_customer_service_url,
            "customer_assistant_enabled": self.customer_assistant_enabled,
            "message_observation_enabled": self.message_observation_enabled,
            "observation_stage": self.observation_stage.value,
            "observer_mode": self.observer_mode,
            "pdd_observation_evidence_configured": (
                self.pdd_observation_evidence_path is not None
            ),
            "pdd_replay_fixture_configured": self.pdd_replay_fixture_path is not None,
            "pdd_replay_platform_store_id": self.pdd_replay_platform_store_id,
            "conversation_buffer_window_seconds": self.conversation_buffer_window_seconds,
            "manual_approval_required": self.manual_approval_required,
            "auto_reply_enabled": self.auto_reply_enabled,
            "real_send_enabled": self.real_send_enabled,
            "real_platform_activation_allowed": self.real_platform_activation_allowed,
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


def save_agent_config(path: str | Path, config: ChannelAgentConfig) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8") + b"\n"
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise AgentConfigError("Channel Agent configuration cannot be saved") from exc


def migrate_agent_config(path: str | Path) -> ChannelAgentConfig:
    """Upgrade V1 in place without moving identity or secret material."""

    target = Path(path)
    config = load_agent_config(target)
    if config.config_version == CONFIG_VERSION:
        return config
    migrated = config.model_copy(
        update={
            "config_version": CONFIG_VERSION,
            "runtime_mode": (
                "MOCK"
                if urlsplit(config.server_url).hostname
                in {"127.0.0.1", "localhost", "::1"}
                else "STAGING"
            ),
        }
    )
    migrated = ChannelAgentConfig.model_validate(migrated.model_dump())
    save_agent_config(target, migrated)
    return migrated


def _reject_sensitive_keys(value: object, path: str = "config") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            safe_reference = key.endswith("_credential_reference")
            if any(part in key for part in _SENSITIVE_KEY_PARTS) and not safe_reference:
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
    "migrate_agent_config",
    "save_agent_config",
]
