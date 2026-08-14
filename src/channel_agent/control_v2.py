from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, RLock
from typing import Any, Callable, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .security import DeviceCredentialMaterial
from .version import AGENT_CONTROL_PROTOCOL_VERSION


LAN_DISCOVERY_PORT = 18421
LAN_DISCOVERY_MAGIC = "AI_CS_CHANNEL_AGENT_DISCOVERY_V2"
_PAIRING_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class AgentControlV2Error(RuntimeError):
    pass


class DeviceAuthenticationError(PermissionError):
    pass


class PairingError(PermissionError):
    pass


class ControlV2Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    control_protocol_version: Literal["2.1"] = AGENT_CONTROL_PROTOCOL_VERSION


class LANHostCandidate(ControlV2Model):
    host_id: str = Field(min_length=1, max_length=128)
    host_name: str = Field(min_length=1, max_length=255)
    environment: Literal["MOCK", "STAGING", "PRODUCTION"]
    server_url: str = Field(min_length=1, max_length=2048)
    server_version: str = Field(min_length=1, max_length=64)
    certificate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ca_certificate_pem: str = Field(min_length=64, max_length=32_768, repr=False)
    customer_service_url: str | None = Field(default=None, min_length=1, max_length=2048)
    customer_service_certificate_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    customer_service_ca_certificate_pem: str | None = Field(
        default=None, min_length=64, max_length=32_768, repr=False
    )

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("LAN host URL must be a credential-free HTTPS origin")
        return normalized

    @field_validator("customer_service_url")
    @classmethod
    def validate_customer_service_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("customer service URL must be a credential-free HTTPS origin")
        return normalized


class LANDiscoveryAnnouncement(ControlV2Model):
    request_nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    candidate: LANHostCandidate
    pairing_proof: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)


class PairDeviceRequest(ControlV2Model):
    host_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    human_confirmed: Literal[True]
    requested_at: datetime

    @field_validator("pairing_code")
    @classmethod
    def normalize_pairing_code(cls, value: str) -> str:
        return normalize_pairing_code(value)


class PairDeviceResponse(ControlV2Model):
    accepted: Literal[True] = True
    host_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    device_credential_reference: str = Field(min_length=1, max_length=512)
    device_secret_base64: str = Field(min_length=44, max_length=2048, repr=False)
    paired_at: datetime

    def secret_bytes(self) -> bytes:
        try:
            value = base64.b64decode(self.device_secret_base64, validate=True)
        except ValueError as exc:
            raise PairingError("pairing response secret is invalid") from exc
        if len(value) < 32:
            raise PairingError("pairing response secret is invalid")
        return value


class HostPairingCodeRotateRequest(ControlV2Model):
    reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认重新生成主机连接码"]


class HostPairingCodeRotateResponse(ControlV2Model):
    host_id: str = Field(min_length=1, max_length=128)
    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    expires_at: AwareDatetime
    display_once: Literal[True] = True


class HostPairingCredential(ControlV2Model):
    """Encrypted-at-rest payload shared by Host Control and LAN discovery."""

    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    expires_at: AwareDatetime


class AgentObservationSubmission(ControlV2Model):
    observation_id: str = Field(min_length=1, max_length=160)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    source_cursor: str = Field(min_length=1, max_length=512)
    source_sequence: int = Field(ge=0)
    payload_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    payload: dict[str, Any]
    captured_at: AwareDatetime


class AgentObservationAck(ControlV2Model):
    observation_id: str
    status: Literal["PERSISTED", "DUPLICATE"]
    acknowledged_cursor: str
    persisted_at: AwareDatetime


AssistantEventType = Literal[
    "MESSAGE_ACCEPTED",
    "QUESTION_GROUP_FORMED",
    "AI_GENERATING",
    "AI_SUGGESTION_READY",
    "WAITING_APPROVAL",
    "OBSERVATION_FAILED",
    "QUALITY_GATE",
    "EXECUTION_PREPARED",
]


