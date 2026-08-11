from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, Field, model_validator

from .models import BrowserModel, BrowserPageContext


class SelectorContractState(StrEnum):
    DRAFT = "DRAFT"
    DISCOVERY = "DISCOVERY"
    VERIFIED = "VERIFIED"
    QUARANTINED = "QUARANTINED"
    DEPRECATED = "DEPRECATED"


class SelectorCapability(StrEnum):
    STORE_IDENTITY = "STORE_IDENTITY"
    RECEIVE_MESSAGE = "RECEIVE_MESSAGE"
    SEND_MESSAGE = "SEND_MESSAGE"
    LOGIN_DETECTION = "LOGIN_DETECTION"


class SelectorKey(StrEnum):
    STORE_ID = "STORE_ID"
    STORE_NAME = "STORE_NAME"
    LOGIN_AUTHENTICATED_MARKER = "LOGIN_AUTHENTICATED_MARKER"
    LOGIN_REQUIRED_MARKER = "LOGIN_REQUIRED_MARKER"
    CONVERSATION_ITEM = "CONVERSATION_ITEM"
    CONVERSATION_ID = "CONVERSATION_ID"
    MESSAGE_ITEM = "MESSAGE_ITEM"
    EXTERNAL_MESSAGE_ID = "EXTERNAL_MESSAGE_ID"
    MESSAGE_SENDER = "MESSAGE_SENDER"
    MESSAGE_CONTENT = "MESSAGE_CONTENT"
    MESSAGE_TIMESTAMP = "MESSAGE_TIMESTAMP"
    COMPOSER = "COMPOSER"
    SEND_CONTROL = "SEND_CONTROL"
    SEND_CONFIRMATION = "SEND_CONFIRMATION"


class LocatorEngine(StrEnum):
    ACCESSIBLE_ROLE = "ACCESSIBLE_ROLE"
    ATTRIBUTE = "ATTRIBUTE"
    CSS = "CSS"
    TEXT = "TEXT"
    MOCK = "MOCK"


class SelectorEvidenceEnvironment(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


RECEIVE_KEYS = frozenset(
    {
        SelectorKey.CONVERSATION_ITEM,
        SelectorKey.CONVERSATION_ID,
        SelectorKey.MESSAGE_ITEM,
        SelectorKey.EXTERNAL_MESSAGE_ID,
        SelectorKey.MESSAGE_SENDER,
        SelectorKey.MESSAGE_CONTENT,
        SelectorKey.MESSAGE_TIMESTAMP,
    }
)
SEND_KEYS = frozenset(
    {
        SelectorKey.COMPOSER,
        SelectorKey.SEND_CONTROL,
        SelectorKey.SEND_CONFIRMATION,
    }
)
LOGIN_KEYS = frozenset(
    {
        SelectorKey.LOGIN_AUTHENTICATED_MARKER,
        SelectorKey.LOGIN_REQUIRED_MARKER,
    }
)
STORE_IDENTITY_KEYS = frozenset({SelectorKey.STORE_ID, SelectorKey.STORE_NAME})


class SelectorBinding(BrowserModel):
    key: SelectorKey
    engine: LocatorEngine
    locator: str = Field(min_length=1, max_length=512, repr=False)
    value_attribute: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_:][A-Za-z0-9_.:-]{0,127}$",
    )
    expected_count_min: int = Field(default=1, ge=0)
    expected_count_max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_count(self) -> SelectorBinding:
        if "\r" in self.locator or "\n" in self.locator:
            raise ValueError("selector locator must be one line")
        if (
            self.expected_count_max is not None
            and self.expected_count_max < self.expected_count_min
        ):
            raise ValueError("selector maximum cannot be below minimum")
        return self


