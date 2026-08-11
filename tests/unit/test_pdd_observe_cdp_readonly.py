from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from channel_engine.browser import (
    BrowserPageContext,
    CDPPageTarget,
    CDPSelectorRejected,
    ChromeDevToolsReadOnlyPagePort,
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorDiscoveryWorkflow,
    SelectorEvidenceEnvironment,
    SelectorKey,
    SelectorVerificationEvidence,
)


NOW = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)


def _evidence(
    capabilities: frozenset[SelectorCapability],
) -> SelectorVerificationEvidence:
    return SelectorVerificationEvidence.issue(
        reference="evidence-ref://synthetic/pdd/observe/selector-v1",
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
        page_fingerprint="sha256:" + "1" * 64,
        applicable_page_version="synthetic-observe-v1",
        verified_by="test-ref://channel-engine/cdp-readonly-suite",
        verified_at=NOW,
        expires_at=NOW + timedelta(days=365),
        capability_boundary=capabilities,
    )


class FixedTargetResolver:
    def __init__(self) -> None:
        self.target = CDPPageTarget(
            target_id="pdd-observe-target",
            websocket_url="ws://127.0.0.1:9222/devtools/page/pdd-observe-target",
            location_origin="https://mms.pinduoduo.com",
        )

    def resolve(self) -> CDPPageTarget:
        return self.target


class ScriptedEvaluator:
    def __init__(self, *results: object) -> None:
        self.results = deque(results)
        self.expressions: list[str] = []

    def evaluate(self, target: CDPPageTarget, expression: str) -> object:
        assert target.target_id == "pdd-observe-target"
        self.expressions.append(expression)
        return self.results.popleft()


def page() -> BrowserPageContext:
    return BrowserPageContext(
        page_context_id="pdd-observe-page",
        session_id="pdd-observe-session",
        generation=1,
        selector_contract_version="observe-v1",
        page_revision="sha256:" + "1" * 64,
        created_at=NOW,
    )


def receive_only_contract() -> SelectorContract:
    capabilities = frozenset(
        {SelectorCapability.STORE_IDENTITY, SelectorCapability.RECEIVE_MESSAGE}
    )
    evidence = _evidence(capabilities)
    return SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="observe-v1",
        state=SelectorContractState.VERIFIED,
        capabilities=capabilities,
        bindings=(
            SelectorBinding(
                key=SelectorKey.STORE_ID,
                engine=LocatorEngine.CSS,
                locator="[data-store-id]",
                value_attribute="data-store-id",
                expected_count_max=1,
            ),
            SelectorBinding(
                key=SelectorKey.STORE_NAME,
                engine=LocatorEngine.CSS,
                locator="[data-store-name]",
                value_attribute="data-store-name",
                expected_count_max=1,
            ),
            SelectorBinding(
                key=SelectorKey.CONVERSATION_ITEM,
                engine=LocatorEngine.CSS,
                locator="[data-conversation]",
            ),
            SelectorBinding(
                key=SelectorKey.CONVERSATION_ID,
                engine=LocatorEngine.CSS,
                locator="[data-conversation-id]",
                value_attribute="data-conversation-id",
            ),
            SelectorBinding(
                key=SelectorKey.MESSAGE_ITEM,
                engine=LocatorEngine.CSS,
                locator="[data-message-id]",
            ),
            SelectorBinding(
                key=SelectorKey.EXTERNAL_MESSAGE_ID,
                engine=LocatorEngine.CSS,
                locator="[data-message-id]",
                value_attribute="data-message-id",
            ),
            SelectorBinding(
                key=SelectorKey.MESSAGE_SENDER,
                engine=LocatorEngine.CSS,
                locator="[data-sender]",
                value_attribute="data-sender",
            ),
            SelectorBinding(
                key=SelectorKey.MESSAGE_CONTENT,
                engine=LocatorEngine.CSS,
                locator=".message-content",
            ),
            SelectorBinding(
                key=SelectorKey.MESSAGE_TIMESTAMP,
                engine=LocatorEngine.CSS,
                locator="time[datetime]",
                value_attribute="datetime",
            ),
        ),
        evidence_reference=evidence.reference,
        verified_at=NOW,
        verification_evidence=evidence,
    )


def raw_message(suffix: str) -> dict[str, str]:
    return {
        "conversation_id": "pdd-conversation-1",
        "external_message_id": f"pdd-message-{suffix}",
        "sender": "customer",
        "content": f"Synthetic observation {suffix}",
        "timestamp": f"2026-08-05T10:00:0{suffix}+00:00",
    }


