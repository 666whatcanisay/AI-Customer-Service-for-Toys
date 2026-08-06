from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from channel_engine.browser import (
    BrowserHeartbeatState,
    BrowserLoginState,
    BrowserObservationConflict,
    BrowserObservationMechanism,
    BrowserObservationMissedMessages,
    BrowserObservationSelectorMismatch,
    BrowserObservationSyncState,
    BrowserObservationUnavailable,
    BrowserPageCapture,
    BrowserPageObserver,
    BrowserPageObserverState,
    BrowserProfileReference,
    BrowserSessionManager,
    BrowserSessionState,
    ChromeLaunchStrategy,
    FakeBrowserRuntimeDriver,
    FakeReadOnlyBrowserPageCapturePort,
    PDDMessageExtractor,
    SelectorRegistry,
    SequencedRawBrowserMessage,
    SqlAlchemyBrowserObservationStore,
    verified_mock_pdd_merchant_chat_v1,
)
from channel_engine.storage.orm import (
    BrowserObservationCheckpointRow,
    BrowserObservationIdentityRow,
)


NOW = datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)
STREAM_ID = "pdd-browser:synthetic-observation-account"


def profile() -> BrowserProfileReference:
    return BrowserProfileReference(
        profile_id="pdd-browser-observation-profile",
        account_ref="synthetic-observation-account",
        storage_reference="profile-ref://pdd/synthetic-observation-account",
    )


def message(
    sequence: int,
    external_message_id: str,
    *,
    conversation_id: str = "synthetic-conversation",
    content: str | None = None,
) -> SequencedRawBrowserMessage:
    return SequencedRawBrowserMessage(
        source_sequence=sequence,
        conversation_id=conversation_id,
        external_message_id=external_message_id,
        sender="synthetic-customer",
        content=content or f"synthetic message {external_message_id}",
        timestamp=NOW + timedelta(seconds=sequence),
        observation_mechanism=BrowserObservationMechanism.DOM_SNAPSHOT,
    )


def capture(
    *messages: SequencedRawBrowserMessage,
    next_cursor: str | None,
    oldest_available_sequence: int | None = None,
) -> BrowserPageCapture:
    oldest = (
        oldest_available_sequence
        if oldest_available_sequence is not None
        else (messages[0].source_sequence if messages else None)
    )
    return BrowserPageCapture(
        attachment_ref="queued-read-attachment",
        page_context_id="queued-page-context",
        page_generation=1,
        selector_contract_id="queued:selector:v1",
        selector_fingerprint="0" * 64,
        requested_cursor=None,
        next_cursor=next_cursor,
        oldest_available_sequence=oldest,
        messages=tuple(messages),
        page_revision="queued-page-revision",
        captured_at=NOW,
    )


def observer_fixture(foundation):
    selector = verified_mock_pdd_merchant_chat_v1(NOW)
    registry = SelectorRegistry()
    registry.register(selector, activate=True)
    driver = FakeBrowserRuntimeDriver(
        page_revision="observation-page-revision-1",
        clock=lambda: NOW,
    )
    manager = BrowserSessionManager(
        driver,
        profile(),
        strategy=ChromeLaunchStrategy.MOCK,
        selector_contract_version=selector.version,
        clock=lambda: NOW,
    )
    manager.start()
    page_port = FakeReadOnlyBrowserPageCapturePort()
    store = SqlAlchemyBrowserObservationStore(foundation["session_factory"])
    observer = BrowserPageObserver(
        manager.snapshot,
        page_port,
        PDDMessageExtractor(),
        registry,
        store,
        stream_id=STREAM_ID,
        clock=lambda: NOW,
    )
    return selector, registry, driver, manager, page_port, store, observer


