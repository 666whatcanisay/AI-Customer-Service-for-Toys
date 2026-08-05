from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DecisionClaimState(StrEnum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    IN_PROGRESS = "IN_PROGRESS"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class DecisionClaim:
    state: DecisionClaimState
    response_json: str | None = None
    claim_token: str | None = None


class GatewayStateStore:
    """Private durable nonce and Decision idempotency state.

    The database stores hashes and completed Gateway responses, never HMAC
    secrets, Authorization headers, source excerpts, prompts, or RAG vectors.
    """

    def __init__(
        self,
        path: Path,
        *,
        nonce_ttl_seconds: int,
        decision_retention_seconds: int,
        decision_lease_seconds: int,
    ) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.nonce_ttl_seconds = nonce_ttl_seconds
        self.decision_retention_seconds = decision_retention_seconds
        self.decision_lease_seconds = decision_lease_seconds
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS gateway_nonces (
                    client_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (client_id, key_id, nonce)
                );
                CREATE TABLE IF NOT EXISTS gateway_decisions (
                    client_id TEXT NOT NULL,
                    route_family TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('IN_PROGRESS', 'COMPLETED')),
                    response_json TEXT,
                    claim_token TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    lease_expires_at REAL NOT NULL,
                    PRIMARY KEY (client_id, route_family, idempotency_key)
                );
                """
            )
            columns = {
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA table_info(gateway_decisions)"
                ).fetchall()
            }
            if "claim_token" not in columns:
                self._connection.execute(
                    "ALTER TABLE gateway_decisions ADD COLUMN claim_token TEXT"
                )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    def claim_nonce(
        self,
        *,
        client_id: str,
        key_id: str,
        nonce: str,
        now_epoch: float,
    ) -> bool:
        with self._lock, self._transaction():
            self._connection.execute(
                "DELETE FROM gateway_nonces WHERE expires_at <= ?", (now_epoch,)
            )
            try:
                self._connection.execute(
                    """
                    INSERT INTO gateway_nonces (client_id, key_id, nonce, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        key_id,
                        nonce,
                        now_epoch + self.nonce_ttl_seconds,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def begin_decision(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        payload_hash: str,
        now_epoch: float,
    ) -> DecisionClaim:
        route_family = "decisions"
        claim_token = uuid.uuid4().hex
        with self._lock, self._transaction():
            self._connection.execute(
                "DELETE FROM gateway_decisions WHERE expires_at <= ?", (now_epoch,)
            )
            row = self._connection.execute(
                """
                SELECT payload_hash, status, response_json, lease_expires_at
                FROM gateway_decisions
                WHERE client_id = ? AND route_family = ? AND idempotency_key = ?
                """,
                (client_id, route_family, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["payload_hash"] != payload_hash:
                    return DecisionClaim(DecisionClaimState.CONFLICT)
                if row["status"] == "COMPLETED":
                    return DecisionClaim(
                        DecisionClaimState.REPLAY,
                        response_json=str(row["response_json"]),
                    )
                if float(row["lease_expires_at"]) > now_epoch:
                    return DecisionClaim(DecisionClaimState.IN_PROGRESS)
                self._connection.execute(
                    """
                    UPDATE gateway_decisions
                    SET updated_at = ?, lease_expires_at = ?, claim_token = ?
                    WHERE client_id = ? AND route_family = ? AND idempotency_key = ?
                    """,
                    (
                        now_epoch,
                        now_epoch + self.decision_lease_seconds,
                        claim_token,
                        client_id,
                        route_family,
                        idempotency_key,
                    ),
                )
                return DecisionClaim(
                    DecisionClaimState.NEW,
                    claim_token=claim_token,
                )

            self._connection.execute(
                """
                INSERT INTO gateway_decisions (
                    client_id, route_family, idempotency_key, payload_hash,
                    status, response_json, created_at, updated_at,
                    expires_at, lease_expires_at, claim_token
                ) VALUES (?, ?, ?, ?, 'IN_PROGRESS', NULL, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    route_family,
                    idempotency_key,
                    payload_hash,
                    now_epoch,
                    now_epoch,
                    now_epoch + self.decision_retention_seconds,
                    now_epoch + self.decision_lease_seconds,
                    claim_token,
                ),
            )
            return DecisionClaim(
                DecisionClaimState.NEW,
                claim_token=claim_token,
            )

    def complete_decision(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        payload_hash: str,
        claim_token: str,
        response_json: str,
        now_epoch: float,
    ) -> None:
        with self._lock, self._transaction():
            cursor = self._connection.execute(
                """
                UPDATE gateway_decisions
                SET status = 'COMPLETED', response_json = ?, updated_at = ?,
                    expires_at = ?, lease_expires_at = ?
                WHERE client_id = ? AND route_family = 'decisions'
                  AND idempotency_key = ? AND payload_hash = ?
                  AND status = 'IN_PROGRESS' AND claim_token = ?
                """,
                (
                    response_json,
                    now_epoch,
                    now_epoch + self.decision_retention_seconds,
                    now_epoch,
                    client_id,
                    idempotency_key,
                    payload_hash,
                    claim_token,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("gateway idempotency completion lost its claim")

    def abandon_decision(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        payload_hash: str,
        claim_token: str,
    ) -> None:
        with self._lock, self._transaction():
            self._connection.execute(
                """
                DELETE FROM gateway_decisions
                WHERE client_id = ? AND route_family = 'decisions'
                  AND idempotency_key = ? AND payload_hash = ?
                  AND status = 'IN_PROGRESS' AND claim_token = ?
                """,
                (client_id, idempotency_key, payload_hash, claim_token),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
