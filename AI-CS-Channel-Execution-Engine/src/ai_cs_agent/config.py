from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


CONFIG_VERSION = "1.0"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE_KEYS = ("password", "secret", "token", "cookie", "authorization")


class ConfigError(ValueError):
    pass


def _required_text(value: object, name: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} is required")
    normalized = value.strip()
    if len(normalized) > maximum or "\r" in normalized or "\n" in normalized:
        raise ConfigError(f"{name} is invalid")
    return normalized


def _identifier(value: object, name: str) -> str:
    normalized = _required_text(value, name, 128)
    if _ID.fullmatch(normalized) is None:
        raise ConfigError(f"{name} is not a Contract V1 identifier")
    return normalized


def _reject_sensitive_keys(value: object, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(marker in lowered for marker in _SENSITIVE_KEYS):
                if not lowered.endswith(("_reference", "_ref")):
                    raise ConfigError(f"plaintext credential field is forbidden at {path}")
            _reject_sensitive_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_keys(item, f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class ServerConfig:
    address: str
    client_id: str
    key_id: str
    credential_reference: str
    timeout_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    chrome_path: str | None
    profile_directory: str


@dataclass(frozen=True, slots=True)
class SafetyConfig:
    kill_switch: bool = True
    manual_approval: bool = True
    auto_reply: bool = False


@dataclass(frozen=True, slots=True)
class AgentConfig:
    schema_version: str
    agent_id: str
    device_id: str
    customer_service_identity: str
    runtime_mode: str
    server: ServerConfig
    browser: BrowserConfig
    safety: SafetyConfig


def load_config(path: str | Path) -> AgentConfig:
    source_path = Path(path)
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError("agent configuration cannot be read") from exc
    if not isinstance(raw, dict):
        raise ConfigError("agent configuration must be an object")
    _reject_sensitive_keys(raw)
    allowed_root = {"schema_version", "agent", "server", "browser", "safety"}
    if set(raw) - allowed_root:
        raise ConfigError("agent configuration contains unknown root fields")
    if raw.get("schema_version") != CONFIG_VERSION:
        raise ConfigError("unsupported agent configuration version")

    agent = _mapping(raw.get("agent"), "agent")
    server = _mapping(raw.get("server"), "server")
    browser = _mapping(raw.get("browser"), "browser")
    safety = _mapping(raw.get("safety"), "safety")
    _exact_fields(
        agent,
        {"agent_id", "device_id", "customer_service_identity", "runtime_mode"},
        "agent",
    )
    _exact_fields(
        server,
        {"address", "client_id", "key_id", "credential_reference", "timeout_seconds"},
        "server",
    )
    _exact_fields(browser, {"chrome_path", "profile_directory"}, "browser")
    _exact_fields(safety, {"kill_switch", "manual_approval", "auto_reply"}, "safety")

    runtime_mode = _required_text(agent.get("runtime_mode"), "runtime_mode", 32).upper()
    if runtime_mode not in {"STAGING", "PILOT"}:
        raise ConfigError("RC runtime_mode must be STAGING or PILOT")
    address = _validate_server_address(server.get("address"), runtime_mode)
    credential_reference = _validate_credential_reference(
        server.get("credential_reference")
    )
    timeout = server.get("timeout_seconds", 5.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ConfigError("server.timeout_seconds must be numeric")
    timeout = float(timeout)
    if not 0.1 <= timeout <= 30.0:
        raise ConfigError("server.timeout_seconds must be between 0.1 and 30")

    chrome_path = browser.get("chrome_path")
    if chrome_path is not None:
        chrome_path = _required_text(chrome_path, "browser.chrome_path", 1024)
    profile = _required_text(
        browser.get("profile_directory"), "browser.profile_directory", 1024
    )
    kill_switch = _boolean(safety.get("kill_switch"), "safety.kill_switch")
    manual_approval = _boolean(
        safety.get("manual_approval"), "safety.manual_approval"
    )
    auto_reply = _boolean(safety.get("auto_reply"), "safety.auto_reply")
    if not manual_approval or auto_reply:
        raise ConfigError("RC requires manual_approval=true and auto_reply=false")
    return AgentConfig(
        schema_version=CONFIG_VERSION,
        agent_id=_identifier(agent.get("agent_id"), "agent.agent_id"),
        device_id=_identifier(agent.get("device_id"), "agent.device_id"),
        customer_service_identity=_required_text(
            agent.get("customer_service_identity"),
            "agent.customer_service_identity",
            160,
        ),
        runtime_mode=runtime_mode,
        server=ServerConfig(
            address=address,
            client_id=_identifier(server.get("client_id"), "server.client_id"),
            key_id=_identifier(server.get("key_id"), "server.key_id"),
            credential_reference=credential_reference,
            timeout_seconds=timeout,
        ),
        browser=BrowserConfig(chrome_path=chrome_path, profile_directory=profile),
        safety=SafetyConfig(
            kill_switch=kill_switch,
            manual_approval=manual_approval,
            auto_reply=auto_reply,
        ),
    )


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be an object")
    return value


def _exact_fields(value: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConfigError(f"{name} contains unknown fields")


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be boolean")
    return value


def _validate_server_address(value: object, runtime_mode: str) -> str:
    text = _required_text(value, "server.address", 2048).rstrip("/")
    parsed = urlsplit(text)
    if (
        not parsed.scheme
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ConfigError("server.address must be an absolute credential-free origin")
    if parsed.scheme not in {"http", "https"}:
        raise ConfigError("server.address must use HTTP or HTTPS")
    if runtime_mode == "PILOT" and parsed.scheme != "https" and parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ConfigError("PILOT remote server requires HTTPS")
    return text


def _validate_credential_reference(value: object) -> str:
    text = _required_text(value, "server.credential_reference", 512)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "wincred"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError("credential reference must use wincred:// without embedded data")
    return text
