from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from channel_engine.models.entities import utc_now
from channel_engine.security import (
    OperatorPermission,
    OperatorPrincipal,
    OperatorRole,
    RBACAuthorizer,
)
from channel_engine.session import CredentialReferenceStatus

from .readiness import (
    PDDReceiveTransportDescriptor,
    PDDTransportActivationState,
    PDDTransportOrigin,
)
from .runtime_status import PDDRuntimeHealth, PDDRuntimeStatus
from .selector import (
    PDDSelectorActivationGate,
    PDDSelectorContract,
    PDDSelectorGovernanceError,
    PDDSelectorRuntimeEnvironment,
    PDDSelectorState,
)


PDD_CONTROLLED_ACTIVATION_VERSION = "1.0"
PDD_CONTROLLED_ACTIVATION_STATUS = "PDD_CONTROLLED_ACTIVATION_READY"


OpaqueRef = Annotated[
    str,
    Field(
        min_length=8,
        max_length=255,
        pattern=r"^[a-z][a-z0-9+.-]*-ref://[^\s\r\n]+$",
    ),
]


def _contains_secret_material(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "cookie=",
            "token=",
            "password=",
            "passwd=",
            "secret=",
            "authorization:",
            "bearer ",
            "bearer%20",
        )
    )


class PDDActivationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    activation_contract_version: Literal["1.0"] = PDD_CONTROLLED_ACTIVATION_VERSION

    @model_validator(mode="after")
    def reject_secret_material(self) -> PDDActivationModel:
        serialized = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        if _contains_secret_material(serialized):
            raise ValueError("activation model contains prohibited secret material")
        return self


