from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from channel_agent.edge_spool import (
    DurableEdgeSpool,
    EdgeObservation,
    EdgeSpoolConflict,
    EdgeSpoolError,
)


class _TestProtector:
    """Deterministic reversible protector used only by this unit test."""

    _mask = b"test-only-edge-spool-mask"

    def protect(self, value: bytes) -> bytes:
        return bytes(byte ^ self._mask[index % len(self._mask)] for index, byte in enumerate(value))

    def unprotect(self, value: bytes) -> bytes:
        return self.protect(value)


def _observation(now: datetime, *, payload: dict[str, object] | None = None) -> EdgeObservation:
    return EdgeObservation(
        observation_id="observation-001",
        agent_id="agent-001",
        device_id="device-001",
        store_id="store-001",
        conversation_id="conversation-001",
        external_message_id="message-001",
        source_sequence=7,
        payload=payload or {"content": "short-lived customer text"},
        captured_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def test_persist_must_commit_before_ack_and_cursor_advance(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    spool = DurableEdgeSpool(tmp_path / "edge.db", _TestProtector(), clock=lambda: now)
    observation = _observation(now)

    with pytest.raises(EdgeSpoolError, match="not persisted"):
        spool.acknowledge(
            observation_id=observation.observation_id,
            payload_digest=observation.payload_digest,
            cursor="cursor-7",
        )
    assert spool.cursor(observation.store_id) is None

    assert spool.persist(observation) is True
    assert spool.cursor(observation.store_id) is None
    spool.acknowledge(
        observation_id=observation.observation_id,
        payload_digest=observation.payload_digest,
        cursor="cursor-7",
    )
    assert spool.cursor(observation.store_id) == "cursor-7"
    assert spool.pending() == ()


def test_restart_recovers_unacked_observation_without_advancing_cursor(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    database = tmp_path / "edge.db"
    first = DurableEdgeSpool(database, _TestProtector(), clock=lambda: now)
    observation = _observation(now)
    first.persist(observation)

    recovered = DurableEdgeSpool(database, _TestProtector(), clock=lambda: now)
    assert recovered.cursor(observation.store_id) is None
    assert recovered.pending() == (observation,)


def test_duplicate_delivery_is_idempotent_but_content_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    spool = DurableEdgeSpool(tmp_path / "edge.db", _TestProtector(), clock=lambda: now)
    observation = _observation(now)
    assert spool.persist(observation) is True
    assert spool.persist(observation) is False

    changed = _observation(now, payload={"content": "different content"})
    with pytest.raises(EdgeSpoolConflict, match="different content"):
        spool.persist(changed)


def test_short_lived_payload_is_not_stored_as_plaintext_and_expires(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    current = [now]
    database = tmp_path / "edge.db"
    spool = DurableEdgeSpool(database, _TestProtector(), clock=lambda: current[0])
    observation = _observation(now)
    spool.persist(observation)

    with sqlite3.connect(database) as connection:
        ciphertext = connection.execute(
            "SELECT payload_ciphertext FROM edge_observations"
        ).fetchone()[0]
    assert b"short-lived customer text" not in bytes(ciphertext)

    current[0] = now + timedelta(minutes=31)
    assert spool.pending() == ()
    assert spool.purge_expired() == 1


def test_retention_cannot_exceed_edge_policy(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
    spool = DurableEdgeSpool(tmp_path / "edge.db", _TestProtector(), clock=lambda: now)
    invalid = _observation(now).model_copy(
        update={"expires_at": now + timedelta(minutes=31)}
    )
    with pytest.raises(EdgeSpoolError, match="retention"):
        spool.persist(invalid)
