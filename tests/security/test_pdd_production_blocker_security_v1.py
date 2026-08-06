from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import LocatorEngine
from channel_engine.conversation import ConversationService
from channel_engine.execution import PDDHumanApprovalExecutionSandbox
from channel_engine.pdd_adapter import (
    FakePDDMessageReader,
    PDDCapturedMessage,
    PDDMessageObservationRuntime,
    PDDSelectorActivationGate,
    PDDSelectorCandidate,
    PDDSelectorGovernance,
    PDDSelectorGovernanceError,
    PDDSelectorRuntimeEnvironment,
    PDDSelectorVerificationEvidence,
    PDD_REQUIRED_OBSERVATION_PURPOSES,
)
from channel_engine.security import (
    OperatorAccessDenied,
    OperatorPrincipal,
    OperatorRole,
    PDDRBACApprovalExecutionService,
)
from channel_engine.session import (
    CredentialReference,
    CredentialReferenceStatus,
    ReferenceOnlyCredentialProvider,
)


NOW = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)


class MetadataOnlyResolver:
    def __init__(self, status: CredentialReferenceStatus) -> None:
        self.status = status

    def inspect(self, reference: CredentialReference) -> CredentialReferenceStatus:
        assert reference == self.status.reference
        return self.status


def principal(role: OperatorRole, identifier: str) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=identifier,
        roles=frozenset({role}),
        identity_provider="test-identity-provider",
        authenticated_at=NOW,
    )


def waiting_decision(foundation):
    reader = FakePDDMessageReader(store_id="pdd-rbac-store", clock=lambda: NOW)
    reader.enqueue(
        PDDCapturedMessage(
            store_id="pdd-rbac-store",
            conversation_id="pdd-rbac-conversation",
            external_message_id="pdd-rbac-message",
            sender="synthetic-customer",
            content="Synthetic PDD RBAC validation question",
            timestamp=NOW,
            captured_at=NOW,
        )
    )
    runtime = PDDMessageObservationRuntime(
        reader,
        ConversationService(foundation["uow_factory"], foundation["gateway"]),
        foundation["uow_factory"],
        clock=lambda: NOW,
    )
    return runtime.observe_once()[0]


def test_reference_only_credential_provider_never_accepts_material() -> None:
    reference = CredentialReference(
        credential_ref="vault://pdd/production/store-a",
        provider="enterprise-vault",
        version="rotation-7",
    )
    resolver = MetadataOnlyResolver(
        CredentialReferenceStatus(
            reference=reference,
            available=True,
            expires_at=NOW + timedelta(hours=1),
            rotation_version="rotation-7",
        )
    )
    provider = ReferenceOnlyCredentialProvider(
        resolver,
        clock=lambda: NOW,
    )

    lease = provider.acquire(reference)

    assert provider.reference_only is True
    assert provider.exposes_credential_material is False
    assert lease.credential_ref == reference
    assert lease.lease_ref.startswith("credential-lease-ref://")
    serialized = f"{provider!r}|{resolver.status!r}|{lease!r}".casefold()
    for secret in ("cookie=", "token=", "password=", "bearer "):
        assert secret not in serialized
    with pytest.raises(ValidationError, match="userinfo"):
        CredentialReference(
            credential_ref="vault://operator:plaintext@pdd/store-a",
            provider="enterprise-vault",
            version="rotation-7",
        )
    with pytest.raises(ValidationError):
        CredentialReferenceStatus(
            reference=reference,
            available=True,
            rotation_version="rotation-7",
            token="forbidden",  # type: ignore[call-arg]
        )


def test_operator_can_approve_but_only_supervisor_can_trigger_execution(
    foundation,
) -> None:
    observed = waiting_decision(foundation)
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-rbac-worker",
        clock=lambda: NOW,
    )
    protected = PDDRBACApprovalExecutionService(sandbox)
    operator = principal(OperatorRole.OPERATOR, "operator-1")
    supervisor = principal(OperatorRole.SUPERVISOR, "supervisor-1")

    enqueued = protected.approve(observed.decision_id, principal=operator)
    with pytest.raises(OperatorAccessDenied) as denied:
        protected.execute(enqueued.execution_id, principal=operator)

    result = protected.execute(enqueued.execution_id, principal=supervisor)

    assert denied.value.permission.value == "EXECUTION_TRIGGER"
    assert result.safety.customer_message_sent is False
    assert result.safety.real_platform_called is False


def test_selector_lifecycle_is_evidence_bound_and_synthetic_never_activates_production() -> None:
    draft = PDDSelectorGovernance.draft("blocker-resolution-v1")
    with pytest.raises(PDDSelectorGovernanceError):
        PDDSelectorActivationGate.require_runtime_token(
            draft,
            environment=PDDSelectorRuntimeEnvironment.SANDBOX,
        )
    candidates = tuple(
        PDDSelectorCandidate(
            purpose=purpose,
            engine_hint=LocatorEngine.MOCK,
            locator_fingerprint=hashlib.sha256(purpose.value.encode()).hexdigest(),
            evidence_reference=(
                f"evidence-ref://synthetic-selector/{purpose.value.casefold()}"
            ),
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
        discovery_reference="discovery-ref://synthetic-selector/blocker-resolution",
        discovered_at=NOW,
    )
    with pytest.raises(PDDSelectorGovernanceError):
        PDDSelectorActivationGate.require_runtime_token(
            discovery,
            environment=PDDSelectorRuntimeEnvironment.SANDBOX,
        )
    verified = PDDSelectorGovernance.verify(
        discovery,
        PDDSelectorVerificationEvidence(
            contract_id=discovery.contract_id,
            contract_fingerprint=discovery.fingerprint(),
            verified_purposes=frozenset(candidate.purpose for candidate in candidates),
            probe_passed=True,
            synthetic_test_data=True,
            evidence_reference="evidence-ref://synthetic-selector/verification",
            checked_at=NOW,
        ),
    )

    token = PDDSelectorActivationGate.require_runtime_token(
        verified,
        environment=PDDSelectorRuntimeEnvironment.SANDBOX,
    )
    assert token.synthetic_test_data is True
    with pytest.raises(PDDSelectorGovernanceError, match="synthetic"):
        PDDSelectorActivationGate.require_runtime_token(
            verified,
            environment=PDDSelectorRuntimeEnvironment.PRODUCTION,
        )
