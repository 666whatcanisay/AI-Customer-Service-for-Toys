from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import LocatorEngine
from channel_engine.pdd_adapter import (
    PDD_ACTIVATION_GATE_ORDER,
    PDDActivationApprovalDecision,
    PDDActivationCheckStatus,
    PDDActivationGateName,
    PDDActivationGateStatus,
    PDDActivationHumanApproval,
    PDDActivationRuntimeSnapshot,
    PDDActivationScope,
    PDDActivationWindow,
    PDDControlledActivationCheckInput,
    PDDControlledActivationPlan,
    PDDControlledActivationPreflight,
    PDDCredentialActivationSnapshot,
    PDDGatewayActivationHealth,
    PDDGatewayActivationSnapshot,
    PDDObservationActivationSafetySnapshot,
    PDDRBACActivationSnapshot,
    PDDReceiveTransportDescriptor,
    PDDRuntimeStatusMonitor,
    PDDSelectorCandidate,
    PDDSelectorGovernance,
    PDDSelectorVerificationEvidence,
    PDDTransportActivationState,
    PDDTransportOrigin,
    PDD_REQUIRED_OBSERVATION_PURPOSES,
    default_pdd_rollback_plan,
)
from channel_engine.security import OperatorPrincipal, OperatorRole
from channel_engine.session import CredentialReference, CredentialReferenceStatus


NOW = datetime(2026, 8, 5, 17, 0, tzinfo=timezone.utc)


def principal(role: OperatorRole, identifier: str) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=identifier,
        roles=frozenset({role}),
        identity_provider="enterprise-sso",
        authenticated_at=NOW,
    )


def plan() -> PDDControlledActivationPlan:
    return PDDControlledActivationPlan(
        scope=PDDActivationScope(
            activation_id="pdd-controlled-activation-001",
            store_binding_refs=("store-binding-ref://approved-enrollment/001",),
            account_refs=("account-ref://approved-enrollment/001",),
            instance_ids=("pdd-instance-001",),
            browser_session_ids=("pdd-browser-session-001",),
        ),
        window=PDDActivationWindow(
            starts_at=NOW - timedelta(minutes=5),
            ends_at=NOW + timedelta(minutes=55),
            change_reference="change-ref://controlled-activation/001",
            run_operator_principal_id="pdd-operator-001",
            stop_owner_principal_id="pdd-admin-001",
            recovery_owner_principal_id="pdd-supervisor-001",
        ),
        created_by="pdd-activation-preparation-owner",
        created_at=NOW - timedelta(hours=1),
    )


def safe_check(**updates) -> PDDControlledActivationCheckInput:
    active_plan = plan()
    reference = CredentialReference(
        credential_ref="vault://pdd/controlled-activation/store-001",
        provider="enterprise-vault",
        version="rotation-1",
    )
    values = {
        "plan": active_plan,
        "transport": PDDReceiveTransportDescriptor(
            implementation_id="pdd-authorized-receive-boundary-v1",
            origin=PDDTransportOrigin.PRODUCTION,
            activation_state=PDDTransportActivationState.DISABLED,
            fake_transport=False,
        ),
        "runtime": PDDActivationRuntimeSnapshot(
            evidence_reference="runtime-ref://pdd/controlled-activation/001",
            runtime=PDDRuntimeStatusMonitor(clock=lambda: NOW).snapshot(),
            captured_at=NOW,
        ),
        "gateway": PDDGatewayActivationSnapshot(
            evidence_reference="gateway-ref://ai-cs/signed-health/001",
            health=PDDGatewayActivationHealth.HEALTHY,
            gateway_contract_version="1.0",
            capability_version="1.0",
            signed_health_verified=True,
            checked_at=NOW,
        ),
        "credential": PDDCredentialActivationSnapshot(
            evidence_reference="credential-ref://status/controlled-activation/001",
            status=CredentialReferenceStatus(
                reference=reference,
                available=True,
                expires_at=NOW + timedelta(hours=1),
                rotation_version="rotation-1",
            ),
            bound_account_reference=active_plan.scope.account_refs[0],
            provider_reference_only=True,
            provider_exposes_credential_material=False,
            inspected_at=NOW,
        ),
        "rbac": PDDRBACActivationSnapshot(
            evidence_reference="rbac-ref://controlled-activation/001",
            run_operator=principal(OperatorRole.OPERATOR, "pdd-operator-001"),
            scope_supervisor=principal(
                OperatorRole.SUPERVISOR,
                "pdd-supervisor-001",
            ),
            security_admin=principal(OperatorRole.ADMIN, "pdd-admin-001"),
            checked_at=NOW,
        ),
        "selector": PDDSelectorGovernance.draft("controlled-activation-v1"),
        "safety": PDDObservationActivationSafetySnapshot(
            policy_reference="policy-ref://pdd/observe-only/001",
            observe_only=True,
            auto_reply=False,
            manual_approval_required=True,
            send_enabled=False,
            outbound_transport_enabled=False,
            execution_creation_enabled=False,
            click_send_enabled=False,
            channel_kill_switch_enabled=True,
            customer_message_capture_started=False,
            checked_at=NOW,
        ),
        "checked_at": NOW,
    }
    values.update(updates)
    return PDDControlledActivationCheckInput(**values)


