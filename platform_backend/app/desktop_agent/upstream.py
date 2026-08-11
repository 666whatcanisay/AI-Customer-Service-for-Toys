"""Signed V2.1 AI-CS service adapter for the Channel Engine Host Control."""

import ctypes
import hashlib
import hmac
import json
import os
import secrets
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import quote
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.desktop_agent.schemas import (
    UpstreamAgentIdentity,
    UpstreamAgentList,
    UpstreamEnrollmentGrant,
    UpstreamHostPairingCode,
)


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

    def rotate_host_pairing_code(self, *, reason: str) -> UpstreamHostPairingCode: ...

    def issue_enrollment_grant(
        self, *, agent_id: str, device_id: str, user_reference: str,
        store_references: tuple[str, ...], reason: str,
    ) -> UpstreamEnrollmentGrant: ...

    def activate_agent(self, *, agent_id: str, reason: str) -> None: ...

    def select_active_store(
        self, *, agent_id: str, device_id: str, user_reference: str,
        store_reference: str, platform: str, observed_platform_store_id: str,
        platform_binding_id: str, platform_binding_verified_at: str,
        binding_revision: int, reason: str,
    ) -> UpstreamAgentIdentity: ...

    def disable_agent(self, *, agent_id: str, reason: str) -> UpstreamAgentIdentity: ...

    def restore_agent_to_registered(
        self, *, agent_id: str, reason: str
    ) -> UpstreamAgentIdentity: ...


