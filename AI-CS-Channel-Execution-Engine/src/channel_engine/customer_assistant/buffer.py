from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

from .models import (
    AIReplyPackage,
    BufferedCustomerMessage,
    BufferedMessageDisposition,
    ConversationTurn,
    CustomerContext,
)


class ConversationBufferError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("conversation buffer timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class SQLiteConversationBuffer:
    """Durable, store-isolated message buffer with bounded recovery.

    Only privacy-filtered message text may enter this store.  A turn is claimed
    after a quiet window, so three short customer messages produce one AI request.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        quiet_window: timedelta = timedelta(seconds=4),
        processing_lease: timedelta = timedelta(minutes=2),
        maximum_turn_messages: int = 32,
        clock: Callable[[], datetime],
    ) -> None:
        if quiet_window <= timedelta(0):
            raise ValueError("conversation quiet window must be positive")
        if processing_lease <= timedelta(0):
            raise ValueError("conversation processing lease must be positive")
        if not 1 <= maximum_turn_messages <= 32:
            raise ValueError("maximum turn size must be between 1 and 32")
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._quiet_window = quiet_window
        self._processing_lease = processing_lease
        self._maximum_turn_messages = maximum_turn_messages
        self._clock = clock
        self._lock = RLock()
        self._initialize()

    def append(
        self, message: BufferedCustomerMessage
    ) -> BufferedMessageDisposition:
        if not message.privacy_filtered:
            raise ConversationBufferError(
                "unfiltered customer content cannot enter the buffer",
                error_code="CUSTOMER_MESSAGE_NOT_PRIVACY_FILTERED",
            )
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                """
                SELECT content_digest FROM assistant_buffer_messages
                WHERE store_id=? AND conversation_id=? AND external_message_id=?
                """,
                (
                    message.store_id,
                    message.conversation_id,
                    message.external_message_id,
                ),
            ).fetchone()
            if existing is not None:
                if existing[0] != message.content_digest:
                    raise ConversationBufferError(
                        "duplicate message id has different redacted content",
                        error_code="CUSTOMER_MESSAGE_IDEMPOTENCY_CONFLICT",
                    )
                return BufferedMessageDisposition.DUPLICATE
            connection.execute(
                """
                INSERT INTO assistant_buffer_messages (
                    store_id, conversation_id, external_message_id,
                    customer_reference, content, content_digest,
                    message_timestamp, received_at, state, turn_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL)
                """,
                (
                    message.store_id,
                    message.conversation_id,
                    message.external_message_id,
                    message.customer_reference,
                    message.content,
                    message.content_digest,
                    _utc(message.timestamp).isoformat(),
                    _utc(message.received_at).isoformat(),
                ),
            )
            return BufferedMessageDisposition.ACCEPTED

    def claim_ready(self, *, now: datetime | None = None) -> ConversationTurn | None:
        current = _utc(now or self._clock())
        cutoff = current - self._quiet_window
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_stale(connection, current)
            scope = connection.execute(
                """
                SELECT store_id, conversation_id, MAX(message_timestamp) AS latest
                FROM assistant_buffer_messages
                WHERE state='PENDING'
                GROUP BY store_id, conversation_id
                HAVING latest <= ?
                ORDER BY latest ASC, store_id ASC, conversation_id ASC
                LIMIT 1
                """,
                (cutoff.isoformat(),),
            ).fetchone()
            if scope is None:
                connection.commit()
                return None
            rows = connection.execute(
                """
                SELECT store_id, conversation_id, external_message_id,
                       customer_reference, content, content_digest,
                       message_timestamp, received_at
                FROM assistant_buffer_messages
                WHERE store_id=? AND conversation_id=? AND state='PENDING'
                ORDER BY message_timestamp ASC, external_message_id ASC
                LIMIT ?
                """,
                (scope[0], scope[1], self._maximum_turn_messages),
            ).fetchall()
            messages = tuple(self._row_to_message(row) for row in rows)
            if not messages:
                connection.commit()
                return None
            identity = json.dumps(
                [
                    messages[0].store_id,
                    messages[0].conversation_id,
                    [item.external_message_id for item in messages],
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            turn_id = "assistant-turn:" + hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()
            connection.executemany(
                """
                UPDATE assistant_buffer_messages
                SET state='PROCESSING', turn_id=?
                WHERE store_id=? AND conversation_id=? AND external_message_id=?
                      AND state='PENDING'
                """,
                [
                    (
                        turn_id,
                        item.store_id,
                        item.conversation_id,
                        item.external_message_id,
                    )
                    for item in messages
                ],
            )
            connection.execute(
                """
                INSERT INTO assistant_buffer_turns (
                    turn_id, store_id, conversation_id, state,
                    claimed_at, updated_at, attempt_count
                ) VALUES (?, ?, ?, 'PROCESSING', ?, ?, 1)
                ON CONFLICT(turn_id) DO UPDATE SET
                    state='PROCESSING', claimed_at=excluded.claimed_at,
                    updated_at=excluded.updated_at,
                    attempt_count=assistant_buffer_turns.attempt_count + 1,
                    reason_code=NULL
                """,
                (
                    turn_id,
                    messages[0].store_id,
                    messages[0].conversation_id,
                    current.isoformat(),
                    current.isoformat(),
                ),
            )
            connection.commit()
            return ConversationTurn(
                turn_id=turn_id,
                store_id=messages[0].store_id,
                conversation_id=messages[0].conversation_id,
                customer_reference=messages[0].customer_reference,
                messages=messages,
                combined_question="\n".join(item.content for item in messages),
                opened_at=messages[0].timestamp,
                closed_at=messages[-1].timestamp,
            )

    def mark_waiting_approval(self, turn_id: str) -> None:
        self._transition(turn_id, "PROCESSING", "WAITING_APPROVAL")

    def save_reply(
        self,
        turn_id: str,
        context: CustomerContext,
        package: AIReplyPackage,
    ) -> None:
        if context.turn_id != turn_id or package.turn_id != turn_id:
            raise ConversationBufferError(
                "assistant reply does not belong to the claimed turn",
                error_code="ASSISTANT_REPLY_TURN_MISMATCH",
            )
        with self._lock, self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state='WAITING_APPROVAL', context_json=?, reply_package_json=?,
                    updated_at=?
                WHERE turn_id=? AND state='PROCESSING'
                """,
                (
                    context.model_dump_json(),
                    package.model_dump_json(),
                    _utc(self._clock()).isoformat(),
                    turn_id,
                ),
            ).rowcount
            if changed != 1:
                raise ConversationBufferError(
                    "assistant reply cannot be saved from the current state",
                    error_code="ASSISTANT_TURN_STATE_CONFLICT",
                )

    def load_reply(
        self, decision_id: str
    ) -> tuple[CustomerContext, AIReplyPackage] | None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT context_json, reply_package_json
                FROM assistant_buffer_turns
                WHERE reply_package_json IS NOT NULL
                """
            ).fetchall()
        for context_json, package_json in rows:
            package = AIReplyPackage.model_validate_json(package_json)
            if package.decision_id == decision_id:
                return CustomerContext.model_validate_json(context_json), package
        return None

    def stored_replies(
        self,
    ) -> tuple[tuple[CustomerContext, AIReplyPackage], ...]:
        """Return durable AI facts used to rebuild downstream projections."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT context_json,reply_package_json
                FROM assistant_buffer_turns
                WHERE context_json IS NOT NULL AND reply_package_json IS NOT NULL
                ORDER BY updated_at,turn_id
                """
            ).fetchall()
        return tuple(
            (
                CustomerContext.model_validate_json(context_json),
                AIReplyPackage.model_validate_json(package_json),
            )
            for context_json, package_json in rows
        )

    def complete(self, turn_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                "SELECT state FROM assistant_buffer_turns WHERE turn_id=?",
                (turn_id,),
            ).fetchone()
            if state is not None and state[0] == "COMPLETED":
                connection.commit()
                return
            changed = connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state='COMPLETED', updated_at=?
                WHERE turn_id=? AND state='WAITING_APPROVAL'
                """,
                (_utc(self._clock()).isoformat(), turn_id),
            ).rowcount
            if changed != 1:
                connection.rollback()
                raise ConversationBufferError(
                    "turn is not waiting for approval",
                    error_code="ASSISTANT_TURN_STATE_CONFLICT",
                )
            connection.execute(
                """
                UPDATE assistant_buffer_messages SET state='COMPLETED'
                WHERE turn_id=? AND state='PROCESSING'
                """,
                (turn_id,),
            )
            connection.commit()

    def mark_manual_intervention(self, turn_id: str, *, reason_code: str) -> None:
        if not reason_code.strip():
            raise ValueError("manual intervention reason is required")
        with self._lock, self._connect() as connection:
            state = connection.execute(
                "SELECT state FROM assistant_buffer_turns WHERE turn_id=?",
                (turn_id,),
            ).fetchone()
            if state is not None and state[0] == "MANUAL_INTERVENTION":
                return
            changed = connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state='MANUAL_INTERVENTION', reason_code=?, updated_at=?
                WHERE turn_id=? AND state IN ('PROCESSING', 'WAITING_APPROVAL')
                """,
                (reason_code, _utc(self._clock()).isoformat(), turn_id),
            ).rowcount
            if changed != 1:
                raise ConversationBufferError(
                    "assistant turn cannot enter manual intervention",
                    error_code="ASSISTANT_TURN_STATE_CONFLICT",
                )

    def requeue_manual_intervention(
        self,
        turn_id: str,
        *,
        reason_code: str = "OPERATOR_CONFIRMED_CONTEXT_UPDATED",
    ) -> None:
        """Requeue a refused AI turn after an explicit verified context update.

        This never retries an Execution. It only returns the already-redacted
        inbound messages to the suggestion pipeline; Approval, Execution,
        Receipt, and platform send remain untouched.
        """

        if not reason_code.strip():
            raise ValueError("requeue reason is required")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM assistant_buffer_turns WHERE turn_id=?",
                (turn_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ConversationBufferError(
                    "assistant turn does not exist",
                    error_code="ASSISTANT_TURN_NOT_FOUND",
                )
            if row[0] != "MANUAL_INTERVENTION":
                connection.rollback()
                raise ConversationBufferError(
                    "only a manual-intervention turn may be explicitly requeued",
                    error_code="ASSISTANT_REQUEUE_STATE_CONFLICT",
                )
            connection.execute(
                """
                UPDATE assistant_buffer_messages
                SET state='PENDING', turn_id=NULL
                WHERE turn_id=? AND state='PROCESSING'
                """,
                (turn_id,),
            )
            connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state='RELEASED', reason_code=?, context_json=NULL,
                    reply_package_json=NULL, updated_at=?
                WHERE turn_id=? AND state='MANUAL_INTERVENTION'
                """,
                (reason_code, _utc(self._clock()).isoformat(), turn_id),
            )
            connection.commit()

    def release(self, turn_id: str, *, reason_code: str) -> None:
        if not reason_code.strip():
            raise ValueError("release reason is required")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT attempt_count FROM assistant_buffer_turns WHERE turn_id=?",
                (turn_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ConversationBufferError(
                    "assistant turn does not exist",
                    error_code="ASSISTANT_TURN_NOT_FOUND",
                )
            next_state = "MANUAL_INTERVENTION" if int(row[0]) >= 3 else "RELEASED"
            connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state=?, reason_code=?, updated_at=?
                WHERE turn_id=? AND state='PROCESSING'
                """,
                (next_state, reason_code, _utc(self._clock()).isoformat(), turn_id),
            )
            if next_state == "RELEASED":
                connection.execute(
                    """
                    UPDATE assistant_buffer_messages
                    SET state='PENDING', turn_id=NULL
                    WHERE turn_id=? AND state='PROCESSING'
                    """,
                    (turn_id,),
                )
            connection.commit()

    def pending_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM assistant_buffer_messages WHERE state='PENDING'"
                ).fetchone()[0]
            )

    def load_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[BufferedCustomerMessage, ...]:
        """Load already-redacted messages for context without changing state."""

        if not 1 <= limit <= 50:
            raise ValueError("assistant history limit must be between 1 and 50")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT store_id, conversation_id, external_message_id,
                       customer_reference, content, content_digest,
                       message_timestamp, received_at
                FROM assistant_buffer_messages
                WHERE store_id=? AND conversation_id=?
                ORDER BY message_timestamp DESC, external_message_id DESC
                LIMIT ?
                """,
                (store_id, conversation_id, limit),
            ).fetchall()
        return tuple(self._row_to_message(row) for row in reversed(rows))

    def purge_expired(
        self, *, retention: timedelta = timedelta(hours=24)
    ) -> dict[str, int]:
        """Delete expired terminal content while preserving all recoverable work."""

        if retention <= timedelta(0) or retention > timedelta(days=30):
            raise ValueError("assistant buffer retention is outside policy")
        cutoff = _utc(self._clock()) - retention
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            terminal = connection.execute(
                """
                SELECT turn_id FROM assistant_buffer_turns
                WHERE updated_at<=?
                  AND state IN ('WAITING_APPROVAL', 'COMPLETED',
                                'MANUAL_INTERVENTION', 'RELEASED')
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            turn_ids = tuple(str(row[0]) for row in terminal)
            messages = 0
            turns = 0
            if turn_ids:
                placeholders = ",".join("?" for _item in turn_ids)
                messages = int(
                    connection.execute(
                        f"DELETE FROM assistant_buffer_messages WHERE turn_id IN ({placeholders})",
                        turn_ids,
                    ).rowcount
                    or 0
                )
                turns = int(
                    connection.execute(
                        f"DELETE FROM assistant_buffer_turns WHERE turn_id IN ({placeholders})",
                        turn_ids,
                    ).rowcount
                    or 0
                )
            connection.commit()
        return {"messages": messages, "turns": turns}

    def _transition(self, turn_id: str, before: str, after: str) -> None:
        with self._lock, self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE assistant_buffer_turns SET state=?, updated_at=?
                WHERE turn_id=? AND state=?
                """,
                (after, _utc(self._clock()).isoformat(), turn_id, before),
            ).rowcount
            if changed != 1:
                raise ConversationBufferError(
                    "assistant turn state transition failed",
                    error_code="ASSISTANT_TURN_STATE_CONFLICT",
                )

    def _recover_stale(self, connection: sqlite3.Connection, now: datetime) -> None:
        cutoff = now - self._processing_lease
        stale = connection.execute(
            """
            SELECT turn_id, attempt_count FROM assistant_buffer_turns
            WHERE state='PROCESSING' AND claimed_at <= ?
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        for turn_id, attempts in stale:
            next_attempt = int(attempts) + 1
            if next_attempt > 3:
                connection.execute(
                    """
                    UPDATE assistant_buffer_turns
                    SET state='MANUAL_INTERVENTION', reason_code='BUFFER_RETRY_EXHAUSTED',
                        attempt_count=?, updated_at=? WHERE turn_id=?
                    """,
                    (next_attempt, now.isoformat(), turn_id),
                )
                continue
            connection.execute(
                """
                UPDATE assistant_buffer_messages SET state='PENDING', turn_id=NULL
                WHERE turn_id=? AND state='PROCESSING'
                """,
                (turn_id,),
            )
            connection.execute(
                """
                UPDATE assistant_buffer_turns
                SET state='RELEASED', reason_code='BUFFER_PROCESSING_LEASE_EXPIRED',
                    attempt_count=?, updated_at=? WHERE turn_id=?
                """,
                (next_attempt, now.isoformat(), turn_id),
            )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> BufferedCustomerMessage:
        return BufferedCustomerMessage(
            store_id=row[0],
            conversation_id=row[1],
            external_message_id=row[2],
            customer_reference=row[3],
            content=row[4],
            content_digest=row[5],
            timestamp=datetime.fromisoformat(row[6]),
            received_at=datetime.fromisoformat(row[7]),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS assistant_buffer_messages (
                    store_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    external_message_id TEXT NOT NULL,
                    customer_reference TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_digest TEXT NOT NULL,
                    message_timestamp TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    turn_id TEXT,
                    PRIMARY KEY (store_id, conversation_id, external_message_id)
                );
                CREATE INDEX IF NOT EXISTS ix_assistant_buffer_pending
                    ON assistant_buffer_messages (state, message_timestamp);
                CREATE TABLE IF NOT EXISTS assistant_buffer_turns (
                    turn_id TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    reason_code TEXT,
                    context_json TEXT,
                    reply_package_json TEXT
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(assistant_buffer_turns)"
                ).fetchall()
            }
            for name in ("context_json", "reply_package_json"):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE assistant_buffer_turns ADD COLUMN {name} TEXT"
                    )


__all__ = ["ConversationBufferError", "SQLiteConversationBuffer"]
