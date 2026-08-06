from __future__ import annotations

from typing import Protocol

from .contract import DecisionRequest, DecisionResponse


class AICSGateway(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """Return a decision proposal without executing channel actions."""


class GatewayUnavailable(RuntimeError):
    pass


class IdempotencyConflict(ValueError):
    """The same idempotency key was reused with a different request body."""
