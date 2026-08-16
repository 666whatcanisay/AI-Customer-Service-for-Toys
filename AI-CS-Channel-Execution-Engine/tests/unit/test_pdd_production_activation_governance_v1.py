from __future__ import annotations

from datetime import timedelta

import pytest

from channel_engine.pdd_adapter import (
    PDDActivationEvidenceBuilder,
    PDDActivationGovernanceRecord,
    PDDActivationGovernanceState,
    PDDActivationGovernanceStateMachine,
    PDDActivationGovernanceTransitionError,
    PDDGatewayActivationHealth,
    PDDGovernanceEvaluationMode,
    PDDGovernanceServiceHealth,
    PDDGovernanceSessionStatus,
    PDDOfflineGovernanceSnapshotFactory,
    PDDProductionActivationDecision,
    PDDProductionGateArea,
    PDDProductionGateController,
    PDDProductionGateStatus,
    PDDProductionSyntheticDrill,
    PDDRollbackGovernance,
)
from pdd_governance_support import NOW, governance_input


def gate(result, area: PDDProductionGateArea):
    return next(item for item in result.gates if item.area is area)


def test_all_gates_pass_without_issuing_activation_authority() -> None:
    result = PDDProductionGateController().evaluate(governance_input())

    assert result.decision is PDDProductionActivationDecision.READY
    assert all(item.status is PDDProductionGateStatus.PASS for item in result.gates)
    assert result.real_platform_activation_allowed is False
    assert result.activation_grant_issued is False
    assert result.real_send_enabled is False
    assert result.allowed_scope == "OBSERVE_ONLY_AFTER_SEPARATE_AUTHORIZATION"


def test_preparation_evidence_can_be_conditional_without_becoming_authorized() -> None:
    evidence = governance_input(
        evaluation_mode=PDDGovernanceEvaluationMode.PREPARATION
    )
    evidence = evidence.model_copy(
        update={
            "system": evidence.system.model_copy(
                update={"source_tree_clean": False}
            ),
            "security": evidence.security.model_copy(
                update={"credential": None, "rbac": None}
            ),
            "channel": evidence.channel.model_copy(
                update={
                    "adapter_health": PDDGovernanceServiceHealth.STOPPED,
                    "session_status": PDDGovernanceSessionStatus.DISCONNECTED,
                }
            ),
            "platform": evidence.platform.model_copy(update={"selector": None}),
        }
    )

    result = PDDProductionGateController().evaluate(evidence)

    assert result.decision is PDDProductionActivationDecision.CONDITIONAL_READY
    assert any(
        item.status is PDDProductionGateStatus.WARNING for item in result.gates
    )
    assert all(item.status is not PDDProductionGateStatus.BLOCKED for item in result.gates)
    assert result.real_platform_activation_allowed is False


def test_contract_hash_mismatch_blocks_runtime_gate() -> None:
    evidence = governance_input()
    evidence = evidence.model_copy(
        update={
            "system": evidence.system.model_copy(
                update={"governance_contract_hash": "0" * 64}
            )
        }
    )

    result = PDDProductionGateController().evaluate(evidence)

    assert result.decision is PDDProductionActivationDecision.BLOCKED
    runtime_gate = gate(result, PDDProductionGateArea.RUNTIME)
    assert runtime_gate.status is PDDProductionGateStatus.BLOCKED
    assert "PDD_RUNTIME_CONTRACT_HASH_MISMATCH" in runtime_gate.reason_codes


def test_offline_snapshot_is_truthful_conditional_and_dormant() -> None:
    evidence = PDDOfflineGovernanceSnapshotFactory.build(
        system_version="channel-engine-rc-v1",
        runtime_version="runtime-v1",
        source_commit_sha="b2c64d54987f1f066a02de8e9e667d5cc0f9857c",
        source_tree_clean=False,
        regression_total=500,
        regression_passed=500,
        regression_warnings=1,
        checked_at=NOW,
    )

    result = PDDProductionGateController().evaluate(evidence)

    assert result.decision is PDDProductionActivationDecision.CONDITIONAL_READY
    assert evidence.runtime.runtime.runtime.real_platform_connected is False
    assert evidence.runtime.gateway.network_connection_started_by_checker is False
    assert evidence.security.credential is None
    assert evidence.security.rbac is None
    assert evidence.execution.execution_creation_enabled is False
    assert evidence.platform.transport.real_network_connected is False
    assert result.real_platform_activation_allowed is False


@pytest.mark.parametrize(
    ("mutation", "expected_area"),
    (
        ("credential", PDDProductionGateArea.SECURITY),
        ("selector", PDDProductionGateArea.PLATFORM),
        ("gateway", PDDProductionGateArea.RUNTIME),
        ("session", PDDProductionGateArea.CHANNEL),
        ("execution", PDDProductionGateArea.EXECUTION),
    ),
)
def test_activation_request_failures_are_blocked_at_the_responsible_gate(
    mutation: str,
    expected_area: PDDProductionGateArea,
) -> None:
    evidence = governance_input()
    if mutation == "credential":
        evidence = evidence.model_copy(
            update={"security": evidence.security.model_copy(update={"credential": None})}
        )
    elif mutation == "selector":
        evidence = evidence.model_copy(
            update={"platform": evidence.platform.model_copy(update={"selector": None})}
        )
    elif mutation == "gateway":
        evidence = evidence.model_copy(
            update={
                "runtime": evidence.runtime.model_copy(
                    update={
                        "gateway": evidence.runtime.gateway.model_copy(
                            update={
                                "health": PDDGatewayActivationHealth.UNAVAILABLE,
                                "signed_health_verified": False,
                            }
                        )
                    }
                )
            }
        )
    elif mutation == "session":
        evidence = evidence.model_copy(
            update={
                "channel": evidence.channel.model_copy(
                    update={"session_status": PDDGovernanceSessionStatus.EXPIRED}
                )
            }
        )
    else:
        evidence = evidence.model_copy(
            update={
                "execution": evidence.execution.model_copy(
                    update={"execution_creation_enabled": True}
                )
            }
        )

    result = PDDProductionGateController().evaluate(evidence)

    assert result.decision is PDDProductionActivationDecision.BLOCKED
    assert gate(result, expected_area).status is PDDProductionGateStatus.BLOCKED
    assert result.real_platform_activation_allowed is False
    assert result.activation_grant_issued is False
    assert result.real_send_enabled is False