def test_observation_lifecycle_extracts_normalized_messages_without_page_writes(
    foundation,
) -> None:
    _selector, _registry, _driver, _manager, page_port, store, observer = (
        observer_fixture(foundation)
    )
    attachment = observer.attach()
    assert attachment.read_only is True
    assert observer.attach() == attachment
    assert page_port.attach_count == 1
    assert observer.heartbeat().healthy is True
    page_port.enqueue(
        capture(
            message(20, "message-20"),
            message(21, "message-21"),
            next_cursor="cursor-21",
        )
    )

    normalized = observer.capture()

    assert [item.external_message_id for item in normalized] == [
        "message-20",
        "message-21",
    ]
    assert all(item.channel == "pdd" for item in normalized)
    assert normalized[0].conversation_id == "synthetic-conversation"
    assert normalized[0].sender == "synthetic-customer"
    assert normalized[0].content == "synthetic message message-20"
    assert normalized[0].timestamp == NOW + timedelta(seconds=20)
    checkpoint = store.load(STREAM_ID)
    assert checkpoint.cursor == "cursor-21"
    assert checkpoint.last_sequence == 21
    assert checkpoint.accepted_count == 2
    assert checkpoint.sync_state is BrowserObservationSyncState.IN_SYNC
    assert page_port.page_write_operations == 0

    with foundation["session_factory"]() as session:
        checkpoint_row = session.get(BrowserObservationCheckpointRow, STREAM_ID)
        identities = session.scalars(
            select(BrowserObservationIdentityRow).where(
                BrowserObservationIdentityRow.stream_id == STREAM_ID
            )
        ).all()
    assert checkpoint_row is not None
    assert len(identities) == 2
    persisted = " ".join(
        f"{row.identity_digest} {row.payload_fingerprint}" for row in identities
    )
    assert "synthetic-customer" not in persisted
    assert "synthetic message" not in persisted

    observer.detach()
    assert observer.state is BrowserPageObserverState.DETACHED
    assert page_port.detach_count == 1
    assert observer.heartbeat().failure_code == "BROWSER_OBSERVER_DETACHED"


def test_duplicate_message_is_suppressed_and_changed_payload_fails_closed(
    foundation,
) -> None:
    _selector, _registry, _driver, _manager, page_port, store, observer = (
        observer_fixture(foundation)
    )
    observer.attach()
    original = message(1, "stable-message")
    page_port.enqueue(capture(original, next_cursor="cursor-1"))
    assert len(observer.capture()) == 1

    page_port.enqueue(
        capture(
            original,
            next_cursor="cursor-duplicate",
            oldest_available_sequence=1,
        )
    )
    assert observer.capture() == ()
    checkpoint = store.load(STREAM_ID)
    assert checkpoint.cursor == "cursor-duplicate"
    assert checkpoint.last_sequence == 1
    assert checkpoint.duplicate_count == 1

    same_external_id_other_conversation = message(
        2,
        "stable-message",
        conversation_id="second-synthetic-conversation",
    )
    page_port.enqueue(
        capture(
            same_external_id_other_conversation,
            next_cursor="cursor-2",
            oldest_available_sequence=1,
        )
    )
    accepted = observer.capture()
    assert [item.conversation_id for item in accepted] == [
        "second-synthetic-conversation"
    ]

    changed = original.model_copy(update={"content": "changed synthetic payload"})
    page_port.enqueue(
        capture(
            changed,
            next_cursor="cursor-conflict",
            oldest_available_sequence=1,
        )
    )
    with pytest.raises(BrowserObservationConflict, match="changed payload"):
        observer.capture()

    failed = store.load(STREAM_ID)
    assert failed.cursor == "cursor-2"
    assert failed.last_sequence == 2
    assert failed.sync_state is BrowserObservationSyncState.FAILED
    assert failed.last_error_code == "BROWSER_OBSERVATION_IDENTITY_REUSED"
    assert observer.state is BrowserPageObserverState.FAILED


