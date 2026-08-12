from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from channel_engine.customer_assistant import (
    AICustomerReplyService,
    BufferedCustomerMessage,
    BufferedMessageDisposition,
    ContextPageState,
    ConversationBufferError,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    CustomerServiceLifecycleProjector,
    CustomerServiceRuntimeState,
    HumanSendConfirmation,
    PageContext,
    ProductContext,
    SQLiteConversationBuffer,
    TransactionContext,
    render_customer_assistant,
)
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker, FakeExecutionAdapter
from channel_engine.gateway import (
    CONTRACT_VERSION,
    DecisionRequest,
    DecisionResponse,
    GatewayRiskLevel,
)
from channel_engine.models import DecisionAction, ReceiptOutcome
from channel_engine.pdd_adapter import PDDCapturedMessage, PDDPrivacyFilter
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage.orm import ApprovalRow, ExecutionRow, ReceiptRow
from channel_agent.config import AgentConfigError, ChannelAgentConfig, load_agent_config


NOW = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)


class SyntheticGateway:
    version = "synthetic-ai-cs.v1"

    def __init__(self) -> None:
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        return DecisionResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=f"decision-{len(self.requests):03d}",
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content=f"建议回复：{request.customer_message}",
            requires_approval=True,
            risk_level=GatewayRiskLevel.LOW,
            gateway_version=self.version,
            metadata={
                "citations": [
                    {"reference": "kb://products/blocks", "title": "积木商品知识"}
                ]
            },
            decided_at=NOW,
        )


class SyntheticContextProvider:
    def __init__(self, *, page_state: ContextPageState = ContextPageState.PRODUCT):
        self.page_state = page_state

    def capture_page_context(self, *, store_id: str, conversation_id: str):
        return PageContext(
            store_id=store_id,
            conversation_id=conversation_id,
            state=self.page_state,
            product=ProductContext(
                product_reference="product-ref://blocks/plane",
                product_name="飞机积木模型",
                sku_reference="sku-ref://blocks/plane/blue",
                sku_name="蓝色标准版",
            ),
            captured_at=NOW,
        )

    def capture_transaction_context(self, *, store_id: str, conversation_id: str):
        del store_id, conversation_id
        return TransactionContext(
            order_reference="order-ref://sha256/example",
            order_status="SHIPPED",
            logistics_status="IN_TRANSIT",
            aftersales_status="NOT_OPENED",
        )

    def load_history(self, *, store_id: str, conversation_id: str, limit: int):
        del store_id, conversation_id, limit
        return ()

    def scopes_for(self, *, store_id: str, conversation_id: str):
        del store_id, conversation_id
        return ("products", "orders", "aftersales")


def redacted_message(
    external_message_id: str,
    content: str,
    *,
    timestamp: datetime,
):
    captured = PDDCapturedMessage(
        store_id="store-001",
        conversation_id="conversation-001",
        external_message_id=external_message_id,
        sender="customer",
        content=content,
        timestamp=timestamp,
        captured_at=timestamp,
    )
    return PDDPrivacyFilter().apply(captured)


def build_assistant(
    foundation,
    tmp_path,
    *,
    outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
):
    gateway = SyntheticGateway()
    provider = SyntheticContextProvider()
    buffer = SQLiteConversationBuffer(
        tmp_path / "assistant-buffer.sqlite3",
        quiet_window=timedelta(seconds=4),
        processing_lease=timedelta(seconds=30),
        clock=lambda: NOW + timedelta(seconds=10),
    )
    collector = CustomerContextCollector(
        provider,
        provider,
        provider,
        provider,
        clock=lambda: NOW + timedelta(seconds=10),
    )
    worker = ExecutionWorker(
        foundation["uow_factory"],
        FakeExecutionAdapter(outcome),
        "assistant-worker",
        clock=lambda: NOW + timedelta(seconds=10),
    )
    runtime = CustomerAssistantRuntime(
        buffer,
        collector,
        AICustomerReplyService(
            foundation["uow_factory"],
            gateway,
            clock=lambda: NOW + timedelta(seconds=10),
        ),
        ExecutionCoordinator(foundation["uow_factory"], ApprovalPolicy()),
        worker,
        foundation["uow_factory"],
        clock=lambda: NOW + timedelta(seconds=10),
    )
    return runtime, buffer, gateway, worker


