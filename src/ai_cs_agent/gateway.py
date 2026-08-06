from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from http.client import HTTPResponse
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPHandler,
    HTTPSHandler,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from .config import ServerConfig
from .security import CredentialProvider


CONTRACT_VERSION = "1.0"
HEALTH_PATH = "/gateway/v1/health"
DECISION_PATH = "/gateway/v1/decisions"
MEDIA_TYPE = "application/vnd.ai-cs.channel-engine.gateway-v1+json"


class GatewayError(RuntimeError):
    pass


class GatewayUnavailable(GatewayError):
    pass


class GatewayAuthenticationFailed(GatewayError):
    pass


class GatewayContractViolation(GatewayError):
    pass


class GatewayOutcomeUnknown(GatewayError):
    pass


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True, slots=True)
class GatewayHealth:
    status: str
    service: str
    contract_version: str
    version: str | None
    capabilities: tuple[str, ...]
    reachable: bool
    real_ai_cs_connected: bool
    timestamp: str
    details: dict[str, str | int | bool]

    @property
    def healthy(self) -> bool:
        return (
            self.status == "HEALTHY"
            and self.reachable
            and self.real_ai_cs_connected
            and self.contract_version == CONTRACT_VERSION
        )


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    reset_seconds: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    opened_at: float | None = None

    def before_request(self) -> None:
        if self.state is CircuitState.OPEN:
            if self.opened_at is None or time.monotonic() - self.opened_at < self.reset_seconds:
                raise GatewayUnavailable("gateway circuit is open")
            self.state = CircuitState.HALF_OPEN

    def success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold or self.state is CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True, slots=True)
class _Response:
    status_code: int
    body: bytes
    headers: Mapping[str, str]


