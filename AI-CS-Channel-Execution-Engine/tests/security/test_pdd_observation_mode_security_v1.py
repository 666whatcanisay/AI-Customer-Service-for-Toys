from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import BrowserLoginState, BrowserSessionState
from channel_engine.pdd_adapter import (
    FakePDDObservationPort,
    PDDObservationBrowserSession,
    PDDObservationModeRuntime,
    PDDObservationSafetyViolation,
    PDDObservedStoreIdentity,
)
from channel_engine.session import CredentialReference


NOW = datetime(2026, 8, 5, 19, 0, tzinfo=timezone.utc)


def minimal_port(*, page_writes: int = 0) -> FakePDDObservationPort:
    return FakePDDObservationPort(
        sessions=(
            PDDObservationBrowserSession(
                browser_session_id="security-session",
                browser_state=BrowserSessionState.LOGIN_REQUIRED,
                login_state=BrowserLoginState.REQUIRED,
                browser_generation=1,
                page_available=True,
                checked_at=NOW,
            ),
        ),
        store_identity=PDDObservedStoreIdentity(
            store_id="synthetic-security-store",
            store_name="Synthetic Security Store",
            source_reference="observation-ref://synthetic/store/security",
            observed_at=NOW,
        ),
        captures=(),
        message_entries=(),
        page_write_operations=page_writes,
    )


def credential() -> CredentialReference:
    return CredentialReference(
        credential_ref="credential-ref://pdd/observation/security",
        provider="windows-credential-manager",
        version="v1",
    )


def test_synthetic_port_requires_explicit_test_override() -> None:
    with pytest.raises(ValueError, match="real read-only platform port"):
        PDDObservationModeRuntime(minimal_port(), credential(), clock=lambda: NOW)


def test_any_page_write_fails_closed_at_composition_time() -> None:
    with pytest.raises(PDDObservationSafetyViolation) as captured:
        PDDObservationModeRuntime(
            minimal_port(page_writes=1),
            credential(),
            allow_synthetic_test_port=True,
            clock=lambda: NOW,
        )
    assert captured.value.error_code == "PDD_OBSERVATION_PORT_UNSAFE"


def test_credential_reference_rejects_embedded_secret_material() -> None:
    with pytest.raises(ValidationError, match="prohibited secret material"):
        CredentialReference(
            credential_ref="credential-ref://pdd/observation?token=forbidden",
            provider="windows-credential-manager",
            version="v1",
        )
