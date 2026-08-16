from __future__ import annotations

import hashlib
import json
from threading import Lock

from channel_engine.models.enums import DecisionAction
from channel_engine.models.entities import new_id, utc_now

from .contract import DecisionRequest, DecisionResponse, GatewayRiskLevel
from .protocol import IdempotencyConflict


class FakeGateway:
    """Deterministic gateway used only by the Foundation environment."""

    version = "fake-gateway.v1"

    def __init__(self) -> None:
        self.call_count = 0
        self._responses: dict[str, tuple[str, DecisionResponse]] = {}
        self._lock = Lock()

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            replay = self._responses.get(request.idempotency_key)
            if replay is not None:
                original_fingerprint, original_response = replay
                if original_fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "idempotency key was reused with a different DecisionRequest"
                    )
                return original_response

            self.call_count += 1
            summary = " ".join(request.customer_message.split())[:120]
            response = DecisionResponse(
                contract_version=request.contract_version,
                request_id=request.request_id,
                idempotency_key=request.idempotency_key,
                correlation_id=request.correlation_id,
                decision_id=new_id("decision"),
                action=DecisionAction.SUGGEST_REPLY,
                proposed_content=f"[FAKE SUGGESTION] Received: {summary}",
                requires_approval=True,
                risk_level=GatewayRiskLevel.LOW,
                gateway_version=self.version,
                metadata={
                    "mode": "FAKE",
                    "request_id": request.request_id,
                    "real_ai_cs_called": False,
                },
                decided_at=utc_now(),
            )
            self._responses[request.idempotency_key] = (fingerprint, response)
            return response
