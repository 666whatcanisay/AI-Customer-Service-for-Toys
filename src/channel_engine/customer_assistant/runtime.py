from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime

from channel_engine.channel import NormalizedMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.gateway import (
    AICSGateway,
    DecisionRequest,
    DecisionResponse,
    GatewayRiskLevel,
)
from channel_engine.models import DecisionState, ReceiptOutcome
from channel_engine.pdd_adapter import PDDPrivacyFilteredMessage
from channel_engine.storage import SqlAlchemyUnitOfWork

from .auto_first_response import StoreApprovedAutoFirstResponseGateway
from .buffer import SQLiteConversationBuffer
from .context import CustomerContextCollector
from .models import (
    AIReplyPackage,
    AssistantExecutionResult,
    AssistantWorkState,
    BufferedCustomerMessage,
    BufferedMessageDisposition,
    ConversationTurn,
    CustomerContext,
    CustomerServiceRuntimeState,
    DesktopAssistantSnapshot,
    HumanSendConfirmation,
    KnowledgeCitation,
)


class CustomerAssistantSafetyError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class CustomerServiceLifecycleProjector:
    """Projects Browser/PDD observations into a product-facing runtime state."""

    @staticmethod
    def project(
        *,
        browser_status: str,
        pdd_login_state: str | None,
        reason_code: str | None = None,
        observation_active: bool = False,
    ) -> CustomerServiceRuntimeState:
        if browser_status in {"FAILED", "DEGRADED", "STOPPED"}:
            return (
                CustomerServiceRuntimeState.STOPPED
                if browser_status == "STOPPED"
                else CustomerServiceRuntimeState.HUMAN_INTERVENTION
            )
        if reason_code and any(
            marker in reason_code
            for marker in ("CAPTCHA", "RISK_CONTROL", "PAGE_CHANGED", "LOGIN_FAILED")
        ):
            return CustomerServiceRuntimeState.HUMAN_INTERVENTION
        if pdd_login_state in {None, "PDD_LOGIN_PAGE", "WAITING_QR_SCAN"}:
            return CustomerServiceRuntimeState.PDD_LOGIN_REQUIRED
        if pdd_login_state in {"PDD_LOGIN_SUCCESS", "OPENING_CUSTOMER_SERVICE"}:
            return CustomerServiceRuntimeState.PDD_AUTHENTICATED
        if pdd_login_state == "CUSTOMER_SERVICE_READY":
            return (
                CustomerServiceRuntimeState.CUSTOMER_SERVICE_RUNNING
                if observation_active
                else CustomerServiceRuntimeState.CUSTOMER_SERVICE_READY
            )
        return CustomerServiceRuntimeState.HUMAN_INTERVENTION


class _CapturingGateway:
    def __init__(self, delegate: AICSGateway) -> None:
        self._delegate = delegate
        self.response: DecisionResponse | None = None

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        response = self._delegate.decide(request)
        self.response = response
        return response


