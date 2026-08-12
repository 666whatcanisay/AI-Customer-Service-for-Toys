from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.assistant_events import AssistantEventJournal
from channel_agent.control_v2 import AgentAssistantSnapshot
from channel_agent.desktop import DesktopAssistantServer


def _snapshot(*, revision: int = 3) -> AgentAssistantSnapshot:
    now = datetime.now(UTC)
    return AgentAssistantSnapshot(
        agent_id="agent-1",
        device_id="device-1",
        store_id="store-1",
        conversation_id="conversation-1",
        revision=revision,
        status="WAITING_APPROVAL",
        turn_id="turn-1",
        decision_id="decision-1",
        request_id="request-1",
        customer_reference="customer-1",
        current_question="privacy filtered question",
        action="REPLY",
        reply_content="answer",
        risk_level="LOW",
        updated_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def test_read_cursor_is_metadata_only_monotonic_and_restart_durable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "assistant-events.sqlite3"
    first = AssistantEventJournal(path)
    assert first.read_revision("conversation-1") == 0
    assert first.mark_conversation_read("conversation-1", 3) == 3
    assert first.mark_conversation_read("conversation-1", 2) == 3

    restarted = AssistantEventJournal(path)
    assert restarted.read_revision("conversation-1") == 3


def test_desktop_multi_conversation_feed_uses_read_cursor(tmp_path: Path) -> None:
    journal = AssistantEventJournal(tmp_path / "assistant-events.sqlite3")
    journal.update_snapshots((_snapshot(),))
    runtime = DesktopAssistantServer(data_root=tmp_path, event_journal=journal)

    unread = runtime.assistant_feed()["conversations"][0]
    assert unread["unreadCount"] == 1
    assert unread["customerReference"] == "customer-1"
    assert unread["reply"]["customerReference"] == "customer-1"
    assert unread["revision"] == 3
    assert "_revision" not in unread

    result = runtime.mark_conversation_read("conversation-1")
    assert result["read_revision"] == 3
    read = runtime.assistant_feed()["conversations"][0]
    assert read["unreadCount"] == 0
    assert read["readRevision"] == 3
