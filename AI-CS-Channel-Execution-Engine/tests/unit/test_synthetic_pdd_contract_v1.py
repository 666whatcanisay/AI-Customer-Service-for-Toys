from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from channel_agent.pdd_login import PDDCDPPageTarget
from channel_agent.pdd_simulator import (
    SYNTHETIC_PDD_URL,
    SimulatorConfirmationPolicy,
    SyntheticPDDAdapter,
    SyntheticPDDCDPClient,
    SyntheticPDDContract,
    SyntheticPDDExecutionAdapter,
    simulator_workspace_feed,
)
from channel_engine.execution import ClaimedExecutionContext, ExecutionCommand
from channel_engine.models import ReceiptOutcome


def contract_payload() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "schemaVersion": "synthetic-pdd-contract.v1",
        "environment": "SIMULATOR",
        "syntheticOnly": True,
        "realPlatformConnected": False,
        "externalSendEnabled": False,
        "pageState": "CUSTOMER_SERVICE_READY",
        "generatedAt": now,
        "store": {"platform": "PDD", "storeId": "SIM-STORE-001", "storeName": "仿真积木店"},
        "conversation": {"conversationId": "SIM-CONV-A01", "customerReference": "sim-customer-a01", "customerLabel": "测试买家 A01"},
        "product": {"productId": "SIM-PRODUCT-001", "productName": "香槟玫瑰积木", "attributes": {"applicable_age": "8岁以上"}},
        "sku": {"skuId": "SIM-SKU-AGE8-CHAMPAGNE", "skuName": "香槟玫瑰礼盒", "attributes": {"color": "香槟玫瑰"}},
        "order": {
            "orderId": "SIM-ORDER-20260807-001", "orderStatus": "待付款",
            "logisticsStatus": "尚未发货", "aftersalesStatus": "无售后申请",
            "paymentDataIncluded": False, "addressDataIncluded": False,
        },
        "messages": [
            {"externalMessageId": "SIM-MSG-A01-001", "sender": "customer", "content": "适合几岁？", "timestamp": now, "sequence": 1},
            {"externalMessageId": "SIM-MSG-A01-002", "sender": "operator", "content": "8岁以上。", "timestamp": now, "sequence": 2},
        ],
    }


class FixedResolver:
    def resolve(self, profile_path: Path) -> PDDCDPPageTarget:
        del profile_path
        return PDDCDPPageTarget("target", "ws://127.0.0.1:9222/devtools/page/target", SYNTHETIC_PDD_URL, "http://127.0.0.1:8431", "/")


class FixedClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.submissions: list[str] = []

    def capture_contract(self, target: PDDCDPPageTarget) -> SyntheticPDDContract:
        del target
        return SyntheticPDDContract.model_validate(self.payload)

    def submit_reply(self, target: PDDCDPPageTarget, **values: str) -> str:
        del target
        self.submissions.append(values["content"])
        return "SIM-MSG-A01-O-0100"


def make_adapter(payload: dict[str, object] | None = None) -> tuple[SyntheticPDDAdapter, FixedClient]:
    client = FixedClient(payload or contract_payload())
    return SyntheticPDDAdapter(
        browser_id="browser:test", profile_path=".", profile_reference="agent-data://test",
        resolver=FixedResolver(), client=client, clock=lambda: datetime.now(UTC),
    ), client


def test_cdp_contract_capture_waits_for_page_application_readiness() -> None:
    class LoadingClient(SyntheticPDDCDPClient):
        def __init__(self) -> None:
            super().__init__(timeout_seconds=1.0)
            self.calls = 0

        def _evaluate(self, target: PDDCDPPageTarget, expression: str) -> object:
            del target, expression
            self.calls += 1
            return None if self.calls == 1 else contract_payload()

    client = LoadingClient()
    contract = client.capture_contract(FixedResolver().resolve(Path(".")))
    assert contract.schema_version == "synthetic-pdd-contract.v1"
    assert client.calls == 2


