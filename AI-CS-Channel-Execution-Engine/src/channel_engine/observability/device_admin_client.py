from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_agent.identity import AgentConnectivityStatus, AgentIdentityStatus


class OperationsDeviceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OperationsDeviceView(OperationsDeviceModel):
    agent_id: str
    device_id: str
    agent_version: str | None = None
    hostname: str | None = None
    identity_status: AgentIdentityStatus
    connectivity_status: AgentConnectivityStatus
    runtime_status: str
    user_reference: str | None = None
    authorized_store_ids: tuple[str, ...] = ()
    active_store_id: str | None = None
    binding_revision: int = Field(ge=0)
    last_heartbeat: AwareDatetime | None = None
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]


class OperationsDeviceList(OperationsDeviceModel):
    items: tuple[OperationsDeviceView, ...]
    count: int = Field(ge=0)
    checked_at: AwareDatetime
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]


class OperationsBindingTargetStore(OperationsDeviceModel):
    store_id: int = Field(ge=1)
    store_code: str
    store_name: str
    platform: str
    is_default: bool


class OperationsBindingTarget(OperationsDeviceModel):
    user_id: str
    username: str
    display_name: str
    stores: tuple[OperationsBindingTargetStore, ...]


class OperationsBindingTargetList(OperationsDeviceModel):
    items: tuple[OperationsBindingTarget, ...]
    count: int = Field(ge=0)
    checked_at: AwareDatetime


