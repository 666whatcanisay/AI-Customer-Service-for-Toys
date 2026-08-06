from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from threading import Lock
from typing import Protocol, runtime_checkable

from pydantic import Field, model_validator

from channel_engine.channel import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    LedgerExecutionAuthorizationService,
)
from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.models import ReceiptOutcome

from .models import BrowserModel, BrowserPageContext
from .selectors import (
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorContractUnavailable,
    SelectorRegistry,
)


class BrowserActionPhase(StrEnum):
    VALIDATED = "VALIDATED"
    COMPOSER_FILLED = "COMPOSER_FILLED"
    SEND_TRIGGERED = "SEND_TRIGGERED"
    CONFIRMED = "CONFIRMED"


class BrowserExecutionMode(StrEnum):
    CONTROLLED_HUMAN_APPROVAL = "CONTROLLED_HUMAN_APPROVAL"


class BrowserSendAction(BrowserModel):
    mode: BrowserExecutionMode = BrowserExecutionMode.CONTROLLED_HUMAN_APPROVAL
    authorized: AuthorizedOutboundMessage
    page: BrowserPageContext
    selector_contract_id: str = Field(min_length=1, max_length=256)
    selector_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class BrowserActionResult(BrowserModel):
    outcome: ReceiptOutcome
    phase: BrowserActionPhase
    external_message_id: str | None = Field(default=None, max_length=255)
    error_code: str | None = Field(default=None, max_length=128)
    page_revision_after: str | None = Field(default=None, max_length=128)
    real_browser_called: bool
    customer_message_sent: bool
    simulation_only: bool = False

    @model_validator(mode="after")
    def validate_outcome(self) -> BrowserActionResult:
        if self.outcome is ReceiptOutcome.SUCCESS:
            if (
                self.phase is not BrowserActionPhase.CONFIRMED
                or self.error_code is not None
                or self.external_message_id is None
            ):
                raise ValueError("SUCCESS requires confirmed external evidence")
            if not self.customer_message_sent and not self.simulation_only:
                raise ValueError("real SUCCESS must confirm customer message delivery")
        elif self.error_code is None:
            raise ValueError("FAILED and UNKNOWN require an error code")
        if self.outcome is ReceiptOutcome.UNKNOWN and self.phase not in {
            BrowserActionPhase.SEND_TRIGGERED,
            BrowserActionPhase.CONFIRMED,
        }:
            raise ValueError("UNKNOWN is reserved for post-trigger uncertainty")
        if self.outcome is ReceiptOutcome.FAILED and self.phase in {
            BrowserActionPhase.SEND_TRIGGERED,
            BrowserActionPhase.CONFIRMED,
        }:
            raise ValueError("post-trigger failure must be classified UNKNOWN")
        if self.outcome is ReceiptOutcome.FAILED and self.customer_message_sent:
            raise ValueError("FAILED cannot claim a sent customer message")
        return self


@runtime_checkable
class BrowserPageRouter(Protocol):
    def route(self, conversation_id: str) -> BrowserPageContext | None:
        """Resolve an ACTIVE isolated page for the approved conversation."""


@runtime_checkable
class BrowserActionPort(Protocol):
    def execute(self, action: BrowserSendAction) -> BrowserActionResult:
        """Infrastructure write port. It must never bypass ledger authorization."""