class AgentAssistantEvent(ControlV2Model):
    event_id: str = Field(min_length=1, max_length=160)
    sequence_id: int = Field(ge=1)
    event_type: AssistantEventType
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=255)
    turn_id: str | None = Field(default=None, min_length=1, max_length=160)
    decision_id: str | None = Field(default=None, min_length=1, max_length=160)
    status: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: AwareDatetime


class AgentAssistantEventPollResponse(ControlV2Model):
    events: tuple[AgentAssistantEvent, ...] = Field(max_length=100)
    next_sequence_id: int = Field(ge=0)
    server_time: AwareDatetime


class AgentAssistantSafetyFacts(ControlV2Model):
    read_only: Literal[True] = True
    manual_approval_required: bool = True
    auto_reply: bool = False
    real_send: Literal[False] = False
    browser_write_operations: Literal[0] = 0
    execution_count: Literal[0] = 0
    receipt_count: Literal[0] = 0
    send_count: Literal[0] = 0
    execution_prepared: bool = False
    preparation_count: int = Field(default=0, ge=0, le=1)


class AgentAssistantSnapshot(ControlV2Model):
    schema_version: Literal["channel-agent-assistant-snapshot.v1"] = (
        "channel-agent-assistant-snapshot.v1"
    )
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    revision: int = Field(ge=1)
    status: Literal["WAITING_APPROVAL", "MANUAL_INTERVENTION", "EXECUTION_PREPARED"]
    turn_id: str = Field(min_length=1, max_length=160)
    # The verified PDD/customer message that the Decision actually answers.
    # Optional keeps already persisted RC5 snapshots readable; controlled real
    # send remains fail-closed when this value is unavailable.
    customer_message_id: str | None = Field(default=None, min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=160)
    request_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(min_length=1, max_length=255)
    current_question: str = Field(min_length=1, max_length=24_000, repr=False)
    action: str = Field(min_length=1, max_length=64)
    reply_content: str | None = Field(default=None, max_length=24_000, repr=False)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    citations: tuple[dict[str, Any], ...] = Field(default=(), max_length=32)
    # Internal UI projection only. This reuses CustomerContext facts and does
    # not change the Gateway or ExecutionPreparation wire contracts.
    product_context: dict[str, Any] | None = None
    ai_cs_action: str = Field(default="UNKNOWN", min_length=1, max_length=64)
    warnings: tuple[str, ...] = Field(default=(), max_length=32)
    required_fields: tuple[str, ...] = Field(default=(), max_length=32)
    policy_mode: Literal["MANUAL_CONFIRM", "AUTO_LOW_RISK"] = "MANUAL_CONFIRM"
    quality_status: Literal["PASS", "BLOCKED"] = "PASS"
    preparation_id: str | None = Field(default=None, max_length=160)
    trace_id: str | None = Field(default=None, pattern=r"^trace:[a-f0-9]{64}$")
    processing_stage: str | None = Field(default=None, max_length=64)
    safety: AgentAssistantSafetyFacts = Field(default_factory=AgentAssistantSafetyFacts)
    updated_at: AwareDatetime
    expires_at: AwareDatetime


class AgentAssistantSnapshotResponse(ControlV2Model):
    snapshot: AgentAssistantSnapshot | None
    server_time: AwareDatetime


class AgentAssistantConversationListResponse(ControlV2Model):
    schema_version: Literal["channel-agent-assistant-conversations.v2"] = (
        "channel-agent-assistant-conversations.v2"
    )
    conversations: tuple[AgentAssistantSnapshot, ...] = Field(max_length=100)
    server_time: AwareDatetime


AssistantPipelineStage = Literal[
    "PROVIDER_READ",
    "EDGE_SPOOL",
    "HOST_PERSIST",
    "BUFFERING",
    "CUSTOMER_CONTEXT",
    "AI_GENERATING",
    "QUALITY_GATE",
    "WAITING_CONFIRMATION",
    "EXECUTION_PREPARED",
    "RECEIPT",
]
AssistantPipelineStageState = Literal[
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "WAITING_HUMAN",
]


