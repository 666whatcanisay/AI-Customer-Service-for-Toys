from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from channel_agent.edge_pdd_observe import (
    PDDSelectorRuntimeEvidence,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceSnapshot,
)
from channel_agent.edge_spool import DurableEdgeSpool
from channel_agent.pdd_conversation_capture import (
    DurablePDDConversationCaptureStore,
    PDDConversationCaptureState,
    PDDReplyAttentionState,
)
from channel_agent.pdd_conversation_navigation import (
    WebSocketPDDConversationNavigationPort,
)
from channel_agent.pdd_login import PDDCDPPageTarget
from channel_agent.pdd_observer import (
    PDDConversationNavigationError,
    PDDConversationNotActive,
    PDDConversationSummary,
    PDDMessageObserver,
)

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
FINGERPRINT = "sha256:" + "b" * 64


class PlainProtector:
    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


def customer_reference(conversation_id: str) -> str:
    return "sha256:" + hashlib.sha256(conversation_id.encode()).hexdigest()


def summary(
    conversation_id: str,
    *,
    sequence: int,
    position: int,
    attention: PDDReplyAttentionState = PDDReplyAttentionState.COUNTDOWN,
    attention_seconds: int | None = 30,
    unread: int = 1,
) -> PDDConversationSummary:
    return PDDConversationSummary(
        store_id="store-1",
        platform_store_id="328616090",
        conversation_id=conversation_id,
        customer_reference=customer_reference(conversation_id),
        unread_count=unread,
        last_activity_at=NOW + timedelta(seconds=sequence),
        latest_sequence=sequence,
        latest_message_id=f"{conversation_id}-message-{sequence}",
        page_position=position,
        attention_state=attention,
        attention_verified=True,
        attention_seconds=attention_seconds,
        attention_evidence_hash=DIGEST,
    )


def snapshot(conversation_id: str, *, sequences: tuple[int, ...]) -> PDDWorkspaceSnapshot:
    return PDDWorkspaceSnapshot(
        store_id="store-1",
        platform_store_id="328616090",
        conversation_id=conversation_id,
        customer_reference=customer_reference(conversation_id),
        page_fingerprint=FINGERPRINT,
        selector_evidence_hash=DIGEST,
        page_state="CUSTOMER_SERVICE_RUNNING",
        messages=tuple(
            PDDWorkspaceMessage(
                external_message_id=f"{conversation_id}-message-{sequence}",
                sender="CUSTOMER",
                content=f"{conversation_id}-content-{sequence}",
                timestamp=NOW + timedelta(seconds=sequence),
                sequence=sequence,
            )
            for sequence in sequences
        ),
        captured_at=NOW,
    )


class NavigableDriver:
    source_kind = "LIVE_PDD"
    navigation_enabled = True

    def __init__(self, summaries, snapshots) -> None:
        self.summaries = tuple(summaries)
        self.snapshots = dict(snapshots)
        self.active: str | None = None
        self.navigated: list[str] = []
        self.allow_attention_missing: list[bool] = []

    def selector_evidence(self, capability: str) -> PDDSelectorRuntimeEvidence:
        assert capability == "OBSERVE"
        return PDDSelectorRuntimeEvidence(
            evidence_hash=DIGEST,
            selector_contract_version="pdd-navigation-test",
            page_fingerprint=FINGERPRINT,
            capability="OBSERVE",
            verified_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )

    def scan_conversations(self):
        return self.summaries

    def capture_conversation(self, item):
        if self.active != item.conversation_id:
            raise PDDConversationNotActive("not active")
        return self.snapshots[item.conversation_id]

    def navigate_to_conversation(self, item, *, allow_attention_missing=False):
        self.active = item.conversation_id
        self.navigated.append(item.conversation_id)
        self.allow_attention_missing.append(allow_attention_missing)


class UnstableNavigableDriver(NavigableDriver):
    def capture_conversation(self, item):
        raise PDDConversationNotActive("target did not stabilize")


class MessageArrivesDuringAckDriver(NavigableDriver):
    def __init__(self, summaries, snapshots) -> None:
        super().__init__(summaries, snapshots)
        self.active_capture_count = 0

    def capture_conversation(self, item):
        if self.active != item.conversation_id:
            raise PDDConversationNotActive("not active")
        self.active_capture_count += 1
        if self.active_capture_count == 1:
            return snapshot(item.conversation_id, sequences=(1,))
        return snapshot(item.conversation_id, sequences=(1, 2))


