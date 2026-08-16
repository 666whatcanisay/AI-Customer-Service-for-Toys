from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.models.entities import utc_now


PDD_PRODUCTION_BLOCKER_RESOLUTION_VERSION = "1.0"


class PDDReadinessModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    readiness_contract_version: Literal["1.0"] = (
        PDD_PRODUCTION_BLOCKER_RESOLUTION_VERSION
    )


class PDDTransportOrigin(StrEnum):
    SANDBOX = "SANDBOX"
    PRODUCTION = "PRODUCTION"


class PDDTransportActivationState(StrEnum):
    DISABLED = "DISABLED"
    READY_FOR_AUTHORIZED_OBSERVATION = "READY_FOR_AUTHORIZED_OBSERVATION"


class PDDReceiveTransportDescriptor(PDDReadinessModel):
    """Composition metadata; it contains no endpoint or credential material."""

    implementation_id: str = Field(min_length=1, max_length=160)
    origin: PDDTransportOrigin
    activation_state: PDDTransportActivationState
    fake_transport: bool
    read_only: Literal[True] = True
    send_supported: Literal[False] = False
    real_network_connected: Literal[False] = False

    @model_validator(mode="after")
    def reject_fake_production_transport(self) -> PDDReceiveTransportDescriptor:
        if self.origin is PDDTransportOrigin.PRODUCTION and self.fake_transport:
            raise ValueError("fake transport cannot enter production composition")
        lowered = self.implementation_id.casefold()
        if self.origin is PDDTransportOrigin.PRODUCTION and any(
            marker in lowered for marker in ("fake", "mock", "sandbox")
        ):
            raise ValueError("production transport identifier is experimental")
        return self


class PDDReadinessGateResult(PDDReadinessModel):
    gate: str = Field(min_length=1, max_length=80)
    passed: bool
    evidence_code: str = Field(min_length=3, max_length=128)


class PDDProductionReadinessResolution(PDDReadinessModel):
    status: Literal["PDD_PRODUCTION_READINESS_UNBLOCKED"]
    gates: tuple[PDDReadinessGateResult, ...]
    structural_blockers: tuple[str, ...]
    real_platform_activation_allowed: Literal[False] = False
    real_send_enabled: Literal[False] = False
    activation_reason: Literal[
        "AUTHORIZED_REAL_TRANSPORT_AND_SELECTOR_EVIDENCE_REQUIRED"
    ] = "AUTHORIZED_REAL_TRANSPORT_AND_SELECTOR_EVIDENCE_REQUIRED"
    evaluated_at: AwareDatetime = Field(default_factory=utc_now)


class PDDProductionReadinessRecheck:
    """Recheck structural blockers without activating or connecting real PDD."""

    @staticmethod
    def evaluate(
        *,
        transport: PDDReceiveTransportDescriptor,
        cursor_safe: bool,
        credential_reference_only: bool,
        rbac_ready: bool,
        selector_evidence_gate_ready: bool,
        monitoring_ready: bool,
    ) -> PDDProductionReadinessResolution:
        gates = (
            PDDReadinessGateResult(
                gate="CURSOR_SAFE",
                passed=cursor_safe,
                evidence_code=(
                    "PDD_CURSOR_PERSIST_COMMIT_ACK"
                    if cursor_safe
                    else "PDD_CURSOR_ORDER_UNSAFE"
                ),
            ),
            PDDReadinessGateResult(
                gate="CREDENTIAL_BOUNDARY",
                passed=credential_reference_only,
                evidence_code=(
                    "PDD_CREDENTIAL_REFERENCE_ONLY"
                    if credential_reference_only
                    else "PDD_CREDENTIAL_BOUNDARY_MISSING"
                ),
            ),
            PDDReadinessGateResult(
                gate="RBAC",
                passed=rbac_ready,
                evidence_code=("PDD_RBAC_ENFORCED" if rbac_ready else "PDD_RBAC_MISSING"),
            ),
            PDDReadinessGateResult(
                gate="SELECTOR_VERIFICATION",
                passed=selector_evidence_gate_ready,
                evidence_code=(
                    "PDD_SELECTOR_EVIDENCE_GATED"
                    if selector_evidence_gate_ready
                    else "PDD_SELECTOR_VERIFICATION_MISSING"
                ),
            ),
            PDDReadinessGateResult(
                gate="MONITORING",
                passed=monitoring_ready,
                evidence_code=(
                    "PDD_RUNTIME_STATUS_COMPLETE"
                    if monitoring_ready
                    else "PDD_RUNTIME_STATUS_MISSING"
                ),
            ),
            PDDReadinessGateResult(
                gate="TRANSPORT_COMPOSITION",
                passed=(
                    transport.origin is PDDTransportOrigin.PRODUCTION
                    and not transport.fake_transport
                    and transport.read_only
                    and not transport.send_supported
                    and not transport.real_network_connected
                ),
                evidence_code="PDD_PRODUCTION_TRANSPORT_DORMANT",
            ),
        )
        blockers = tuple(gate.gate for gate in gates if not gate.passed)
        if blockers:
            raise RuntimeError(
                "PDD production readiness blockers remain: " + ", ".join(blockers)
            )
        return PDDProductionReadinessResolution(
            status="PDD_PRODUCTION_READINESS_UNBLOCKED",
            gates=gates,
            structural_blockers=(),
        )


__all__ = [
    "PDD_PRODUCTION_BLOCKER_RESOLUTION_VERSION",
    "PDDProductionReadinessRecheck",
    "PDDProductionReadinessResolution",
    "PDDReadinessGateResult",
    "PDDReceiveTransportDescriptor",
    "PDDTransportActivationState",
    "PDDTransportOrigin",
]
