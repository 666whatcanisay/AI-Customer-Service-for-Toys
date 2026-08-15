from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.assistant_events import AssistantEventJournal
from channel_agent.control_v2 import AgentAssistantSnapshot
from channel_agent.desktop import DesktopAssistantServer


def _snapshot(
    *, revision: int = 3, customer_message_id: str | None = None
) -> AgentAssistantSnapshot:
    now = datetime.now(UTC)
    return AgentAssistantSnapshot(
        agent_id="agent-1",
        device_id="device-1",
        store_id="store-1",
        conversation_id="conversation-1",
        revision=revision,
        status="WAITING_APPROVAL",
        turn_id="turn-1",
        customer_message_id=customer_message_id,
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


def test_desktop_feed_uses_verified_customer_message_id_and_keeps_old_snapshot_compatible(
    tmp_path: Path,
) -> None:
    del tmp_path
    verified = DesktopAssistantServer._snapshot_feed(
        _snapshot(customer_message_id="pdd-customer-message-001").model_dump(
            mode="json"
        )
    )
    assert verified["reply"]["messageId"] == "pdd-customer-message-001"
    assert (
        verified["conversations"][0]["messages"][0]["messageId"]
        == "pdd-customer-message-001"
    )

    legacy_payload = _snapshot().model_dump(mode="json", exclude={"customer_message_id"})
    restored = AgentAssistantSnapshot.model_validate(legacy_payload)
    assert restored.customer_message_id is None
    legacy = DesktopAssistantServer._snapshot_feed(restored.model_dump(mode="json"))
    assert legacy["reply"]["messageId"] == "turn-1"


def test_desktop_feed_projects_customer_and_operator_history_in_time_order() -> None:
    snapshot = _snapshot(customer_message_id="customer-message-1").model_copy(
        update={
            "ai_cs_action": "DIRECT_ANSWER",
            "visible_history": (
                {
                    "message_id": "customer-message-1",
                    "sender": "CUSTOMER",
                    "content": "这个商品拼好后有多大？",
                    "timestamp": "2026-08-15T07:20:00+00:00",
                    "privacy_filtered": True,
                },
                {
                    "message_id": "operator-message-1",
                    "sender": "OPERATOR",
                    "content": "亲，这款拼好后约20cm左右哦。",
                    "timestamp": "2026-08-15T07:20:08+00:00",
                    "privacy_filtered": True,
                },
            ),
        }
    )

    conversation = DesktopAssistantServer._snapshot_feed(
        snapshot.model_dump(mode="json")
    )["conversations"][0]

    assert [item["senderRole"] for item in conversation["messages"]] == [
        "CUSTOMER",
        "AGENT",
    ]
    assert conversation["messages"][1]["messageId"] == "operator-message-1"
    assert conversation["attentionLevel"] == "NONE"
    assert conversation["requiresHuman"] is False


def test_desktop_feed_marks_explicit_human_transfer_red() -> None:
    snapshot = _snapshot().model_copy(
        update={
            "status": "MANUAL_INTERVENTION",
            "ai_cs_action": "TRANSFER_HUMAN",
        }
    )

    conversation = DesktopAssistantServer._snapshot_feed(
        snapshot.model_dump(mode="json")
    )["conversations"][0]

    assert conversation["requiresHuman"] is True
    assert conversation["attentionLevel"] == "HUMAN_REQUIRED"


def test_successful_auto_reply_is_shown_as_outbound_and_not_waiting(tmp_path: Path) -> None:
    journal = AssistantEventJournal(tmp_path / "assistant-events.sqlite3")
    snapshot = _snapshot(customer_message_id="message-1")
    journal.update_snapshots((snapshot,))
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "controlled-auto-successes.json").write_text(
        json.dumps(
            {
                "schema_version": "controlled-auto-successes.v1",
                "items": [
                    {
                        "decision_id": "decision-1",
                        "conversation_id": "conversation-1",
                        "receipt_id": "receipt-1",
                        "sent_at": (
                            snapshot.updated_at + timedelta(seconds=1)
                        ).isoformat(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    conversation = DesktopAssistantServer(
        data_root=tmp_path, event_journal=journal
    ).assistant_feed()["conversations"][0]

    assert conversation["attentionLevel"] == "NONE"
    assert conversation["processingStage"] == "AUTO_REPLIED"
    assert conversation["autoReplyReceiptId"] == "receipt-1"
    assert conversation["messages"][-1]["senderRole"] == "AGENT"
