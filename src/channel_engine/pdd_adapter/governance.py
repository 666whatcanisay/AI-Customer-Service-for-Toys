from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from channel_engine.gateway.contract import CONTRACT_VERSION, build_gateway_contract_schema
from channel_engine.models.entities import utc_now

from .activation import (
    PDD_CONTROLLED_ACTIVATION_VERSION,
    PDDActivationRuntimeSnapshot,
    PDDControlledActivationCheckInput,
    PDDCredentialActivationSnapshot,
    PDDGatewayActivationHealth,
    PDDGatewayActivationSnapshot,
    PDDRBACActivationSnapshot,
)
from .readiness import (
    PDDReceiveTransportDescriptor,
    PDDTransportActivationState,
    PDDTransportOrigin,
)
from .runtime_status import PDDRuntimeHealth, PDDRuntimeStatusMonitor
from .selector import PDDSelectorContract, PDDSelectorGovernance, PDDSelectorState


PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION = "1.0"
PDD_PRODUCTION_ACTIVATION_GOVERNANCE_STATUS = (
    "PDD_PRODUCTION_ACTIVATION_GOVERNANCE_READY"
)


def _contains_sensitive_material(value: str) -> bool:
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


class PDDGovernanceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    governance_contract_version: Literal["1.0"] = (
        PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION
    )

    @model_validator(mode="after")
    def reject_sensitive_material(self) -> PDDGovernanceModel:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        if _contains_sensitive_material(payload):
            raise ValueError("governance artifact contains prohibited sensitive material")
        return self


class PDDProductionGateArea(StrEnum):
    RUNTIME = "RUNTIME"
    SECURITY = "SECURITY"
    CHANNEL = "CHANNEL"
    EXECUTION = "EXECUTION"
    PLATFORM = "PLATFORM"


PDD_PRODUCTION_GATE_ORDER = (
    PDDProductionGateArea.RUNTIME,
    PDDProductionGateArea.SECURITY,
    PDDProductionGateArea.CHANNEL,
    PDDProductionGateArea.EXECUTION,
    PDDProductionGateArea.PLATFORM,
)


class PDDProductionGateStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class PDDProductionActivationDecision(StrEnum):
    READY = "READY"
    CONDITIONAL_READY = "CONDITIONAL_READY"
    BLOCKED = "BLOCKED"


class PDDGovernanceEvaluationMode(StrEnum):
    PREPARATION = "PREPARATION"
    ACTIVATION_REQUEST = "ACTIVATION_REQUEST"


class PDDActivationGovernanceState(StrEnum):
    DRAFT = "DRAFT"
    PREFLIGHT = "PREFLIGHT"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REVOKED = "REVOKED"


class PDDGovernanceServiceHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    UNAVAILABLE = "UNAVAILABLE"


class PDDGovernanceSessionStatus(StrEnum):
    CONNECTED = "CONNECTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    DISCONNECTED = "DISCONNECTED"


class PDDGovernanceDrillScenario(StrEnum):
    ALL_GATES_PASS = "ALL_GATES_PASS"
    CREDENTIAL_FAILURE = "CREDENTIAL_FAILURE"
    SELECTOR_UNVERIFIED = "SELECTOR_UNVERIFIED"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ROLLBACK = "ROLLBACK"


class PDDRollbackGovernanceAction(StrEnum):
    STOP_EXECUTION = "STOP_EXECUTION"
    STOP_ADAPTER = "STOP_ADAPTER"
    SAVE_AUDIT = "SAVE_AUDIT"
    PRESERVE_RECEIPTS = "PRESERVE_RECEIPTS"


PDD_ROLLBACK_GOVERNANCE_ORDER = (
    PDDRollbackGovernanceAction.STOP_EXECUTION,
    PDDRollbackGovernanceAction.STOP_ADAPTER,
    PDDRollbackGovernanceAction.SAVE_AUDIT,
    PDDRollbackGovernanceAction.PRESERVE_RECEIPTS,
)


class PDDGovernanceServiceEvidence(PDDGovernanceModel):
    service_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9._-]{0,79}$",
    )
    version: str = Field(min_length=1, max_length=64)
    health: PDDGovernanceServiceHealth
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )


