from __future__ import annotations

import hashlib
import json
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
            if self.verified_at is None:
                raise ValueError("verified selector contract requires verified_at")
            if not required.issubset(set(keys)):
                raise ValueError("verified selector contract is missing required keys")
        elif self.verified_at is not None:
            raise ValueError("unverified selector contract cannot have verified_at")
        return self

    @property
    def contract_id(self) -> str:
        return f"{self.platform}:{self.page}:{self.version}"

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"verified_at"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class SelectorProbeResult(BrowserModel):
    contract_id: str
    contract_fingerprint: str
    page_context_id: str
    passed: bool
    missing_keys: tuple[SelectorKey, ...] = ()
    ambiguous_keys: tuple[SelectorKey, ...] = ()
    checked_at: AwareDatetime


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
        return SelectorContract(
            platform=contract.platform,
            page=contract.page,
            version=contract.version,
            state=SelectorContractState.VERIFIED,
            capabilities=contract.capabilities,
            bindings=contract.bindings,
            evidence_reference=contract.evidence_reference,
            verified_at=verified_at,
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

    return SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="mock-v1",
        state=SelectorContractState.VERIFIED,
        capabilities=frozenset(
            {
                SelectorCapability.LOGIN_DETECTION,
                SelectorCapability.RECEIVE_MESSAGE,
                SelectorCapability.SEND_MESSAGE,
            }
        ),
        bindings=tuple(
            SelectorBinding(
                key=key,
                engine=LocatorEngine.MOCK,
                locator=f"mock://{key.value.casefold()}",
            )
            for key in sorted(
                RECEIVE_KEYS | SEND_KEYS | LOGIN_KEYS,
                key=lambda item: item.value,
            )
        ),
        evidence_reference="experiment://offline-mock-selector-contract-v1",
        verified_at=verified_at,
    )


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
    "SelectorKey",
    "SelectorProbe",
    "SelectorProbeResult",
    "SelectorRegistry",
    "STORE_IDENTITY_KEYS",
    "draft_pdd_merchant_chat_v1",
    "verified_mock_pdd_merchant_chat_v1",
]
