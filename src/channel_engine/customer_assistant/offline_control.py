from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .history import ConversationHistoryCandidate, HistorySource
from .models import AIReplyPackage, ConversationHistoryEntry, CustomerContext


class OfflineControlError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class _ClosingConnection(sqlite3.Connection):
    """sqlite3's default context manager commits but does not close on Windows."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class OfflineControlModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ReplyPolicyMode(StrEnum):
    MANUAL_CONFIRM = "MANUAL_CONFIRM"
    AUTO_LOW_RISK = "AUTO_LOW_RISK"


class QualityGateStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class AuthorizationKind(StrEnum):
    HUMAN = "HUMAN"
    AUTO_POLICY = "AUTO_POLICY"


class PreparationState(StrEnum):
    READY = "READY"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class PipelineStage(StrEnum):
    PROVIDER_READ = "PROVIDER_READ"
    EDGE_SPOOL = "EDGE_SPOOL"
    HOST_PERSIST = "HOST_PERSIST"
    BUFFERING = "BUFFERING"
    CUSTOMER_CONTEXT = "CUSTOMER_CONTEXT"
    AI_GENERATING = "AI_GENERATING"
    QUALITY_GATE = "QUALITY_GATE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTION_PREPARED = "EXECUTION_PREPARED"
    RECEIPT = "RECEIPT"


class PipelineStageState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING_HUMAN = "WAITING_HUMAN"


class ReceiptKind(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    REAL = "REAL"


class TransportKind(StrEnum):
    SYNTHETIC_PDD = "SYNTHETIC_PDD"
    REAL_PDD = "REAL_PDD"


class ReplyPolicy(OfflineControlModel):
    store_id: str = Field(min_length=1, max_length=160)
    mode: ReplyPolicyMode = ReplyPolicyMode.MANUAL_CONFIRM
    revision: int = Field(ge=1)
    updated_by: str = Field(min_length=1, max_length=160)
    updated_at: AwareDatetime


class QualityGateResult(OfflineControlModel):
    decision_id: str = Field(min_length=1, max_length=160)
    status: QualityGateStatus
    reason_codes: tuple[str, ...] = Field(max_length=32)
    checked_at: AwareDatetime


class ExecutionPreparation(OfflineControlModel):
    preparation_version: Literal["1.0"] = "1.0"
    preparation_id: str = Field(pattern=r"^execution-preparation:[a-f0-9]{64}$")
    decision_id: str = Field(min_length=1, max_length=160)
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_revision: int = Field(ge=1)
    policy_mode: ReplyPolicyMode
    policy_revision: int = Field(ge=1)
    authorization_kind: AuthorizationKind
    authorized_by: str = Field(min_length=1, max_length=160)
    state: PreparationState
    prepared_at: AwareDatetime
    expires_at: AwareDatetime
    real_send_enabled: Literal[False] = False
    external_side_effect: Literal[False] = False


class PipelineTraceStep(OfflineControlModel):
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    stage: PipelineStage
    state: PipelineStageState
    reason_code: str = Field(min_length=1, max_length=128)
    started_at: AwareDatetime
    updated_at: AwareDatetime
    duration_ms: float = Field(ge=0)


class OfflineReceipt(OfflineControlModel):
    receipt_id: str = Field(min_length=1, max_length=160)
    execution_id: str = Field(min_length=1, max_length=160)
    receipt_kind: ReceiptKind
    transport_kind: TransportKind
    environment: Literal["SIMULATOR", "OFFLINE_REPLAY", "PRODUCTION"]
    outcome: Literal["SUCCESS", "FAILED", "UNKNOWN"]
    external_side_effect: bool
    customer_message_sent: bool | None
    adapter_identity: str | None = Field(default=None, max_length=160)
    activation_evidence: str | None = Field(default=None, max_length=512)
    external_reference: str | None = Field(default=None, max_length=256)
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def isolate_synthetic_and_real_receipts(self) -> "OfflineReceipt":
        if self.receipt_kind is ReceiptKind.SYNTHETIC:
            if self.transport_kind is not TransportKind.SYNTHETIC_PDD:
                raise ValueError("synthetic receipt requires synthetic transport")
            if self.environment not in {"SIMULATOR", "OFFLINE_REPLAY"}:
                raise ValueError("synthetic receipt cannot claim production environment")
            if self.external_side_effect or self.customer_message_sent is not False:
                raise ValueError("synthetic receipt cannot claim a real customer side effect")
            if any(
                value is not None
                for value in (
                    self.adapter_identity,
                    self.activation_evidence,
                    self.external_reference,
                )
            ):
                raise ValueError("synthetic receipt cannot carry real transport evidence")
        else:
            if self.transport_kind is not TransportKind.REAL_PDD:
                raise ValueError("real receipt requires real PDD transport")
            if self.environment != "PRODUCTION":
                raise ValueError("real receipt requires production environment")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (
                    self.adapter_identity,
                    self.activation_evidence,
                    self.external_reference,
                )
            ):
                raise ValueError("real receipt requires adapter, activation and external evidence")
        return self


class ReplyControlOutcome(OfflineControlModel):
    policy: ReplyPolicy
    quality: QualityGateResult
    preparation: ExecutionPreparation | None
    waiting_for_human: bool


class ReplyQualityGate:
    """Deterministic post-generation gate; it never asks another model to judge."""

    _FAILURE_WARNINGS = frozenset(
        {
            "RAG_RUNTIME_ERROR",
            "LLM_REQUEST_FAILED",
            "MODEL_NOT_CONFIGURED",
            "KNOWLEDGE_NOT_PUBLISHED",
        }
    )

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def evaluate(
        self, context: CustomerContext, package: AIReplyPackage
    ) -> QualityGateResult:
        reasons: list[str] = []
        if package.action != "SUGGEST_REPLY" or not package.reply_content:
            reasons.append("NO_ACTIONABLE_REPLY")
        if package.store_id != context.store_id or package.conversation_id != context.conversation_id:
            reasons.append("CONTEXT_SCOPE_MISMATCH")
        if package.customer_reference != context.customer_reference:
            reasons.append("CUSTOMER_SCOPE_MISMATCH")
        if set(package.warnings) & self._FAILURE_WARNINGS:
            reasons.append("AI_CAPABILITY_UNAVAILABLE")
        if package.ai_cs_action in {"REFUSE", "TRANSFER_HUMAN", "REQUIRE_LOOKUP"}:
            reasons.append("AI_ACTION_REQUIRES_HUMAN")
        if package.reply_content and any(
            marker in package.reply_content.casefold()
            for marker in ("traceback", "internal server error", "system prompt")
        ):
            reasons.append("UNSAFE_REPLY_CONTENT")
        return QualityGateResult(
            decision_id=package.decision_id,
            status=(QualityGateStatus.BLOCKED if reasons else QualityGateStatus.PASS),
            reason_codes=tuple(sorted(set(reasons))) or ("QUALITY_PASS",),
            checked_at=self._clock().astimezone(UTC),
        )


class OfflineReplyControlStore:
    """Durable offline policy, preparation, trace and receipt authority."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime],
        preparation_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if preparation_ttl <= timedelta(0):
            raise ValueError("execution preparation TTL must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._ttl = preparation_ttl
        self._quality = ReplyQualityGate(clock=clock)
        self._lock = RLock()
        self._initialize()

    def policy(self, store_id: str) -> ReplyPolicy:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT mode,revision,updated_by,updated_at FROM reply_policies WHERE store_id=?",
                (store_id,),
            ).fetchone()
        if row is None:
            return ReplyPolicy(
                store_id=store_id,
                mode=ReplyPolicyMode.MANUAL_CONFIRM,
                revision=1,
                updated_by="system:default",
                updated_at=self._clock().astimezone(UTC),
            )
        return ReplyPolicy(
            store_id=store_id,
            mode=ReplyPolicyMode(row[0]),
            revision=int(row[1]),
            updated_by=row[2],
            updated_at=datetime.fromisoformat(row[3]),
        )

    def set_policy(
        self,
        store_id: str,
        mode: ReplyPolicyMode,
        *,
        authorized_by: str,
        expected_revision: int | None = None,
    ) -> ReplyPolicy:
        if not authorized_by.strip():
            raise OfflineControlError(
                "reply policy change requires an authenticated principal",
                error_code="REPLY_POLICY_AUTHORIZATION_REQUIRED",
            )
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT mode,revision FROM reply_policies WHERE store_id=?",
                (store_id,),
            ).fetchone()
            current_revision = int(existing[1]) if existing else 1
            if expected_revision is not None and expected_revision != current_revision:
                connection.rollback()
                raise OfflineControlError(
                    "reply policy revision changed",
                    error_code="REPLY_POLICY_REVISION_CONFLICT",
                )
            next_revision = current_revision + (0 if existing and existing[0] == mode.value else 1)
            connection.execute(
                """
                INSERT INTO reply_policies(store_id,mode,revision,updated_by,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(store_id) DO UPDATE SET
                    mode=excluded.mode,revision=excluded.revision,
                    updated_by=excluded.updated_by,updated_at=excluded.updated_at
                """,
                (store_id, mode.value, next_revision, authorized_by.strip(), now.isoformat()),
            )
            connection.execute(
                "INSERT INTO reply_policy_audit(store_id,mode,revision,principal,changed_at) VALUES(?,?,?,?,?)",
                (store_id, mode.value, next_revision, authorized_by.strip(), now.isoformat()),
            )
            connection.commit()
        return ReplyPolicy(
            store_id=store_id,
            mode=mode,
            revision=next_revision,
            updated_by=authorized_by.strip(),
            updated_at=now,
        )

    def register_observation(
        self,
        *,
        observation_id: str,
        store_id: str,
        conversation_id: str,
        trace_id: str,
    ) -> int:
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_observation = connection.execute(
                "SELECT revision FROM offline_observation_revisions WHERE observation_id=?",
                (observation_id,),
            ).fetchone()
            if existing_observation is not None:
                connection.commit()
                return int(existing_observation[0])
            row = connection.execute(
                "SELECT revision FROM conversation_revisions WHERE store_id=? AND conversation_id=?",
                (store_id, conversation_id),
            ).fetchone()
            revision = (int(row[0]) if row else 0) + 1
            connection.execute(
                """
                INSERT INTO conversation_revisions(store_id,conversation_id,revision,updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(store_id,conversation_id) DO UPDATE SET
                    revision=excluded.revision,updated_at=excluded.updated_at
                """,
                (store_id, conversation_id, revision, now.isoformat()),
            )
            connection.execute(
                "INSERT INTO offline_observation_revisions(observation_id,trace_id,store_id,conversation_id,revision,created_at) VALUES(?,?,?,?,?,?)",
                (
                    observation_id,
                    trace_id,
                    store_id,
                    conversation_id,
                    revision,
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE execution_preparations
                SET state='INVALIDATED', invalidation_reason='NEW_CUSTOMER_MESSAGE', updated_at=?
                WHERE store_id=? AND conversation_id=? AND state='READY'
                """,
                (now.isoformat(), store_id, conversation_id),
            )
            connection.commit()
        self.record_trace(
            trace_id,
            PipelineStage.BUFFERING,
            PipelineStageState.RUNNING,
            "BUFFER_ACCEPTED",
        )
        return revision

    def register_reply(
        self,
        context: CustomerContext,
        package: AIReplyPackage,
        *,
        trace_id: str,
    ) -> ReplyControlOutcome:
        quality = self._quality.evaluate(context, package)
        policy = self.policy(package.store_id)
        revision = self._conversation_revision(package.store_id, package.conversation_id)
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO offline_reply_decisions(
                    decision_id,trace_id,store_id,conversation_id,customer_reference,
                    conversation_revision,policy_mode,policy_revision,quality_status,
                    quality_reasons,context_json,package_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(decision_id) DO NOTHING
                """,
                (
                    package.decision_id,
                    trace_id,
                    package.store_id,
                    package.conversation_id,
                    package.customer_reference,
                    revision,
                    policy.mode.value,
                    policy.revision,
                    quality.status.value,
                    json.dumps(list(quality.reason_codes), separators=(",", ":")),
                    context.model_dump_json(),
                    package.model_dump_json(),
                    now.isoformat(),
                ),
            )
        self.record_trace(
            trace_id,
            PipelineStage.QUALITY_GATE,
            (
                PipelineStageState.SUCCEEDED
                if quality.status is QualityGateStatus.PASS
                else PipelineStageState.FAILED
            ),
            quality.reason_codes[0],
        )
        preparation = None
        if self._auto_eligible(context, package, quality, policy):
            preparation = self.prepare(
                package.decision_id,
                authorization_kind=AuthorizationKind.AUTO_POLICY,
                authorized_by=f"policy:{policy.store_id}:r{policy.revision}",
            )
        elif quality.status is QualityGateStatus.PASS:
            self.record_trace(
                trace_id,
                PipelineStage.WAITING_CONFIRMATION,
                PipelineStageState.WAITING_HUMAN,
                "MANUAL_CONFIRM_REQUIRED",
            )
        return ReplyControlOutcome(
            policy=policy,
            quality=quality,
            preparation=preparation,
            waiting_for_human=preparation is None and quality.status is QualityGateStatus.PASS,
        )

    def prepare(
        self,
        decision_id: str,
        *,
        authorization_kind: AuthorizationKind,
        authorized_by: str,
        expected_store_id: str | None = None,
        expected_conversation_id: str | None = None,
        expected_customer_reference: str | None = None,
    ) -> ExecutionPreparation:
        if not authorized_by.strip():
            raise OfflineControlError(
                "execution preparation requires authorization",
                error_code="EXECUTION_PREPARATION_AUTHORIZATION_REQUIRED",
            )
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire_ready(connection, now)
            row = connection.execute(
                """
                SELECT trace_id,store_id,conversation_id,customer_reference,
                       conversation_revision,policy_mode,policy_revision,quality_status
                FROM offline_reply_decisions WHERE decision_id=?
                """,
                (decision_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise OfflineControlError(
                    "reply decision is unavailable",
                    error_code="OFFLINE_REPLY_DECISION_NOT_FOUND",
                )
            trace_id, store_id, conversation_id, customer_reference = row[:4]
            revision, policy_mode, policy_revision, quality_status = row[4:]
            if quality_status != QualityGateStatus.PASS.value:
                connection.rollback()
                raise OfflineControlError(
                    "quality-blocked reply cannot be prepared",
                    error_code="EXECUTION_PREPARATION_QUALITY_BLOCKED",
                )
            if any(
                expected is not None and expected != actual
                for expected, actual in (
                    (expected_store_id, store_id),
                    (expected_conversation_id, conversation_id),
                    (expected_customer_reference, customer_reference),
                )
            ):
                connection.rollback()
                raise OfflineControlError(
                    "execution preparation target does not match the decision",
                    error_code="EXECUTION_PREPARATION_TARGET_MISMATCH",
                )
            current_revision = connection.execute(
                "SELECT revision FROM conversation_revisions WHERE store_id=? AND conversation_id=?",
                (store_id, conversation_id),
            ).fetchone()
            if current_revision is None or int(current_revision[0]) != int(revision):
                connection.rollback()
                raise OfflineControlError(
                    "conversation changed after reply generation",
                    error_code="EXECUTION_PREPARATION_REVISION_STALE",
                )
            if authorization_kind is AuthorizationKind.AUTO_POLICY and policy_mode != ReplyPolicyMode.AUTO_LOW_RISK.value:
                connection.rollback()
                raise OfflineControlError(
                    "decision policy snapshot does not permit automatic preparation",
                    error_code="AUTO_LOW_RISK_POLICY_NOT_ACTIVE",
                )
            identity = json.dumps(
                [decision_id, authorization_kind.value, revision],
                separators=(",", ":"),
            )
            preparation_id = "execution-preparation:" + hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()
            existing = connection.execute(
                "SELECT preparation_json FROM execution_preparations WHERE preparation_id=?",
                (preparation_id,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return ExecutionPreparation.model_validate_json(existing[0])
            prepared = ExecutionPreparation(
                preparation_id=preparation_id,
                decision_id=decision_id,
                trace_id=trace_id,
                store_id=store_id,
                conversation_id=conversation_id,
                customer_reference=customer_reference,
                conversation_revision=int(revision),
                policy_mode=ReplyPolicyMode(policy_mode),
                policy_revision=int(policy_revision),
                authorization_kind=authorization_kind,
                authorized_by=authorized_by.strip(),
                state=PreparationState.READY,
                prepared_at=now,
                expires_at=now + self._ttl,
            )
            connection.execute(
                """
                INSERT INTO execution_preparations(
                    preparation_id,decision_id,trace_id,store_id,conversation_id,
                    state,invalidation_reason,preparation_json,prepared_at,expires_at,updated_at
                ) VALUES(?,?,?,?,?,'READY',NULL,?,?,?,?)
                """,
                (
                    preparation_id,
                    decision_id,
                    trace_id,
                    store_id,
                    conversation_id,
                    prepared.model_dump_json(),
                    now.isoformat(),
                    prepared.expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.commit()
        self.record_trace(
            trace_id,
            PipelineStage.EXECUTION_PREPARED,
            PipelineStageState.SUCCEEDED,
            "REAL_SEND_BLOCKED",
        )
        return prepared

    def preparation(self, decision_id: str) -> ExecutionPreparation | None:
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            self._expire_ready(connection, now)
            row = connection.execute(
                """
                SELECT preparation_json,state FROM execution_preparations
                WHERE decision_id=? ORDER BY prepared_at DESC LIMIT 1
                """,
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        value = ExecutionPreparation.model_validate_json(row[0])
        return value.model_copy(update={"state": PreparationState(row[1])})

    def reply_outcome(self, decision_id: str) -> ReplyControlOutcome | None:
        """Read the immutable decision snapshot without re-evaluating policy."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT store_id,policy_mode,policy_revision,quality_status,
                       quality_reasons,created_at
                FROM offline_reply_decisions WHERE decision_id=?
                """,
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        store_id, policy_mode, policy_revision, quality_status, reasons, created_at = row
        preparation = self.preparation(decision_id)
        quality = QualityGateResult(
            decision_id=decision_id,
            status=QualityGateStatus(quality_status),
            reason_codes=tuple(json.loads(reasons)),
            checked_at=datetime.fromisoformat(created_at),
        )
        policy = ReplyPolicy(
            store_id=store_id,
            mode=ReplyPolicyMode(policy_mode),
            revision=int(policy_revision),
            updated_by=f"decision-snapshot:{decision_id}",
            updated_at=datetime.fromisoformat(created_at),
        )
        return ReplyControlOutcome(
            policy=policy,
            quality=quality,
            preparation=preparation,
            waiting_for_human=(
                preparation is None and quality.status is QualityGateStatus.PASS
            ),
        )

    def authorized_history_candidates(
        self,
        *,
        store_id: str,
        conversation_id: str,
    ) -> tuple[ConversationHistoryCandidate, ...]:
        """Project only quality-passed, explicitly authorized replies as history."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.decision_id,d.package_json,p.preparation_json,p.prepared_at
                FROM offline_reply_decisions AS d
                JOIN execution_preparations AS p ON p.decision_id=d.decision_id
                WHERE d.store_id=? AND d.conversation_id=? AND d.quality_status='PASS'
                ORDER BY p.prepared_at,d.decision_id
                """,
                (store_id, conversation_id),
            ).fetchall()
        values: list[ConversationHistoryCandidate] = []
        for decision_id, package_json, preparation_json, prepared_at in rows:
            package = AIReplyPackage.model_validate_json(package_json)
            preparation = ExecutionPreparation.model_validate_json(preparation_json)
            if not package.reply_content:
                continue
            source = (
                HistorySource.HUMAN
                if preparation.authorization_kind is AuthorizationKind.HUMAN
                else HistorySource.AUTO_POLICY
            )
            digest = hashlib.sha256(package.reply_content.encode("utf-8")).hexdigest()
            values.append(
                ConversationHistoryCandidate(
                    entry=ConversationHistoryEntry(
                        store_id=store_id,
                        conversation_id=conversation_id,
                        external_message_id=f"authorized-reply:{decision_id}",
                        sender="operator",
                        content=package.reply_content,
                        timestamp=datetime.fromisoformat(prepared_at),
                        content_digest=digest,
                    ),
                    source=source,
                    logical_key=f"decision:{decision_id}",
                    decision_id=decision_id,
                )
            )
        return tuple(values)

    def conversation_revision(self, store_id: str, conversation_id: str) -> int:
        return self._conversation_revision(store_id, conversation_id)

    def record_history_audit(self, trace_id: str, audit: dict[str, object]) -> None:
        """Persist content-free acceptance evidence for the exact AI input history."""

        payload = json.dumps(
            audit,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        now = self._clock().astimezone(UTC).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO context_history_audits(trace_id,audit_json,created_at)
                VALUES(?,?,?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    audit_json=excluded.audit_json,created_at=excluded.created_at
                """,
                (trace_id, payload, now),
            )

    def history_audit(self, trace_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT audit_json FROM context_history_audits WHERE trace_id=?",
                (trace_id,),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def record_trace(
        self,
        trace_id: str,
        stage: PipelineStage,
        state: PipelineStageState,
        reason_code: str,
    ) -> PipelineTraceStep:
        if not reason_code.strip() or len(reason_code) > 128:
            raise ValueError("trace reason code is invalid")
        now = self._clock().astimezone(UTC)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT started_at FROM pipeline_trace_steps WHERE trace_id=? AND stage=?",
                (trace_id, stage.value),
            ).fetchone()
            started = datetime.fromisoformat(row[0]) if row else now
            duration_ms = max(0.0, (now - started).total_seconds() * 1000)
            connection.execute(
                """
                INSERT INTO pipeline_trace_steps(
                    trace_id,stage,state,reason_code,started_at,updated_at,duration_ms
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(trace_id,stage) DO UPDATE SET
                    state=excluded.state,reason_code=excluded.reason_code,
                    updated_at=excluded.updated_at,duration_ms=excluded.duration_ms
                """,
                (
                    trace_id,
                    stage.value,
                    state.value,
                    reason_code.strip(),
                    started.isoformat(),
                    now.isoformat(),
                    duration_ms,
                ),
            )
        return PipelineTraceStep(
            trace_id=trace_id,
            stage=stage,
            state=state,
            reason_code=reason_code.strip(),
            started_at=started,
            updated_at=now,
            duration_ms=duration_ms,
        )

    def trace(self, trace_id: str) -> tuple[PipelineTraceStep, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT stage,state,reason_code,started_at,updated_at,duration_ms
                FROM pipeline_trace_steps WHERE trace_id=? ORDER BY rowid
                """,
                (trace_id,),
            ).fetchall()
        return tuple(
            PipelineTraceStep(
                trace_id=trace_id,
                stage=PipelineStage(row[0]),
                state=PipelineStageState(row[1]),
                reason_code=row[2],
                started_at=datetime.fromisoformat(row[3]),
                updated_at=datetime.fromisoformat(row[4]),
                duration_ms=float(row[5]),
            )
            for row in rows
        )

    def record_receipt(self, receipt: OfflineReceipt) -> OfflineReceipt:
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT receipt_json FROM offline_receipts WHERE receipt_id=?",
                (receipt.receipt_id,),
            ).fetchone()
            serialized = receipt.model_dump_json()
            if existing is not None and existing[0] != serialized:
                raise OfflineControlError(
                    "immutable offline receipt conflicts with persisted evidence",
                    error_code="OFFLINE_RECEIPT_CONFLICT",
                )
            connection.execute(
                "INSERT OR IGNORE INTO offline_receipts(receipt_id,receipt_kind,outcome,receipt_json,recorded_at) VALUES(?,?,?,?,?)",
                (
                    receipt.receipt_id,
                    receipt.receipt_kind.value,
                    receipt.outcome,
                    serialized,
                    receipt.recorded_at.isoformat(),
                ),
            )
        return receipt

    def real_success_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM offline_receipts WHERE receipt_kind='REAL' AND outcome='SUCCESS'"
            ).fetchone()
        return int(row[0])

    def purge_expired_content(self, *, retention: timedelta = timedelta(hours=24)) -> int:
        cutoff = self._clock().astimezone(UTC) - retention
        with self._lock, self._connect() as connection:
            changed = connection.execute(
                "DELETE FROM pipeline_trace_steps WHERE updated_at<=?",
                (cutoff.isoformat(),),
            ).rowcount
        return int(changed or 0)

    def _auto_eligible(
        self,
        context: CustomerContext,
        package: AIReplyPackage,
        quality: QualityGateResult,
        policy: ReplyPolicy,
    ) -> bool:
        if (
            policy.mode is not ReplyPolicyMode.AUTO_LOW_RISK
            or quality.status is not QualityGateStatus.PASS
            or package.ai_cs_action != "DIRECT_ANSWER"
            or package.risk_level.value != "LOW"
            or package.required_fields
        ):
            return False
        product_id = context.page.product.product_reference
        sku_id = context.page.product.sku_reference
        return any(
            citation.product_id == product_id
            and (sku_id is None or citation.sku_id in {None, sku_id})
            for citation in package.citations
        )

    def _conversation_revision(self, store_id: str, conversation_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision FROM conversation_revisions WHERE store_id=? AND conversation_id=?",
                (store_id, conversation_id),
            ).fetchone()
        return int(row[0]) if row else 1

    @staticmethod
    def _expire_ready(connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            """
            UPDATE execution_preparations
            SET state='EXPIRED',invalidation_reason='PREPARATION_TTL_EXPIRED',updated_at=?
            WHERE state='READY' AND expires_at<=?
            """,
            (now.isoformat(), now.isoformat()),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=5.0, factory=_ClosingConnection
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reply_policies(
                    store_id TEXT PRIMARY KEY, mode TEXT NOT NULL, revision INTEGER NOT NULL,
                    updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reply_policy_audit(
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT, store_id TEXT NOT NULL,
                    mode TEXT NOT NULL, revision INTEGER NOT NULL, principal TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_revisions(
                    store_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(store_id,conversation_id)
                );
                CREATE TABLE IF NOT EXISTS offline_observation_revisions(
                    observation_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL,
                    store_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS offline_reply_decisions(
                    decision_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, store_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, customer_reference TEXT NOT NULL,
                    conversation_revision INTEGER NOT NULL, policy_mode TEXT NOT NULL,
                    policy_revision INTEGER NOT NULL, quality_status TEXT NOT NULL,
                    quality_reasons TEXT NOT NULL, context_json TEXT NOT NULL,
                    package_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_preparations(
                    preparation_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL UNIQUE,
                    trace_id TEXT NOT NULL, store_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    state TEXT NOT NULL, invalidation_reason TEXT, preparation_json TEXT NOT NULL,
                    prepared_at TEXT NOT NULL, expires_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_execution_preparation_scope
                    ON execution_preparations(store_id,conversation_id,state);
                CREATE TABLE IF NOT EXISTS pipeline_trace_steps(
                    trace_id TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL,
                    reason_code TEXT NOT NULL, started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL, PRIMARY KEY(trace_id,stage)
                );
                CREATE TABLE IF NOT EXISTS offline_receipts(
                    receipt_id TEXT PRIMARY KEY, receipt_kind TEXT NOT NULL,
                    outcome TEXT NOT NULL, receipt_json TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS context_history_audits(
                    trace_id TEXT PRIMARY KEY, audit_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )


__all__ = [
    "AuthorizationKind",
    "ExecutionPreparation",
    "OfflineControlError",
    "OfflineReceipt",
    "OfflineReplyControlStore",
    "PipelineStage",
    "PipelineStageState",
    "PipelineTraceStep",
    "PreparationState",
    "QualityGateResult",
    "QualityGateStatus",
    "ReceiptKind",
    "ReplyControlOutcome",
    "ReplyPolicy",
    "ReplyPolicyMode",
    "ReplyQualityGate",
    "TransportKind",
]
