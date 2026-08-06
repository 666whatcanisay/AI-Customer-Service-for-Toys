from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import RLock
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from channel_engine.models.entities import new_id, utc_now

from .auth import GatewayRequestSigner
from .client import (
    AICSGatewayClient,
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    GatewayContractViolation,
    GatewayHealth,
    GatewayHealthStatus,
    GatewayRetryPolicy,
    GatewayTransport,
    GatewayTransportError,
    GatewayTransportResponse,
    GatewayTransportTimeout,
)
from .contract import (
    CONTRACT_VERSION,
    DecisionRequest,
    DecisionResponse,
    Event,
    ExecutionReceipt,
)
from .http import GatewayAdapterConfig, HttpGatewayTransport
from .mock_server import MockAICSServer, MockAICSServerTimeout, MockDecisionBehavior
from .protocol import GatewayUnavailable, IdempotencyConflict
from .sandbox import (
    GATEWAY_EVENT_PATH_PREFIX,
    GATEWAY_RECEIPT_PATH_PREFIX,
    GatewaySandboxStage,
    GatewaySandboxTraceStore,
    SandboxArtifactAck,
    SandboxGatewayArtifactServer,
    SandboxGatewayClient,
)


AI_CS_GATEWAY_INTEGRATION_VERSION = "1.0"


