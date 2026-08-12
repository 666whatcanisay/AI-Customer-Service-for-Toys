from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.channel.execution_boundary import (
    LedgerExecutionAuthorizationService,
)
from channel_engine.customer_assistant import (
    HumanSendConfirmation,
    SQLiteConversationBuffer,
)
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import ReceiptOutcome
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork

from .pdd_workspace import ExistingPDDWorkspaceObserver
from .pdd_workspace_send import (
    ControlledPDDWorkspaceBrowserSender,
    ControlledPDDWorkspaceExecutionAdapter,
)
from .controlled_send_grant import (
    ControlledSendGrantError,
    ControlledSendGrantStore,
    ControlledSendGrantV1,
)


class ApprovedReplyBridgeError(RuntimeError):
    def __init__(self, message: str, *, error_code: str, status_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class ApprovedReplyModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ApprovedReplyRequest(ApprovedReplyModel):
    contract_version: Literal["1.1"] = "1.1"
    decision_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_message_id: str = Field(min_length=1, max_length=255)
    reply_text: str = Field(min_length=1, max_length=8_000, repr=False)
    operator_reference: str = Field(min_length=1, max_length=160)
    confirmation_phrase: str = Field(min_length=1, max_length=512, repr=False)
    idempotency_key: str = Field(min_length=1, max_length=255)
    confirmed_at: AwareDatetime
    controlled_send_grant: ControlledSendGrantV1


class ApprovedReplyResponse(ApprovedReplyModel):
    contract_version: Literal["1.1"] = "1.1"
    decision_id: str
    approval_id: str
    execution_id: str
    receipt_id: str
    outcome: Literal["SUCCESS", "FAILED", "UNKNOWN"]
    customer_message_sent: bool | None
    automatic_retry_allowed: Literal[False] = False
    manual_intervention_required: bool
    error_code: str | None = None


class ApprovedReplyService:
    """Local-only manual approval boundary for one exact AI reply."""

    def __init__(
        self,
        *,
        feed_path: str | Path,
        buffer: SQLiteConversationBuffer,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        observer: ExistingPDDWorkspaceObserver,
        browser_sender: ControlledPDDWorkspaceBrowserSender,
        controlled_send_grant_store: ControlledSendGrantStore,
        controlled_send_enabled: bool,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.feed_path = Path(feed_path)
        self._buffer = buffer
        self._uow_factory = uow_factory
        self._observer = observer
        self._browser_sender = browser_sender
        self._grant_store = controlled_send_grant_store
        self._enabled = controlled_send_enabled
        self._clock = clock
        self._lock = RLock()

    def health(self) -> dict[str, object]:
        return {
            "service": "channel-agent-approved-reply-bridge",
            "version": "1.1",
            "controlled_send_enabled": self._enabled,
            "auto_reply_enabled": False,
            "manual_approval_required": True,
            "edge_lifecycle_owned": False,
        }

    def approve_and_send(
        self,
        request: ApprovedReplyRequest,
    ) -> ApprovedReplyResponse:
        with self._lock:
            if not self._enabled:
                raise ApprovedReplyBridgeError(
                    "controlled PDD send is not explicitly enabled",
                    error_code="PDD_CONTROLLED_SEND_DISABLED",
                    status_code=403,
                )
            if request.confirmed_at.astimezone(UTC) < self._clock().astimezone(UTC) - timedelta(minutes=5):
                raise ApprovedReplyBridgeError(
                    "human confirmation expired",
                    error_code="PDD_SEND_CONFIRMATION_EXPIRED",
                    status_code=409,
                )
            expected_key = f"pdd-controlled-send:{request.decision_id}"
            if request.idempotency_key != expected_key:
                raise ApprovedReplyBridgeError(
                    "controlled send idempotency key does not match the decision",
                    error_code="PDD_SEND_IDEMPOTENCY_KEY_MISMATCH",
                    status_code=409,
                )

            feed = self._load_feed()
            reply = feed.get("reply")
            if not isinstance(reply, dict):
                raise ApprovedReplyBridgeError(
                    "AI reply is no longer available",
                    error_code="PDD_SEND_REPLY_NOT_AVAILABLE",
                    status_code=409,
                )
            if (
                reply.get("decisionId") != request.decision_id
                or reply.get("conversationId") != request.conversation_id
                or reply.get("messageId") != request.customer_message_id
                or reply.get("answer") != request.reply_text
                or reply.get("state") != "WAITING_APPROVAL"
            ):
                raise ApprovedReplyBridgeError(
                    "the confirmed reply does not match the current AI package",
                    error_code="PDD_SEND_REPLY_PACKAGE_MISMATCH",
                    status_code=409,
                )

            stored = self._buffer.load_reply(request.decision_id)
            if stored is None:
                raise ApprovedReplyBridgeError(
                    "durable AI reply package is missing",
                    error_code="PDD_SEND_DURABLE_REPLY_MISSING",
                    status_code=409,
                )
            context, package = stored
            if (
                package.state != "WAITING_APPROVAL"
                or package.reply_content != request.reply_text
                or package.conversation_id != request.conversation_id
            ):
                raise ApprovedReplyBridgeError(
                    "durable AI reply package does not match",
                    error_code="PDD_SEND_DURABLE_REPLY_MISMATCH",
                    status_code=409,
                )

            snapshot = self._observer.capture()
            confirmation = HumanSendConfirmation(
                decision_id=request.decision_id,
                operator_id=request.operator_reference,
                expected_store_id=package.store_id,
                expected_conversation_id=package.conversation_id,
                expected_customer_reference=package.customer_reference,
                current_store_id=snapshot.store_id,
                current_conversation_id=snapshot.conversation_id,
                current_customer_reference=snapshot.customer_reference,
                confirmation_phrase=request.confirmation_phrase,
                confirmed_at=request.confirmed_at,
            )
            try:
                confirmation.assert_exact_target()
            except ValueError as exc:
                raise ApprovedReplyBridgeError(
                    "current PDD target does not match the human confirmation",
                    error_code="PDD_SEND_CURRENT_TARGET_MISMATCH",
                    status_code=409,
                ) from exc
            if context.page.product.product_reference != snapshot.product.product_reference:
                raise ApprovedReplyBridgeError(
                    "current PDD product changed after AI generation",
                    error_code="PDD_SEND_PRODUCT_CHANGED",
                    status_code=409,
                )

            try:
                self._grant_store.consume_once(
                    request.controlled_send_grant,
                    store_id=package.store_id,
                    test_buyer_hash=package.customer_reference,
                    conversation_id=package.conversation_id,
                    customer_message_id=request.customer_message_id,
                    decision_id=request.decision_id,
                    reply_content=request.reply_text,
                    now=self._clock(),
                )
            except ControlledSendGrantError as exc:
                raise ApprovedReplyBridgeError(
                    "controlled send grant is invalid or already consumed",
                    error_code="PDD_CONTROLLED_SEND_GRANT_REJECTED",
                    status_code=409,
                ) from exc

            coordinator = ExecutionCoordinator(
                self._uow_factory,
                ApprovalPolicy(),
            )
            adapter = ControlledPDDWorkspaceExecutionAdapter(
                authorization_service=LedgerExecutionAuthorizationService(
                    self._uow_factory,
                    clock=self._clock,
                ),
                sender=self._browser_sender,
                expected_store_id=package.store_id,
                expected_conversation_id=package.conversation_id,
                expected_customer_reference=package.customer_reference,
                expected_customer_message_id=request.customer_message_id,
                expected_content=request.reply_text,
            )
            worker = ExecutionWorker(
                self._uow_factory,
                adapter,
                worker_id=f"channel-agent-approved-send-{request.decision_id[-24:]}",
                policy=ApprovalPolicy(),
                lease_duration=timedelta(seconds=30),
                clock=self._clock,
            )
            enqueued = coordinator.approve_and_enqueue(
                request.decision_id,
                request.operator_reference,
            )
            worker.run_execution(enqueued.execution_id)
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                execution = repo.get_execution(enqueued.execution_id)
                receipt = repo.get_receipt_for_execution(enqueued.execution_id)
            if receipt is None:
                raise ApprovedReplyBridgeError(
                    "execution stopped without an immutable receipt",
                    error_code="PDD_SEND_RECEIPT_MISSING",
                    status_code=500,
                )
            customer_message_sent = receipt.details.get("customer_message_sent")
            if customer_message_sent not in {True, False, None}:
                raise ApprovedReplyBridgeError(
                    "execution receipt contains an invalid send fact",
                    error_code="PDD_SEND_RECEIPT_FACT_INVALID",
                    status_code=500,
                )
            if receipt.outcome is ReceiptOutcome.SUCCESS:
                if not customer_message_sent:
                    raise ApprovedReplyBridgeError(
                        "successful receipt did not confirm the PDD message",
                        error_code="PDD_SEND_RECEIPT_CONFIRMATION_MISSING",
                        status_code=500,
                    )
                self._buffer.complete(package.turn_id)
            else:
                self._buffer.mark_manual_intervention(
                    package.turn_id,
                    reason_code=f"EXECUTION_{receipt.outcome.value}",
                )
            return ApprovedReplyResponse(
                decision_id=request.decision_id,
                approval_id=enqueued.approval_id,
                execution_id=execution.execution_id,
                receipt_id=receipt.receipt_id,
                outcome=receipt.outcome.value,
                customer_message_sent=customer_message_sent,
                manual_intervention_required=receipt.outcome is not ReceiptOutcome.SUCCESS,
                error_code=(
                    str(receipt.details.get("error_code"))
                    if receipt.details.get("error_code")
                    else None
                ),
            )

    def _load_feed(self) -> dict[str, object]:
        try:
            value = json.loads(self.feed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ApprovedReplyBridgeError(
                "Channel Agent feed is unavailable",
                error_code="PDD_SEND_FEED_UNAVAILABLE",
                status_code=503,
            ) from exc
        if not isinstance(value, dict):
            raise ApprovedReplyBridgeError(
                "Channel Agent feed is invalid",
                error_code="PDD_SEND_FEED_INVALID",
                status_code=503,
            )
        safety = value.get("safety")
        if not isinstance(safety, dict) or safety.get("autoReply") is not False:
            raise ApprovedReplyBridgeError(
                "Channel Agent feed safety state is invalid",
                error_code="PDD_SEND_FEED_SAFETY_INVALID",
                status_code=503,
            )
        return value


__all__ = [
    "ApprovedReplyBridgeError",
    "ApprovedReplyRequest",
    "ApprovedReplyResponse",
    "ApprovedReplyService",
]
