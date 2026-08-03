from __future__ import annotations

from channel_engine.models.enums import DecisionAction

from .protocol import DecisionRequest, DecisionResponse


class FakeGateway:
    """Deterministic gateway used only by the Foundation environment."""

    version = "fake-gateway.v1"

    def __init__(self) -> None:
        self.call_count = 0

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.call_count += 1
        summary = " ".join(request.customer_message.split())[:120]
        return DecisionResponse(
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content=f"[FAKE SUGGESTION] Received: {summary}",
            requires_approval=True,
            gateway_version=self.version,
            metadata={
                "mode": "FAKE",
                "request_id": request.request_id,
                "real_ai_cs_called": False,
            },
        )
