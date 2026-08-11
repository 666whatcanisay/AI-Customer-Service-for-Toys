from __future__ import annotations

from datetime import UTC, datetime, timedelta

from channel_agent.edge_execution import AuthorizedEdgeSendCommand
from channel_agent.edge_pdd import (
    ControlledPDDWorkspaceTransport,
    PDDSelectorRuntimeEvidence,
    PDDTransportConfirmation,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceProduct,
    PDDWorkspaceSnapshot,
)
from channel_agent.execution_authorization import (
    ExecutionAuthorizationClaims,
    ExecutionAuthorizationSigner,
    ExecutionAuthorizationVerifier,
    reply_text_sha256,
)


NOW = datetime(2026, 8, 8, 11, 0, tzinfo=UTC)
SECRET = b"edge-pdd-execution-authorization-secret"
EVIDENCE_HASH = "sha256:" + "b" * 64
PAGE_HASH = "sha256:" + "c" * 64
CUSTOMER = "sha256:" + "d" * 64


def _snapshot(content: str = "电话是13800138000，适合几岁？") -> PDDWorkspaceSnapshot:
    return PDDWorkspaceSnapshot(
        store_id="SIM-STORE-001",
        store_name="仿真积木店",
        conversation_id="SIM-CONV-001",
        customer_reference=CUSTOMER,
        page_fingerprint=PAGE_HASH,
        page_state="CUSTOMER_SERVICE_RUNNING",
        product=PDDWorkspaceProduct(
            product_id="SIM-PRODUCT-001",
            product_name="香槟玫瑰积木",
            sku_id="SIM-SKU-AGE8",
            sku_name="8岁以上",
            attributes={"applicable_age": "8岁以上"},
        ),
        messages=(
            PDDWorkspaceMessage(
                external_message_id="SIM-MSG-001",
                sender="CUSTOMER",
                content=content,
                timestamp=NOW,
                sequence=1,
            ),
        ),
        captured_at=NOW,
    )


class Driver:
    def __init__(self, snapshot: PDDWorkspaceSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def capture(self) -> PDDWorkspaceSnapshot:
        return self.snapshot

    def selector_evidence(self, _capability: str) -> PDDSelectorRuntimeEvidence:
        return PDDSelectorRuntimeEvidence(
            evidence_hash=EVIDENCE_HASH,
            selector_contract_version="pdd-synthetic-v2",
            page_fingerprint=PAGE_HASH,
            capability="SEND_MESSAGE",
            verified_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )

    def submit_approved_reply(self, **_kwargs) -> PDDTransportConfirmation:
        self.calls += 1
        return PDDTransportConfirmation(
            transport_triggered=True,
            confirmed=True,
            external_message_id="SIM-MSG-REPLY-001",
        )


def _command() -> AuthorizedEdgeSendCommand:
    reply = "您好，这款积木适合8岁以上儿童。"
    signer = ExecutionAuthorizationSigner(
        key_id="edge-key",
        secret=SECRET,
        clock=lambda: NOW,
    )
    authorization = signer.issue(
        ExecutionAuthorizationClaims(
            agent_id="agent-001",
            device_id="device-001",
            store_id="SIM-STORE-001",
            conversation_id="SIM-CONV-001",
            customer_reference=CUSTOMER,
            message_id="SIM-MSG-001",
            decision_id="decision-001",
            approval_id="approval-001",
            execution_id="execution-001",
            lease_id="lease-001",
            lease_expires_at=NOW + timedelta(minutes=2),
            reply_sha256=reply_text_sha256(reply),
            send_key="send-key-001",
            policy_version="simulator-policy-v2",
            selector_evidence_hash=EVIDENCE_HASH,
            activation_grant_id="simulator-grant",
            human_approval_verified=True,
            lease_valid=True,
            kill_switch_disabled=True,
            store_allowlisted=True,
            risk_policy_allowed=True,
            rate_limit_allowed=True,
        )
    )
    return AuthorizedEdgeSendCommand(authorization=authorization, reply_text=reply)


def test_observation_maps_full_context_and_redacts_phone() -> None:
    values = PDDWorkspaceObservationMapper(
        agent_id="agent-001", device_id="device-001"
    ).map_customer_messages(_snapshot())
    assert len(values) == 1
    assert values[0].payload["content"] == "电话是[手机号已脱敏]，适合几岁？"
    assert values[0].payload["product"]["sku_id"] == "SIM-SKU-AGE8"
    assert values[0].payload["order"]["contains_payment_data"] is False


def test_controlled_transport_requires_matching_signed_evidence() -> None:
    driver = Driver(_snapshot())
    verifier = ExecutionAuthorizationVerifier(
        key_resolver=lambda _key_id: SECRET,
        clock=lambda: NOW,
    )
    result = ControlledPDDWorkspaceTransport(
        driver,
        verifier,
        clock=lambda: NOW,
    ).send(_command())
    assert result.outcome == "SUCCESS"
    assert result.customer_message_sent is True
    assert driver.calls == 1


def test_page_fingerprint_change_fails_before_transport() -> None:
    snapshot = _snapshot().model_copy(update={"page_fingerprint": "sha256:" + "e" * 64})
    driver = Driver(snapshot)
    result = ControlledPDDWorkspaceTransport(
        driver,
        ExecutionAuthorizationVerifier(
            key_resolver=lambda _key_id: SECRET,
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    ).send(_command())
    assert result.outcome == "FAILED"
    assert result.transport_triggered is False
    assert driver.calls == 0