def test_sql_cursor_recovers_after_observer_restart_and_detects_missed_message(
    foundation,
) -> None:
    selector, registry, _driver, manager, first_port, _store, first = (
        observer_fixture(foundation)
    )
    first.attach()
    first_port.enqueue(
        capture(
            message(10, "message-10"),
            message(11, "message-11"),
            next_cursor="cursor-11",
        )
    )
    assert len(first.capture()) == 2
    first.detach()

    replacement_port = FakeReadOnlyBrowserPageCapturePort()
    replacement_store = SqlAlchemyBrowserObservationStore(
        foundation["session_factory"]
    )
    replacement = BrowserPageObserver(
        manager.snapshot,
        replacement_port,
        PDDMessageExtractor(),
        registry,
        replacement_store,
        stream_id=STREAM_ID,
        clock=lambda: NOW,
    )
    replacement.attach()
    replacement_port.enqueue(
        capture(
            message(12, "message-12"),
            next_cursor="cursor-12",
            oldest_available_sequence=10,
        )
    )
    recovered = replacement.capture()
    assert [item.external_message_id for item in recovered] == ["message-12"]
    assert replacement_port.capture_history[0] == ("cursor-11", 11, 100)
    assert replacement.checkpoint().last_sequence == 12
    assert replacement.checkpoint().selector_contract_id == selector.contract_id

    replacement_port.enqueue(
        capture(
            message(14, "message-14"),
            next_cursor="cursor-14",
            oldest_available_sequence=10,
        )
    )
    with pytest.raises(BrowserObservationMissedMessages, match="gap"):
        replacement.capture()
    failed = replacement.checkpoint()
    assert failed.cursor == "cursor-12"
    assert failed.last_sequence == 12
    assert failed.last_error_code == "BROWSER_OBSERVATION_MESSAGE_GAP"


def test_page_crash_degrades_observer_and_blocks_capture(foundation) -> None:
    _selector, _registry, driver, manager, page_port, store, observer = (
        observer_fixture(foundation)
    )
    observer.attach()
    page_port.enqueue(capture(message(1, "before-crash"), next_cursor="cursor-1"))
    assert len(observer.capture()) == 1
    driver.heartbeat_state = BrowserHeartbeatState.CRASHED
    manager.heartbeat()
    assert manager.snapshot().state is BrowserSessionState.CRASHED

    heartbeat = observer.heartbeat()
    assert heartbeat.healthy is False
    assert heartbeat.failure_code == "BROWSER_SESSION_NOT_ACTIVE"
    assert observer.state is BrowserPageObserverState.DEGRADED
    with pytest.raises(BrowserObservationUnavailable, match="not ACTIVE"):
        observer.capture()
    assert page_port.capture_count == 1
    assert store.load(STREAM_ID).cursor == "cursor-1"

    driver.heartbeat_state = BrowserHeartbeatState.HEALTHY
    recovered = manager.recover()
    assert recovered.state is BrowserSessionState.ACTIVE
    assert recovered.generation == 2
    observer.attach()
    page_port.enqueue(
        capture(
            message(2, "after-crash"),
            next_cursor="cursor-2",
            oldest_available_sequence=1,
        )
    )
    resumed = observer.capture()
    assert [item.external_message_id for item in resumed] == ["after-crash"]
    assert page_port.capture_history[-1] == ("cursor-1", 1, 100)
    assert store.load(STREAM_ID).last_sequence == 2


def test_login_expiry_degrades_observer_and_requires_human_takeover(
    foundation,
) -> None:
    _selector, _registry, driver, manager, page_port, _store, observer = (
        observer_fixture(foundation)
    )
    observer.attach()
    driver.login_state = BrowserLoginState.EXPIRED
    expired = manager.heartbeat()
    assert expired.state is BrowserSessionState.EXPIRED
    assert expired.human_takeover_required is True

    heartbeat = observer.heartbeat()
    assert heartbeat.healthy is False
    assert heartbeat.failure_code == "BROWSER_LOGIN_EXPIRED"
    with pytest.raises(BrowserObservationUnavailable, match="login is required"):
        observer.capture()
    assert page_port.capture_count == 0
    assert page_port.page_write_operations == 0


def test_real_page_port_cannot_attach_mock_selector_contract(foundation) -> None:
    _selector, registry, _driver, manager, _page_port, store, _observer = (
        observer_fixture(foundation)
    )

    class RealPageBoundaryStub(FakeReadOnlyBrowserPageCapturePort):
        real_page_transport = True

    observer = BrowserPageObserver(
        manager.snapshot,
        RealPageBoundaryStub(),
        PDDMessageExtractor(),
        registry,
        store,
        stream_id="pdd-browser:real-boundary-synthetic",
        clock=lambda: NOW,
    )
    with pytest.raises(BrowserObservationSelectorMismatch, match="mock selector"):
        observer.attach()