def test_real_page_port_baselines_history_then_returns_only_new_messages() -> None:
    evaluator = ScriptedEvaluator(
        [raw_message("1")],
        [raw_message("1"), raw_message("2")],
    )
    port = ChromeDevToolsReadOnlyPagePort(
        FixedTargetResolver(),
        evaluator,
        runtime_environment=SelectorEvidenceEnvironment.SYNTHETIC,
        clock=lambda: NOW,
    )
    contract = receive_only_contract()
    attachment = port.attach(page(), contract)

    baseline = port.capture(
        attachment,
        page(),
        contract,
        cursor=None,
        after_sequence=-1,
        limit=20,
    )
    observed = port.capture(
        attachment,
        page(),
        contract,
        cursor=baseline.next_cursor,
        after_sequence=-1,
        limit=20,
    )

    assert baseline.messages == ()
    assert baseline.next_cursor is not None
    assert len(observed.messages) == 1
    assert observed.messages[0].external_message_id == "pdd-message-2"
    assert observed.messages[0].source_sequence == 0
    assert port.page_write_operations == 0
    assert port.heartbeat(attachment) is True


def test_real_page_port_reads_store_identity_without_raw_credentials() -> None:
    evaluator = ScriptedEvaluator(
        {
            "STORE_ID": {"count": 1, "value": "store-verified-001"},
            "STORE_NAME": {"count": 1, "value": "Synthetic Store"},
        }
    )
    port = ChromeDevToolsReadOnlyPagePort(
        FixedTargetResolver(),
        evaluator,
        runtime_environment=SelectorEvidenceEnvironment.SYNTHETIC,
        clock=lambda: NOW,
    )
    bindings = tuple(
        binding
        for binding in receive_only_contract().bindings
        if binding.key in {SelectorKey.STORE_ID, SelectorKey.STORE_NAME}
    )

    values, source_reference, _observed_at = port.read_values(page(), bindings)

    assert values[SelectorKey.STORE_ID] == "store-verified-001"
    assert values[SelectorKey.STORE_NAME] == "Synthetic Store"
    assert source_reference.startswith("browser-page-ref://")
    assert "cookie" not in "".join(evaluator.expressions).casefold()
    assert port.page_write_operations == 0


def test_real_page_port_rejects_send_capability_and_unverified_selector() -> None:
    port = ChromeDevToolsReadOnlyPagePort(
        FixedTargetResolver(),
        ScriptedEvaluator(),
        runtime_environment=SelectorEvidenceEnvironment.SYNTHETIC,
        clock=lambda: NOW,
    )
    receive = receive_only_contract()
    with_send = receive.model_copy(
        update={
            "capabilities": frozenset(
                {*receive.capabilities, SelectorCapability.SEND_MESSAGE}
            )
        }
    )
    draft = receive.model_copy(
        update={
            "state": SelectorContractState.DRAFT,
            "verified_at": None,
            "verification_evidence": None,
        }
    )

    with pytest.raises(CDPSelectorRejected, match="receive-only"):
        port.attach(page(), with_send)
    with pytest.raises(CDPSelectorRejected, match="VERIFIED"):
        port.attach(page(), draft)
    assert not hasattr(port, "send_message")
    assert not hasattr(port, "click")
    assert not hasattr(port, "input")


def test_selector_discovery_requires_probe_before_verified_activation() -> None:
    verified_shape = receive_only_contract()
    draft = SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="observe-discovery-v1",
        state=SelectorContractState.DRAFT,
        capabilities=frozenset(),
        bindings=(),
        evidence_reference="discovery://pdd-observe-unverified",
    )
    discovery = SelectorDiscoveryWorkflow.begin(
        draft,
        evidence_reference="discovery-ref://pdd/observe/session-1",
    )
    candidate = SelectorDiscoveryWorkflow.record_candidates(
        discovery,
        capabilities=verified_shape.capabilities,
        bindings=verified_shape.bindings,
        evidence_reference="evidence-ref://pdd/observe/session-1/candidates",
    )
    counts = {
        binding.key.value: {"count": 1, "value": None}
        for binding in candidate.bindings
    }
    port = ChromeDevToolsReadOnlyPagePort(
        FixedTargetResolver(),
        ScriptedEvaluator(counts),
        runtime_environment=SelectorEvidenceEnvironment.SYNTHETIC,
        clock=lambda: NOW,
    )

    probe = port.probe(page(), candidate)
    verified = SelectorDiscoveryWorkflow.verify(
        candidate,
        probe,
        verified_at=NOW,
        verified_by="test-ref://channel-engine/discovery-suite",
        expires_at=NOW + timedelta(days=365),
        applicable_page_version="synthetic-observe-discovery-v1",
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
    )

    assert discovery.state is SelectorContractState.DISCOVERY
    assert candidate.state is SelectorContractState.DISCOVERY
    assert probe.passed is True
    assert verified.state is SelectorContractState.VERIFIED
    assert verified.verified_at == NOW
