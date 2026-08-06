from __future__ import annotations

import pytest

from channel_engine.pdd_adapter import (
    PDD_REQUIRED_OBSERVATION_PURPOSES,
    PDDSelectorGovernance,
    PDDSelectorGovernanceError,
    PDDSelectorState,
    PDDSelectorVerificationEvidence,
)

from .helpers import NOW, verified_selector_token


def test_selector_governance_requires_draft_discovery_verified_sequence() -> None:
    draft = PDDSelectorGovernance.draft()
    assert draft.state is PDDSelectorState.DRAFT

    invalid_evidence = PDDSelectorVerificationEvidence(
        contract_id=draft.contract_id,
        contract_fingerprint=draft.fingerprint(),
        verified_purposes=frozenset(PDD_REQUIRED_OBSERVATION_PURPOSES),
        probe_passed=True,
        synthetic_test_data=True,
        evidence_reference="evidence-ref://offline/direct-verification",
        checked_at=NOW,
    )
    with pytest.raises(PDDSelectorGovernanceError, match="DISCOVERY"):
        PDDSelectorGovernance.verify(draft, invalid_evidence)
    with pytest.raises(PDDSelectorGovernanceError, match="VERIFIED"):
        PDDSelectorGovernance.require_verified(
            draft,
            synthetic_test_data=True,
        )

    token = verified_selector_token()
    assert token.purposes == PDD_REQUIRED_OBSERVATION_PURPOSES
    assert token.synthetic_test_data is True


def test_selector_contract_contains_fingerprints_not_executable_locators() -> None:
    token = verified_selector_token()
    dumped = token.model_dump(mode="json")
    assert "locator" not in dumped
    assert "css" not in str(dumped).casefold()
    assert "xpath" not in str(dumped).casefold()
    assert not hasattr(token, "run")
    assert not hasattr(token, "click")
