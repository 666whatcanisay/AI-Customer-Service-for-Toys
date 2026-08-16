from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from channel_engine.browser.selectors import LocatorEngine
from channel_engine.pdd_adapter._base import PDDPrototypeModel


class PDDSelectorState(StrEnum):
    DRAFT = "DRAFT"
    DISCOVERY = "DISCOVERY"
    VERIFIED = "VERIFIED"


class PDDSelectorRuntimeEnvironment(StrEnum):
    SANDBOX = "SANDBOX"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class PDDSelectorPurpose(StrEnum):
    LOGIN_STATE = "LOGIN_STATE"
    PAGE_STATE = "PAGE_STATE"
    STORE_IDENTITY = "STORE_IDENTITY"
    CONVERSATION_ID = "CONVERSATION_ID"
    MESSAGE_ITEM = "MESSAGE_ITEM"
    MESSAGE_ID = "MESSAGE_ID"
    MESSAGE_SENDER = "MESSAGE_SENDER"
    MESSAGE_CONTENT = "MESSAGE_CONTENT"
    MESSAGE_TIMESTAMP = "MESSAGE_TIMESTAMP"


PDD_REQUIRED_MESSAGE_PURPOSES = frozenset(
    {
        PDDSelectorPurpose.CONVERSATION_ID,
        PDDSelectorPurpose.MESSAGE_ITEM,
        PDDSelectorPurpose.MESSAGE_ID,
        PDDSelectorPurpose.MESSAGE_SENDER,
        PDDSelectorPurpose.MESSAGE_CONTENT,
        PDDSelectorPurpose.MESSAGE_TIMESTAMP,
    }
)
PDD_REQUIRED_OBSERVATION_PURPOSES = frozenset(
    {
        PDDSelectorPurpose.LOGIN_STATE,
        PDDSelectorPurpose.PAGE_STATE,
        PDDSelectorPurpose.STORE_IDENTITY,
    }
) | PDD_REQUIRED_MESSAGE_PURPOSES


class PDDSelectorGovernanceError(RuntimeError):
    pass


class PDDSelectorCandidate(PDDPrototypeModel):
    """A non-executable selector description; no CSS/XPath text is stored."""

    purpose: PDDSelectorPurpose
    engine_hint: LocatorEngine
    locator_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^evidence-ref://[^\s\r\n]+$",
    )
    observed_match_count: int = Field(ge=0)


class PDDSelectorContract(PDDPrototypeModel):
    contract_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^pdd:merchant_chat:[A-Za-z0-9._:-]+$",
    )
    state: PDDSelectorState
    candidates: tuple[PDDSelectorCandidate, ...] = ()
    discovery_reference: str | None = Field(default=None, max_length=255)
    discovered_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None
    verification_evidence_reference: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^evidence-ref://[^\s\r\n]+$",
    )
    verification_synthetic_test_data: bool | None = None

    @model_validator(mode="after")
    def validate_lifecycle_evidence(self) -> PDDSelectorContract:
        purposes = [candidate.purpose for candidate in self.candidates]
        if len(purposes) != len(set(purposes)):
            raise ValueError("selector purposes must be unique")
        if self.state is PDDSelectorState.DRAFT:
            if self.candidates or any(
                value is not None
                for value in (
                    self.discovery_reference,
                    self.discovered_at,
                    self.verified_at,
                    self.verification_evidence_reference,
                    self.verification_synthetic_test_data,
                )
            ):
                raise ValueError("DRAFT selector contract cannot contain discoveries")
        elif self.state is PDDSelectorState.DISCOVERY:
            if (
                not self.candidates
                or self.discovery_reference is None
                or self.discovered_at is None
                or self.verified_at is not None
                or self.verification_evidence_reference is not None
                or self.verification_synthetic_test_data is not None
            ):
                raise ValueError("DISCOVERY selector contract requires candidate evidence")
        else:
            if (
                not self.candidates
                or self.discovery_reference is None
                or self.discovered_at is None
                or self.verified_at is None
                or self.verification_evidence_reference is None
                or self.verification_synthetic_test_data is None
            ):
                raise ValueError("VERIFIED selector contract requires complete evidence")
            if not PDD_REQUIRED_OBSERVATION_PURPOSES.issubset(set(purposes)):
                raise ValueError("VERIFIED selector contract is incomplete")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"verified_at"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class PDDSelectorVerificationEvidence(PDDPrototypeModel):
    contract_id: str = Field(min_length=1, max_length=160)
    contract_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    verified_purposes: frozenset[PDDSelectorPurpose]
    probe_passed: bool
    synthetic_test_data: bool
    evidence_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^evidence-ref://[^\s\r\n]+$",
    )
    checked_at: AwareDatetime


