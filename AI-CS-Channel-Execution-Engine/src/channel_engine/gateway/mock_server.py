from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from threading import Lock

from pydantic import ValidationError

from channel_engine.models import DecisionAction
from channel_engine.models.entities import new_id, utc_now

from .auth import (
    GatewayAuthenticationFailed,
    GatewayAuthenticationRequired,
    GatewayContractVersionMismatch,
    verify_gateway_request,
)
from .client import (
    DECISION_PATH,
    GATEWAY_MEDIA_TYPE,
    HEALTH_PATH,
    GatewayHealth,
    GatewayHealthStatus,
    GatewayTransportError,
    GatewayTransportResponse,
    GatewayTransportTimeout,
    canonical_gateway_body,
)
from .contract import (
    CONTRACT_VERSION,
    RETRYABLE_ERROR_CODES,
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    GatewayError,
    GatewayErrorCode,
    GatewayRiskLevel,
)


DECISION_BODY_LIMIT_BYTES = 64 * 1024

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


class MockDecisionMode(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True, slots=True)
class MockDecisionBehavior:
    mode: MockDecisionMode
    error_code: GatewayErrorCode = GatewayErrorCode.SERVICE_UNAVAILABLE
    message: str = "Mock AI-CS failure"
    retry_after_seconds: int | None = None
    commit_before_timeout: bool = False

    def __post_init__(self) -> None:
        if self.mode is MockDecisionMode.ERROR:
            retryable = self.error_code in RETRYABLE_ERROR_CODES
            if not retryable and self.retry_after_seconds is not None:
                raise ValueError("non-retryable mock errors cannot set Retry-After")
            if (
                self.error_code is GatewayErrorCode.RATE_LIMITED
                and self.retry_after_seconds is None
            ):
                raise ValueError("mock RATE_LIMITED requires retry_after_seconds")
        elif self.retry_after_seconds is not None:
            raise ValueError("Retry-After only applies to mock ERROR behavior")
        if self.commit_before_timeout and self.mode is not MockDecisionMode.TIMEOUT:
            raise ValueError("commit_before_timeout only applies to TIMEOUT behavior")


class MockAICSServerTimeout(RuntimeError):
    """The mock server accepted an attempt but produced no transport response."""


@dataclass(frozen=True, slots=True)
class MockTransportAttempt:
    method: str
    path: str
    body_sha256: str
    request_id: str | None
    correlation_id: str | None
    idempotency_key: str | None
    nonce: str | None
    timeout_seconds: float


