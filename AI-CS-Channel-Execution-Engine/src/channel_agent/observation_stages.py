from __future__ import annotations

from enum import StrEnum


class ObservationStage(StrEnum):
    """Monotonic RC4 observation-chain activation stages.

    Stages deliberately stop before any platform write.  Moving to a later
    stage only enables more of the read/Host/assistant path; it never enables
    automatic reply, execution, or PDD transport.
    """

    DISABLED = "DISABLED"
    CONVERSATION_LIST = "CONVERSATION_LIST"
    MESSAGE_CAPTURE = "MESSAGE_CAPTURE"
    HOST_INGEST = "HOST_INGEST"
    ASSISTANT_FEED = "ASSISTANT_FEED"
    AI_SUGGESTIONS = "AI_SUGGESTIONS"

    @property
    def rank(self) -> int:
        return _STAGE_ORDER[self]

    def allows(self, required: "ObservationStage") -> bool:
        return self.rank >= required.rank


_STAGE_ORDER = {
    ObservationStage.DISABLED: 0,
    ObservationStage.CONVERSATION_LIST: 1,
    ObservationStage.MESSAGE_CAPTURE: 2,
    ObservationStage.HOST_INGEST: 3,
    ObservationStage.ASSISTANT_FEED: 4,
    ObservationStage.AI_SUGGESTIONS: 5,
}


__all__ = ["ObservationStage"]
