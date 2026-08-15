from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from channel_engine.browser.selectors import (
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorEvidenceEnvironment,
    SelectorKey,
    SelectorVerificationEvidence,
)

from channel_agent.pdd_login import PDDCDPPageTarget
from channel_agent.pdd_workspace import (
    PDDWorkspaceSelectorState,
    PDDWorkspaceSnapshot,
)
from channel_agent.pdd_workspace_send import (
    ControlledPDDWorkspaceBrowserSender,
    PDDWorkspaceActionResult,
    PDDWorkspaceOutboundSelectorContract,
    PDDWorkspaceSendError,
    PDDWorkspaceSendProbe,
    PDDWorkspaceSendState,
)
from channel_engine.customer_assistant import (
    ConversationHistoryEntry,
    ProductContext,
    TransactionContext,
)
from channel_engine.models import ReceiptOutcome


STORE_ID = "pdd-store:" + "a" * 64
RAW_UID = "current-customer-1"
CONVERSATION_ID = "pdd-conversation:" + hashlib.sha256(
    f"{STORE_ID}\0{RAW_UID}".encode("utf-8")
).hexdigest()
CUSTOMER_REFERENCE = "sha256:" + "b" * 64
CUSTOMER_MESSAGE_ID = "pdd-message:" + "c" * 64
OPERATOR_MESSAGE_ID = "pdd-message:" + "d" * 64


def _message(message_id: str, sender: str, content: str) -> ConversationHistoryEntry:
    return ConversationHistoryEntry(
        store_id=STORE_ID,
        conversation_id=CONVERSATION_ID,
        external_message_id=message_id,
        sender=sender,
        content=content,
        timestamp=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
        content_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _snapshot(*messages: ConversationHistoryEntry) -> PDDWorkspaceSnapshot:
    return PDDWorkspaceSnapshot(
        browser_id="browser-1",
        profile_reference="profile-ref://agent/pdd",
        page_url="https://mms.pinduoduo.com/chat-merchant/index.html#/",
        selector_version="pdd-merchant-chat-observe.v1",
        selector_state=PDDWorkspaceSelectorState.VERIFIED,
        store_id=STORE_ID,
        store_name="PDD商家账号",
        conversation_id=CONVERSATION_ID,
        customer_reference=CUSTOMER_REFERENCE,
        product=ProductContext(
            product_reference="pdd-product:" + "e" * 64,
            product_name="测试积木",
        ),
        transaction=TransactionContext(),
        visible_history=messages,
        captured_at=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )


class _Observer:
    def __init__(self, snapshots: list[PDDWorkspaceSnapshot]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    def capture(self) -> PDDWorkspaceSnapshot:
        value = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
        self.calls += 1
        return value


class _Resolver:
    def resolve(self, _profile_path: Path) -> PDDCDPPageTarget:
        return PDDCDPPageTarget(
            target_id="target-1",
            websocket_url="ws://127.0.0.1:9222/devtools/page/target-1",
            page_url="https://mms.pinduoduo.com/chat-merchant/index.html#/",
            page_origin="https://mms.pinduoduo.com",
            page_path="/chat-merchant/index.html",
        )


class _ActionPort:
    def __init__(self, *, triggered: bool = True) -> None:
        self.triggered = triggered
        self.action_calls = 0

    def probe(self, _target, contract) -> PDDWorkspaceSendProbe:
        return PDDWorkspaceSendProbe(
            page_url=contract.page_url,
            current_uid=RAW_UID,
            input_count=1,
            send_button_count=1,
            input_text_length=0,
            send_button_text=contract.send_button_text,
            page_fingerprint=contract.page_fingerprint,
        )

    def fill_and_submit(self, _target, _contract, *, expected_current_uid, content):
        assert expected_current_uid == RAW_UID
        assert content == "已确认回复"
        self.action_calls += 1
        return PDDWorkspaceActionResult(
            triggered=self.triggered,
            error_code=None if self.triggered else "PDD_SEND_REJECTED",
        )


def _send_selector_contract() -> PDDWorkspaceOutboundSelectorContract:
    capabilities = frozenset({SelectorCapability.SEND_MESSAGE})
    verified_at = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)
    evidence = SelectorVerificationEvidence.issue(
        reference="evidence-ref://synthetic/pdd/workspace-send-v1",
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
        page_fingerprint="sha256:" + "9" * 64,
        applicable_page_version="synthetic-pdd-workspace-v1",
        verified_by="test-ref://channel-agent/workspace-send-suite",
        verified_at=verified_at,
        expires_at=datetime(2027, 8, 7, 8, 0, tzinfo=UTC),
        capability_boundary=capabilities,
    )
    canonical = SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="synthetic-send-v1",
        state=SelectorContractState.VERIFIED,
        capabilities=capabilities,
        bindings=(
            SelectorBinding(
                key=SelectorKey.CONVERSATION_ITEM,
                engine=LocatorEngine.CSS,
                locator="[currentuid]",
            ),
            SelectorBinding(
                key=SelectorKey.COMPOSER,
                engine=LocatorEngine.CSS,
                locator="#replyTextarea",
            ),
            SelectorBinding(
                key=SelectorKey.SEND_CONTROL,
                engine=LocatorEngine.CSS,
                locator=".reply-footer .send-btn",
            ),
            SelectorBinding(
                key=SelectorKey.SEND_CONFIRMATION,
                engine=LocatorEngine.TEXT,
                locator="发送",
            ),
        ),
        evidence_reference=evidence.reference,
        verified_at=verified_at,
        verification_evidence=evidence,
    )
    return PDDWorkspaceOutboundSelectorContract(
        selector_contract=canonical,
        runtime_environment=SelectorEvidenceEnvironment.SYNTHETIC,
    )


