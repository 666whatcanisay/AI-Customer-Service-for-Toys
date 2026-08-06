"""Credential-isolating adapter for the existing Channel Agent Admin API."""

from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.desktop_agent.schemas import UpstreamAgentList, UpstreamEnrollmentGrant


class ChannelAgentNotConfigured(RuntimeError):
    pass


class ChannelAgentUnavailable(RuntimeError):
    pass


class ChannelAgentPermissionInvalid(RuntimeError):
    pass


class ChannelAgentResponseInvalid(RuntimeError):
    pass


class ChannelAgentRequestRejected(RuntimeError):
    pass


class ChannelAgentUpstream(Protocol):
    def list_agents(self) -> UpstreamAgentList: ...

    def issue_enrollment_grant(
        self, *, agent_id: str, device_id: str, user_reference: str,
        store_references: tuple[str, ...], reason: str,
    ) -> UpstreamEnrollmentGrant: ...


class HttpChannelAgentUpstream:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _configuration(self) -> tuple[str, str]:
        if not self.settings.channel_agent_integration_enabled:
            raise ChannelAgentNotConfigured("Channel Agent integration is disabled")
        base_url = self.settings.channel_agent_server_url
        secret_path = self.settings.channel_agent_operator_session_file
        if not base_url or not secret_path:
            raise ChannelAgentNotConfigured("Channel Agent integration is incomplete")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ChannelAgentNotConfigured("Channel Agent server URL is invalid")
        if parsed.scheme == "http" and parsed.hostname.casefold() not in {
            "127.0.0.1", "localhost", "::1"
        }:
            raise ChannelAgentNotConfigured("Non-loopback Channel Agent requires HTTPS")
        path = Path(secret_path).expanduser().resolve()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ChannelAgentNotConfigured("Channel Agent session reference is unavailable") from exc
        if len(raw) > 4096:
            raise ChannelAgentNotConfigured("Channel Agent session reference is invalid")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChannelAgentNotConfigured("Channel Agent session reference is invalid") from exc
        token = text.strip()
        if not token or "\n" in token or "\r" in token:
            raise ChannelAgentNotConfigured("Channel Agent session reference is invalid")
        return base_url, token

    def _request(self, method: str, path: str, *, json: dict | None = None) -> object:
        base_url, session_reference = self._configuration()
        try:
            response = httpx.request(
                method,
                f"{base_url}{path}",
                headers={"X-Operator-Session-Reference": session_reference},
                json=json,
                timeout=self.settings.channel_agent_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ChannelAgentUnavailable("Channel Agent server is unreachable") from exc
        if response.status_code in {401, 403}:
            raise ChannelAgentPermissionInvalid("Channel Agent operator permission is invalid")
        if response.status_code >= 400:
            raise ChannelAgentRequestRejected("Channel Agent rejected the request")
        try:
            return response.json()
        except ValueError as exc:
            raise ChannelAgentResponseInvalid("Channel Agent returned invalid JSON") from exc

    def list_agents(self) -> UpstreamAgentList:
        try:
            return UpstreamAgentList.model_validate(
                self._request("GET", "/channel-agent/v1/admin/agents")
            )
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid("Channel Agent list contract is invalid") from exc

    def issue_enrollment_grant(
        self, *, agent_id: str, device_id: str, user_reference: str,
        store_references: tuple[str, ...], reason: str,
    ) -> UpstreamEnrollmentGrant:
        payload = {
            "protocol_version": "1.0",
            "agent_id": agent_id,
            "device_id": device_id,
            "user_reference": user_reference,
            "store_references": list(store_references),
            "expires_in_seconds": 600,
            "reason": reason,
        }
        try:
            return UpstreamEnrollmentGrant.model_validate(
                self._request(
                    "POST", "/channel-agent/v1/admin/enrollment-grants", json=payload
                )
            )
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid("Channel Agent grant contract is invalid") from exc


def get_channel_agent_upstream() -> ChannelAgentUpstream:
    return HttpChannelAgentUpstream(get_settings())
