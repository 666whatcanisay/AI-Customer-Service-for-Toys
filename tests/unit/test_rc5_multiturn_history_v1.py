from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from channel_engine.customer_assistant import (
    AuthorizationKind,
    ConversationHistoryCandidate,
    ConversationHistoryEntry,
    HistorySource,
    VISIBLE_HISTORY_LIMIT,
    merge_visible_history,
)


NOW = datetime(2026, 8, 12, 2, 0, tzinfo=UTC)


def _candidate(
    index: int,
    *,
    source: HistorySource,
    sender: str = "customer",
    store_id: str = "store-a",
    conversation_id: str = "conversation-a",
    logical_key: str | None = None,
    content: str | None = None,
) -> ConversationHistoryCandidate:
    text = content or f"history-{index}"
    decision_id = f"decision-{index}" if sender == "operator" else None
    return ConversationHistoryCandidate(
        entry=ConversationHistoryEntry(
            store_id=store_id,
            conversation_id=conversation_id,
            external_message_id=f"message-{index}-{source.value.lower()}",
            sender=sender,  # type: ignore[arg-type]
            content=text,
            timestamp=NOW + timedelta(seconds=index),
            content_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        ),
        source=source,
        logical_key=logical_key or f"message:{index}",
        decision_id=decision_id,
    )


def test_empty_first_turn_has_no_visible_history() -> None:
    merged = merge_visible_history(
        (), store_id="store-a", conversation_id="conversation-a"
    )

    assert merged.entries == ()
    assert merged.audit["raw_history_count"] == 0
    assert merged.audit["passed_history_count"] == 0
    assert merged.audit["first_message_id"] is None


def test_human_wins_same_turn_auto_policy_conflict() -> None:
    automatic = _candidate(
        1,
        source=HistorySource.AUTO_POLICY,
        sender="operator",
        logical_key="decision:shared",
        content="自动策略候选",
    )
    human = _candidate(
        2,
        source=HistorySource.HUMAN,
        sender="operator",
        logical_key="decision:shared",
        content="人工确认候选",
    )

    merged = merge_visible_history(
        (automatic, human), store_id="store-a", conversation_id="conversation-a"
    )

    assert [item.content for item in merged.entries] == ["人工确认候选"]
    assert [item["source"] for item in merged.audit["entries"]] == ["HUMAN"]


def test_real_pdd_source_has_highest_priority_and_no_synthetic_fallback() -> None:
    synthetic = _candidate(
        1,
        source=HistorySource.SYNTHETIC,
        logical_key="message:shared",
        content="synthetic fallback",
    )
    real = _candidate(
        2,
        source=HistorySource.REAL_PDD,
        logical_key="message:shared",
        content="real page fact",
    )

    merged = merge_visible_history(
        (synthetic, real),
        store_id="store-a",
        conversation_id="conversation-a",
        real_operator_history_missing=True,
    )

    assert [item.content for item in merged.entries] == ["real page fact"]
    assert merged.audit["real_operator_history_missing"] is True
    assert merged.audit["entries"][0]["source"] == "REAL_PDD"


def test_recent_twenty_are_ordered_and_oldest_are_truncated() -> None:
    candidates = tuple(
        reversed(
            [
                _candidate(index, source=HistorySource.SYNTHETIC)
                for index in range(1, 26)
            ]
        )
    )

    merged = merge_visible_history(
        candidates,
        store_id="store-a",
        conversation_id="conversation-a",
        limit=VISIBLE_HISTORY_LIMIT,
    )

    assert len(merged.entries) == 20
    assert [item.content for item in merged.entries] == [
        f"history-{index}" for index in range(6, 26)
    ]
    assert merged.audit["raw_history_count"] == 25
    assert merged.audit["truncated_history_count"] == 5
    assert merged.audit["truncation_boundary_message_id"] == (
        "message-5-synthetic"
    )


def test_duplicate_visible_fact_is_not_repeated() -> None:
    first = _candidate(1, source=HistorySource.SYNTHETIC, content="same")
    duplicate = ConversationHistoryCandidate(
        entry=first.entry.model_copy(update={"external_message_id": "duplicate-id"}),
        source=HistorySource.SYNTHETIC,
        logical_key="message:duplicate",
    )

    merged = merge_visible_history(
        (first, duplicate), store_id="store-a", conversation_id="conversation-a"
    )

    assert len(merged.entries) == 1
    assert merged.audit["deduplicated_history_count"] == 1


@pytest.mark.parametrize(
    ("store_id", "conversation_id"),
    (("store-b", "conversation-a"), ("store-a", "conversation-b")),
)
def test_history_cannot_cross_store_or_conversation(
    store_id: str, conversation_id: str
) -> None:
    contaminated = _candidate(
        1,
        source=HistorySource.SYNTHETIC,
        store_id=store_id,
        conversation_id=conversation_id,
    )

    with pytest.raises(ValueError, match="scope"):
        merge_visible_history(
            (contaminated,),
            store_id="store-a",
            conversation_id="conversation-a",
        )


def test_authorization_source_enum_matches_execution_authority() -> None:
    assert AuthorizationKind.HUMAN.value == HistorySource.HUMAN.value
    assert AuthorizationKind.AUTO_POLICY.value == HistorySource.AUTO_POLICY.value
