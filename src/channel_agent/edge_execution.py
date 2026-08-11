from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationVerifier,
    reply_text_sha256,
)


class EdgeExecutionError(RuntimeError):
    pass


class EdgeExecutionConflict(EdgeExecutionError):
    pass


class EdgeExecutionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class EdgeTransportResult(EdgeExecutionModel):
    outcome: Literal["SUCCESS", "FAILED", "UNKNOWN"]
    transport_triggered: bool | None
    customer_message_sent: bool | None
    confirmation_state: Literal["CONFIRMED_SUCCESS", "CONFIRMED_FAILURE", "UNCONFIRMED"]
    external_message_id: str | None = Field(default=None, min_length=1, max_length=255)
    error_code: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_facts(self) -> EdgeTransportResult:
        if self.outcome == "SUCCESS" and (
            self.transport_triggered is not True
            or self.customer_message_sent is not True
            or self.confirmation_state != "CONFIRMED_SUCCESS"
        ):
            raise ValueError("SUCCESS requires confirmed send facts")
        if self.outcome == "FAILED" and self.confirmation_state != "CONFIRMED_FAILURE":
            raise ValueError("FAILED requires confirmed failure")
        if self.outcome == "UNKNOWN" and (
            self.transport_triggered is False
            or self.customer_message_sent is False
            or self.confirmation_state != "UNCONFIRMED"
        ):
            raise ValueError("UNKNOWN cannot claim that transport or send was false")
        return self


class AuthorizedEdgeSendCommand(EdgeExecutionModel):
    authorization: ExecutionAuthorization
    reply_text: str = Field(min_length=1, max_length=8_000, repr=False)


class EdgeExecutionReceipt(EdgeExecutionModel):
    receipt_id: str = Field(min_length=1, max_length=160)
    authorization_id: str = Field(min_length=1, max_length=160)
    execution_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    send_key: str = Field(min_length=1, max_length=255)
    reply_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    outcome: Literal["SUCCESS", "FAILED", "UNKNOWN"]
    transport_triggered: bool | None
    customer_message_sent: bool | None
    confirmation_state: Literal["CONFIRMED_SUCCESS", "CONFIRMED_FAILURE", "UNCONFIRMED"]
    reconciliation_required: bool
    automatic_retry_allowed: Literal[False] = False
    external_message_id: str | None = None
    error_code: str | None = None
    created_at: AwareDatetime


class AuthorizedEdgeTransport(Protocol):
    def send(self, command: AuthorizedEdgeSendCommand) -> EdgeTransportResult: ...


