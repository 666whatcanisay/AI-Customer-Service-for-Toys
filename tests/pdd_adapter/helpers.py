from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from channel_engine.browser.selectors import LocatorEngine
from channel_engine.pdd_adapter import (
    PDD_REQUIRED_OBSERVATION_PURPOSES,
    PDDMessageEnvelope,
    PDDMessageSourceKind,
    PDDRawMetadata,
    PDDSelectorCandidate,
    PDDSelectorGovernance,
    PDDSelectorPurpose,
    PDDSelectorVerificationEvidence,
    PDDVerifiedSelectorToken,
)


NOW = datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verified_selector_token() -> PDDVerifiedSelectorToken:
    draft = PDDSelectorGovernance.draft()
    candidates = tuple(
        PDDSelectorCandidate(
            purpose=purpose,
            engine_hint=LocatorEngine.MOCK,
            locator_fingerprint=digest(f"synthetic-locator:{purpose.value}"),
            evidence_reference=f"evidence-ref://offline/{purpose.value.casefold()}",
            observed_match_count=1,
        )
        for purpose in sorted(
            PDD_REQUIRED_OBSERVATION_PURPOSES,
            key=lambda item: item.value,
        )
    )
    discovery = PDDSelectorGovernance.begin_discovery(
        draft,
        candidates=candidates,
        discovery_reference="discovery-ref://offline/prototype-v1",
        discovered_at=NOW,
    )
    evidence = PDDSelectorVerificationEvidence(
        contract_id=discovery.contract_id,
        contract_fingerprint=discovery.fingerprint(),
        verified_purposes=frozenset(candidate.purpose for candidate in candidates),
        probe_passed=True,
        synthetic_test_data=True,
        evidence_reference="evidence-ref://offline/prototype-verification-v1",
        checked_at=NOW,
    )
    verified = PDDSelectorGovernance.verify(discovery, evidence)
    return PDDSelectorGovernance.require_verified(
        verified,
        synthetic_test_data=True,
    )


def message_envelope(
    *,
    token: PDDVerifiedSelectorToken,
    message_id: str = "synthetic-message-1",
    conversation_id: str = "synthetic-conversation-1",
    content: str = "synthetic customer question",
    store_id: str = "synthetic-store-1",
) -> PDDMessageEnvelope:
    return PDDMessageEnvelope(
        external_message_id=message_id,
        sender="customer",
        content=content,
        timestamp=NOW,
        store_id=store_id,
        conversation_external_id=conversation_id,
        raw_metadata=PDDRawMetadata(
            source_kind=PDDMessageSourceKind.SYNTHETIC_FIXTURE,
            source_event_ref_digest=digest(f"source:{message_id}"),
            payload_digest=digest(f"payload:{message_id}:{content}"),
            cursor_digest=digest("cursor:1"),
            source_sequence=1,
            selector_contract_id=token.contract_id,
            observed_at=NOW,
        ),
    )
