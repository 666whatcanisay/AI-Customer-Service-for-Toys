from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ControlledSendGrantError(RuntimeError):
    """Fail-closed boundary for the independent TEST_ONLY send path."""


type AutoPolicyMode = Literal["AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"]
type AutoAuthorizationBasis = Literal[
    "EXACT_APPROVED_REPLY",
    "QUALITY_GATED_LOW_RISK",
    "STORE_APPROVED_KNOWLEDGE",
    "STORE_APPROVED_FIXED_REPLY",
    "STORE_APPROVED_FALLBACK",
]


class ControlledSendGrantV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["controlled-send-grant.v1"] = "controlled-send-grant.v1"
    grant_id: str = Field(pattern=r"^controlled-send-grant:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=160)
    ai_cs_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
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
    pilot_window_id: str | None = Field(
        default=None,
        pattern=r"^controlled-pilot-window:[a-f0-9]{64}$",
    )

    @model_validator(mode="after")
    def validate_ttl(self) -> ControlledSendGrantV1:
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
        ai_cs_store_id: str | None = None,
        platform_store_id: str | None = None,
        test_buyer_hash: str,
        conversation_id: str,
        customer_message_id: str,
        decision_id: str,
        reply_content: str,
        operator_reference: str,
        issued_at: datetime,
        pilot_window_id: str | None = None,
    ) -> ControlledSendGrantV1:
        issued = issued_at.astimezone(UTC)
        reply_hash = hashlib.sha256(reply_content.encode("utf-8")).hexdigest()
        material_items: list[object] = [
            store_id,
            test_buyer_hash,
            conversation_id,
            customer_message_id,
            decision_id,
            reply_hash,
            operator_reference,
            issued.isoformat(),
        ]
        # Preserve the original manual-grant identity when no Pilot window is used.
        if pilot_window_id is not None:
            material_items.append(pilot_window_id)
        if ai_cs_store_id is not None or platform_store_id is not None:
            material_items.extend([ai_cs_store_id, platform_store_id])
        material = json.dumps(
            material_items,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return cls(
            grant_id="controlled-send-grant:"
            + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            store_id=store_id,
            ai_cs_store_id=ai_cs_store_id,
            platform_store_id=platform_store_id,
            test_buyer_hash=test_buyer_hash,
            conversation_id=conversation_id,
            customer_message_id=customer_message_id,
            decision_id=decision_id,
            reply_content_sha256=reply_hash,
            operator_reference=operator_reference,
            issued_at=issued,
            expires_at=issued + timedelta(minutes=5),
            pilot_window_id=pilot_window_id,
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


def normalize_pilot_question(value: str) -> str:
    """Canonicalize only the question, never the approved reply text."""

    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def normalized_question_sha256(value: str) -> str:
    return hashlib.sha256(normalize_pilot_question(value).encode("utf-8")).hexdigest()


class ControlledAutoPolicyGrantV1(BaseModel):
    """One single-use AUTO authorization for one current Decision."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["controlled-auto-policy-grant.v1"] = (
        "controlled-auto-policy-grant.v1"
    )
    grant_id: str = Field(pattern=r"^controlled-auto-policy-grant:[a-f0-9]{64}$")
    pilot_window_id: str = Field(
        pattern=r"^controlled-pilot-window:[a-f0-9]{64}$"
    )
    store_id: str = Field(min_length=1, max_length=160)
    ai_cs_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    test_buyer_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_message_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=255)
    reply_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_reply_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str | None = Field(default=None, max_length=255)
    sku_id: str | None = Field(default=None, max_length=255)
    policy_mode: AutoPolicyMode = "AUTO_LOW_RISK"
    policy_revision: int = Field(ge=1)
    whitelist_revision: str = Field(min_length=1, max_length=160)
    knowledge_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reply_evidence_bundle_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    authorization_basis: AutoAuthorizationBasis = "EXACT_APPROVED_REPLY"
    deployment_scope: Literal["PILOT", "PRODUCTION_AUTO"] = "PILOT"
    nonce: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    max_attempts: Literal[1] = 1
    max_successes: Literal[1] = 1
    authorization_kind: Literal["AUTO_POLICY"] = "AUTO_POLICY"
    test_only: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> ControlledAutoPolicyGrantV1:
        if self.expires_at <= self.issued_at:
            raise ValueError("controlled auto grant expiry is invalid")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("controlled auto grant TTL cannot exceed five minutes")
        if self.authorization_basis == "EXACT_APPROVED_REPLY":
            if self.reply_content_sha256 != self.approved_reply_sha256:
                raise ValueError("AUTO Pilot reply must exactly match the approved reply")
        else:
            if not all(
                (
                    self.ai_cs_store_id,
                    self.platform_store_id,
                    self.reply_evidence_bundle_sha256,
                    self.nonce,
                )
            ):
                raise ValueError(
                    "governed AUTO requires double Store identity, Evidence, and nonce"
                )
            if self.authorization_basis in {
                "QUALITY_GATED_LOW_RISK",
                "STORE_APPROVED_KNOWLEDGE",
            } and not self.product_id:
                raise ValueError("knowledge-backed AUTO requires product")
            if self.deployment_scope == "PRODUCTION_AUTO" and self.test_only:
                raise ValueError("production AUTO grant cannot claim test_only=true")
        if (
            self.policy_mode == "AUTO_ALL_MESSAGES_V1"
            and self.authorization_basis == "EXACT_APPROVED_REPLY"
        ):
            raise ValueError("all-message AUTO requires a governed per-message basis")
        return self

    @classmethod
    def issue(
        cls,
        *,
        pilot_window_id: str,
        store_id: str,
        ai_cs_store_id: str | None = None,
        platform_store_id: str | None = None,
        test_buyer_hash: str,
        conversation_id: str,
        customer_message_id: str,
        decision_id: str,
        question: str,
        reply_content: str,
        approved_reply_sha256: str | None,
        product_id: str | None,
        sku_id: str | None,
        policy_revision: int,
        whitelist_revision: str,
        knowledge_scope_sha256: str,
        issued_at: datetime,
        reply_evidence_bundle_sha256: str | None = None,
        authorization_basis: AutoAuthorizationBasis = "EXACT_APPROVED_REPLY",
        policy_mode: AutoPolicyMode = "AUTO_LOW_RISK",
        deployment_scope: Literal["PILOT", "PRODUCTION_AUTO"] = "PILOT",
        nonce: str | None = None,
    ) -> ControlledAutoPolicyGrantV1:
        issued = issued_at.astimezone(UTC)
        reply_hash = hashlib.sha256(reply_content.encode("utf-8")).hexdigest()
        question_hash = normalized_question_sha256(question)
        approved_hash = approved_reply_sha256 or reply_hash
        issued_nonce = nonce or (
            secrets.token_hex(32)
            if authorization_basis != "EXACT_APPROVED_REPLY"
            else None
        )
        material = json.dumps(
            [
                pilot_window_id,
                store_id,
                ai_cs_store_id,
                platform_store_id,
                test_buyer_hash,
                conversation_id,
                customer_message_id,
                decision_id,
                question_hash,
                reply_hash,
                product_id,
                sku_id,
                policy_revision,
                whitelist_revision,
                knowledge_scope_sha256,
                reply_evidence_bundle_sha256,
                authorization_basis,
                policy_mode,
                deployment_scope,
                issued_nonce,
                issued.isoformat(),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return cls(
            grant_id="controlled-auto-policy-grant:"
            + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            pilot_window_id=pilot_window_id,
            store_id=store_id,
            ai_cs_store_id=ai_cs_store_id,
            platform_store_id=platform_store_id,
            test_buyer_hash=test_buyer_hash,
            conversation_id=conversation_id,
            customer_message_id=customer_message_id,
            decision_id=decision_id,
            reply_content_sha256=reply_hash,
            approved_reply_sha256=approved_hash,
            normalized_question_sha256=question_hash,
            product_id=product_id,
            sku_id=sku_id,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            knowledge_scope_sha256=knowledge_scope_sha256,
            reply_evidence_bundle_sha256=reply_evidence_bundle_sha256,
            authorization_basis=authorization_basis,
            policy_mode=policy_mode,
            deployment_scope=deployment_scope,
            nonce=issued_nonce,
            issued_at=issued,
            expires_at=issued + timedelta(minutes=5),
            test_only=deployment_scope == "PILOT",
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
            raise ControlledSendGrantError("controlled auto grant is not active")
        actual = (
            store_id,
            test_buyer_hash,
            conversation_id,
            customer_message_id,
            decision_id,
            hashlib.sha256(reply_content.encode("utf-8")).hexdigest(),
        )
        expected = (
            self.store_id,
            self.test_buyer_hash,
            self.conversation_id,
            self.customer_message_id,
            self.decision_id,
            self.reply_content_sha256,
        )
        if actual != expected:
            raise ControlledSendGrantError("controlled auto target or reply hash changed")


type ControlledSendGrant = ControlledSendGrantV1 | ControlledAutoPolicyGrantV1


class ControlledPilotSendWindowV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["controlled-pilot-send-window.v1"] = (
        "controlled-pilot-send-window.v1"
    )
    window_id: str = Field(pattern=r"^controlled-pilot-window:[a-f0-9]{64}$")
    mode: Literal["MANUAL_CONFIRM", "AUTO_POLICY"]
    store_id: str = Field(min_length=1, max_length=160)
    ai_cs_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    test_buyer_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_id: str = Field(min_length=1, max_length=255)
    normalized_question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_reply_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str | None = Field(default=None, max_length=255)
    sku_id: str | None = Field(default=None, max_length=255)
    policy_revision: int = Field(ge=1)
    whitelist_revision: str = Field(min_length=1, max_length=160)
    knowledge_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reply_evidence_bundle_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    authorization_basis: AutoAuthorizationBasis = "EXACT_APPROVED_REPLY"
    policy_mode: AutoPolicyMode = "AUTO_LOW_RISK"
    deployment_scope: Literal["PILOT", "PRODUCTION_AUTO"] = "PILOT"
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    max_successes: Literal[1] = 1

    @model_validator(mode="after")
    def validate_ttl(self) -> ControlledPilotSendWindowV1:
        if self.expires_at <= self.issued_at:
            raise ValueError("controlled Pilot window expiry is invalid")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("controlled Pilot window TTL cannot exceed five minutes")
        if self.authorization_basis != "EXACT_APPROVED_REPLY" and not all(
            (
                self.ai_cs_store_id,
                self.platform_store_id,
                self.reply_evidence_bundle_sha256,
            )
        ):
            raise ValueError(
                "governed AUTO window requires double Store identity and Evidence"
            )
        return self

    @classmethod
    def issue(
        cls,
        *,
        mode: Literal["MANUAL_CONFIRM", "AUTO_POLICY"],
        store_id: str,
        ai_cs_store_id: str | None = None,
        platform_store_id: str | None = None,
        test_buyer_hash: str,
        conversation_id: str,
        question: str,
        approved_reply: str,
        product_id: str | None,
        sku_id: str | None,
        policy_revision: int,
        whitelist_revision: str,
        knowledge_scope_sha256: str,
        issued_at: datetime,
        reply_evidence_bundle_sha256: str | None = None,
        authorization_basis: AutoAuthorizationBasis = "EXACT_APPROVED_REPLY",
        policy_mode: AutoPolicyMode = "AUTO_LOW_RISK",
        deployment_scope: Literal["PILOT", "PRODUCTION_AUTO"] = "PILOT",
    ) -> ControlledPilotSendWindowV1:
        issued = issued_at.astimezone(UTC)
        question_hash = normalized_question_sha256(question)
        reply_hash = hashlib.sha256(approved_reply.encode("utf-8")).hexdigest()
        material = json.dumps(
            [
                mode,
                store_id,
                ai_cs_store_id,
                platform_store_id,
                test_buyer_hash,
                conversation_id,
                question_hash,
                reply_hash,
                product_id,
                sku_id,
                policy_revision,
                whitelist_revision,
                knowledge_scope_sha256,
                reply_evidence_bundle_sha256,
                authorization_basis,
                policy_mode,
                deployment_scope,
                issued.isoformat(),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return cls(
            window_id="controlled-pilot-window:"
            + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            mode=mode,
            store_id=store_id,
            ai_cs_store_id=ai_cs_store_id,
            platform_store_id=platform_store_id,
            test_buyer_hash=test_buyer_hash,
            conversation_id=conversation_id,
            normalized_question_sha256=question_hash,
            approved_reply_sha256=reply_hash,
            product_id=product_id,
            sku_id=sku_id,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            knowledge_scope_sha256=knowledge_scope_sha256,
            reply_evidence_bundle_sha256=reply_evidence_bundle_sha256,
            authorization_basis=authorization_basis,
            policy_mode=policy_mode,
            deployment_scope=deployment_scope,
            issued_at=issued,
            expires_at=issued + timedelta(minutes=5),
        )


class ControlledPilotSendWindowStore:
    """Durable, single-open-window switch; default state is always disabled."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS controlled_pilot_send_window (
                    window_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    opened_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    closed_at TEXT,
                    close_reason TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_controlled_pilot_open
                ON controlled_pilot_send_window(status)
                WHERE status = 'OPEN'
                """
            )

    def arm(self, window: ControlledPilotSendWindowV1, *, now: datetime) -> None:
        current = now.astimezone(UTC)
        if current < window.issued_at or current >= window.expires_at:
            raise ControlledSendGrantError("controlled Pilot window is not active")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._expire_locked(connection, current)
                connection.execute(
                    """
                    INSERT INTO controlled_pilot_send_window (
                        window_id, payload_json, mode, status, opened_at, expires_at
                    ) VALUES (?, ?, ?, 'OPEN', ?, ?)
                    """,
                    (
                        window.window_id,
                        window.model_dump_json(),
                        window.mode,
                        current.isoformat(),
                        window.expires_at.astimezone(UTC).isoformat(),
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ControlledSendGrantError(
                "another controlled Pilot send window is already open"
            ) from exc

    def active(self, *, now: datetime) -> ControlledPilotSendWindowV1 | None:
        current = now.astimezone(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_locked(connection, current)
            row = connection.execute(
                """
                SELECT payload_json FROM controlled_pilot_send_window
                WHERE status = 'OPEN'
                """
            ).fetchone()
            connection.commit()
        return (
            ControlledPilotSendWindowV1.model_validate_json(row[0])
            if row is not None
            else None
        )

    def assert_authorized(
        self,
        grant: ControlledSendGrant,
        *,
        question: str,
        product_id: str | None,
        sku_id: str | None,
        knowledge_scope_sha256: str,
        reply_evidence_bundle_sha256: str | None = None,
        now: datetime,
    ) -> ControlledPilotSendWindowV1:
        window = self.active(now=now)
        if window is None or grant.pilot_window_id != window.window_id:
            raise ControlledSendGrantError("controlled Pilot send window is disabled")
        expected_mode = (
            "AUTO_POLICY"
            if isinstance(grant, ControlledAutoPolicyGrantV1)
            else "MANUAL_CONFIRM"
        )
        if window.mode != expected_mode:
            raise ControlledSendGrantError("grant type does not match Pilot window mode")
        question_hash = normalized_question_sha256(question)
        if (
            grant.store_id != window.store_id
            or grant.ai_cs_store_id != window.ai_cs_store_id
            or grant.platform_store_id != window.platform_store_id
            or grant.test_buyer_hash != window.test_buyer_hash
            or grant.conversation_id != window.conversation_id
            or question_hash != window.normalized_question_sha256
            or grant.reply_content_sha256 != window.approved_reply_sha256
            or product_id != window.product_id
            or sku_id != window.sku_id
            or knowledge_scope_sha256 != window.knowledge_scope_sha256
        ):
            raise ControlledSendGrantError("controlled Pilot scope or exact hash changed")
        if isinstance(grant, ControlledAutoPolicyGrantV1) and (
            grant.normalized_question_sha256 != window.normalized_question_sha256
            or grant.approved_reply_sha256 != window.approved_reply_sha256
            or grant.policy_revision != window.policy_revision
            or grant.whitelist_revision != window.whitelist_revision
            or grant.knowledge_scope_sha256 != window.knowledge_scope_sha256
            or grant.authorization_basis != window.authorization_basis
            or grant.policy_mode != window.policy_mode
            or grant.deployment_scope != window.deployment_scope
            or grant.ai_cs_store_id != window.ai_cs_store_id
            or grant.platform_store_id != window.platform_store_id
            or grant.reply_evidence_bundle_sha256
            != window.reply_evidence_bundle_sha256
            or reply_evidence_bundle_sha256
            != window.reply_evidence_bundle_sha256
        ):
            raise ControlledSendGrantError("AUTO Pilot policy or allowlist changed")
        return window

    def close(self, window_id: str, *, reason: str, now: datetime) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                """
                UPDATE controlled_pilot_send_window
                SET status = 'CLOSED', closed_at = ?, close_reason = ?
                WHERE window_id = ? AND status = 'OPEN'
                """,
                (now.astimezone(UTC).isoformat(), reason[:160], window_id),
            ).rowcount
            connection.commit()
        if changed != 1:
            raise ControlledSendGrantError("controlled Pilot window is not open")

    def consume_success(self, window_id: str, *, now: datetime) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                """
                UPDATE controlled_pilot_send_window
                SET success_count = 1, status = 'CLOSED', closed_at = ?,
                    close_reason = 'SUCCESS_LIMIT_REACHED'
                WHERE window_id = ? AND status = 'OPEN' AND success_count = 0
                """,
                (now.astimezone(UTC).isoformat(), window_id),
            ).rowcount
            connection.commit()
        if changed != 1:
            raise ControlledSendGrantError("controlled Pilot success was already consumed")

    def _expire_locked(self, connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            """
            UPDATE controlled_pilot_send_window
            SET status = 'CLOSED', closed_at = ?, close_reason = 'TTL_EXPIRED'
            WHERE status = 'OPEN' AND expires_at <= ?
            """,
            (now.isoformat(), now.isoformat()),
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None)


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
        grant: ControlledSendGrant,
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
        grant: ControlledSendGrant,
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
    "ControlledAutoPolicyGrantV1",
    "ControlledPDDTestOnlySendGate",
    "ControlledPilotSendWindowStore",
    "ControlledPilotSendWindowV1",
    "ControlledSendGrant",
    "ControlledSendGrantError",
    "ControlledSendGrantStore",
    "ControlledSendGrantV1",
    "normalize_pilot_question",
    "normalized_question_sha256",
]
