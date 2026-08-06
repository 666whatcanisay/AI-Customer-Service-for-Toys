from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from channel_engine.browser.models import (
    BrowserLoginState,
    BrowserSessionState,
)
from channel_engine.browser.selectors import (
    LocatorEngine,
    SelectorContract,
    SelectorContractState,
    SelectorKey,
    draft_pdd_merchant_chat_v1,
)
from channel_engine.models.entities import new_id, utc_now
from channel_engine.session.models import ChannelSessionStatus

from .adapter_foundation import ChannelMessageV1
from .protocol import AdapterHealth, AdapterHealthStatus


PDD_DISCOVERY_FRAMEWORK_VERSION = "1.0"


class PDDDiscoveryModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    discovery_framework_version: Literal["1.0"] = PDD_DISCOVERY_FRAMEWORK_VERSION


class PDDDiscoveryLifecycle(StrEnum):
    READY = "READY"
    OBSERVING = "OBSERVING"
    DEGRADED = "DEGRADED"


class SelectorCandidateConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PDDDiscoverySafetyViolation(ValueError):
    pass


class PDDDiscoveryUnavailable(RuntimeError):
    pass


def _safe_page_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("page URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("page URL cannot contain credentials, query, or fragment")
    if len(value) > 512:
        raise ValueError("page URL is too long")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _safe_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https", "ws", "wss"}
        or parsed.hostname is None
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("network origin must not contain path or secret material")
    return f"{parsed.scheme}://{parsed.netloc}"


class PDDDOMMetadata(PDDDiscoveryModel):
    element_count: int = Field(ge=0)
    iframe_count: int = Field(ge=0)
    shadow_root_count: int = Field(ge=0)
    text_node_count: int = Field(ge=0)
    attribute_names: tuple[str, ...] = Field(max_length=128)
    dom_revision_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("attribute_names")
    @classmethod
    def validate_attribute_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("DOM attribute names must be unique")
        for name in value:
            if not name or len(name) > 80 or not all(
                character.isalnum() or character in {"-", "_", ":"}
                for character in name
            ):
                raise ValueError("DOM metadata contains an invalid attribute name")
        return value


class PDDSelectorCandidate(PDDDiscoveryModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    logical_key: SelectorKey
    engine_hint: LocatorEngine
    structural_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_match_count: int = Field(ge=0)
    confidence: SelectorCandidateConfidence

    @model_validator(mode="after")
    def reject_write_selectors(self) -> PDDSelectorCandidate:
        if self.logical_key in {
            SelectorKey.COMPOSER,
            SelectorKey.SEND_CONTROL,
            SelectorKey.SEND_CONFIRMATION,
        }:
            raise ValueError("observe-only discovery rejects write selector candidates")
        return self


class PDDScreenshotMetadata(PDDDiscoveryModel):
    captured: bool
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)
    image_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    redaction_applied: bool
    bytes_retained: Literal[False] = False

    @model_validator(mode="after")
    def validate_capture(self) -> PDDScreenshotMetadata:
        values = (self.width, self.height, self.image_digest)
        if self.captured:
            if any(item is None for item in values) or not self.redaction_applied:
                raise ValueError(
                    "captured screenshot metadata requires dimensions, digest, and redaction"
                )
        elif any(item is not None for item in values):
            raise ValueError("uncaptured screenshot cannot carry image metadata")
        return self


class PDDNetworkMetadata(PDDDiscoveryModel):
    request_count: int = Field(ge=0)
    websocket_upgrade_count: int = Field(ge=0)
    origins: tuple[str, ...] = Field(max_length=32)
    methods: tuple[str, ...] = Field(max_length=16)
    resource_types: tuple[str, ...] = Field(max_length=32)
    response_status_classes: dict[str, int] = Field(default_factory=dict)
    headers_captured: Literal[False] = False
    bodies_captured: Literal[False] = False
    cookies_captured: Literal[False] = False

    @field_validator("origins")
    @classmethod
    def validate_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        sanitized = tuple(_safe_origin(item) for item in value)
        if len(sanitized) != len(set(sanitized)):
            raise ValueError("network origins must be unique")
        return sanitized

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
        if len(value) != len(set(value)) or any(item not in allowed for item in value):
            raise ValueError("network methods must be unique standard HTTP methods")
        return value

    @field_validator("resource_types")
    @classmethod
    def validate_resource_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("network resource types must be unique")
        for item in value:
            if not item or len(item) > 64 or not item.replace("_", "").isalnum():
                raise ValueError("invalid network resource type")
        return value

    @field_validator("response_status_classes")
    @classmethod
    def validate_status_classes(cls, value: dict[str, int]) -> dict[str, int]:
        if any(key not in {"1xx", "2xx", "3xx", "4xx", "5xx"} for key in value):
            raise ValueError("network response metadata only accepts status classes")
        if any(count < 0 for count in value.values()):
            raise ValueError("network response counts cannot be negative")
        return value


class PDDDiscoverySessionMetadata(PDDDiscoveryModel):
    browser_session_id: str = Field(min_length=1, max_length=128)
    page_context_id: str | None = Field(default=None, max_length=128)
    browser_generation: int = Field(ge=0)
    browser_state: BrowserSessionState
    login_state: BrowserLoginState
    channel_session_state: ChannelSessionStatus
    page_available: bool
    automatic_login_performed: Literal[False] = False
    credential_material_captured: Literal[False] = False
    write_capability_enabled: Literal[False] = False


class PDDMessageCandidateMetadata(PDDDiscoveryModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    message_identity_digest: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    conversation_identity_digest: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    sender_category: Literal["customer", "merchant", "system", "unknown"]
    content_present: bool
    content_length: int = Field(ge=0, le=8_000)
    timestamp_present: bool
    timestamp_timezone_aware: bool
    synthetic_test_data: bool

    @model_validator(mode="after")
    def validate_content(self) -> PDDMessageCandidateMetadata:
        if self.content_present != (self.content_length > 0):
            raise ValueError("message content presence and length disagree")
        return self


class PDDPageMetadata(PDDDiscoveryModel):
    page_url: str
    page_title: Literal["[REDACTED]"] = "[REDACTED]"
    page_title_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_title_length: int = Field(ge=0, le=512)
    page_revision_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("page_url")
    @classmethod
    def validate_page_url(cls, value: str) -> str:
        return _safe_page_url(value)


class PDDDiscoveryCapture(PDDDiscoveryModel):
    capture_id: str = Field(min_length=1, max_length=128)
    page: PDDPageMetadata
    dom: PDDDOMMetadata
    selector_candidates: tuple[PDDSelectorCandidate, ...] = Field(max_length=128)
    screenshot: PDDScreenshotMetadata
    network: PDDNetworkMetadata
    session: PDDDiscoverySessionMetadata
    message_candidates: tuple[PDDMessageCandidateMetadata, ...] = Field(max_length=100)
    captured_at: AwareDatetime


class PDDDiscoveryPortHealth(PDDDiscoveryModel):
    healthy: bool
    page_available: bool
    reason_code: str = Field(min_length=3, max_length=128)
    checked_at: AwareDatetime
    real_platform_connected: Literal[False] = False


@runtime_checkable
class PDDDiscoveryObservationPort(Protocol):
    """Read-only browser metadata port; it has no navigation or action method."""

    @property
    def port_name(self) -> str: ...

    def capture_metadata(self) -> PDDDiscoveryCapture: ...

    def health_check(self) -> PDDDiscoveryPortHealth: ...


class PDDDiscoveryObservation(PDDDiscoveryModel):
    observation_id: str = Field(min_length=1, max_length=128)
    capture: PDDDiscoveryCapture
    selector_contract: SelectorContract
    mapping_contract_state: Literal[SelectorContractState.DRAFT] = (
        SelectorContractState.DRAFT
    )
    runtime_delivery_enabled: Literal[False] = False
    send_enabled: Literal[False] = False
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def enforce_draft_only(self) -> PDDDiscoveryObservation:
        contract = self.selector_contract
        if (
            contract.state is not SelectorContractState.DRAFT
            or contract.bindings
            or contract.capabilities
            or contract.verified_at is not None
        ):
            raise ValueError("discovery observation requires an identity-only DRAFT")
        return self


@runtime_checkable
class PDDDiscoveryObservationStore(Protocol):
    def append(self, observation: PDDDiscoveryObservation) -> None: ...

    def list_observations(self) -> tuple[PDDDiscoveryObservation, ...]: ...


class InMemoryPDDDiscoveryObservationStore:
    def __init__(self) -> None:
        self._items: list[PDDDiscoveryObservation] = []
        self._ids: set[str] = set()
        self._lock = RLock()

    def append(self, observation: PDDDiscoveryObservation) -> None:
        with self._lock:
            if observation.observation_id in self._ids:
                existing = next(
                    item
                    for item in self._items
                    if item.observation_id == observation.observation_id
                )
                if existing != observation:
                    raise ValueError("discovery observation id conflict")
                return
            self._ids.add(observation.observation_id)
            self._items.append(observation)

    def list_observations(self) -> tuple[PDDDiscoveryObservation, ...]:
        with self._lock:
            return tuple(self._items)


class SyntheticPDDMessageEvidence(PDDDiscoveryModel):
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["customer"] = "customer"
    content: str = Field(min_length=1, max_length=8_000)
    timestamp: AwareDatetime
    synthetic_test_data: Literal[True] = True


class PDDMessageMappingPreview(PDDDiscoveryModel):
    mapping_contract_id: Literal["pdd:merchant_chat:message:v1"] = (
        "pdd:merchant_chat:message:v1"
    )
    mapping_contract_state: Literal[SelectorContractState.DRAFT] = (
        SelectorContractState.DRAFT
    )
    message: ChannelMessageV1
    blockers: tuple[str, ...]
    runtime_eligible: Literal[False] = False


class PDDDiscoveryMessageMapper:
    """Maps synthetic evidence for schema preview; never emits runtime delivery."""

    def preview(self, evidence: SyntheticPDDMessageEvidence) -> PDDMessageMappingPreview:
        if evidence.synthetic_test_data is not True:
            raise PDDDiscoverySafetyViolation(
                "discovery message mapping accepts synthetic test evidence only"
            )
        return PDDMessageMappingPreview(
            message=ChannelMessageV1(
                message_id=evidence.message_id,
                channel="pdd",
                store_id=evidence.store_id,
                conversation_id=evidence.conversation_id,
                sender=evidence.sender,
                content=evidence.content,
                timestamp=evidence.timestamp,
            ),
            blockers=(
                "DISCOVERY_OBSERVE_ONLY",
                "SELECTOR_CONTRACT_DRAFT",
                "MAPPING_CONTRACT_DRAFT",
            ),
        )


class PDDDiscoveryAdapter:
    """Observe-only composition root with no send, click, or login surface."""

    channel = "pdd"
    adapter_name = "PDDDiscoveryAdapterV1"

    def __init__(
        self,
        observation_port: PDDDiscoveryObservationPort,
        *,
        store: PDDDiscoveryObservationStore | None = None,
        mapper: PDDDiscoveryMessageMapper | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not isinstance(observation_port, PDDDiscoveryObservationPort):
            raise TypeError("observation port does not implement the read-only contract")
        self.observation_port = observation_port
        self.store = store or InMemoryPDDDiscoveryObservationStore()
        self.mapper = mapper or PDDDiscoveryMessageMapper()
        self._clock = clock
        self._state = PDDDiscoveryLifecycle.READY
        self._lock = RLock()
        self.observation_count = 0
        self.last_error_code: str | None = None

    @property
    def lifecycle_state(self) -> PDDDiscoveryLifecycle:
        with self._lock:
            return self._state

    def capture_metadata(self) -> PDDDiscoveryCapture:
        with self._lock:
            if self._state is PDDDiscoveryLifecycle.OBSERVING:
                raise PDDDiscoveryUnavailable("discovery capture is already running")
            self._state = PDDDiscoveryLifecycle.OBSERVING
        try:
            capture = self.observation_port.capture_metadata()
        except Exception as exc:
            with self._lock:
                self._state = PDDDiscoveryLifecycle.DEGRADED
                self.last_error_code = "PDD_DISCOVERY_CAPTURE_FAILED"
            raise PDDDiscoveryUnavailable("PDD discovery capture failed") from exc
        with self._lock:
            self._state = PDDDiscoveryLifecycle.READY
            self.last_error_code = None
        return capture

    def observe_only(self) -> PDDDiscoveryObservation:
        capture = self.capture_metadata()
        observation = PDDDiscoveryObservation(
            observation_id=new_id("pdd-discovery-observation"),
            capture=capture,
            selector_contract=draft_pdd_merchant_chat_v1(),
            observed_at=capture.captured_at,
        )
        self.store.append(observation)
        with self._lock:
            self.observation_count += 1
        return observation

    def preview_message_mapping(
        self, evidence: SyntheticPDDMessageEvidence
    ) -> PDDMessageMappingPreview:
        return self.mapper.preview(evidence)

    def health_check(self) -> AdapterHealth:
        try:
            port_health = self.observation_port.health_check()
            health = (
                AdapterHealthStatus.HEALTHY
                if port_health.healthy and port_health.page_available
                else AdapterHealthStatus.DEGRADED
            )
            reason_code = port_health.reason_code
            if (
                health is AdapterHealthStatus.HEALTHY
                and self.lifecycle_state is PDDDiscoveryLifecycle.DEGRADED
            ):
                health = AdapterHealthStatus.DEGRADED
                reason_code = self.last_error_code or "PDD_DISCOVERY_DEGRADED"
        except Exception as exc:
            health = AdapterHealthStatus.UNHEALTHY
            reason_code = f"PDD_DISCOVERY_HEALTH_{type(exc).__name__.upper()}"
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=health,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "mode": "DISCOVERY_OBSERVE_ONLY",
                "port": self.observation_port.port_name,
                "lifecycle": self.lifecycle_state.value,
                "reason_code": reason_code,
                "selector_contract_state": SelectorContractState.DRAFT.value,
                "mapping_contract_state": SelectorContractState.DRAFT.value,
                "observation_count": self.observation_count,
                "runtime_delivery_enabled": False,
                "send_enabled": False,
                "reply_enabled": False,
                "click_enabled": False,
                "automatic_login_enabled": False,
                "real_platform_connected": False,
            },
        )


class FakePDDDiscoveryObservationPort:
    """Metadata-only fake port. It has no browser control or write API."""

    port_name = "fake-pdd-discovery-observation-port.v1"

    def __init__(
        self,
        captures: tuple[PDDDiscoveryCapture, ...],
        *,
        healthy: bool = True,
        page_available: bool = True,
        capture_unavailable: bool = False,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._captures = deque(captures)
        self.healthy = healthy
        self.page_available = page_available
        self.capture_unavailable = capture_unavailable
        self._clock = clock
        self.capture_count = 0
        self.health_count = 0
        self.write_action_count = 0
        self.real_platform_call_count = 0

    def capture_metadata(self) -> PDDDiscoveryCapture:
        self.capture_count += 1
        if self.capture_unavailable or not self._captures:
            raise PDDDiscoveryUnavailable("fake discovery capture unavailable")
        return self._captures.popleft()

    def health_check(self) -> PDDDiscoveryPortHealth:
        self.health_count += 1
        return PDDDiscoveryPortHealth(
            healthy=self.healthy,
            page_available=self.page_available,
            reason_code=(
                "PDD_DISCOVERY_PORT_HEALTHY"
                if self.healthy and self.page_available
                else "PDD_DISCOVERY_PORT_DEGRADED"
            ),
            checked_at=self._clock(),
        )


__all__ = [
    "PDD_DISCOVERY_FRAMEWORK_VERSION",
    "FakePDDDiscoveryObservationPort",
    "InMemoryPDDDiscoveryObservationStore",
    "PDDDOMMetadata",
    "PDDDiscoveryAdapter",
    "PDDDiscoveryCapture",
    "PDDDiscoveryLifecycle",
    "PDDDiscoveryMessageMapper",
    "PDDDiscoveryModel",
    "PDDDiscoveryObservation",
    "PDDDiscoveryObservationPort",
    "PDDDiscoveryObservationStore",
    "PDDDiscoveryPortHealth",
    "PDDDiscoverySafetyViolation",
    "PDDDiscoverySessionMetadata",
    "PDDDiscoveryUnavailable",
    "PDDMessageCandidateMetadata",
    "PDDMessageMappingPreview",
    "PDDNetworkMetadata",
    "PDDPageMetadata",
    "PDDScreenshotMetadata",
    "PDDSelectorCandidate",
    "SelectorCandidateConfidence",
    "SyntheticPDDMessageEvidence",
]
