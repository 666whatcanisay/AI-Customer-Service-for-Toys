from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import (
    BrowserLoginState,
    BrowserSessionState,
    LocatorEngine,
    SelectorContractState,
    SelectorContractUnavailable,
    SelectorKey,
    SelectorRegistry,
)
from channel_engine.channel import (
    AdapterHealthStatus,
    FakePDDDiscoveryObservationPort,
    InMemoryPDDDiscoveryObservationStore,
    PDDDOMMetadata,
    PDDDiscoveryAdapter,
    PDDDiscoveryCapture,
    PDDDiscoveryLifecycle,
    PDDDiscoverySessionMetadata,
    PDDDiscoveryUnavailable,
    PDDMessageCandidateMetadata,
    PDDNetworkMetadata,
    PDDPageMetadata,
    PDDScreenshotMetadata,
    PDDSelectorCandidate,
    SelectorCandidateConfidence,
    SyntheticPDDMessageEvidence,
)
from channel_engine.session import ChannelSessionStatus


NOW = datetime(2026, 8, 4, 17, 0, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def discovery_capture(capture_id: str = "capture-1") -> PDDDiscoveryCapture:
    return PDDDiscoveryCapture(
        capture_id=capture_id,
        page=PDDPageMetadata(
            page_url="https://merchant.test/chat",
            page_title_digest=DIGEST_A,
            page_title_length=18,
            page_revision_digest=DIGEST_B,
        ),
        dom=PDDDOMMetadata(
            element_count=120,
            iframe_count=1,
            shadow_root_count=0,
            text_node_count=40,
            attribute_names=("class", "data-test", "aria-label"),
            dom_revision_digest=DIGEST_C,
        ),
        selector_candidates=(
            PDDSelectorCandidate(
                candidate_id="candidate-message-item",
                logical_key=SelectorKey.MESSAGE_ITEM,
                engine_hint=LocatorEngine.CSS,
                structural_fingerprint=DIGEST_A,
                observed_match_count=3,
                confidence=SelectorCandidateConfidence.LOW,
            ),
        ),
        screenshot=PDDScreenshotMetadata(
            captured=True,
            width=1280,
            height=720,
            image_digest=DIGEST_B,
            redaction_applied=True,
        ),
        network=PDDNetworkMetadata(
            request_count=12,
            websocket_upgrade_count=1,
            origins=("https://merchant.test", "wss://events.merchant.test"),
            methods=("GET", "POST"),
            resource_types=("document", "fetch", "websocket"),
            response_status_classes={"2xx": 11, "3xx": 1},
        ),
        session=PDDDiscoverySessionMetadata(
            browser_session_id="browser-session-1",
            page_context_id="page-context-1",
            browser_generation=1,
            browser_state=BrowserSessionState.LOGIN_REQUIRED,
            login_state=BrowserLoginState.REQUIRED,
            channel_session_state=ChannelSessionStatus.AUTH_REQUIRED,
            page_available=True,
        ),
        message_candidates=(
            PDDMessageCandidateMetadata(
                candidate_id="message-candidate-1",
                message_identity_digest=DIGEST_A,
                conversation_identity_digest=DIGEST_B,
                sender_category="customer",
                content_present=True,
                content_length=24,
                timestamp_present=True,
                timestamp_timezone_aware=True,
                synthetic_test_data=True,
            ),
        ),
        captured_at=NOW,
    )


def test_discovery_capture_observe_health_and_draft_selector() -> None:
    first = discovery_capture("capture-metadata")
    second = discovery_capture("capture-observation")
    port = FakePDDDiscoveryObservationPort((first, second), clock=lambda: NOW)
    store = InMemoryPDDDiscoveryObservationStore()
    adapter = PDDDiscoveryAdapter(port, store=store, clock=lambda: NOW)

    metadata = adapter.capture_metadata()
    assert metadata.capture_id == "capture-metadata"
    assert store.list_observations() == ()
    observation = adapter.observe_only()
    health = adapter.health_check()

    assert observation.capture.capture_id == "capture-observation"
    assert observation.selector_contract.state is SelectorContractState.DRAFT
    assert observation.selector_contract.bindings == ()
    assert observation.selector_contract.capabilities == frozenset()
    assert observation.runtime_delivery_enabled is False
    assert observation.send_enabled is False
    assert len(store.list_observations()) == 1
    assert adapter.lifecycle_state is PDDDiscoveryLifecycle.READY
    assert adapter.observation_count == 1
    assert health.status is AdapterHealthStatus.HEALTHY
    assert health.real_platform_connected is False
    assert health.details["send_enabled"] is False
    assert health.details["click_enabled"] is False
    assert port.write_action_count == 0
    assert port.real_platform_call_count == 0

    serialized = observation.model_dump_json()
    assert "[REDACTED]" in serialized
    assert "merchant.test/chat" in serialized
    assert "locator" not in serialized
    assert "cookie=" not in serialized.casefold()
    assert "token=" not in serialized.casefold()
    assert '"cookies_captured":false' in serialized.casefold()

    registry = SelectorRegistry()
    registry.register(observation.selector_contract)
    with pytest.raises(SelectorContractUnavailable):
        registry.active("pdd", "merchant_chat")


def test_message_mapping_is_synthetic_preview_and_never_runtime_eligible() -> None:
    adapter = PDDDiscoveryAdapter(
        FakePDDDiscoveryObservationPort((discovery_capture(),), clock=lambda: NOW),
        clock=lambda: NOW,
    )
    preview = adapter.preview_message_mapping(
        SyntheticPDDMessageEvidence(
            store_id="synthetic-store",
            conversation_id="synthetic-conversation",
            message_id="synthetic-message",
            content="synthetic customer question",
            timestamp=NOW,
        )
    )

    assert preview.message.channel == "pdd"
    assert preview.message.store_id == "synthetic-store"
    assert preview.message.sender == "customer"
    assert preview.mapping_contract_state is SelectorContractState.DRAFT
    assert preview.runtime_eligible is False
    assert preview.blockers == (
        "DISCOVERY_OBSERVE_ONLY",
        "SELECTOR_CONTRACT_DRAFT",
        "MAPPING_CONTRACT_DRAFT",
    )


def test_discovery_metadata_rejects_secret_and_write_surfaces() -> None:
    with pytest.raises(ValidationError, match="query"):
        PDDPageMetadata(
            page_url="https://merchant.test/chat?token=forbidden",
            page_title_digest=DIGEST_A,
            page_title_length=1,
            page_revision_digest=DIGEST_B,
        )
    with pytest.raises(ValidationError, match="redaction"):
        PDDScreenshotMetadata(
            captured=True,
            width=100,
            height=100,
            image_digest=DIGEST_A,
            redaction_applied=False,
        )
    with pytest.raises(ValidationError):
        PDDNetworkMetadata(
            request_count=1,
            websocket_upgrade_count=0,
            origins=("https://merchant.test",),
            methods=("GET",),
            resource_types=("document",),
            cookies_captured=True,
        )
    with pytest.raises(ValidationError, match="write selector"):
        PDDSelectorCandidate(
            candidate_id="forbidden-send-control",
            logical_key=SelectorKey.SEND_CONTROL,
            engine_hint=LocatorEngine.CSS,
            structural_fingerprint=DIGEST_A,
            observed_match_count=1,
            confidence=SelectorCandidateConfidence.LOW,
        )


def test_capture_failure_degrades_without_creating_observation() -> None:
    store = InMemoryPDDDiscoveryObservationStore()
    port = FakePDDDiscoveryObservationPort(
        (), capture_unavailable=True, clock=lambda: NOW
    )
    adapter = PDDDiscoveryAdapter(port, store=store, clock=lambda: NOW)

    with pytest.raises(PDDDiscoveryUnavailable):
        adapter.observe_only()

    assert adapter.lifecycle_state is PDDDiscoveryLifecycle.DEGRADED
    assert adapter.last_error_code == "PDD_DISCOVERY_CAPTURE_FAILED"
    assert store.list_observations() == ()
    assert port.write_action_count == 0
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED
