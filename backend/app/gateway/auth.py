from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from app.gateway.contract import (
    CONTRACT_VERSION,
    GatewayErrorCode,
    GatewayProblem,
    utc_now,
)
from app.gateway.store import GatewayStateStore


_AUTHORIZATION_PATTERN = re.compile(
    r"^HMAC-SHA256 Credential=([^/]+)/([^,]+),Signature=([A-Za-z0-9_-]{43})$"
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,86}$")
_CONTENT_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _safe_identifier(value: str | None) -> str | None:
    if value and _IDENTIFIER_PATTERN.fullmatch(value):
        return value
    return None


def canonical_signing_text(
    *,
    method: str,
    path: str,
    contract_version: str,
    client_id: str,
    key_id: str,
    timestamp: str,
    nonce: str,
    request_id: str,
    correlation_id: str,
    idempotency_key: str,
    content_sha256: str,
) -> bytes:
    return "\n".join(
        (
            "HMAC-SHA256",
            method.upper(),
            path,
            contract_version,
            client_id,
            key_id,
            timestamp,
            nonce,
            request_id,
            correlation_id,
            idempotency_key,
            content_sha256,
        )
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class GatewayIdentity:
    client_id: str
    key_id: str
    request_id: str
    correlation_id: str
    idempotency_key: str


class GatewayAuthenticator:
    def __init__(
        self,
        *,
        credentials: Mapping[tuple[str, str], bytes],
        state_store: GatewayStateStore,
        allowed_clock_skew_seconds: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not credentials:
            raise ValueError("gateway requires at least one credential")
        for secret in credentials.values():
            if not isinstance(secret, bytes) or len(secret) < 32:
                raise ValueError("gateway HMAC secret must contain at least 32 bytes")
        self._credentials = dict(credentials)
        self._state_store = state_store
        self._allowed_clock_skew_seconds = allowed_clock_skew_seconds
        self._clock = clock

    def verify(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> GatewayIdentity:
        normalized = {name.lower(): value for name, value in headers.items()}
        request_id = _safe_identifier(normalized.get("x-request-id"))
        correlation_id = _safe_identifier(normalized.get("x-correlation-id"))
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
            raise GatewayProblem(
                status_code=401,
                code=GatewayErrorCode.AUTHENTICATION_REQUIRED,
                message="Gateway authentication metadata is required.",
                request_id=request_id,
                correlation_id=correlation_id,
            )
        if normalized["x-ai-cs-contract-version"] != CONTRACT_VERSION:
            raise GatewayProblem(
                status_code=406,
                code=GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION,
                message="Gateway contract version is not supported.",
                request_id=request_id,
                correlation_id=correlation_id,
            )

        authorization = _AUTHORIZATION_PATTERN.fullmatch(normalized["authorization"])
        nonce = normalized["x-ai-cs-nonce"]
        content_sha256 = normalized["x-ai-cs-content-sha256"]
        idempotency_key = _safe_identifier(normalized.get("idempotency-key"))
        if (
            authorization is None
            or request_id is None
            or correlation_id is None
            or idempotency_key is None
            or _NONCE_PATTERN.fullmatch(nonce) is None
            or _CONTENT_HASH_PATTERN.fullmatch(content_sha256) is None
        ):
            self._authentication_failed(request_id, correlation_id)

        assert authorization is not None
        assert request_id is not None
        assert correlation_id is not None
        assert idempotency_key is not None
        client_id, key_id, signature = authorization.groups()
        if (
            _safe_identifier(client_id) is None
            or _safe_identifier(key_id) is None
        ):
            self._authentication_failed(request_id, correlation_id)

        timestamp_text = normalized["x-ai-cs-timestamp"]
        try:
            timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        except ValueError:
            self._authentication_failed(request_id, correlation_id)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            self._authentication_failed(request_id, correlation_id)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("gateway verifier clock must include a timezone")
        if abs((now - timestamp).total_seconds()) > self._allowed_clock_skew_seconds:
            self._authentication_failed(request_id, correlation_id)

        actual_hash = hashlib.sha256(body).hexdigest()
        if not hmac.compare_digest(actual_hash, content_sha256):
            self._authentication_failed(request_id, correlation_id)

        secret = self._credentials.get((client_id, key_id))
        known_credential = secret is not None
        comparison_secret = secret or bytes(32)
        expected = hmac.new(
            comparison_secret,
            canonical_signing_text(
                method=method,
                path=path,
                contract_version=CONTRACT_VERSION,
                client_id=client_id,
                key_id=key_id,
                timestamp=timestamp_text,
                nonce=nonce,
                request_id=request_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                content_sha256=content_sha256,
            ),
            hashlib.sha256,
        ).digest()
        expected_text = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
        if not known_credential or not hmac.compare_digest(expected_text, signature):
            self._authentication_failed(request_id, correlation_id)

        now_epoch = now.astimezone(timezone.utc).timestamp()
        if not self._state_store.claim_nonce(
            client_id=client_id,
            key_id=key_id,
            nonce=nonce,
            now_epoch=now_epoch,
        ):
            self._authentication_failed(request_id, correlation_id)

        return GatewayIdentity(
            client_id=client_id,
            key_id=key_id,
            request_id=request_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _authentication_failed(
        request_id: str | None,
        correlation_id: str | None,
    ) -> None:
        raise GatewayProblem(
            status_code=401,
            code=GatewayErrorCode.AUTHENTICATION_FAILED,
            message="Gateway authentication failed.",
            request_id=request_id,
            correlation_id=correlation_id,
        )
