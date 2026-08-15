from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ControlledAutoRuntimeError(RuntimeError):
    """Fail-closed error for the persistent single-store AUTO state."""


class ControlledAutoRuntimeStateV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["controlled-auto-runtime-state.v1"] = (
        "controlled-auto-runtime-state.v1"
    )
    revision: int = Field(ge=1)
    runtime_mode: Literal["PILOT", "PRODUCTION_AUTO"] = "PILOT"
    production_real_send_enabled: bool = False
    controlled_pilot_send_enabled: bool = False
    controlled_store_auto_enabled: bool = False
    ai_cs_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    policy_mode: Literal[
        "MANUAL_CONFIRM", "AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"
    ] = "MANUAL_CONFIRM"
    policy_revision: int = Field(ge=1)
    whitelist_revision: str = Field(min_length=1, max_length=160)
    kill_switch_enabled: bool = True
    per_message_grant_enforced: Literal[True] = True
    unique_sender_path_enabled: Literal[True] = True
    unknown_automatic_retry_enabled: Literal[False] = False
    changed_by: str = Field(min_length=1, max_length=160)
    changed_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_mode(self) -> ControlledAutoRuntimeStateV1:
        if self.runtime_mode == "PILOT":
            if self.production_real_send_enabled or self.controlled_store_auto_enabled:
                raise ValueError("PILOT cannot enable production or Store AUTO")
        elif (
            not self.production_real_send_enabled
            or not self.controlled_store_auto_enabled
            or self.controlled_pilot_send_enabled
            or not self.ai_cs_store_id
            or not self.platform_store_id
            or self.policy_mode not in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}
            or self.kill_switch_enabled
        ):
            raise ValueError("PRODUCTION_AUTO state is incomplete or unsafe")
        return self


class SendSafetyEvaluationV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["send-safety-evaluation.v1"] = (
        "send-safety-evaluation.v1"
    )
    status: Literal["PASS", "BLOCKED"]
    runtime_mode: Literal["PILOT", "PRODUCTION_AUTO"]
    reason_codes: tuple[str, ...]
    evaluated_at: AwareDatetime


