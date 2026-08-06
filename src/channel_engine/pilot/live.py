from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from channel_engine.models.entities import utc_now

from .models import (
    PDD_PILOT_TARGET_STORE_NAME,
    PilotBrowserStatus,
    PilotEvidenceType,
    PilotExecutionResult,
    PilotIntakeResult,
    PilotModel,
    PilotRuntimeState,
    PilotStoreStatus,
)
from .runtime import PDDPilotRuntime, PilotRuntimeError


PDD_PILOT_LIVE_CONTRACT_VERSION = "1.0"


class PilotLiveCheckStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class PilotLiveCheckName(StrEnum):
    AGENT_STATUS = "AGENT_STATUS"
    RUNTIME_STORAGE = "RUNTIME_STORAGE"
    CLEAN_ACTIVATION_DATABASE = "CLEAN_ACTIVATION_DATABASE"
    SAFETY_MODE = "SAFETY_MODE"
    KILL_SWITCH = "KILL_SWITCH"
    STORE_BINDING = "STORE_BINDING"
    CREDENTIAL_REFERENCE = "CREDENTIAL_REFERENCE"
    SINGLE_REPLY_LIMIT = "SINGLE_REPLY_LIMIT"
    BROWSER_DRIVER = "BROWSER_DRIVER"
    LOGIN_RULES = "LOGIN_RULES"
    SELECTOR_CONTRACT = "SELECTOR_CONTRACT"
    STORE_IDENTITY_PROBE = "STORE_IDENTITY_PROBE"
    INBOUND_TRANSPORT = "INBOUND_TRANSPORT"
    AI_CS_GATEWAY = "AI_CS_GATEWAY"
    OUTBOUND_TRANSPORT = "OUTBOUND_TRANSPORT"


class PilotLiveFinalStatus(StrEnum):
    ACTIVATION_BLOCKED = "PDD_SINGLE_STORE_PILOT_ACTIVATION_BLOCKED"
    ACTIVATION_IN_PROGRESS = "PDD_SINGLE_STORE_PILOT_ACTIVATION_IN_PROGRESS"
    STOPPED = "PDD_SINGLE_STORE_PILOT_STOPPED"
    LIVE = "PDD_SINGLE_STORE_PILOT_LIVE"


