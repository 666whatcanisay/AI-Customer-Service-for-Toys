from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.retention import TransientBusinessDataPolicy


def test_client_business_cache_is_temporary_but_cursor_state_is_preserved(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime" / "real-pdd-assistant"
    root.mkdir(parents=True)
    feed = root / "assistant-feed.json"
    buffer = root / "conversation-buffer.sqlite3"
    checkpoint = root / "workspace-checkpoint.sqlite3"
    feed.write_text('{"customer":"redacted"}', encoding="utf-8")
    buffer.write_bytes(b"temporary-redacted-chat")
    checkpoint.write_bytes(b"message-ids-and-digests-only")
    stale = datetime(2026, 8, 7, 10, 0, tzinfo=UTC).timestamp()
    os.utime(feed, (stale, stale))
    os.utime(buffer, (stale, stale))

    removed = TransientBusinessDataPolicy(
        maximum_age=timedelta(minutes=30),
        clock=lambda: datetime(2026, 8, 7, 11, 0, tzinfo=UTC),
    ).purge_expired(tmp_path)

    assert set(removed) == {"assistant-feed.json", "conversation-buffer.sqlite3"}
    assert not feed.exists()
    assert not buffer.exists()
    assert checkpoint.is_file()


def test_safe_stop_removes_only_exact_business_cache_allowlist(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "real-pdd-assistant"
    root.mkdir(parents=True)
    (root / "assistant-feed.json").write_text("{}", encoding="utf-8")
    (root / "conversation-buffer.sqlite3").write_bytes(b"buffer")
    (root / "receipts.sqlite3").write_bytes(b"immutable-receipt")
    (root / "status.json").write_text("{}", encoding="utf-8")

    TransientBusinessDataPolicy().purge_on_safe_stop(tmp_path)

    assert not (root / "assistant-feed.json").exists()
    assert not (root / "conversation-buffer.sqlite3").exists()
    assert (root / "receipts.sqlite3").is_file()
    assert (root / "status.json").is_file()
