from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from channel_engine.control.gate import (
    AllowExecutionControlGate,
    ExecutionControlBlocked,
    ExecutionControlGate,
)
from channel_engine.control.models import KillSwitchState
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork
from channel_engine.storage.orm import (
    PDDExecutionStoreBindingRow,
    PDDProductionSafetyStateRow,
    PDDSafetyAuditEventRow,
    PDDSendRateEventRow,
    PDDSendTransportReceiptRow,
    PDDStoreAccountRow,
)

from .pdd_send import (
    PDDApprovedExecutionContext,
    PDDSendGateDecision,
    PDDSendIdempotencyConflict,
    PDDSendReceiptRecord,
    PDDSendReceiptStore,
    PDDSendSafetyError,
    PDDSendSession,
)
from .platform import AuthorizedOutboundMessage
from .protocol import ChannelSendReceipt


PDD_PRODUCTION_SAFETY_VERSION = "1.0"
PDD_PRODUCTION_CONFIRMATION_PHRASE = "ENABLE_PDD_PRODUCTION_SAFETY_V1"
PDD_SAFETY_SINGLETON_ID = "pdd-production-safety"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _contains_sensitive_material(value: object) -> bool:
    forbidden_keys = ("cookie", "token", "password", "secret", "authorization")
    forbidden_values = (
        "cookie=",
        "token=",
        "password=",
        "secret=",
        "bearer ",
        "set-cookie",
    )
    if isinstance(value, Mapping):
        return any(
            any(marker in str(key).casefold() for marker in forbidden_keys)
            or _contains_sensitive_material(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_sensitive_material(item) for item in value)
    if isinstance(value, str):
        normalized = value.casefold()
        return any(marker in normalized for marker in forbidden_values)
    return False


class PDDSafetyModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDEnvironmentProfile(StrEnum):
    MOCK = "MOCK"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class PDDStoreStatus(StrEnum):
    ALLOWLISTED = "ALLOWLISTED"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class PDDSafetyAuditAction(StrEnum):
    PRODUCTION_ENABLED = "PRODUCTION_ENABLED"
    PRODUCTION_DISABLED = "PRODUCTION_DISABLED"
    STORE_ALLOWLISTED = "STORE_ALLOWLISTED"
    STORE_STATUS_CHANGED = "STORE_STATUS_CHANGED"
    CREDENTIAL_CHANGED = "CREDENTIAL_CHANGED"
    EXECUTION_STORE_BOUND = "EXECUTION_STORE_BOUND"
    SEND_AUTHORIZED = "SEND_AUTHORIZED"
    SEND_BLOCKED = "SEND_BLOCKED"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    KILL_SWITCH_DISABLED = "KILL_SWITCH_DISABLED"


class PDDCredentialReference(PDDSafetyModel):
    """Opaque locator only; there is intentionally no cookie/token/secret field."""

    credential_ref: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )
    expires_at: AwareDatetime | None = None


class StoreAccount(PDDSafetyModel):
    safety_contract_version: Literal["1.0"] = PDD_PRODUCTION_SAFETY_VERSION
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    store_name: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    credential_reference: PDDCredentialReference
    environment: PDDEnvironmentProfile
    status: PDDStoreStatus
    updated_at: AwareDatetime


class PDDRateLimitPolicy(PDDSafetyModel):
    store_per_minute: int = Field(default=2, ge=1, le=60)
    conversation_per_minute: int = Field(default=1, ge=1, le=20)
    store_per_day: int = Field(default=20, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_limits(self) -> PDDRateLimitPolicy:
        if self.conversation_per_minute > self.store_per_minute:
            raise ValueError("conversation rate cannot exceed store rate")
        if self.store_per_minute > self.store_per_day:
            raise ValueError("minute rate cannot exceed daily rate")
        return self


class PDDProductionSafetyState(PDDSafetyModel):
    safety_contract_version: Literal["1.0"] = PDD_PRODUCTION_SAFETY_VERSION
    revision: int = Field(ge=0)
    environment: PDDEnvironmentProfile = PDDEnvironmentProfile.MOCK
    production_enabled: bool = False
    dry_run: bool = True
    kill_switch: KillSwitchState = KillSwitchState.DISABLED
    rate_limit: PDDRateLimitPolicy = PDDRateLimitPolicy()
    updated_at: AwareDatetime
    updated_by: str = Field(min_length=1, max_length=160)
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )

    @model_validator(mode="after")
    def validate_environment(self) -> PDDProductionSafetyState:
        if self.environment is not PDDEnvironmentProfile.PRODUCTION:
            if self.production_enabled:
                raise ValueError("non-production environment cannot be enabled")
            if not self.dry_run:
                raise ValueError("non-production environment must remain dry-run")
        return self


