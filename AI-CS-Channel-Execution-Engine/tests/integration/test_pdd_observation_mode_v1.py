from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

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
    PDDDOMMetadata,
    PDDDiscoveryCapture,
    PDDDiscoverySessionMetadata,
    PDDNetworkMetadata,
    PDDPageMetadata,
    PDDScreenshotMetadata,
    PDDSelectorCandidate,
    SelectorCandidateConfidence,
)
from channel_engine.pdd_adapter import (
    FakePDDObservationPort,
    PDDMessageEntryProbe,
    PDDObservationBrowserSession,
    PDDObservationError,
    PDDObservationModeRuntime,
    PDDObservationSessionState,
    PDDObservedStoreIdentity,
)
from channel_engine.session import (
    ChannelInstanceStatus,
    ChannelSessionStatus,
    CredentialReference,
)
from channel_engine.storage.orm import (
    ApprovalRow,
    ChannelInstanceRow,
    ChannelRuntimeSessionRow,
    ConversationRow,
    DecisionRow,
    EventRow,
    ExecutionRow,
    MessageRow,
    OutboxRow,
    ReceiptRow,
)


NOW = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
SESSION_ID = "pdd-observation-browser-session"


def session(
    login: BrowserLoginState,
    state: BrowserSessionState,
    *,
    page_available: bool = True,
) -> PDDObservationBrowserSession:
    return PDDObservationBrowserSession(
        browser_session_id=SESSION_ID,
        browser_state=state,
        login_state=login,
        browser_generation=1,
        page_available=page_available,
        checked_at=NOW,
    )


def metadata_capture() -> PDDDiscoveryCapture:
    return PDDDiscoveryCapture(
        capture_id="pdd-observation-dom-capture",
        page=PDDPageMetadata(
            page_url="https://mms.pinduoduo.com/chat",
            page_title_digest="a" * 64,
            page_title_length=12,
            page_revision_digest="b" * 64,
        ),
        dom=PDDDOMMetadata(
            element_count=240,
            iframe_count=1,
            shadow_root_count=0,
            text_node_count=65,
            attribute_names=("aria-label", "class", "data-testid"),
            dom_revision_digest="c" * 64,
        ),
        selector_candidates=(
            PDDSelectorCandidate(
                candidate_id="message-entry-candidate",
                logical_key=SelectorKey.MESSAGE_ITEM,
                engine_hint=LocatorEngine.CSS,
                structural_fingerprint="d" * 64,
                observed_match_count=1,
                confidence=SelectorCandidateConfidence.LOW,
            ),
        ),
        screenshot=PDDScreenshotMetadata(
            captured=False,
            redaction_applied=True,
        ),
        network=PDDNetworkMetadata(
            request_count=4,
            websocket_upgrade_count=1,
            origins=("https://mms.pinduoduo.com",),
            methods=("GET",),
            resource_types=("document", "websocket"),
            response_status_classes={"2xx": 4},
        ),
        session=PDDDiscoverySessionMetadata(
            browser_session_id=SESSION_ID,
            page_context_id="pdd-observation-page-context",
            browser_generation=1,
            browser_state=BrowserSessionState.ACTIVE,
            login_state=BrowserLoginState.AUTHENTICATED,
            channel_session_state=ChannelSessionStatus.CONNECTED,
            page_available=True,
        ),
        message_candidates=(),
        captured_at=NOW,
    )


def build_runtime() -> tuple[PDDObservationModeRuntime, FakePDDObservationPort]:
    port = FakePDDObservationPort(
        sessions=(
            session(BrowserLoginState.REQUIRED, BrowserSessionState.LOGIN_REQUIRED),
            session(BrowserLoginState.AUTHENTICATED, BrowserSessionState.ACTIVE),
        ),
        store_identity=PDDObservedStoreIdentity(
            store_id="synthetic-observed-store-001",
            store_name="Synthetic Observed Store",
            source_reference="observation-ref://synthetic/store/bootstrap-metadata",
            observed_at=NOW,
        ),
        captures=(metadata_capture(),),
        message_entries=(
            PDDMessageEntryProbe(
                page_available=True,
                entry_present=True,
                candidate_count=1,
                observed_at=NOW,
            ),
        ),
    )
    runtime = PDDObservationModeRuntime(
        port,
        CredentialReference(
            credential_ref="credential-ref://pdd/observation/manual-session",
            provider="windows-credential-manager",
            version="v1",
        ),
        allow_synthetic_test_port=True,
        clock=lambda: NOW,
    )
    return runtime, port