def selector_contract(*, synthetic: bool):
    draft = PDDSelectorGovernance.draft("controlled-activation-test-v1")
    candidates = tuple(
        PDDSelectorCandidate(
            purpose=purpose,
            engine_hint=LocatorEngine.MOCK,
            locator_fingerprint=hashlib.sha256(purpose.value.encode()).hexdigest(),
            evidence_reference=f"evidence-ref://selector/{purpose.value.casefold()}",
            observed_match_count=1,
        )
        for purpose in sorted(
            PDD_REQUIRED_OBSERVATION_PURPOSES,
            key=lambda value: value.value,
        )
    )
    discovery = PDDSelectorGovernance.begin_discovery(
        draft,
        candidates=candidates,
        discovery_reference="discovery-ref://selector/controlled-activation-test",
        discovered_at=NOW - timedelta(minutes=20),
    )
    return PDDSelectorGovernance.verify(
        discovery,
        PDDSelectorVerificationEvidence(
            contract_id=discovery.contract_id,
            contract_fingerprint=discovery.fingerprint(),
            verified_purposes=frozenset(
                candidate.purpose for candidate in candidates
            ),
            probe_passed=True,
            synthetic_test_data=synthetic,
            evidence_reference="evidence-ref://selector/verification-test-fixture",
            checked_at=NOW - timedelta(minutes=10),
        ),
    )


def approvals(active_plan: PDDControlledActivationPlan):
    fingerprint = active_plan.fingerprint()
    return (
        PDDActivationHumanApproval(
            approval_reference="approval-ref://controlled-activation/supervisor",
            principal=principal(OperatorRole.SUPERVISOR, "pdd-supervisor-001"),
            decision=PDDActivationApprovalDecision.APPROVED,
            plan_fingerprint=fingerprint,
            reason="批准限定时间窗内的只读观察准备",
            decided_at=NOW - timedelta(minutes=3),
            expires_at=NOW + timedelta(minutes=30),
        ),
        PDDActivationHumanApproval(
            approval_reference="approval-ref://controlled-activation/admin",
            principal=principal(OperatorRole.ADMIN, "pdd-admin-001"),
            decision=PDDActivationApprovalDecision.APPROVED,
            plan_fingerprint=fingerprint,
            reason="安全边界和停止责任人已确认",
            decided_at=NOW - timedelta(minutes=2),
            expires_at=NOW + timedelta(minutes=30),
        ),
    )


def test_scope_and_gate_order_are_singleton_and_immutable() -> None:
    active_plan = plan()

    assert active_plan.ordered_gates == PDD_ACTIVATION_GATE_ORDER
    assert active_plan.real_platform_activation_allowed is False
    assert active_plan.customer_message_read_allowed_by_plan is False
    assert active_plan.activation_grant_issued is False
    with pytest.raises(ValidationError):
        PDDActivationScope(
            activation_id="invalid-multi-store",
            store_binding_refs=(
                "store-binding-ref://approved/001",
                "store-binding-ref://approved/002",
            ),
            account_refs=("account-ref://approved/001",),
            instance_ids=("instance-001",),
            browser_session_ids=("browser-session-001",),
        )


def test_default_rollback_order_is_fail_closed_and_preserves_history() -> None:
    rollback = default_pdd_rollback_plan()

    assert [step.action.value for step in rollback.steps] == [
        "DISABLE_EXECUTION",
        "STOP_ADAPTER",
        "STOP_SESSION",
        "ISOLATE_GATEWAY",
        "SEAL_EVIDENCE",
        "REQUIRE_MANUAL_VERIFICATION",
    ]
    assert all(not step.automatic and not step.destructive for step in rollback.steps)
    assert rollback.preserves_receipts is True
    assert rollback.preserves_events is True
    assert rollback.preserves_audit is True
    assert rollback.automatic_reconnect_after_unknown is False


