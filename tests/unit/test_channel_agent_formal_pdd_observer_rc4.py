from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from channel_agent.edge_pdd_observe import (
    PDDSelectorRuntimeEvidence,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceSnapshot,
)
from channel_agent.edge_spool import DurableEdgeSpool
from channel_agent.pdd_observer import (
    PDDConversationNotActive,
    PDDConversationSummary,
    PDDMessageObserver,
    PDDObserverFatalError,
)

NOW = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
FINGERPRINT = "sha256:" + "b" * 64
CUSTOMER = "sha256:" + "c" * 64


class PlainProtector:
    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


class Driver:
    def __init__(self, summaries, snapshots):
        self.summaries = tuple(summaries)
        self.snapshots = snapshots

    def selector_evidence(self, capability: str):
        return PDDSelectorRuntimeEvidence(
            evidence_hash=DIGEST,
            selector_contract_version="pdd-observe-test",
            page_fingerprint=FINGERPRINT,
            capability="OBSERVE",
            verified_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )

    def scan_conversations(self):
        return self.summaries

    def capture_conversation(self, summary):
        value = self.snapshots[summary.conversation_id]
        if isinstance(value, Exception):
            raise value
        return value


class ManualCurrentConversationDriver(Driver):
    navigation_enabled = False


def summary(conversation: str, *, unread: int | None, sequence: int = 3):
    return PDDConversationSummary(
        store_id="c-store-1",
        platform_store_id="328616090",
        conversation_id=conversation,
        customer_reference=CUSTOMER,
        unread_count=unread,
        last_activity_at=NOW,
        latest_sequence=sequence,
    )


def message(sequence: int, sender: str, content: str = "test"):
    return PDDWorkspaceMessage(
        external_message_id=f"message-{sequence}",
        sender=sender,
        content=content,
        timestamp=NOW + timedelta(seconds=sequence),
        sequence=sequence,
    )


def snapshot(conversation: str, messages):
    return PDDWorkspaceSnapshot(
        store_id="c-store-1",
        platform_store_id="328616090",
        conversation_id=conversation,
        customer_reference=CUSTOMER,
        page_fingerprint=FINGERPRINT,
        selector_evidence_hash=DIGEST,
        page_state="CUSTOMER_SERVICE_RUNNING",
        messages=tuple(messages),
        captured_at=NOW,
    )


def observer(tmp_path, driver, forwarded, diagnostics):
    spool = DurableEdgeSpool(tmp_path / "spool.sqlite3", PlainProtector(), clock=lambda: NOW)
    return PDDMessageObserver(
        driver=driver,
        mapper=PDDWorkspaceObservationMapper(agent_id="agent-1", device_id="device-1"),
        spool=spool,
        forward=forwarded.append,
        diagnostic=lambda code, item, details: diagnostics.append(
            (code, item.conversation_id, details)
        ),
        clock=lambda: NOW,
    )


def test_startup_unread_customer_followed_by_bot_is_not_lost(tmp_path):
    item = summary("conversation-1", unread=1)
    forwarded = []
    diagnostics = []
    value = observer(
        tmp_path,
        Driver(
            [item],
            {
                item.conversation_id: snapshot(
                    item.conversation_id,
                    [message(1, "CUSTOMER", "where"), message(2, "BOT", "notice")],
                )
            },
        ),
        forwarded,
        diagnostics,
    ).scan_once()

    assert value.observations_forwarded == 1
    assert forwarded[0].payload["origin"] == "STARTUP_UNREAD"
    assert forwarded[0].payload["content"] == "where"


def test_operator_tail_closes_prior_customer_group(tmp_path):
    item = summary("conversation-1", unread=1)
    forwarded = []
    diagnostics = []
    observer(
        tmp_path,
        Driver(
            [item],
            {item.conversation_id: snapshot(item.conversation_id, [message(1, "CUSTOMER"), message(2, "OPERATOR")])},
        ),
        forwarded,
        diagnostics,
    ).scan_once()
    assert forwarded == []


def test_inactive_unread_conversation_requires_human_selection(tmp_path):
    first = summary("visible", unread=1)
    second = summary("not-visible", unread=2)
    forwarded = []
    diagnostics = []
    result = observer(
        tmp_path,
        Driver(
            [first, second],
            {
                "visible": snapshot("visible", [message(1, "CUSTOMER")]),
                "not-visible": PDDConversationNotActive("human selection required"),
            },
        ),
        forwarded,
        diagnostics,
    ).scan_once()

    assert result.observations_forwarded == 1
    assert result.manual_review_required == 1
    assert diagnostics[0][0] == "CONVERSATION_REQUIRES_HUMAN_SELECTION"


def test_unknown_startup_unread_state_is_never_silently_baselined(tmp_path):
    item = summary("conversation-1", unread=None)
    diagnostics = []
    result = observer(
        tmp_path,
        Driver([item], {item.conversation_id: snapshot(item.conversation_id, [])}),
        [],
        diagnostics,
    ).scan_once()
    assert result.manual_review_required == 1
    assert result.baselines_established == 0
    assert diagnostics[0][0] == "STARTUP_UNREAD_STATE_UNKNOWN"


def test_manual_current_conversation_baselines_without_navigation_then_reads_new_message(
    tmp_path,
):
    item = summary("conversation-1", unread=None)
    driver = ManualCurrentConversationDriver(
        [item],
        {
            item.conversation_id: snapshot(
                item.conversation_id,
                [message(1, "CUSTOMER", "old"), message(2, "OPERATOR", "done")],
            )
        },
    )
    forwarded = []
    diagnostics = []
    runtime = observer(tmp_path, driver, forwarded, diagnostics)

    baseline = runtime.scan_once()

    assert baseline.baselines_established == 1
    assert baseline.manual_review_required == 0
    assert forwarded == []
    assert diagnostics == []

    driver.snapshots[item.conversation_id] = snapshot(
        item.conversation_id,
        [
            message(1, "CUSTOMER", "old"),
            message(2, "OPERATOR", "done"),
            message(3, "CUSTOMER", "new"),
        ],
    )
    captured = runtime.scan_once()

    assert captured.observations_forwarded == 1
    assert forwarded[0].payload["content"] == "new"
    assert forwarded[0].payload["origin"] == "LIVE_PDD"


def test_manual_current_conversation_mode_never_selects_inactive_rows(tmp_path):
    active = summary("active", unread=None)
    inactive = summary("inactive", unread=None)
    forwarded = []
    diagnostics = []
    result = observer(
        tmp_path,
        ManualCurrentConversationDriver(
            [active, inactive],
            {
                "active": snapshot("active", [message(1, "OPERATOR", "done")]),
                "inactive": PDDConversationNotActive("not selected"),
            },
        ),
        forwarded,
        diagnostics,
    ).scan_once()

    assert result.baselines_established == 1
    assert result.manual_review_required == 0
    assert forwarded == []
    assert diagnostics == []


def test_page_fingerprint_change_fails_closed(tmp_path):
    item = summary("conversation-1", unread=1)
    changed = snapshot(item.conversation_id, [message(1, "CUSTOMER")]).model_copy(
        update={"page_fingerprint": "sha256:" + "d" * 64}
    )
    with pytest.raises(PDDObserverFatalError):
        observer(tmp_path, Driver([item], {item.conversation_id: changed}), [], []).scan_once()