class PDDVerifiedSelectorToken(PDDPrototypeModel):
    """Capability proof consumed by observers; it cannot locate or execute DOM."""

    contract_id: str = Field(min_length=1, max_length=160)
    contract_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    purposes: frozenset[PDDSelectorPurpose]
    verified_at: AwareDatetime
    synthetic_test_data: bool


class PDDSelectorGovernance:
    @staticmethod
    def draft(version: str = "prototype-v1") -> PDDSelectorContract:
        if not version or any(character.isspace() for character in version):
            raise ValueError("selector version must be a non-blank token")
        return PDDSelectorContract(
            contract_id=f"pdd:merchant_chat:{version}",
            state=PDDSelectorState.DRAFT,
        )

    @staticmethod
    def begin_discovery(
        draft: PDDSelectorContract,
        *,
        candidates: tuple[PDDSelectorCandidate, ...],
        discovery_reference: str,
        discovered_at: datetime,
    ) -> PDDSelectorContract:
        if draft.state is not PDDSelectorState.DRAFT:
            raise PDDSelectorGovernanceError("selector discovery must start at DRAFT")
        if not discovery_reference.startswith("discovery-ref://"):
            raise PDDSelectorGovernanceError(
                "selector discovery requires a non-secret discovery reference"
            )
        return PDDSelectorContract(
            contract_id=draft.contract_id,
            state=PDDSelectorState.DISCOVERY,
            candidates=candidates,
            discovery_reference=discovery_reference,
            discovered_at=discovered_at,
        )

    @staticmethod
    def verify(
        discovery: PDDSelectorContract,
        evidence: PDDSelectorVerificationEvidence,
    ) -> PDDSelectorContract:
        if discovery.state is not PDDSelectorState.DISCOVERY:
            raise PDDSelectorGovernanceError(
                "only a DISCOVERY selector contract can be verified"
            )
        candidate_purposes = frozenset(
            candidate.purpose for candidate in discovery.candidates
        )
        if (
            evidence.contract_id != discovery.contract_id
            or evidence.contract_fingerprint != discovery.fingerprint()
            or not evidence.probe_passed
            or evidence.verified_purposes != candidate_purposes
            or not PDD_REQUIRED_OBSERVATION_PURPOSES.issubset(candidate_purposes)
        ):
            raise PDDSelectorGovernanceError(
                "selector verification evidence does not prove the discovery contract"
            )
        return discovery.model_copy(
            update={
                "state": PDDSelectorState.VERIFIED,
                "verified_at": evidence.checked_at,
                "verification_evidence_reference": evidence.evidence_reference,
                "verification_synthetic_test_data": evidence.synthetic_test_data,
            }
        )

    @staticmethod
    def require_verified(
        contract: PDDSelectorContract,
        *,
        synthetic_test_data: bool | None = None,
    ) -> PDDVerifiedSelectorToken:
        if contract.state is not PDDSelectorState.VERIFIED or contract.verified_at is None:
            raise PDDSelectorGovernanceError(
                "selector contract must be VERIFIED before runtime consumption"
            )
        stored_assurance = contract.verification_synthetic_test_data
        if stored_assurance is None:
            raise PDDSelectorGovernanceError(
                "selector contract has no immutable verification assurance"
            )
        if (
            synthetic_test_data is not None
            and synthetic_test_data is not stored_assurance
        ):
            raise PDDSelectorGovernanceError(
                "caller assurance does not match selector verification evidence"
            )
        return PDDVerifiedSelectorToken(
            contract_id=contract.contract_id,
            contract_fingerprint=contract.fingerprint(),
            purposes=frozenset(candidate.purpose for candidate in contract.candidates),
            verified_at=contract.verified_at,
            synthetic_test_data=stored_assurance,
        )


class PDDSelectorActivationGate:
    """Issue a capability token only for the environment proven by evidence."""

    @staticmethod
    def require_runtime_token(
        contract: PDDSelectorContract,
        *,
        environment: PDDSelectorRuntimeEnvironment,
    ) -> PDDVerifiedSelectorToken:
        token = PDDSelectorGovernance.require_verified(contract)
        if (
            environment is PDDSelectorRuntimeEnvironment.PRODUCTION
            and token.synthetic_test_data
        ):
            raise PDDSelectorGovernanceError(
                "synthetic selector evidence cannot activate production runtime"
            )
        return token


__all__ = [
    "PDD_REQUIRED_MESSAGE_PURPOSES",
    "PDD_REQUIRED_OBSERVATION_PURPOSES",
    "PDDSelectorCandidate",
    "PDDSelectorActivationGate",
    "PDDSelectorContract",
    "PDDSelectorGovernance",
    "PDDSelectorGovernanceError",
    "PDDSelectorPurpose",
    "PDDSelectorRuntimeEnvironment",
    "PDDSelectorState",
    "PDDSelectorVerificationEvidence",
    "PDDVerifiedSelectorToken",
]