class ControlledOutboundBrowserExecutor:
    """Lease-fenced Execution Adapter; it contains no Playwright implementation."""

    def __init__(
        self,
        authorization_service: LedgerExecutionAuthorizationService,
        page_router: BrowserPageRouter,
        selector_registry: SelectorRegistry,
        action_port: BrowserActionPort,
    ) -> None:
        self.authorization_service = authorization_service
        self.page_router = page_router
        self.selector_registry = selector_registry
        self.action_port = action_port
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        del command
        raise ExecutionBoundaryDenied(
            "browser execution requires a claimed Execution and active lease"
        )

    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        self.call_count += 1
        if (
            command.execution_id != context.execution_id
            or command.decision_id != context.decision_id
        ):
            return self._denied("BROWSER_EXECUTION_CONTEXT_MISMATCH")
        try:
            authorized = self.authorization_service.issue(
                execution_id=context.execution_id,
                worker_id=context.worker_id,
                execution_lease_token=context.lease_token,
            )
            self.authorization_service.verify(authorized)
            if (
                authorized.authorization.approval_id != context.approval_id
                or authorized.authorization.approved_by != context.approved_by
                or authorized.message.content != command.proposed_content
                or authorized.message.idempotency_key != command.idempotency_key
            ):
                return self._denied("BROWSER_EXECUTION_CONTEXT_MISMATCH")
            page = self.page_router.route(authorized.message.conversation_id)
            if page is None:
                return self._denied("BROWSER_PAGE_CONTEXT_UNAVAILABLE")
            contract = self.selector_registry.get(
                page.platform, page.page, page.selector_contract_version
            )
            if (
                contract.state is not SelectorContractState.VERIFIED
                or SelectorCapability.SEND_MESSAGE not in contract.capabilities
            ):
                return self._denied("BROWSER_SELECTOR_CONTRACT_NOT_SEND_VERIFIED")
            action = BrowserSendAction(
                authorized=authorized,
                page=page,
                selector_contract_id=contract.contract_id,
                selector_fingerprint=contract.fingerprint(),
            )
        except ExecutionBoundaryDenied:
            return self._denied("BROWSER_SEND_AUTHORIZATION_DENIED")
        except SelectorContractUnavailable:
            return self._denied("BROWSER_SELECTOR_CONTRACT_UNAVAILABLE")
        except Exception:
            return self._denied("BROWSER_PREFLIGHT_FAILED")

        try:
            result = self.action_port.execute(action)
        except Exception as exc:
            return ExecutionResult(
                outcome=ReceiptOutcome.UNKNOWN,
                error_code="BROWSER_ACTION_EXCEPTION_UNKNOWN",
                details={
                    "mode": BrowserExecutionMode.CONTROLLED_HUMAN_APPROVAL.value,
                    "failure_type": type(exc).__name__,
                    "automatic_reply": False,
                    "automatic_retry_allowed": False,
                    "human_takeover_required": True,
                    "real_browser_called": False,
                    "customer_message_sent": False,
                },
            )
        return ExecutionResult(
            outcome=result.outcome,
            external_reference=result.external_message_id,
            error_code=result.error_code,
            details={
                "mode": BrowserExecutionMode.CONTROLLED_HUMAN_APPROVAL.value,
                "browser_action_phase": result.phase.value,
                "selector_contract_id": contract.contract_id,
                "selector_fingerprint": contract.fingerprint(),
                "page_revision_after": result.page_revision_after,
                "decision_id": authorized.authorization.decision_id,
                "approval_id": authorized.authorization.approval_id,
                "human_approval_verified": True,
                "execution_lease_verified": True,
                "automatic_reply": False,
                "automatic_retry_allowed": (
                    result.outcome is ReceiptOutcome.FAILED
                    and result.phase
                    in {
                        BrowserActionPhase.VALIDATED,
                        BrowserActionPhase.COMPOSER_FILLED,
                    }
                ),
                "human_takeover_required": result.outcome is ReceiptOutcome.UNKNOWN,
                "real_browser_called": result.real_browser_called,
                "customer_message_sent": result.customer_message_sent,
                "simulation_only": result.simulation_only,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": BrowserExecutionMode.CONTROLLED_HUMAN_APPROVAL.value,
                "automatic_reply": False,
                "automatic_retry_allowed": False,
                "human_takeover_required": True,
                "real_browser_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
                "payment_performed": False,
            },
        )


class FakeBrowserPageRouter:
    def __init__(self) -> None:
        self._pages: dict[str, BrowserPageContext] = {}

    def bind(self, conversation_id: str, page: BrowserPageContext) -> None:
        self._pages[conversation_id] = page

    def route(self, conversation_id: str) -> BrowserPageContext | None:
        return self._pages.get(conversation_id)


class FakeBrowserActionPort:
    """Idempotent offline action port. It never invokes a real browser."""

    def __init__(
        self,
        outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
    ) -> None:
        self.outcome = outcome
        self.call_count = 0
        self.real_browser_called = False
        self._results: dict[str, tuple[str, BrowserActionResult]] = {}
        self._lock = Lock()

    def execute(self, action: BrowserSendAction) -> BrowserActionResult:
        key = action.authorized.message.idempotency_key
        fingerprint = hashlib.sha256(
            json.dumps(
                action.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self._lock:
            existing = self._results.get(key)
            if existing is not None:
                if existing[0] != fingerprint:
                    raise ValueError("browser action idempotency conflict")
                return existing[1]
            self.call_count += 1
            result = {
                ReceiptOutcome.SUCCESS: BrowserActionResult(
                    outcome=ReceiptOutcome.SUCCESS,
                    phase=BrowserActionPhase.CONFIRMED,
                    external_message_id=f"mock-browser-{key}",
                    page_revision_after=action.page.page_revision,
                    real_browser_called=False,
                    customer_message_sent=False,
                    simulation_only=True,
                ),
                ReceiptOutcome.FAILED: BrowserActionResult(
                    outcome=ReceiptOutcome.FAILED,
                    phase=BrowserActionPhase.VALIDATED,
                    error_code="MOCK_BROWSER_PRECONDITION_FAILED",
                    page_revision_after=action.page.page_revision,
                    real_browser_called=False,
                    customer_message_sent=False,
                    simulation_only=True,
                ),
                ReceiptOutcome.UNKNOWN: BrowserActionResult(
                    outcome=ReceiptOutcome.UNKNOWN,
                    phase=BrowserActionPhase.SEND_TRIGGERED,
                    error_code="MOCK_BROWSER_CONFIRMATION_UNKNOWN",
                    page_revision_after=action.page.page_revision,
                    real_browser_called=False,
                    customer_message_sent=False,
                    simulation_only=True,
                ),
            }[self.outcome]
            self._results[key] = (fingerprint, result)
            return result


__all__ = [
    "BrowserActionPhase",
    "BrowserActionPort",
    "BrowserActionResult",
    "BrowserExecutionMode",
    "BrowserPageRouter",
    "BrowserSendAction",
    "ControlledOutboundBrowserExecutor",
    "FakeBrowserActionPort",
    "FakeBrowserPageRouter",
]