class ControlledAutoRuntimeStateStore:
    """Atomic persistent state; Store AUTO never acts as a send authorization."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS controlled_auto_runtime_state (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                    payload_json TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT payload_json FROM controlled_auto_runtime_state WHERE singleton_id=1"
            ).fetchone()
            if row is None:
                initial = ControlledAutoRuntimeStateV1(
                    revision=1,
                    policy_revision=1,
                    whitelist_revision="initial-disabled",
                    changed_by="system",
                    changed_at=datetime.now(UTC),
                    reason="DEFAULT_FAIL_CLOSED",
                )
                connection.execute(
                    "INSERT INTO controlled_auto_runtime_state(singleton_id,payload_json) "
                    "VALUES(1,?)",
                    (initial.model_dump_json(),),
                )

    def load(self) -> ControlledAutoRuntimeStateV1:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM controlled_auto_runtime_state WHERE singleton_id=1"
            ).fetchone()
        if row is None:
            raise ControlledAutoRuntimeError("controlled AUTO state is unavailable")
        try:
            return ControlledAutoRuntimeStateV1.model_validate_json(row[0])
        except ValueError as exc:
            raise ControlledAutoRuntimeError("controlled AUTO state is invalid") from exc

    def set_pilot(
        self,
        *,
        operator: str,
        reason: str,
        controlled_pilot_send_enabled: bool,
        kill_switch_enabled: bool = False,
        policy_revision: int = 1,
        whitelist_revision: str = "pilot",
        policy_mode: Literal[
            "MANUAL_CONFIRM", "AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"
        ] = "MANUAL_CONFIRM",
    ) -> ControlledAutoRuntimeStateV1:
        return self._replace(
            runtime_mode="PILOT",
            production_real_send_enabled=False,
            controlled_pilot_send_enabled=controlled_pilot_send_enabled,
            controlled_store_auto_enabled=False,
            ai_cs_store_id=None,
            platform_store_id=None,
            policy_mode=policy_mode,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            kill_switch_enabled=kill_switch_enabled,
            changed_by=operator,
            reason=reason,
        )

    def activate_production_auto(
        self,
        *,
        ai_cs_store_id: str,
        platform_store_id: str,
        policy_revision: int,
        whitelist_revision: str,
        operator: str,
        reason: str,
        policy_mode: Literal[
            "AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"
        ] = "AUTO_LOW_RISK",
    ) -> ControlledAutoRuntimeStateV1:
        return self._replace(
            runtime_mode="PRODUCTION_AUTO",
            production_real_send_enabled=True,
            controlled_pilot_send_enabled=False,
            controlled_store_auto_enabled=True,
            ai_cs_store_id=ai_cs_store_id,
            platform_store_id=platform_store_id,
            policy_mode=policy_mode,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            kill_switch_enabled=False,
            changed_by=operator,
            reason=reason,
        )

    def enable_kill_switch(
        self, *, operator: str, reason: str
    ) -> ControlledAutoRuntimeStateV1:
        current = self.load()
        return self._replace(
            runtime_mode="PILOT",
            production_real_send_enabled=False,
            controlled_pilot_send_enabled=False,
            controlled_store_auto_enabled=False,
            ai_cs_store_id=None,
            platform_store_id=None,
            policy_mode="MANUAL_CONFIRM",
            policy_revision=current.policy_revision,
            whitelist_revision=current.whitelist_revision,
            kill_switch_enabled=True,
            changed_by=operator,
            reason=reason,
        )

    def fail_closed_after_terminal(
        self, *, outcome: Literal["FAILED", "UNKNOWN"], reason: str
    ) -> ControlledAutoRuntimeStateV1:
        return self.enable_kill_switch(
            operator="automatic-safety-controller",
            reason=f"{outcome}:{reason}"[:512],
        )

    def _replace(self, **changes: object) -> ControlledAutoRuntimeStateV1:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM controlled_auto_runtime_state WHERE singleton_id=1"
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ControlledAutoRuntimeError("controlled AUTO state disappeared")
            current = ControlledAutoRuntimeStateV1.model_validate_json(row[0])
            candidate = current.model_copy(
                update={
                    **changes,
                    "revision": current.revision + 1,
                    "changed_at": datetime.now(UTC),
                }
            )
            candidate = ControlledAutoRuntimeStateV1.model_validate(
                candidate.model_dump(mode="python")
            )
            connection.execute(
                "UPDATE controlled_auto_runtime_state SET payload_json=? WHERE singleton_id=1",
                (candidate.model_dump_json(),),
            )
            connection.commit()
        return candidate

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0, isolation_level=None)


class ControlledAutoDecisionLedger:
    """Durable no-retry ledger keyed by the immutable customer Decision."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS controlled_auto_decisions (
                    decision_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    terminal_at TEXT,
                    outcome TEXT,
                    receipt_id TEXT
                )
                """
            )

    def claim_once(self, decision_id: str, *, now: datetime) -> bool:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO controlled_auto_decisions"
                    "(decision_id,state,claimed_at) VALUES(?, 'CLAIMED', ?)",
                    (decision_id, now.astimezone(UTC).isoformat()),
                )
                connection.commit()
                return True
            except sqlite3.IntegrityError:
                connection.rollback()
                return False

    def finish(
        self,
        decision_id: str,
        *,
        outcome: Literal["SUCCESS", "FAILED", "UNKNOWN", "BLOCKED"],
        receipt_id: str | None,
        now: datetime,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE controlled_auto_decisions SET state='TERMINAL',"
                "terminal_at=?,outcome=?,receipt_id=? "
                "WHERE decision_id=? AND state='CLAIMED'",
                (
                    now.astimezone(UTC).isoformat(),
                    outcome,
                    receipt_id,
                    decision_id,
                ),
            ).rowcount
            connection.commit()
        if changed != 1:
            raise ControlledAutoRuntimeError("AUTO Decision is not claimable")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0, isolation_level=None)


def evaluate_send_safety(
    state: ControlledAutoRuntimeStateV1,
    *,
    observed_ai_cs_store_id: str | None = None,
    observed_platform_store_id: str | None = None,
    real_execution_attempts: int = 0,
    terminal_receipts: int = 0,
    successful_receipts: int = 0,
    operator_message_ids: int = 0,
    unknown_automatic_retries: int = 0,
    concrete_send_requested: bool = False,
    concrete_send_has_valid_grant: bool = False,
    evaluated_at: datetime | None = None,
) -> SendSafetyEvaluationV1:
    reasons: list[str] = []
    if state.runtime_mode == "PILOT":
        if state.production_real_send_enabled:
            reasons.append("PILOT_PRODUCTION_REAL_SEND_ENABLED")
        if state.controlled_store_auto_enabled:
            reasons.append("PILOT_STORE_AUTO_ENABLED")
    else:
        if not state.production_real_send_enabled:
            reasons.append("PRODUCTION_REAL_SEND_DISABLED")
        if not state.controlled_store_auto_enabled:
            reasons.append("PRODUCTION_STORE_AUTO_DISABLED")
        if state.controlled_pilot_send_enabled:
            reasons.append("PRODUCTION_PILOT_WINDOW_STATE_ENABLED")
        if not state.ai_cs_store_id or not state.platform_store_id:
            reasons.append("PRODUCTION_DOUBLE_STORE_BINDING_MISSING")
        if observed_ai_cs_store_id != state.ai_cs_store_id:
            reasons.append("PRODUCTION_AI_CS_STORE_MISMATCH")
        if observed_platform_store_id != state.platform_store_id:
            reasons.append("PRODUCTION_PLATFORM_STORE_MISMATCH")
        if state.policy_mode not in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}:
            reasons.append("PRODUCTION_POLICY_NOT_AUTO_ENABLED")
        if state.kill_switch_enabled:
            reasons.append("PRODUCTION_KILL_SWITCH_ENABLED")
    if not state.per_message_grant_enforced:
        reasons.append("PER_MESSAGE_GRANT_NOT_ENFORCED")
    if not state.unique_sender_path_enabled:
        reasons.append("UNIQUE_SENDER_PATH_NOT_ENFORCED")
    if state.unknown_automatic_retry_enabled or unknown_automatic_retries:
        reasons.append("UNKNOWN_AUTOMATIC_RETRY_NONZERO")
    if concrete_send_requested and not concrete_send_has_valid_grant:
        reasons.append("CONCRETE_SEND_GRANT_MISSING")
    if real_execution_attempts != terminal_receipts:
        reasons.append("EXECUTION_RECEIPT_RECONCILIATION_FAILED")
    if successful_receipts != operator_message_ids:
        reasons.append("SUCCESS_OPERATOR_MESSAGE_RECONCILIATION_FAILED")
    if successful_receipts > terminal_receipts:
        reasons.append("SUCCESS_RECEIPT_COUNT_INVALID")
    return SendSafetyEvaluationV1(
        status="BLOCKED" if reasons else "PASS",
        runtime_mode=state.runtime_mode,
        reason_codes=tuple(reasons or ("MODE_AND_SEND_FACTS_CONSISTENT",)),
        evaluated_at=(evaluated_at or datetime.now(UTC)).astimezone(UTC),
    )


__all__ = [
    "ControlledAutoDecisionLedger",
    "ControlledAutoRuntimeError",
    "ControlledAutoRuntimeStateStore",
    "ControlledAutoRuntimeStateV1",
    "SendSafetyEvaluationV1",
    "evaluate_send_safety",
]
