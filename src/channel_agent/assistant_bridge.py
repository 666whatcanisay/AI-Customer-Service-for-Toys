from __future__ import annotations

import hashlib
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

from .controlled_send_grant import (
    ControlledAutoPolicyGrantV1,
    ControlledPilotSendWindowStore,
    ControlledSendGrant,
    ControlledSendGrantError,
    ControlledSendGrantStore,
    ControlledSendGrantV1,
    normalized_question_sha256,
)
from .pdd_workspace import ExistingPDDWorkspaceObserver
from .pdd_workspace_send import (
    ControlledPDDWorkspaceBrowserSender,
    ControlledPDDWorkspaceExecutionAdapter,
)

ApprovedReplyIntent = Literal["HUMAN_CONFIRMED_SEND", "AUTO_POLICY_PILOT_SEND"]


def knowledge_scope_sha256(package) -> str:
    """Bind a Pilot authorization to the exact knowledge evidence used by AI."""

    material = {
        "gateway_version": package.gateway_version,
        "citations": [
            {
                "reference": item.reference,
                "title": item.title,
                "excerpt": item.excerpt,
                "product_id": item.product_id,
                "sku_id": item.sku_id,
                "source_kind": item.source_kind,
            }
            for item in package.citations
        ],
    }
    canonical = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
    controlled_send_grant: ControlledSendGrantV1 | ControlledAutoPolicyGrantV1


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
    authorization_kind: Literal["MANUAL_CONFIRM", "AUTO_POLICY"]
    pilot_window_id: str | None = None


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
        controlled_pilot_window_store: ControlledPilotSendWindowStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.feed_path = Path(feed_path)
        self._buffer = buffer
        self._uow_factory = uow_factory
        self._observer = observer
        self._browser_sender = browser_sender
        self._grant_store = controlled_send_grant_store
        self._pilot_windows = controlled_pilot_window_store
        self._enabled = controlled_send_enabled
        self._clock = clock
        self._lock = RLock()

    def health(self) -> dict[str, object]:
        active_window = (
            self._pilot_windows.active(now=self._clock())
            if self._pilot_windows is not None
            else None
        )
        return {
            "service": "channel-agent-approved-reply-bridge",
            "version": "1.1",
            "controlled_send_enabled": self._enabled,
            "production_real_send_enabled": False,
            "controlled_pilot_send_enabled": active_window is not None,
            "controlled_pilot_mode": active_window.mode if active_window else None,
            "auto_reply_enabled": False,
            "manual_approval_required": True,
            "edge_lifecycle_owned": False,
        }

    def approve_and_send(
        self,
        request: ApprovedReplyRequest,
        *,
        intent: ApprovedReplyIntent = "HUMAN_CONFIRMED_SEND",
    ) -> ApprovedReplyResponse:
        """Execute through the sole sender and fail-close any armed Pilot window."""

        window_id = request.controlled_send_grant.pilot_window_id
        try:
            return self._approve_and_send_locked(request, intent=intent)
        except Exception:
            # Once a one-shot Pilot authorization is presented, every terminal
            # failure consumes the opportunity.  A caller must never be able to
            # fix up a rejected request and reuse the same armed window.
            self._close_pilot_window_safely(window_id, reason="VALIDATION_OR_SEND_FAILED")
            raise

    def _approve_and_send_locked(
        self,
        request: ApprovedReplyRequest,
        *,
        intent: ApprovedReplyIntent,
    ) -> ApprovedReplyResponse:
        with self._lock:
            grant = request.controlled_send_grant
            expected_intent: ApprovedReplyIntent = (
                "AUTO_POLICY_PILOT_SEND"
                if isinstance(grant, ControlledAutoPolicyGrantV1)
                else "HUMAN_CONFIRMED_SEND"
            )
            if intent != expected_intent:
                raise ApprovedReplyBridgeError(
                    "approved-reply intent does not match the grant type",
                    error_code="PDD_SEND_INTENT_GRANT_MISMATCH",
                    status_code=403,
                )
            if not self._enabled:
                raise ApprovedReplyBridgeError(
                    "controlled PDD send is not explicitly enabled",
                    error_code="PDD_CONTROLLED_SEND_DISABLED",
                    status_code=403,
                )
            if request.confirmed_at.astimezone(UTC) < self._clock().astimezone(UTC) - timedelta(minutes=5):
                raise ApprovedReplyBridgeError(
                    "controlled send authorization expired",
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
            if context.page.product.sku_reference != snapshot.product.sku_reference:
                raise ApprovedReplyBridgeError(
                    "current PDD SKU changed after AI generation",
                    error_code="PDD_SEND_SKU_CHANGED",
                    status_code=409,
                )

            window_id: str | None = None
            if grant.pilot_window_id is not None:
                if self._pilot_windows is None:
                    raise ApprovedReplyBridgeError(
                        "controlled Pilot window state is unavailable",
                        error_code="PDD_CONTROLLED_PILOT_DISABLED",
                        status_code=403,
                    )
                try:
                    window = self._pilot_windows.assert_authorized(
                        grant,
                        question=package.customer_question,
                        product_id=context.page.product.product_reference,
                        sku_id=context.page.product.sku_reference,
                        knowledge_scope_sha256=knowledge_scope_sha256(package),
                        now=self._clock(),
                    )
                except ControlledSendGrantError as exc:
                    raise ApprovedReplyBridgeError(
                        "controlled Pilot scope or exact approved hash changed",
                        error_code="PDD_CONTROLLED_PILOT_SCOPE_MISMATCH",
                        status_code=409,
                    ) from exc
                window_id = window.window_id
            elif isinstance(grant, ControlledAutoPolicyGrantV1):
                raise ApprovedReplyBridgeError(
                    "AUTO Pilot requires an active one-shot window",
                    error_code="PDD_CONTROLLED_PILOT_DISABLED",
                    status_code=403,
                )

            if isinstance(grant, ControlledAutoPolicyGrantV1):
                self._assert_auto_policy_package(
                    feed_reply=reply,
                    package=package,
                    grant=grant,
                )

            try:
                response = self._execute_same_send_chain(
                    request=request,
                    grant=grant,
                    package=package,
                )
            except Exception:
                self._close_pilot_window_safely(window_id, reason="FAILED")
                raise
            if window_id is not None and self._pilot_windows is not None:
                if response.outcome == "SUCCESS" and response.customer_message_sent is True:
                    self._pilot_windows.consume_success(window_id, now=self._clock())
                else:
                    self._close_pilot_window_safely(
                        window_id,
                        reason=f"EXECUTION_{response.outcome}",
                    )
            return response

    def _execute_same_send_chain(
        self,
        *,
        request: ApprovedReplyRequest,
        grant: ControlledSendGrant,
        package,
    ) -> ApprovedReplyResponse:
        try:
            self._grant_store.consume_once(
                grant,
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

        coordinator = ExecutionCoordinator(self._uow_factory, ApprovalPolicy())
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
            authorization_kind=grant.authorization_kind,
            pilot_window_id=grant.pilot_window_id,
        )

    def _assert_auto_policy_package(
        self,
        *,
        feed_reply: dict[str, object],
        package,
        grant: ControlledAutoPolicyGrantV1,
    ) -> None:
        """Fail closed unless the new AI package is the exact approved low-risk answer."""

        reply_content = package.reply_content or ""
        reply_hash = hashlib.sha256(reply_content.encode("utf-8")).hexdigest()
        if (
            reply_hash != grant.reply_content_sha256
            or reply_hash != grant.approved_reply_sha256
        ):
            raise ApprovedReplyBridgeError(
                "the AUTO Pilot reply differs from the human-approved answer",
                error_code="REPLY_HASH_MISMATCH",
                status_code=409,
            )
        if normalized_question_sha256(package.customer_question) != (
            grant.normalized_question_sha256
        ):
            raise ApprovedReplyBridgeError(
                "the AUTO Pilot question differs from the approved question",
                error_code="QUESTION_HASH_MISMATCH",
                status_code=409,
            )
        if knowledge_scope_sha256(package) != grant.knowledge_scope_sha256:
            raise ApprovedReplyBridgeError(
                "the AUTO Pilot knowledge scope changed",
                error_code="KNOWLEDGE_SCOPE_MISMATCH",
                status_code=409,
            )
        quality_status = str(feed_reply.get("qualityStatus") or "").upper()
        policy_mode = str(feed_reply.get("policyMode") or "").upper()
        action = str(feed_reply.get("action") or "").upper()
        if (
            package.action != "SUGGEST_REPLY"
            or package.ai_cs_action != "DIRECT_ANSWER"
            or package.risk_level.value != "LOW"
            or package.state != "WAITING_APPROVAL"
            or quality_status != "PASS"
            or policy_mode != "AUTO_LOW_RISK"
            or action not in {"CONTROLLED_ANSWER", "DIRECT_ANSWER"}
        ):
            raise ApprovedReplyBridgeError(
                "the AI package is not eligible for the low-risk AUTO Pilot",
                error_code="AUTO_POLICY_QUALITY_GATE_BLOCKED",
                status_code=409,
            )

    def _close_pilot_window_safely(
        self,
        window_id: str | None,
        *,
        reason: str,
    ) -> None:
        if window_id is None or self._pilot_windows is None:
            return
        try:
            self._pilot_windows.close(window_id, reason=reason, now=self._clock())
        except ControlledSendGrantError:
            # The window may already have expired or been revoked. Either state is safe.
            return

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
    "ApprovedReplyIntent",
    "ApprovedReplyRequest",
    "ApprovedReplyResponse",
    "ApprovedReplyService",
    "knowledge_scope_sha256",
]