class PDDActivationGateName(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    CREDENTIAL_CHECK = "CREDENTIAL_CHECK"
    RBAC_CHECK = "RBAC_CHECK"
    SELECTOR_CHECK = "SELECTOR_CHECK"
    OBSERVATION_MODE = "OBSERVATION_MODE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


PDD_ACTIVATION_GATE_ORDER = (
    PDDActivationGateName.PREFLIGHT,
    PDDActivationGateName.CREDENTIAL_CHECK,
    PDDActivationGateName.RBAC_CHECK,
    PDDActivationGateName.SELECTOR_CHECK,
    PDDActivationGateName.OBSERVATION_MODE,
    PDDActivationGateName.HUMAN_APPROVAL,
)


class PDDActivationGateStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


class PDDActivationCheckStatus(StrEnum):
    BLOCKED = "BLOCKED"
    READY_FOR_SEPARATE_ACTIVATION_AUTHORIZATION = (
        "READY_FOR_SEPARATE_ACTIVATION_AUTHORIZATION"
    )


class PDDGatewayActivationHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CHECKED = "NOT_CHECKED"


class PDDActivationApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PDDRollbackAction(StrEnum):
    DISABLE_EXECUTION = "DISABLE_EXECUTION"
    STOP_ADAPTER = "STOP_ADAPTER"
    STOP_SESSION = "STOP_SESSION"
    ISOLATE_GATEWAY = "ISOLATE_GATEWAY"
    SEAL_EVIDENCE = "SEAL_EVIDENCE"
    REQUIRE_MANUAL_VERIFICATION = "REQUIRE_MANUAL_VERIFICATION"


PDD_ROLLBACK_ORDER = (
    PDDRollbackAction.DISABLE_EXECUTION,
    PDDRollbackAction.STOP_ADAPTER,
    PDDRollbackAction.STOP_SESSION,
    PDDRollbackAction.ISOLATE_GATEWAY,
    PDDRollbackAction.SEAL_EVIDENCE,
    PDDRollbackAction.REQUIRE_MANUAL_VERIFICATION,
)


class PDDActivationScope(PDDActivationModel):
    """Exactly one store, account, instance and browser session."""

    activation_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    platform: Literal["pdd"] = "pdd"
    store_binding_refs: tuple[OpaqueRef, ...] = Field(min_length=1, max_length=1)
    account_refs: tuple[OpaqueRef, ...] = Field(min_length=1, max_length=1)
    instance_ids: tuple[str, ...] = Field(min_length=1, max_length=1)
    browser_session_ids: tuple[str, ...] = Field(min_length=1, max_length=1)
    multi_store_enabled: Literal[False] = False
    observe_only: Literal[True] = True
    send_enabled: Literal[False] = False
    automatic_login_enabled: Literal[False] = False

    @field_validator("instance_ids", "browser_session_ids")
    @classmethod
    def validate_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not value or len(value) > 128 or any(char.isspace() for char in value):
                raise ValueError("activation instance/session IDs must be opaque tokens")
        return values


class PDDActivationWindow(PDDActivationModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone_name: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    change_reference: OpaqueRef
    run_operator_principal_id: str = Field(min_length=1, max_length=160)
    stop_owner_principal_id: str = Field(min_length=1, max_length=160)
    recovery_owner_principal_id: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_window(self) -> PDDActivationWindow:
        duration = self.ends_at - self.starts_at
        if duration < timedelta(minutes=15) or duration > timedelta(hours=4):
            raise ValueError("activation window must be between 15 minutes and 4 hours")
        return self


class PDDRollbackStep(PDDActivationModel):
    sequence: int = Field(ge=1, le=6)
    action: PDDRollbackAction
    owner_role: OperatorRole
    verification_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )
    timeout_seconds: int = Field(ge=1, le=300)
    automatic: Literal[False] = False
    destructive: Literal[False] = False


class PDDRollbackPlan(PDDActivationModel):
    steps: tuple[PDDRollbackStep, ...]
    trigger_codes: frozenset[str] = Field(min_length=1)
    preserves_receipts: Literal[True] = True
    preserves_events: Literal[True] = True
    preserves_audit: Literal[True] = True
    requires_fresh_preflight_before_recovery: Literal[True] = True
    automatic_reconnect_after_unknown: Literal[False] = False

    @model_validator(mode="after")
    def validate_order(self) -> PDDRollbackPlan:
        if tuple(step.sequence for step in self.steps) != tuple(range(1, 7)):
            raise ValueError("rollback steps must be contiguous from 1 through 6")
        if tuple(step.action for step in self.steps) != PDD_ROLLBACK_ORDER:
            raise ValueError("rollback action order is safety-critical and immutable")
        return self


def default_pdd_rollback_plan() -> PDDRollbackPlan:
    return PDDRollbackPlan(
        steps=(
            PDDRollbackStep(
                sequence=1,
                action=PDDRollbackAction.DISABLE_EXECUTION,
                owner_role=OperatorRole.ADMIN,
                verification_code="PDD_EXECUTION_CREATION_DISABLED",
                timeout_seconds=15,
            ),
            PDDRollbackStep(
                sequence=2,
                action=PDDRollbackAction.STOP_ADAPTER,
                owner_role=OperatorRole.OPERATOR,
                verification_code="PDD_ADAPTER_STOPPED",
                timeout_seconds=30,
            ),
            PDDRollbackStep(
                sequence=3,
                action=PDDRollbackAction.STOP_SESSION,
                owner_role=OperatorRole.OPERATOR,
                verification_code="PDD_SESSION_STOPPED",
                timeout_seconds=60,
            ),
            PDDRollbackStep(
                sequence=4,
                action=PDDRollbackAction.ISOLATE_GATEWAY,
                owner_role=OperatorRole.ADMIN,
                verification_code="PDD_GATEWAY_ISOLATED",
                timeout_seconds=30,
            ),
            PDDRollbackStep(
                sequence=5,
                action=PDDRollbackAction.SEAL_EVIDENCE,
                owner_role=OperatorRole.SUPERVISOR,
                verification_code="PDD_EVIDENCE_SEALED",
                timeout_seconds=120,
            ),
            PDDRollbackStep(
                sequence=6,
                action=PDDRollbackAction.REQUIRE_MANUAL_VERIFICATION,
                owner_role=OperatorRole.SUPERVISOR,
                verification_code="PDD_MANUAL_VERIFICATION_REQUIRED",
                timeout_seconds=300,
            ),
        ),
        trigger_codes=frozenset(
            {
                "OPERATOR_STOP",
                "ACTIVATION_WINDOW_EXPIRED",
                "STORE_IDENTITY_MISMATCH",
                "SELECTOR_UNKNOWN",
                "SESSION_EXPIRED",
                "CURSOR_UNKNOWN",
                "GATEWAY_UNHEALTHY",
                "ANY_SEND_PATH_DETECTED",
            }
        ),
    )


class PDDControlledActivationPlan(PDDActivationModel):
    status: Literal["PDD_CONTROLLED_ACTIVATION_READY"] = (
        PDD_CONTROLLED_ACTIVATION_STATUS
    )
    scope: PDDActivationScope
    window: PDDActivationWindow
    ordered_gates: tuple[PDDActivationGateName, ...] = PDD_ACTIVATION_GATE_ORDER
    rollback: PDDRollbackPlan = Field(default_factory=default_pdd_rollback_plan)
    created_by: str = Field(min_length=1, max_length=160)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    real_platform_activation_allowed: Literal[False] = False
    real_send_enabled: Literal[False] = False
    customer_message_read_allowed_by_plan: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    production_readiness_status: Literal["PDD_PRODUCTION_READINESS_UNBLOCKED"] = (
        "PDD_PRODUCTION_READINESS_UNBLOCKED"
    )

    @model_validator(mode="after")
    def validate_gate_order(self) -> PDDControlledActivationPlan:
        if self.ordered_gates != PDD_ACTIVATION_GATE_ORDER:
            raise ValueError("controlled activation gate order is immutable")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class PDDActivationRuntimeSnapshot(PDDActivationModel):
    evidence_reference: OpaqueRef
    runtime: PDDRuntimeStatus
    captured_at: AwareDatetime


class PDDGatewayActivationSnapshot(PDDActivationModel):
    evidence_reference: OpaqueRef
    health: PDDGatewayActivationHealth
    gateway_contract_version: str = Field(min_length=1, max_length=64)
    capability_version: str = Field(min_length=1, max_length=64)
    signed_health_verified: bool
    checked_at: AwareDatetime
    network_connection_started_by_checker: Literal[False] = False


class PDDCredentialActivationSnapshot(PDDActivationModel):
    evidence_reference: OpaqueRef
    status: CredentialReferenceStatus
    bound_account_reference: OpaqueRef
    provider_reference_only: bool
    provider_exposes_credential_material: bool
    inspected_at: AwareDatetime


class PDDRBACActivationSnapshot(PDDActivationModel):
    evidence_reference: OpaqueRef
    run_operator: OperatorPrincipal
    scope_supervisor: OperatorPrincipal
    security_admin: OperatorPrincipal
    checked_at: AwareDatetime

    @model_validator(mode="after")
    def validate_separation_of_duties(self) -> PDDRBACActivationSnapshot:
        principals = (
            self.run_operator.principal_id,
            self.scope_supervisor.principal_id,
            self.security_admin.principal_id,
        )
        if len(set(principals)) != 3:
            raise ValueError("activation roles require three distinct principals")
        return self


class PDDObservationActivationSafetySnapshot(PDDActivationModel):
    policy_reference: OpaqueRef
    observe_only: bool
    auto_reply: bool
    manual_approval_required: bool
    send_enabled: bool
    outbound_transport_enabled: bool
    execution_creation_enabled: bool
    click_send_enabled: bool
    channel_kill_switch_enabled: bool
    customer_message_capture_started: bool
    checked_at: AwareDatetime


class PDDActivationHumanApproval(PDDActivationModel):
    approval_reference: OpaqueRef
    principal: OperatorPrincipal
    decision: PDDActivationApprovalDecision
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=3, max_length=500)
    decided_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("reason")
    @classmethod
    def reject_sensitive_reason(cls, value: str) -> str:
        if _contains_secret_material(value):
            raise ValueError("approval reason contains prohibited secret material")
        return value

    @model_validator(mode="after")
    def validate_expiry(self) -> PDDActivationHumanApproval:
        if self.expires_at <= self.decided_at:
            raise ValueError("activation approval must expire")
        return self