class AgentAssistantTraceStep(ControlV2Model):
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    stage: AssistantPipelineStage
    state: AssistantPipelineStageState
    reason_code: str = Field(min_length=1, max_length=128)
    started_at: AwareDatetime
    updated_at: AwareDatetime
    duration_ms: float = Field(ge=0)


class AgentAssistantTraceResponse(ControlV2Model):
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    steps: tuple[AgentAssistantTraceStep, ...]
    server_time: AwareDatetime


class DeviceCredentialResolver(Protocol):
    def __call__(self, agent_id: str, device_id: str) -> DeviceCredentialMaterial: ...


class ReplayNonceStore(Protocol):
    def consume(self, namespace: str, nonce: str, timestamp: int, expires_at: int) -> bool: ...


class DeviceRequestSigner:
    def __init__(self, agent_id: str, device_id: str, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("device signing secret must be at least 32 bytes")
        self.agent_id = agent_id
        self.device_id = device_id
        self._secret = bytes(secret)

    def headers(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        actual_timestamp = int(time.time()) if timestamp is None else int(timestamp)
        actual_nonce = nonce or secrets.token_hex(16)
        body_sha256 = hashlib.sha256(body).hexdigest()
        signature = hmac.new(
            self._secret,
            _request_canonical(
                self.agent_id,
                self.device_id,
                method,
                path,
                actual_timestamp,
                actual_nonce,
                body_sha256,
            ),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Channel-Agent-Control": AGENT_CONTROL_PROTOCOL_VERSION,
            "X-Channel-Agent-Id": self.agent_id,
            "X-Channel-Device-Id": self.device_id,
            "X-Channel-Timestamp": str(actual_timestamp),
            "X-Channel-Nonce": actual_nonce,
            "X-Channel-Body-SHA256": body_sha256,
            "X-Channel-Signature": signature,
        }


class DeviceRequestVerifier:
    def __init__(
        self,
        resolver: DeviceCredentialResolver,
        *,
        clock: Callable[[], float] = time.time,
        allowed_skew_seconds: int = 120,
        nonce_store: ReplayNonceStore | None = None,
    ) -> None:
        self._resolver = resolver
        self._clock = clock
        self._allowed_skew = allowed_skew_seconds
        self._nonces: dict[tuple[str, str], int] = {}
        self._nonce_store = nonce_store
        self._lock = RLock()

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> tuple[str, str]:
        try:
            agent_id = headers["x-channel-agent-id"]
            device_id = headers["x-channel-device-id"]
            timestamp = int(headers["x-channel-timestamp"])
            nonce = headers["x-channel-nonce"]
            body_sha256 = headers["x-channel-body-sha256"]
            signature = headers["x-channel-signature"]
            protocol = headers["x-channel-agent-control"]
        except (KeyError, ValueError) as exc:
            raise DeviceAuthenticationError("device authentication headers are missing") from exc
        if protocol != AGENT_CONTROL_PROTOCOL_VERSION:
            raise DeviceAuthenticationError("device control protocol is unsupported")
        with self._lock:
            now = int(self._clock())
            if abs(now - timestamp) > self._allowed_skew:
                raise DeviceAuthenticationError("device request timestamp is outside the replay window")
            if len(nonce) != 32 or any(character not in "0123456789abcdef" for character in nonce):
                raise DeviceAuthenticationError("device request nonce is invalid")
            if hashlib.sha256(body).hexdigest() != body_sha256:
                raise DeviceAuthenticationError("device request body digest is invalid")
            self._purge_nonces(now)
            try:
                material = self._resolver(agent_id, device_id)
            except Exception as exc:
                raise DeviceAuthenticationError(
                    "device credential is unavailable"
                ) from exc
            expected = hmac.new(
                material.for_signing(),
                _request_canonical(
                    agent_id,
                    device_id,
                    method,
                    path,
                    timestamp,
                    nonce,
                    body_sha256,
                ),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise DeviceAuthenticationError("device request signature is invalid")
            nonce_key = (device_id, nonce)
            if self._nonce_store is not None:
                if not self._nonce_store.consume(
                    f"device:{agent_id}:{device_id}",
                    nonce,
                    timestamp,
                    now + self._allowed_skew,
                ):
                    raise DeviceAuthenticationError("device request nonce was replayed")
            else:
                if nonce_key in self._nonces:
                    raise DeviceAuthenticationError("device request nonce was replayed")
                self._nonces[nonce_key] = timestamp
            return agent_id, device_id

    def _purge_nonces(self, now: int) -> None:
        cutoff = now - self._allowed_skew
        self._nonces = {
            key: timestamp
            for key, timestamp in self._nonces.items()
            if timestamp >= cutoff
        }


class ServiceRequestSigner:
    """AI-CS service identity signer; it is deliberately separate from device keys."""

    def __init__(self, service_id: str, key_id: str, secret: bytes) -> None:
        if not service_id or not key_id or len(secret) < 32:
            raise ValueError("service signing identity is invalid")
        self.service_id = service_id
        self.key_id = key_id
        self._secret = bytes(secret)

    def headers(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        actual_timestamp = int(time.time()) if timestamp is None else int(timestamp)
        actual_nonce = nonce or secrets.token_hex(16)
        body_sha256 = hashlib.sha256(body).hexdigest()
        signature = hmac.new(
            self._secret,
            _service_request_canonical(
                self.service_id,
                self.key_id,
                method,
                path,
                actual_timestamp,
                actual_nonce,
                body_sha256,
            ),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Channel-Agent-Control": AGENT_CONTROL_PROTOCOL_VERSION,
            "X-Channel-Service-Id": self.service_id,
            "X-Channel-Service-Key-Id": self.key_id,
            "X-Channel-Timestamp": str(actual_timestamp),
            "X-Channel-Nonce": actual_nonce,
            "X-Channel-Body-SHA256": body_sha256,
            "X-Channel-Signature": signature,
        }


class ServiceRequestVerifier:
    def __init__(
        self,
        resolver: Callable[[str, str], bytes],
        *,
        clock: Callable[[], float] = time.time,
        allowed_skew_seconds: int = 120,
        nonce_store: ReplayNonceStore | None = None,
    ) -> None:
        self._resolver = resolver
        self._clock = clock
        self._allowed_skew = allowed_skew_seconds
        self._nonce_store = nonce_store
        self._nonces: dict[tuple[str, str], int] = {}
        self._lock = RLock()

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> str:
        try:
            service_id = headers["x-channel-service-id"]
            key_id = headers["x-channel-service-key-id"]
            timestamp = int(headers["x-channel-timestamp"])
            nonce = headers["x-channel-nonce"]
            body_sha256 = headers["x-channel-body-sha256"]
            signature = headers["x-channel-signature"]
            protocol = headers["x-channel-agent-control"]
        except (KeyError, ValueError) as exc:
            raise DeviceAuthenticationError("service authentication headers are missing") from exc
        now = int(self._clock())
        if protocol != AGENT_CONTROL_PROTOCOL_VERSION:
            raise DeviceAuthenticationError("service control protocol is unsupported")
        if abs(now - timestamp) > self._allowed_skew:
            raise DeviceAuthenticationError("service request timestamp is outside the replay window")
        if len(nonce) != 32 or any(character not in "0123456789abcdef" for character in nonce):
            raise DeviceAuthenticationError("service request nonce is invalid")
        if hashlib.sha256(body).hexdigest() != body_sha256:
            raise DeviceAuthenticationError("service request body digest is invalid")
        try:
            secret = self._resolver(service_id, key_id)
        except Exception as exc:
            raise DeviceAuthenticationError(
                "service credential is unavailable"
            ) from exc
        if len(secret) < 32:
            raise DeviceAuthenticationError("service credential is invalid")
        expected = hmac.new(
            secret,
            _service_request_canonical(
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
        if not hmac.compare_digest(expected, signature):
            raise DeviceAuthenticationError("service request signature is invalid")
        with self._lock:
            namespace = f"service:{service_id}:{key_id}"
            if self._nonce_store is not None:
                accepted = self._nonce_store.consume(
                    namespace,
                    nonce,
                    timestamp,
                    now + self._allowed_skew,
                )
            else:
                cutoff = now - self._allowed_skew
                self._nonces = {
                    key: value for key, value in self._nonces.items() if value >= cutoff
                }
                replay_key = (namespace, nonce)
                accepted = replay_key not in self._nonces
                if accepted:
                    self._nonces[replay_key] = timestamp
            if not accepted:
                raise DeviceAuthenticationError("service request nonce was replayed")
        return service_id


def generate_pairing_code() -> str:
    return "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(12))


def normalize_pairing_code(value: str) -> str:
    normalized = "".join(character for character in value.upper() if character not in " -")
    if len(normalized) != 12 or any(character not in _PAIRING_ALPHABET for character in normalized):
        raise ValueError("pairing code must contain 12 safe characters")
    return normalized


def encode_pairing_credential(code: str, expires_at: datetime) -> bytes:
    return HostPairingCredential(
        pairing_code=normalize_pairing_code(code),
        expires_at=expires_at,
    ).model_dump_json().encode("utf-8")


def decode_pairing_credential(value: bytes) -> HostPairingCredential:
    if not value or len(value) > 4096:
        raise PairingError("pairing credential is unavailable")
    try:
        return HostPairingCredential.model_validate_json(value)
    except ValueError as exc:
        raise PairingError("pairing credential is invalid") from exc


def announcement_proof(candidate: LANHostCandidate, request_nonce: str, code: str) -> str:
    normalized = normalize_pairing_code(code)
    value = json.dumps(
        {
            "request_nonce": request_nonce,
            "candidate": candidate.model_dump(mode="json"),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(normalized.encode("ascii"), value, hashlib.sha256).hexdigest()


def verify_announcement(
    announcement: LANDiscoveryAnnouncement,
    code: str,
) -> None:
    expected = announcement_proof(
        announcement.candidate,
        announcement.request_nonce,
        code,
    )
    if not hmac.compare_digest(expected, announcement.pairing_proof):
        raise PairingError("connection code does not authenticate the selected host")


@dataclass(slots=True)
class LANDiscoveryResponder:
    candidate: LANHostCandidate
    pairing_code_provider: Callable[[], str]
    bind_address: str = "0.0.0.0"
    port: int = LAN_DISCOVERY_PORT

    def serve(self, stop_event: Event) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transport:
            transport.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            transport.bind((self.bind_address, self.port))
            transport.settimeout(0.5)
            while not stop_event.is_set():
                try:
                    payload, address = transport.recvfrom(4096)
                except TimeoutError:
                    continue
                try:
                    request = json.loads(payload.decode("utf-8"))
                    if request.get("magic") != LAN_DISCOVERY_MAGIC:
                        continue
                    nonce = str(request["nonce"])
                    if len(nonce) != 32:
                        continue
                    response = LANDiscoveryAnnouncement(
                        request_nonce=nonce,
                        candidate=self.candidate,
                        pairing_proof=announcement_proof(
                            self.candidate,
                            nonce,
                            self.pairing_code_provider(),
                        ),
                    )
                    transport.sendto(
                        response.model_dump_json().encode("utf-8"),
                        address,
                    )
                except (KeyError, PairingError, PermissionError, TypeError, ValueError, UnicodeError):
                    continue


def discover_lan_hosts(
    *,
    timeout_seconds: float = 2.0,
    port: int = LAN_DISCOVERY_PORT,
    broadcast_address: str = "255.255.255.255",
) -> tuple[LANDiscoveryAnnouncement, ...]:
    nonce = secrets.token_hex(16)
    request = json.dumps(
        {"magic": LAN_DISCOVERY_MAGIC, "nonce": nonce},
        separators=(",", ":"),
    ).encode("utf-8")
    found: dict[str, LANDiscoveryAnnouncement] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transport:
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        transport.bind(("0.0.0.0", 0))
        transport.settimeout(0.2)
        transport.sendto(request, (broadcast_address, port))
        deadline = time.monotonic() + max(timeout_seconds, 0.1)
        while time.monotonic() < deadline:
            try:
                payload, _address = transport.recvfrom(65_535)
            except TimeoutError:
                continue
            try:
                announcement = LANDiscoveryAnnouncement.model_validate_json(payload)
            except ValueError:
                continue
            if announcement.request_nonce == nonce:
                found[announcement.candidate.host_id] = announcement
    return tuple(found[key] for key in sorted(found))


def certificate_sha256(pem: str) -> str:
    return hashlib.sha256(pem.encode("utf-8")).hexdigest()


def _request_canonical(
    agent_id: str,
    device_id: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body_sha256: str,
) -> bytes:
    if not path.startswith("/") or "\n" in path or "\r" in path:
        raise ValueError("signed request path is invalid")
    values = (
        agent_id,
        device_id,
        method.upper(),
        path,
        str(timestamp),
        nonce,
        body_sha256,
    )
    if any("\n" in value or "\r" in value for value in values):
        raise ValueError("signed request value is invalid")
    return "\n".join(values).encode("utf-8")


def _service_request_canonical(
    service_id: str,
    key_id: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body_sha256: str,
) -> bytes:
    if not path.startswith("/") or any(character in path for character in "\r\n"):
        raise ValueError("signed service request path is invalid")
    values = (
        service_id,
        key_id,
        method.upper(),
        path,
        str(timestamp),
        nonce,
        body_sha256,
    )
    if any("\n" in value or "\r" in value for value in values):
        raise ValueError("signed service request value is invalid")
    return "\n".join(values).encode("utf-8")


_EXECUTION_MODEL_NAMES = {
    "AgentCommandEnvelope",
    "AgentCommandPollResponse",
    "AgentReceiptAck",
    "AgentReceiptSubmission",
    "ServiceApprovalAck",
    "ServiceApprovalDelivery",
}


def __getattr__(name: str):
    """Load execution-only models only when a send-capable host imports them.

    This preserves the source API for Host Control while allowing the formal
    OBSERVE_ONLY Windows package to omit all execution and PDD-send modules.
    """

    if name in _EXECUTION_MODEL_NAMES:
        from . import execution_control

        return getattr(execution_control, name)
    raise AttributeError(name)


__all__ = [
    "AgentControlV2Error",
    "AgentAssistantEvent",
    "AgentAssistantEventPollResponse",
    "AgentAssistantSafetyFacts",
    "AgentAssistantSnapshot",
    "AgentAssistantConversationListResponse",
    "AgentAssistantSnapshotResponse",
    "AgentCommandEnvelope",
    "AgentCommandPollResponse",
    "AgentObservationAck",
    "AgentObservationSubmission",
    "AssistantEventType",
    "AgentReceiptAck",
    "AgentReceiptSubmission",
    "DeviceAuthenticationError",
    "DeviceRequestSigner",
    "DeviceRequestVerifier",
    "HostPairingCodeRotateRequest",
    "HostPairingCodeRotateResponse",
    "HostPairingCredential",
    "LANDiscoveryAnnouncement",
    "LANDiscoveryResponder",
    "LANHostCandidate",
    "LAN_DISCOVERY_PORT",
    "PairDeviceRequest",
    "PairDeviceResponse",
    "PairingError",
    "ReplayNonceStore",
    "ServiceApprovalAck",
    "ServiceApprovalDelivery",
    "ServiceRequestSigner",
    "ServiceRequestVerifier",
    "announcement_proof",
    "certificate_sha256",
    "decode_pairing_credential",
    "discover_lan_hosts",
    "encode_pairing_credential",
    "generate_pairing_code",
    "normalize_pairing_code",
    "verify_announcement",
]
