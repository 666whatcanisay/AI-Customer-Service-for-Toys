from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ControlledSendGrantError(RuntimeError):
    """Fail-closed boundary for the independent TEST_ONLY send path."""


class ControlledSendGrantV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["controlled-send-grant.v1"] = "controlled-send-grant.v1"
    grant_id: str = Field(pattern=r"^controlled-send-grant:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=160)
    test_buyer_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_message_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=255)
    reply_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operator_reference: str = Field(min_length=1, max_length=160)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    max_attempts: Literal[1] = 1
    authorization_kind: Literal["MANUAL_CONFIRM"] = "MANUAL_CONFIRM"
    test_only: Literal[True] = True
    auto_policy_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_ttl(self) -> "ControlledSendGrantV1":
        if self.expires_at <= self.issued_at:
            raise ValueError("controlled send grant expiry is invalid")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("controlled send grant TTL cannot exceed five minutes")
        return self

    @classmethod
    def issue(
        cls,
        *,
        store_id: str,
        test_buyer_hash: str,
        conversation_id: str,
        customer_message_id: str,
        decision_id: str,
        reply_content: str,
        operator_reference: str,
        issued_at: datetime,
    ) -> "ControlledSendGrantV1":
        issued = issued_at.astimezone(UTC)
        reply_hash = hashlib.sha256(reply_content.encode("utf-8")).hexdigest()
        material = json.dumps(
            [
                store_id,
                test_buyer_hash,
                conversation_id,
                customer_message_id,
                decision_id,
                reply_hash,
                operator_reference,
                issued.isoformat(),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return cls(
            grant_id="controlled-send-grant:"
            + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            store_id=store_id,
            test_buyer_hash=test_buyer_hash,
            conversation_id=conversation_id,
            customer_message_id=customer_message_id,
            decision_id=decision_id,
            reply_content_sha256=reply_hash,
            operator_reference=operator_reference,
            issued_at=issued,
            expires_at=issued + timedelta(minutes=5),
        )

    def assert_target(
        self,
        *,
        store_id: str,
        test_buyer_hash: str,
        conversation_id: str,
        customer_message_id: str,
        decision_id: str,
        reply_content: str,
        now: datetime,
    ) -> None:
        current = now.astimezone(UTC)
        if current < self.issued_at or current >= self.expires_at:
            raise ControlledSendGrantError("controlled send grant is not active")
        expected = (
            self.store_id,
            self.test_buyer_hash,
            self.conversation_id,
            self.customer_message_id,
            self.decision_id,
            self.reply_content_sha256,
        )
        actual = (
            store_id,
            test_buyer_hash,
            conversation_id,
            customer_message_id,
            decision_id,
            hashlib.sha256(reply_content.encode("utf-8")).hexdigest(),
        )
        if actual != expected:
            raise ControlledSendGrantError("controlled send target or content changed")


class ControlledSendGrantStore:
    """Persistent single-attempt ledger, isolated from the production Agent."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consumed_controlled_send_grant (
                    grant_id TEXT PRIMARY KEY,
                    grant_digest TEXT NOT NULL,
                    consumed_at TEXT NOT NULL
                )
                """
            )

    def consume_once(
        self,
        grant: ControlledSendGrantV1,
        *,
        store_id: str,
        test_buyer_hash: str,
        conversation_id: str,
        customer_message_id: str,
        decision_id: str,
        reply_content: str,
        now: datetime,
    ) -> None:
        grant.assert_target(
            store_id=store_id,
            test_buyer_hash=test_buyer_hash,
            conversation_id=conversation_id,
            customer_message_id=customer_message_id,
            decision_id=decision_id,
            reply_content=reply_content,
            now=now,
        )
        digest = hashlib.sha256(
            grant.model_dump_json().encode("utf-8")
        ).hexdigest()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO consumed_controlled_send_grant
                        (grant_id, grant_digest, consumed_at)
                    VALUES (?, ?, ?)
                    """,
                    (grant.grant_id, digest, now.astimezone(UTC).isoformat()),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ControlledSendGrantError(
                "controlled send grant was already consumed; retry is forbidden"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None)


class ControlledBrowserSendPort(Protocol):
    def send(
        self,
        *,
        content: str,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_customer_message_id: str,
    ) -> object: ...


class ControlledPDDTestOnlySendGate:
    """Independent grant gate; never composed into the formal read runtime."""

    def __init__(
        self,
        *,
        sender: ControlledBrowserSendPort,
        grant_store: ControlledSendGrantStore,
    ) -> None:
        self._sender = sender
        self._grant_store = grant_store

    def send_once(
        self,
        grant: ControlledSendGrantV1,
        *,
        content: str,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_customer_message_id: str,
        expected_decision_id: str,
        now: datetime,
    ) -> object:
        self._grant_store.consume_once(
            grant,
            store_id=expected_store_id,
            test_buyer_hash=expected_customer_reference,
            conversation_id=expected_conversation_id,
            customer_message_id=expected_customer_message_id,
            decision_id=expected_decision_id,
            reply_content=content,
            now=now,
        )
        return self._sender.send(
            content=content,
            expected_store_id=expected_store_id,
            expected_conversation_id=expected_conversation_id,
            expected_customer_reference=expected_customer_reference,
            expected_customer_message_id=expected_customer_message_id,
        )


__all__ = [
    "ControlledPDDTestOnlySendGate",
    "ControlledSendGrantError",
    "ControlledSendGrantStore",
    "ControlledSendGrantV1",
]