def test_state_machine_allows_ordered_governance_but_never_active() -> None:
    record = PDDActivationGovernanceRecord(governance_id="governance-001")
    for target, reason in (
        (PDDActivationGovernanceState.PREFLIGHT, "PDD_PREFLIGHT_STARTED"),
        (
            PDDActivationGovernanceState.READY_FOR_APPROVAL,
            "PDD_PREFLIGHT_PASSED",
        ),
        (PDDActivationGovernanceState.APPROVED, "PDD_GOVERNANCE_APPROVED"),
    ):
        record = PDDActivationGovernanceStateMachine.transition(
            record,
            target,
            reason_code=reason,
            changed_at=NOW,
        )

    assert record.state is PDDActivationGovernanceState.APPROVED
    assert record.revision == 3
    assert record.real_platform_activation_allowed is False
    assert record.activation_grant_issued is False
    with pytest.raises(
        PDDActivationGovernanceTransitionError,
        match="external activation authority",
    ):
        PDDActivationGovernanceStateMachine.transition(
            record,
            PDDActivationGovernanceState.ACTIVE,
            reason_code="PDD_ACTIVE_REQUESTED",
            changed_at=NOW,
        )


def test_state_machine_rejects_skips_and_revoked_is_terminal() -> None:
    draft = PDDActivationGovernanceRecord(governance_id="governance-002")
    with pytest.raises(PDDActivationGovernanceTransitionError, match="illegal"):
        PDDActivationGovernanceStateMachine.transition(
            draft,
            PDDActivationGovernanceState.APPROVED,
            reason_code="PDD_ILLEGAL_SKIP",
            changed_at=NOW,
        )
    revoked = PDDActivationGovernanceStateMachine.transition(
        draft,
        PDDActivationGovernanceState.REVOKED,
        reason_code="PDD_GOVERNANCE_REVOKED",
        changed_at=NOW,
    )
    with pytest.raises(PDDActivationGovernanceTransitionError, match="illegal"):
        PDDActivationGovernanceStateMachine.transition(
            revoked,
            PDDActivationGovernanceState.PREFLIGHT,
            reason_code="PDD_RESTART_FORBIDDEN",
            changed_at=NOW,
        )


def test_evidence_bundle_is_immutable_hashed_and_data_minimized() -> None:
    evidence = governance_input()
    decision = PDDProductionGateController().evaluate(evidence)

    first = PDDActivationEvidenceBuilder.build(
        evidence,
        decision,
        generated_at=NOW,
    )
    second = PDDActivationEvidenceBuilder.build(
        evidence,
        decision,
        generated_at=NOW,
    )
    serialized = first.model_dump_json().casefold()

    assert first.bundle_hash == second.bundle_hash
    assert first.bundle_id == second.bundle_id
    assert first.contains_credential_material is False
    assert first.contains_customer_data is False
    assert first.real_platform_operations == 0
    assert first.real_platform_activation_allowed is False
    for marker in ("cookie=", "token=", "password=", "bearer "):
        assert marker not in serialized


def test_rollback_order_is_immutable_and_never_deletes_history() -> None:
    rollback = PDDRollbackGovernance.simulate()

    assert [step.action.value for step in rollback.steps] == [
        "STOP_EXECUTION",
        "STOP_ADAPTER",
        "SAVE_AUDIT",
        "PRESERVE_RECEIPTS",
    ]
    assert rollback.execution_stopped is True
    assert rollback.adapter_stopped is True
    assert rollback.audit_saved is True
    assert rollback.receipts_preserved is True
    assert rollback.history_deleted is False
    assert rollback.real_platform_operations == 0


def test_all_synthetic_drill_scenarios_fail_closed() -> None:
    report = PDDProductionSyntheticDrill().run(
        governance_input(),
        generated_at=NOW + timedelta(minutes=1),
    )

    assert len(report.results) == 6
    assert report.all_fail_closed is True
    assert report.real_platform_operations == 0
    assert all(result.fail_closed for result in report.results)
    assert all(result.real_platform_activation_allowed is False for result in report.results)
    assert all(result.activation_grant_issued is False for result in report.results)
    assert all(result.real_send_enabled is False for result in report.results)
    assert report.results[1].actual_blocking_area is PDDProductionGateArea.SECURITY
    assert report.results[2].actual_blocking_area is PDDProductionGateArea.PLATFORM
    assert report.results[3].actual_blocking_area is PDDProductionGateArea.RUNTIME
    assert report.results[4].actual_blocking_area is PDDProductionGateArea.CHANNEL
    assert report.results[5].rollback is not None
