from __future__ import annotations

from collections import deque

from .protocol import ChannelMessage


class FakeChannel:
    def __init__(self) -> None:
        self._messages: deque[ChannelMessage] = deque()

    def enqueue(self, message: ChannelMessage) -> None:
        self._messages.append(message)

    def receive(self) -> ChannelMessage | None:
        if not self._messages:
            return None
        return self._messages.popleft()

    @property
    def pending_count(self) -> int:
        return len(self._messages)
