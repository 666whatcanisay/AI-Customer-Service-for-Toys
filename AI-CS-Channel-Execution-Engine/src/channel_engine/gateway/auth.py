from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import ValidationError

from channel_engine.models.entities import utc_now

from .contract import AuthenticationMetadata, CONTRACT_VERSION, DecisionRequest


_AUTHORIZATION_PATTERN = re.compile(
    r"^HMAC-SHA256 Credential=([^/]+)/([^,]+),Signature=([A-Za-z0-9_-]{43})$"
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class GatewayAuthenticationError(ValueError):
    """Base class for fail-closed gateway authentication failures."""


class GatewayAuthenticationRequired(GatewayAuthenticationError):
    pass


class GatewayAuthenticationFailed(GatewayAuthenticationError):
    pass


class GatewayContractVersionMismatch(GatewayAuthenticationError):
    pass


def _timestamp_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("gateway authentication timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_signing_text(
    *,
    method: str,
    path: str,
    metadata: AuthenticationMetadata,
    timestamp_text: str,
    request_id: str,
    correlation_id: str,
    idempotency_key: str,
) -> bytes:
    return "\n".join(
        (
            metadata.scheme,
            method.upper(),
            path,
            metadata.contract_version,
            metadata.client_id,
            metadata.key_id,
            timestamp_text,
            metadata.nonce,
            request_id,
            correlation_id,
            idempotency_key,
            metadata.content_sha256,
        )
    ).encode("utf-8")


def _signature(secret: bytes, signing_text: bytes) -> str:
    digest = hmac.new(secret, signing_text, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


@dataclass(frozen=True, slots=True)
class GatewayRequestSigner:
    client_id: str
    key_id: str
    secret: bytes = field(repr=False)
    clock: Callable[[], datetime] = field(default=utc_now, repr=False)
    nonce_factory: Callable[[], str] = field(
        default=lambda: base64.urlsafe_b64encode(secrets.token_bytes(18))
        .decode("ascii")
        .rstrip("="),
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise ValueError("gateway HMAC secret must contain at least 32 bytes")

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
        for name, value in (
            ("request_id", request_id),
            ("correlation_id", correlation_id),
            ("idempotency_key", idempotency_key),
        ):
            if _IDENTIFIER_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} is not a valid Gateway Contract identifier")
        timestamp = self.clock()
        timestamp_text = _timestamp_text(timestamp)
        nonce = self.nonce_factory()
        content_sha256 = hashlib.sha256(body).hexdigest()
        unsigned = AuthenticationMetadata(
            contract_version=CONTRACT_VERSION,
            scheme="HMAC-SHA256",
            client_id=self.client_id,
            key_id=self.key_id,
            timestamp=timestamp,
            nonce=nonce,
            content_sha256=content_sha256,
            signature="A" * 43,
        )
        signature = _signature(
            self.secret,
            _canonical_signing_text(
                method=method,
                path=path,
                metadata=unsigned,
                timestamp_text=timestamp_text,
                request_id=request_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            ),
        )
        metadata = unsigned.model_copy(update={"signature": signature})
        headers = {
            "Authorization": (
                f"{metadata.scheme} Credential={metadata.client_id}/"
                f"{metadata.key_id},Signature={metadata.signature}"
            ),
            "X-AI-CS-Contract-Version": metadata.contract_version,
            "X-AI-CS-Timestamp": timestamp_text,
            "X-AI-CS-Nonce": metadata.nonce,
            "X-AI-CS-Content-SHA256": metadata.content_sha256,
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
            "Idempotency-Key": idempotency_key,
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        return headers

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
        identity = secrets.token_hex(12)
        return self.sign(
            body,
            method=method,
            path=path,
            request_id=request_id or f"health-request-{identity}",
            correlation_id=correlation_id or f"health-correlation-{identity}",
            idempotency_key=idempotency_key or f"health-check-{identity}",
            content_type=None,
        )


def verify_gateway_request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    credentials: Mapping[tuple[str, str], bytes],
    now: datetime,
    allowed_clock_skew_seconds: int = 300,
) -> AuthenticationMetadata:
    normalized = _normalized_headers(headers)
    required_headers = (
        "authorization",
        "x-ai-cs-contract-version",
        "x-ai-cs-timestamp",
        "x-ai-cs-nonce",
        "x-ai-cs-content-sha256",
        "x-request-id",
        "x-correlation-id",
        "idempotency-key",
    )
    if any(not normalized.get(name) for name in required_headers):
        raise GatewayAuthenticationRequired("required gateway authentication is missing")
    if normalized["x-ai-cs-contract-version"] != CONTRACT_VERSION:
        raise GatewayContractVersionMismatch("unsupported gateway contract version")

    authorization = _AUTHORIZATION_PATTERN.fullmatch(normalized["authorization"])
    if authorization is None:
        raise GatewayAuthenticationFailed("gateway Authorization header is invalid")
    client_id, key_id, signature = authorization.groups()
    timestamp_text = normalized["x-ai-cs-timestamp"]
    try:
        timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        metadata = AuthenticationMetadata(
            contract_version=normalized["x-ai-cs-contract-version"],
            scheme="HMAC-SHA256",
            client_id=client_id,
            key_id=key_id,
            timestamp=timestamp,
            nonce=normalized["x-ai-cs-nonce"],
            content_sha256=normalized["x-ai-cs-content-sha256"],
            signature=signature,
        )
    except (ValueError, ValidationError) as exc:
        raise GatewayAuthenticationFailed(
            "gateway authentication metadata is invalid"
        ) from exc

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("gateway verifier clock must include a timezone")
    age = abs((now - metadata.timestamp).total_seconds())
    if age > allowed_clock_skew_seconds:
        raise GatewayAuthenticationFailed("gateway authentication timestamp is stale")
    actual_hash = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(actual_hash, metadata.content_sha256):
        raise GatewayAuthenticationFailed("gateway content hash is invalid")

    secret = credentials.get((client_id, key_id))
    if secret is None or len(secret) < 32:
        raise GatewayAuthenticationFailed("gateway credential is invalid")
    expected = _signature(
        secret,
        _canonical_signing_text(
            method=method,
            path=path,
            metadata=metadata,
            timestamp_text=timestamp_text,
            request_id=normalized["x-request-id"],
            correlation_id=normalized["x-correlation-id"],
            idempotency_key=normalized["idempotency-key"],
        ),
    )
    if not hmac.compare_digest(expected, metadata.signature):
        raise GatewayAuthenticationFailed("gateway signature is invalid")
    return metadata


__all__ = [
    "GatewayAuthenticationError",
    "GatewayAuthenticationFailed",
    "GatewayAuthenticationRequired",
    "GatewayContractVersionMismatch",
    "GatewayRequestSigner",
    "verify_gateway_request",
]