class GatewayServiceIdentity(BaseModel):
    """Non-secret service identity and opaque credential reference."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    client_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    key_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    credential_ref: str = Field(
        min_length=5,
        max_length=255,
        pattern=r"^[a-z][a-z0-9+.-]*://[^\s\r\n]+$",
    )

    @field_validator("credential_ref")
    @classmethod
    def reject_embedded_secret(cls, value: str) -> str:
        lowered = value.casefold()
        if any(
            marker in lowered
            for marker in (
                "secret=",
                "token=",
                "password=",
                "cookie=",
                "bearer%20",
            )
        ):
            raise ValueError("credential_ref contains embedded secret material")
        parsed = urlsplit(value)
        if (
            not parsed.scheme
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "credential_ref must be an opaque, query-free secret reference"
            )
        return value


class GatewayCredentialUnavailable(PermissionError):
    pass


class GatewaySigningToken:
    """Short-lived in-memory token; repr and string conversion never reveal bytes."""

    __slots__ = ("credential_ref", "key_id", "expires_at", "_material")

    def __init__(
        self,
        *,
        credential_ref: str,
        key_id: str,
        material: bytes,
        expires_at: datetime,
    ) -> None:
        if not isinstance(material, bytes) or len(material) < 32:
            raise ValueError("gateway signing material must contain at least 32 bytes")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("gateway signing token expiry must include timezone")
        self.credential_ref = credential_ref
        self.key_id = key_id
        self.expires_at = expires_at
        self._material = material

    def __repr__(self) -> str:
        return (
            "GatewaySigningToken(credential_ref="
            f"{self.credential_ref!r}, key_id={self.key_id!r}, "
            f"expires_at={self.expires_at!r}, material=<redacted>)"
        )

    __str__ = __repr__

    def _material_for_signing(self) -> bytes:
        return self._material


@runtime_checkable
class GatewayTokenProvider(Protocol):
    def acquire(self, identity: GatewayServiceIdentity) -> GatewaySigningToken:
        """Resolve a short-lived token from an opaque reference."""


class FakeGatewayTokenProvider:
    """Test-only provider. Production implementations belong in a secret backend."""

    def __init__(
        self,
        tokens: Mapping[str, tuple[str, bytes]],
        *,
        ttl: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("gateway token ttl must be positive")
        self._tokens = dict(tokens)
        self._ttl = ttl
        self._clock = clock
        self.acquire_count = 0

    def __repr__(self) -> str:
        return (
            "FakeGatewayTokenProvider(references="
            f"{tuple(sorted(self._tokens))!r}, material=<redacted>)"
        )

    def acquire(self, identity: GatewayServiceIdentity) -> GatewaySigningToken:
        registered = self._tokens.get(identity.credential_ref)
        if registered is None or registered[0] != identity.key_id:
            raise GatewayCredentialUnavailable(
                "gateway credential reference is unavailable"
            )
        self.acquire_count += 1
        now = _aware(self._clock())
        return GatewaySigningToken(
            credential_ref=identity.credential_ref,
            key_id=registered[0],
            material=registered[1],
            expires_at=now + self._ttl,
        )


class ProviderBackedGatewayAuthenticator:
    """GatewayRequestSigner-compatible facade that resolves keys per request."""

    def __init__(
        self,
        identity: GatewayServiceIdentity,
        provider: GatewayTokenProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(provider, GatewayTokenProvider):
            raise TypeError("provider does not implement GatewayTokenProvider")
        self.identity = identity
        self._provider = provider
        self._clock = clock
        self._nonce_factory = nonce_factory or (
            lambda: secrets.token_urlsafe(18).rstrip("=")
        )

    def sign(
        self,
        body: bytes,
        *,
        method: str,
        path: str,
        request_id: str,
        correlation_id: str,
        idempotency_key: str,
        content_type: str | None,
    ) -> dict[str, str]:
        signer = self._resolve_signer()
        return signer.sign(
            body,
            method=method,
            path=path,
            request_id=request_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            content_type=content_type,
        )

    def sign_decision(
        self,
        request: DecisionRequest,
        body: bytes,
        *,
        method: str,
        path: str,
        content_type: str = "application/json",
    ) -> dict[str, str]:
        return self.sign(
            body,
            method=method,
            path=path,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            content_type=content_type,
        )

    def sign_health(
        self,
        *,
        method: str,
        path: str,
        body: bytes = b"",
        request_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        identity = new_id("health")
        return self.sign(
            body,
            method=method,
            path=path,
            request_id=request_id or f"health-request-{identity}",
            correlation_id=correlation_id or f"health-correlation-{identity}",
            idempotency_key=idempotency_key or f"health-check-{identity}",
            content_type=None,
        )

    def _resolve_signer(self) -> GatewayRequestSigner:
        token = self._provider.acquire(self.identity)
        now = _aware(self._clock())
        if (
            token.credential_ref != self.identity.credential_ref
            or token.key_id != self.identity.key_id
        ):
            raise GatewayCredentialUnavailable(
                "gateway signing token does not match service identity"
            )
        if token.expires_at <= now:
            raise GatewayCredentialUnavailable("gateway signing token is expired")
        return GatewayRequestSigner(
            client_id=self.identity.client_id,
            key_id=self.identity.key_id,
            secret=token._material_for_signing(),
            clock=self._clock,
            nonce_factory=self._nonce_factory,
        )


class GatewayCircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True, slots=True)
class GatewayCircuitBreakerPolicy:
    failure_threshold: int = 3
    reset_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.failure_threshold <= 100:
            raise ValueError("circuit failure_threshold must be between 1 and 100")
        if self.reset_timeout_seconds <= 0:
            raise ValueError("circuit reset timeout must be positive")


class GatewayCircuitSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    state: GatewayCircuitState
    consecutive_failures: int = Field(ge=0)
    opened_at: AwareDatetime | None
    checked_at: AwareDatetime


class GatewayCircuitOpen(GatewayUnavailable):
    outcome_unknown = False


class GatewayCircuitBreaker:
    def __init__(
        self,
        policy: GatewayCircuitBreakerPolicy | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.policy = policy or GatewayCircuitBreakerPolicy()
        self._clock = clock
        self._state = GatewayCircuitState.CLOSED
        self._failures = 0
        self._opened_at: datetime | None = None
        self._lock = RLock()

    def before_call(self) -> None:
        with self._lock:
            now = _aware(self._clock())
            if self._state is GatewayCircuitState.OPEN:
                assert self._opened_at is not None
                elapsed = (now - self._opened_at).total_seconds()
                if elapsed < self.policy.reset_timeout_seconds:
                    raise GatewayCircuitOpen("AI-CS gateway circuit is open")
                self._state = GatewayCircuitState.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self._state = GatewayCircuitState.CLOSED
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if (
                self._state is GatewayCircuitState.HALF_OPEN
                or self._failures >= self.policy.failure_threshold
            ):
                self._state = GatewayCircuitState.OPEN
                self._opened_at = _aware(self._clock())

    def snapshot(self) -> GatewayCircuitSnapshot:
        with self._lock:
            return GatewayCircuitSnapshot(
                state=self._state,
                consecutive_failures=self._failures,
                opened_at=self._opened_at,
                checked_at=_aware(self._clock()),
            )


class GatewayArtifactOutcomeUnknown(GatewayUnavailable):
    def __init__(self, artifact_id: str, attempts: int) -> None:
        super().__init__(
            f"gateway artifact acceptance is unknown after {attempts} attempts"
        )
        self.artifact_id = artifact_id
        self.attempts = attempts
        self.outcome_unknown = True


@runtime_checkable
class GatewayClientInterface(Protocol):
    def request_decision(self, request: DecisionRequest) -> DecisionResponse: ...

    def publish_event(self, event: Event) -> SandboxArtifactAck: ...

    def send_execution_result(
        self, receipt: ExecutionReceipt
    ) -> SandboxArtifactAck: ...

    def health_check(self) -> GatewayHealth: ...


class GatewayClient:
    """Real-ready Contract V1 client; transport and token provider are injected."""

    contract_version = CONTRACT_VERSION

    def __init__(
        self,
        transport: GatewayTransport,
        identity: GatewayServiceIdentity,
        token_provider: GatewayTokenProvider,
        *,
        decision_retry_policy: GatewayRetryPolicy | None = None,
        artifact_retry_policy: GatewayRetryPolicy | None = None,
        circuit_breaker: GatewayCircuitBreaker | None = None,
        timeout_seconds: float = 15.0,
        trace_store: GatewaySandboxTraceStore | None = None,
        clock: Callable[[], datetime] = utc_now,
        nonce_factory: Callable[[], str] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(transport, GatewayTransport):
            raise TypeError("transport does not implement GatewayTransport")
        self.identity = identity
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._artifact_retry = artifact_retry_policy or GatewayRetryPolicy()
        self.circuit_breaker = circuit_breaker or GatewayCircuitBreaker(clock=clock)
        self.authenticator = ProviderBackedGatewayAuthenticator(
            identity,
            token_provider,
            clock=clock,
            nonce_factory=nonce_factory,
        )
        self.trace_store = trace_store or GatewaySandboxTraceStore(clock=clock)
        decision_client = AICSGatewayClient(
            transport,
            self.authenticator,  # compatible signing facade
            retry_policy=decision_retry_policy,
            timeout_seconds=timeout_seconds,
            sleeper=sleeper,
        )
        self._contract_client = SandboxGatewayClient(
            decision_client,
            transport,
            self.authenticator,  # compatible signing facade
            trace_store=self.trace_store,
        )
        self._http_transport: HttpGatewayTransport | None = None

    @classmethod
    def from_http(
        cls,
        config: GatewayAdapterConfig,
        identity: GatewayServiceIdentity,
        token_provider: GatewayTokenProvider,
        **kwargs,
    ) -> GatewayClient:
        if config.client_id != identity.client_id or config.key_id != identity.key_id:
            raise ValueError("gateway HTTP config and service identity disagree")
        transport = HttpGatewayTransport(config)
        client = cls(
            transport,
            identity,
            token_provider,
            timeout_seconds=config.timeout_seconds,
            **kwargs,
        )
        client._http_transport = transport
        return client

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        return self.request_decision(request)

    def request_decision(self, request: DecisionRequest) -> DecisionResponse:
        try:
            self.circuit_breaker.before_call()
        except GatewayCircuitOpen:
            self.trace_store.record(
                stage=GatewaySandboxStage.GATEWAY_FAILED,
                correlation_id=request.correlation_id,
                message_id=request.message_id,
                request_id=request.request_id,
                error_code="GATEWAY_CIRCUIT_OPEN",
            )
            raise
        try:
            response = self._contract_client.request_decision(request)
        except GatewayCredentialUnavailable:
            self.trace_store.record(
                stage=GatewaySandboxStage.GATEWAY_FAILED,
                correlation_id=request.correlation_id,
                message_id=request.message_id,
                request_id=request.request_id,
                error_code="GATEWAY_CREDENTIAL_UNAVAILABLE",
            )
            self.circuit_breaker.record_failure()
            raise
        except (
            AICSGatewayTimeout,
            AICSGatewayRequestFailed,
            GatewayContractViolation,
            GatewayUnavailable,
        ):
            self.circuit_breaker.record_failure()
            raise
        except IdempotencyConflict:
            raise
        self.circuit_breaker.record_success()
        return response

    def publish_event(self, event: Event) -> SandboxArtifactAck:
        return self._publish_with_retry(
            event.event_id,
            lambda: self._contract_client.publish_event(event),
        )

    def publish_execution_event(self, event: Event) -> SandboxArtifactAck:
        return self._publish_with_retry(
            event.event_id,
            lambda: self._contract_client.publish_execution_event(event),
        )

    def send_execution_result(
        self, receipt: ExecutionReceipt
    ) -> SandboxArtifactAck:
        return self._publish_with_retry(
            receipt.receipt_id,
            lambda: self._contract_client.send_execution_result(receipt),
        )

    def publish_execution_receipt(
        self, receipt: ExecutionReceipt
    ) -> SandboxArtifactAck:
        return self.send_execution_result(receipt)

    def health_check(self) -> GatewayHealth:
        if self.circuit_breaker.snapshot().state is GatewayCircuitState.OPEN:
            return GatewayHealth(
                status=GatewayHealthStatus.UNHEALTHY,
                service="ai-cs-gateway",
                contract_version=CONTRACT_VERSION,
                version=None,
                capabilities=(),
                reachable=False,
                real_ai_cs_connected=False,
                timestamp=_aware(self._clock()),
                details={"failure_type": "GatewayCircuitOpen"},
            )
        return self._contract_client.health_check()

    def close(self) -> None:
        if self._http_transport is not None:
            self._http_transport.close()

    def __enter__(self) -> GatewayClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _publish_with_retry(
        self,
        artifact_id: str,
        operation: Callable[[], SandboxArtifactAck],
    ) -> SandboxArtifactAck:
        self.circuit_breaker.before_call()
        policy = self._artifact_retry
        for attempt in range(1, policy.max_attempts + 1):
            try:
                result = operation()
            except AICSGatewayRequestFailed as exc:
                if exc.envelope.error.retryable and attempt < policy.max_attempts:
                    self._backoff(attempt, exc.envelope.error.retry_after_seconds)
                    continue
                self.circuit_breaker.record_failure()
                raise
            except GatewayUnavailable as exc:
                if attempt < policy.max_attempts:
                    self._backoff(attempt, None)
                    continue
                self.circuit_breaker.record_failure()
                raise GatewayArtifactOutcomeUnknown(artifact_id, attempt) from exc
            except (GatewayContractViolation, GatewayCredentialUnavailable):
                self.circuit_breaker.record_failure()
                raise
            self.circuit_breaker.record_success()
            return result
        raise AssertionError("artifact retry loop exited unexpectedly")

    def _backoff(self, attempt: int, retry_after: int | None) -> None:
        if retry_after is not None:
            delay = min(float(retry_after), self._artifact_retry.max_backoff_seconds)
        else:
            delay = min(
                self._artifact_retry.base_backoff_seconds * (2 ** (attempt - 1)),
                self._artifact_retry.max_backoff_seconds,
            )
        self._sleeper(delay)


class MockAICSGatewayCompatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"


class MockAICSGateway:
    """Unified in-process mock for health, Decision, Event and Receipt routes."""

    def __init__(
        self,
        credentials: Mapping[tuple[str, str], bytes],
        *,
        decision_behavior: MockDecisionBehavior | None = None,
        compatibility: MockAICSGatewayCompatibility = (
            MockAICSGatewayCompatibility.COMPATIBLE
        ),
        clock: Callable[[], datetime] = utc_now,
        healthy: bool = True,
    ) -> None:
        self.decision_server = MockAICSServer(
            credentials,
            default_behavior=decision_behavior,
            clock=clock,
            healthy=healthy,
        )
        self.artifact_server = SandboxGatewayArtifactServer(
            credentials,
            clock=clock,
        )
        self.compatibility = compatibility

    def handle_request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        if path.startswith((GATEWAY_EVENT_PATH_PREFIX, GATEWAY_RECEIPT_PATH_PREFIX)):
            response = self.artifact_server.handle_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
            )
        else:
            response = self.decision_server.handle_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
            )
        if (
            self.compatibility is MockAICSGatewayCompatibility.INCOMPATIBLE_VERSION
            and response.status_code == 200
        ):
            payload = json.loads(response.body or b"{}")
            if isinstance(payload, dict) and "contract_version" in payload:
                payload["contract_version"] = "2.0"
            response_headers = dict(response.headers)
            response_headers["X-AI-CS-Contract-Version"] = "2.0"
            return GatewayTransportResponse(
                status_code=response.status_code,
                body=json.dumps(payload, separators=(",", ":")).encode(),
                headers=response_headers,
            )
        return response


class MockAICSGatewayTransport:
    def __init__(self, server: MockAICSGateway, *, unavailable: bool = False) -> None:
        self.server = server
        self.unavailable = unavailable
        self.attempt_count = 0

    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        if self.unavailable:
            raise GatewayTransportError("mock integrated AI-CS gateway is unavailable")
        if timeout_seconds <= 0:
            raise ValueError("gateway timeout must be positive")
        self.attempt_count += 1
        try:
            return self.server.handle_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
            )
        except MockAICSServerTimeout as exc:
            raise GatewayTransportTimeout("mock integrated AI-CS timed out") from exc


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


__all__ = [
    "AI_CS_GATEWAY_INTEGRATION_VERSION",
    "FakeGatewayTokenProvider",
    "GatewayArtifactOutcomeUnknown",
    "GatewayCircuitBreaker",
    "GatewayCircuitBreakerPolicy",
    "GatewayCircuitOpen",
    "GatewayCircuitSnapshot",
    "GatewayCircuitState",
    "GatewayClient",
    "GatewayClientInterface",
    "GatewayCredentialUnavailable",
    "GatewayServiceIdentity",
    "GatewaySigningToken",
    "GatewayTokenProvider",
    "MockAICSGateway",
    "MockAICSGatewayCompatibility",
    "MockAICSGatewayTransport",
    "ProviderBackedGatewayAuthenticator",
]
