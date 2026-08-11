from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from channel_agent.control_v2 import (
    AgentCommandPollResponse,
    AgentReceiptSubmission,
    ServiceApprovalDelivery,
)
from channel_agent.edge_execution import (
    EdgeExecutionService,
    EdgeReceiptStore,
)
from channel_agent.edge_pdd import (
    ControlledPDDWorkspaceTransport,
    PDDSelectorRuntimeEvidence,
    PDDTransportConfirmation,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceOrder,
    PDDWorkspaceProduct,
    PDDWorkspaceSnapshot,
)
from channel_agent.edge_runtime import CurrentPageExecutionContext, EdgeRuntime
from channel_agent.edge_spool import DurableEdgeSpool
from channel_agent.execution_authorization import (
    ExecutionAuthorizationSigner,
    ExecutionAuthorizationVerifier,
)
from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_engine.agent.control_store import AgentControlStore
from channel_engine.agent.execution_commands import (
    ExecutionCommandIssuer,
    ExecutionSafetySnapshot,
    SqlAlchemyAgentReceiptReconciler,
)
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    ContextPageState,
    ConversationHistoryEntry,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    CustomerServiceRuntimeState,
    PageContext,
    ProductContext,
    SQLiteConversationBuffer,
    TransactionContext,
)
from channel_engine.execution import ExecutionCoordinator
from channel_engine.gateway import FakeGateway
from channel_engine.models import ExecutionState
from channel_engine.pdd_adapter import PDDPrivacyFilteredMessage
from channel_engine.policy import ApprovalPolicy


NOW = datetime(2026, 8, 8, 13, 0, tzinfo=UTC)
SECRET = b"synthetic-e2e-execution-authorization-secret"
SELECTOR_HASH = "sha256:" + "7" * 64
PAGE_HASH = "sha256:" + "8" * 64
CUSTOMER = "sha256:" + "9" * 64


class TestProtector:
    def protect(self, value: bytes) -> bytes:
        return b"protected:" + value[::-1]

    def unprotect(self, value: bytes) -> bytes:
        assert value.startswith(b"protected:")
        return value.removeprefix(b"protected:")[::-1]


class SyntheticWorkspaceDriver:
    def __init__(self, snapshot: PDDWorkspaceSnapshot) -> None:
        self.snapshot = snapshot
        self.synthetic_send_count = 0

    def capture(self) -> PDDWorkspaceSnapshot:
        return self.snapshot

    def selector_evidence(self, _capability: str) -> PDDSelectorRuntimeEvidence:
        return PDDSelectorRuntimeEvidence(
            evidence_hash=SELECTOR_HASH,
            selector_contract_version="synthetic-pdd-selector.v2",
            page_fingerprint=PAGE_HASH,
            capability="SEND_MESSAGE",
            verified_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )

    def submit_approved_reply(
        self, *, reply_text: str, execution_id: str, send_key: str
    ) -> PDDTransportConfirmation:
        assert execution_id and send_key
        self.synthetic_send_count += 1
        sequence = max(item.sequence for item in self.snapshot.messages) + 1
        external_id = f"SIM-MSG-REPLY-{sequence:03d}"
        self.snapshot = self.snapshot.model_copy(
            update={
                "messages": self.snapshot.messages
                + (
                    PDDWorkspaceMessage(
                        external_message_id=external_id,
                        sender="OPERATOR",
                        content=reply_text,
                        timestamp=NOW + timedelta(seconds=10),
                        sequence=sequence,
                    ),
                )
            }
        )
        return PDDTransportConfirmation(
            transport_triggered=True,
            confirmed=True,
            external_message_id=external_id,
        )


class ContextProvider:
    def __init__(self, snapshot: PDDWorkspaceSnapshot, buffer: SQLiteConversationBuffer) -> None:
        self.snapshot = snapshot
        self.buffer = buffer

    def capture_page_context(self, *, store_id: str, conversation_id: str) -> PageContext:
        assert (store_id, conversation_id) == (
            self.snapshot.store_id,
            self.snapshot.conversation_id,
        )
        return PageContext(
            store_id=store_id,
            store_name=self.snapshot.store_name,
            conversation_id=conversation_id,
            state=ContextPageState.CUSTOMER_SERVICE,
            product=ProductContext(
                product_reference=self.snapshot.product.product_id,
                product_name=self.snapshot.product.product_name,
                sku_reference=self.snapshot.product.sku_id,
                sku_name=self.snapshot.product.sku_name,
                attributes=self.snapshot.product.attributes,
            ),
            captured_at=self.snapshot.captured_at,
        )

    def capture_transaction_context(
        self, *, store_id: str, conversation_id: str
    ) -> TransactionContext:
        assert store_id == self.snapshot.store_id
        return TransactionContext(
            order_reference=self.snapshot.order.order_reference,
            order_status=self.snapshot.order.order_status,
            logistics_status=self.snapshot.order.logistics_status,
            aftersales_status=self.snapshot.order.aftersales_status,
        )

    def load_history(self, *, store_id: str, conversation_id: str, limit: int):
        return self.buffer.load_history(
            store_id=store_id, conversation_id=conversation_id, limit=limit
        )

    def load_visible_history(self, *, store_id: str, conversation_id: str, limit: int):
        values = []
        for item in self.snapshot.messages[-limit:]:
            values.append(
                ConversationHistoryEntry(
                    store_id=store_id,
                    conversation_id=conversation_id,
                    external_message_id=item.external_message_id,
                    sender="customer" if item.sender == "CUSTOMER" else "operator",
                    content=item.content,
                    timestamp=item.timestamp,
                    content_digest=hashlib.sha256(item.content.encode()).hexdigest(),
                )
            )
        return tuple(values)

    def scopes_for(self, **_kwargs):
        return ("conversation", "products", "orders")


