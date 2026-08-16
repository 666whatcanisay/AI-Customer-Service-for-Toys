from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from channel_engine.browser import (
    BrowserObservationMechanism,
    BrowserObservationMissedMessages,
    BrowserPageCapture,
    BrowserPageObserver,
    BrowserProfileReference,
    BrowserSessionManager,
    ChromeLaunchStrategy,
    FakeBrowserRuntimeDriver,
    FakeReadOnlyBrowserPageCapturePort,
    PDDMessageExtractor,
    SelectorRegistry,
    SequencedRawBrowserMessage,
    SqlAlchemyBrowserObservationStore,
    verified_mock_pdd_merchant_chat_v1,
)
from channel_engine.conversation import ConversationService
from channel_engine.pdd_adapter import (
    BrowserPDDMessageReader,
    PDDDurableMessageObservationRuntime,
)
from channel_engine.session import (
    ChannelInstance,
    ChannelInstanceStatus,
    ChannelSession,
    ChannelSessionStatus,
    ChannelSessionStore,
    CredentialReference,
    MessageReliabilityService,
)
from channel_engine.storage.orm import ChannelMessageInboxRow, DecisionRow


NOW = datetime(2026, 8, 5, 14, 0, tzinfo=timezone.utc)
STORE_ID = "pdd-cursor-safe-store"
INSTANCE_ID = "pdd-cursor-safe-instance"
STREAM_ID = "pdd-browser:pdd-cursor-safe-store"


def raw(sequence: int, message_id: str) -> SequencedRawBrowserMessage:
    return SequencedRawBrowserMessage(
        source_sequence=sequence,
        conversation_id="pdd-cursor-safe-conversation",
        external_message_id=message_id,
        sender="synthetic-customer",
        content=f"synthetic observation {message_id}",
        timestamp=NOW,
        observation_mechanism=BrowserObservationMechanism.DOM_SNAPSHOT,
    )


def capture(
    *messages: SequencedRawBrowserMessage,
    next_cursor: str,
    oldest: int | None = None,
) -> BrowserPageCapture:
    return BrowserPageCapture(
        attachment_ref="queued-attachment",
        page_context_id="queued-page",
        page_generation=1,
        selector_contract_id="queued-selector",
        selector_fingerprint="0" * 64,
        requested_cursor=None,
        next_cursor=next_cursor,
        oldest_available_sequence=(
            oldest if oldest is not None else messages[0].source_sequence
        ),
        messages=tuple(messages),
        page_revision="queued-revision",
        captured_at=NOW,
    )