class PDDGovernanceSystemEvidence(PDDGovernanceModel):
    system_version: str = Field(min_length=1, max_length=64)
    runtime_version: str = Field(min_length=1, max_length=64)
    source_commit_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_tree_clean: bool
    gateway_contract_version: str = Field(min_length=1, max_length=64)
    gateway_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    activation_contract_version: Literal["1.0"] = PDD_CONTROLLED_ACTIVATION_VERSION
    activation_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    governance_contract_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class PDDGovernanceRuntimeEvidence(PDDGovernanceModel):
    services: tuple[PDDGovernanceServiceEvidence, ...] = Field(min_length=1)
    runtime: PDDActivationRuntimeSnapshot
    gateway: PDDGatewayActivationSnapshot

    @model_validator(mode="after")
    def require_unique_services(self) -> PDDGovernanceRuntimeEvidence:
        names = tuple(service.service_name for service in self.services)
        if len(names) != len(set(names)):
            raise ValueError("runtime service evidence must be unique")
        return self


class PDDGovernanceSecurityEvidence(PDDGovernanceModel):
    credential: PDDCredentialActivationSnapshot | None
    rbac: PDDRBACActivationSnapshot | None


class PDDGovernanceChannelEvidence(PDDGovernanceModel):
    adapter_registered: bool
    adapter_health: PDDGovernanceServiceHealth
    session_status: PDDGovernanceSessionStatus
    single_store_scope: bool
    single_account_scope: bool
    single_instance_scope: bool
    single_browser_session_scope: bool
    cursor_persist_commit_ack: bool
    cursor_backlog: int = Field(ge=0)


class PDDGovernanceExecutionEvidence(PDDGovernanceModel):
    approval_required: bool
    automatic_approval_enabled: bool
    lease_required: bool
    receipt_required: bool
    receipt_immutable: bool
    failure_receipt_required: bool
    unknown_auto_retry_enabled: bool
    execution_creation_enabled: bool


class PDDGovernancePlatformEvidence(PDDGovernanceModel):
    selector: PDDSelectorContract | None
    transport: PDDReceiveTransportDescriptor
    selector_runtime_execution_enabled: bool
    transport_runtime_activation_enabled: bool


