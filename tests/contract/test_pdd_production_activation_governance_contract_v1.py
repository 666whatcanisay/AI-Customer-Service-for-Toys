from __future__ import annotations

from channel_engine.pdd_adapter import (
    PDD_PRODUCTION_ACTIVATION_GOVERNANCE_STATUS,
    PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION,
    PDD_PRODUCTION_GATE_ORDER,
    PDDActivationEvidenceBundle,
    PDDActivationGovernanceRecord,
    PDDProductionGovernanceDecisionResult,
    PDDProductionGovernanceInput,
)


def test_governance_contract_is_versioned_and_gate_order_is_frozen() -> None:
    assert PDD_PRODUCTION_ACTIVATION_GOVERNANCE_VERSION == "1.0"
    assert PDD_PRODUCTION_ACTIVATION_GOVERNANCE_STATUS == (
        "PDD_PRODUCTION_ACTIVATION_GOVERNANCE_READY"
    )
    assert [gate.value for gate in PDD_PRODUCTION_GATE_ORDER] == [
        "RUNTIME",
        "SECURITY",
        "CHANNEL",
        "EXECUTION",
        "PLATFORM",
    ]
    assert PDDProductionGovernanceInput.model_json_schema()["title"] == (
        "PDDProductionGovernanceInput"
    )


def test_every_governance_surface_hard_codes_critical_flags_false() -> None:
    for model in (
        PDDProductionGovernanceInput,
        PDDProductionGovernanceDecisionResult,
        PDDActivationGovernanceRecord,
        PDDActivationEvidenceBundle,
    ):
        properties = model.model_json_schema()["properties"]
        assert properties["real_platform_activation_allowed"]["const"] is False
        assert properties["activation_grant_issued"]["const"] is False
        assert properties["real_send_enabled"]["const"] is False