class PDDExecutionStoreBinding(PDDSafetyModel):
    execution_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    bound_at: AwareDatetime
    bound_by: str = Field(min_length=1, max_length=160)


class PDDSafetyAuditEvent(PDDSafetyModel):
    safety_contract_version: Literal["1.0"] = PDD_PRODUCTION_SAFETY_VERSION
    audit_event_id: str = Field(min_length=1, max_length=128)
    operator: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$",
    )
    action: PDDSafetyAuditAction
    timestamp: AwareDatetime
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )
    store_id: str | None = Field(default=None, max_length=128)
    execution_id: str | None = Field(default=None, max_length=128)
    before: dict[str, object] = Field(default_factory=dict)
    after: dict[str, object] = Field(default_factory=dict)

    @field_validator("operator", "reason", "store_id", "execution_id")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is not None and _contains_sensitive_material(value):
            raise ValueError("PDD safety audit contains sensitive material")
        return value

    @model_validator(mode="after")
    def validate_snapshots(self) -> PDDSafetyAuditEvent:
        if _contains_sensitive_material(self.before) or _contains_sensitive_material(
            self.after
        ):
            raise ValueError("PDD safety audit snapshots contain sensitive material")
        return self


class PDDProductionSafetyDenied(PDDSendSafetyError):
    pass


class PDDRateLimitReviewRequired(PDDProductionSafetyDenied):
    pass


class PDDExecutionControlBlocked(ExecutionControlBlocked):
    error_code = "PDD_KILL_SWITCH_ENABLED"


class KillSwitchStatusProvider(Protocol):
    def kill_switch_status(self): ...  # type: ignore[no-untyped-def]


class PDDProductionSafetyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create_state(self, now: datetime) -> PDDProductionSafetyState:
        row = self._session.get(PDDProductionSafetyStateRow, PDD_SAFETY_SINGLETON_ID)
        if row is None:
            state = PDDProductionSafetyState(
                revision=0,
                updated_at=now,
                updated_by="system",
                reason="PDD_SAFETY_DEFAULT_MOCK",
            )
            self._session.add(self._state_row(state))
            self._session.flush()
            return state
        self._assert_version(row.safety_contract_version)
        return self._state_from_row(row)

    def save_state(
        self,
        current: PDDProductionSafetyState,
        updated: PDDProductionSafetyState,
    ) -> None:
        result = self._session.execute(
            update(PDDProductionSafetyStateRow)
            .where(
                PDDProductionSafetyStateRow.singleton_id
                == PDD_SAFETY_SINGLETON_ID,
                PDDProductionSafetyStateRow.revision == current.revision,
            )
            .values(**self._state_values(updated))
        )
        if result.rowcount != 1:
            raise PDDProductionSafetyDenied(
                "PDD safety state changed concurrently",
                error_code="PDD_SAFETY_STATE_CONFLICT",
            )

    def upsert_store(self, account: StoreAccount) -> None:
        row = self._session.get(PDDStoreAccountRow, account.store_id)
        values = self._store_values(account)
        if row is None:
            self._session.add(PDDStoreAccountRow(store_id=account.store_id, **values))
        else:
            self._assert_version(row.safety_contract_version)
            for key, value in values.items():
                setattr(row, key, value)
        self._session.flush()

    def get_store(self, store_id: str) -> StoreAccount | None:
        row = self._session.get(PDDStoreAccountRow, store_id)
        if row is None:
            return None
        self._assert_version(row.safety_contract_version)
        return self._store_from_row(row)

    def save_binding(self, binding: PDDExecutionStoreBinding) -> None:
        existing = self._session.get(
            PDDExecutionStoreBindingRow,
            binding.execution_id,
        )
        if existing is not None:
            self._assert_version(existing.safety_contract_version)
            if (
                existing.store_id != binding.store_id
                or existing.conversation_id != binding.conversation_id
            ):
                raise PDDProductionSafetyDenied(
                    "Execution is already bound to another store or conversation",
                    error_code="PDD_EXECUTION_STORE_BINDING_CONFLICT",
                )
            return
        self._session.add(
            PDDExecutionStoreBindingRow(
                execution_id=binding.execution_id,
                safety_contract_version=PDD_PRODUCTION_SAFETY_VERSION,
                store_id=binding.store_id,
                conversation_id=binding.conversation_id,
                bound_at=binding.bound_at,
                bound_by=binding.bound_by,
            )
        )
        self._session.flush()

    def get_binding(self, execution_id: str) -> PDDExecutionStoreBinding | None:
        row = self._session.get(PDDExecutionStoreBindingRow, execution_id)
        if row is None:
            return None
        self._assert_version(row.safety_contract_version)
        return PDDExecutionStoreBinding(
            execution_id=row.execution_id,
            store_id=row.store_id,
            conversation_id=row.conversation_id,
            bound_at=_as_utc(row.bound_at),
            bound_by=row.bound_by,
        )

    def append_audit(self, event: PDDSafetyAuditEvent) -> None:
        self._session.add(
            PDDSafetyAuditEventRow(
                audit_event_id=event.audit_event_id,
                safety_contract_version=PDD_PRODUCTION_SAFETY_VERSION,
                operator=event.operator,
                action=event.action.value,
                timestamp=event.timestamp,
                reason=event.reason,
                store_id=event.store_id,
                execution_id=event.execution_id,
                before=event.before,
                after=event.after,
            )
        )

    def list_audits(self, limit: int = 100) -> list[PDDSafetyAuditEvent]:
        if limit < 1:
            raise ValueError("audit limit must be positive")
        rows = self._session.scalars(
            select(PDDSafetyAuditEventRow)
            .order_by(
                PDDSafetyAuditEventRow.timestamp,
                PDDSafetyAuditEventRow.audit_event_id,
            )
            .limit(limit)
        ).all()
        return [self._audit_from_row(row) for row in rows]

    def reserve_rate(
        self,
        *,
        execution_id: str,
        store_id: str,
        conversation_id: str,
        policy: PDDRateLimitPolicy,
        now: datetime,
    ) -> tuple[bool, str | None]:
        existing = self._session.scalar(
            select(PDDSendRateEventRow).where(
                PDDSendRateEventRow.execution_id == execution_id
            )
        )
        if existing is not None:
            if (
                existing.store_id != store_id
                or existing.conversation_id != conversation_id
            ):
                return False, "PDD_RATE_IDENTITY_CONFLICT"
            return False, "PDD_SEND_RESERVATION_REVIEW_REQUIRED"
        minute_start = now - timedelta(minutes=1)
        day_start = now - timedelta(hours=24)
        store_minute = self._count_rate(
            store_id=store_id,
            since=minute_start,
        )
        if store_minute >= policy.store_per_minute:
            return False, "PDD_STORE_PER_MINUTE_REVIEW_REQUIRED"
        conversation_minute = self._count_rate(
            store_id=store_id,
            conversation_id=conversation_id,
            since=minute_start,
        )
        if conversation_minute >= policy.conversation_per_minute:
            return False, "PDD_CONVERSATION_RATE_REVIEW_REQUIRED"
        store_day = self._count_rate(store_id=store_id, since=day_start)
        if store_day >= policy.store_per_day:
            return False, "PDD_STORE_DAILY_REVIEW_REQUIRED"
        self._session.add(
            PDDSendRateEventRow(
                rate_event_id=new_id("pdd-send-rate"),
                safety_contract_version=PDD_PRODUCTION_SAFETY_VERSION,
                execution_id=execution_id,
                store_id=store_id,
                conversation_id=conversation_id,
                reserved_at=now,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise PDDProductionSafetyDenied(
                "PDD rate reservation conflicted",
                error_code="PDD_RATE_RESERVATION_CONFLICT",
            ) from exc
        return True, None

    def _count_rate(
        self,
        *,
        store_id: str,
        since: datetime,
        conversation_id: str | None = None,
    ) -> int:
        statement = select(func.count(PDDSendRateEventRow.rate_event_id)).where(
            PDDSendRateEventRow.store_id == store_id,
            PDDSendRateEventRow.reserved_at >= since,
        )
        if conversation_id is not None:
            statement = statement.where(
                PDDSendRateEventRow.conversation_id == conversation_id
            )
        return int(self._session.scalar(statement) or 0)

    @staticmethod
    def _state_values(state: PDDProductionSafetyState) -> dict[str, object]:
        return {
            "safety_contract_version": PDD_PRODUCTION_SAFETY_VERSION,
            "revision": state.revision,
            "environment": state.environment.value,
            "production_enabled": int(state.production_enabled),
            "dry_run": int(state.dry_run),
            "kill_switch_state": state.kill_switch.value,
            "store_per_minute": state.rate_limit.store_per_minute,
            "conversation_per_minute": state.rate_limit.conversation_per_minute,
            "store_per_day": state.rate_limit.store_per_day,
            "updated_at": state.updated_at,
            "updated_by": state.updated_by,
            "reason": state.reason,
        }

    @classmethod
    def _state_row(
        cls,
        state: PDDProductionSafetyState,
    ) -> PDDProductionSafetyStateRow:
        return PDDProductionSafetyStateRow(
            singleton_id=PDD_SAFETY_SINGLETON_ID,
            **cls._state_values(state),
        )

    @staticmethod
    def _state_from_row(
        row: PDDProductionSafetyStateRow,
    ) -> PDDProductionSafetyState:
        return PDDProductionSafetyState(
            revision=row.revision,
            environment=PDDEnvironmentProfile(row.environment),
            production_enabled=bool(row.production_enabled),
            dry_run=bool(row.dry_run),
            kill_switch=KillSwitchState(row.kill_switch_state),
            rate_limit=PDDRateLimitPolicy(
                store_per_minute=row.store_per_minute,
                conversation_per_minute=row.conversation_per_minute,
                store_per_day=row.store_per_day,
            ),
            updated_at=_as_utc(row.updated_at),
            updated_by=row.updated_by,
            reason=row.reason,
        )

    @staticmethod
    def _store_values(account: StoreAccount) -> dict[str, object]:
        return {
            "safety_contract_version": PDD_PRODUCTION_SAFETY_VERSION,
            "platform": account.platform,
            "store_name": account.store_name,
            "credential_reference": account.credential_reference.credential_ref,
            "credential_version": account.credential_reference.version,
            "credential_expires_at": account.credential_reference.expires_at,
            "environment": account.environment.value,
            "status": account.status.value,
            "updated_at": account.updated_at,
        }

    @staticmethod
    def _store_from_row(row: PDDStoreAccountRow) -> StoreAccount:
        return StoreAccount(
            platform="pdd",
            store_id=row.store_id,
            store_name=row.store_name,
            credential_reference=PDDCredentialReference(
                credential_ref=row.credential_reference,
                version=row.credential_version,
                expires_at=(
                    _as_utc(row.credential_expires_at)
                    if row.credential_expires_at is not None
                    else None
                ),
            ),
            environment=PDDEnvironmentProfile(row.environment),
            status=PDDStoreStatus(row.status),
            updated_at=_as_utc(row.updated_at),
        )

    @staticmethod
    def _audit_from_row(row: PDDSafetyAuditEventRow) -> PDDSafetyAuditEvent:
        return PDDSafetyAuditEvent(
            audit_event_id=row.audit_event_id,
            operator=row.operator,
            action=PDDSafetyAuditAction(row.action),
            timestamp=_as_utc(row.timestamp),
            reason=row.reason,
            store_id=row.store_id,
            execution_id=row.execution_id,
            before=row.before,
            after=row.after,
        )

    @staticmethod
    def _assert_version(version: str) -> None:
        if version != PDD_PRODUCTION_SAFETY_VERSION:
            raise PDDProductionSafetyDenied(
                "unsupported PDD safety persistence version",
                error_code="PDD_SAFETY_VERSION_UNSUPPORTED",
            )


class SqlAlchemyPDDSendReceiptStore:
    """Durable triple-key receipt replay for production-safety transports."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory

    def get_by_execution_id(self, execution_id: str) -> PDDSendReceiptRecord | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(PDDSendTransportReceiptRow, execution_id)
            return self._from_row(row) if row is not None else None

    def find_any(
        self,
        *,
        execution_id: str,
        message_id: str,
        send_key: str,
    ) -> PDDSendReceiptRecord | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(PDDSendTransportReceiptRow).where(
                    or_(
                        PDDSendTransportReceiptRow.execution_id == execution_id,
                        PDDSendTransportReceiptRow.message_id == message_id,
                        PDDSendTransportReceiptRow.send_key == send_key,
                    )
                )
            ).all()
            if not rows:
                return None
            identities = {row.execution_id for row in rows}
            if len(identities) != 1:
                raise PDDSendIdempotencyConflict(
                    "PDD send identities resolve to different durable receipts",
                    error_code="PDD_SEND_IDENTITY_SPLIT_BRAIN",
                )
            return self._from_row(rows[0])

    def append(self, record: PDDSendReceiptRecord) -> PDDSendReceiptRecord:
        try:
            with self._uow_factory() as uow:
                assert uow.session is not None
                existing = uow.session.get(
                    PDDSendTransportReceiptRow,
                    record.execution_id,
                )
                if existing is not None:
                    original = self._from_row(existing)
                    if original != record:
                        raise PDDSendIdempotencyConflict(
                            "PDD durable receipt identity has different evidence",
                            error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
                        )
                    return original
                conflicting = uow.session.scalar(
                    select(PDDSendTransportReceiptRow).where(
                        or_(
                            PDDSendTransportReceiptRow.message_id
                            == record.message_id,
                            PDDSendTransportReceiptRow.send_key == record.send_key,
                        )
                    )
                )
                if conflicting is not None:
                    raise PDDSendIdempotencyConflict(
                        "PDD message_id or send_key is already bound",
                        error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
                    )
                receipt = record.receipt
                uow.session.add(
                    PDDSendTransportReceiptRow(
                        execution_id=record.execution_id,
                        safety_contract_version=PDD_PRODUCTION_SAFETY_VERSION,
                        decision_id=record.decision_id,
                        approval_id=record.approval_id,
                        message_id=record.message_id,
                        send_key=record.send_key,
                        request_fingerprint=record.request_fingerprint,
                        receipt_id=receipt.receipt_id,
                        channel=receipt.channel,
                        conversation_id=receipt.conversation_id,
                        external_message_id=receipt.external_message_id,
                        outcome=receipt.outcome.value,
                        error_code=receipt.error_code,
                        details=receipt.details,
                        recorded_at=receipt.recorded_at,
                    )
                )
        except IntegrityError as exc:
            raise PDDSendIdempotencyConflict(
                "PDD durable receipt append conflicted",
                error_code="PDD_SEND_IDEMPOTENCY_CONFLICT",
            ) from exc
        return record

    @staticmethod
    def _from_row(row: PDDSendTransportReceiptRow) -> PDDSendReceiptRecord:
        PDDProductionSafetyRepository._assert_version(
            row.safety_contract_version
        )
        return PDDSendReceiptRecord(
            execution_id=row.execution_id,
            decision_id=row.decision_id,
            approval_id=row.approval_id,
            message_id=row.message_id,
            send_key=row.send_key,
            request_fingerprint=row.request_fingerprint,
            receipt=ChannelSendReceipt(
                receipt_id=row.receipt_id,
                channel=row.channel,
                conversation_id=row.conversation_id,
                execution_id=row.execution_id,
                idempotency_key=row.send_key,
                external_message_id=row.external_message_id,
                outcome=ReceiptOutcome(row.outcome),
                error_code=row.error_code,
                details=row.details,
                recorded_at=_as_utc(row.recorded_at),
            ),
        )


class PDDProductionSafetyService:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self.receipt_store: PDDSendReceiptStore = SqlAlchemyPDDSendReceiptStore(
            uow_factory
        )

    def status(self) -> PDDProductionSafetyState:
        with self._uow_factory() as uow:
            assert uow.session is not None
            return PDDProductionSafetyRepository(uow.session).get_or_create_state(
                _as_utc(self._clock())
            )

    def enable_production(
        self,
        *,
        confirmation_phrase: str,
        operator: str,
        reason: str,
        dry_run: bool = True,
        rate_limit: PDDRateLimitPolicy | None = None,
    ) -> PDDProductionSafetyState:
        if confirmation_phrase != PDD_PRODUCTION_CONFIRMATION_PHRASE:
            raise PDDProductionSafetyDenied(
                "PDD production requires the exact confirmation phrase",
                error_code="PDD_PRODUCTION_CONFIRMATION_REQUIRED",
            )
        return self._update_state(
            environment=PDDEnvironmentProfile.PRODUCTION,
            production_enabled=True,
            dry_run=dry_run,
            rate_limit=rate_limit,
            operator=operator,
            reason=reason,
            action=PDDSafetyAuditAction.PRODUCTION_ENABLED,
        )

    def disable_production(
        self,
        *,
        operator: str,
        reason: str,
    ) -> PDDProductionSafetyState:
        return self._update_state(
            environment=PDDEnvironmentProfile.MOCK,
            production_enabled=False,
            dry_run=True,
            rate_limit=None,
            operator=operator,
            reason=reason,
            action=PDDSafetyAuditAction.PRODUCTION_DISABLED,
        )

    def enable_kill_switch(
        self,
        *,
        operator: str,
        reason: str,
    ) -> PDDProductionSafetyState:
        return self._set_kill_switch(
            target=KillSwitchState.ENABLED,
            operator=operator,
            reason=reason,
            action=PDDSafetyAuditAction.KILL_SWITCH_TRIGGERED,
        )

    def disable_kill_switch(
        self,
        *,
        operator: str,
        reason: str,
    ) -> PDDProductionSafetyState:
        return self._set_kill_switch(
            target=KillSwitchState.DISABLED,
            operator=operator,
            reason=reason,
            action=PDDSafetyAuditAction.KILL_SWITCH_DISABLED,
        )

    def allow_store(
        self,
        account: StoreAccount,
        *,
        operator: str,
        reason: str,
    ) -> StoreAccount:
        if account.status is not PDDStoreStatus.ALLOWLISTED:
            raise ValueError("allow_store requires ALLOWLISTED status")
        now = _as_utc(self._clock())
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            before_account = repo.get_store(account.store_id)
            normalized = account.model_copy(update={"updated_at": now})
            repo.upsert_store(normalized)
            repo.append_audit(
                self._audit(
                    action=PDDSafetyAuditAction.STORE_ALLOWLISTED,
                    operator=operator,
                    reason=reason,
                    store_id=account.store_id,
                    before=self._store_audit_state(before_account),
                    after=self._store_audit_state(normalized),
                    now=now,
                )
            )
        return normalized

    def set_store_status(
        self,
        store_id: str,
        status: PDDStoreStatus,
        *,
        operator: str,
        reason: str,
    ) -> StoreAccount:
        now = _as_utc(self._clock())
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            current = self._require_store(repo, store_id)
            updated = current.model_copy(update={"status": status, "updated_at": now})
            repo.upsert_store(updated)
            repo.append_audit(
                self._audit(
                    action=PDDSafetyAuditAction.STORE_STATUS_CHANGED,
                    operator=operator,
                    reason=reason,
                    store_id=store_id,
                    before=self._store_audit_state(current),
                    after=self._store_audit_state(updated),
                    now=now,
                )
            )
        return updated

    def change_credential(
        self,
        store_id: str,
        credential_reference: PDDCredentialReference,
        *,
        operator: str,
        reason: str,
    ) -> StoreAccount:
        now = _as_utc(self._clock())
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            current = self._require_store(repo, store_id)
            updated = current.model_copy(
                update={
                    "credential_reference": credential_reference,
                    "updated_at": now,
                }
            )
            repo.upsert_store(updated)
            repo.append_audit(
                self._audit(
                    action=PDDSafetyAuditAction.CREDENTIAL_CHANGED,
                    operator=operator,
                    reason=reason,
                    store_id=store_id,
                    before={"credential_version": current.credential_reference.version},
                    after={"credential_version": credential_reference.version},
                    now=now,
                )
            )
        return updated

    def bind_execution(
        self,
        *,
        execution_id: str,
        store_id: str,
        conversation_id: str,
        operator: str,
        reason: str,
    ) -> PDDExecutionStoreBinding:
        now = _as_utc(self._clock())
        binding = PDDExecutionStoreBinding(
            execution_id=execution_id,
            store_id=store_id,
            conversation_id=conversation_id,
            bound_at=now,
            bound_by=operator,
        )
        with self._uow_factory() as uow:
            assert uow.session is not None
            uow.require_repository().get_execution(execution_id)
            repo = PDDProductionSafetyRepository(uow.session)
            account = self._require_store(repo, store_id)
            if account.status is not PDDStoreStatus.ALLOWLISTED:
                raise PDDProductionSafetyDenied(
                    "Execution cannot bind a non-allowlisted store",
                    error_code="PDD_STORE_NOT_ALLOWLISTED",
                )
            repo.save_binding(binding)
            repo.append_audit(
                self._audit(
                    action=PDDSafetyAuditAction.EXECUTION_STORE_BOUND,
                    operator=operator,
                    reason=reason,
                    store_id=store_id,
                    execution_id=execution_id,
                    after={"conversation_id": conversation_id},
                    now=now,
                )
            )
        return binding

    def list_audit_events(self, limit: int = 100) -> list[PDDSafetyAuditEvent]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            return PDDProductionSafetyRepository(uow.session).list_audits(limit)

    def authorize_send(
        self,
        context: PDDApprovedExecutionContext,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
        *,
        global_kill_switch_enabled: bool,
    ) -> PDDSendGateDecision:
        now = _as_utc(self._clock())
        denial: tuple[str, str] | None = None
        permit: PDDSendGateDecision | None = None
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            state = repo.get_or_create_state(now)
            binding = repo.get_binding(context.execution_id)
            account = repo.get_store(binding.store_id) if binding is not None else None
            if global_kill_switch_enabled:
                denial = (
                    "PDD_GLOBAL_KILL_SWITCH_ENABLED",
                    "GLOBAL_KILL_SWITCH_ENABLED",
                )
            elif state.kill_switch is KillSwitchState.ENABLED:
                denial = ("PDD_KILL_SWITCH_ENABLED", "PDD_KILL_SWITCH_ENABLED")
            elif (
                state.environment is not PDDEnvironmentProfile.PRODUCTION
                or not state.production_enabled
            ):
                denial = (
                    "PDD_PRODUCTION_NOT_ENABLED",
                    "PRODUCTION_NOT_EXPLICITLY_ENABLED",
                )
            elif binding is None:
                denial = (
                    "PDD_EXECUTION_STORE_BINDING_MISSING",
                    "EXECUTION_STORE_BINDING_MISSING",
                )
            elif binding.conversation_id != command.message.conversation_id:
                denial = (
                    "PDD_EXECUTION_CONVERSATION_MISMATCH",
                    "EXECUTION_CONVERSATION_MISMATCH",
                )
            elif account is None or account.status is not PDDStoreStatus.ALLOWLISTED:
                denial = ("PDD_STORE_NOT_ALLOWLISTED", "STORE_NOT_ALLOWLISTED")
            elif account.environment is not PDDEnvironmentProfile.PRODUCTION:
                denial = (
                    "PDD_STORE_ENVIRONMENT_MISMATCH",
                    "STORE_ENVIRONMENT_MISMATCH",
                )
            elif (
                account.credential_reference.credential_ref
                != session.cookie_reference
            ):
                denial = (
                    "PDD_CREDENTIAL_REFERENCE_MISMATCH",
                    "CREDENTIAL_REFERENCE_MISMATCH",
                )
            elif (
                account.credential_reference.expires_at is not None
                and _as_utc(account.credential_reference.expires_at) <= now
            ):
                denial = (
                    "PDD_CREDENTIAL_REFERENCE_EXPIRED",
                    "CREDENTIAL_REFERENCE_EXPIRED",
                )
            else:
                allowed, rate_error = repo.reserve_rate(
                    execution_id=context.execution_id,
                    store_id=binding.store_id,
                    conversation_id=binding.conversation_id,
                    policy=state.rate_limit,
                    now=now,
                )
                if not allowed:
                    denial = (
                        rate_error or "PDD_RATE_LIMIT_REVIEW_REQUIRED",
                        "RATE_LIMIT_REVIEW_REQUIRED",
                    )
                else:
                    permit = PDDSendGateDecision(
                        gate_name="pdd-production-safety-gate.v1",
                        environment=state.environment.value,
                        store_id=binding.store_id,
                        dry_run=state.dry_run,
                    )
                    repo.append_audit(
                        self._audit(
                            action=PDDSafetyAuditAction.SEND_AUTHORIZED,
                            operator="system:pdd-safety-gate",
                            reason="PDD_SEND_SAFETY_AUTHORIZED",
                            store_id=binding.store_id,
                            execution_id=context.execution_id,
                            after={
                                "environment": state.environment.value,
                                "dry_run": state.dry_run,
                                "rate_reserved": True,
                            },
                            now=now,
                        )
                    )
            if denial is not None:
                repo.append_audit(
                    self._audit(
                        action=PDDSafetyAuditAction.SEND_BLOCKED,
                        operator="system:pdd-safety-gate",
                        reason=denial[1],
                        store_id=binding.store_id if binding is not None else None,
                        execution_id=context.execution_id,
                        before={
                            "environment": state.environment.value,
                            "production_enabled": state.production_enabled,
                            "kill_switch": state.kill_switch.value,
                        },
                        after={"blocked": True, "error_code": denial[0]},
                        now=now,
                    )
                )
        if denial is not None:
            error_type = (
                PDDRateLimitReviewRequired
                if "REVIEW_REQUIRED" in denial[0]
                else PDDProductionSafetyDenied
            )
            raise error_type(
                "PDD production safety gate blocked send",
                error_code=denial[0],
            )
        assert permit is not None
        return permit

    def _update_state(
        self,
        *,
        environment: PDDEnvironmentProfile,
        production_enabled: bool,
        dry_run: bool,
        rate_limit: PDDRateLimitPolicy | None,
        operator: str,
        reason: str,
        action: PDDSafetyAuditAction,
    ) -> PDDProductionSafetyState:
        now = _as_utc(self._clock())
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            current = repo.get_or_create_state(now)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "environment": environment,
                    "production_enabled": production_enabled,
                    "dry_run": dry_run,
                    "rate_limit": rate_limit or current.rate_limit,
                    "updated_at": now,
                    "updated_by": operator,
                    "reason": reason,
                }
            )
            repo.save_state(current, updated)
            repo.append_audit(
                self._audit(
                    action=action,
                    operator=operator,
                    reason=reason,
                    before=self._state_audit(current),
                    after=self._state_audit(updated),
                    now=now,
                )
            )
        return updated

    def _set_kill_switch(
        self,
        *,
        target: KillSwitchState,
        operator: str,
        reason: str,
        action: PDDSafetyAuditAction,
    ) -> PDDProductionSafetyState:
        now = _as_utc(self._clock())
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = PDDProductionSafetyRepository(uow.session)
            current = repo.get_or_create_state(now)
            updated = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "kill_switch": target,
                    "updated_at": now,
                    "updated_by": operator,
                    "reason": reason,
                }
            )
            repo.save_state(current, updated)
            repo.append_audit(
                self._audit(
                    action=action,
                    operator=operator,
                    reason=reason,
                    before=self._state_audit(current),
                    after=self._state_audit(updated),
                    now=now,
                )
            )
        return updated

    @staticmethod
    def _state_audit(state: PDDProductionSafetyState) -> dict[str, object]:
        return {
            "revision": state.revision,
            "environment": state.environment.value,
            "production_enabled": state.production_enabled,
            "dry_run": state.dry_run,
            "kill_switch": state.kill_switch.value,
            "rate_limit": state.rate_limit.model_dump(mode="json"),
        }

    @staticmethod
    def _store_audit_state(account: StoreAccount | None) -> dict[str, object]:
        if account is None:
            return {}
        return {
            "platform": account.platform,
            "store_id": account.store_id,
            "environment": account.environment.value,
            "status": account.status.value,
            "credential_version": account.credential_reference.version,
        }

    @staticmethod
    def _audit(
        *,
        action: PDDSafetyAuditAction,
        operator: str,
        reason: str,
        now: datetime,
        store_id: str | None = None,
        execution_id: str | None = None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> PDDSafetyAuditEvent:
        return PDDSafetyAuditEvent(
            audit_event_id=new_id("pdd-safety-audit"),
            operator=operator,
            action=action,
            timestamp=now,
            reason=reason,
            store_id=store_id,
            execution_id=execution_id,
            before=before or {},
            after=after or {},
        )

    @staticmethod
    def _require_store(
        repo: PDDProductionSafetyRepository,
        store_id: str,
    ) -> StoreAccount:
        account = repo.get_store(store_id)
        if account is None:
            raise PDDProductionSafetyDenied(
                "PDD store is not registered",
                error_code="PDD_STORE_NOT_ALLOWLISTED",
            )
        return account


class PDDProductionSafetyGate:
    gate_name = "pdd-production-safety-gate.v1"

    def __init__(
        self,
        service: PDDProductionSafetyService,
        *,
        global_control_plane: KillSwitchStatusProvider | None = None,
    ) -> None:
        self.service = service
        self.global_control_plane = global_control_plane
        self.receipt_store = service.receipt_store

    def authorize_send(
        self,
        context: PDDApprovedExecutionContext,
        command: AuthorizedOutboundMessage,
        session: PDDSendSession,
    ) -> PDDSendGateDecision:
        global_enabled = False
        if self.global_control_plane is not None:
            global_enabled = (
                self.global_control_plane.kill_switch_status().state
                is KillSwitchState.ENABLED
            )
        return self.service.authorize_send(
            context,
            command,
            session,
            global_kill_switch_enabled=global_enabled,
        )


class PDDProductionExecutionGate:
    """PDD channel kill switch composed with the existing global control gate."""

    def __init__(
        self,
        *,
        delegate: ExecutionControlGate | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._delegate = delegate or AllowExecutionControlGate()
        self._clock = clock

    def assert_new_execution_allowed(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._delegate.assert_new_execution_allowed(uow)
        if not self._pdd_allowed(uow):
            raise PDDExecutionControlBlocked(
                "PDD kill switch is ENABLED; new Execution is forbidden"
            )

    def pending_claim_allowed(self, uow: SqlAlchemyUnitOfWork) -> bool:
        return self._delegate.pending_claim_allowed(uow) and self._pdd_allowed(uow)

    def _pdd_allowed(self, uow: SqlAlchemyUnitOfWork) -> bool:
        if uow.session is None:
            raise RuntimeError("PDD execution gate requires an active unit of work")
        state = PDDProductionSafetyRepository(uow.session).get_or_create_state(
            _as_utc(self._clock())
        )
        return state.kill_switch is KillSwitchState.DISABLED


__all__ = [
    "PDD_PRODUCTION_CONFIRMATION_PHRASE",
    "PDD_PRODUCTION_SAFETY_VERSION",
    "PDDCredentialReference",
    "PDDEnvironmentProfile",
    "PDDExecutionControlBlocked",
    "PDDExecutionStoreBinding",
    "PDDProductionExecutionGate",
    "PDDProductionSafetyDenied",
    "PDDProductionSafetyGate",
    "PDDProductionSafetyRepository",
    "PDDProductionSafetyService",
    "PDDProductionSafetyState",
    "PDDRateLimitPolicy",
    "PDDRateLimitReviewRequired",
    "PDDSafetyAuditAction",
    "PDDSafetyAuditEvent",
    "PDDStoreStatus",
    "StoreAccount",
    "SqlAlchemyPDDSendReceiptStore",
]
