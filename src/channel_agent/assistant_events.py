from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Condition, Event, Thread
from typing import Callable

from .client import ChannelEngineClient
from .control_v2 import AgentAssistantEvent, AgentAssistantSnapshot


class AssistantEventJournal:
    """Small local resume journal for Host event notifications.

    It stores workflow identifiers and status only. Customer message text, order
    data and AI reply content remain in AI-CS and are not copied here.
    """

    def __init__(self, path: str | Path, *, maximum_events: int = 1_000) -> None:
        self.path = Path(path)
        if maximum_events < 100 or maximum_events > 10_000:
            raise ValueError("assistant event journal limit is outside policy")
        self._maximum_events = maximum_events
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._changed = Condition()
        self._snapshot: AgentAssistantSnapshot | None = None
        self._snapshots: tuple[AgentAssistantSnapshot, ...] = ()
        self._initialize()

    def append(self, event: AgentAssistantEvent) -> None:
        payload = event.model_dump(mode="json")
        if payload.get("metadata", {}).get("contains_customer_content") is True:
            raise ValueError("customer content cannot enter the local event journal")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM assistant_events WHERE sequence_id=?",
                (event.sequence_id,),
            ).fetchone()
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if existing is not None:
                if existing[0] != serialized:
                    raise ValueError("assistant event cursor conflict")
                return
            connection.execute(
                "INSERT INTO assistant_events(sequence_id,event_id,payload_json) VALUES(?,?,?)",
                (event.sequence_id, event.event_id, serialized),
            )
            connection.execute(
                """
                DELETE FROM assistant_events
                WHERE sequence_id NOT IN (
                    SELECT sequence_id FROM assistant_events
                    ORDER BY sequence_id DESC LIMIT ?
                )
                """,
                (self._maximum_events,),
            )
        with self._changed:
            self._changed.notify_all()

    def read_after(self, sequence_id: int, *, limit: int = 100) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM assistant_events WHERE sequence_id>? ORDER BY sequence_id LIMIT ?",
                (max(sequence_id, 0), max(1, min(limit, 100))),
            ).fetchall()
        return tuple(json.loads(row[0]) for row in rows)

    def last_sequence_id(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COALESCE(MAX(sequence_id),0) FROM assistant_events").fetchone()
        return int(row[0])

    def wait_for_change(self, timeout: float) -> None:
        with self._changed:
            self._changed.wait(timeout=max(0.05, min(timeout, 30.0)))

    def update_snapshot(self, snapshot: AgentAssistantSnapshot | None) -> None:
        with self._changed:
            if snapshot == self._snapshot:
                return
            self._snapshot = snapshot
            self._snapshots = () if snapshot is None else (snapshot,)
            self._changed.notify_all()

    def update_snapshots(
        self, snapshots: tuple[AgentAssistantSnapshot, ...]
    ) -> None:
        with self._changed:
            if snapshots == self._snapshots:
                return
            self._snapshots = snapshots
            self._snapshot = snapshots[0] if snapshots else None
            self._changed.notify_all()

    def assistant_snapshot(self) -> AgentAssistantSnapshot | None:
        with self._changed:
            return self._snapshot

    def assistant_snapshots(self) -> tuple[AgentAssistantSnapshot, ...]:
        with self._changed:
            return self._snapshots

    def mark_conversation_read(self, conversation_id: str, revision: int) -> int:
        """Advance the metadata-only local read cursor for one conversation."""

        if not conversation_id.strip() or len(conversation_id) > 255:
            raise ValueError("assistant conversation id is invalid")
        if revision < 1:
            raise ValueError("assistant conversation revision is invalid")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assistant_read_cursors(conversation_id, revision)
                VALUES(?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    revision=MAX(assistant_read_cursors.revision, excluded.revision)
                """,
                (conversation_id, revision),
            )
            row = connection.execute(
                "SELECT revision FROM assistant_read_cursors WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        with self._changed:
            self._changed.notify_all()
        return int(row[0])

    def read_revision(self, conversation_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision FROM assistant_read_cursors WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        return 0 if row is None else int(row[0])

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_events(
                    sequence_id INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_read_cursors(
                    conversation_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK(revision >= 1)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection


class AssistantEventPoller:
    def __init__(
        self,
        client: ChannelEngineClient,
        journal: AssistantEventJournal,
        *,
        interval_seconds: float = 1.0,
        error_sink: Callable[[str], None] | None = None,
    ) -> None:
        self._client = client
        self._journal = journal
        self._interval = max(0.25, min(interval_seconds, 10.0))
        self._error_sink = error_sink or (lambda _code: None)
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="channel-agent-assistant-events", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, timeout))
        self._thread = None

    def poll_once(self) -> int:
        response = self._client.poll_assistant_events(
            after_sequence_id=self._journal.last_sequence_id(),
            limit=100,
        )
        for event in response.events:
            self._journal.append(event)
        fetch_conversations = getattr(
            self._client, "fetch_assistant_conversations", None
        )
        if callable(fetch_conversations):
            conversation_response = fetch_conversations(limit=100)
            self._journal.update_snapshots(conversation_response.conversations)
        else:
            fetch_snapshot = getattr(self._client, "fetch_assistant_snapshot", None)
            if callable(fetch_snapshot):
                snapshot_response = fetch_snapshot()
                self._journal.update_snapshot(snapshot_response.snapshot)
        return len(response.events)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                code = "ASSISTANT_EVENT_POLL_" + type(exc).__name__.upper()
                self._error_sink(code[:120])
            self._stop.wait(self._interval)


__all__ = ["AssistantEventJournal", "AssistantEventPoller"]