class AICustomerReplyService:
    """Maps CustomerContext to frozen Gateway V1 without generating local AI text."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        gateway: AICSGateway,
        *,
        clock: Callable[[], AwareDatetime],
        auto_first_response_enabled: bool = False,
    ) -> None:
        self._uow_factory = uow_factory
        self._auto_first_response_enabled = auto_first_response_enabled
        self._gateway = (
            StoreApprovedAutoFirstResponseGateway(gateway, clock=clock)
            if auto_first_response_enabled
            else gateway
        )
        self._clock = clock

    def generate(self, context: CustomerContext) -> AIReplyPackage:
        capture = _CapturingGateway(self._gateway)
        gateway_context = context.gateway_context()
        if self._auto_first_response_enabled:
            gateway_context["auto_first_response_policy"] = "AUTO_ALL_MESSAGES_V1"
        conversation = ConversationService(
            self._uow_factory,
            capture,
            decision_context_provider=lambda _message: dict(gateway_context),
        )
        # A verified context revision must create a new idempotent AI input.
        # Reusing only turn_id would replay a prior safe refusal after the
        # product knowledge context changes.
        external_message_id = "assistant-input:" + hashlib.sha256(
            context.context_id.encode("utf-8")
        ).hexdigest()
        intake = conversation.receive(
            NormalizedMessage(
                channel="pdd",
                store_id=context.store_id,
                conversation_id=context.conversation_id,
                external_message_id=external_message_id,
                sender="customer",
                content=context.current_question,
                timestamp=context.assembled_at,
            )
        )
        if (
            intake.decision_state is not DecisionState.WAITING_APPROVAL
            or not intake.requires_approval
        ):
            raise CustomerAssistantSafetyError(
                "AI reply did not stop at human approval",
                error_code="ASSISTANT_DECISION_NOT_WAITING_APPROVAL",
            )
        response = capture.response
        if response is None:
            # Idempotent replay after a process restart.  The core Decision is
            # durable, but Contract V1 metadata is not; fail to a higher risk and
            # an empty citation list instead of inventing evidence.
            request_id = f"decision-request-{intake.message_id}"
            risk_level = GatewayRiskLevel.HIGH
            citations: tuple[KnowledgeCitation, ...] = ()
            gateway_version = "decision-replay-without-metadata"
            action = "SUGGEST_REPLY" if intake.proposed_content else "NO_ACTION"
        else:
            request_id = response.request_id
            risk_level = response.risk_level
            citations = self._citations(response.metadata)
            gateway_version = response.gateway_version
            action = response.action.value
        metadata = response.metadata if response is not None else {}
        if (
            response is None
            and self._auto_first_response_enabled
            and intake.proposed_content
        ):
            recovery_hash = hashlib.sha256(
                (
                    f"auto-first-recovered-decision.v1\0{intake.decision_id}"
                    f"\0{context.context_id}\0{intake.proposed_content}"
                ).encode()
            ).hexdigest()
            metadata = {
                "ai_cs_action": "CONTROLLED_ANSWER",
                "quality_gate_status": "PASS",
                "warnings": ["DECISION_METADATA_RECOVERED"],
                "required_fields": [],
                "auto_authorization_basis": "STORE_APPROVED_FALLBACK",
                "reply_evidence_bundle": {"bundle_sha256": recovery_hash},
            }
        ai_cs_action = metadata.get("ai_cs_action")
        if not isinstance(ai_cs_action, str) or not ai_cs_action.strip():
            ai_cs_action = "UNKNOWN"
        warnings = metadata.get("warnings")
        if not isinstance(warnings, list) or not all(
            isinstance(item, str) and item.strip() for item in warnings
        ):
            warnings = []
        required_fields = metadata.get("required_fields")
        if not isinstance(required_fields, list) or not all(
            isinstance(item, str) and item.strip() for item in required_fields
        ):
            required_fields = []
        quality_gate_status = str(
            metadata.get("quality_gate_status") or "UNKNOWN"
        ).upper()
        if quality_gate_status not in {"PASS", "BLOCKED"}:
            quality_gate_status = "UNKNOWN"
        evidence_bundle_sha256: str | None = None
        raw_evidence = metadata.get("reply_evidence_bundle")
        if isinstance(raw_evidence, Mapping):
            raw_hash = raw_evidence.get("bundle_sha256")
            if (
                isinstance(raw_hash, str)
                and len(raw_hash) == 64
                and all(
                    character in "0123456789abcdef"
                    for character in raw_hash.lower()
                )
            ):
                evidence_bundle_sha256 = raw_hash.lower()
        auto_authorization_basis = str(
            metadata.get("auto_authorization_basis") or "QUALITY_GATED_LOW_RISK"
        ).upper()
        if auto_authorization_basis not in {
            "QUALITY_GATED_LOW_RISK",
            "STORE_APPROVED_KNOWLEDGE",
            "STORE_APPROVED_FIXED_REPLY",
            "STORE_APPROVED_FALLBACK",
        }:
            auto_authorization_basis = "QUALITY_GATED_LOW_RISK"
        return AIReplyPackage(
            turn_id=context.turn_id,
            context_id=context.context_id,
            request_id=request_id,
            decision_id=intake.decision_id,
            store_id=context.store_id,
            conversation_id=context.conversation_id,
            customer_reference=context.customer_reference,
            customer_question=context.current_question,
            action=action,
            reply_content=intake.proposed_content,
            citations=citations,
            risk_level=risk_level,
            ai_cs_action=ai_cs_action.strip()[:64],
            warnings=tuple(item.strip()[:128] for item in warnings[:32]),
            required_fields=tuple(item.strip()[:128] for item in required_fields[:32]),
            quality_gate_status=quality_gate_status,
            evidence_bundle_sha256=evidence_bundle_sha256,
            auto_authorization_basis=auto_authorization_basis,
            state=(
                "WAITING_APPROVAL"
                if action == "SUGGEST_REPLY"
                else "MANUAL_INTERVENTION"
            ),
            gateway_version=gateway_version,
            generated_at=self._clock(),
        )

    @staticmethod
    def _citations(metadata: Mapping[str, object]) -> tuple[KnowledgeCitation, ...]:
        raw = metadata.get("citations")
        if not isinstance(raw, list):
            return ()
        results: list[KnowledgeCitation] = []
        for index, item in enumerate(raw[:32], start=1):
            if isinstance(item, str) and item.strip():
                results.append(
                    KnowledgeCitation(reference=item.strip()[:512], title=f"知识来源 {index}")
                )
            elif isinstance(item, dict):
                reference = item.get("reference") or item.get("id")
                title = item.get("title")
                if isinstance(reference, str) and isinstance(title, str):
                    product_id = item.get("product_id")
                    sku_id = item.get("sku_id")
                    source_kind = item.get("source_kind")
                    excerpt = item.get("excerpt")
                    results.append(
                        KnowledgeCitation(
                            reference=reference.strip()[:512],
                            title=title.strip()[:256],
                            excerpt=(
                                excerpt.strip()[:1000]
                                if isinstance(excerpt, str) and excerpt.strip()
                                else None
                            ),
                            product_id=(
                                product_id.strip()[:160]
                                if isinstance(product_id, str) and product_id.strip()
                                else None
                            ),
                            sku_id=(
                                sku_id.strip()[:160]
                                if isinstance(sku_id, str) and sku_id.strip()
                                else None
                            ),
                            source_kind=(
                                source_kind.strip()[:64]
                                if isinstance(source_kind, str) and source_kind.strip()
                                else None
                            ),
                        )
                    )
        return tuple(results)


@runtime_checkable
class ExactExecutionRunner(Protocol):
    def run_execution(self, execution_id: str): ...


class CustomerAssistantRuntime:
    """Product flow orchestrator; real platform transport remains externally gated."""

    def __init__(
        self,
        buffer: SQLiteConversationBuffer,
        context_collector: CustomerContextCollector,
        reply_service: AICustomerReplyService,
        execution_coordinator: ExecutionCoordinator | None,
        execution_runner: ExecutionWorker | None,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        clock: Callable[[], AwareDatetime],
        real_send_enabled: bool = False,
    ) -> None:
        if real_send_enabled:
            raise CustomerAssistantSafetyError(
                "real send requires a separate production activation grant",
                error_code="ASSISTANT_REAL_SEND_NOT_ACTIVATED",
            )
        self._buffer = buffer
        self._contexts = context_collector
        self._replies = reply_service
        self._coordinator = execution_coordinator
        self._runner = execution_runner
        self._uow_factory = uow_factory
        self._clock = clock
        self._latest: AIReplyPackage | None = None
        self._latest_context: CustomerContext | None = None

    def ingest_redacted(
        self, message: PDDPrivacyFilteredMessage
    ) -> BufferedMessageDisposition:
        return self._buffer.append(
            BufferedCustomerMessage.from_redacted(
                store_id=message.store_id,
                conversation_id=message.conversation_id,
                external_message_id=message.external_message_id,
                content=message.content,
                timestamp=message.timestamp,
                received_at=message.captured_at,
            )
        )

    def generate_ready_reply(
        self,
        *,
        now: AwareDatetime | None = None,
        on_turn_claimed: Callable[[ConversationTurn], None] | None = None,
    ) -> AIReplyPackage | None:
        turn = self._buffer.claim_ready(now=now)
        if turn is None:
            return None
        try:
            if on_turn_claimed is not None:
                on_turn_claimed(turn)
            context = self._contexts.collect(turn)
            package = self._replies.generate(context)
            self._buffer.save_reply(turn.turn_id, context, package)
            if package.state == "MANUAL_INTERVENTION":
                self._buffer.mark_manual_intervention(
                    turn.turn_id,
                    reason_code="AI_CS_NO_ACTION",
                )
            self._latest = package
            self._latest_context = context
            return package
        except Exception as exc:
            reason = "".join(
                character if character.isalnum() else "_"
                for character in type(exc).__name__.upper()
            )[:80]
            self._buffer.release(turn.turn_id, reason_code=reason or "ASSISTANT_FAILURE")
            raise

    def stored_reply(
        self, decision_id: str
    ) -> tuple[CustomerContext, AIReplyPackage] | None:
        """Read the durable context/package pair for quality and preparation gates."""

        return self._buffer.load_reply(decision_id)

    def stored_replies(
        self,
    ) -> tuple[tuple[CustomerContext, AIReplyPackage], ...]:
        """Enumerate canonical durable replies for projection reconciliation."""

        return self._buffer.stored_replies()

    def purge_expired_content(
        self, *, retention: timedelta = timedelta(hours=24)
    ) -> dict[str, int]:
        return self._buffer.purge_expired(retention=retention)

    def confirm_and_execute(
        self, confirmation: HumanSendConfirmation
    ) -> AssistantExecutionResult:
        if self._coordinator is None or self._runner is None:
            raise CustomerAssistantSafetyError(
                "execution transport is disabled for read-only PDD integration",
                error_code="ASSISTANT_EXECUTION_TRANSPORT_DISABLED",
            )
        stored = self._buffer.load_reply(confirmation.decision_id)
        if stored is None:
            raise CustomerAssistantSafetyError(
                "reply package is not available for approval",
                error_code="ASSISTANT_REPLY_PACKAGE_NOT_FOUND",
            )
        _context, package = stored
        confirmation.assert_exact_target()
        if (
            confirmation.decision_id != package.decision_id
            or confirmation.expected_store_id != package.store_id
            or confirmation.expected_conversation_id != package.conversation_id
            or confirmation.expected_customer_reference != package.customer_reference
        ):
            raise CustomerAssistantSafetyError(
                "human confirmation does not match the AI reply package",
                error_code="ASSISTANT_CONFIRMATION_CONTEXT_MISMATCH",
            )
        enqueued = self._coordinator.approve_and_enqueue(
            package.decision_id,
            confirmation.operator_id,
        )
        result = self._runner.run_execution(enqueued.execution_id)
        if result is None:
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                receipt = repo.get_receipt_for_execution(enqueued.execution_id)
            if receipt is None:
                raise CustomerAssistantSafetyError(
                    "execution exists without an immutable receipt",
                    error_code="ASSISTANT_EXECUTION_RECEIPT_MISSING",
                )
            outcome = receipt.outcome
            receipt_id = receipt.receipt_id
        else:
            outcome = result.receipt_outcome
            receipt_id = result.receipt_id
            if outcome is None or receipt_id is None:
                raise CustomerAssistantSafetyError(
                    "execution worker did not create an immutable receipt",
                    error_code="ASSISTANT_EXECUTION_RECEIPT_MISSING",
                )
        if outcome is ReceiptOutcome.SUCCESS:
            self._buffer.complete(package.turn_id)
        else:
            self._buffer.mark_manual_intervention(
                package.turn_id,
                reason_code=f"EXECUTION_{outcome.value}",
            )
        with self._uow_factory() as uow:
            durable_receipt = uow.require_repository().get_receipt_for_execution(
                enqueued.execution_id
            )
        if durable_receipt is None:
            raise CustomerAssistantSafetyError(
                "execution exists without an immutable receipt",
                error_code="ASSISTANT_EXECUTION_RECEIPT_MISSING",
            )
        customer_message_sent = durable_receipt.details.get("customer_message_sent")
        if customer_message_sent not in {True, False, None}:
            raise CustomerAssistantSafetyError(
                "execution receipt contains an invalid send fact",
                error_code="ASSISTANT_EXECUTION_RECEIPT_INVALID",
            )
        return AssistantExecutionResult(
            decision_id=package.decision_id,
            approval_id=enqueued.approval_id,
            execution_id=enqueued.execution_id,
            receipt_id=receipt_id,
            outcome=outcome.value,
            customer_message_sent=customer_message_sent,
            automatic_retry_allowed=False,
            manual_intervention_required=outcome is not ReceiptOutcome.SUCCESS,
        )

    def desktop_snapshot(
        self,
        *,
        runtime_state: CustomerServiceRuntimeState,
        agent_online: bool,
        pdd_status: str,
    ) -> DesktopAssistantSnapshot:
        package = self._latest
        context = self._latest_context
        actions = (
            ("ADOPT_REPLY", "EDIT_REPLY", "REGENERATE", "CONFIRM_SEND")
            if package is not None and package.action == "SUGGEST_REPLY"
            else ()
        )
        return DesktopAssistantSnapshot(
            runtime_state=runtime_state,
            work_state=(
                (
                    AssistantWorkState.WAITING_APPROVAL
                    if package.action == "SUGGEST_REPLY"
                    else AssistantWorkState.MANUAL_INTERVENTION
                )
                if package is not None
                else None
            ),
            agent_online=agent_online,
            pdd_status=pdd_status,
            store_id=package.store_id if package else None,
            store_name=context.page.store_name if context else None,
            customer_reference=package.customer_reference if package else None,
            current_question=package.customer_question if package else None,
            product_summary=(
                context.page.product.product_name
                if context and context.page.product.product_name
                else None
            ),
            reply_package=package,
            risk_notice=(
                f"风险等级：{package.risk_level.value}；发送前必须人工核对店铺、会话和客户。"
                if package
                else None
            ),
            available_actions=actions,
            updated_at=self._clock(),
        )


__all__ = [
    "AICustomerReplyService",
    "CustomerAssistantRuntime",
    "CustomerAssistantSafetyError",
    "CustomerServiceLifecycleProjector",
    "ExactExecutionRunner",
]