class OperationsEnrollmentGrant(OperationsDeviceModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"]
    grant_id: str
    agent_id: str
    device_id: str
    user_reference: str
    store_references: tuple[str, ...]
    binding_code: str = Field(pattern=r"^[A-F0-9]{32}$", repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime


class OperationsHostPairingCode(OperationsDeviceModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"]
    host_id: str
    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    expires_at: AwareDatetime
    display_once: Literal[True]


class DeviceAdminClientError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class DeviceAdminClientPort(Protocol):
    def list_devices(self, access_token: str) -> OperationsDeviceList: ...

    def rotate_host_pairing_code(
        self, access_token: str, reason: str
    ) -> OperationsHostPairingCode: ...

    def list_binding_targets(
        self, access_token: str
    ) -> OperationsBindingTargetList: ...

    def issue_enrollment_grant(
        self,
        access_token: str,
        agent_id: str,
        *,
        user_id: str,
        store_ids: tuple[int, ...],
        reason: str,
    ) -> OperationsEnrollmentGrant: ...

    def disable(
        self, access_token: str, agent_id: str, reason: str
    ) -> OperationsDeviceList: ...

    def restore_to_registered(
        self, access_token: str, agent_id: str, reason: str
    ) -> OperationsDeviceList: ...


@dataclass(frozen=True, slots=True)
class OperationsAdminSession:
    access_token: str
    username: str
    display_name: str
    expires_at: datetime


class OperationsAdminSessionBroker:
    """Process-local AI-CS admin sessions; credentials and tokens never hit disk."""

    cookie_name = "channel_ops_admin_session"

    def __init__(self, ai_cs_base_url: str, *, timeout_seconds: float = 5.0) -> None:
        self.base_url = _validated_loopback_url(ai_cs_base_url)
        self.timeout_seconds = timeout_seconds
        self._sessions: dict[str, OperationsAdminSession] = {}
        self._lock = RLock()

    def login(self, username: str, password: str) -> tuple[str, OperationsAdminSession]:
        try:
            response = httpx.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
                timeout=self.timeout_seconds,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            raise DeviceAdminClientError("AI_CS_ADMIN_SERVICE_UNREACHABLE") from exc
        if response.status_code == 401:
            raise DeviceAdminClientError("AI_CS_ADMIN_LOGIN_REJECTED", 401)
        if response.status_code == 429:
            raise DeviceAdminClientError("AI_CS_ADMIN_LOGIN_RATE_LIMITED", 429)
        if response.status_code >= 400:
            raise DeviceAdminClientError("AI_CS_ADMIN_LOGIN_FAILED", 503)
        try:
            payload = response.json()
            user = payload["user"]
            roles = set(user.get("roles") or ())
            permissions = set(user.get("permissions") or ())
            if "ADMIN" not in roles and "user.manage" not in permissions:
                raise DeviceAdminClientError("AI_CS_ADMIN_PERMISSION_REQUIRED", 403)
            expires_at = datetime.fromisoformat(
                str(payload["expires_at"]).replace("Z", "+00:00")
            )
            session = OperationsAdminSession(
                access_token=str(payload["access_token"]),
                username=str(user["username"]),
                display_name=str(user.get("display_name") or user["username"]),
                expires_at=expires_at,
            )
        except DeviceAdminClientError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise DeviceAdminClientError("AI_CS_ADMIN_LOGIN_RESPONSE_INVALID", 502) from exc
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = session
        return session_id, session

    def resolve(self, session_id: str | None) -> OperationsAdminSession:
        if not session_id:
            raise DeviceAdminClientError("OPS_ADMIN_LOGIN_REQUIRED", 401)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise DeviceAdminClientError("OPS_ADMIN_SESSION_INVALID", 401)
            now = datetime.now(UTC)
            expires_at = (
                session.expires_at
                if session.expires_at.tzinfo is not None
                else session.expires_at.replace(tzinfo=UTC)
            )
            if expires_at <= now:
                self._sessions.pop(session_id, None)
                raise DeviceAdminClientError("OPS_ADMIN_SESSION_EXPIRED", 401)
            return session

    def logout(self, session_id: str | None) -> None:
        if session_id:
            with self._lock:
                self._sessions.pop(session_id, None)


class HttpAICSDeviceAdminClient:
    def __init__(self, ai_cs_base_url: str, *, timeout_seconds: float = 5.0) -> None:
        self.base_url = _validated_loopback_url(ai_cs_base_url)
        self.timeout_seconds = timeout_seconds

    def list_devices(self, access_token: str) -> OperationsDeviceList:
        return self._request("GET", "/api/v1/admin/desktop-workflow/devices", access_token)

    def rotate_host_pairing_code(
        self, access_token: str, reason: str
    ) -> OperationsHostPairingCode:
        payload = self._request_json(
            "POST",
            "/api/v1/admin/desktop-workflow/host/pairing-codes/rotate",
            access_token,
            payload={
                "reason": reason,
                "confirmation_phrase": "确认重新生成主机连接码",
            },
        )
        try:
            return OperationsHostPairingCode.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise DeviceAdminClientError(
                "AI_CS_HOST_PAIRING_CODE_RESPONSE_INVALID", 502
            ) from exc

    def list_binding_targets(
        self, access_token: str
    ) -> OperationsBindingTargetList:
        payload = self._request_json(
            "GET", "/api/v1/admin/desktop-workflow/binding-targets", access_token
        )
        try:
            return OperationsBindingTargetList.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise DeviceAdminClientError("AI_CS_BINDING_TARGET_RESPONSE_INVALID", 502) from exc

    def issue_enrollment_grant(
        self,
        access_token: str,
        agent_id: str,
        *,
        user_id: str,
        store_ids: tuple[int, ...],
        reason: str,
    ) -> OperationsEnrollmentGrant:
        payload = self._request_json(
            "POST",
            f"/api/v1/admin/desktop-workflow/devices/{quote(agent_id, safe='')}/enrollment-grants",
            access_token,
            payload={
                "user_id": user_id,
                "store_ids": list(store_ids),
                "reason": reason,
                "confirmation_phrase": "确认生成设备绑定许可",
            },
        )
        try:
            return OperationsEnrollmentGrant.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise DeviceAdminClientError("AI_CS_ENROLLMENT_GRANT_RESPONSE_INVALID", 502) from exc

    def disable(
        self, access_token: str, agent_id: str, reason: str
    ) -> OperationsDeviceList:
        return self._request(
            "POST",
            f"/api/v1/admin/desktop-workflow/devices/{quote(agent_id, safe='')}/disable",
            access_token,
            payload={
                "reason": reason,
                "confirmation_phrase": "确认禁用设备",
            },
        )

    def restore_to_registered(
        self, access_token: str, agent_id: str, reason: str
    ) -> OperationsDeviceList:
        return self._request(
            "POST",
            f"/api/v1/admin/desktop-workflow/devices/{quote(agent_id, safe='')}/restore-to-registered",
            access_token,
            payload={
                "reason": reason,
                "confirmation_phrase": "确认恢复为待绑定",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> OperationsDeviceList:
        body = self._request_json(method, path, access_token, payload=payload)
        try:
            return OperationsDeviceList.model_validate(body)
        except (ValueError, TypeError) as exc:
            raise DeviceAdminClientError("AI_CS_DEVICE_RESPONSE_INVALID", 502) from exc

    def _request_json(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> object:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
                timeout=self.timeout_seconds,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            raise DeviceAdminClientError("AI_CS_DEVICE_ADMIN_UNREACHABLE") from exc
        if response.status_code == 401:
            raise DeviceAdminClientError("OPS_ADMIN_SESSION_REJECTED", 401)
        if response.status_code == 403:
            raise DeviceAdminClientError("OPS_ADMIN_PERMISSION_DENIED", 403)
        if response.status_code >= 400:
            raise DeviceAdminClientError("HOST_CONTROL_DEVICE_OPERATION_REJECTED", 503)
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise DeviceAdminClientError("AI_CS_DEVICE_RESPONSE_INVALID", 502) from exc


def _validated_loopback_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("AI-CS admin URL must be an explicit loopback origin")
    return value.rstrip("/")


__all__ = [
    "DeviceAdminClientError",
    "DeviceAdminClientPort",
    "HttpAICSDeviceAdminClient",
    "OperationsBindingTargetList",
    "OperationsEnrollmentGrant",
    "OperationsHostPairingCode",
    "OperationsAdminSessionBroker",
    "OperationsDeviceList",
    "OperationsDeviceView",
]