class SimulatorPolicy:
    def evaluate(self, delivery: ServiceApprovalDelivery) -> ExecutionSafetySnapshot:
        return ExecutionSafetySnapshot(
            transport_mode="SIMULATOR",
            policy_version=delivery.policy_version,
            selector_evidence_hash=delivery.selector_evidence_hash,
            activation_grant_id=delivery.activation_grant_id,
            customer_reference=delivery.customer_reference,
            human_approval_verified=True,
            kill_switch_disabled=True,
            store_allowlisted=True,
            conversation_matches=True,
            customer_matches=True,
            risk_policy_allowed=True,
            rate_limit_allowed=True,
            selector_evidence_valid=True,
            activation_grant_valid=True,
            synthetic_send_enabled=True,
            real_send_enabled=False,
            real_platform_activation_allowed=False,
        )


def _snapshot() -> PDDWorkspaceSnapshot:
    messages = tuple(
        PDDWorkspaceMessage(
            external_message_id=f"SIM-MSG-{index:03d}",
            sender="CUSTOMER",
            content=content,
            timestamp=NOW + timedelta(milliseconds=index * 200),
            sequence=index,
        )
        for index, content in enumerate(
            ("你好", "我买的香槟玫瑰积木", "请问适合几岁，物流什么时候到？"),
            start=1,
        )
    )
    return PDDWorkspaceSnapshot(
        store_id="SIM-STORE-001",
        store_name="仿真积木店",
        conversation_id="SIM-CONV-001",
        customer_reference=CUSTOMER,
        page_fingerprint=PAGE_HASH,
        page_state="CUSTOMER_SERVICE_RUNNING",
        product=PDDWorkspaceProduct(
            product_id="SIM-PRODUCT-001",
            product_name="香槟玫瑰积木花束",
            sku_id="SIM-SKU-AGE8",
            sku_name="8岁以上礼盒装",
            attributes={"applicable_age": "8岁以上"},
        ),
        order=PDDWorkspaceOrder(
            order_reference="SIM-ORDER-001",
            order_status="已发货",
            logistics_status="运输中",
            aftersales_status="无售后",
        ),
        messages=messages,
        captured_at=NOW + timedelta(seconds=1),
    )