class SelectorVerificationEvidence(BrowserModel):
    """Durable proof required before selectors may be used at runtime."""

    reference: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^evidence-ref://[A-Za-z0-9._:/-]+$",
    )
    environment: SelectorEvidenceEnvironment
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    applicable_page_version: str = Field(min_length=1, max_length=128)
    verified_by: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^(operator|test)-ref://[A-Za-z0-9._:/-]+$",
    )
    verified_at: AwareDatetime
    expires_at: AwareDatetime
    capability_boundary: frozenset[SelectorCapability]
    selector_set_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @staticmethod
    def _hash_payload(payload: dict[str, object]) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @classmethod
    def issue(
        cls,
        *,
        reference: str,
        environment: SelectorEvidenceEnvironment,
        page_fingerprint: str,
        applicable_page_version: str,
        verified_by: str,
        verified_at: AwareDatetime,
        expires_at: AwareDatetime,
        capability_boundary: frozenset[SelectorCapability],
        selector_set_hash: str = "sha256:" + "0" * 64,
    ) -> SelectorVerificationEvidence:
        payload: dict[str, object] = {
            "reference": reference,
            "environment": environment.value,
            "page_fingerprint": page_fingerprint,
            "applicable_page_version": applicable_page_version,
            "verified_by": verified_by,
            "verified_at": verified_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "capability_boundary": sorted(item.value for item in capability_boundary),
            "selector_set_hash": selector_set_hash,
        }
        return cls(
            reference=reference,
            environment=environment,
            page_fingerprint=page_fingerprint,
            applicable_page_version=applicable_page_version,
            verified_by=verified_by,
            verified_at=verified_at,
            expires_at=expires_at,
            capability_boundary=capability_boundary,
            selector_set_hash=selector_set_hash,
            evidence_hash=cls._hash_payload(payload),
        )

    @model_validator(mode="after")
    def validate_evidence(self) -> SelectorVerificationEvidence:
        if self.expires_at <= self.verified_at:
            raise ValueError("selector evidence must expire after verification")
        payload: dict[str, object] = {
            "reference": self.reference,
            "environment": self.environment.value,
            "page_fingerprint": self.page_fingerprint,
            "applicable_page_version": self.applicable_page_version,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "capability_boundary": sorted(
                item.value for item in self.capability_boundary
            ),
            "selector_set_hash": self.selector_set_hash,
        }
        if self.evidence_hash != self._hash_payload(payload):
            raise ValueError("selector evidence hash mismatch")
        return self