def test_gate_sequence_stops_at_first_missing_evidence() -> None:
    check = safe_check(credential=None)

    result = PDDControlledActivationPreflight().evaluate(check)

    assert result.status is PDDActivationCheckStatus.BLOCKED
    assert result.gates[0].status is PDDActivationGateStatus.PASS
    assert result.blocking_gate is PDDActivationGateName.CREDENTIAL_CHECK
    assert result.gates[1].reason_code == "PDD_CREDENTIAL_EVIDENCE_MISSING"
    assert all(
        gate.status is PDDActivationGateStatus.NOT_RUN for gate in result.gates[2:]
    )
    assert result.activation_authorized is False
    assert result.activation_grant_issued is False


def test_draft_and_synthetic_selectors_cannot_pass_production_gate() -> None:
    draft_result = PDDControlledActivationPreflight().evaluate(safe_check())
    synthetic_result = PDDControlledActivationPreflight().evaluate(
        safe_check(selector=selector_contract(synthetic=True))
    )

    assert draft_result.blocking_gate is PDDActivationGateName.SELECTOR_CHECK
    assert synthetic_result.blocking_gate is PDDActivationGateName.SELECTOR_CHECK
    assert synthetic_result.gates[3].reason_code == (
        "PDD_SELECTOR_NOT_PRODUCTION_VERIFIED"
    )
    assert synthetic_result.real_platform_connected is False


def test_all_fixture_gates_only_reach_separate_authorization_boundary() -> None:
    # This representative contract exercises the positive branch only. It does not
    # claim real PDD evidence and the evaluator cannot issue a runtime grant.
    active_plan = plan()
    check = safe_check(
        plan=active_plan,
        selector=selector_contract(synthetic=False),
        approvals=approvals(active_plan),
    )

    result = PDDControlledActivationPreflight().evaluate(check)

    assert result.status is (
        PDDActivationCheckStatus.READY_FOR_SEPARATE_ACTIVATION_AUTHORIZATION
    )
    assert all(gate.status is PDDActivationGateStatus.PASS for gate in result.gates)
    assert result.ready_for_separate_activation_authorization is True
    assert result.activation_authorized is False
    assert result.activation_grant_issued is False
    assert result.real_platform_connected is False
    assert result.real_send_enabled is False
    assert result.next_action_code == (
        "PDD_REQUEST_SEPARATE_SHORT_LIVED_ACTIVATION_GRANT"
    )


def test_evidence_manifest_proves_the_checker_has_no_platform_side_effects() -> None:
    result = PDDControlledActivationPreflight().evaluate(safe_check())
    serialized = result.model_dump_json().casefold()

    assert result.evidence.checker_network_operations == 0
    assert result.evidence.checker_browser_operations == 0
    assert result.evidence.checker_customer_messages_read == 0
    assert result.evidence.checker_send_operations == 0
    assert result.evidence.contains_secret_material is False
    assert result.evidence.cursor_backlog == 0
    for marker in ("cookie=", "token=", "password=", "bearer "):
        assert marker not in serialized


def test_human_approval_reason_rejects_secret_material() -> None:
    with pytest.raises(ValidationError, match="secret material"):
        PDDActivationHumanApproval(
            approval_reference="approval-ref://controlled-activation/admin",
            principal=principal(OperatorRole.ADMIN, "pdd-admin-001"),
            decision=PDDActivationApprovalDecision.APPROVED,
            plan_fingerprint=plan().fingerprint(),
            reason="token=must-not-be-recorded",
            decided_at=NOW,
            expires_at=NOW + timedelta(minutes=30),
        )


def test_unsafe_observation_policy_is_blocked_before_human_approval() -> None:
    active_plan = plan()
    unsafe = safe_check(
        plan=active_plan,
        selector=selector_contract(synthetic=False),
        safety=PDDObservationActivationSafetySnapshot(
            policy_reference="policy-ref://pdd/unsafe-test-fixture",
            observe_only=True,
            auto_reply=False,
            manual_approval_required=True,
            send_enabled=False,
            outbound_transport_enabled=False,
            execution_creation_enabled=True,
            click_send_enabled=False,
            channel_kill_switch_enabled=True,
            customer_message_capture_started=False,
            checked_at=NOW,
        ),
        approvals=approvals(active_plan),
    )

    result = PDDControlledActivationPreflight().evaluate(unsafe)

    assert result.blocking_gate is PDDActivationGateName.OBSERVATION_MODE
    assert result.gates[4].reason_code == "PDD_OBSERVATION_POLICY_BLOCKED"
    assert result.gates[5].status is PDDActivationGateStatus.NOT_RUN
    assert result.activation_authorized is False