class HttpChannelAgentUpstream:
    def __init__(
        self,
        settings: Settings,
        *,
        credential_resolver: Callable[[str], bytes] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self._credential_resolver = credential_resolver or _read_windows_credential
        self._clock = clock

    def _configuration(self) -> tuple[str, str, str, bytes, bool | str]:
        if not self.settings.channel_agent_integration_enabled:
            raise ChannelAgentNotConfigured("Channel Agent integration is disabled")
        base_url = self.settings.channel_agent_server_url
        service_id = self.settings.channel_agent_service_id
        key_id = self.settings.channel_agent_service_key_id
        credential_reference = self.settings.channel_agent_service_credential_reference
        if not base_url or not service_id or not key_id or not credential_reference:
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
        try:
            secret = self._credential_resolver(credential_reference)
        except Exception as exc:
            raise ChannelAgentNotConfigured(
                "Channel Agent service credential reference is unavailable"
            ) from exc
        if len(secret) < 32:
            raise ChannelAgentNotConfigured("Channel Agent service credential is invalid")
        certificate_file = self.settings.channel_agent_ca_certificate_file
        verify: bool | str = True
        if parsed.scheme == "https":
            if not certificate_file:
                raise ChannelAgentNotConfigured(
                    "Channel Agent CA certificate is not configured"
                )
            certificate_path = Path(certificate_file)
            if not certificate_path.is_file():
                raise ChannelAgentNotConfigured(
                    "Channel Agent CA certificate is unavailable"
                )
            verify = str(certificate_path)
        return base_url, service_id, key_id, secret, verify

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> object:
        base_url, service_id, key_id, secret, verify = self._configuration()
        body = (
            b""
            if json is None
            else __import__("json").dumps(
                json, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        )
        timestamp = int(self._clock())
        nonce = secrets.token_hex(16)
        body_sha256 = hashlib.sha256(body).hexdigest()
        signature = hmac.new(
            secret,
            _canonical_service_request(
                service_id,
                key_id,
                method,
                path,
                timestamp,
                nonce,
                body_sha256,
            ),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-Channel-Agent-Control": "2.1",
            "X-Channel-Service-Id": service_id,
            "X-Channel-Service-Key-Id": key_id,
            "X-Channel-Timestamp": str(timestamp),
            "X-Channel-Nonce": nonce,
            "X-Channel-Body-SHA256": body_sha256,
            "X-Channel-Signature": signature,
        }
        if body:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = httpx.request(
                method,
                f"{base_url}{path}",
                headers=headers,
                content=body or None,
                timeout=self.settings.channel_agent_timeout_seconds,
                verify=verify,
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
                self._request("GET", "/channel-agent/v2/service/agents")
            )
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid("Channel Agent list contract is invalid") from exc

    def rotate_host_pairing_code(self, *, reason: str) -> UpstreamHostPairingCode:
        try:
            return UpstreamHostPairingCode.model_validate(
                self._request(
                    "POST",
                    "/channel-agent/v2/service/pairing-codes/rotate",
                    json={
                        "control_protocol_version": "2.1",
                        "reason": reason,
                        "confirmation_phrase": "确认重新生成主机连接码",
                    },
                    extra_headers={
                        "X-Operator-Intent": "HUMAN_CONFIRMED_HOST_PAIRING_CODE_ROTATION"
                    },
                )
            )
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid(
                "Channel Agent pairing-code response is invalid"
            ) from exc

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
                    "POST", "/channel-agent/v2/service/enrollment-grants", json=payload
                )
            )
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid("Channel Agent grant contract is invalid") from exc

    def activate_agent(self, *, agent_id: str, reason: str) -> None:
        self._request(
            "POST",
            f"/channel-agent/v2/service/agents/{quote(agent_id, safe='')}/activate",
            json={"protocol_version": "1.0", "reason": reason},
        )

    def select_active_store(
        self, *, agent_id: str, device_id: str, user_reference: str,
        store_reference: str, platform: str, observed_platform_store_id: str,
        platform_binding_id: str, platform_binding_verified_at: str,
        binding_revision: int, reason: str,
    ) -> UpstreamAgentIdentity:
        response = self._request(
            "POST",
            f"/channel-agent/v2/service/agents/{quote(agent_id, safe='')}/active-store",
            json={
                "protocol_version": "1.0",
                "device_id": device_id,
                "user_reference": user_reference,
                "store_reference": store_reference,
                "platform": platform,
                "observed_platform_store_id": observed_platform_store_id,
                "platform_binding_id": platform_binding_id,
                "platform_binding_verified_at": platform_binding_verified_at,
                "binding_revision": binding_revision,
                "human_confirmed": True,
                "reason": reason,
            },
            extra_headers={
                "X-Operator-Intent": "HUMAN_CONFIRMED_STORE_SELECTION"
            },
        )
        try:
            return UpstreamAgentIdentity.model_validate(response)
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid(
                "Channel Agent active-store response is invalid"
            ) from exc

    def disable_agent(
        self, *, agent_id: str, reason: str
    ) -> UpstreamAgentIdentity:
        response = self._request(
            "POST",
            f"/channel-agent/v2/service/agents/{quote(agent_id, safe='')}/disable",
            json={"protocol_version": "1.0", "reason": reason},
        )
        try:
            return UpstreamAgentIdentity.model_validate(response)
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid(
                "Channel Agent disable response is invalid"
            ) from exc

    def restore_agent_to_registered(
        self, *, agent_id: str, reason: str
    ) -> UpstreamAgentIdentity:
        response = self._request(
            "POST",
            f"/channel-agent/v2/service/agents/{quote(agent_id, safe='')}/restore-to-registered",
            json={
                "protocol_version": "1.0",
                "reason": reason,
                "confirmation_phrase": "确认恢复为待绑定",
            },
            extra_headers={
                "X-Operator-Intent": "HUMAN_CONFIRMED_AGENT_RESTORE"
            },
        )
        try:
            return UpstreamAgentIdentity.model_validate(response)
        except ValidationError as exc:
            raise ChannelAgentResponseInvalid(
                "Channel Agent restore response is invalid"
            ) from exc


def _canonical_service_request(
    service_id: str,
    key_id: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body_sha256: str,
) -> bytes:
    values = (
        service_id,
        key_id,
        method.upper(),
        path,
        str(timestamp),
        nonce,
        body_sha256,
    )
    if not path.startswith("/") or any("\r" in value or "\n" in value for value in values):
        raise ChannelAgentNotConfigured("Channel Agent signed request is invalid")
    return "\n".join(values).encode("utf-8")


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _read_windows_credential(reference: str) -> bytes:
    if os.name != "nt" or not reference.startswith("wincred://"):
        raise ValueError("Windows Credential Manager reference is required")
    from urllib.parse import unquote, urlsplit

    parsed = urlsplit(reference)
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("service credential reference is invalid")
    target = unquote(parsed.netloc + parsed.path)
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    pointer = ctypes.POINTER(_CREDENTIALW)()
    read = library.CredReadW
    read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    read.restype = wintypes.BOOL
    free = library.CredFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = None
    if not read(target, 1, 0, ctypes.byref(pointer)):
        raise ValueError("service credential reference cannot be resolved")
    try:
        credential = pointer.contents
        if not credential.CredentialBlob or credential.CredentialBlobSize < 32:
            raise ValueError("service credential is unavailable")
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
    finally:
        free(pointer)


def get_channel_agent_upstream() -> ChannelAgentUpstream:
    return HttpChannelAgentUpstream(get_settings())
