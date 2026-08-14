from __future__ import annotations

import hashlib
from collections.abc import Sequence


def build_reply_turn_envelope(
    *,
    turn_id: str,
    messages: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Build the candidate AI-CS turn boundary without changing Gateway V1."""

    if not 1 <= len(messages) <= 32:
        raise ValueError("reply turn must contain between 1 and 32 messages")
    if len({message_id for message_id, _content in messages}) != len(messages):
        raise ValueError("reply turn message ids must be unique")

    rows: list[dict[str, object]] = []
    cursor = 0
    for message_id, content in messages:
        if not message_id or "\r" in message_id or "\n" in message_id:
            raise ValueError("reply turn message id must be a nonblank single line")
        if not content:
            raise ValueError("reply turn message content must be nonblank")
        end = cursor + len(content)
        rows.append(
            {
                "message_id": message_id,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "range_start": cursor,
                "range_end": end,
            }
        )
        cursor = end + 1

    aggregate = "\n".join(content for _message_id, content in messages)
    return {
        "schema_version": "ai-cs-reply-turn.v1",
        "turn_id": turn_id,
        "aggregate_content_sha256": hashlib.sha256(
            aggregate.encode("utf-8")
        ).hexdigest(),
        "index_unit": "UNICODE_CODE_POINT",
        "aggregation_separator": "\n",
        "messages": rows,
    }


__all__ = ["build_reply_turn_envelope"]