class EdgeReceiptStore:
    """Append-only local receipt staging; acknowledged rows may be purged by retention."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_receipts (
                    send_key TEXT PRIMARY KEY,
                    receipt_id TEXT NOT NULL UNIQUE,
                    execution_id TEXT NOT NULL UNIQUE,
                    reply_sha256 TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    acknowledged_at TEXT
                )
                """
            )

    def get(self, *, send_key: str, execution_id: str, reply_sha256: str) -> EdgeExecutionReceipt | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT execution_id, reply_sha256, receipt_json FROM edge_receipts WHERE send_key = ?",
                (send_key,),
            ).fetchone()
        if row is None:
            return None
        if row[0] != execution_id or row[1] != reply_sha256:
            raise EdgeExecutionConflict("send key is bound to another execution or reply")
        return EdgeExecutionReceipt.model_validate_json(row[2])

    def append(self, receipt: EdgeExecutionReceipt) -> None:
        payload = receipt.model_dump_json()
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO edge_receipts (send_key, receipt_id, execution_id, reply_sha256, receipt_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        receipt.send_key,
                        receipt.receipt_id,
                        receipt.execution_id,
                        receipt.reply_sha256,
                        payload,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                row = connection.execute(
                    "SELECT execution_id, reply_sha256, receipt_json FROM edge_receipts WHERE send_key = ?",
                    (receipt.send_key,),
                )
                row = row.fetchone()
                existing = None if row is None else EdgeExecutionReceipt.model_validate_json(row[2])
                if existing != receipt:
                    raise EdgeExecutionConflict("immutable edge receipt already exists") from exc

    def acknowledge(self, receipt_id: str) -> None:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE edge_receipts SET acknowledged_at = ? WHERE receipt_id = ?",
                (datetime.now(UTC).isoformat(), receipt_id),
            )
            if cursor.rowcount != 1:
                raise EdgeExecutionError("edge receipt does not exist")
            connection.commit()

    def pending(self) -> tuple[EdgeExecutionReceipt, ...]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT receipt_json FROM edge_receipts "
                "WHERE acknowledged_at IS NULL ORDER BY rowid"
            ).fetchall()
        return tuple(EdgeExecutionReceipt.model_validate_json(row[0]) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


class EdgeExecutionService:
    def __init__(
        self,
        *,
        agent_id: str,
        device_id: str,
        verifier: ExecutionAuthorizationVerifier,
        receipt_store: EdgeReceiptStore,
        transport: AuthorizedEdgeTransport,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.agent_id = agent_id
        self.device_id = device_id
        self._verifier = verifier
        self._receipts = receipt_store
        self._transport = transport
        self._clock = clock
        self._lock = RLock()

    def execute(
        self,
        command: AuthorizedEdgeSendCommand,
        *,
        current_store_id: str,
        current_conversation_id: str,
        current_customer_reference: str,
        current_selector_evidence_hash: str,
    ) -> EdgeExecutionReceipt:
        authorization = command.authorization
        reply_hash = reply_text_sha256(command.reply_text)
        with self._lock:
            existing = self._receipts.get(
                send_key=authorization.send_key,
                execution_id=authorization.execution_id,
                reply_sha256=reply_hash,
            )
            if existing is not None:
                return existing
            self._verifier.verify(
                authorization,
                agent_id=self.agent_id,
                device_id=self.device_id,
                store_id=current_store_id,
                conversation_id=current_conversation_id,
                customer_reference=current_customer_reference,
                reply_text=command.reply_text,
                selector_evidence_hash=current_selector_evidence_hash,
            )
            try:
                result = self._transport.send(command)
            except Exception:
                result = EdgeTransportResult(
                    outcome="UNKNOWN",
                    transport_triggered=None,
                    customer_message_sent=None,
                    confirmation_state="UNCONFIRMED",
                    error_code="EDGE_TRANSPORT_RESULT_UNKNOWN",
                )
            receipt = EdgeExecutionReceipt(
                receipt_id=_receipt_id(authorization.execution_id),
                authorization_id=authorization.authorization_id,
                execution_id=authorization.execution_id,
                decision_id=authorization.decision_id,
                approval_id=authorization.approval_id,
                lease_id=authorization.lease_id,
                send_key=authorization.send_key,
                reply_sha256=reply_hash,
                outcome=result.outcome,
                transport_triggered=result.transport_triggered,
                customer_message_sent=result.customer_message_sent,
                confirmation_state=result.confirmation_state,
                reconciliation_required=result.outcome == "UNKNOWN",
                external_message_id=result.external_message_id,
                error_code=result.error_code,
                created_at=self._clock().astimezone(UTC),
            )
            self._receipts.append(receipt)
            return receipt


def _receipt_id(execution_id: str) -> str:
    digest = hashlib.sha256(execution_id.encode("utf-8")).hexdigest()[:32]
    return f"edge-receipt:{digest}"


__all__ = [
    "AuthorizedEdgeSendCommand",
    "AuthorizedEdgeTransport",
    "EdgeExecutionConflict",
    "EdgeExecutionError",
    "EdgeExecutionReceipt",
    "EdgeExecutionService",
    "EdgeReceiptStore",
    "EdgeTransportResult",
]