def test_contract_maps_store_product_sku_order_and_two_sided_history() -> None:
    adapter, _client = make_adapter()
    snapshot = adapter.capture()
    assert snapshot.store_id == "SIM-STORE-001"
    assert snapshot.product.product_reference == "SIM-PRODUCT-001"
    assert snapshot.product.sku_reference == "SIM-SKU-AGE8-CHAMPAGNE"
    assert snapshot.product.attributes["applicable_age"] == "8岁以上"
    assert snapshot.transaction.order_reference == "SIM-ORDER-20260807-001"
    assert [item.sender for item in snapshot.visible_history] == ["customer", "operator"]
    feed = simulator_workspace_feed(snapshot)
    assert feed["productContext"]["skuReference"] == "SIM-SKU-AGE8-CHAMPAGNE"
    assert feed["transactionContext"]["address_data_included"] is False
    assert feed["safety"]["readOnly"] is True
    assert feed["safety"]["autoReply"] is False
    assert feed["safety"]["realSend"] is False
    assert feed["safety"]["manualApprovalRequired"] is True
    assert feed["safety"]["realPlatformConnected"] is False
    assert feed["safety"]["browserWriteOperations"] == 0
    assert feed["safety"]["executionCount"] == 0
    assert feed["safety"]["receiptCount"] == 0
    assert feed["safety"]["sendCount"] == 0
    assert feed["simulation"]["environment"] == "SIMULATOR"
    assert feed["simulation"]["externalSideEffect"] is False


@pytest.mark.parametrize(
    ("field", "unsafe"),
    (("syntheticOnly", False), ("realPlatformConnected", True), ("externalSendEnabled", True)),
)
def test_contract_fails_closed_when_simulator_safety_flag_changes(field: str, unsafe: bool) -> None:
    payload = contract_payload()
    payload[field] = unsafe
    with pytest.raises(ValidationError):
        SyntheticPDDContract.model_validate(payload)


def test_simulator_confirmation_is_exact_and_keeps_production_flags_disabled() -> None:
    adapter, _client = make_adapter()
    snapshot = adapter.capture()
    package = SimpleNamespace(
        decision_id="decision-1", store_id=snapshot.store_id,
        conversation_id=snapshot.conversation_id, customer_reference=snapshot.customer_reference,
    )
    confirmation = SimulatorConfirmationPolicy.confirmation(package, snapshot)
    confirmation.assert_exact_target()
    assert confirmation.operator_id == "simulator-auto-confirmation"


def test_execution_adapter_returns_synthetic_receipt_details_and_is_idempotent() -> None:
    adapter, client = make_adapter()
    snapshot = adapter.capture()

    class Authorization:
        def issue(self, **values: str):
            del values
            return SimpleNamespace(
                authorization=SimpleNamespace(approval_id="approval-1"),
                message=SimpleNamespace(content="建议回复"),
            )

        def verify(self, authorized) -> None:
            del authorized

    executor = SyntheticPDDExecutionAdapter(
        authorization_service=Authorization(), adapter=adapter,
        expected_store_id=snapshot.store_id,
        expected_conversation_id=snapshot.conversation_id,
        expected_customer_reference=snapshot.customer_reference,
        expected_content="建议回复",
    )
    command = ExecutionCommand(execution_id="execution-1", decision_id="decision-1", proposed_content="建议回复", idempotency_key="send-1")
    context = ClaimedExecutionContext(
        execution_id="execution-1", decision_id="decision-1", approval_id="approval-1",
        approved_by="simulator-auto-confirmation", worker_id="worker-1", lease_token="lease-1",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    first = executor.execute_claimed(command, context)
    second = executor.execute_claimed(command, context)
    assert first == second
    assert first.outcome is ReceiptOutcome.SUCCESS
    assert first.details["customer_message_sent"] is False
    assert first.details["real_send_enabled"] is False
    assert first.details["external_side_effect"] is False
    assert client.submissions == ["建议回复"]