def confirmation(package, *, conversation_id: str | None = None):
    return HumanSendConfirmation(
        decision_id=package.decision_id,
        operator_id="operator-001",
        expected_store_id=package.store_id,
        expected_conversation_id=package.conversation_id,
        expected_customer_reference=package.customer_reference,
        current_store_id=package.store_id,
        current_conversation_id=conversation_id or package.conversation_id,
        current_customer_reference=package.customer_reference,
        confirmation_phrase=f"CONFIRM SEND {package.decision_id}",
        confirmed_at=NOW + timedelta(seconds=11),
    )


def test_three_short_messages_are_combined_into_one_customer_context(foundation, tmp_path):
    runtime, buffer, gateway, _worker = build_assistant(foundation, tmp_path)
    messages = (
        redacted_message("m-001", "你好", timestamp=NOW),
        redacted_message("m-002", "我买的飞机模型", timestamp=NOW + timedelta(seconds=1)),
        redacted_message("m-003", "少一个零件怎么办", timestamp=NOW + timedelta(seconds=2)),
    )
    for item in messages:
        assert runtime.ingest_redacted(item) is BufferedMessageDisposition.ACCEPTED

    assert runtime.generate_ready_reply(now=NOW + timedelta(seconds=3)) is None
    package = runtime.generate_ready_reply(now=NOW + timedelta(seconds=7))

    assert package is not None
    assert package.customer_question == "你好\n我买的飞机模型\n少一个零件怎么办"
    assert len(gateway.requests) == 1
    context = gateway.requests[0].context
    assert context["product"]["sku_name"] == "蓝色标准版"
    assert context["transaction"]["order_status"] == "SHIPPED"
    assert len(context["conversation_history"]) == 3
    assert package.state == "WAITING_APPROVAL"
    assert package.citations[0].reference == "kb://products/blocks"
    assert buffer.pending_count() == 0


@pytest.mark.parametrize(
    ("question", "page_state", "expected_scope"),
    [
        ("这个飞机模型适合几岁？", ContextPageState.PRODUCT, "products"),
        ("缺少一个机翼零件怎么办？", ContextPageState.AFTERSALES, "aftersales"),
        ("物流今天能到吗？", ContextPageState.ORDER, "orders"),
        ("怎么申请售后？", ContextPageState.AFTERSALES, "aftersales"),
    ],
)
def test_customer_service_scenarios_receive_complete_context(
    foundation, tmp_path, question, page_state, expected_scope
):
    runtime, _buffer, gateway, _worker = build_assistant(foundation, tmp_path)
    runtime._contexts._page.page_state = page_state
    runtime.ingest_redacted(redacted_message("m-001", question, timestamp=NOW))

    package = runtime.generate_ready_reply(now=NOW + timedelta(seconds=5))

    assert package is not None
    assert expected_scope in gateway.requests[0].context["knowledge_scopes"]
    assert gateway.requests[0].context["privacy_filtered"] is True
    assert package.requires_human_approval is True


def test_duplicate_delivery_is_idempotent_and_conflicting_content_fails_closed(
    foundation, tmp_path
):
    runtime, _buffer, _gateway, _worker = build_assistant(foundation, tmp_path)
    first = redacted_message("m-001", "商品有现货吗？", timestamp=NOW)
    assert runtime.ingest_redacted(first) is BufferedMessageDisposition.ACCEPTED
    assert runtime.ingest_redacted(first) is BufferedMessageDisposition.DUPLICATE

    conflict = redacted_message("m-001", "同一ID的不同内容", timestamp=NOW)
    with pytest.raises(ConversationBufferError) as raised:
        runtime.ingest_redacted(conflict)
    assert raised.value.error_code == "CUSTOMER_MESSAGE_IDEMPOTENCY_CONFLICT"


