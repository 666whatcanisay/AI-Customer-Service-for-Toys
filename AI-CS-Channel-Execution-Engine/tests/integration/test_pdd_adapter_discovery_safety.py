from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from channel_engine.browser import BrowserLoginState, BrowserSessionState
from channel_engine.channel import (
    FakePDDDiscoveryObservationPort,
    PDDDOMMetadata,
    PDDDiscoveryAdapter,
    PDDDiscoveryCapture,
    PDDDiscoverySessionMetadata,
    PDDNetworkMetadata,
    PDDPageMetadata,
    PDDScreenshotMetadata,
    SyntheticPDDMessageEvidence,
)
from channel_engine.session import ChannelSessionStatus
from channel_engine.storage.orm import (
    ApprovalRow,
    ConversationRow,
    DecisionRow,
    EventRow,
    ExecutionRow,
    MessageRow,
    OutboxRow,
    ReceiptRow,
)


NOW = datetime(2026, 8, 4, 17, 30, tzinfo=timezone.utc)


def safe_capture() -> PDDDiscoveryCapture:
    return PDDDiscoveryCapture(
        capture_id="safety-capture",
        page=PDDPageMetadata(
            page_url="https://merchant.test/chat",
            page_title_digest="a" * 64,
            page_title_length=0,
            page_revision_digest="b" * 64,
        ),
        dom=PDDDOMMetadata(
            element_count=0,
            iframe_count=0,
            shadow_root_count=0,
            text_node_count=0,
            attribute_names=(),
            dom_revision_digest="c" * 64,
        ),
        selector_candidates=(),
        screenshot=PDDScreenshotMetadata(
            captured=False,
            redaction_applied=True,
        ),
        network=PDDNetworkMetadata(
            request_count=0,
            websocket_upgrade_count=0,
            origins=(),
            methods=(),
            resource_types=(),
        ),
        session=PDDDiscoverySessionMetadata(
            browser_session_id="safety-browser-session",
            browser_generation=0,
            browser_state=BrowserSessionState.CREATED,
            login_state=BrowserLoginState.UNKNOWN,
            channel_session_state=ChannelSessionStatus.CREATED,
            page_available=False,
        ),
        message_candidates=(),
        captured_at=NOW,
    )


def test_discovery_mode_creates_no_execution_receipt_event_or_send(
    foundation,
) -> None:
    port = FakePDDDiscoveryObservationPort((safe_capture(),), clock=lambda: NOW)
    adapter = PDDDiscoveryAdapter(port, clock=lambda: NOW)

    observation = adapter.observe_only()
    preview = adapter.preview_message_mapping(
        SyntheticPDDMessageEvidence(
            store_id="synthetic-store",
            conversation_id="synthetic-conversation",
            message_id="synthetic-message",
            content="synthetic discovery-only message",
            timestamp=NOW,
        )
    )
    health = adapter.health_check()

    assert observation.runtime_delivery_enabled is False
    assert observation.send_enabled is False
    assert preview.runtime_eligible is False
    assert health.details["send_enabled"] is False
    assert not hasattr(adapter, "send_message")
    assert not hasattr(adapter, "reply")
    assert not hasattr(adapter, "click")
    assert not hasattr(port, "send_message")
    assert not hasattr(port, "click")
    assert port.write_action_count == 0
    assert port.real_platform_call_count == 0

    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        for row_type in (
            ConversationRow,
            MessageRow,
            DecisionRow,
            ApprovalRow,
            ExecutionRow,
            ReceiptRow,
            EventRow,
            OutboxRow,
        ):
            assert uow.session.scalar(
                select(func.count()).select_from(row_type)
            ) == 0