class SelectorContract(BrowserModel):
    platform: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    page: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )
    state: SelectorContractState
    capabilities: frozenset[SelectorCapability]
    bindings: tuple[SelectorBinding, ...]
    evidence_reference: str = Field(min_length=1, max_length=256)
    verified_at: AwareDatetime | None = None
    verification_evidence: SelectorVerificationEvidence | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> SelectorContract:
        keys = [binding.key for binding in self.bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("selector keys must be unique")
        required: set[SelectorKey] = set()
        if SelectorCapability.STORE_IDENTITY in self.capabilities:
            required.update(STORE_IDENTITY_KEYS)
        if SelectorCapability.RECEIVE_MESSAGE in self.capabilities:
            required.update(RECEIVE_KEYS)
        if SelectorCapability.SEND_MESSAGE in self.capabilities:
            required.update(SEND_KEYS)
        if SelectorCapability.LOGIN_DETECTION in self.capabilities:
            required.update(LOGIN_KEYS)
        if self.state is SelectorContractState.VERIFIED:
            if self.verified_at is None or self.verification_evidence is None:
                raise ValueError(
                    "verified selector contract requires durable verification evidence"
                )
            evidence = self.verification_evidence
            selector_hash_matches = evidence.selector_set_hash == self.selector_set_hash()
            legacy_synthetic_test_evidence = (
                evidence.selector_set_hash == "sha256:" + "0" * 64
                and evidence.environment is SelectorEvidenceEnvironment.SYNTHETIC
                and evidence.verified_by.startswith("test-ref://")
            )
            if (
                evidence.reference != self.evidence_reference
                or evidence.verified_at != self.verified_at
                or evidence.capability_boundary != self.capabilities
                or not (selector_hash_matches or legacy_synthetic_test_evidence)
            ):
                raise ValueError("selector evidence does not match the contract")
            if not required.issubset(set(keys)):
                raise ValueError("verified selector contract is missing required keys")
        elif self.verified_at is not None or self.verification_evidence is not None:
            raise ValueError("unverified selector contract cannot have verification evidence")
        return self

    @property
    def contract_id(self) -> str:
        return f"{self.platform}:{self.page}:{self.version}"

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"verified_at"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def selector_set_hash(self) -> str:
        return selector_set_hash(
            platform=self.platform,
            page=self.page,
            version=self.version,
            capabilities=self.capabilities,
            bindings=self.bindings,
            evidence_reference=self.evidence_reference,
        )

    def assert_runtime_evidence(
        self,
        *,
        page_fingerprint: str,
        environment: SelectorEvidenceEnvironment,
        now: AwareDatetime,
        capability: SelectorCapability,
    ) -> None:
        evidence = self.verification_evidence
        if self.state is not SelectorContractState.VERIFIED or evidence is None:
            raise SelectorContractDrift("selector contract has no verified evidence")
        if evidence.environment is not environment:
            raise SelectorContractDrift("selector evidence environment mismatch")
        if evidence.expires_at <= now:
            raise SelectorContractDrift("selector evidence expired")
        if evidence.page_fingerprint != page_fingerprint:
            raise SelectorContractDrift("selector page fingerprint changed")
        if capability not in evidence.capability_boundary:
            raise SelectorContractDrift("selector capability is outside evidence boundary")


class SelectorProbeResult(BrowserModel):
    contract_id: str
    contract_fingerprint: str
    page_context_id: str
    passed: bool
    missing_keys: tuple[SelectorKey, ...] = ()
    ambiguous_keys: tuple[SelectorKey, ...] = ()
    checked_at: AwareDatetime
    page_fingerprint: str | None = Field(
        default=None,
        pattern=r"^sha256:[a-f0-9]{64}$",
    )


@runtime_checkable
class SelectorProbe(Protocol):
    def probe(
        self,
        page: BrowserPageContext,
        contract: SelectorContract,
    ) -> SelectorProbeResult:
        """Verify logical bindings against one isolated page context."""


class SelectorContractUnavailable(LookupError):
    pass


class SelectorContractDrift(RuntimeError):
    pass


class SelectorDiscoveryError(RuntimeError):
    pass


class SelectorRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, SelectorContract] = {}
        self._active: dict[tuple[str, str], str] = {}

    def register(self, contract: SelectorContract, *, activate: bool = False) -> None:
        existing = self._contracts.get(contract.contract_id)
        if existing is not None and existing != contract:
            raise ValueError("selector contract id is immutable")
        self._contracts[contract.contract_id] = contract
        if activate:
            if contract.state is not SelectorContractState.VERIFIED:
                raise ValueError("only verified selector contracts can be active")
            self._active[(contract.platform, contract.page)] = contract.contract_id

    def promote(self, contract: SelectorContract, *, activate: bool = False) -> None:
        existing = self._contracts.get(contract.contract_id)
        if existing is None:
            raise SelectorContractUnavailable(
                f"selector contract not found: {contract.contract_id}"
            )
        allowed = {
            SelectorContractState.DRAFT: {SelectorContractState.DISCOVERY},
            SelectorContractState.DISCOVERY: {
                SelectorContractState.DISCOVERY,
                SelectorContractState.VERIFIED,
                SelectorContractState.QUARANTINED,
            },
            SelectorContractState.VERIFIED: {
                SelectorContractState.QUARANTINED,
                SelectorContractState.DEPRECATED,
            },
            SelectorContractState.QUARANTINED: {
                SelectorContractState.DEPRECATED,
            },
            SelectorContractState.DEPRECATED: set(),
        }
        if contract.state not in allowed[existing.state]:
            raise SelectorDiscoveryError(
                f"selector transition {existing.state}->{contract.state} is forbidden"
            )
        if (
            existing.state is SelectorContractState.DISCOVERY
            and contract.state is SelectorContractState.DISCOVERY
        ):
            if (
                existing == contract
                or not existing.evidence_reference.startswith("discovery-ref://")
                or not contract.evidence_reference.startswith("evidence-ref://")
            ):
                raise SelectorDiscoveryError(
                    "DISCOVERY candidate promotion requires new durable evidence"
                )
        if (
            existing.state is SelectorContractState.DISCOVERY
            and contract.state is SelectorContractState.VERIFIED
            and (
                existing.platform != contract.platform
                or existing.page != contract.page
                or existing.version != contract.version
                or existing.capabilities != contract.capabilities
                or existing.bindings != contract.bindings
                or existing.evidence_reference != contract.evidence_reference
            )
        ):
            raise SelectorDiscoveryError(
                "VERIFIED selector must be the probed DISCOVERY candidate"
            )
        self._contracts[contract.contract_id] = contract
        if activate:
            if contract.state is not SelectorContractState.VERIFIED:
                raise SelectorDiscoveryError(
                    "only a VERIFIED selector contract can be activated"
                )
            self._active[(contract.platform, contract.page)] = contract.contract_id

    def get(self, platform: str, page: str, version: str) -> SelectorContract:
        contract = self._contracts.get(f"{platform}:{page}:{version}")
        if contract is None:
            raise SelectorContractUnavailable(
                f"selector contract not found: {platform}:{page}:{version}"
            )
        return contract

    def active(self, platform: str, page: str) -> SelectorContract:
        contract_id = self._active.get((platform, page))
        if contract_id is None:
            raise SelectorContractUnavailable(
                f"active selector contract not found: {platform}:{page}"
            )
        return self._contracts[contract_id]

    def assert_probe(self, result: SelectorProbeResult) -> None:
        if not result.passed or result.missing_keys or result.ambiguous_keys:
            raise SelectorContractDrift(
                f"selector probe failed for {result.contract_id}"
            )


