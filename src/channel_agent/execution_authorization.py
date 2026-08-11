from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .version import AGENT_CONTROL_PROTOCOL_VERSION


class ExecutionAuthorizationError(PermissionError):
    pass


class ExecutionAuthorizationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ExecutionAuthorizationClaims(ExecutionAuthorizationModel):
    """Server-verified facts required before an edge send can be authorized."""

    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(min_length=1, max_length=255)
    message_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    lease_expires_at: AwareDatetime
    reply_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    send_key: str = Field(min_length=1, max_length=255)
    policy_version: str = Field(min_length=1, max_length=128)
    selector_evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    activation_grant_id: str = Field(min_length=1, max_length=160)
    human_approval_verified: Literal[True]
    lease_valid: Literal[True]
    kill_switch_disabled: Literal[True]
    store_allowlisted: Literal[True]
    risk_policy_allowed: Literal[True]
    rate_limit_allowed: Literal[True]


class ExecutionAuthorization(ExecutionAuthorizationClaims):
    control_protocol_version: Literal["2.1"] = AGENT_CONTROL_PROTOCOL_VERSION
    authorization_id: str = Field(min_length=1, max_length=160)
    key_id: str = Field(min_length=1, max_length=128)
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    signature: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)

    @model_validator(mode="after")
    def validate_time_boundary(self) -> ExecutionAuthorization:
        if self.expires_at <= self.issued_at:
            raise ValueError("execution authorization must expire after issuance")
        if self.expires_at > self.issued_at + timedelta(minutes=5):
            raise ValueError("execution authorization lifetime exceeds five minutes")
        if self.expires_at > self.lease_expires_at:
            raise ValueError("execution authorization cannot outlive the lease")
        return self

    def canonical_bytes(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class ExecutionAuthorizationSigner:
    def __init__(
        self,
        *,
        key_id: str,
        secret: bytes,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lifetime: timedelta = timedelta(seconds=60),
    ) -> None:
        if not key_id or len(key_id) > 128:
            raise ValueError("execution authorization key id is invalid")
        if len(secret) < 32:
            raise ValueError("execution authorization signing key is too short")
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=5):
            raise ValueError("execution authorization lifetime is invalid")
        self.key_id = key_id
        self._secret = bytes(secret)
        self._clock = clock
        self._lifetime = lifetime

    def issue(self, claims: ExecutionAuthorizationClaims) -> ExecutionAuthorization:
        now = self._clock().astimezone(UTC)
        expires_at = min(now + self._lifetime, claims.lease_expires_at.astimezone(UTC))
        if expires_at <= now:
            raise ExecutionAuthorizationError("execution lease is no longer valid")
        unsigned = {
            **claims.model_dump(mode="python"),
            "control_protocol_version": AGENT_CONTROL_PROTOCOL_VERSION,
            "authorization_id": f"execution-authorization:{claims.execution_id}",
            "key_id": self.key_id,
            "nonce": secrets.token_hex(16),
            "issued_at": now,
            "expires_at": expires_at,
            "signature": "0" * 64,
        }
        candidate = ExecutionAuthorization.model_validate(unsigned)
        signature = hmac.new(
            self._secret,
            candidate.canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()
        return candidate.model_copy(update={"signature": signature})


class ExecutionAuthorizationVerifier:
    def __init__(
        self,
        *,
        key_resolver: Callable[[str], bytes],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._key_resolver = key_resolver
        self._clock = clock
        self._consumed: set[tuple[str, str]] = set()
        self._lock = RLock()

    def verify(
        self,
        authorization: ExecutionAuthorization,
        *,
        agent_id: str,
        device_id: str,
        store_id: str,
        conversation_id: str,
        customer_reference: str,
        reply_text: str,
        selector_evidence_hash: str,
        consume: bool = True,
    ) -> None:
        now = self._clock().astimezone(UTC)
        if now < authorization.issued_at.astimezone(UTC) - timedelta(seconds=30):
            raise ExecutionAuthorizationError("execution authorization is not active")
        if now >= authorization.expires_at.astimezone(UTC):
            raise ExecutionAuthorizationError("execution authorization expired")
        if now >= authorization.lease_expires_at.astimezone(UTC):
            raise ExecutionAuthorizationError("execution lease expired")
        actual_reply_hash = reply_text_sha256(reply_text)
        expected = (
            (authorization.agent_id, agent_id, "agent"),
            (authorization.device_id, device_id, "device"),
            (authorization.store_id, store_id, "store"),
            (authorization.conversation_id, conversation_id, "conversation"),
            (authorization.customer_reference, customer_reference, "customer"),
            (authorization.reply_sha256, actual_reply_hash, "reply"),
            (
                authorization.selector_evidence_hash,
                selector_evidence_hash,
                "selector evidence",
            ),
        )
        mismatch = next((label for signed, actual, label in expected if signed != actual), None)
        if mismatch is not None:
            raise ExecutionAuthorizationError(f"execution authorization {mismatch} mismatch")
        try:
            secret = self._key_resolver(authorization.key_id)
        except Exception as exc:
            raise ExecutionAuthorizationError("execution authorization key is unavailable") from exc
        if len(secret) < 32:
            raise ExecutionAuthorizationError("execution authorization key is invalid")
        expected_signature = hmac.new(
            secret,
            authorization.canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, authorization.signature):
            raise ExecutionAuthorizationError("execution authorization signature is invalid")
        if consume:
            with self._lock:
                replay_key = (authorization.authorization_id, authorization.nonce)
                if replay_key in self._consumed:
                    raise ExecutionAuthorizationError("execution authorization was replayed")
                self._consumed.add(replay_key)


def reply_text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "ExecutionAuthorization",
    "ExecutionAuthorizationClaims",
    "ExecutionAuthorizationError",
    "ExecutionAuthorizationSigner",
    "ExecutionAuthorizationVerifier",
    "reply_text_sha256",
]
