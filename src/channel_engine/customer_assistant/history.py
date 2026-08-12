from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from .models import ConversationHistoryEntry


VISIBLE_HISTORY_LIMIT = 20


class HistorySource(StrEnum):
    REAL_PDD = "REAL_PDD"
    HUMAN = "HUMAN"
    AUTO_POLICY = "AUTO_POLICY"
    SYNTHETIC = "SYNTHETIC"


_SOURCE_PRIORITY = {
    HistorySource.REAL_PDD: 4,
    HistorySource.HUMAN: 3,
    HistorySource.AUTO_POLICY: 2,
    HistorySource.SYNTHETIC: 1,
}


@dataclass(frozen=True, slots=True)
class ConversationHistoryCandidate:
    entry: ConversationHistoryEntry
    source: HistorySource
    logical_key: str
    decision_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationHistoryMerge:
    entries: tuple[ConversationHistoryEntry, ...]
    audit: dict[str, object]


def merge_visible_history(
    candidates: tuple[ConversationHistoryCandidate, ...],
    *,
    store_id: str,
    conversation_id: str,
    limit: int = VISIBLE_HISTORY_LIMIT,
    real_operator_history_missing: bool = False,
) -> ConversationHistoryMerge:
    """Merge already-filtered history with explicit source precedence.

    This is deliberately an internal projection.  Gateway Contract V1 still
    receives the existing ``ConversationHistoryEntry`` shape only.
    """

    if not 1 <= limit <= VISIBLE_HISTORY_LIMIT:
        raise ValueError("visible conversation history limit must be between 1 and 20")
    for candidate in candidates:
        if (
            candidate.entry.store_id != store_id
            or candidate.entry.conversation_id != conversation_id
        ):
            raise ValueError("visible conversation history crossed its scope")

    by_logical_key: dict[str, ConversationHistoryCandidate] = {}
    for candidate in candidates:
        existing = by_logical_key.get(candidate.logical_key)
        if existing is None or _SOURCE_PRIORITY[candidate.source] > _SOURCE_PRIORITY[
            existing.source
        ]:
            by_logical_key[candidate.logical_key] = candidate

    ordered = sorted(
        by_logical_key.values(),
        key=lambda item: (
            item.entry.timestamp,
            item.entry.external_message_id,
            -_SOURCE_PRIORITY[item.source],
        ),
    )
    # A source can expose the same visible fact under two identifiers.  Content
    # hash plus timestamp prevents that duplicate without collapsing legitimate
    # repeated customer messages from different moments.
    unique: list[ConversationHistoryCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in ordered:
        identity = (
            candidate.entry.sender,
            candidate.entry.content_digest,
            candidate.entry.timestamp.isoformat(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(candidate)

    selected = unique[-limit:]
    scope_digest = hashlib.sha256(
        f"{store_id}\0{conversation_id}".encode("utf-8")
    ).hexdigest()
    audit_entries = [
        {
            "sender": item.entry.sender,
            "source": item.source.value,
            "message_id": item.entry.external_message_id,
            "decision_id": item.decision_id,
            "content_sha256": item.entry.content_digest,
            "timestamp": item.entry.timestamp.isoformat(),
            "privacy_filtered": item.entry.privacy_filtered,
            "scope_sha256": scope_digest,
        }
        for item in selected
    ]
    return ConversationHistoryMerge(
        entries=tuple(item.entry for item in selected),
        audit={
            "raw_history_count": len(candidates),
            "deduplicated_history_count": len(unique),
            "passed_history_count": len(selected),
            "truncated_history_count": max(0, len(unique) - len(selected)),
            "limit": limit,
            "truncation_boundary_message_id": (
                unique[-limit - 1].entry.external_message_id
                if len(unique) > limit
                else None
            ),
            "first_message_id": (
                selected[0].entry.external_message_id if selected else None
            ),
            "last_message_id": (
                selected[-1].entry.external_message_id if selected else None
            ),
            "scope_sha256": scope_digest,
            "real_operator_history_missing": real_operator_history_missing,
            "entries": audit_entries,
        },
    )


__all__ = [
    "ConversationHistoryCandidate",
    "ConversationHistoryMerge",
    "HistorySource",
    "VISIBLE_HISTORY_LIMIT",
    "merge_visible_history",
]