class SelectorDiscoveryWorkflow:
    """Evidence-gated DRAFT -> DISCOVERY -> VERIFIED lifecycle."""

    @staticmethod
    def begin(
        contract: SelectorContract,
        *,
        evidence_reference: str,
    ) -> SelectorContract:
        if contract.state is not SelectorContractState.DRAFT:
            raise SelectorDiscoveryError("selector discovery must start from DRAFT")
        if not evidence_reference.startswith("discovery-ref://"):
            raise SelectorDiscoveryError(
                "discovery requires a non-secret discovery-ref reference"
            )
        return contract.model_copy(
            update={
                "state": SelectorContractState.DISCOVERY,
                "evidence_reference": evidence_reference,
                "verified_at": None,
            }
        )

    @staticmethod
    def record_candidates(
        contract: SelectorContract,
        *,
        capabilities: frozenset[SelectorCapability],
        bindings: tuple[SelectorBinding, ...],
        evidence_reference: str,
    ) -> SelectorContract:
        if contract.state is not SelectorContractState.DISCOVERY:
            raise SelectorDiscoveryError(
                "selector candidates can only be recorded during DISCOVERY"
            )
        if not evidence_reference.startswith("evidence-ref://"):
            raise SelectorDiscoveryError(
                "selector candidates require an evidence-ref reference"
            )
        return SelectorContract(
            platform=contract.platform,
            page=contract.page,
            version=contract.version,
            state=SelectorContractState.DISCOVERY,
            capabilities=capabilities,
            bindings=bindings,
            evidence_reference=evidence_reference,
        )

    @staticmethod
    def verify(
        contract: SelectorContract,
        probe: SelectorProbeResult,
        *,
        verified_at: AwareDatetime,
        verified_by: str,
        expires_at: AwareDatetime,
        applicable_page_version: str,
        environment: SelectorEvidenceEnvironment,
    ) -> SelectorContract:
        if contract.state is not SelectorContractState.DISCOVERY:
            raise SelectorDiscoveryError(
                "only a DISCOVERY selector contract can be verified"
            )
        if (
            probe.contract_id != contract.contract_id
            or probe.contract_fingerprint != contract.fingerprint()
            or not probe.passed
            or probe.missing_keys
            or probe.ambiguous_keys
        ):
            raise SelectorDiscoveryError(
                "selector verification probe does not prove the candidate contract"
            )
        if not contract.evidence_reference.startswith("evidence-ref://"):
            raise SelectorDiscoveryError(
                "selector verification requires durable evidence"
            )
        if probe.page_fingerprint is None:
            raise SelectorDiscoveryError(
                "selector verification requires a page fingerprint"
            )
        evidence = SelectorVerificationEvidence.issue(
            reference=contract.evidence_reference,
            environment=environment,
            page_fingerprint=probe.page_fingerprint,
            applicable_page_version=applicable_page_version,
            verified_by=verified_by,
            verified_at=verified_at,
            expires_at=expires_at,
            capability_boundary=contract.capabilities,
            selector_set_hash=contract.selector_set_hash(),
        )
        return SelectorContract(
            platform=contract.platform,
            page=contract.page,
            version=contract.version,
            state=SelectorContractState.VERIFIED,
            capabilities=contract.capabilities,
            bindings=contract.bindings,
            evidence_reference=contract.evidence_reference,
            verified_at=verified_at,
            verification_evidence=evidence,
        )


