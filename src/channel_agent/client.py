from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from .config import ChannelAgentConfig
from .binding import AgentEnrollmentRequest, AgentEnrollmentResponse
from .contract import (
    AgentConfigResponse,
    AgentHeartbeatAck,
    AgentHeartbeatRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentRuntimeStatus,
    ManagedAgentConfig,
)
from .version import AGENT_PROTOCOL_VERSION, AGENT_VERSION
from .identity import AgentIdentity, AgentIdentityStatus


class AgentClientError(RuntimeError):
    pass


class AgentConnectionError(AgentClientError):
    pass


class AgentRejectedError(AgentClientError):
    """A fail-closed Channel Engine rejection with bounded public metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class AgentProtocolError(AgentClientError):
    pass


class ChannelEngineClient:
    """Versioned control client; it exposes no message or execution operation."""

    REGISTER_PATH = "/channel-agent/v1/agents/register"
    ENROLL_PATH = "/channel-agent/v1/agents/enroll"

    def __init__(
        self,
        config: ChannelAgentConfig,
        *,
        http_client: Any | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._identity: AgentIdentity | None = None
        self._http = http_client or httpx.Client(
            base_url=config.server_url,
            timeout=httpx.Timeout(config.connect_timeout_seconds),
            follow_redirects=False,
        )

    def register(
        self,
        *,
        hostname: str,
        status: AgentRuntimeStatus,
        timestamp: datetime,
    ) -> AgentRegistrationResponse:
        request = AgentRegistrationRequest(
            agent_id=self._config.agent_id,
            device_id=self._config.device_id,
            agent_version=AGENT_VERSION,
            user_reference=self._config.user_reference,
            store_reference=self._config.store_reference,
            store_references=self._config.store_references,
            hostname=hostname,
            status=status,
            timestamp=timestamp,
        )
        response = self._request(
            "POST",
            self.REGISTER_PATH,
            json=request.model_dump(mode="json"),
            headers={
                "Idempotency-Key": (
                    f"agent-register:{self._config.agent_id}:{self._config.device_id}"
                )
            },
        )
        envelope = self._validate_response(response, AgentRegistrationResponse)
        self._identity = envelope.identity
        return envelope

    def enroll(self, binding_code: str) -> AgentEnrollmentResponse:
        if not self._enrollment_transport_is_safe():
            raise AgentConnectionError(
                "Agent enrollment requires HTTPS or a loopback Channel Engine"
            )
        request = AgentEnrollmentRequest(
            agent_id=self._config.agent_id,
            device_id=self._config.device_id,
            binding_code=binding_code,
        )
        response = self._request(
            "POST",
            self.ENROLL_PATH,
            json=request.model_dump(mode="json"),
        )
        envelope = self._validate_response(response, AgentEnrollmentResponse)
        binding = envelope.binding
        self._identity = AgentIdentity(
            agent_id=binding.agent_id,
            device_id=binding.device_id,
            user_id=binding.user_id,
            store_id=binding.store_ids[0] if binding.store_ids else None,
            store_ids=binding.store_ids,
            status=binding.identity_status,
            binding_revision=binding.binding_revision,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )
        return envelope

    def report_status(
        self,
        *,
        hostname: str,
        status: AgentRuntimeStatus,
        timestamp: datetime,
    ) -> AgentHeartbeatAck:
        identity = self._identity
        asserted = identity is not None and identity.status in {
            AgentIdentityStatus.BOUND,
            AgentIdentityStatus.ACTIVE,
        }
        store_ids = identity.effective_store_ids if asserted else ()
        request = AgentHeartbeatRequest(
            agent_id=self._config.agent_id,
            device_id=self._config.device_id,
            user_id=identity.user_id if asserted else None,
            store_id=store_ids[0] if store_ids else None,
            store_ids=store_ids,
            binding_revision=identity.binding_revision if asserted else 0,
            version=AGENT_VERSION,
            hostname=hostname,
            status=status,
            timestamp=timestamp,
        )
        path = f"/channel-agent/v1/agents/{quote(self._config.agent_id, safe='')}/status"
        response = self._request(
            "PUT",
            path,
            json=request.model_dump(mode="json"),
        )
        envelope = self._validate_response(response, AgentHeartbeatAck)
        if envelope.identity is not None:
            self._identity = envelope.identity
        return envelope

    def fetch_config(self) -> ManagedAgentConfig:
        path = f"/channel-agent/v1/agents/{quote(self._config.agent_id, safe='')}/config"
        response = self._request(
            "GET",
            path,
            params={"device_id": self._config.device_id},
        )
        envelope = self._validate_response(response, AgentConfigResponse)
        if envelope.agent_id != self._config.agent_id:
            raise AgentProtocolError("Channel Engine returned config for another agent")
        if envelope.device_id != self._config.device_id:
            raise AgentProtocolError("Channel Engine returned config for another device")
        if envelope.identity is not None:
            self._identity = envelope.identity
        return envelope.config

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def _enrollment_transport_is_safe(self) -> bool:
        parsed = urlsplit(self._config.server_url)
        if parsed.scheme == "https":
            return True
        return parsed.hostname in {"127.0.0.1", "::1", "localhost"}

    def _request(self, method: str, path: str, **kwargs: object) -> Any:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"ai-cs-channel-agent/{AGENT_VERSION}",
            "X-Channel-Agent-Protocol": AGENT_PROTOCOL_VERSION,
        }
        supplied = kwargs.pop("headers", None)
        if isinstance(supplied, dict):
            headers.update({str(key): str(value) for key, value in supplied.items()})
        try:
            response = self._http.request(method, path, headers=headers, **kwargs)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise AgentConnectionError("Channel Engine is unavailable") from exc
        except OSError as exc:
            raise AgentConnectionError("Channel Engine connection failed") from exc
        if response.status_code >= 500:
            raise AgentConnectionError("Channel Engine returned a server error")
        if response.status_code >= 400:
            raise AgentRejectedError(
                f"Channel Engine rejected Agent request with status {response.status_code}",
                status_code=int(response.status_code),
                error_code=self._response_error_code(response),
            )
        return response

    @staticmethod
    def _response_error_code(response: Any) -> str | None:
        """Extract only the bounded error code; never retain a response body."""

        try:
            payload = response.json()
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        detail = payload.get("detail")
        if isinstance(detail, dict):
            value = detail.get("code")
        else:
            error = payload.get("error")
            value = error.get("code") if isinstance(error, dict) else None
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        if not normalized or len(normalized) > 128:
            return None
        return normalized

    @staticmethod
    def _validate_response(response: Any, model_type: Any) -> Any:
        try:
            payload = response.json()
            value = model_type.model_validate(payload)
        except (ValueError, ValidationError, TypeError) as exc:
            raise AgentProtocolError("Channel Engine returned an invalid V1 envelope") from exc
        if value.protocol_version != AGENT_PROTOCOL_VERSION:
            raise AgentProtocolError("Channel Agent protocol version mismatch")
        return value


__all__ = [
    "AgentClientError",
    "AgentConnectionError",
    "AgentProtocolError",
    "AgentRejectedError",
    "ChannelEngineClient",
]
