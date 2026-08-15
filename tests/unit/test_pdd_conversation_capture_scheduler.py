from __future__ import annotations

from datetime import UTC, datetime

from channel_agent.pdd_conversation_capture import (
    DurablePDDConversationCaptureStore,
    PDDConversationCaptureState,
    PDDReplyAttentionState,
)

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)
EVIDENCE = "sha256:" + "a" * 64


def observe(
    store: DurablePDDConversationCaptureStore,
    conversation_id: str,
    *,
    state: PDDReplyAttentionState = PDDReplyAttentionState.COUNTDOWN,
    seconds: int | None = 30,
    sequence: int | None = 1,
    message_id: str | None = None,
    position: int = 0,
):
    return store.observe_attention(
        store_id="store-1",
        platform_store_id="328616090",
        conversation_id=conversation_id,
        attention_state=state,
        attention_verified=True,
        attention_seconds=seconds,
        attention_evidence_hash=EVIDENCE,
        page_position=position,
        latest_sequence=sequence,
        latest_message_id=(
            message_id
            if message_id is not None
            else None if sequence is None else f"message-{sequence}"
        ),
    )


def complete(
    store: DurablePDDConversationCaptureStore,
    conversation_id: str,
    *,
    sequence: int = 1,
):
    assert store.claim("store-1", "328616090", conversation_id)
    waiting = store.mark_captured(
        store_id="store-1",
        platform_store_id="328616090",
        conversation_id=conversation_id,
        latest_message_id=f"message-{sequence}",
        latest_sequence=sequence,
        host_acked_sequence=None,
    )
    assert waiting.state is PDDConversationCaptureState.CAPTURED_WAITING_ACK
    result = store.reconcile_ack(
        "store-1", "328616090", conversation_id, sequence
    )
    assert result is not None
    assert result.state is PDDConversationCaptureState.COMPLETED
    return result


def test_completed_conversation_reopens_only_for_new_message_or_marker_reentry(
    tmp_path,
) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    assert observe(store, "conversation-a") is not None
    complete(store, "conversation-a")

    continuous = observe(store, "conversation-a", sequence=1)
    assert continuous is not None
    assert continuous.state is PDDConversationCaptureState.COMPLETED
    assert store.pending() == ()

    newer = observe(store, "conversation-a", sequence=2)
    assert newer is not None
    assert newer.state is PDDConversationCaptureState.PENDING

    complete(store, "conversation-a", sequence=2)
    observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=2,
    )
    reappeared = observe(store, "conversation-a", sequence=2)
    assert reappeared is not None
    assert reappeared.state is PDDConversationCaptureState.PENDING


def test_changed_latest_message_id_reopens_when_page_has_no_stable_sequence(
    tmp_path,
) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    observe(store, "conversation-a", sequence=None, message_id="message-a")
    complete(store, "conversation-a")

    changed = observe(
        store,
        "conversation-a",
        sequence=None,
        message_id="message-b",
    )
    assert changed is not None
    assert changed.state is PDDConversationCaptureState.PENDING


def test_missing_attention_establishes_preview_baseline_without_scheduling_history(
    tmp_path,
) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )

    baseline = observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=None,
        message_id="preview-a",
    )

    assert baseline is not None
    assert baseline.state is PDDConversationCaptureState.COMPLETED
    assert baseline.attention_present is False
    assert baseline.latest_message_id == "preview-a"
    assert store.pending() == ()


def test_preview_change_schedules_exact_conversation_when_attention_is_missing(
    tmp_path,
) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=None,
        message_id="preview-a",
    )

    changed = observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=None,
        message_id="preview-b",
    )

    assert changed is not None
    assert changed.state is PDDConversationCaptureState.PENDING
    assert changed.attention_present is False
    assert [item.conversation_id for item in store.pending()] == ["conversation-a"]


def test_preview_identity_upgrade_rebaselines_without_scheduling_history(tmp_path) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=None,
        message_id="sha256:" + "a" * 64,
    )

    upgraded = observe(
        store,
        "conversation-a",
        state=PDDReplyAttentionState.NONE,
        seconds=None,
        sequence=None,
        message_id="preview-sha256:" + "b" * 64,
    )

    assert upgraded is not None
    assert upgraded.state is PDDConversationCaptureState.COMPLETED
    assert upgraded.latest_message_id == "preview-sha256:" + "b" * 64
    assert store.pending() == ()


def test_countdown_reset_reopens_same_conversation_without_row_message_id(
    tmp_path,
) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    observe(
        store,
        "conversation-a",
        seconds=167,
        sequence=None,
        message_id=None,
    )
    complete(store, "conversation-a")

    decreasing = observe(
        store,
        "conversation-a",
        seconds=160,
        sequence=None,
        message_id=None,
    )
    assert decreasing is not None
    assert decreasing.state is PDDConversationCaptureState.COMPLETED

    restarted = observe(
        store,
        "conversation-a",
        seconds=180,
        sequence=None,
        message_id=None,
    )
    assert restarted is not None
    assert restarted.state is PDDConversationCaptureState.PENDING


def test_scheduler_priority_limit_and_conversation_isolation(tmp_path) -> None:
    store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    observe(
        store,
        "countdown-late",
        seconds=90,
        position=0,
    )
    observe(
        store,
        "overdue",
        state=PDDReplyAttentionState.OVERDUE,
        seconds=120,
        position=3,
    )
    observe(store, "countdown-urgent", seconds=5, position=4)
    for index in range(25):
        observe(store, f"unknown-{index:02d}", state=PDDReplyAttentionState.UNKNOWN)

    pending = store.pending(limit=100)
    assert len(pending) == 20
    assert [item.conversation_id for item in pending[:3]] == [
        "overdue",
        "countdown-urgent",
        "countdown-late",
    ]

    complete(store, "overdue")
    assert store.get("store-1", "328616090", "countdown-urgent").state is (
        PDDConversationCaptureState.PENDING
    )


def test_interrupted_navigation_is_recovered_without_losing_the_task(tmp_path) -> None:
    path = tmp_path / "spool.sqlite3"
    store = DurablePDDConversationCaptureStore(path, clock=lambda: NOW)
    observe(store, "conversation-a")
    assert store.claim("store-1", "328616090", "conversation-a")

    restarted = DurablePDDConversationCaptureStore(path, clock=lambda: NOW)
    assert restarted.recover_interrupted() == 1
    record = restarted.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.PENDING
    assert record.last_error_code == "RECOVERED_AFTER_NAVIGATION_INTERRUPTION"