class MockAICSServer:
    """In-process AI-CS mock implementing only the frozen Decision V1 route."""

    version = "mock-ai-cs.v1"

    def __init__(
        self,
        credentials: Mapping[tuple[str, str], bytes],
        *,
        default_behavior: MockDecisionBehavior | None = None,
        clock: Callable[[], datetime] = utc_now,
        healthy: bool = True,
    ) -> None:
        if not credentials:
            raise ValueError("mock AI-CS requires at least one client credential")
        self._credentials = dict(credentials)
        if any(
            not isinstance(secret, bytes) or len(secret) < 32
            for secret in self._credentials.values()
        ):
            raise ValueError("mock AI-CS HMAC secrets must contain at least 32 bytes")
        self._default_behavior = default_behavior or MockDecisionBehavior(
            MockDecisionMode.SUCCESS
        )
        self._behaviors: deque[MockDecisionBehavior] = deque()
        self._clock = clock
        self._healthy = healthy
        self._responses: dict[
            tuple[str, str], tuple[str, DecisionResponse]
        ] = {}
        self._seen_nonces: dict[tuple[str, str, str], datetime] = {}
        self._lock = Lock()
        self.request_count = 0
        self.health_check_count = 0
        self.decision_compute_count = 0
        self.replay_count = 0
        self.error_count = 0
        self.timeout_count = 0

    def queue_behaviors(self, behaviors: Iterable[MockDecisionBehavior]) -> None:
        with self._lock:
            self._behaviors.extend(behaviors)

    def handle_request(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        if path == HEALTH_PATH and method.upper() == "GET":
            return self._health_response(
                method=method,
                path=path,
                body=body,
                headers=headers,
            )
        with self._lock:
            self.request_count += 1
        if path != DECISION_PATH:
            return self._error_response(GatewayErrorCode.RESOURCE_NOT_FOUND)
        if method.upper() != "POST":
            return self._error_response(GatewayErrorCode.METHOD_NOT_ALLOWED)
        if len(body) > DECISION_BODY_LIMIT_BYTES:
            return self._error_response(GatewayErrorCode.PAYLOAD_TOO_LARGE)

        normalized_headers = {
            name.lower(): value for name, value in headers.items()
        }
        content_type = normalized_headers.get("content-type", "")
        if content_type.split(";", maxsplit=1)[0].strip().lower() not in {
            "application/json",
            GATEWAY_MEDIA_TYPE,
        }:
            return self._error_response(GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE)
        now = self._clock()
        try:
            authentication = verify_gateway_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
                credentials=self._credentials,
                now=now,
            )
        except GatewayAuthenticationRequired:
            return self._error_response(GatewayErrorCode.AUTHENTICATION_REQUIRED)
        except GatewayContractVersionMismatch:
            return self._error_response(
                GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION
            )
        except GatewayAuthenticationFailed:
            return self._error_response(GatewayErrorCode.AUTHENTICATION_FAILED)

        if not self._accept_nonce(
            authentication.client_id,
            authentication.key_id,
            authentication.nonce,
            now,
        ):
            return self._error_response(GatewayErrorCode.AUTHENTICATION_FAILED)
        try:
            json.loads(
                body.decode("utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON constant: {value}")
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return self._error_response(GatewayErrorCode.INVALID_REQUEST)
        try:
            request = DecisionRequest.model_validate_json(body)
        except ValidationError:
            return self._error_response(GatewayErrorCode.SCHEMA_VALIDATION_FAILED)
        if (
            normalized_headers.get("x-request-id") != request.request_id
            or normalized_headers.get("x-correlation-id") != request.correlation_id
            or normalized_headers.get("idempotency-key") != request.idempotency_key
        ):
            return self._error_response(
                GatewayErrorCode.INVALID_REQUEST,
                request=request,
            )

        fingerprint = hashlib.sha256(canonical_gateway_body(request)).hexdigest()
        key = (authentication.client_id, request.idempotency_key)
        with self._lock:
            replay = self._responses.get(key)
            if replay is not None:
                original_fingerprint, original_response = replay
                if original_fingerprint != fingerprint:
                    self.error_count += 1
                    return self._error_response(
                        GatewayErrorCode.IDEMPOTENCY_CONFLICT,
                        request=request,
                    )
                self.replay_count += 1
                return self._success_response(
                    request,
                    original_response,
                    replayed=True,
                )
            behavior = (
                self._behaviors.popleft()
                if self._behaviors
                else self._default_behavior
            )
            if behavior.mode is MockDecisionMode.ERROR:
                self.error_count += 1
                return self._error_response(
                    behavior.error_code,
                    request=request,
                    message=behavior.message,
                    retry_after_seconds=behavior.retry_after_seconds,
                )

            response = self._build_decision(request)
            if behavior.mode is MockDecisionMode.SUCCESS:
                self._responses[key] = (fingerprint, response)
                self.decision_compute_count += 1
                return self._success_response(request, response, replayed=False)

            self.timeout_count += 1
            if behavior.commit_before_timeout:
                self._responses[key] = (fingerprint, response)
                self.decision_compute_count += 1
            raise MockAICSServerTimeout("mock AI-CS produced no response")

    def _health_response(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayTransportResponse:
        with self._lock:
            self.health_check_count += 1
            healthy = self._healthy
        if body:
            return self._error_response(GatewayErrorCode.INVALID_REQUEST)
        now = self._clock()
        try:
            authentication = verify_gateway_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
                credentials=self._credentials,
                now=now,
            )
        except GatewayAuthenticationRequired:
            return self._error_response(GatewayErrorCode.AUTHENTICATION_REQUIRED)
        except GatewayContractVersionMismatch:
            return self._error_response(
                GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION
            )
        except GatewayAuthenticationFailed:
            return self._error_response(GatewayErrorCode.AUTHENTICATION_FAILED)
        if not self._accept_nonce(
            authentication.client_id,
            authentication.key_id,
            authentication.nonce,
            now,
        ):
            return self._error_response(GatewayErrorCode.AUTHENTICATION_FAILED)
        normalized_headers = {
            name.lower(): value for name, value in headers.items()
        }
        if not healthy:
            return GatewayTransportResponse(
                status_code=503,
                body=b'{"status":"UNHEALTHY"}',
                headers={"X-AI-CS-Contract-Version": CONTRACT_VERSION},
            )
        health = GatewayHealth(
            status=GatewayHealthStatus.HEALTHY,
            service="mock-ai-cs",
            contract_version=CONTRACT_VERSION,
            version=self.version,
            capabilities=("decision.v1",),
            reachable=True,
            real_ai_cs_connected=False,
            timestamp=self._clock(),
            details={"mode": "MOCK", "real_ai_cs_called": False},
        )
        return GatewayTransportResponse(
            status_code=200,
            body=health.model_dump_json().encode("utf-8"),
            headers={
                "X-AI-CS-Contract-Version": CONTRACT_VERSION,
                "X-Request-ID": normalized_headers["x-request-id"],
                "X-Correlation-ID": normalized_headers["x-correlation-id"],
                "Idempotency-Replayed": "false",
            },
        )

    def _accept_nonce(
        self,
        client_id: str,
        key_id: str,
        nonce: str,
        now: datetime,
    ) -> bool:
        expiry = now - timedelta(minutes=10)
        nonce_key = (client_id, key_id, nonce)
        with self._lock:
            self._seen_nonces = {
                key: seen_at
                for key, seen_at in self._seen_nonces.items()
                if seen_at >= expiry
            }
            if nonce_key in self._seen_nonces:
                return False
            self._seen_nonces[nonce_key] = now
            return True

    def _build_decision(self, request: DecisionRequest) -> DecisionResponse:
        summary = " ".join(request.customer_message.split())[:120]
        return DecisionResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=new_id("decision"),
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content=f"[MOCK AI-CS SUGGESTION] Received: {summary}",
            requires_approval=True,
            risk_level=GatewayRiskLevel.LOW,
            gateway_version=self.version,
            metadata={
                "mode": "MOCK",
                "real_ai_cs_called": False,
                "automatic_execution_authorized": False,
            },
            decided_at=self._clock(),
        )

    def _success_response(
        self,
        request: DecisionRequest,
        response: DecisionResponse,
        *,
        replayed: bool,
    ) -> GatewayTransportResponse:
        return GatewayTransportResponse(
            status_code=200,
            body=response.model_dump_json().encode("utf-8"),
            headers={
                "X-AI-CS-Contract-Version": CONTRACT_VERSION,
                "X-Request-ID": request.request_id,
                "X-Correlation-ID": request.correlation_id,
                "Idempotency-Replayed": str(replayed).lower(),
            },
        )

    def _error_response(
        self,
        code: GatewayErrorCode,
        *,
        request: DecisionRequest | None = None,
        message: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> GatewayTransportResponse:
        if code is GatewayErrorCode.RATE_LIMITED and retry_after_seconds is None:
            retry_after_seconds = 1
        error = GatewayError(
            error_id=new_id("gateway-error"),
            code=code,
            message=message or f"Mock AI-CS rejected the request: {code.value}",
            retryable=code in RETRYABLE_ERROR_CODES,
            retry_after_seconds=retry_after_seconds,
            request_id=request.request_id if request is not None else None,
            correlation_id=request.correlation_id if request is not None else None,
            details={"mode": "MOCK", "real_ai_cs_called": False},
            occurred_at=self._clock(),
        )
        headers = {"X-AI-CS-Contract-Version": CONTRACT_VERSION}
        if code is GatewayErrorCode.RATE_LIMITED:
            headers["Retry-After"] = str(retry_after_seconds)
        return GatewayTransportResponse(
            status_code=_ERROR_STATUS_BY_CODE[code],
            body=ErrorEnvelope(
                contract_version=CONTRACT_VERSION,
                error=error,
            ).model_dump_json().encode("utf-8"),
            headers=headers,
        )


class MockAICSTransport:
    """Local transport; it never opens a socket or resolves a host."""

    def __init__(self, server: MockAICSServer, *, unavailable: bool = False) -> None:
        self._server = server
        self.unavailable = unavailable
        self.attempts: list[MockTransportAttempt] = []

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
            raise GatewayTransportError("mock AI-CS transport is unavailable")
        normalized = {name.lower(): value for name, value in headers.items()}
        self.attempts.append(
            MockTransportAttempt(
                method=method,
                path=path,
                body_sha256=hashlib.sha256(body).hexdigest(),
                request_id=normalized.get("x-request-id"),
                correlation_id=normalized.get("x-correlation-id"),
                idempotency_key=normalized.get("idempotency-key"),
                nonce=normalized.get("x-ai-cs-nonce"),
                timeout_seconds=timeout_seconds,
            )
        )
        try:
            return self._server.handle_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
            )
        except MockAICSServerTimeout as exc:
            raise GatewayTransportTimeout("mock AI-CS request timed out") from exc


__all__ = [
    "DECISION_BODY_LIMIT_BYTES",
    "MockAICSServer",
    "MockAICSServerTimeout",
    "MockAICSTransport",
    "MockDecisionBehavior",
    "MockDecisionMode",
    "MockTransportAttempt",
]
