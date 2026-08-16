from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from channel_engine.browser import LocatorEngine
from channel_engine.pdd_adapter import (
    PDDActivationRuntimeSnapshot,
    PDDCredentialActivationSnapshot,
    PDDGatewayActivationHealth,
    PDDGatewayActivationSnapshot,
    PDDGovernanceChannelEvidence,
    PDDGovernanceEvaluationMode,
    PDDGovernanceExecutionEvidence,
    PDDGovernancePlatformEvidence,
    PDDGovernanceRegressionEvidence,
    PDDGovernanceRuntimeEvidence,
    PDDGovernanceSecurityEvidence,
    PDDGovernanceServiceEvidence,
    PDDGovernanceServiceHealth,
    PDDGovernanceSessionStatus,
    PDDGovernanceSystemEvidence,
    PDDProductionGovernanceInput,
    PDDRBACActivationSnapshot,
    PDDReceiveTransportDescriptor,
    PDDRuntimeComponentStatus,
    PDDRuntimeHealth,
    PDDRuntimeStatus,
    PDDSelectorCandidate,
    PDDSelectorContract,
    PDDSelectorState,
    PDDTransportActivationState,
    PDDTransportOrigin,
    PDD_REQUIRED_OBSERVATION_PURPOSES,
    pdd_activation_contract_hash,
    pdd_gateway_contract_hash,
    pdd_governance_contract_hash,
)
from channel_engine.security import OperatorPrincipal, OperatorRole
from channel_engine.session import CredentialReference, CredentialReferenceStatus


NOW = datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)


def principal(role: OperatorRole, identifier: str) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=identifier,
        roles=frozenset({role}),
        identity_provider="enterprise-sso",
        authenticated_at=NOW,
    )


def component(name: str) -> PDDRuntimeComponentStatus:
    return PDDRuntimeComponentStatus(
        component=name,
        health=PDDRuntimeHealth.HEALTHY,
        reason_code=f"PDD_{name}_HEALTHY",
        checked_at=NOW,
    )


def healthy_runtime() -> PDDRuntimeStatus:
    return PDDRuntimeStatus(
        overall=PDDRuntimeHealth.HEALTHY,
        session=component("SESSION"),
        cursor=component("CURSOR"),
        browser=component("BROWSER"),
        adapter=component("ADAPTER"),
        recovery=component("RECOVERY"),
        cursor_last_persisted_sequence=12,
        cursor_last_processed_sequence=12,
        cursor_backlog=0,
        recovery_attempts=0,
        manual_intervention_required=False,
        checked_at=NOW,
    )


def representative_verified_selector() -> PDDSelectorContract:
    candidates = tuple(
        PDDSelectorCandidate(
            purpose=purpose,
            engine_hint=LocatorEngine.ATTRIBUTE,
            locator_fingerprint=hashlib.sha256(purpose.value.encode()).hexdigest(),
            evidence_reference=f"evidence-ref://governance-fixture/{purpose.value.casefold()}",
            observed_match_count=1,
        )
        for purpose in sorted(
            PDD_REQUIRED_OBSERVATION_PURPOSES,
            key=lambda item: item.value,
        )
    )
    return PDDSelectorContract(
        contract_id="pdd:merchant_chat:governance-representative-v1",
        state=PDDSelectorState.VERIFIED,
        candidates=candidates,
        discovery_reference="discovery-ref://governance-fixture/selector",
        discovered_at=NOW - timedelta(minutes=30),
        verified_at=NOW - timedelta(minutes=20),
        verification_evidence_reference=(
            "evidence-ref://governance-fixture/selector-verification"
        ),
        verification_synthetic_test_data=False,
    )


def governance_input(
    *,
    evaluation_mode: PDDGovernanceEvaluationMode = (
        PDDGovernanceEvaluationMode.ACTIVATION_REQUEST
    ),
) -> PDDProductionGovernanceInput:
    reference = CredentialReference(
        credential_ref="vault://pdd/governance/store-001",
        provider="enterprise-vault",
        version="rotation-1",
    )
    return PDDProductionGovernanceInput(
        evaluation_mode=evaluation_mode,
        system=PDDGovernanceSystemEvidence(
            system_version="channel-engine-rc-v1",
            runtime_version="runtime-v1",
            source_commit_sha="b2c64d54987f1f066a02de8e9e667d5cc0f9857c",
            source_tree_clean=True,
            gateway_contract_version="1.0",
            gateway_contract_hash=pdd_gateway_contract_hash(),
            activation_contract_hash=pdd_activation_contract_hash(),
            governance_contract_hash=pdd_governance_contract_hash(),
        ),
        runtime=PDDGovernanceRuntimeEvidence(
            services=(
                PDDGovernanceServiceEvidence(
                    service_name="channel-runtime",
                    version="v1",
                    health=PDDGovernanceServiceHealth.HEALTHY,
                    reason_code="PDD_CHANNEL_RUNTIME_HEALTHY",
                ),
                PDDGovernanceServiceEvidence(
                    service_name="gateway-client",
                    version="v1",
                    health=PDDGovernanceServiceHealth.HEALTHY,
                    reason_code="PDD_GATEWAY_CLIENT_HEALTHY",
                ),
                PDDGovernanceServiceEvidence(
                    service_name="sqlite-runtime",
                    version="v1",
                    health=PDDGovernanceServiceHealth.HEALTHY,
                    reason_code="PDD_SQLITE_RUNTIME_HEALTHY",
                ),
            ),
            runtime=PDDActivationRuntimeSnapshot(
                evidence_reference="runtime-ref://pdd/governance/001",
                runtime=healthy_runtime(),
                captured_at=NOW,
            ),
            gateway=PDDGatewayActivationSnapshot(
                evidence_reference="gateway-ref://ai-cs/governance/001",
                health=PDDGatewayActivationHealth.HEALTHY,
                gateway_contract_version="1.0",
                capability_version="1.0",
                signed_health_verified=True,
                checked_at=NOW,
            ),
        ),
        security=PDDGovernanceSecurityEvidence(
            credential=PDDCredentialActivationSnapshot(
                evidence_reference="credential-ref://pdd/governance/001",
                status=CredentialReferenceStatus(
                    reference=reference,
                    available=True,
                    expires_at=NOW + timedelta(hours=1),
                    rotation_version="rotation-1",
                ),
                bound_account_reference="account-ref://pdd/governance/001",
                provider_reference_only=True,
                provider_exposes_credential_material=False,
                inspected_at=NOW,
            ),
            rbac=PDDRBACActivationSnapshot(
                evidence_reference="rbac-ref://pdd/governance/001",
                run_operator=principal(OperatorRole.OPERATOR, "operator-001"),
                scope_supervisor=principal(
                    OperatorRole.SUPERVISOR,
                    "supervisor-001",
                ),
                security_admin=principal(OperatorRole.ADMIN, "admin-001"),
                checked_at=NOW,
            ),
        ),
        channel=PDDGovernanceChannelEvidence(
            adapter_registered=True,
            adapter_health=PDDGovernanceServiceHealth.HEALTHY,
            session_status=PDDGovernanceSessionStatus.CONNECTED,
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
            selector=representative_verified_selector(),
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
            total=480,
            passed=480,
            failed=0,
            warnings=1,
            pytest_pass=True,
            compileall_pass=True,
            security_scan_pass=True,
            contract_pass=True,
            checked_at=NOW,
        ),
        checked_at=NOW,
    )


__all__ = [
    "NOW",
    "governance_input",
    "healthy_runtime",
    "principal",
    "representative_verified_selector",
]