def test_human_login_store_discovery_and_entry_observation_are_read_only(
    foundation,
) -> None:
    runtime, port = build_runtime()

    assert runtime.start().state is PDDObservationSessionState.AUTH_REQUIRED
    assert (
        runtime.begin_human_login_wait().state
        is PDDObservationSessionState.WAITING_USER
    )
    assert runtime.check_session().state is PDDObservationSessionState.CONNECTED

    instance = runtime.discover_store()
    evidence = runtime.observe_page()
    status = runtime.status()

    assert instance.platform == "pdd"
    assert instance.status is ChannelInstanceStatus.CONNECTED
    assert instance.store_id == "synthetic-observed-store-001"
    assert evidence.channel_instance == instance
    assert evidence.selector_contract.state is SelectorContractState.DRAFT
    assert evidence.selector_contract.bindings == ()
    assert evidence.selector_contract.capabilities == frozenset()
    assert evidence.message_entry.entry_present is True
    assert evidence.message_entry.customer_content_captured is False
    assert evidence.message_entry.message_identity_captured is False
    assert evidence.message_entry.runtime_delivery_enabled is False
    assert evidence.page_capture.message_candidates == ()
    assert evidence.page_capture.screenshot.captured is False
    assert status.store_discovered is True
    assert status.message_entry_observed is True

    assert port.automatic_login_performed is False
    assert port.page_write_operations == 0
    assert port.send_operations == 0
    assert port.credential_material_persisted is False
    assert not hasattr(runtime, "send_message")
    assert not hasattr(runtime, "approve")
    assert not hasattr(runtime, "execute")
    assert not hasattr(port, "click")
    assert not hasattr(port, "reply")

    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        for row_type in (
            ConversationRow,
            ChannelInstanceRow,
            ChannelRuntimeSessionRow,
            MessageRow,
            DecisionRow,
            ApprovalRow,
            ExecutionRow,
            ReceiptRow,
            EventRow,
            OutboxRow,
        ):
            assert uow.session.scalar(select(func.count()).select_from(row_type)) == 0

    registry = SelectorRegistry()
    registry.register(evidence.selector_contract)
    try:
        registry.active("pdd", "merchant_chat")
    except SelectorContractUnavailable:
        pass
    else:
        raise AssertionError("DRAFT selector must never become active")


def test_store_discovery_is_blocked_until_human_login_completes() -> None:
    runtime, port = build_runtime()

    assert runtime.start().state is PDDObservationSessionState.AUTH_REQUIRED
    try:
        runtime.discover_store()
    except PDDObservationError as exc:
        assert exc.error_code == "PDD_OBSERVATION_STORE_REQUIRES_LOGIN"
    else:
        raise AssertionError("store discovery must require human-authenticated session")

    assert port.store_discovery_count == 0
    assert runtime.safety_snapshot().send_operations == 0


def test_audit_is_metadata_only_and_credential_never_enters_evidence() -> None:
    runtime, _ = build_runtime()
    runtime.start()
    runtime.begin_human_login_wait()
    runtime.check_session()
    runtime.discover_store()
    evidence = runtime.observe_page()

    audit_json = "".join(item.model_dump_json() for item in runtime.audit_events())
    evidence_json = evidence.model_dump_json()

    assert "credential-ref://" not in audit_json
    assert "credential-ref://" not in evidence_json
    assert "Synthetic Observed Store" not in audit_json
    assert "customer_content" not in audit_json
    assert "cookie" not in audit_json.casefold()
    assert "password" not in audit_json.casefold()
    assert "token=" not in audit_json.casefold()
    assert runtime.safety_snapshot().execution_created == 0
    assert runtime.safety_snapshot().receipt_created == 0
    assert runtime.safety_snapshot().send_operations == 0


def test_login_expiry_moves_to_expired_and_requires_human_again() -> None:
    port = FakePDDObservationPort(
        sessions=(
            session(BrowserLoginState.AUTHENTICATED, BrowserSessionState.ACTIVE),
            session(BrowserLoginState.EXPIRED, BrowserSessionState.EXPIRED),
        ),
        store_identity=PDDObservedStoreIdentity(
            store_id="synthetic-expired-store-001",
            store_name="Synthetic Expired Store",
            source_reference="observation-ref://synthetic/store/expired",
            observed_at=NOW,
        ),
        captures=(),
        message_entries=(),
    )
    runtime = PDDObservationModeRuntime(
        port,
        CredentialReference(
            credential_ref="credential-ref://pdd/observation/expired-session",
            provider="windows-credential-manager",
            version="v1",
        ),
        allow_synthetic_test_port=True,
        clock=lambda: NOW,
    )

    assert runtime.start().state is PDDObservationSessionState.CONNECTED
    assert runtime.check_session().state is PDDObservationSessionState.EXPIRED
    assert (
        runtime.begin_human_login_wait().state
        is PDDObservationSessionState.WAITING_USER
    )