class PDDControlledActivationCheckInput(PDDActivationModel):
    plan: PDDControlledActivationPlan
    transport: PDDReceiveTransportDescriptor
    runtime: PDDActivationRuntimeSnapshot
    gateway: PDDGatewayActivationSnapshot
    safety: PDDObservationActivationSafetySnapshot
    credential: PDDCredentialActivationSnapshot | None = None
    rbac: PDDRBACActivationSnapshot | None = None
    selector: PDDSelectorContract | None = None
    approvals: tuple[PDDActivationHumanApproval, ...] = ()
    checked_at: AwareDatetime = Field(default_factory=utc_now)


class PDDActivationGateResult(PDDActivationModel):
    gate: PDDActivationGateName
    status: PDDActivationGateStatus
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )
    checked_at: AwareDatetime


class PDDActivationEvidenceManifest(PDDActivationModel):
    manifest_id: str = Field(min_length=1, max_length=128)
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_evidence_reference: OpaqueRef
    runtime_status: PDDRuntimeHealth
    session_status: PDDRuntimeHealth
    adapter_status: PDDRuntimeHealth
    cursor_status: PDDRuntimeHealth
    cursor_last_persisted_sequence: int = Field(ge=0)
    cursor_last_processed_sequence: int = Field(ge=0)
    cursor_backlog: int = Field(ge=0)
    gateway_evidence_reference: OpaqueRef
    gateway_status: PDDGatewayActivationHealth
    credential_evidence_reference: OpaqueRef | None = None
    selector_state: PDDSelectorState | None = None
    selector_evidence_reference: str | None = Field(default=None, max_length=255)
    rbac_evidence_reference: OpaqueRef | None = None
    gate_results: tuple[PDDActivationGateResult, ...]
    captured_at: AwareDatetime
    checker_network_operations: Literal[0] = 0
    checker_browser_operations: Literal[0] = 0
    checker_customer_messages_read: Literal[0] = 0
    checker_send_operations: Literal[0] = 0
    contains_secret_material: Literal[False] = False