def build_runtime(foundation):
    selector = verified_mock_pdd_merchant_chat_v1(NOW)
    registry = SelectorRegistry()
    registry.register(selector, activate=True)
    manager = BrowserSessionManager(
        FakeBrowserRuntimeDriver(clock=lambda: NOW),
        BrowserProfileReference(
            profile_id="pdd-cursor-safe-profile",
            account_ref="pdd-cursor-safe-account",
            storage_reference="profile-ref://pdd/cursor-safe-account",
        ),
        strategy=ChromeLaunchStrategy.MOCK,
        selector_contract_version=selector.version,
        clock=lambda: NOW,
    )
    manager.start()
    page_port = FakeReadOnlyBrowserPageCapturePort()
    browser_store = SqlAlchemyBrowserObservationStore(foundation["session_factory"])
    observer = BrowserPageObserver(
        manager.snapshot,
        page_port,
        PDDMessageExtractor(),
        registry,
        browser_store,
        stream_id=STREAM_ID,
        clock=lambda: NOW,
    )
    observer.attach()

    credential = CredentialReference(
        credential_ref="vault://pdd/cursor-safe-store",
        provider="test-vault",
        version="v1",
    )
    session_store = ChannelSessionStore(foundation["uow_factory"])
    session_store.create_instance(
        ChannelInstance(
            instance_id=INSTANCE_ID,
            platform="pdd",
            store_id=STORE_ID,
            status=ChannelInstanceStatus.CONNECTED,
            adapter_type="BrowserPDDMessageReader.v1",
            active_session_id="pdd-cursor-safe-session",
            created_at=NOW,
            updated_at=NOW,
        ),
        ChannelSession(
            session_id="pdd-cursor-safe-session",
            instance_id=INSTANCE_ID,
            status=ChannelSessionStatus.CONNECTED,
            credential_ref=credential,
            credential_lease_ref="credential-lease-ref://pdd/cursor-safe",
            heartbeat_time=NOW,
            expires_at=datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc),
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    reliability = MessageReliabilityService(
        foundation["uow_factory"],
        session_store,
        clock=lambda: NOW,
    )
    reader = BrowserPDDMessageReader(
        observer,
        manager.snapshot,
        store_id=STORE_ID,
        clock=lambda: NOW,
    )
    runtime = PDDDurableMessageObservationRuntime(
        reader,
        reliability,
        ConversationService(foundation["uow_factory"], foundation["gateway"]),
        foundation["uow_factory"],
        instance_id=INSTANCE_ID,
        clock=lambda: NOW,
    )
    return page_port, browser_store, reliability, runtime


def test_crash_after_message_commit_before_cursor_ack_recovers_without_loss(
    foundation,
) -> None:
    page_port, browser_store, reliability, runtime = build_runtime(foundation)
    first_capture = capture(raw(10, "pdd-safe-message-10"), next_cursor="cursor-10")
    page_port.enqueue(first_capture)

    def crash() -> None:
        raise RuntimeError("simulated process crash after SQLite commit")

    with pytest.raises(RuntimeError, match="simulated process crash"):
        runtime.ingest_once(after_transaction_commit=crash)

    assert browser_store.load(STREAM_ID).cursor is None
    assert reliability.get_cursor(INSTANCE_ID).last_sequence == 1
    assert len(reliability.receive_pending(INSTANCE_ID)) == 1

    page_port.enqueue(first_capture)
    replay = runtime.ingest_once()
    evidence = runtime.drain_pending()

    assert replay.persisted_message_ids == ()
    assert replay.duplicate_message_ids == ("pdd-safe-message-10",)
    assert replay.persistence_preceded_cursor_ack is True
    assert browser_store.load(STREAM_ID).cursor == "cursor-10"
    assert evidence[0].decision_state == "WAITING_APPROVAL"
    assert reliability.get_cursor(INSTANCE_ID).last_acked_sequence == 1
    with foundation["session_factory"]() as session:
        assert len(list(session.scalars(select(ChannelMessageInboxRow)))) == 1
        assert len(list(session.scalars(select(DecisionRow)))) == 1


def test_duplicate_source_delivery_is_idempotent_after_cursor_commit(foundation) -> None:
    page_port, browser_store, reliability, runtime = build_runtime(foundation)
    item = raw(3, "pdd-safe-duplicate")
    page_port.enqueue(capture(item, next_cursor="cursor-3"))
    first = runtime.run_once()

    page_port.enqueue(
        capture(item, next_cursor="cursor-duplicate", oldest=3)
    )
    ingest = runtime.ingest_once()
    second = runtime.drain_pending()

    assert len(first) == 1
    assert ingest.persisted_message_ids == ()
    assert ingest.duplicate_message_ids == ()
    assert second == ()
    assert browser_store.load(STREAM_ID).duplicate_count == 1
    assert reliability.get_cursor(INSTANCE_ID).last_sequence == 1


def test_missing_browser_sequence_fails_before_persist_or_cursor_advance(
    foundation,
) -> None:
    page_port, browser_store, reliability, runtime = build_runtime(foundation)
    page_port.enqueue(capture(raw(7, "pdd-safe-message-7"), next_cursor="cursor-7"))
    runtime.run_once()

    page_port.enqueue(
        capture(raw(9, "pdd-safe-message-9"), next_cursor="cursor-9", oldest=7)
    )
    with pytest.raises(BrowserObservationMissedMessages):
        runtime.ingest_once()

    assert browser_store.load(STREAM_ID).cursor == "cursor-7"
    assert reliability.get_cursor(INSTANCE_ID).last_sequence == 1
    with foundation["session_factory"]() as session:
        assert len(list(session.scalars(select(ChannelMessageInboxRow)))) == 1