def build_observer(tmp_path, driver):
    spool = DurableEdgeSpool(
        tmp_path / "spool.sqlite3", PlainProtector(), clock=lambda: NOW
    )
    capture_store = DurablePDDConversationCaptureStore(
        tmp_path / "spool.sqlite3", clock=lambda: NOW
    )
    forwarded = []

    def forward(observation):
        spool.persist(observation)
        spool.acknowledge(
            observation_id=observation.observation_id,
            payload_digest=observation.payload_digest,
            cursor=observation.source_cursor,
        )
        forwarded.append(observation)

    observer = PDDMessageObserver(
        driver=driver,
        mapper=PDDWorkspaceObservationMapper(agent_id="agent-1", device_id="device-1"),
        spool=spool,
        capture_store=capture_store,
        forward=forward,
        clock=lambda: NOW,
    )
    return observer, spool, capture_store, forwarded


def test_three_buyers_are_serially_navigated_and_durably_isolated(tmp_path) -> None:
    summaries = [
        summary("conversation-a", sequence=1, position=2, attention_seconds=9),
        summary("conversation-b", sequence=1, position=0, attention_seconds=3),
        summary("conversation-c", sequence=1, position=1, attention_seconds=6),
    ]
    driver = NavigableDriver(
        summaries,
        {
            item.conversation_id: snapshot(item.conversation_id, sequences=(1,))
            for item in summaries
        },
    )
    observer, spool, capture_store, forwarded = build_observer(tmp_path, driver)

    result = observer.scan_once()

    assert result.observations_forwarded == 3
    assert driver.navigated == [
        "conversation-b",
        "conversation-c",
        "conversation-a",
    ]
    assert {item.conversation_id for item in forwarded} == {
        "conversation-a",
        "conversation-b",
        "conversation-c",
    }
    for item in summaries:
        assert spool.conversation_cursor(
            item.store_id, item.platform_store_id, item.conversation_id
        )[1] == 1
        record = capture_store.get(
            item.store_id, item.platform_store_id, item.conversation_id
        )
        assert record is not None
        assert record.state is PDDConversationCaptureState.COMPLETED
        assert record.captured_message_high_watermark == 1
        assert record.latest_message_id == item.latest_message_id


def test_completed_red_row_does_not_reopen_without_a_new_row_watermark(tmp_path) -> None:
    item = summary("conversation-a", sequence=1, position=0)
    driver = NavigableDriver(
        [item], {item.conversation_id: snapshot(item.conversation_id, sequences=(1,))}
    )
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)

    observer.scan_once()
    observer.scan_once()

    assert [observation.external_message_id for observation in forwarded] == [
        "conversation-a-message-1"
    ]
    assert driver.navigated == ["conversation-a"]
    record = capture_store.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.COMPLETED
    assert record.latest_message_id == item.latest_message_id


def test_interrupted_navigation_is_recovered_on_the_next_scan_without_restart(
    tmp_path,
) -> None:
    item = summary("conversation-a", sequence=1, position=0)
    driver = NavigableDriver(
        [item], {item.conversation_id: snapshot(item.conversation_id, sequences=(1,))}
    )
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)
    capture_store.observe_attention(
        store_id=item.store_id,
        platform_store_id=item.platform_store_id,
        conversation_id=item.conversation_id,
        attention_state=item.attention_state,
        attention_verified=True,
        attention_seconds=item.attention_seconds,
        attention_evidence_hash=item.attention_evidence_hash,
        page_position=item.page_position,
        latest_sequence=item.latest_sequence,
        latest_message_id=item.latest_message_id,
    )
    assert capture_store.claim(
        item.store_id, item.platform_store_id, item.conversation_id
    )

    result = observer.scan_once()

    assert result.observations_forwarded == 1
    assert driver.navigated == ["conversation-a"]
    assert len(forwarded) == 1
    record = capture_store.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.COMPLETED
    assert record.attempts == 2
    assert record.latest_message_id == item.latest_message_id