class GatewayClient:
    """Frozen Gateway Contract V1 client with no Fake or fallback transport."""

    def __init__(
        self,
        config: ServerConfig,
        credential_provider: CredentialProvider,
        *,
        max_attempts: int = 3,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        if not 1 <= max_attempts <= 3:
            raise ValueError("Gateway Contract V1 permits one to three attempts")
        self.config = config
        self.credential_provider = credential_provider
        self.max_attempts = max_attempts
        self.circuit = circuit_breaker or CircuitBreaker()
        self._opener = build_opener(
            ProxyHandler({}),
            HTTPHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )

    def health_check(self) -> GatewayHealth:
        self.circuit.before_request()
        headers = self._signed_headers(b"", "GET", HEALTH_PATH)
        headers["Accept"] = MEDIA_TYPE
        try:
            response = self._send("GET", HEALTH_PATH, b"", headers)
            if response.status_code != 200:
                if response.status_code in {401, 403}:
                    raise GatewayAuthenticationFailed(
                        "gateway rejected client authentication"
                    )
                error = _parse_error_envelope(response.body)
                if error["error_code"] in {
                    "AUTHENTICATION_REQUIRED",
                    "AUTHENTICATION_FAILED",
                    "AUTHORIZATION_DENIED",
                }:
                    raise GatewayAuthenticationFailed(
                        "gateway rejected client authentication"
                    )
                raise GatewayContractViolation("gateway health returned non-200")
            self._validate_identity_headers(response.headers, headers)
            health = _parse_health(response.body)
            if not health.healthy:
                raise GatewayUnavailable("gateway reported unhealthy")
            self.circuit.success()
            return health
        except GatewayError:
            self.circuit.failure()
            raise

    def request_decision(self, request: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _validate_decision_request(dict(request))
        body = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        for attempt in range(1, self.max_attempts + 1):
            self.circuit.before_request()
            headers = self._signed_headers(
                body,
                "POST",
                DECISION_PATH,
                request_id=normalized["request_id"],
                correlation_id=normalized["correlation_id"],
                idempotency_key=normalized["idempotency_key"],
            )
            headers["Content-Type"] = MEDIA_TYPE
            headers["Accept"] = MEDIA_TYPE
            try:
                response = self._send("POST", DECISION_PATH, body, headers)
            except GatewayUnavailable as exc:
                self.circuit.failure()
                if attempt == self.max_attempts:
                    raise GatewayOutcomeUnknown(
                        "decision outcome is unknown; automatic execution is forbidden"
                    ) from exc
                time.sleep(min(0.05 * 2 ** (attempt - 1), 0.5))
                continue
            if response.status_code == 200:
                self._validate_identity_headers(response.headers, headers)
                decision = _parse_decision_response(response.body, normalized)
                self.circuit.success()
                return decision
            error = _parse_error_envelope(response.body)
            if bool(error["retryable"]) and attempt < self.max_attempts:
                self.circuit.failure()
                time.sleep(min(float(error.get("retry_after_seconds") or 0.05), 1.0))
                continue
            self.circuit.failure()
            raise GatewayError(f"gateway rejected request: {error['error_code']}")
        raise AssertionError("gateway retry loop exited unexpectedly")

    def _signed_headers(
        self,
        body: bytes,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        identity = secrets.token_hex(12)
        request_id = request_id or f"health-request-{identity}"
        correlation_id = correlation_id or f"health-correlation-{identity}"
        idempotency_key = idempotency_key or f"health-check-{identity}"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        nonce = base64.urlsafe_b64encode(secrets.token_bytes(18)).decode().rstrip("=")
        content_hash = hashlib.sha256(body).hexdigest()
        canonical = "\n".join(
            (
                "HMAC-SHA256",
                method.upper(),
                path,
                CONTRACT_VERSION,
                self.config.client_id,
                self.config.key_id,
                timestamp,
                nonce,
                request_id,
                correlation_id,
                idempotency_key,
                content_hash,
            )
        ).encode("utf-8")
        material = self.credential_provider.acquire(
            self.config.credential_reference
        ).for_signing()
        signature = base64.urlsafe_b64encode(
            hmac.new(material, canonical, hashlib.sha256).digest()
        ).decode("ascii").rstrip("=")
        return {
            "Authorization": (
                f"HMAC-SHA256 Credential={self.config.client_id}/"
                f"{self.config.key_id},Signature={signature}"
            ),
            "X-AI-CS-Contract-Version": CONTRACT_VERSION,
            "X-AI-CS-Timestamp": timestamp,
            "X-AI-CS-Nonce": nonce,
            "X-AI-CS-Content-SHA256": content_hash,
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
            "Idempotency-Key": idempotency_key,
        }

    def _send(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> _Response:
        request = Request(
            self.config.address + path,
            data=body if method == "POST" else None,
            headers=dict(headers),
            method=method,
        )
        try:
            response: HTTPResponse = self._opener.open(
                request, timeout=self.config.timeout_seconds
            )
            with response:
                return _Response(
                    status_code=response.status,
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise GatewayContractViolation("gateway redirects are forbidden") from exc
            return _Response(exc.code, exc.read(), dict(exc.headers.items()))
        except (URLError, TimeoutError, OSError) as exc:
            raise GatewayUnavailable("AI-CS gateway transport failed") from exc

    @staticmethod
    def _validate_identity_headers(
        response_headers: Mapping[str, str], request_headers: Mapping[str, str]
    ) -> None:
        normalized = {key.casefold(): value for key, value in response_headers.items()}
        expected = {
            "x-ai-cs-contract-version": CONTRACT_VERSION,
            "x-request-id": request_headers["X-Request-ID"],
            "x-correlation-id": request_headers["X-Correlation-ID"],
        }
        if any(normalized.get(key) != value for key, value in expected.items()):
            raise GatewayContractViolation("gateway identity headers do not match request")


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GatewayContractViolation("gateway returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise GatewayContractViolation("gateway response must be an object")
    return value


def _parse_health(body: bytes) -> GatewayHealth:
    value = _json_object(body)
    expected = {
        "status",
        "service",
        "contract_version",
        "version",
        "capabilities",
        "reachable",
        "real_ai_cs_connected",
        "timestamp",
        "details",
    }
    if set(value) != expected or value.get("contract_version") != CONTRACT_VERSION:
        raise GatewayContractViolation("GatewayHealth failed Contract V1")
    if value.get("status") not in {"HEALTHY", "UNHEALTHY"}:
        raise GatewayContractViolation("GatewayHealth status is invalid")
    if not isinstance(value.get("capabilities"), list):
        raise GatewayContractViolation("GatewayHealth capabilities are invalid")
    if not isinstance(value.get("details"), dict):
        raise GatewayContractViolation("GatewayHealth details are invalid")
    return GatewayHealth(
        status=value["status"],
        service=str(value["service"]),
        contract_version=value["contract_version"],
        version=value["version"],
        capabilities=tuple(str(item) for item in value["capabilities"]),
        reachable=value["reachable"] is True,
        real_ai_cs_connected=value["real_ai_cs_connected"] is True,
        timestamp=str(value["timestamp"]),
        details=dict(value["details"]),
    )


def _validate_decision_request(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "contract_version",
        "request_id",
        "idempotency_key",
        "correlation_id",
        "conversation_id",
        "message_id",
        "customer_message",
        "context",
        "requested_at",
    }
    if set(value) != expected or value.get("contract_version") != CONTRACT_VERSION:
        raise GatewayContractViolation("DecisionRequest failed Contract V1")
    for key in expected - {"context"}:
        if not isinstance(value[key], str) or not value[key].strip():
            raise GatewayContractViolation(f"DecisionRequest {key} is invalid")
    if not isinstance(value["context"], dict):
        raise GatewayContractViolation("DecisionRequest context is invalid")
    return value


def _parse_decision_response(body: bytes, request: Mapping[str, Any]) -> dict[str, Any]:
    value = _json_object(body)
    expected = {
        "contract_version",
        "request_id",
        "idempotency_key",
        "correlation_id",
        "decision_id",
        "action",
        "proposed_content",
        "requires_approval",
        "risk_level",
        "gateway_version",
        "metadata",
        "decided_at",
    }
    if set(value) != expected or value.get("contract_version") != CONTRACT_VERSION:
        raise GatewayContractViolation("DecisionResponse failed Contract V1")
    for name in ("request_id", "idempotency_key", "correlation_id"):
        if value.get(name) != request[name]:
            raise GatewayContractViolation("DecisionResponse identity mismatch")
    if value.get("requires_approval") is not True:
        raise GatewayContractViolation("DecisionResponse must require approval")
    if value.get("action") not in {"SUGGEST_REPLY", "NO_ACTION"}:
        raise GatewayContractViolation("DecisionResponse action is invalid")
    if value["action"] == "SUGGEST_REPLY" and not value.get("proposed_content"):
        raise GatewayContractViolation("SUGGEST_REPLY requires proposed_content")
    if value["action"] == "NO_ACTION" and value.get("proposed_content") is not None:
        raise GatewayContractViolation("NO_ACTION forbids proposed_content")
    if value.get("risk_level") not in {"LOW", "MEDIUM", "HIGH"}:
        raise GatewayContractViolation("DecisionResponse risk is invalid")
    return value


def _parse_error_envelope(body: bytes) -> dict[str, Any]:
    value = _json_object(body)
    if set(value) != {"contract_version", "error"} or value.get(
        "contract_version"
    ) != CONTRACT_VERSION:
        raise GatewayContractViolation("ErrorEnvelope failed Contract V1")
    error = value.get("error")
    if not isinstance(error, dict):
        raise GatewayContractViolation("ErrorEnvelope error is invalid")
    required = {"error_code", "retryable"}
    if not required.issubset(error) or not isinstance(error["retryable"], bool):
        raise GatewayContractViolation("ErrorEnvelope fields are invalid")
    return error