def _sender(observer: _Observer, actions: _ActionPort, **kwargs):
    return ControlledPDDWorkspaceBrowserSender(
        observer=observer,  # type: ignore[arg-type]
        profile_path=Path("profile"),
        resolver=_Resolver(),  # type: ignore[arg-type]
        action_port=actions,
        contract=_send_selector_contract(),
        confirmation_timeout_seconds=kwargs.get("timeout", 0.05),
        poll_seconds=0.001,
        sleep=lambda _seconds: None,
    )


def test_controlled_send_confirms_operator_echo_after_exact_human_target() -> None:
    customer = _message(CUSTOMER_MESSAGE_ID, "customer", "客户问题")
    operator = _message(OPERATOR_MESSAGE_ID, "operator", "已确认回复")
    actions = _ActionPort()
    sender = _sender(_Observer([_snapshot(customer), _snapshot(customer, operator)]), actions)

    result = sender.send(
        content="已确认回复",
        expected_store_id=STORE_ID,
        expected_conversation_id=CONVERSATION_ID,
        expected_customer_reference=CUSTOMER_REFERENCE,
        expected_customer_message_id=CUSTOMER_MESSAGE_ID,
    )

    assert result.state is PDDWorkspaceSendState.CONFIRMED
    assert result.outcome is ReceiptOutcome.SUCCESS
    assert result.customer_message_sent is True
    assert result.external_message_id == OPERATOR_MESSAGE_ID
    assert actions.action_calls == 1


def test_controlled_send_rejects_changed_conversation_before_browser_action() -> None:
    customer = _message(CUSTOMER_MESSAGE_ID, "customer", "客户问题")
    changed = _snapshot(customer).model_copy(
        update={"conversation_id": "pdd-conversation:" + "f" * 64}
    )
    actions = _ActionPort()
    sender = _sender(_Observer([changed]), actions)

    with pytest.raises(PDDWorkspaceSendError) as caught:
        sender.send(
            content="已确认回复",
            expected_store_id=STORE_ID,
            expected_conversation_id=CONVERSATION_ID,
            expected_customer_reference=CUSTOMER_REFERENCE,
            expected_customer_message_id=CUSTOMER_MESSAGE_ID,
        )

    assert caught.value.error_code == "PDD_SEND_CONVERSATION_MISMATCH"
    assert actions.action_calls == 0


def test_controlled_send_rejects_customer_message_already_answered() -> None:
    customer = _message(CUSTOMER_MESSAGE_ID, "customer", "new question")
    operator = _message(OPERATOR_MESSAGE_ID, "operator", "existing answer")
    actions = _ActionPort()
    sender = _sender(_Observer([_snapshot(customer, operator)]), actions)

    with pytest.raises(PDDWorkspaceSendError) as caught:
        sender.send(
            content="second answer",
            expected_store_id=STORE_ID,
            expected_conversation_id=CONVERSATION_ID,
            expected_customer_reference=CUSTOMER_REFERENCE,
            expected_customer_message_id=CUSTOMER_MESSAGE_ID,
        )

    assert caught.value.error_code == "PDD_SEND_CUSTOMER_ALREADY_ANSWERED"
    assert actions.action_calls == 0


def test_trigger_without_confirmed_operator_echo_is_unknown_and_never_retried() -> None:
    customer = _message(CUSTOMER_MESSAGE_ID, "customer", "客户问题")
    actions = _ActionPort()
    sender = _sender(_Observer([_snapshot(customer)]), actions, timeout=0.001)

    result = sender.send(
        content="已确认回复",
        expected_store_id=STORE_ID,
        expected_conversation_id=CONVERSATION_ID,
        expected_customer_reference=CUSTOMER_REFERENCE,
        expected_customer_message_id=CUSTOMER_MESSAGE_ID,
    )

    assert result.state is PDDWorkspaceSendState.UNKNOWN
    assert result.outcome is ReceiptOutcome.UNKNOWN
    assert result.customer_message_sent is None
    assert result.error_code == "PDD_SEND_CONFIRMATION_TIMEOUT_UNKNOWN"
    assert actions.action_calls == 1