def test_synthetic_buyer_to_ai_reply_to_signed_send_to_receipt(foundation, tmp_path) -> None:
    snapshot = _snapshot()
    buffer = SQLiteConversationBuffer(
        tmp_path / "conversation-buffer.sqlite3",
        quiet_window=timedelta(seconds=1),
        clock=lambda: NOW + timedelta(seconds=5),
    )
    context_provider = ContextProvider(snapshot, buffer)
    runtime = CustomerAssistantRuntime(
        buffer,
        CustomerContextCollector(
            context_provider,
            context_provider,
            context_provider,
            context_provider,
            visible_history_provider=context_provider,
            clock=lambda: NOW + timedelta(seconds=5),
        ),
        AICustomerReplyService(
            foundation["uow_factory"],
            FakeGateway(),
            clock=lambda: NOW + timedelta(seconds=5),
        ),
        None,
        None,
        foundation["uow_factory"],
        clock=lambda: NOW + timedelta(seconds=5),
        real_send_enabled=False,
    )
    control_store = AgentControlStore(
        foundation["session_factory"], clock=lambda: NOW + timedelta(seconds=5)
    )
    reconciler = SqlAlchemyAgentReceiptReconciler(
        foundation["uow_factory"], clock=lambda: NOW + timedelta(seconds=12)
    )

    class HostClient:
        def submit_observation(self, submission):
            ack = control_store.persist_observation(submission)
            payload = submission.payload
            runtime.ingest_redacted(
                PDDPrivacyFilteredMessage(
                    store_id=submission.store_id,
                    conversation_id=submission.conversation_id,
                    external_message_id=submission.external_message_id,
                    content=payload["content"],
                    timestamp=datetime.fromisoformat(payload["timestamp"]),
                    captured_at=submission.captured_at,
                    redacted_content_digest=hashlib.sha256(
                        payload["content"].encode()
                    ).hexdigest(),
                )
            )
            return ack

        def poll_command(self):
            return AgentCommandPollResponse(
                command=control_store.poll_command("agent-sim", "device-sim"),
                server_time=NOW + timedelta(seconds=10),
            )

        def submit_receipt(self, submission: AgentReceiptSubmission):
            ack = control_store.persist_receipt(submission)
            reconciler(submission)
            return ack

    driver = SyntheticWorkspaceDriver(snapshot)
    verifier = ExecutionAuthorizationVerifier(
        key_resolver=lambda _key_id: SECRET,
        clock=lambda: NOW + timedelta(seconds=10),
    )
    receipt_store = EdgeReceiptStore(tmp_path / "edge-receipts.sqlite3")
    edge = EdgeRuntime(
        agent_id="agent-sim",
        device_id="device-sim",
        client=HostClient(),
        spool=DurableEdgeSpool(
            tmp_path / "edge-spool.sqlite3",
            TestProtector(),
            clock=lambda: NOW + timedelta(seconds=2),
        ),
        execution=EdgeExecutionService(
            agent_id="agent-sim",
            device_id="device-sim",
            verifier=verifier,
            receipt_store=receipt_store,
            transport=ControlledPDDWorkspaceTransport(
                driver,
                verifier,
                clock=lambda: NOW + timedelta(seconds=10),
            ),
            clock=lambda: NOW + timedelta(seconds=11),
        ),
        receipt_store=receipt_store,
        clock=lambda: NOW + timedelta(seconds=12),
    )

    observations = PDDWorkspaceObservationMapper(
        agent_id="agent-sim", device_id="device-sim"
    ).map_customer_messages(snapshot, now=NOW + timedelta(seconds=2))
    assert len(observations) == 3
    for observation in observations:
        assert edge.capture_and_forward(observation).status == "PERSISTED"

    package = runtime.generate_ready_reply(now=NOW + timedelta(seconds=5))
    assert package is not None
    assert package.state == "WAITING_APPROVAL"
    assert package.customer_question == "你好\n我买的香槟玫瑰积木\n请问适合几岁，物流什么时候到？"
    assistant = runtime.desktop_snapshot(
        runtime_state=CustomerServiceRuntimeState.CUSTOMER_SERVICE_RUNNING,
        agent_online=True,
        pdd_status="SIMULATOR_READY",
    )
    assert assistant.reply_package == package
    assert assistant.manual_approval_required is True
    assert assistant.auto_reply_enabled is False
    assert assistant.real_send_enabled is False

    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(package.decision_id, "operator:human")
    with foundation["uow_factory"]() as uow:
        decision = uow.require_repository().get_decision(package.decision_id)
    identity = AgentIdentity(
        agent_id="agent-sim",
        device_id="device-sim",
        user_id="user-sim",
        store_id=snapshot.store_id,
        store_ids=(snapshot.store_id,),
        authorized_store_ids=(snapshot.store_id,),
        active_store_id=snapshot.store_id,
        status=AgentIdentityStatus.ACTIVE,
        binding_revision=1,
        created_at=NOW,
        updated_at=NOW,
    )
    issuer = ExecutionCommandIssuer(
        uow_factory=foundation["uow_factory"],
        identity_resolver=lambda _agent_id: identity,
        policy=SimulatorPolicy(),
        signer=ExecutionAuthorizationSigner(
            key_id="synthetic-execution-key",
            secret=SECRET,
            clock=lambda: NOW + timedelta(seconds=9),
        ),
        clock=lambda: NOW + timedelta(seconds=9),
    )
    delivery = ServiceApprovalDelivery(
        approval_delivery_id="synthetic-human-approval",
        agent_id="agent-sim",
        device_id="device-sim",
        store_id=snapshot.store_id,
        conversation_id=snapshot.conversation_id,
        customer_reference=snapshot.customer_reference,
        message_id=decision.message_id,
        decision_id=package.decision_id,
        approval_id=enqueued.approval_id,
        operator_reference="operator:human",
        reply_text=package.reply_content,
        policy_version="synthetic-policy-v2",
        selector_evidence_hash=SELECTOR_HASH,
        activation_grant_id="synthetic-activation-grant",
        approved_at=NOW + timedelta(seconds=8),
    )
    assert control_store.enqueue_command(issuer(delivery)) == "QUEUED"

    receipt = edge.poll_and_execute(
        CurrentPageExecutionContext(
            store_id=snapshot.store_id,
            conversation_id=snapshot.conversation_id,
            customer_reference=snapshot.customer_reference,
            selector_evidence_hash=SELECTOR_HASH,
        )
    )
    assert receipt is not None and receipt.outcome == "SUCCESS"
    assert driver.synthetic_send_count == 1
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        core_receipt = repo.get_receipt_for_execution(enqueued.execution_id)
    assert execution.state is ExecutionState.SUCCESS
    assert core_receipt is not None
    assert core_receipt.details["customer_message_sent"] is True
    assert core_receipt.details["automatic_retry_allowed"] is False
    assert edge.poll_and_execute(
        CurrentPageExecutionContext(
            store_id=snapshot.store_id,
            conversation_id=snapshot.conversation_id,
            customer_reference=snapshot.customer_reference,
            selector_evidence_hash=SELECTOR_HASH,
        )
    ) is None
    assert driver.synthetic_send_count == 1