class PDDControlledActivationCheckResult(PDDActivationModel):
    preparation_status: Literal["PDD_CONTROLLED_ACTIVATION_READY"] = (
        PDD_CONTROLLED_ACTIVATION_STATUS
    )
    status: PDDActivationCheckStatus
    gates: tuple[PDDActivationGateResult, ...]
    blocking_gate: PDDActivationGateName | None
    next_action_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )
    evidence: PDDActivationEvidenceManifest
    rollback: PDDRollbackPlan
    ready_for_separate_activation_authorization: bool
    activation_authorized: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_platform_connected: Literal[False] = False
    real_send_enabled: Literal[False] = False
    evaluated_at: AwareDatetime


class PDDControlledActivationPreflight:
    """Pure offline gate evaluator. It cannot open a browser or transport."""

    def __init__(self, authorizer: RBACAuthorizer | None = None) -> None:
        self._authorizer = authorizer or RBACAuthorizer()

    def evaluate(
        self,
        check: PDDControlledActivationCheckInput,
    ) -> PDDControlledActivationCheckResult:
        evaluations = {
            PDDActivationGateName.PREFLIGHT: self._preflight,
            PDDActivationGateName.CREDENTIAL_CHECK: self._credential,
            PDDActivationGateName.RBAC_CHECK: self._rbac,
            PDDActivationGateName.SELECTOR_CHECK: self._selector,
            PDDActivationGateName.OBSERVATION_MODE: self._observation,
            PDDActivationGateName.HUMAN_APPROVAL: self._human_approval,
        }
        gate_results: list[PDDActivationGateResult] = []
        blocked = False
        for gate in PDD_ACTIVATION_GATE_ORDER:
            if blocked:
                result = PDDActivationGateResult(
                    gate=gate,
                    status=PDDActivationGateStatus.NOT_RUN,
                    reason_code="PDD_GATE_PREREQUISITE_NOT_PASSED",
                    checked_at=check.checked_at,
                )
            else:
                passed, reason_code = evaluations[gate](check)
                result = PDDActivationGateResult(
                    gate=gate,
                    status=(
                        PDDActivationGateStatus.PASS
                        if passed
                        else PDDActivationGateStatus.BLOCKED
                    ),
                    reason_code=reason_code,
                    checked_at=check.checked_at,
                )
                blocked = not passed
            gate_results.append(result)

        blocking = next(
            (
                result.gate
                for result in gate_results
                if result.status is PDDActivationGateStatus.BLOCKED
            ),
            None,
        )
        ready = blocking is None
        status = (
            PDDActivationCheckStatus.READY_FOR_SEPARATE_ACTIVATION_AUTHORIZATION
            if ready
            else PDDActivationCheckStatus.BLOCKED
        )
        evidence = self._manifest(check, tuple(gate_results))
        return PDDControlledActivationCheckResult(
            status=status,
            gates=tuple(gate_results),
            blocking_gate=blocking,
            next_action_code=(
                "PDD_REQUEST_SEPARATE_SHORT_LIVED_ACTIVATION_GRANT"
                if ready
                else f"PDD_RESOLVE_{blocking.value}"
            ),
            evidence=evidence,
            rollback=check.plan.rollback,
            ready_for_separate_activation_authorization=ready,
            evaluated_at=check.checked_at,
        )

    @staticmethod
    def _preflight(check: PDDControlledActivationCheckInput) -> tuple[bool, str]:
        runtime = check.runtime.runtime
        transport = check.transport
        within_window = check.plan.window.starts_at <= check.checked_at <= check.plan.window.ends_at
        passed = all(
            (
                within_window,
                transport.origin is PDDTransportOrigin.PRODUCTION,
                transport.activation_state is PDDTransportActivationState.DISABLED,
                not transport.fake_transport,
                transport.read_only,
                not transport.send_supported,
                not transport.real_network_connected,
                not runtime.real_platform_connected,
                not runtime.send_enabled,
                runtime.cursor_backlog == 0,
                not runtime.manual_intervention_required,
                check.gateway.health is PDDGatewayActivationHealth.HEALTHY,
                check.gateway.signed_health_verified,
            )
        )
        return (
            passed,
            "PDD_PREFLIGHT_SAFE_AND_DORMANT" if passed else "PDD_PREFLIGHT_BLOCKED",
        )

    @staticmethod
    def _credential(check: PDDControlledActivationCheckInput) -> tuple[bool, str]:
        snapshot = check.credential
        if snapshot is None:
            return False, "PDD_CREDENTIAL_EVIDENCE_MISSING"
        reference = snapshot.status.reference
        provider_name = reference.provider.casefold()
        provider_is_production = not any(
            marker in provider_name for marker in ("fake", "mock", "sandbox")
        )
        not_expired = (
            snapshot.status.expires_at is None
            or snapshot.status.expires_at > check.checked_at
        )
        account_matches = (
            snapshot.bound_account_reference == check.plan.scope.account_refs[0]
        )
        passed = all(
            (
                snapshot.provider_reference_only,
                not snapshot.provider_exposes_credential_material,
                snapshot.status.available,
                not_expired,
                provider_is_production,
                account_matches,
            )
        )
        return (
            passed,
            "PDD_CREDENTIAL_REFERENCE_READY"
            if passed
            else "PDD_CREDENTIAL_CHECK_BLOCKED",
        )

    def _rbac(self, check: PDDControlledActivationCheckInput) -> tuple[bool, str]:
        snapshot = check.rbac
        if snapshot is None:
            return False, "PDD_RBAC_EVIDENCE_MISSING"
        providers = {
            snapshot.run_operator.identity_provider.casefold(),
            snapshot.scope_supervisor.identity_provider.casefold(),
            snapshot.security_admin.identity_provider.casefold(),
        }
        if any(
            marker in provider
            for provider in providers
            for marker in ("fake", "mock", "sandbox")
        ):
            return False, "PDD_RBAC_IDENTITY_PROVIDER_NOT_PRODUCTION"
        try:
            self._authorizer.require(
                snapshot.run_operator,
                OperatorPermission.APPROVAL_READ,
            )
            self._authorizer.require(
                snapshot.scope_supervisor,
                OperatorPermission.SELECTOR_VERIFY,
            )
            self._authorizer.require(
                snapshot.security_admin,
                OperatorPermission.SAFETY_ADMIN,
            )
        except PermissionError:
            return False, "PDD_RBAC_PERMISSION_BLOCKED"
        expected_roles = (
            OperatorRole.OPERATOR in snapshot.run_operator.roles,
            OperatorRole.SUPERVISOR in snapshot.scope_supervisor.roles,
            OperatorRole.ADMIN in snapshot.security_admin.roles,
        )
        owner_bindings = (
            snapshot.run_operator.principal_id
            == check.plan.window.run_operator_principal_id,
            snapshot.security_admin.principal_id
            == check.plan.window.stop_owner_principal_id,
            snapshot.scope_supervisor.principal_id
            == check.plan.window.recovery_owner_principal_id,
        )
        passed = all(expected_roles + owner_bindings)
        return passed, "PDD_RBAC_READY" if passed else "PDD_RBAC_ROLE_BLOCKED"

    @staticmethod
    def _selector(check: PDDControlledActivationCheckInput) -> tuple[bool, str]:
        if check.selector is None:
            return False, "PDD_SELECTOR_EVIDENCE_MISSING"
        try:
            PDDSelectorActivationGate.require_runtime_token(
                check.selector,
                environment=PDDSelectorRuntimeEnvironment.PRODUCTION,
            )
        except PDDSelectorGovernanceError:
            return False, "PDD_SELECTOR_NOT_PRODUCTION_VERIFIED"
        return True, "PDD_SELECTOR_PRODUCTION_VERIFIED"

    @staticmethod
    def _observation(check: PDDControlledActivationCheckInput) -> tuple[bool, str]:
        safety = check.safety
        passed = all(
            (
                safety.observe_only,
                not safety.auto_reply,
                safety.manual_approval_required,
                not safety.send_enabled,
                not safety.outbound_transport_enabled,
                not safety.execution_creation_enabled,
                not safety.click_send_enabled,
                safety.channel_kill_switch_enabled,
                not safety.customer_message_capture_started,
            )
        )
        return (
            passed,
            "PDD_OBSERVATION_POLICY_SAFE"
            if passed
            else "PDD_OBSERVATION_POLICY_BLOCKED",
        )

    def _human_approval(
        self,
        check: PDDControlledActivationCheckInput,
    ) -> tuple[bool, str]:
        fingerprint = check.plan.fingerprint()
        usable = tuple(
            approval
            for approval in check.approvals
            if approval.plan_fingerprint == fingerprint
            and approval.expires_at > check.checked_at
            and approval.decision is PDDActivationApprovalDecision.APPROVED
        )
        if any(
            approval.decision is PDDActivationApprovalDecision.REJECTED
            for approval in check.approvals
        ):
            return False, "PDD_HUMAN_APPROVAL_REJECTED"
        supervisor = any(
            OperatorRole.SUPERVISOR in approval.principal.roles for approval in usable
        )
        admin = any(OperatorRole.ADMIN in approval.principal.roles for approval in usable)
        distinct = len({approval.principal.principal_id for approval in usable}) >= 2
        passed = supervisor and admin and distinct
        return (
            passed,
            "PDD_HUMAN_APPROVAL_READY"
            if passed
            else "PDD_HUMAN_APPROVAL_MISSING",
        )

    @staticmethod
    def _manifest(
        check: PDDControlledActivationCheckInput,
        gates: tuple[PDDActivationGateResult, ...],
    ) -> PDDActivationEvidenceManifest:
        runtime = check.runtime.runtime
        fingerprint = check.plan.fingerprint()
        manifest_id = f"pdd-activation-evidence-{fingerprint[:20]}"
        return PDDActivationEvidenceManifest(
            manifest_id=manifest_id,
            plan_fingerprint=fingerprint,
            runtime_evidence_reference=check.runtime.evidence_reference,
            runtime_status=runtime.overall,
            session_status=runtime.session.health,
            adapter_status=runtime.adapter.health,
            cursor_status=runtime.cursor.health,
            cursor_last_persisted_sequence=runtime.cursor_last_persisted_sequence,
            cursor_last_processed_sequence=runtime.cursor_last_processed_sequence,
            cursor_backlog=runtime.cursor_backlog,
            gateway_evidence_reference=check.gateway.evidence_reference,
            gateway_status=check.gateway.health,
            credential_evidence_reference=(
                check.credential.evidence_reference if check.credential else None
            ),
            selector_state=check.selector.state if check.selector else None,
            selector_evidence_reference=(
                check.selector.verification_evidence_reference
                if check.selector
                else None
            ),
            rbac_evidence_reference=(check.rbac.evidence_reference if check.rbac else None),
            gate_results=gates,
            captured_at=check.checked_at,
        )


__all__ = [
    "PDD_ACTIVATION_GATE_ORDER",
    "PDD_CONTROLLED_ACTIVATION_STATUS",
    "PDD_CONTROLLED_ACTIVATION_VERSION",
    "PDDActivationApprovalDecision",
    "PDDActivationCheckStatus",
    "PDDActivationEvidenceManifest",
    "PDDActivationGateName",
    "PDDActivationGateResult",
    "PDDActivationGateStatus",
    "PDDActivationHumanApproval",
    "PDDActivationRuntimeSnapshot",
    "PDDActivationScope",
    "PDDActivationWindow",
    "PDDControlledActivationCheckInput",
    "PDDControlledActivationCheckResult",
    "PDDControlledActivationPlan",
    "PDDControlledActivationPreflight",
    "PDDCredentialActivationSnapshot",
    "PDDGatewayActivationHealth",
    "PDDGatewayActivationSnapshot",
    "PDDObservationActivationSafetySnapshot",
    "PDDRBACActivationSnapshot",
    "PDDRollbackAction",
    "PDDRollbackPlan",
    "PDDRollbackStep",
    "default_pdd_rollback_plan",
]