class PilotLiveCapabilitySnapshot(PilotModel):
    """Externally verified facts; values are never inferred from a Fake port."""

    agent_online: bool = False
    runtime_storage_ready: bool = False
    clean_activation_database: bool = False
    browser_login_rules_verified: bool = False
    selector_contract_verified: bool = False
    store_identity_probe_verified: bool = False
    real_ai_cs_gateway: bool = False
    real_outbound_transport: bool = False
    evidence_sources: tuple[str, ...] = ()

    @field_validator("evidence_sources")
    @classmethod
    def reject_secret_material(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        forbidden = ("cookie=", "token=", "secret=", "password=", "bearer ")
        for value in values:
            lowered = value.casefold()
            if any(marker in lowered for marker in forbidden):
                raise ValueError("live capability source contains secret material")
        return values


class PilotLivePreflightCheck(PilotModel):
    name: PilotLiveCheckName
    status: PilotLiveCheckStatus
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class PilotLivePreflightReport(PilotModel):
    target_status: Literal["PDD_SINGLE_STORE_PILOT_LIVE"] = (
        "PDD_SINGLE_STORE_PILOT_LIVE"
    )
    generated_at: AwareDatetime
    store_id: str
    store_name: str
    ready_for_manual_login: bool
    auto_reply: Literal[False] = False
    manual_approval: Literal[True] = True
    maximum_replies: Literal[1] = 1
    checks: tuple[PilotLivePreflightCheck, ...]
    blockers: tuple[str, ...]


class PilotLiveEvidenceReport(PilotModel):
    target_status: Literal["PDD_SINGLE_STORE_PILOT_LIVE"] = (
        "PDD_SINGLE_STORE_PILOT_LIVE"
    )
    final_status: PilotLiveFinalStatus
    generated_at: AwareDatetime
    store_id: str
    store_name: str
    auto_reply: Literal[False] = False
    manual_approval: Literal[True] = True
    maximum_replies: Literal[1] = 1
    browser_generation: int | None = Field(default=None, ge=1)
    session_status: str
    store_status: str
    runtime_status: str
    evidence_counts: dict[str, int]
    evidence_ids: tuple[str, ...]
    blockers: tuple[str, ...]


class PilotLiveActivationError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PilotLiveActivationService:
    """One-message, one-reply activation guard over the existing Pilot runtime."""

    def __init__(
        self,
        runtime: PDDPilotRuntime,
        capabilities: PilotLiveCapabilitySnapshot | None = None,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self.runtime = runtime
        self.capabilities = capabilities or PilotLiveCapabilitySnapshot()
        self._clock = clock
        self._lock = RLock()
        self._intake: PilotIntakeResult | None = None
        self._execution: PilotExecutionResult | None = None

    def preflight(self) -> PilotLivePreflightReport:
        config = self.runtime.config
        checks = (
            self._check(
                PilotLiveCheckName.AGENT_STATUS,
                self.capabilities.agent_online,
                "PILOT_AGENT_ONLINE",
                "PILOT_AGENT_NOT_ONLINE",
            ),
            self._check(
                PilotLiveCheckName.RUNTIME_STORAGE,
                self.capabilities.runtime_storage_ready,
                "PILOT_RUNTIME_STORAGE_READY",
                "PILOT_RUNTIME_STORAGE_NOT_READY",
            ),
            self._check(
                PilotLiveCheckName.CLEAN_ACTIVATION_DATABASE,
                self.capabilities.clean_activation_database,
                "PILOT_ACTIVATION_DATABASE_CLEAN",
                "PILOT_ACTIVATION_DATABASE_UNVERIFIED",
            ),
            self._check(
                PilotLiveCheckName.SAFETY_MODE,
                config.auto_reply is False and config.approval_required is True,
                "PILOT_SAFETY_MODE_VALID",
                "PILOT_SAFETY_MODE_INVALID",
            ),
            self._check(
                PilotLiveCheckName.KILL_SWITCH,
                not self.runtime.kill_switch.enabled(),
                "PILOT_KILL_SWITCH_DISABLED",
                "PILOT_KILL_SWITCH_ENABLED_OR_UNKNOWN",
            ),
            self._check(
                PilotLiveCheckName.STORE_BINDING,
                self._store_binding_is_verified(),
                "PILOT_STORE_BINDING_VERIFIED",
                "PILOT_STORE_BINDING_UNVERIFIED",
            ),
            self._check(
                PilotLiveCheckName.CREDENTIAL_REFERENCE,
                config.credential_reference.startswith(
                    ("credential-ref://", "secret-ref://")
                ),
                "PILOT_CREDENTIAL_REFERENCE_VALID",
                "PILOT_CREDENTIAL_REFERENCE_INVALID",
            ),
            self._check(
                PilotLiveCheckName.SINGLE_REPLY_LIMIT,
                config.send_limit == 1,
                "PILOT_SINGLE_REPLY_LIMIT_ACTIVE",
                "PILOT_SINGLE_REPLY_LIMIT_REQUIRED",
            ),
            self._check(
                PilotLiveCheckName.BROWSER_DRIVER,
                self.runtime.browser.real_browser_capable,
                "PILOT_REAL_BROWSER_CAPABLE",
                "PILOT_REAL_BROWSER_UNAVAILABLE",
            ),
            self._check(
                PilotLiveCheckName.LOGIN_RULES,
                self.capabilities.browser_login_rules_verified,
                "PILOT_LOGIN_RULES_VERIFIED",
                "PILOT_LOGIN_RULES_UNVERIFIED",
            ),
            self._check(
                PilotLiveCheckName.SELECTOR_CONTRACT,
                self.capabilities.selector_contract_verified,
                "PILOT_SELECTOR_CONTRACT_VERIFIED",
                "PILOT_SELECTOR_CONTRACT_DRAFT",
            ),
            self._check(
                PilotLiveCheckName.STORE_IDENTITY_PROBE,
                self.capabilities.store_identity_probe_verified,
                "PILOT_STORE_IDENTITY_PROBE_VERIFIED",
                "PILOT_STORE_IDENTITY_PROBE_UNVERIFIED",
            ),
            self._check(
                PilotLiveCheckName.INBOUND_TRANSPORT,
                self.runtime.inbound.real_platform_transport,
                "PILOT_REAL_INBOUND_TRANSPORT_READY",
                "PILOT_REAL_INBOUND_TRANSPORT_UNAVAILABLE",
            ),
            self._check(
                PilotLiveCheckName.AI_CS_GATEWAY,
                self.capabilities.real_ai_cs_gateway,
                "PILOT_REAL_AI_CS_GATEWAY_READY",
                "PILOT_REAL_AI_CS_GATEWAY_UNAVAILABLE",
            ),
            self._check(
                PilotLiveCheckName.OUTBOUND_TRANSPORT,
                self.capabilities.real_outbound_transport,
                "PILOT_REAL_OUTBOUND_TRANSPORT_READY",
                "PILOT_REAL_OUTBOUND_TRANSPORT_UNAVAILABLE",
            ),
        )
        blockers = tuple(
            item.reason_code
            for item in checks
            if item.status is PilotLiveCheckStatus.BLOCKED
        )
        return PilotLivePreflightReport(
            generated_at=self._clock(),
            store_id=config.store_id,
            store_name=config.store_name,
            ready_for_manual_login=not blockers,
            checks=checks,
            blockers=blockers,
        )

    def start_manual_login(self):  # type: ignore[no-untyped-def]
        with self._lock:
            report = self.preflight()
            if not report.ready_for_manual_login:
                self._record_preflight(report)
                raise PilotLiveActivationError(
                    "Pilot live preflight is blocked",
                    error_code="PILOT_LIVE_PREFLIGHT_BLOCKED",
                )
            self._record_preflight(report)
            dashboard = self.runtime.start()
            if dashboard.store_status is PilotStoreStatus.MISMATCH:
                self._emergency_stop("PILOT_STORE_MISMATCH")
            return dashboard

    def check_session(self):  # type: ignore[no-untyped-def]
        with self._lock:
            dashboard = self.runtime.check()
            if dashboard.store_status is PilotStoreStatus.MISMATCH:
                self._emergency_stop("PILOT_STORE_MISMATCH")
            return dashboard

    def poll_one_message(self) -> PilotIntakeResult | None:
        with self._lock:
            self._assert_preflight()
            if self._intake is not None:
                return self._intake
            if self._message_evidence_count() >= 1:
                raise PilotLiveActivationError(
                    "Pilot activation permits exactly one inbound message",
                    error_code="PILOT_LIVE_MESSAGE_LIMIT_REACHED",
                )
            try:
                self._intake = self.runtime.poll_message()
            except Exception as exc:
                self._emergency_stop("PILOT_INBOUND_UNKNOWN_STOP")
                raise PilotLiveActivationError(
                    "Pilot inbound state is unknown; activation stopped",
                    error_code="PILOT_LIVE_INBOUND_UNKNOWN",
                ) from exc
            return self._intake

    def approve_first_reply(
        self,
        decision_id: str,
        approved_by: str,
    ) -> PilotExecutionResult:
        with self._lock:
            self._assert_preflight()
            if self._intake is None or self._intake.decision_id != decision_id:
                raise PilotLiveActivationError(
                    "Approval is not bound to the one observed Pilot message",
                    error_code="PILOT_LIVE_DECISION_BINDING_MISMATCH",
                )
            if self._execution is not None:
                if self._execution.decision_id != decision_id:
                    raise PilotLiveActivationError(
                        "Pilot activation reply limit is exhausted",
                        error_code="PILOT_LIVE_REPLY_LIMIT_REACHED",
                    )
                return self._execution
            result = self.runtime.approve_and_execute(decision_id, approved_by)
            self._execution = result
            if result.receipt_outcome == "UNKNOWN" or result.execution_state == "UNKNOWN":
                self._emergency_stop("PILOT_SEND_UNKNOWN_STOP")
            return result

    def stop(self, *, reason: str = "PILOT_OPERATOR_STOP"):
        with self._lock:
            dashboard = self.runtime.stop()
            self.runtime.persistence.evidence(
                evidence_type=PilotEvidenceType.LIVE_STOPPED,
                store_id=self.runtime.config.store_id,
                correlation_id=self.runtime.config.store_id,
                idempotency_key=f"pilot:live:stopped:{self._clock().isoformat()}",
                payload={"reason_code": reason},
                recorded_at=self._clock(),
            )
            return dashboard

    def evidence_report(self) -> PilotLiveEvidenceReport:
        preflight = self.preflight()
        evidence = self.runtime.evidence(1000)
        counts: dict[str, int] = {}
        for item in evidence:
            counts[item.evidence_type.value] = counts.get(item.evidence_type.value, 0) + 1
        blockers = list(preflight.blockers)
        required = (
            PilotEvidenceType.STARTUP,
            PilotEvidenceType.BROWSER_SESSION,
            PilotEvidenceType.STORE_BINDING,
            PilotEvidenceType.MESSAGE_RECEIVED,
            PilotEvidenceType.DECISION_CREATED,
            PilotEvidenceType.APPROVAL_GRANTED,
            PilotEvidenceType.EXECUTION_STARTED,
            PilotEvidenceType.RECEIPT_RECORDED,
        )
        for evidence_type in required:
            if counts.get(evidence_type.value, 0) < 1:
                blockers.append(f"PILOT_EVIDENCE_{evidence_type.value}_MISSING")
        if counts.get(PilotEvidenceType.MESSAGE_RECEIVED.value, 0) > 1:
            blockers.append("PILOT_LIVE_MULTIPLE_MESSAGES_DETECTED")
        reservations = self.runtime.persistence.list_reservations(
            self.runtime.config.store_id
        )
        if len(reservations) > 1:
            blockers.append("PILOT_LIVE_MULTIPLE_EXECUTIONS_DETECTED")
        receipts = [
            item
            for item in evidence
            if item.evidence_type is PilotEvidenceType.RECEIPT_RECORDED
        ]
        receipt_proves_real_success = bool(
            len(receipts) == 1
            and receipts[0].payload.get("outcome") == "SUCCESS"
            and receipts[0].payload.get("real_platform_called") is True
            and receipts[0].payload.get("customer_message_sent") is True
        )
        if receipts and not receipt_proves_real_success:
            blockers.append("PILOT_LIVE_REAL_SEND_RECEIPT_UNPROVEN")
        browser = self.runtime.browser_snapshot()
        dashboard = self.runtime.status()
        live = bool(
            not blockers
            and preflight.ready_for_manual_login
            and browser.real_browser_started
            and browser.status is PilotBrowserStatus.CONNECTED
            and browser.generation is not None
            and dashboard.store_status is PilotStoreStatus.MATCHED
            and dashboard.runtime_state is PilotRuntimeState.READY
            and len(reservations) == 1
            and receipt_proves_real_success
        )
        stopped = any(
            item.evidence_type is PilotEvidenceType.LIVE_STOPPED for item in evidence
        )
        if live:
            final_status = PilotLiveFinalStatus.LIVE
        elif stopped:
            final_status = PilotLiveFinalStatus.STOPPED
        elif not preflight.ready_for_manual_login:
            final_status = PilotLiveFinalStatus.ACTIVATION_BLOCKED
        else:
            final_status = PilotLiveFinalStatus.ACTIVATION_IN_PROGRESS
        return PilotLiveEvidenceReport(
            final_status=final_status,
            generated_at=self._clock(),
            store_id=self.runtime.config.store_id,
            store_name=self.runtime.config.store_name,
            browser_generation=browser.generation,
            session_status=browser.status.value,
            store_status=dashboard.store_status.value,
            runtime_status=dashboard.runtime_state.value,
            evidence_counts=counts,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def _assert_preflight(self) -> None:
        if not self.preflight().ready_for_manual_login:
            raise PilotLiveActivationError(
                "Pilot live preflight is blocked",
                error_code="PILOT_LIVE_PREFLIGHT_BLOCKED",
            )

    def _store_binding_is_verified(self) -> bool:
        config = self.runtime.config
        lowered = config.store_id.casefold()
        placeholder = any(
            marker in lowered
            for marker in ("placeholder", "must-be-verified", "unknown", "todo")
        )
        return not placeholder and config.store_name == PDD_PILOT_TARGET_STORE_NAME

    def _record_preflight(self, report: PilotLivePreflightReport) -> None:
        self.runtime.persistence.evidence(
            evidence_type=PilotEvidenceType.LIVE_PREFLIGHT,
            store_id=self.runtime.config.store_id,
            correlation_id=self.runtime.config.store_id,
            idempotency_key=f"pilot:live:preflight:{report.generated_at.isoformat()}",
            payload={
                "ready": report.ready_for_manual_login,
                "blockers": list(report.blockers),
                "maximum_replies": 1,
                "auto_reply": False,
                "manual_approval": True,
            },
            recorded_at=report.generated_at,
        )

    def _message_evidence_count(self) -> int:
        return sum(
            item.evidence_type is PilotEvidenceType.MESSAGE_RECEIVED
            for item in self.runtime.evidence(1000)
        )

    def _emergency_stop(self, reason: str) -> None:
        try:
            self.runtime.enable_kill_switch(
                operator="pilot-live-guard",
                reason=reason,
            )
        finally:
            self.runtime.stop()
            now = self._clock()
            self.runtime.persistence.evidence(
                evidence_type=PilotEvidenceType.LIVE_STOPPED,
                store_id=self.runtime.config.store_id,
                correlation_id=self.runtime.config.store_id,
                idempotency_key=f"pilot:live:emergency-stop:{reason}:{now.isoformat()}",
                payload={"reason_code": reason, "fail_closed": True},
                recorded_at=now,
            )
        raise PilotLiveActivationError(
            "Pilot activation stopped by fail-closed guard",
            error_code=reason,
        )

    @staticmethod
    def _check(
        name: PilotLiveCheckName,
        passed: bool,
        pass_code: str,
        blocked_code: str,
    ) -> PilotLivePreflightCheck:
        return PilotLivePreflightCheck(
            name=name,
            status=(
                PilotLiveCheckStatus.PASS
                if passed
                else PilotLiveCheckStatus.BLOCKED
            ),
            reason_code=pass_code if passed else blocked_code,
        )


__all__ = [
    "PDD_PILOT_LIVE_CONTRACT_VERSION",
    "PilotLiveActivationError",
    "PilotLiveActivationService",
    "PilotLiveCapabilitySnapshot",
    "PilotLiveCheckName",
    "PilotLiveCheckStatus",
    "PilotLiveEvidenceReport",
    "PilotLiveFinalStatus",
    "PilotLivePreflightCheck",
    "PilotLivePreflightReport",
]
