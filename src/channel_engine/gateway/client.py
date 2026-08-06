from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pydantic import (
    ValidationError,
)

from channel_engine.models.entities import utc_now

from .auth import GatewayRequestSigner
from .contract import (
    CONTRACT_VERSION,
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    GatewayErrorCode,
    GatewayHealth,
    GatewayHealthStatus,
)
from .protocol import GatewayUnavailable, IdempotencyConflict


DECISION_PATH = "/gateway/v1/decisions"
HEALTH_PATH = "/gateway/v1/health"
GATEWAY_MEDIA_TYPE = "application/vnd.ai-cs.channel-engine.gateway-v1+json"
DECISION_TIMEOUT_SECONDS = 15.0

_ERROR_STATUS_BY_CODE = {
    GatewayErrorCode.INVALID_REQUEST: 400,
    GatewayErrorCode.AUTHENTICATION_REQUIRED: 401,
    GatewayErrorCode.AUTHENTICATION_FAILED: 401,
    GatewayErrorCode.AUTHORIZATION_DENIED: 403,
    GatewayErrorCode.RESOURCE_NOT_FOUND: 404,
    GatewayErrorCode.METHOD_NOT_ALLOWED: 405,
    GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION: 406,
    GatewayErrorCode.IDEMPOTENCY_IN_PROGRESS: 409,
    GatewayErrorCode.IDEMPOTENCY_CONFLICT: 409,
    GatewayErrorCode.PAYLOAD_TOO_LARGE: 413,
    GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    GatewayErrorCode.SCHEMA_VALIDATION_FAILED: 422,
    GatewayErrorCode.RATE_LIMITED: 429,
    GatewayErrorCode.INTERNAL_ERROR: 500,
    GatewayErrorCode.SERVICE_UNAVAILABLE: 503,
    GatewayErrorCode.DEADLINE_EXCEEDED: 504,
}


def canonical_gateway_body(request: DecisionRequest) -> bytes:
    payload = request.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class GatewayTransportResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str]

    def __post_init__(self) -> None:
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be a valid HTTP status")
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@runtime_checkable
class GatewayTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> GatewayTransportResponse:
        """Perform one transport attempt without changing the business payload."""


class GatewayTransportError(RuntimeError):
    pass


class GatewayTransportTimeout(GatewayTransportError):
    pass


class GatewayContractViolation(RuntimeError):
    pass


class AICSGatewayTimeout(GatewayUnavailable):
    def __init__(self, attempts: int) -> None:
        super().__init__(
            f"AI-CS decision outcome is unknown after {attempts} timed-out attempts"
        )
        self.attempts = attempts
        self.outcome_unknown = True