def test_buffer_recovers_a_stale_claim_without_losing_or_reordering_messages(tmp_path):
    path = tmp_path / "recovery.sqlite3"
    first = SQLiteConversationBuffer(
        path,
        quiet_window=timedelta(seconds=4),
        processing_lease=timedelta(seconds=30),
        clock=lambda: NOW + timedelta(seconds=5),
    )
    one = BufferedCustomerMessage.from_redacted(
        store_id="store-001",
        conversation_id="conversation-001",
        external_message_id="m-001",
        content="第一句",
        timestamp=NOW,
        received_at=NOW,
    )
    two = BufferedCustomerMessage.from_redacted(
        store_id="store-001",
        conversation_id="conversation-001",
        external_message_id="m-002",
        content="第二句",
        timestamp=NOW + timedelta(seconds=1),
        received_at=NOW + timedelta(seconds=1),
    )
    first.append(two)
    first.append(one)
    crashed_claim = first.claim_ready(now=NOW + timedelta(seconds=5))
    assert crashed_claim is not None

    recovered = SQLiteConversationBuffer(
        path,
        quiet_window=timedelta(seconds=4),
        processing_lease=timedelta(seconds=30),
        clock=lambda: NOW + timedelta(seconds=40),
    ).claim_ready(now=NOW + timedelta(seconds=40))

    assert recovered is not None
    assert recovered.turn_id == crashed_claim.turn_id
    assert [item.external_message_id for item in recovered.messages] == ["m-001", "m-002"]
    assert recovered.combined_question == "第一句\n第二句"


def test_buffer_purges_only_expired_terminal_customer_content(tmp_path):
    current = [NOW - timedelta(days=2)]
    buffer = SQLiteConversationBuffer(
        tmp_path / "retention.sqlite3",
        quiet_window=timedelta(seconds=1),
        processing_lease=timedelta(minutes=1),
        maximum_turn_messages=32,
        clock=lambda: current[0],
    )
    message = BufferedCustomerMessage.from_redacted(
        store_id="store-retention",
        conversation_id="conversation-expired",
        external_message_id="message-expired",
        content="privacy filtered expired content",
        timestamp=current[0],
        received_at=current[0],
    )
    assert buffer.append(message) is BufferedMessageDisposition.ACCEPTED
    turn = buffer.claim_ready(now=current[0] + timedelta(seconds=2))
    assert turn is not None
    buffer.mark_manual_intervention(turn.turn_id, reason_code="TEST_TERMINAL")

    current[0] = NOW
    assert buffer.purge_expired() == {"messages": 1, "turns": 1}
    assert buffer.load_history(
        store_id="store-retention",
        conversation_id="conversation-expired",
        limit=10,
    ) == ()


def test_send_requires_exact_human_confirmation_and_produces_receipt(foundation, tmp_path):
    runtime, _buffer, _gateway, worker = build_assistant(foundation, tmp_path)
    runtime.ingest_redacted(redacted_message("m-001", "请问有现货吗？", timestamp=NOW))
    package = runtime.generate_ready_reply(now=NOW + timedelta(seconds=5))
    assert package is not None

    with pytest.raises(ValueError, match="conversation"):
        runtime.confirm_and_execute(confirmation(package, conversation_id="wrong"))
    with foundation["session_factory"]() as session:
        assert list(session.scalars(select(ApprovalRow))) == []
        assert list(session.scalars(select(ExecutionRow))) == []

    result = runtime.confirm_and_execute(confirmation(package))

    assert result.outcome == "SUCCESS"
    assert result.receipt_id is not None
    assert result.customer_message_sent is False
    assert worker._adapter.call_count == 1
    with foundation["session_factory"]() as session:
        assert len(list(session.scalars(select(ApprovalRow)))) == 1
        assert len(list(session.scalars(select(ExecutionRow)))) == 1
        assert len(list(session.scalars(select(ReceiptRow)))) == 1