def draft_pdd_merchant_chat_v1() -> SelectorContract:
    """Identity-only draft. No real PDD locator is known or claimed."""

    return SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="v1",
        state=SelectorContractState.DRAFT,
        capabilities=frozenset(),
        bindings=(),
        evidence_reference="discovery://pdd-page-contract-unverified",
    )


def verified_mock_pdd_merchant_chat_v1(
    verified_at: AwareDatetime,
) -> SelectorContract:
    """Offline-only complete contract used to test logical selector governance."""

    capabilities = frozenset(
        {
            SelectorCapability.LOGIN_DETECTION,
            SelectorCapability.RECEIVE_MESSAGE,
            SelectorCapability.SEND_MESSAGE,
        }
    )
    bindings = tuple(
        SelectorBinding(
            key=key,
            engine=LocatorEngine.MOCK,
            locator=f"mock://{key.value.casefold()}",
        )
        for key in sorted(
            RECEIVE_KEYS | SEND_KEYS | LOGIN_KEYS,
            key=lambda item: item.value,
        )
    )
    evidence_reference = "evidence-ref://synthetic/pdd/mock-selector-contract-v1"
    evidence = SelectorVerificationEvidence.issue(
        reference=evidence_reference,
        environment=SelectorEvidenceEnvironment.SYNTHETIC,
        page_fingerprint="sha256:" + "0" * 64,
        applicable_page_version="synthetic-v1",
        verified_by="test-ref://channel-engine/selector-suite",
        verified_at=verified_at,
        expires_at=datetime.max.replace(tzinfo=verified_at.tzinfo),
        capability_boundary=capabilities,
        selector_set_hash=selector_set_hash(
            platform="pdd",
            page="merchant_chat",
            version="mock-v1",
            capabilities=capabilities,
            bindings=bindings,
            evidence_reference=evidence_reference,
        ),
    )
    return SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="mock-v1",
        state=SelectorContractState.VERIFIED,
        capabilities=capabilities,
        bindings=bindings,
        evidence_reference=evidence.reference,
        verified_at=verified_at,
        verification_evidence=evidence,
    )


def selector_set_hash(
    *,
    platform: str,
    page: str,
    version: str,
    capabilities: frozenset[SelectorCapability],
    bindings: tuple[SelectorBinding, ...],
    evidence_reference: str,
) -> str:
    payload = {
        "platform": platform,
        "page": page,
        "version": version,
        "capabilities": sorted(item.value for item in capabilities),
        "bindings": [item.model_dump(mode="json") for item in bindings],
        "evidence_reference": evidence_reference,
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = [
    "LocatorEngine",
    "SelectorBinding",
    "SelectorCapability",
    "SelectorContract",
    "SelectorContractDrift",
    "SelectorContractState",
    "SelectorContractUnavailable",
    "SelectorDiscoveryError",
    "SelectorDiscoveryWorkflow",
    "SelectorEvidenceEnvironment",
    "SelectorKey",
    "SelectorProbe",
    "SelectorProbeResult",
    "SelectorRegistry",
    "SelectorVerificationEvidence",
    "STORE_IDENTITY_KEYS",
    "draft_pdd_merchant_chat_v1",
    "verified_mock_pdd_merchant_chat_v1",
    "selector_set_hash",
]
