from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now

from .lifecycle import (
    ChannelAuthentication,
    ChannelAuthenticationFailed,
    ChannelConnectionState,
    ChannelCredentialReference,
    ChannelHeartbeat,
    ChannelLifecycleManager,
    ChannelSession,
    ChannelSessionUnavailable,
)
from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    PlatformAdapter,
    SendAuthorizationVerifier,
)
from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelSendReceipt,
    NormalizedMessage,
)


class FakePlatformInboundMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    conversation_ref: str = Field(min_length=1, max_length=255)
    message_ref: str = Field(min_length=1, max_length=255)
    sender_ref: str = Field(min_length=1, max_length=255)
    text: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    occurred_at: AwareDatetime


class FakeChannelAuthenticationBroker:
    """Secretless contract-test broker; never models a platform token."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        session_ttl: timedelta = timedelta(minutes=10),
        reject_authentication: bool = False,
    ) -> None:
        self._clock = clock
        self._session_ttl = session_ttl
        self.reject_authentication = reject_authentication
        self.call_count = 0

    def authenticate(
        self,
        channel: str,
        credential: ChannelCredentialReference,
    ) -> ChannelAuthentication:
        self.call_count += 1
        if self.reject_authentication:
            raise ChannelAuthenticationFailed(
                "fake credential broker rejected authentication"
            )
        now = self._clock()
        return ChannelAuthentication(
            principal_ref=f"principal:{channel}:{credential.account_ref}",
            account_ref=credential.account_ref,
            credential_id=credential.credential_id,
            credential_version=credential.version,
            auth_scheme=credential.auth_scheme,
            authenticated_at=now,
            expires_at=now + self._session_ttl,
        )


class FakeChannelHeartbeatProbe:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.call_count = 0

    def probe(self, session: ChannelSession) -> bool:
        del session
        self.call_count += 1
        return self.healthy


class FakePlatformAdapterV1:
    """Contract adapter with lifecycle and ledger guard, but no platform I/O."""

    adapter_name = "FakePlatformAdapterV1"

    def __init__(
        self,
        channel: str,
        credential: ChannelCredentialReference,
        authorization_verifier: SendAuthorizationVerifier,
        *,
        authentication_broker: FakeChannelAuthenticationBroker | None = None,
        heartbeat_probe: FakeChannelHeartbeatProbe | None = None,
        send_outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.channel = channel
        self._authorization_verifier = authorization_verifier
        self._clock = clock
        self.authentication_broker = (
            authentication_broker
            or FakeChannelAuthenticationBroker(clock=clock)
        )
        self.heartbeat_probe = heartbeat_probe or FakeChannelHeartbeatProbe()
        self.lifecycle = ChannelLifecycleManager(
            channel,
            credential,
            self.authentication_broker,
            self.heartbeat_probe,
            clock=clock,
            real_platform_connection=False,
        )
        self.send_outcome = send_outcome
        self.receive_call_count = 0
        self.send_call_count = 0
        self._inbound: deque[NormalizedMessage] = deque()
        self._inbound_fingerprints: dict[tuple[str, str], str] = {}
        self._send_results: dict[str, tuple[str, ChannelSendReceipt]] = {}
        self._lock = Lock()

    def connect(self) -> ChannelSession:
        return self.lifecycle.connect()

    def heartbeat(self) -> ChannelHeartbeat:
        return self.lifecycle.heartbeat()

    def disconnect(self) -> None:
        self.lifecycle.disconnect()

    def get_session(self) -> ChannelSession | None:
        return self.lifecycle.get_session()

    def normalize_message(
        self,
        raw: FakePlatformInboundMessage,
    ) -> NormalizedMessage:
        return NormalizedMessage(
            channel=self.channel,
            conversation_id=raw.conversation_ref,
            external_message_id=raw.message_ref,
            sender=raw.sender_ref,
            content=raw.text,
            timestamp=raw.occurred_at,
        )

    def enqueue_external_message(self, raw: FakePlatformInboundMessage) -> bool:
        normalized = self.normalize_message(raw)
        fingerprint = self._fingerprint(normalized.model_dump(mode="json"))
        key = (normalized.conversation_id, normalized.external_message_id)
        with self._lock:
            existing = self._inbound_fingerprints.get(key)
            if existing is not None:
                if existing != fingerprint:
                    raise ValueError(
                        "external_message_id was reused with different content"
                    )
                return False
            self._inbound_fingerprints[key] = fingerprint
            self._inbound.append(normalized)
            return True

    def receive_message(self) -> NormalizedMessage | None:
        self._assert_active_session()
        with self._lock:
            self.receive_call_count += 1
            return self._inbound.popleft() if self._inbound else None

    def send_message(
        self,
        command: AuthorizedOutboundMessage,
    ) -> ChannelSendReceipt:
        if not isinstance(command, AuthorizedOutboundMessage):
            raise ExecutionBoundaryDenied(
                "PlatformAdapter rejects sends without execution authorization"
            )
        self._assert_active_session()
        self._authorization_verifier.verify(command)
        message = command.message
        if message.channel != self.channel:
            raise ExecutionBoundaryDenied(
                "approved send targets a different channel adapter"
            )
        fingerprint = self._fingerprint(message.model_dump(mode="json"))
        with self._lock:
            replay = self._send_results.get(message.idempotency_key)
            if replay is not None:
                original_fingerprint, original_receipt = replay
                if original_fingerprint != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "send idempotency key is bound to different content"
                    )
                return original_receipt
            self.send_call_count += 1
            error_code = {
                ReceiptOutcome.SUCCESS: None,
                ReceiptOutcome.FAILED: "FAKE_PLATFORM_SEND_FAILED",
                ReceiptOutcome.UNKNOWN: "FAKE_PLATFORM_SEND_UNKNOWN",
            }[self.send_outcome]
            receipt = ChannelSendReceipt(
                receipt_id=new_id("fake-platform-receipt"),
                channel=self.channel,
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                external_message_id=(
                    new_id("fake-platform-message")
                    if self.send_outcome is ReceiptOutcome.SUCCESS
                    else None
                ),
                outcome=self.send_outcome,
                error_code=error_code,
                details={
                    "mode": "CONTRACT_TEST",
                    "adapter": self.adapter_name,
                    "authorization_id": command.authorization.authorization_id,
                    "real_platform_called": False,
                    "customer_message_sent": False,
                    "refund_performed": False,
                    "order_modified": False,
                },
                recorded_at=self._clock(),
            )
            self._send_results[message.idempotency_key] = (
                fingerprint,
                receipt,
            )
            return receipt

    def health_check(self) -> AdapterHealth:
        connection = self.lifecycle.connection
        session = self.get_session()
        status = {
            ChannelConnectionState.CONNECTED: AdapterHealthStatus.HEALTHY,
            ChannelConnectionState.DEGRADED: AdapterHealthStatus.DEGRADED,
        }.get(connection.state, AdapterHealthStatus.UNHEALTHY)
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=status,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "mode": "CONTRACT_TEST",
                "connection_state": connection.state.value,
                "authenticated_session": bool(
                    session is not None and session.authenticated
                ),
                "credential_provider": self.lifecycle.credential.provider,
                "credential_version": self.lifecycle.credential.version,
                "real_platform_called": False,
                "automatic_send_enabled": False,
            },
        )

    def _assert_active_session(self) -> None:
        session = self.get_session()
        connection = self.lifecycle.connection
        if (
            session is None
            or connection.state is not ChannelConnectionState.CONNECTED
            or session.expires_at <= self._clock()
        ):
            raise ChannelSessionUnavailable(
                "a healthy authenticated channel session is required"
            )

    @staticmethod
    def _fingerprint(payload: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


__all__ = [
    "FakeChannelAuthenticationBroker",
    "FakeChannelHeartbeatProbe",
    "FakePlatformAdapterV1",
    "FakePlatformInboundMessage",
    "PlatformAdapter",
]