def test_unknown_stops_and_never_retries_automatically(foundation, tmp_path):
    runtime, _buffer, _gateway, worker = build_assistant(
        foundation, tmp_path, outcome=ReceiptOutcome.UNKNOWN
    )
    runtime.ingest_redacted(redacted_message("m-001", "物流异常了吗？", timestamp=NOW))
    package = runtime.generate_ready_reply(now=NOW + timedelta(seconds=5))
    assert package is not None

    first = runtime.confirm_and_execute(confirmation(package))
    replay = runtime.confirm_and_execute(confirmation(package))

    assert first.outcome == replay.outcome == "UNKNOWN"
    assert first.receipt_id == replay.receipt_id
    assert first.automatic_retry_allowed is False
    assert first.manual_intervention_required is True
    assert worker._adapter.call_count == 1


def test_product_runtime_projection_stops_on_page_or_risk_control_changes():
    assert CustomerServiceLifecycleProjector.project(
        browser_status="OPENED", pdd_login_state="WAITING_QR_SCAN"
    ) is CustomerServiceRuntimeState.PDD_LOGIN_REQUIRED
    assert CustomerServiceLifecycleProjector.project(
        browser_status="READY", pdd_login_state="CUSTOMER_SERVICE_READY"
    ) is CustomerServiceRuntimeState.CUSTOMER_SERVICE_READY
    assert CustomerServiceLifecycleProjector.project(
        browser_status="READY",
        pdd_login_state="CUSTOMER_SERVICE_READY",
        observation_active=True,
    ) is CustomerServiceRuntimeState.CUSTOMER_SERVICE_RUNNING
    assert CustomerServiceLifecycleProjector.project(
        browser_status="READY",
        pdd_login_state="CUSTOMER_SERVICE_READY",
        reason_code="PDD_RISK_CONTROL_DETECTED",
        observation_active=True,
    ) is CustomerServiceRuntimeState.HUMAN_INTERVENTION


def test_agent_configuration_keeps_assistant_default_off_and_rejects_unsafe_modes(
    tmp_path,
):
    safe = ChannelAgentConfig(
        server_url="http://127.0.0.1:8000",
        agent_id="agent-001",
        device_id="device-001",
    )
    assert safe.customer_assistant_enabled is False
    assert safe.manual_approval_required is True
    assert safe.auto_reply_enabled is False
    assert safe.real_send_enabled is False

    for override in (
        {"manual_approval_required": False},
        {"auto_reply_enabled": True},
        {"real_send_enabled": True},
    ):
        with pytest.raises(ValueError):
            ChannelAgentConfig(
                server_url="http://127.0.0.1:8000",
                agent_id="agent-001",
                device_id="device-001",
                **override,
            )

    unsafe = tmp_path / "agent.json"
    unsafe.write_text(
        '{"server_url":"http://127.0.0.1:8000","agent_id":"a",'
        '"device_id":"d","password":"forbidden"}',
        encoding="utf-8",
    )
    with pytest.raises(AgentConfigError):
        load_agent_config(unsafe)


def test_desktop_snapshot_exposes_human_actions_but_keeps_real_send_disabled(
    foundation, tmp_path
):
    runtime, _buffer, _gateway, _worker = build_assistant(foundation, tmp_path)
    runtime.ingest_redacted(redacted_message("m-001", "商品规格是什么？", timestamp=NOW))
    runtime.generate_ready_reply(now=NOW + timedelta(seconds=5))

    snapshot = runtime.desktop_snapshot(
        runtime_state=CustomerServiceRuntimeState.CUSTOMER_SERVICE_RUNNING,
        agent_online=True,
        pdd_status="客服工作台运行中",
    )

    assert snapshot.available_actions == (
        "ADOPT_REPLY",
        "EDIT_REPLY",
        "REGENERATE",
        "CONFIRM_SEND",
    )
    assert snapshot.auto_reply_enabled is False
    assert snapshot.real_send_enabled is False
    assert snapshot.manual_approval_required is True

    html = render_customer_assistant(snapshot)
    assert "客户问题" in html
    assert "AI 建议回复" in html
    assert "采用回复" in html
    assert "修改回复" in html
    assert "重新生成" in html
    assert "确认发送" in html
    assert 'data-action="CONFIRM_SEND" disabled' in html
    assert "自动发送" not in html
