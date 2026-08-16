from __future__ import annotations

from channel_engine.channel import (
    AdapterHealth,
    AdapterHealthStatus,
    AuthorizedOutboundMessage,
    ChannelConversation,
)
from channel_engine.models.entities import utc_now

from .models import BrowserSession, BrowserSessionState
from .observer import ReceiveOnlyPageObserver
from .ports import BrowserExecutionDisabled
from .session import BrowserSessionManager


class MockPDDBrowserAdapter:
    """Receive-only Browser Adapter shape backed exclusively by offline fakes."""

    channel = "pdd"
    adapter_name = "MockPDDBrowserAdapterV1"

    def __init__(
        self,
        session_manager: BrowserSessionManager,
        observer: ReceiveOnlyPageObserver,
    ) -> None:
        self.session_manager = session_manager
        self.observer = observer
        self._conversations: dict[str, ChannelConversation] = {}
        self.receive_count = 0
        self.send_call_count = 0

    def connect(self) -> BrowserSession:
        return self.session_manager.start()

    def disconnect(self) -> BrowserSession:
        return self.session_manager.stop()

    def heartbeat(self) -> BrowserSession:
        return self.session_manager.heartbeat()

    def receive_message(self):
        message = self.observer.receive_message()
        if message is None:
            return None
        self.receive_count += 1
        current = self._conversations.get(message.conversation_id)
        self._conversations[message.conversation_id] = ChannelConversation(
            channel=message.channel,
            conversation_id=message.conversation_id,
            participant_ids=(message.sender,),
            message_count=(current.message_count + 1 if current else 1),
            last_message_at=message.timestamp,
        )
        return message

    def send_message(self, command: AuthorizedOutboundMessage):
        del command
        self.send_call_count += 1
        raise BrowserExecutionDisabled(
            "receive-only Browser Adapter cannot send; use claimed outbound executor"
        )

    def get_conversation(self, conversation_id: str) -> ChannelConversation | None:
        return self._conversations.get(conversation_id)

    def get_session(self) -> BrowserSession:
        return self.session_manager.snapshot()

    def health_check(self) -> AdapterHealth:
        session = self.session_manager.snapshot()
        status = {
            BrowserSessionState.ACTIVE: AdapterHealthStatus.HEALTHY,
            BrowserSessionState.DEGRADED: AdapterHealthStatus.DEGRADED,
        }.get(session.state, AdapterHealthStatus.UNHEALTHY)
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=status,
            checked_at=utc_now(),
            real_platform_connected=False,
            details={
                "mode": "RECEIVE_ONLY",
                "browser_session_state": session.state.value,
                "login_state": session.login_state.value,
                "selector_contract_version": (
                    session.page_context.selector_contract_version
                    if session.page_context is not None
                    else None
                ),
                "human_takeover_required": session.human_takeover_required,
                "real_browser_started": False,
            },
        )


__all__ = ["MockPDDBrowserAdapter"]
