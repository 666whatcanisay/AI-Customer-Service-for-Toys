from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from channel_engine.browser.evidence_store import (
    SelectorEvidenceConflict,
    SelectorEvidenceStore,
)
from channel_engine.browser.selectors import (
    SelectorCapability,
    SelectorContractDrift,
    SelectorEvidenceEnvironment,
    verified_mock_pdd_merchant_chat_v1,
)
from channel_engine.storage import create_engine_and_session, create_schema


def test_verified_selector_requires_durable_matching_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'selector.db').as_posix()}"
    )
    create_schema(engine)
    store = SelectorEvidenceStore(sessions)
    contract = verified_mock_pdd_merchant_chat_v1(now)

    store.record(contract, activate=True)
    restored = store.active(
        platform="pdd",
        page="merchant_chat",
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
        page_fingerprint="sha256:" + "0" * 64,
        capability=SelectorCapability.SEND_MESSAGE,
        now=now + timedelta(minutes=1),
    )
    assert restored == contract

    with pytest.raises(SelectorContractDrift, match="fingerprint"):
        store.active(
            platform="pdd",
            page="merchant_chat",
            environment=SelectorEvidenceEnvironment.SYNTHETIC,
            page_fingerprint="sha256:" + "9" * 64,
            capability=SelectorCapability.SEND_MESSAGE,
            now=now + timedelta(minutes=1),
        )
    engine.dispose()


def test_unverified_or_mutated_evidence_cannot_enter_store(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'selector.db').as_posix()}"
    )
    create_schema(engine)
    store = SelectorEvidenceStore(sessions)
    verified = verified_mock_pdd_merchant_chat_v1(now)
    with pytest.raises(SelectorEvidenceConflict, match="VERIFIED"):
        store.record(
            verified.model_copy(
                update={
                    "state": "DISCOVERY",
                    "verified_at": None,
                    "verification_evidence": None,
                }
            )
        )
    store.record(verified)
    changed = verified.model_copy(
        update={"bindings": tuple(reversed(verified.bindings))}
    )
    with pytest.raises(SelectorEvidenceConflict):
        store.record(changed)
    engine.dispose()