def test_same_buyer_new_message_reopens_without_replaying_old_observation(tmp_path) -> None:
    first = summary("conversation-a", sequence=1, position=0)
    driver = NavigableDriver(
        [first], {first.conversation_id: snapshot(first.conversation_id, sequences=(1,))}
    )
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)
    observer.scan_once()

    second = summary("conversation-a", sequence=2, position=0)
    driver.summaries = (second,)
    driver.snapshots[second.conversation_id] = snapshot(
        second.conversation_id, sequences=(1, 2)
    )
    observer.scan_once()

    assert [item.external_message_id for item in forwarded] == [
        "conversation-a-message-1",
        "conversation-a-message-2",
    ]
    record = capture_store.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.COMPLETED
    assert record.captured_message_high_watermark == 2


def test_preview_change_navigates_exact_row_when_pdd_attention_marker_is_missing(
    tmp_path,
) -> None:
    first = summary(
        "conversation-a",
        sequence=1,
        position=0,
        attention=PDDReplyAttentionState.NONE,
        attention_seconds=None,
    )
    second = summary(
        "conversation-a",
        sequence=2,
        position=0,
        attention=PDDReplyAttentionState.NONE,
        attention_seconds=None,
    )
    driver = NavigableDriver(
        [second],
        {
            second.conversation_id: PDDWorkspaceSnapshot(
                store_id="store-1",
                platform_store_id="328616090",
                conversation_id=second.conversation_id,
                customer_reference=customer_reference(second.conversation_id),
                page_fingerprint=FINGERPRINT,
                selector_evidence_hash=DIGEST,
                page_state="CUSTOMER_SERVICE_RUNNING",
                messages=(
                    PDDWorkspaceMessage(
                        external_message_id="conversation-a-message-1",
                        sender="CUSTOMER",
                        content="historical-content",
                        timestamp=NOW - timedelta(minutes=1),
                        sequence=1,
                    ),
                    PDDWorkspaceMessage(
                        external_message_id="conversation-a-message-2",
                        sender="CUSTOMER",
                        content="new-content",
                        timestamp=NOW + timedelta(seconds=2),
                        sequence=2,
                    ),
                ),
                captured_at=NOW + timedelta(seconds=2),
            )
        },
    )
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)
    capture_store.observe_attention(
        store_id=first.store_id,
        platform_store_id=first.platform_store_id,
        conversation_id=first.conversation_id,
        attention_state=first.attention_state,
        attention_verified=False,
        attention_seconds=None,
        attention_evidence_hash=None,
        page_position=first.page_position,
        latest_sequence=None,
        latest_message_id=first.latest_message_id,
    )

    result = observer.scan_once()

    assert result.observations_forwarded == 1
    assert driver.navigated == ["conversation-a"]
    assert driver.allow_attention_missing == [True]
    assert [item.external_message_id for item in forwarded] == [
        "conversation-a-message-2",
    ]


def test_unstable_target_returns_durable_task_to_pending(tmp_path) -> None:
    item = summary("conversation-a", sequence=1, position=0)
    driver = UnstableNavigableDriver(
        [item], {item.conversation_id: snapshot(item.conversation_id, sequences=(1,))}
    )
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)

    result = observer.scan_once()

    assert result.observations_forwarded == 0
    assert forwarded == []
    record = capture_store.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.PENDING
    assert record.last_error_code == "PDD_NAVIGATION_TARGET_NOT_STABLE"


def test_ack_completion_rechecks_same_conversation_for_second_arrival(tmp_path) -> None:
    item = summary("conversation-a", sequence=1, position=0)
    driver = MessageArrivesDuringAckDriver([item], {})
    observer, _, capture_store, forwarded = build_observer(tmp_path, driver)

    result = observer.scan_once()

    assert result.observations_forwarded == 2
    assert [observation.external_message_id for observation in forwarded] == [
        "conversation-a-message-1",
        "conversation-a-message-2",
    ]
    record = capture_store.get("store-1", "328616090", "conversation-a")
    assert record is not None
    assert record.state is PDDConversationCaptureState.COMPLETED
    assert record.captured_message_high_watermark == 2


class Resolver:
    def resolve(self, profile_path):
        del profile_path
        return PDDCDPPageTarget(
            target_id="target-1",
            websocket_url="ws://127.0.0.1:9222/devtools/page/target-1",
            page_url="https://mms.pinduoduo.com/chat-merchant/index.html#/",
            page_origin="https://mms.pinduoduo.com",
            page_path="/chat-merchant/index.html",
        )