class AICSGatewayRequestFailed(RuntimeError):
    def __init__(
        self,
        status_code: int,
        envelope: ErrorEnvelope,
        attempts: int,
    ) -> None:
        super().__init__(
            f"AI-CS gateway rejected the request with {envelope.error.code.value}"
        )
        self.status_code = status_code
        self.envelope = envelope
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class GatewayRetryPolicy:
    max_attempts: int = 3
    base_backoff_seconds: float = 0.05
    max_backoff_seconds: float = 1.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("Gateway Contract V1 permits 1 to 3 transport attempts")
        if self.base_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("gateway backoff values cannot be negative")
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ValueError("max_backoff_seconds cannot be below base_backoff_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


class AICSGatewayClient:
    """Contract-validating AI-CS client with no built-in network transport."""

    def __init__(
        self,
        transport: GatewayTransport,
        signer: GatewayRequestSigner,
        *,
        retry_policy: GatewayRetryPolicy | None = None,
        timeout_seconds: float = DECISION_TIMEOUT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("gateway timeout_seconds must be positive")
        if not isinstance(transport, GatewayTransport):
            raise TypeError("transport does not implement GatewayTransport")
        self._transport = transport
        self._signer = signer
        self._retry_policy = retry_policy or GatewayRetryPolicy()
        self._timeout_seconds = timeout_seconds
        self._sleeper = sleeper
        self._random_source = random_source
        self._responses: dict[str, tuple[str, DecisionResponse]] = {}
        self._lock = Lock()
        self.request_attempt_count = 0
        self.retry_count = 0
        self.cache_replay_count = 0

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        return self.request_decision(request)

    def request_decision(self, request: DecisionRequest) -> DecisionResponse:
        try:
            body = canonical_gateway_body(request)
            validated_request = DecisionRequest.model_validate_json(body)
        except (TypeError, ValueError, ValidationError) as exc:
            raise GatewayContractViolation("DecisionRequest failed Contract V1") from exc
        fingerprint = hashlib.sha256(body).hexdigest()
        with self._lock:
            cached = self._responses.get(validated_request.idempotency_key)
            if cached is not None:
                original_fingerprint, original_response = cached
                if not original_fingerprint == fingerprint:
                    raise IdempotencyConflict(
                        "idempotency key was reused with a different DecisionRequest"
                    )
                self.cache_replay_count += 1
                return original_response

        response = self._request_with_retry(validated_request, body)
        with self._lock:
            existing = self._responses.get(validated_request.idempotency_key)
            if existing is not None and existing[0] != fingerprint:
                raise IdempotencyConflict(
                    "idempotency key was reused with a different DecisionRequest"
                )
            self._responses[validated_request.idempotency_key] = (
                fingerprint,
                response,
            )
        return response

    def health_check(self) -> GatewayHealth:
        try:
            body = b""
            headers = self._signer.sign_health(
                method="GET",
                path=HEALTH_PATH,
                body=body,
            )
            headers["Accept"] = GATEWAY_MEDIA_TYPE
            response = self._transport.request(
                method="GET",
                path=HEALTH_PATH,
                body=body,
                headers=headers,
                timeout_seconds=min(self._timeout_seconds, 5.0),
            )
            if response.status_code != 200:
                raise GatewayContractViolation("gateway health returned non-200")
            normalized_headers = {
                name.lower(): value for name, value in response.headers.items()
            }
            expected_headers = {
                "x-ai-cs-contract-version": CONTRACT_VERSION,
                "x-request-id": headers["X-Request-ID"],
                "x-correlation-id": headers["X-Correlation-ID"],
            }
            if any(
                normalized_headers.get(name) != value
                for name, value in expected_headers.items()
            ):
                raise GatewayContractViolation(
                    "gateway health headers do not match request"
                )
            health = GatewayHealth.model_validate_json(response.body)
            if health.contract_version != CONTRACT_VERSION:
                raise GatewayContractViolation("gateway health version mismatch")
            return health
        except (GatewayTransportError, GatewayContractViolation, ValidationError) as exc:
            return GatewayHealth(
                status=GatewayHealthStatus.UNHEALTHY,
                service="ai-cs-gateway",
                contract_version=CONTRACT_VERSION,
                version=None,
                capabilities=(),
                reachable=False,
                real_ai_cs_connected=False,
                timestamp=utc_now(),
                details={"failure_type": type(exc).__name__},
            )

    def _request_with_retry(
        self,
        request: DecisionRequest,
        body: bytes,
    ) -> DecisionResponse:
        policy = self._retry_policy
        for attempt in range(1, policy.max_attempts + 1):
            headers = self._signer.sign_decision(
                request,
                body,
                method="POST",
                path=DECISION_PATH,
                content_type=GATEWAY_MEDIA_TYPE,
            )
            headers["Accept"] = GATEWAY_MEDIA_TYPE
            with self._lock:
                self.request_attempt_count += 1
            try:
                transport_response = self._transport.request(
                    method="POST",
                    path=DECISION_PATH,
                    body=body,
                    headers=headers,
                    timeout_seconds=self._timeout_seconds,
                )
            except GatewayTransportTimeout as exc:
                if attempt == policy.max_attempts:
                    raise AICSGatewayTimeout(attempt) from exc
                self._backoff(attempt, None)
                continue
            except GatewayTransportError as exc:
                if attempt == policy.max_attempts:
                    raise GatewayUnavailable(
                        f"AI-CS gateway unavailable after {attempt} attempts"
                    ) from exc
                self._backoff(attempt, None)
                continue

            if transport_response.status_code == 200:
                return self._validate_success(request, transport_response)

            envelope = self._validate_error(request, transport_response)
            if envelope.error.retryable and attempt < policy.max_attempts:
                self._backoff(attempt, envelope.error.retry_after_seconds)
                continue
            raise AICSGatewayRequestFailed(
                transport_response.status_code,
                envelope,
                attempt,
            )
        raise AssertionError("gateway retry loop exited unexpectedly")

    def _validate_success(
        self,
        request: DecisionRequest,
        transport_response: GatewayTransportResponse,
    ) -> DecisionResponse:
        headers = {
            name.lower(): value for name, value in transport_response.headers.items()
        }
        expected_headers = {
            "x-ai-cs-contract-version": CONTRACT_VERSION,
            "x-request-id": request.request_id,
            "x-correlation-id": request.correlation_id,
        }
        if any(headers.get(name) != value for name, value in expected_headers.items()):
            raise GatewayContractViolation("gateway success headers do not match request")
        if headers.get("idempotency-replayed") not in {"true", "false"}:
            raise GatewayContractViolation("gateway replay header is invalid")
        try:
            response = DecisionResponse.model_validate_json(transport_response.body)
        except ValidationError as exc:
            raise GatewayContractViolation(
                "DecisionResponse failed Gateway Contract V1"
            ) from exc
        if (
            response.request_id != request.request_id
            or response.idempotency_key != request.idempotency_key
            or response.correlation_id != request.correlation_id
        ):
            raise GatewayContractViolation(
                "DecisionResponse does not echo request identity"
            )
        return response

    def _validate_error(
        self,
        request: DecisionRequest,
        transport_response: GatewayTransportResponse,
    ) -> ErrorEnvelope:
        headers = {
            name.lower(): value for name, value in transport_response.headers.items()
        }
        if headers.get("x-ai-cs-contract-version") != CONTRACT_VERSION:
            raise GatewayContractViolation("gateway error version header is invalid")
        try:
            envelope = ErrorEnvelope.model_validate_json(transport_response.body)
        except ValidationError as exc:
            raise GatewayContractViolation(
                "gateway non-2xx response is not a Contract V1 ErrorEnvelope"
            ) from exc
        expected_status = _ERROR_STATUS_BY_CODE[envelope.error.code]
        if transport_response.status_code != expected_status:
            raise GatewayContractViolation("gateway error code/status mismatch")
        if envelope.error.request_id not in {None, request.request_id}:
            raise GatewayContractViolation("gateway error request_id mismatch")
        if envelope.error.correlation_id not in {None, request.correlation_id}:
            raise GatewayContractViolation("gateway error correlation_id mismatch")
        retry_after = headers.get("retry-after")
        if envelope.error.code is GatewayErrorCode.RATE_LIMITED:
            if retry_after is None or retry_after != str(
                envelope.error.retry_after_seconds
            ):
                raise GatewayContractViolation("Retry-After does not match envelope")
        return envelope

    def _backoff(self, attempt: int, retry_after_seconds: int | None) -> None:
        policy = self._retry_policy
        exponential = min(
            policy.max_backoff_seconds,
            policy.base_backoff_seconds * (2 ** (attempt - 1)),
        )
        multiplier = 1 + policy.jitter_ratio * (2 * self._random_source() - 1)
        delay = max(0.0, exponential * multiplier)
        if retry_after_seconds is not None:
            delay = max(delay, float(retry_after_seconds))
        with self._lock:
            self.retry_count += 1
        self._sleeper(delay)


__all__ = [
    "AICSGatewayClient",
    "AICSGatewayRequestFailed",
    "AICSGatewayTimeout",
    "DECISION_PATH",
    "DECISION_TIMEOUT_SECONDS",
    "GatewayContractViolation",
    "GATEWAY_MEDIA_TYPE",
    "GatewayHealth",
    "GatewayHealthStatus",
    "GatewayRetryPolicy",
    "GatewayTransport",
    "GatewayTransportError",
    "GatewayTransportResponse",
    "GatewayTransportTimeout",
    "HEALTH_PATH",
    "canonical_gateway_body",
]
