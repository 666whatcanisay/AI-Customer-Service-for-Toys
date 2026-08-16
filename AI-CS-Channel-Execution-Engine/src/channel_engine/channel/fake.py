from __future__ import annotations

from .adapter_foundation import FakeChannelAdapter, FakeChannelInbound
from .protocol import NormalizedMessage


class FakeChannel(FakeChannelAdapter):
    """Compatibility name backed by the managed ChannelAdapter V1 fake."""

    def __init__(self) -> None:
        super().__init__(channel="fake", store_id="fake-store")
        self.connect()

    def enqueue(self, message: NormalizedMessage) -> None:
        if message.channel != self.channel:
            raise ValueError("legacy message channel does not match fake adapter")
        self.enqueue_message(
            FakeChannelInbound(
                message_id=message.external_message_id,
                conversation_id=message.conversation_id,
                sender=message.sender,
                content=message.content,
                timestamp=message.timestamp,
            )
        )

    def receive(self) -> NormalizedMessage | None:
        message = self.receive_message()
        if message is None:
            return None
        # Preserve the Foundation-era compatibility contract. Store routing is
        # carried by ChannelMessageV1 in the managed adapter path.
        return message.model_copy(update={"store_id": None})