class Evaluator:
    def __init__(self, trigger_result=None) -> None:
        self.trigger_result = trigger_result or {
            "triggered": True,
            "error_code": None,
            "x": 120.0,
            "y": 240.0,
        }
        self.expressions: list[str] = []
        self.clicks: list[tuple[float, float]] = []

    def evaluate(self, target, expression):
        del target
        self.expressions.append(expression)
        if "scrollIntoView" in expression:
            return self.trigger_result
        return "1234567890"

    def dispatch_mouse_click(self, target, *, x, y):
        del target
        self.clicks.append((x, y))


SELECTORS = {
    name: {"selector": f"[data-pdd='{name}']", "attribute": None}
    for name in (
        "conversation_item",
        "conversation_id",
        "conversation_attention",
        "conversation_select_target",
        "active_conversation_id",
        "reply_input",
        "message_container",
    )
}


def navigation_port(evaluator) -> WebSocketPDDConversationNavigationPort:
    return WebSocketPDDConversationNavigationPort(
        profile_path="C:/safe-profile",
        applicable_path="/chat-merchant/index.html",
        selectors=SELECTORS,
        resolver=Resolver(),
        evaluator=evaluator,
        timeout_seconds=0.25,
    )


def test_navigation_port_is_single_purpose_and_checks_human_input() -> None:
    evaluator = Evaluator()
    navigation_port(evaluator).navigate(
        summary("1234567890", sequence=1, position=0)
    )

    expression = evaluator.expressions[0]
    assert "scrollIntoView" in expression
    assert "targets[0].click()" not in expression
    assert "inputText.length > 0" in expression
    assert "input.isComposing === true" in expression
    assert "document.activeElement === input" not in expression
    assert ".value =" not in expression
    assert "dispatchEvent" not in expression
    assert evaluator.clicks == [(120.0, 240.0)]

    # The selector is always resolved from the already identity-verified row.
    # This keeps the real ``.chat-detail`` click target row-local and prevents
    # a same-class child in another buyer conversation from being clicked.
    assert "const targets = nodes(row, 'conversation_select_target')" in expression

    active_expression = evaluator.expressions[1]
    assert "active.length === 0" in active_expression
    assert "active.length > maximum" in active_expression
    assert "new Set(normalized)" in active_expression
    assert "unique.length === 1" in active_expression


def test_navigation_port_fails_closed_when_human_input_is_active() -> None:
    evaluator = Evaluator(
        {"triggered": False, "error_code": "PDD_NAVIGATION_HUMAN_INPUT_ACTIVE"}
    )
    with pytest.raises(PDDConversationNavigationError) as raised:
        navigation_port(evaluator).navigate(
            summary("1234567890", sequence=1, position=0)
        )
    assert raised.value.error_code == "PDD_NAVIGATION_HUMAN_INPUT_ACTIVE"
    assert raised.value.manual_review is False
    assert evaluator.clicks == []


def test_human_input_pause_keeps_capture_pending_for_automatic_resume(tmp_path) -> None:
    capture_store = DurablePDDConversationCaptureStore(tmp_path / "spool.sqlite3")
    item = summary("conversation-a", sequence=1, position=0)
    capture_store.observe_attention(
        store_id=item.store_id,
        platform_store_id=item.platform_store_id,
        conversation_id=item.conversation_id,
        attention_state=item.attention_state,
        attention_verified=True,
        attention_seconds=item.attention_seconds,
        attention_evidence_hash=item.attention_evidence_hash,
        page_position=item.page_position,
        latest_sequence=item.latest_sequence,
        latest_message_id=item.latest_message_id,
    )
    assert capture_store.claim(
        item.store_id, item.platform_store_id, item.conversation_id
    )

    capture_store.mark_failure(
        store_id=item.store_id,
        platform_store_id=item.platform_store_id,
        conversation_id=item.conversation_id,
        error_code="PDD_NAVIGATION_HUMAN_INPUT_ACTIVE",
        manual_review=False,
    )

    record = capture_store.get(
        item.store_id, item.platform_store_id, item.conversation_id
    )
    assert record is not None
    assert record.state is PDDConversationCaptureState.PENDING
