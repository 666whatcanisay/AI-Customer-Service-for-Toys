from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class PDDReplyAttentionState(StrEnum):
    NONE = "NONE"
    COUNTDOWN = "COUNTDOWN"
    OVERDUE = "OVERDUE"
    UNKNOWN = "UNKNOWN"


class PDDConversationCaptureState(StrEnum):
    PENDING = "PENDING"
    NAVIGATING = "NAVIGATING"
    CAPTURED_WAITING_ACK = "CAPTURED_WAITING_ACK"
    COMPLETED = "COMPLETED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PDDConversationCaptureRecord(BaseModel):
    """Durable Adapter scheduling state; it is not an ACK/Cursor replacement."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    state: PDDConversationCaptureState
    attention_state: PDDReplyAttentionState
    attention_present: bool
    attention_seconds: int | None = Field(default=None, ge=0, le=604_800)
    attention_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    page_position: int | None = Field(default=None, ge=0, le=10_000)
    captured_message_high_watermark: int = Field(default=0, ge=0)
    latest_message_id: str | None = Field(default=None, min_length=1, max_length=255)
    first_observed_at: AwareDatetime
    last_observed_at: AwareDatetime
    attempts: int = Field(default=0, ge=0)
    last_error_code: str | None = Field(default=None, min_length=1, max_length=160)


class DurablePDDConversationCaptureStore:
    """Persistent single-browser scheduling records stored beside the Edge spool.

    This table only decides which visible PDD conversation should be captured.
    Durable observations and Host acknowledgement continue to use the existing
    ``DurableEdgeSpool`` tables and cursor semantics unchanged.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = RLock()
        self._initialize()

    def recover_interrupted(self) -> int:
        """A click may have consumed the red marker; retain and retry the task."""

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?, last_error_code = ?
                WHERE state = ?
                """,
                (
                    PDDConversationCaptureState.PENDING.value,
                    "RECOVERED_AFTER_NAVIGATION_INTERRUPTION",
                    PDDConversationCaptureState.NAVIGATING.value,
                ),
            )
            connection.commit()
            return int(cursor.rowcount)

    def observe_attention(
        self,
        *,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        attention_state: PDDReplyAttentionState,
        attention_verified: bool,
        attention_seconds: int | None,
        attention_evidence_hash: str | None,
        page_position: int | None,
        latest_sequence: int | None,
        latest_message_id: str | None,
    ) -> PDDConversationCaptureRecord | None:
        """Observe one visible row and reopen a completed conversation safely.

        A continuously decreasing countdown does not create a new task every scan.
        Re-entry occurs only when the marker reappears after being absent, the
        row exposes a changed message watermark, or the countdown visibly resets
        for a later customer message in the same conversation.
        """

        now = self._clock().astimezone(UTC)
        scope = (store_id, platform_store_id or "", conversation_id)
        present = attention_verified and attention_state is not PDDReplyAttentionState.NONE
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT state, attention_present, captured_message_high_watermark,
                       first_observed_at, latest_message_id, attention_state,
                       attention_seconds
                FROM pdd_conversation_captures
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                scope,
            ).fetchone()
            if row is None:
                if not present:
                    # PDD may change or temporarily omit its red "reply due"
                    # marker.  Keep a privacy-safe row-preview baseline so a
                    # later preview change can still schedule this exact
                    # conversation without treating every historical row as
                    # pending on startup.
                    if latest_message_id is None:
                        connection.commit()
                        return None
                    connection.execute(
                        """
                        INSERT INTO pdd_conversation_captures (
                            store_id, platform_store_id, conversation_id, state,
                            attention_state, attention_present, attention_seconds,
                            attention_evidence_hash, page_position,
                            captured_message_high_watermark, latest_message_id,
                            first_observed_at, last_observed_at, attempts, last_error_code
                        ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 0, ?, ?, ?, 0, NULL)
                        """,
                        (
                            *scope,
                            PDDConversationCaptureState.COMPLETED.value,
                            attention_state.value,
                            attention_seconds,
                            attention_evidence_hash,
                            page_position,
                            latest_message_id,
                            now.isoformat(),
                            now.isoformat(),
                        ),
                    )
                    connection.commit()
                else:
                    connection.execute(
                        """
                    INSERT INTO pdd_conversation_captures (
                        store_id, platform_store_id, conversation_id, state,
                        attention_state, attention_present, attention_seconds,
                        attention_evidence_hash, page_position,
                        captured_message_high_watermark, latest_message_id,
                        first_observed_at, last_observed_at, attempts, last_error_code
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 0, NULL, ?, ?, 0, NULL)
                    """,
                        (
                            *scope,
                            PDDConversationCaptureState.PENDING.value,
                            attention_state.value,
                            attention_seconds,
                            attention_evidence_hash,
                            page_position,
                            now.isoformat(),
                            now.isoformat(),
                        ),
                    )
            else:
                state = PDDConversationCaptureState(str(row[0]))
                was_present = bool(row[1])
                watermark = int(row[2])
                sequence_advanced = latest_sequence is not None and latest_sequence > watermark
                message_changed = (
                    latest_message_id is not None
                    and row[4] is not None
                    and latest_message_id != str(row[4])
                )
                preview_identity_upgraded = (
                    latest_message_id is not None
                    and row[4] is not None
                    and str(row[4]).startswith("sha256:")
                    and latest_message_id.startswith("preview-sha256:")
                )
                if preview_identity_upgraded:
                    message_changed = False
                    if (
                        not present
                        and state
                        in {
                            PDDConversationCaptureState.PENDING,
                            PDDConversationCaptureState.NAVIGATING,
                            PDDConversationCaptureState.MANUAL_REVIEW,
                        }
                    ):
                        state = PDDConversationCaptureState.COMPLETED
                previous_attention_state = PDDReplyAttentionState(str(row[5]))
                previous_attention_seconds = (
                    None if row[6] is None else int(row[6])
                )
                countdown_restarted = (
                    attention_state is PDDReplyAttentionState.COUNTDOWN
                    and attention_seconds is not None
                    and (
                        previous_attention_state is PDDReplyAttentionState.OVERDUE
                        or (
                            previous_attention_state
                            is PDDReplyAttentionState.COUNTDOWN
                            and previous_attention_seconds is not None
                            and attention_seconds > previous_attention_seconds + 2
                        )
                    )
                )
                if state is PDDConversationCaptureState.COMPLETED and (
                    sequence_advanced
                    or message_changed
                    or (present and (not was_present or countdown_restarted))
                ):
                    state = PDDConversationCaptureState.PENDING
                connection.execute(
                    """
                    UPDATE pdd_conversation_captures
                    SET state = ?, attention_state = ?, attention_present = ?,
                        attention_seconds = ?, attention_evidence_hash = ?,
                        page_position = ?, last_observed_at = ?,
                        latest_message_id = CASE WHEN ? THEN ? ELSE latest_message_id END,
                        last_error_code = CASE WHEN ? THEN NULL ELSE last_error_code END
                    WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                    """,
                    (
                        state.value,
                        attention_state.value,
                        1 if present else 0,
                        attention_seconds,
                        attention_evidence_hash,
                        page_position,
                        now.isoformat(),
                        1 if preview_identity_upgraded else 0,
                        latest_message_id,
                        1
                        if preview_identity_upgraded
                        or state is PDDConversationCaptureState.PENDING
                        else 0,
                        *scope,
                    ),
                )
            connection.commit()
        return self.get(store_id, platform_store_id, conversation_id)

    def mark_preview_baseline(
        self,
        *,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        latest_message_id: str | None,
    ) -> PDDConversationCaptureRecord:
        """Complete a preview-only task that contained no new customer message."""

        now = self._clock().astimezone(UTC).isoformat()
        scope = (store_id, platform_store_id or "", conversation_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?,
                    latest_message_id = COALESCE(?, latest_message_id),
                    last_observed_at = ?, last_error_code = NULL
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                (
                    PDDConversationCaptureState.COMPLETED.value,
                    latest_message_id,
                    now,
                    *scope,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise KeyError("PDD conversation capture task does not exist")
            connection.commit()
        record = self.get(store_id, platform_store_id, conversation_id)
        if record is None:
            raise KeyError("PDD conversation capture task disappeared")
        return record

    def pending(self, *, limit: int = 20) -> tuple[PDDConversationCaptureRecord, ...]:
        bounded = max(1, min(limit, 20))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT store_id, platform_store_id, conversation_id, state,
                       attention_state, attention_present, attention_seconds,
                       attention_evidence_hash, page_position,
                       captured_message_high_watermark, latest_message_id,
                       first_observed_at, last_observed_at, attempts, last_error_code
                FROM pdd_conversation_captures
                WHERE state = ?
                ORDER BY
                    CASE attention_state
                        WHEN 'OVERDUE' THEN 0
                        WHEN 'COUNTDOWN' THEN 1
                        ELSE 2
                    END,
                    CASE WHEN attention_seconds IS NULL THEN 2147483647
                         ELSE attention_seconds END,
                    CASE WHEN page_position IS NULL THEN 2147483647
                         ELSE page_position END,
                    first_observed_at,
                    conversation_id
                LIMIT ?
                """,
                (PDDConversationCaptureState.PENDING.value, bounded),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def claim(
        self, store_id: str, platform_store_id: str | None, conversation_id: str
    ) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?, attempts = attempts + 1, last_error_code = NULL
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                  AND state = ?
                """,
                (
                    PDDConversationCaptureState.NAVIGATING.value,
                    store_id,
                    platform_store_id or "",
                    conversation_id,
                    PDDConversationCaptureState.PENDING.value,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1

    def mark_captured(
        self,
        *,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        latest_message_id: str | None,
        latest_sequence: int,
        host_acked_sequence: int | None,
    ) -> PDDConversationCaptureRecord:
        if latest_sequence < 0:
            raise ValueError("PDD capture watermark cannot be negative")
        state = (
            PDDConversationCaptureState.COMPLETED
            if host_acked_sequence is not None and host_acked_sequence >= latest_sequence
            else PDDConversationCaptureState.CAPTURED_WAITING_ACK
        )
        now = self._clock().astimezone(UTC).isoformat()
        scope = (store_id, platform_store_id or "", conversation_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?,
                    captured_message_high_watermark = CASE
                        WHEN ? > captured_message_high_watermark THEN ?
                        ELSE captured_message_high_watermark END,
                    latest_message_id = CASE
                        WHEN ? >= captured_message_high_watermark THEN ?
                        ELSE latest_message_id END,
                    last_observed_at = ?, last_error_code = NULL
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                (
                    state.value,
                    latest_sequence,
                    latest_sequence,
                    latest_sequence,
                    latest_message_id,
                    now,
                    *scope,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise KeyError("PDD conversation capture task does not exist")
            connection.commit()
        record = self.get(store_id, platform_store_id, conversation_id)
        if record is None:
            raise KeyError("PDD conversation capture task disappeared")
        return record

    def reconcile_ack(
        self,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        host_acked_sequence: int | None,
    ) -> PDDConversationCaptureRecord | None:
        if host_acked_sequence is None:
            return self.get(store_id, platform_store_id, conversation_id)
        scope = (store_id, platform_store_id or "", conversation_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?, last_error_code = NULL
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                  AND state = ? AND captured_message_high_watermark <= ?
                """,
                (
                    PDDConversationCaptureState.COMPLETED.value,
                    *scope,
                    PDDConversationCaptureState.CAPTURED_WAITING_ACK.value,
                    host_acked_sequence,
                ),
            )
            connection.commit()
        return self.get(store_id, platform_store_id, conversation_id)

    def mark_failure(
        self,
        *,
        store_id: str,
        platform_store_id: str | None,
        conversation_id: str,
        error_code: str,
        manual_review: bool,
    ) -> None:
        state = (
            PDDConversationCaptureState.MANUAL_REVIEW
            if manual_review
            else PDDConversationCaptureState.PENDING
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE pdd_conversation_captures
                SET state = ?, last_error_code = ?
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                (
                    state.value,
                    error_code[:160],
                    store_id,
                    platform_store_id or "",
                    conversation_id,
                ),
            )
            connection.commit()

    def get(
        self, store_id: str, platform_store_id: str | None, conversation_id: str
    ) -> PDDConversationCaptureRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT store_id, platform_store_id, conversation_id, state,
                       attention_state, attention_present, attention_seconds,
                       attention_evidence_hash, page_position,
                       captured_message_high_watermark, latest_message_id,
                       first_observed_at, last_observed_at, attempts, last_error_code
                FROM pdd_conversation_captures
                WHERE store_id = ? AND platform_store_id = ? AND conversation_id = ?
                """,
                (store_id, platform_store_id or "", conversation_id),
            ).fetchone()
        return None if row is None else self._record(row)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pdd_conversation_captures (
                    store_id TEXT NOT NULL,
                    platform_store_id TEXT NOT NULL DEFAULT '',
                    conversation_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attention_state TEXT NOT NULL,
                    attention_present INTEGER NOT NULL,
                    attention_seconds INTEGER,
                    attention_evidence_hash TEXT,
                    page_position INTEGER,
                    captured_message_high_watermark INTEGER NOT NULL DEFAULT 0,
                    latest_message_id TEXT,
                    first_observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT,
                    PRIMARY KEY(store_id, platform_store_id, conversation_id)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _record(row: Iterable[object]) -> PDDConversationCaptureRecord:
        values = tuple(row)
        platform_store_id = str(values[1]) if values[1] else None
        return PDDConversationCaptureRecord(
            store_id=str(values[0]),
            platform_store_id=platform_store_id,
            conversation_id=str(values[2]),
            state=PDDConversationCaptureState(str(values[3])),
            attention_state=PDDReplyAttentionState(str(values[4])),
            attention_present=bool(values[5]),
            attention_seconds=None if values[6] is None else int(values[6]),
            attention_evidence_hash=None if values[7] is None else str(values[7]),
            page_position=None if values[8] is None else int(values[8]),
            captured_message_high_watermark=int(values[9]),
            latest_message_id=None if values[10] is None else str(values[10]),
            first_observed_at=datetime.fromisoformat(str(values[11])),
            last_observed_at=datetime.fromisoformat(str(values[12])),
            attempts=int(values[13]),
            last_error_code=None if values[14] is None else str(values[14]),
        )


__all__ = [
    "DurablePDDConversationCaptureStore",
    "PDDConversationCaptureRecord",
    "PDDConversationCaptureState",
    "PDDReplyAttentionState",
]
