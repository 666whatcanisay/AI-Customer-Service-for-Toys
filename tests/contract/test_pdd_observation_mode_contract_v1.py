from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import SelectorContractState
from channel_engine.pdd_adapter import (
    PDDMessageEntryProbe,
    PDDObservationSafetySnapshot,
    PDDObservationSessionState,
    PDDObservedStoreIdentity,
)


NOW = datetime(2026, 8, 5, 18, 30, tzinfo=timezone.utc)


def test_observation_contract_freezes_states_and_zero_side_effects() -> None:
    assert tuple(item.value for item in PDDObservationSessionState) == (
        "AUTH_REQUIRED",
        "WAITING_USER",
        "CONNECTED",
        "EXPIRED",
    )
    safety = PDDObservationSafetySnapshot()
    assert safety.execution_created == 0
    assert safety.receipt_created == 0
    assert safety.send_operations == 0
    assert safety.browser_write_operations == 0
    assert safety.automatic_login_performed is False
    assert safety.credential_material_persisted is False
    assert safety.customer_content_captured is False
    assert safety.selector_activated is False


def test_message_entry_probe_never_contains_message_or_conversation_payload() -> None:
    probe = PDDMessageEntryProbe(
        page_available=True,
        entry_present=True,
        candidate_count=1,
        observed_at=NOW,
    )
    fields = set(PDDMessageEntryProbe.model_fields)
    assert probe.selector_state is SelectorContractState.DRAFT
    assert "content" not in fields
    assert "message_id" not in fields
    assert "conversation_id" not in fields
    assert "sender" not in fields
    assert "payload" not in fields


def test_store_identity_rejects_placeholders() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        PDDObservedStoreIdentity(
            store_id="placeholder-store",
            store_name="Pending Store",
            source_reference="observation-ref://synthetic/store/pending",
            observed_at=NOW,
        )
