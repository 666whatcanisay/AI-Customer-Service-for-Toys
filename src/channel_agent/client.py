from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from .config import ChannelAgentConfig
from .binding import (
    AgentActiveStoreSelectionRequest,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
)
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
from .control_v2 import DeviceRequestSigner
from .control_v2 import (
    AgentAssistantEventPollResponse,
    AgentObservationAck,
    AgentObservationSubmission,
)
from .security import DeviceCredentialStore, WindowsDeviceCredentialStore


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


class AgentPairingRequiredError(AgentClientError):
    """The device has no V2.1 credential and must be paired by a human."""

    pass


class ChannelEngineClient:
    """Signed Agent Control V2.1 client used by the production Edge runtime."""

    def __init__(
        self,
        config: ChannelAgentConfig,
        *,
        http_client: Any | None = None,
        credential_store: DeviceCredentialStore | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._identity: AgentIdentity | None = None
        self._credential_store = credential_store or WindowsDeviceCredentialStore()
        self._signer: DeviceRequestSigner | None = None
        if config.device_credential_reference is not None:
            material = self._credential_store.acquire(
                config.device_credential_reference
            )
            self._signer = DeviceRequestSigner(
                config.agent_id,
                config.device_id,
                material.for_signing(),
            )
        self._http = http_client or httpx.Client(
            base_url=config.server_url,
            timeout=httpx.Timeout(config.connect_timeout_seconds),
            follow_redirects=False,
            verify=(
                str(config.server_ca_certificate_path)
                if config.server_ca_certificate_path is not None
                else True
            ),
            trust_env=False,
        )

    @property
    def identity(self) -> AgentIdentity | None:
        """Return the last server-authoritative public identity snapshot."""
        return self._identity

    def _control_path(self, suffix: str) -> str:
        if self._signer is None:
            raise AgentPairingRequiredError(
                "Channel Agent device pairing is required before control requests"
            )
        return f"/channel-agent/v2{suffix}"

    @property
    def secure_control_ready(self) -> bool:
        return self._signer is not None

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
            authorized_store_ids=self._config.store_references,
            active_store_id=self._config.store_reference,
            hostname=hostname,
            status=status,
            timestamp=timestamp,
        )
        response = self._request(
            "POST",
            self._control_path("/agents/register"),
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
            self._control_path("/agents/enroll"),
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
            authorized_store_ids=(
                binding.authorized_store_ids or binding.store_ids
            ),
            active_store_id=binding.active_store_id,
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
            authorized_store_ids=store_ids,
            active_store_id=(
                identity.effective_active_store_id if asserted else None
            ),
            binding_revision=identity.binding_revision if asserted else 0,
            version=AGENT_VERSION,
            hostname=hostname,
            status=status,
            timestamp=timestamp,
        )
        path = self._control_path(
            f"/agents/{quote(self._config.agent_id, safe='')}/status"
        )
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
        path = self._control_path(
            f"/agents/{quote(self._config.agent_id, safe='')}/config"
        )
        request_arguments = (
            {} if self._signer is not None else {"params": {"device_id": self._config.device_id}}
        )
        response = self._request("GET", path, **request_arguments)
        envelope = self._validate_response(response, AgentConfigResponse)
        if envelope.agent_id != self._config.agent_id:
            raise AgentProtocolError("Channel Engine returned config for another agent")
        if envelope.device_id != self._config.device_id:
            raise AgentProtocolError("Channel Engine returned config for another device")
        if envelope.identity is not None:
            self._identity = envelope.identity
        return envelope.config

    def select_active_store(
        self,
        store_reference: str,
        observed_store_reference: str,
        *,
        reason: str,
    ) -> AgentIdentity:
        if self._signer is None:
            raise AgentConnectionError(
                "active store selection requires the secure Agent control protocol"
            )
        identity = self._identity
        if identity is None:
            raise AgentProtocolError("Agent identity is unavailable")
        request = AgentActiveStoreSelectionRequest(
            device_id=self._config.device_id,
            store_reference=store_reference,
            observed_store_reference=observed_store_reference,
            binding_revision=identity.binding_revision,
            reason=reason,
        )
        path = self._control_path(
            f"/agents/{quote(self._config.agent_id, safe='')}/active-store"
        )
        response = self._request(
            "PUT",
            path,
            json=request.model_dump(mode="json"),
        )
        try:
            selected = AgentIdentity.model_validate(response.json())
        except (ValueError, ValidationError, TypeError) as exc:
            raise AgentProtocolError(
                "Channel Engine returned an invalid active store response"
            ) from exc
        self._identity = selected
        return selected

    def submit_observation(
        self, submission: AgentObservationSubmission
    ) -> AgentObservationAck:
        self._assert_v21_ready()
        response = self._request(
            "POST",
            "/channel-agent/v2/observations",
            json=submission.model_dump(mode="json"),
        )
        return self._validate_control_response(response, AgentObservationAck)

    def poll_command(self):
        AgentCommandPollResponse = _execution_model("AgentCommandPollResponse")

        self._assert_v21_ready()
        response = self._request("GET", "/channel-agent/v2/commands/next")
        return self._validate_control_response(response, AgentCommandPollResponse)

    def poll_assistant_events(
        self,
        *,
        after_sequence_id: int = 0,
        limit: int = 100,
    ) -> AgentAssistantEventPollResponse:
        self._assert_v21_ready()
        response = self._request(
            "GET",
            "/channel-agent/v2/assistant-events/next",
            params={"after_sequence_id": after_sequence_id, "limit": limit},
        )
        return self._validate_control_response(
            response, AgentAssistantEventPollResponse
        )

    def fetch_assistant_snapshot(
        self,
        *,
        store_id: str | None = None,
        conversation_id: str | None = None,
    ):
        from .control_v2 import AgentAssistantSnapshotResponse

        self._assert_v21_ready()
        params = {}
        if store_id is not None or conversation_id is not None:
            if store_id is None or conversation_id is None:
                raise ValueError("assistant snapshot scope must be complete")
            params = {
                "store_id": store_id,
                "conversation_id": conversation_id,
            }
        response = self._request(
            "GET",
            "/channel-agent/v2/assistant-snapshot",
            params=params,
        )
        return self._validate_control_response(
            response, AgentAssistantSnapshotResponse
        )

    def submit_receipt(self, submission):
        AgentReceiptAck = _execution_model("AgentReceiptAck")

        self._assert_v21_ready()
        response = self._request(
            "POST",
            "/channel-agent/v2/receipts",
            json=submission.model_dump(mode="json"),
        )
        return self._validate_control_response(response, AgentReceiptAck)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()
    def _enrollment_transport_is_safe(self) -> bool:
        parsed = urlsplit(self._config.server_url)
        if parsed.scheme == "https":
            return True
        return parsed.hostname in {"127.0.0.1", "::1", "localhost"}

    def _assert_v21_ready(self) -> None:
        if self._signer is None:
            raise AgentPairingRequiredError(
                "Channel Agent V2.1 device credential is unavailable"
            )

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
        if self._signer is not None:
            value = kwargs.pop("json", None)
            if value is None:
                body = b""
            else:
                body = json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                kwargs["content"] = body
            headers.update(self._signer.headers(method, path, body))
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
            raise AgentProtocolError("Channel Engine returned an invalid control envelope") from exc
        if value.protocol_version != AGENT_PROTOCOL_VERSION:
            raise AgentProtocolError("Channel Agent protocol version mismatch")
        return value

    @staticmethod
    def _validate_control_response(response: Any, model_type: Any) -> Any:
        try:
            return model_type.model_validate(response.json())
        except (ValueError, ValidationError, TypeError) as exc:
            raise AgentProtocolError(
                "Channel Engine returned an invalid V2.1 control response"
            ) from exc


def _execution_model(name: str):
    """Keep send-capable contracts absent from the OBSERVE_ONLY package."""

    module = __import__("channel_agent.execution_control", fromlist=(name,))
    return getattr(module, name)


__all__ = [
    "AgentClientError",
    "AgentConnectionError",
    "AgentProtocolError",
    "AgentPairingRequiredError",
    "AgentRejectedError",
    "ChannelEngineClient",
]
