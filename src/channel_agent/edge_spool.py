from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .security import TransientPayloadProtector


class EdgeSpoolError(RuntimeError):
    pass


class EdgeSpoolConflict(EdgeSpoolError):
    pass


class EdgeObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    observation_id: str = Field(min_length=1, max_length=160)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    source_cursor: str | None = Field(default=None, min_length=1, max_length=512)
    source_sequence: int = Field(ge=0)
    payload: dict[str, object]
    captured_at: AwareDatetime
    expires_at: AwareDatetime

    @property
    def payload_digest(self) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(
                self.payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class DurableEdgeSpool:
    """Encrypted, short-lived persist-before-ACK queue for the edge runtime."""

    def __init__(
        self,
        path: str | Path,
        protector: TransientPayloadProtector,
        *,
        maximum_age: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if maximum_age <= timedelta(0) or maximum_age > timedelta(hours=2):
            raise ValueError("edge spool retention must be within two hours")
        self.path = Path(path)
        self._protector = protector
        self._maximum_age = maximum_age
        self._clock = clock
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def persist(self, observation: EdgeObservation) -> bool:
        now = self._clock().astimezone(UTC)
        if observation.expires_at > observation.captured_at + self._maximum_age:
            raise EdgeSpoolError("edge observation retention exceeds policy")
        if observation.expires_at <= now:
            raise EdgeSpoolError("edge observation already expired")
        raw_payload = json.dumps(
            observation.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = self._protector.protect(raw_payload)
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_digest FROM edge_observations WHERE observation_id = ?",
                (observation.observation_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != observation.payload_digest:
                    raise EdgeSpoolConflict(
                        "same observation id was delivered with different content"
                    )
                return False
            connection.execute(
                """
                INSERT INTO edge_observations (
                    observation_id, agent_id, device_id, store_id,
                    platform_store_id, conversation_id, external_message_id,
                    source_cursor, source_sequence,
                    payload_digest, payload_ciphertext, captured_at, expires_at, acked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    observation.observation_id,
                    observation.agent_id,
                    observation.device_id,
                    observation.store_id,
                    observation.platform_store_id,
                    observation.conversation_id,
                    observation.external_message_id,
                    observation.source_cursor,
                    observation.source_sequence,
                    observation.payload_digest,
                    encrypted,
                    observation.captured_at.isoformat(),
                    observation.expires_at.isoformat(),
                ),
            )
            connection.commit()
            return True

    def acknowledge(
        self,
        *,
        observation_id: str,
        payload_digest: str,
        cursor: str,
    ) -> None:
        """Advance the cursor only after the durable observation transaction exists."""

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT store_id, platform_store_id, conversation_id,
                       source_sequence, payload_digest
                FROM edge_observations WHERE observation_id = ?
                """,
                (observation_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise EdgeSpoolError("cannot ACK an observation that was not persisted")
            if row[4] != payload_digest:
                connection.rollback()
                raise EdgeSpoolConflict("ACK payload digest does not match persisted data")
            connection.execute(
                "UPDATE edge_observations SET acked_at = ? WHERE observation_id = ?",
                (self._clock().astimezone(UTC).isoformat(), observation_id),
            )
            connection.execute(
                """
                INSERT INTO edge_cursors (store_id, cursor, observation_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(store_id) DO UPDATE SET
                    cursor=excluded.cursor,
                    observation_id=excluded.observation_id,
                    updated_at=excluded.updated_at
                """,
                (
                    row[0],
                    cursor,
                    observation_id,
                    self._clock().astimezone(UTC).isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO edge_conversation_cursors (
                    store_id, platform_store_id, conversation_id, cursor,
                    source_sequence, observation_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(store_id, platform_store_id, conversation_id) DO UPDATE SET
                    cursor=excluded.cursor,
                    source_sequence=CASE
                        WHEN excluded.source_sequence >= edge_conversation_cursors.source_sequence
                        THEN excluded.source_sequence
                        ELSE edge_conversation_cursors.source_sequence
                    END,
                    observation_id=CASE
                        WHEN excluded.source_sequence >= edge_conversation_cursors.source_sequence
                        THEN excluded.observation_id
                        ELSE edge_conversation_cursors.observation_id
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    row[0],
                    row[1] or "",
                    row[2],
                    cursor,
                    int(row[3]),
                    observation_id,
                    self._clock().astimezone(UTC).isoformat(),
                ),
            )
            connection.commit()

    def pending(self) -> tuple[EdgeObservation, ...]:
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT observation_id, agent_id, device_id, store_id,
                       platform_store_id, conversation_id, external_message_id,
                       source_cursor, source_sequence,
                       payload_ciphertext, captured_at, expires_at
                FROM edge_observations
                WHERE acked_at IS NULL AND expires_at > ?
                ORDER BY source_sequence, captured_at, observation_id
                """,
                (now.isoformat(),),
            ).fetchall()
        values: list[EdgeObservation] = []
        for row in rows:
            payload = json.loads(self._protector.unprotect(row[9]).decode("utf-8"))
            values.append(
                EdgeObservation(
                    observation_id=row[0],
                    agent_id=row[1],
                    device_id=row[2],
                    store_id=row[3],
                    platform_store_id=row[4],
                    conversation_id=row[5],
                    external_message_id=row[6],
                    source_cursor=row[7],
                    source_sequence=row[8],
                    payload=payload,
                    captured_at=datetime.fromisoformat(row[10]),
                    expires_at=datetime.fromisoformat(row[11]),
                )
            )
        return tuple(values)

    def cursor(self, store_id: str) -> str | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT cursor FROM edge_cursors WHERE store_id = ?", (store_id,)
            ).fetchone()
            return None if row is None else str(row[0])

    def conversation_cursor(
        self,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
    ) -> tuple[str, int] | None:
        """Return the last Host-ACKed cursor for one isolated conversation."""

        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT cursor, source_sequence
                FROM edge_conversation_cursors
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                (store_id, platform_store_id or "", conversation_id),
            ).fetchone()
            return None if row is None else (str(row[0]), int(row[1]))

    def establish_high_water(
        self,
        *,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        cursor: str,
        source_sequence: int,
    ) -> None:
        """Record a history baseline without pretending that Host ACKed a message."""

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO edge_conversation_cursors (
                    store_id, platform_store_id, conversation_id, cursor,
                    source_sequence, observation_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(store_id, platform_store_id, conversation_id) DO NOTHING
                """,
                (
                    store_id,
                    platform_store_id or "",
                    conversation_id,
                    cursor,
                    source_sequence,
                    self._clock().astimezone(UTC).isoformat(),
                ),
            )
            connection.commit()

    def purge_expired(self) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM edge_observations WHERE expires_at <= ?",
                (self._clock().astimezone(UTC).isoformat(),),
            )
            connection.commit()
            return int(cursor.rowcount)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS edge_observations (
                    observation_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    platform_store_id TEXT,
                    conversation_id TEXT NOT NULL,
                    external_message_id TEXT NOT NULL,
                    source_cursor TEXT,
                    source_sequence INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload_ciphertext BLOB NOT NULL,
                    captured_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    acked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS edge_cursors (
                    store_id TEXT PRIMARY KEY,
                    cursor TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(observation_id) REFERENCES edge_observations(observation_id)
                );
                CREATE TABLE IF NOT EXISTS edge_conversation_cursors (
                    store_id TEXT NOT NULL,
                    platform_store_id TEXT NOT NULL DEFAULT '',
                    conversation_id TEXT NOT NULL,
                    cursor TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL,
                    observation_id TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(store_id, platform_store_id, conversation_id)
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(edge_observations)")
            }
            if "source_cursor" not in columns:
                connection.execute(
                    "ALTER TABLE edge_observations ADD COLUMN source_cursor TEXT"
                )
            if "platform_store_id" not in columns:
                connection.execute(
                    "ALTER TABLE edge_observations ADD COLUMN platform_store_id TEXT"
                )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = [
    "DurableEdgeSpool",
    "EdgeObservation",
    "EdgeSpoolConflict",
    "EdgeSpoolError",
]