class PDDGovernanceRegressionEvidence(PDDGovernanceModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    warnings: int = Field(ge=0)
    pytest_pass: bool
    compileall_pass: bool
    security_scan_pass: bool
    contract_pass: bool
    checked_at: AwareDatetime

    @model_validator(mode="after")
    def validate_counts(self) -> PDDGovernanceRegressionEvidence:
        if self.passed + self.failed != self.total:
            raise ValueError("regression total must equal passed plus failed")
        return self


class PDDProductionGovernanceInput(PDDGovernanceModel):
    evaluation_mode: PDDGovernanceEvaluationMode
    system: PDDGovernanceSystemEvidence
    runtime: PDDGovernanceRuntimeEvidence
    security: PDDGovernanceSecurityEvidence
    channel: PDDGovernanceChannelEvidence
    execution: PDDGovernanceExecutionEvidence
    platform: PDDGovernancePlatformEvidence
    regression: PDDGovernanceRegressionEvidence
    checked_at: AwareDatetime = Field(default_factory=utc_now)
    real_platform_activation_allowed: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_send_enabled: Literal[False] = False


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def pdd_gateway_contract_hash() -> str:
    return _sha256_json(build_gateway_contract_schema())


def pdd_activation_contract_hash() -> str:
    return _sha256_json(PDDControlledActivationCheckInput.model_json_schema())


def pdd_governance_contract_hash() -> str:
    return _sha256_json(PDDProductionGovernanceInput.model_json_schema())


class PDDProductionGateResult(PDDGovernanceModel):
    area: PDDProductionGateArea
    status: PDDProductionGateStatus
    reason_codes: tuple[str, ...] = Field(min_length=1)
    checked_at: AwareDatetime

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not value or len(value) > 128 or not value.replace("_", "").isalnum():
                raise ValueError("gate reason codes must be uppercase tokens")
            if value != value.upper():
                raise ValueError("gate reason codes must be uppercase tokens")
        return values


class PDDProductionGovernanceDecisionResult(PDDGovernanceModel):
    governance_status: Literal["PDD_PRODUCTION_ACTIVATION_GOVERNANCE_READY"] = (
        PDD_PRODUCTION_ACTIVATION_GOVERNANCE_STATUS
    )
    decision: PDDProductionActivationDecision
    gates: tuple[PDDProductionGateResult, ...]
    allowed_scope: Literal["OBSERVE_ONLY_AFTER_SEPARATE_AUTHORIZATION"] = (
        "OBSERVE_ONLY_AFTER_SEPARATE_AUTHORIZATION"
    )
    forbidden_scopes: tuple[str, ...] = (
        "SEND",
        "AUTO_REPLY",
        "REFUND",
        "ORDER_MODIFICATION",
        "PAYMENT",
        "MULTI_STORE",
    )
    conditions: tuple[str, ...]
    real_platform_activation_allowed: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_send_enabled: Literal[False] = False
    evaluated_at: AwareDatetime


class PDDProductionGateController:
    """Pure decision controller; it exposes no platform or execution action."""

    def evaluate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGovernanceDecisionResult:
        gates = (
            self._runtime_gate(evidence),
            self._security_gate(evidence),
            self._channel_gate(evidence),
            self._execution_gate(evidence),
            self._platform_gate(evidence),
        )
        if tuple(result.area for result in gates) != PDD_PRODUCTION_GATE_ORDER:
            raise RuntimeError("production gate order drifted")
        statuses = {result.status for result in gates}
        if PDDProductionGateStatus.BLOCKED in statuses:
            decision = PDDProductionActivationDecision.BLOCKED
        elif PDDProductionGateStatus.WARNING in statuses:
            decision = PDDProductionActivationDecision.CONDITIONAL_READY
        else:
            decision = PDDProductionActivationDecision.READY
        conditions = tuple(
            code
            for gate in gates
            if gate.status is not PDDProductionGateStatus.PASS
            for code in gate.reason_codes
        )
        return PDDProductionGovernanceDecisionResult(
            decision=decision,
            gates=gates,
            conditions=conditions,
            evaluated_at=evidence.checked_at,
        )

    @staticmethod
    def _status(
        *,
        blocked: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> tuple[PDDProductionGateStatus, tuple[str, ...]]:
        if blocked:
            return PDDProductionGateStatus.BLOCKED, blocked
        if warnings:
            return PDDProductionGateStatus.WARNING, warnings
        return PDDProductionGateStatus.PASS, ("PDD_GATE_PASSED",)

    def _runtime_gate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGateResult:
        blocked: list[str] = []
        warnings: list[str] = []
        if not all(
            (
                evidence.regression.pytest_pass,
                evidence.regression.compileall_pass,
                evidence.regression.security_scan_pass,
                evidence.regression.contract_pass,
                evidence.regression.failed == 0,
            )
        ):
            blocked.append("PDD_RUNTIME_REGRESSION_BLOCKED")
        if (
            evidence.system.gateway_contract_version != CONTRACT_VERSION
            or evidence.system.gateway_contract_hash != pdd_gateway_contract_hash()
            or evidence.system.activation_contract_hash
            != pdd_activation_contract_hash()
            or evidence.system.governance_contract_hash
            != pdd_governance_contract_hash()
        ):
            blocked.append("PDD_RUNTIME_CONTRACT_HASH_MISMATCH")
        if any(
            service.health is PDDGovernanceServiceHealth.UNAVAILABLE
            for service in evidence.runtime.services
        ):
            blocked.append("PDD_RUNTIME_SERVICE_UNAVAILABLE")
        runtime = evidence.runtime.runtime.runtime
        if runtime.manual_intervention_required:
            blocked.append("PDD_RUNTIME_MANUAL_INTERVENTION_REQUIRED")
        if runtime.cursor_backlog > 0:
            blocked.append("PDD_RUNTIME_CURSOR_BACKLOG")
        gateway = evidence.runtime.gateway
        if gateway.health is not PDDGatewayActivationHealth.HEALTHY:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_RUNTIME_GATEWAY_NOT_HEALTHY")
        if not gateway.signed_health_verified:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_RUNTIME_GATEWAY_SIGNATURE_PENDING")
        if not evidence.system.source_tree_clean:
            warnings.append("PDD_RUNTIME_SOURCE_TREE_NOT_SEALED")
        if runtime.overall is PDDRuntimeHealth.BLOCKED:
            blocked.append("PDD_RUNTIME_STATUS_BLOCKED")
        elif runtime.overall in {
            PDDRuntimeHealth.DISABLED,
            PDDRuntimeHealth.DEGRADED,
        }:
            warnings.append("PDD_RUNTIME_NOT_ACTIVE_HEALTHY")
        status, reasons = self._status(
            blocked=tuple(dict.fromkeys(blocked)),
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return PDDProductionGateResult(
            area=PDDProductionGateArea.RUNTIME,
            status=status,
            reason_codes=reasons,
            checked_at=evidence.checked_at,
        )

    def _security_gate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGateResult:
        blocked: list[str] = []
        warnings: list[str] = []
        credential = evidence.security.credential
        if credential is None:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_SECURITY_CREDENTIAL_EVIDENCE_PENDING")
        elif not all(
            (
                credential.provider_reference_only,
                not credential.provider_exposes_credential_material,
                credential.status.available,
                credential.status.expires_at is None
                or credential.status.expires_at > evidence.checked_at,
            )
        ):
            blocked.append("PDD_SECURITY_CREDENTIAL_BOUNDARY_BLOCKED")
        rbac = evidence.security.rbac
        if rbac is None:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_SECURITY_RBAC_EVIDENCE_PENDING")
        status, reasons = self._status(
            blocked=tuple(blocked),
            warnings=tuple(warnings),
        )
        return PDDProductionGateResult(
            area=PDDProductionGateArea.SECURITY,
            status=status,
            reason_codes=reasons,
            checked_at=evidence.checked_at,
        )

    def _channel_gate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGateResult:
        channel = evidence.channel
        blocked: list[str] = []
        warnings: list[str] = []
        if not all(
            (
                channel.single_store_scope,
                channel.single_account_scope,
                channel.single_instance_scope,
                channel.single_browser_session_scope,
            )
        ):
            blocked.append("PDD_CHANNEL_SCOPE_NOT_SINGLETON")
        if not channel.cursor_persist_commit_ack or channel.cursor_backlog > 0:
            blocked.append("PDD_CHANNEL_CURSOR_UNSAFE")
        if not channel.adapter_registered:
            blocked.append("PDD_CHANNEL_ADAPTER_UNREGISTERED")
        if channel.adapter_health is PDDGovernanceServiceHealth.UNAVAILABLE:
            blocked.append("PDD_CHANNEL_ADAPTER_UNAVAILABLE")
        elif channel.adapter_health in {
            PDDGovernanceServiceHealth.STOPPED,
            PDDGovernanceServiceHealth.DEGRADED,
        }:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_CHANNEL_ADAPTER_NOT_HEALTHY")
        if channel.session_status in {
            PDDGovernanceSessionStatus.EXPIRED,
            PDDGovernanceSessionStatus.FAILED,
        }:
            blocked.append("PDD_CHANNEL_SESSION_INVALID")
        elif channel.session_status is not PDDGovernanceSessionStatus.CONNECTED:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_CHANNEL_SESSION_NOT_CONNECTED")
        status, reasons = self._status(
            blocked=tuple(blocked),
            warnings=tuple(warnings),
        )
        return PDDProductionGateResult(
            area=PDDProductionGateArea.CHANNEL,
            status=status,
            reason_codes=reasons,
            checked_at=evidence.checked_at,
        )

    def _execution_gate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGateResult:
        execution = evidence.execution
        passed = all(
            (
                execution.approval_required,
                not execution.automatic_approval_enabled,
                execution.lease_required,
                execution.receipt_required,
                execution.receipt_immutable,
                execution.failure_receipt_required,
                not execution.unknown_auto_retry_enabled,
                not execution.execution_creation_enabled,
            )
        )
        status, reasons = self._status(
            blocked=(() if passed else ("PDD_EXECUTION_SAFETY_BLOCKED",)),
            warnings=(),
        )
        return PDDProductionGateResult(
            area=PDDProductionGateArea.EXECUTION,
            status=status,
            reason_codes=reasons,
            checked_at=evidence.checked_at,
        )

    def _platform_gate(
        self,
        evidence: PDDProductionGovernanceInput,
    ) -> PDDProductionGateResult:
        platform = evidence.platform
        blocked: list[str] = []
        warnings: list[str] = []
        transport = platform.transport
        if not all(
            (
                transport.origin is PDDTransportOrigin.PRODUCTION,
                transport.activation_state is PDDTransportActivationState.DISABLED,
                not transport.fake_transport,
                transport.read_only,
                not transport.send_supported,
                not transport.real_network_connected,
                not platform.transport_runtime_activation_enabled,
                not platform.selector_runtime_execution_enabled,
            )
        ):
            blocked.append("PDD_PLATFORM_TRANSPORT_BOUNDARY_BLOCKED")
        selector = platform.selector
        selector_ready = (
            selector is not None
            and selector.state is PDDSelectorState.VERIFIED
            and selector.verification_synthetic_test_data is False
        )
        if not selector_ready:
            target = (
                blocked
                if evidence.evaluation_mode
                is PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
                else warnings
            )
            target.append("PDD_PLATFORM_SELECTOR_EVIDENCE_PENDING")
        status, reasons = self._status(
            blocked=tuple(blocked),
            warnings=tuple(warnings),
        )
        return PDDProductionGateResult(
            area=PDDProductionGateArea.PLATFORM,
            status=status,
            reason_codes=reasons,
            checked_at=evidence.checked_at,
        )


class PDDActivationGovernanceTransition(PDDGovernanceModel):
    from_state: PDDActivationGovernanceState
    to_state: PDDActivationGovernanceState
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )
    changed_at: AwareDatetime


class PDDActivationGovernanceRecord(PDDGovernanceModel):
    governance_id: str = Field(min_length=1, max_length=128)
    state: PDDActivationGovernanceState = PDDActivationGovernanceState.DRAFT
    revision: int = Field(default=0, ge=0)
    history: tuple[PDDActivationGovernanceTransition, ...] = ()
    real_platform_activation_allowed: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_send_enabled: Literal[False] = False


class PDDActivationGovernanceTransitionError(RuntimeError):
    pass


class PDDActivationGovernanceStateMachine:
    _allowed = {
        PDDActivationGovernanceState.DRAFT: {
            PDDActivationGovernanceState.PREFLIGHT,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.PREFLIGHT: {
            PDDActivationGovernanceState.READY_FOR_APPROVAL,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.READY_FOR_APPROVAL: {
            PDDActivationGovernanceState.APPROVED,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.APPROVED: {
            PDDActivationGovernanceState.ACTIVE,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.ACTIVE: {
            PDDActivationGovernanceState.PAUSED,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.PAUSED: {
            PDDActivationGovernanceState.ACTIVE,
            PDDActivationGovernanceState.REVOKED,
        },
        PDDActivationGovernanceState.REVOKED: set(),
    }

    @classmethod
    def transition(
        cls,
        record: PDDActivationGovernanceRecord,
        target: PDDActivationGovernanceState,
        *,
        reason_code: str,
        changed_at: AwareDatetime,
    ) -> PDDActivationGovernanceRecord:
        if target not in cls._allowed[record.state]:
            raise PDDActivationGovernanceTransitionError(
                f"illegal governance transition {record.state}->{target}"
            )
        if target is PDDActivationGovernanceState.ACTIVE:
            raise PDDActivationGovernanceTransitionError(
                "ACTIVE requires an external activation authority and grant"
            )
        transition = PDDActivationGovernanceTransition(
            from_state=record.state,
            to_state=target,
            reason_code=reason_code,
            changed_at=changed_at,
        )
        return record.model_copy(
            update={
                "state": target,
                "revision": record.revision + 1,
                "history": record.history + (transition,),
            }
        )


class PDDRollbackGovernanceStep(PDDGovernanceModel):
    sequence: int = Field(ge=1, le=4)
    action: PDDRollbackGovernanceAction
    result_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
    )


class PDDRollbackGovernanceResult(PDDGovernanceModel):
    steps: tuple[PDDRollbackGovernanceStep, ...]
    execution_stopped: Literal[True] = True
    adapter_stopped: Literal[True] = True
    audit_saved: Literal[True] = True
    receipts_preserved: Literal[True] = True
    history_deleted: Literal[False] = False
    real_platform_operations: Literal[0] = 0

    @model_validator(mode="after")
    def validate_order(self) -> PDDRollbackGovernanceResult:
        if tuple(step.sequence for step in self.steps) != (1, 2, 3, 4):
            raise ValueError("rollback governance steps must be contiguous")
        if tuple(step.action for step in self.steps) != PDD_ROLLBACK_GOVERNANCE_ORDER:
            raise ValueError("rollback governance order is immutable")
        return self


class PDDRollbackGovernance:
    @staticmethod
    def simulate() -> PDDRollbackGovernanceResult:
        return PDDRollbackGovernanceResult(
            steps=tuple(
                PDDRollbackGovernanceStep(
                    sequence=index,
                    action=action,
                    result_code=f"PDD_ROLLBACK_{action.value}_CONFIRMED",
                )
                for index, action in enumerate(
                    PDD_ROLLBACK_GOVERNANCE_ORDER,
                    start=1,
                )
            )
        )


class PDDActivationEvidenceBundle(PDDGovernanceModel):
    bundle_id: str = Field(min_length=1, max_length=128)
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    system: PDDGovernanceSystemEvidence
    runtime: PDDGovernanceRuntimeEvidence
    security: PDDGovernanceSecurityEvidence
    channel: PDDGovernanceChannelEvidence
    execution: PDDGovernanceExecutionEvidence
    platform: PDDGovernancePlatformEvidence
    testing: PDDGovernanceRegressionEvidence
    decision: PDDProductionGovernanceDecisionResult
    generated_at: AwareDatetime
    contains_credential_material: Literal[False] = False
    contains_customer_data: Literal[False] = False
    real_platform_activation_allowed: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_send_enabled: Literal[False] = False
    real_platform_operations: Literal[0] = 0


class PDDActivationEvidenceBuilder:
    @staticmethod
    def contract_hash() -> str:
        return pdd_governance_contract_hash()

    @staticmethod
    def build(
        evidence: PDDProductionGovernanceInput,
        decision: PDDProductionGovernanceDecisionResult,
        *,
        generated_at: AwareDatetime,
    ) -> PDDActivationEvidenceBundle:
        payload = {
            "system": evidence.system.model_dump(mode="json"),
            "runtime": evidence.runtime.model_dump(mode="json"),
            "security": evidence.security.model_dump(mode="json"),
            "channel": evidence.channel.model_dump(mode="json"),
            "execution": evidence.execution.model_dump(mode="json"),
            "platform": evidence.platform.model_dump(mode="json"),
            "testing": evidence.regression.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "generated_at": generated_at.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PDDActivationEvidenceBundle(
            bundle_id=f"pdd-governance-evidence-{digest[:20]}",
            bundle_hash=digest,
            system=evidence.system,
            runtime=evidence.runtime,
            security=evidence.security,
            channel=evidence.channel,
            execution=evidence.execution,
            platform=evidence.platform,
            testing=evidence.regression,
            decision=decision,
            generated_at=generated_at,
        )


class PDDOfflineGovernanceSnapshotFactory:
    """Create a truthful dormant preparation snapshot without external I/O."""

    @staticmethod
    def build(
        *,
        system_version: str,
        runtime_version: str,
        source_commit_sha: str,
        source_tree_clean: bool,
        regression_total: int,
        regression_passed: int,
        regression_warnings: int,
        checked_at: AwareDatetime,
    ) -> PDDProductionGovernanceInput:
        return PDDProductionGovernanceInput(
            evaluation_mode=PDDGovernanceEvaluationMode.PREPARATION,
            system=PDDGovernanceSystemEvidence(
                system_version=system_version,
                runtime_version=runtime_version,
                source_commit_sha=source_commit_sha,
                source_tree_clean=source_tree_clean,
                gateway_contract_version=CONTRACT_VERSION,
                gateway_contract_hash=pdd_gateway_contract_hash(),
                activation_contract_hash=pdd_activation_contract_hash(),
                governance_contract_hash=pdd_governance_contract_hash(),
            ),
            runtime=PDDGovernanceRuntimeEvidence(
                services=(
                    PDDGovernanceServiceEvidence(
                        service_name="governance-control",
                        version=PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION,
                        health=PDDGovernanceServiceHealth.HEALTHY,
                        reason_code="PDD_GOVERNANCE_CONTROL_HEALTHY",
                    ),
                    PDDGovernanceServiceEvidence(
                        service_name="channel-runtime",
                        version=runtime_version,
                        health=PDDGovernanceServiceHealth.STOPPED,
                        reason_code="PDD_CHANNEL_RUNTIME_DORMANT",
                    ),
                    PDDGovernanceServiceEvidence(
                        service_name="gateway-client",
                        version=CONTRACT_VERSION,
                        health=PDDGovernanceServiceHealth.STOPPED,
                        reason_code="PDD_GATEWAY_CLIENT_DORMANT",
                    ),
                ),
                runtime=PDDActivationRuntimeSnapshot(
                    evidence_reference="runtime-ref://pdd/governance/offline",
                    runtime=PDDRuntimeStatusMonitor(
                        clock=lambda: checked_at
                    ).snapshot(),
                    captured_at=checked_at,
                ),
                gateway=PDDGatewayActivationSnapshot(
                    evidence_reference="gateway-ref://ai-cs/governance/not-checked",
                    health=PDDGatewayActivationHealth.NOT_CHECKED,
                    gateway_contract_version=CONTRACT_VERSION,
                    capability_version="not-checked",
                    signed_health_verified=False,
                    checked_at=checked_at,
                ),
            ),
            security=PDDGovernanceSecurityEvidence(
                credential=None,
                rbac=None,
            ),
            channel=PDDGovernanceChannelEvidence(
                adapter_registered=True,
                adapter_health=PDDGovernanceServiceHealth.STOPPED,
                session_status=PDDGovernanceSessionStatus.DISCONNECTED,
                single_store_scope=True,
                single_account_scope=True,
                single_instance_scope=True,
                single_browser_session_scope=True,
                cursor_persist_commit_ack=True,
                cursor_backlog=0,
            ),
            execution=PDDGovernanceExecutionEvidence(
                approval_required=True,
                automatic_approval_enabled=False,
                lease_required=True,
                receipt_required=True,
                receipt_immutable=True,
                failure_receipt_required=True,
                unknown_auto_retry_enabled=False,
                execution_creation_enabled=False,
            ),
            platform=PDDGovernancePlatformEvidence(
                selector=PDDSelectorGovernance.draft("production-governance-v1"),
                transport=PDDReceiveTransportDescriptor(
                    implementation_id="pdd-authorized-receive-boundary-v1",
                    origin=PDDTransportOrigin.PRODUCTION,
                    activation_state=PDDTransportActivationState.DISABLED,
                    fake_transport=False,
                ),
                selector_runtime_execution_enabled=False,
                transport_runtime_activation_enabled=False,
            ),
            regression=PDDGovernanceRegressionEvidence(
                total=regression_total,
                passed=regression_passed,
                failed=regression_total - regression_passed,
                warnings=regression_warnings,
                pytest_pass=regression_total == regression_passed,
                compileall_pass=True,
                security_scan_pass=True,
                contract_pass=True,
                checked_at=checked_at,
            ),
            checked_at=checked_at,
        )


class PDDGovernanceDrillResult(PDDGovernanceModel):
    scenario: PDDGovernanceDrillScenario
    decision: PDDProductionActivationDecision
    expected_blocking_area: PDDProductionGateArea | None
    actual_blocking_area: PDDProductionGateArea | None
    fail_closed: Literal[True] = True
    rollback: PDDRollbackGovernanceResult | None = None
    real_platform_activation_allowed: Literal[False] = False
    activation_grant_issued: Literal[False] = False
    real_send_enabled: Literal[False] = False
    real_platform_operations: Literal[0] = 0


class PDDGovernanceDrillReport(PDDGovernanceModel):
    results: tuple[PDDGovernanceDrillResult, ...]
    all_fail_closed: Literal[True] = True
    generated_at: AwareDatetime
    real_platform_operations: Literal[0] = 0

    @model_validator(mode="after")
    def validate_scenarios(self) -> PDDGovernanceDrillReport:
        if tuple(result.scenario for result in self.results) != tuple(
            PDDGovernanceDrillScenario
        ):
            raise ValueError("synthetic drill must contain all scenarios in order")
        return self


class PDDProductionSyntheticDrill:
    def __init__(self, controller: PDDProductionGateController | None = None) -> None:
        self._controller = controller or PDDProductionGateController()

    def run(
        self,
        baseline: PDDProductionGovernanceInput,
        *,
        generated_at: AwareDatetime,
    ) -> PDDGovernanceDrillReport:
        activation_baseline = baseline.model_copy(
            update={"evaluation_mode": PDDGovernanceEvaluationMode.ACTIVATION_REQUEST}
        )
        scenarios = (
            (
                PDDGovernanceDrillScenario.ALL_GATES_PASS,
                activation_baseline,
                None,
                None,
            ),
            (
                PDDGovernanceDrillScenario.CREDENTIAL_FAILURE,
                activation_baseline.model_copy(
                    update={
                        "security": activation_baseline.security.model_copy(
                            update={"credential": None}
                        )
                    }
                ),
                PDDProductionGateArea.SECURITY,
                None,
            ),
            (
                PDDGovernanceDrillScenario.SELECTOR_UNVERIFIED,
                activation_baseline.model_copy(
                    update={
                        "platform": activation_baseline.platform.model_copy(
                            update={"selector": None}
                        )
                    }
                ),
                PDDProductionGateArea.PLATFORM,
                None,
            ),
            (
                PDDGovernanceDrillScenario.GATEWAY_UNAVAILABLE,
                activation_baseline.model_copy(
                    update={
                        "runtime": activation_baseline.runtime.model_copy(
                            update={
                                "gateway": activation_baseline.runtime.gateway.model_copy(
                                    update={
                                        "health": PDDGatewayActivationHealth.UNAVAILABLE,
                                        "signed_health_verified": False,
                                    }
                                )
                            }
                        )
                    }
                ),
                PDDProductionGateArea.RUNTIME,
                None,
            ),
            (
                PDDGovernanceDrillScenario.SESSION_EXPIRED,
                activation_baseline.model_copy(
                    update={
                        "channel": activation_baseline.channel.model_copy(
                            update={"session_status": PDDGovernanceSessionStatus.EXPIRED}
                        )
                    }
                ),
                PDDProductionGateArea.CHANNEL,
                None,
            ),
            (
                PDDGovernanceDrillScenario.ROLLBACK,
                activation_baseline,
                None,
                PDDRollbackGovernance.simulate(),
            ),
        )
        results: list[PDDGovernanceDrillResult] = []
        for scenario, scenario_input, expected_area, rollback in scenarios:
            decision = self._controller.evaluate(scenario_input)
            actual_area = next(
                (
                    gate.area
                    for gate in decision.gates
                    if gate.status is PDDProductionGateStatus.BLOCKED
                ),
                None,
            )
            if expected_area != actual_area:
                raise RuntimeError(
                    f"synthetic drill {scenario} did not fail closed at expected gate"
                )
            if scenario in {
                PDDGovernanceDrillScenario.ALL_GATES_PASS,
                PDDGovernanceDrillScenario.ROLLBACK,
            } and decision.decision is not PDDProductionActivationDecision.READY:
                raise RuntimeError(f"synthetic drill {scenario} baseline is not READY")
            results.append(
                PDDGovernanceDrillResult(
                    scenario=scenario,
                    decision=decision.decision,
                    expected_blocking_area=expected_area,
                    actual_blocking_area=actual_area,
                    rollback=rollback,
                )
            )
        return PDDGovernanceDrillReport(
            results=tuple(results),
            generated_at=generated_at,
        )


__all__ = [
    "PDD_PRODUCTION_ACTIVATION_GOVERNANCE_STATUS",
    "PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION",
    "PDD_PRODUCTION_GATE_ORDER",
    "PDD_ROLLBACK_GOVERNANCE_ORDER",
    "PDDActivationEvidenceBuilder",
    "PDDActivationEvidenceBundle",
    "PDDActivationGovernanceRecord",
    "PDDActivationGovernanceState",
    "PDDActivationGovernanceStateMachine",
    "PDDActivationGovernanceTransition",
    "PDDActivationGovernanceTransitionError",
    "PDDGovernanceChannelEvidence",
    "PDDGovernanceDrillReport",
    "PDDGovernanceDrillResult",
    "PDDGovernanceDrillScenario",
    "PDDGovernanceEvaluationMode",
    "PDDGovernanceExecutionEvidence",
    "PDDOfflineGovernanceSnapshotFactory",
    "PDDGovernancePlatformEvidence",
    "PDDGovernanceRegressionEvidence",
    "PDDGovernanceRuntimeEvidence",
    "PDDGovernanceSecurityEvidence",
    "PDDGovernanceServiceEvidence",
    "PDDGovernanceServiceHealth",
    "PDDGovernanceSessionStatus",
    "PDDGovernanceSystemEvidence",
    "PDDProductionActivationDecision",
    "PDDProductionGateArea",
    "PDDProductionGateController",
    "PDDProductionGateResult",
    "PDDProductionGateStatus",
    "PDDProductionGovernanceDecisionResult",
    "PDDProductionGovernanceInput",
    "PDDProductionSyntheticDrill",
    "PDDRollbackGovernance",
    "PDDRollbackGovernanceAction",
    "PDDRollbackGovernanceResult",
    "PDDRollbackGovernanceStep",
    "pdd_activation_contract_hash",
    "pdd_gateway_contract_hash",
    "pdd_governance_contract_hash",
]
