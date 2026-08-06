from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Callable
from threading import RLock

from channel_engine.channel.adapter_foundation import ChannelMessageV1
from channel_engine.channel.protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelConversation,
)
from channel_engine.models.entities import utc_now
from channel_engine.pdd_adapter.browser import (
    FakePDDBrowserAdapter,
    PDDBrowserAdapter,
    PDDBrowserHealthState,
    PDDBrowserPageState,
)
from channel_engine.pdd_adapter.mapper import (
    PDDDeduplicationStatus,
    PDDMessageDeduplicator,
    PDDMessageMapper,
)
from channel_engine.pdd_adapter.message import PDDConversation, PDDMessageEnvelope
from channel_engine.pdd_adapter.selector import (
    PDDSelectorState,
    PDDVerifiedSelectorToken,
)
from channel_engine.pdd_adapter.session import PDDSession, PDDSessionStatus


class PDDPrototypeUnavailable(RuntimeError):
    pass


class FakePDDAdapter:
    """Offline, inbound-only PDD adapter skeleton with no platform I/O surface."""

    channel = "pdd"
    adapter_name = "FakePDDAdapterPrototypeV1"

    def __init__(
        self,
        *,
        store_id: str,
        selector_token: PDDVerifiedSelectorToken,
        browser: PDDBrowserAdapter | None = None,
        clock: Callable = utc_now,
    ) -> None:
        if not selector_token.synthetic_test_data:
            raise ValueError("prototype adapter accepts synthetic selector evidence only")
        self.store_id = store_id
        self._selector_token = selector_token
        self._selector_state = PDDSelectorState.VERIFIED
        self._browser = browser or FakePDDBrowserAdapter(clock=clock)
        if not isinstance(self._browser, PDDBrowserAdapter):
            raise TypeError("browser does not implement the read-only PDD boundary")
        self._mapper = PDDMessageMapper(selector_token)
        self._deduplicator = PDDMessageDeduplicator()
        self._clock = clock
        self._session: PDDSession | None = None
        self._inbound: deque[PDDMessageEnvelope] = deque()
        self._conversations: dict[str, ChannelConversation] = {}
        self._lock = RLock()
        self.received_count = 0
        self.duplicate_count = 0

    @property
    def selector_state(self) -> PDDSelectorState:
        return self._selector_state

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._inbound)

    def open_session(self, session: PDDSession) -> PDDBrowserPageState:
        if session.store_id != self.store_id:
            raise PDDPrototypeUnavailable("PDD session store mismatch")
        if session.status is not PDDSessionStatus.CONNECTED:
            raise PDDPrototypeUnavailable("CONNECTED PDD session is required")
        state = self._browser.open_session(session, self._selector_token)
        with self._lock:
            self._session = session
        return state

    def enqueue_observation(self, envelope: PDDMessageEnvelope) -> None:
        if envelope.store_id != self.store_id:
            raise ValueError("PDD observation store mismatch")
        if envelope.raw_metadata.selector_contract_id != self._selector_token.contract_id:
            raise ValueError("PDD observation selector contract mismatch")
        with self._lock:
            self._inbound.append(envelope)

    def receive_messages(self, limit: int = 100) -> tuple[ChannelMessageV1, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("receive limit must be between 1 and 100")
        self._assert_observation_ready()
        accepted: list[ChannelMessageV1] = []
        with self._lock:
            while self._inbound and len(accepted) < limit:
                envelope = self._inbound.popleft()
                external_id = envelope.conversation_external_id
                conversation = PDDConversation(
                    conversation_id=(
                        "pdd-conversation-"
                        + hashlib.sha256(
                            f"{self.store_id}:{external_id}".encode()
                        ).hexdigest()[:32]
                    ),
                    external_id=external_id,
                    store_id=self.store_id,
                )
                mapped = self._mapper.map(envelope, conversation)
                dedupe = self._deduplicator.accept(mapped)
                if dedupe.status is PDDDeduplicationStatus.DUPLICATE:
                    self.duplicate_count += 1
                    continue
                accepted.append(mapped.message)
                self.received_count += 1
                previous = self._conversations.get(mapped.message.conversation_id)
                participants = set(previous.participant_ids if previous else ())
                participants.add(mapped.message.sender)
                self._conversations[mapped.message.conversation_id] = (
                    ChannelConversation(
                        channel=self.channel,
                        conversation_id=mapped.message.conversation_id,
                        participant_ids=tuple(sorted(participants)),
                        message_count=(previous.message_count if previous else 0) + 1,
                        last_message_at=mapped.message.timestamp,
                    )
                )
        return tuple(accepted)

    def get_conversation(
        self, conversation_id: str
    ) -> ChannelConversation | None:
        with self._lock:
            return self._conversations.get(conversation_id)

    def capture_state(self) -> PDDBrowserPageState:
        self._assert_selector_verified()
        return self._browser.capture_state()

    def health_check(self) -> AdapterHealth:
        browser = self._browser.health_check()
        session_connected = (
            self._session is not None
            and self._session.status is PDDSessionStatus.CONNECTED
        )
        selector_verified = self._selector_state is PDDSelectorState.VERIFIED
        healthy = (
            browser.status is PDDBrowserHealthState.HEALTHY
            and session_connected
            and selector_verified
        )
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=(
                AdapterHealthStatus.HEALTHY
                if healthy
                else AdapterHealthStatus.DEGRADED
            ),
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "mode": "OFFLINE_PROTOTYPE_OBSERVE_ONLY",
                "store_bound": True,
                "session_connected": session_connected,
                "page_available": browser.page_available,
                "selector_state": self._selector_state.value,
                "mapping_contract": PDDMessageMapper.mapping_contract_id,
                "pending_count": self.pending_count,
                "received_count": self.received_count,
                "duplicate_count": self.duplicate_count,
                "write_capability_enabled": False,
                "real_platform_connected": False,
            },
        )

    def simulate_selector_state(self, state: PDDSelectorState) -> None:
        self._selector_state = state

    def simulate_page_unavailable(self) -> None:
        browser = self._browser
        if not isinstance(browser, FakePDDBrowserAdapter):
            raise PDDPrototypeUnavailable("page simulation requires the fake browser")
        browser.simulate_page_unavailable()

    def simulate_session_state(self, status: PDDSessionStatus) -> None:
        with self._lock:
            if self._session is None:
                raise PDDPrototypeUnavailable("PDD prototype session is not open")
            self._session = self._session.model_copy(
                update={"status": status, "last_seen": self._clock()}
            )

    def _assert_selector_verified(self) -> None:
        if self._selector_state is not PDDSelectorState.VERIFIED:
            raise PDDPrototypeUnavailable(
                "PDD selector contract is not VERIFIED; observation fails closed"
            )

    def _assert_observation_ready(self) -> None:
        self._assert_selector_verified()
        if (
            self._session is None
            or self._session.status is not PDDSessionStatus.CONNECTED
        ):
            raise PDDPrototypeUnavailable("PDD prototype session is not CONNECTED")
        browser = self._browser.health_check()
        if browser.status is not PDDBrowserHealthState.HEALTHY:
            raise PDDPrototypeUnavailable("PDD prototype page is unavailable")


__all__ = ["FakePDDAdapter", "PDDPrototypeUnavailable"]
