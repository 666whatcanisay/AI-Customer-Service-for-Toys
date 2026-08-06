from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Mapping, Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator

from channel_engine.agent import (
    AgentEnvironment,
    ChannelAgentConfig,
    StoreBinding,
    StoreBindingStatus,
)
from channel_engine.browser import (
    BrowserLoginState,
    BrowserPageContext,
    BrowserSession,
    BrowserSessionState,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorKey,
)

from .models import PilotModel


PDD_PILOT_ENV_CONTRACT_VERSION = "1.0"
_MAX_PILOT_ENV_CONFIG_BYTES = 1_048_576


class PilotEnvironmentTransportMode(StrEnum):
    DISABLED = "DISABLED"
    REAL_RECEIVE_ONLY = "REAL_RECEIVE_ONLY"


class PilotEnvironmentCheckStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class PilotEnvironmentFinalStatus(StrEnum):
    READY = "PDD_PILOT_ENV_READY"
    BLOCKED = "PDD_PILOT_ENV_BLOCKED"


class PilotGatewayVerification(PilotModel):
    endpoint: str = Field(min_length=1, max_length=512)
    client_id: str = Field(min_length=1, max_length=128)
    key_id: str = Field(min_length=1, max_length=128)
    decision_route: bool
    health_route: bool
    signed_health_verified: bool
    health_status: Literal["HEALTHY", "UNHEALTHY"]
    contract_version: str = Field(min_length=1, max_length=64)
    gateway_version: str | None = Field(default=None, max_length=128)
    capability_version: str | None = Field(default=None, max_length=128)
    real_ai_cs_connected: bool
    secret_persisted_by_verifier: Literal[False] = False
    decision_requested: Literal[False] = False
    verified_at: AwareDatetime


class PilotEnvironmentConfig(PilotModel):
    agent: ChannelAgentConfig
    gateway_client_id: Literal["channel-engine"] = "channel-engine"
    gateway_key_id: str = Field(
        default="pilot-env-v1",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    browser_profile_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    merchant_chat_url: str = Field(min_length=1, max_length=2048)
    selector_contract_id: Literal["pdd:merchant_chat:v1"] = "pdd:merchant_chat:v1"
    selector_activation_requested: Literal[False] = False
    inbound_transport_mode: PilotEnvironmentTransportMode = (
        PilotEnvironmentTransportMode.DISABLED
    )
    inbound_transport_name: str | None = Field(default=None, max_length=128)
    outbound_transport_enabled: Literal[False] = False
    customer_message_read_enabled: Literal[False] = False
    automatic_login: Literal[False] = False
    auto_reply: Literal[False] = False
    manual_approval: Literal[True] = True

    @field_validator("merchant_chat_url")
    @classmethod
    def validate_merchant_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not (
            hostname == "pinduoduo.com" or hostname.endswith(".pinduoduo.com")
        ):
            raise ValueError("Pilot merchant chat must use an official PDD HTTPS host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Pilot merchant chat URL cannot contain credentials/query")
        return value

    @model_validator(mode="after")
    def validate_pilot_safety(self) -> PilotEnvironmentConfig:
        if self.agent.safety.runtime_mode is not AgentEnvironment.PILOT:
            raise ValueError("Pilot Environment requires Agent runtime_mode=PILOT")
        if not self.agent.safety.dry_run or not self.agent.safety.kill_switch:
            raise ValueError(
                "Pilot Environment preparation requires dry_run and kill switch"
            )
        if self.agent.channel.store_binding is not None:
            raise ValueError(
                "Pilot store binding must be discovered after real human login"
            )
        if self.agent.channel.credential_reference is None:
            raise ValueError("Pilot channel requires an opaque credential reference")
        if (
            self.inbound_transport_mode is PilotEnvironmentTransportMode.DISABLED
            and self.inbound_transport_name is not None
        ):
            raise ValueError("disabled Pilot transport cannot name an implementation")
        if self.inbound_transport_name and "fake" in self.inbound_transport_name.casefold():
            raise ValueError("Pilot Environment cannot activate a Fake transport")
        return self

    @property
    def profile_directory(self) -> Path:
        return self.agent.browser.profile_root / self.browser_profile_id


class PilotEnvironmentCheck(PilotModel):
    name: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]{2,63}$",
    )
    status: PilotEnvironmentCheckStatus
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class PilotEnvironmentReadiness(PilotModel):
    final_status: PilotEnvironmentFinalStatus
    generated_at: AwareDatetime
    node_id: str
    profile_directory: Path
    store_binding: Literal["PENDING_PAGE_DISCOVERY"] = "PENDING_PAGE_DISCOVERY"
    selector_state: SelectorContractState
    transports_active: Literal[False] = False
    customer_message_read_enabled: Literal[False] = False
    outbound_transport_enabled: Literal[False] = False
    checks: tuple[PilotEnvironmentCheck, ...]
    blockers: tuple[str, ...]


class PilotEnvironmentService:
    def __init__(self, config: PilotEnvironmentConfig) -> None:
        self.config = config

    def provision_profile_directory(self) -> Path:
        root = self.config.agent.browser.profile_root.resolve()
        target = self.config.profile_directory.resolve()
        if root == target or root not in target.parents:
            raise ValueError("Pilot profile must be a child of the dedicated profile root")
        if target.is_symlink():
            raise ValueError("Pilot profile directory cannot be a symbolic link")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def readiness(
        self,
        gateway: PilotGatewayVerification,
        selector: SelectorContract,
        *,
        generated_at: AwareDatetime,
    ) -> PilotEnvironmentReadiness:
        config = self.config
        checks = (
            self._check(
                "AGENT_NODE",
                bool(config.agent.node_id and config.agent.node_name),
                "PILOT_AGENT_NODE_REGISTERED",
                "PILOT_AGENT_NODE_UNREGISTERED",
            ),
            self._check(
                "GATEWAY_CONTRACT",
                bool(
                    gateway.decision_route
                    and gateway.health_route
                    and gateway.signed_health_verified
                    and gateway.real_ai_cs_connected
                    and gateway.contract_version == "1.0"
                    and gateway.gateway_version == "ai-cs-gateway.v1"
                    and gateway.client_id == config.gateway_client_id
                    and gateway.key_id == config.gateway_key_id
                ),
                "PILOT_GATEWAY_CONTRACT_VERIFIED",
                "PILOT_GATEWAY_CONTRACT_UNVERIFIED",
            ),
            self._check(
                "CHROME_EXECUTABLE",
                config.agent.browser.chrome_path.is_file(),
                "PILOT_CHROME_AVAILABLE",
                "PILOT_CHROME_UNAVAILABLE",
            ),
            self._check(
                "DEDICATED_PROFILE",
                config.profile_directory.is_dir()
                and not config.profile_directory.is_symlink(),
                "PILOT_PROFILE_PROVISIONED",
                "PILOT_PROFILE_NOT_PROVISIONED",
            ),
            self._check(
                "CREDENTIAL_REFERENCE",
                config.agent.channel.credential_reference is not None,
                "PILOT_CREDENTIAL_REFERENCE_REGISTERED",
                "PILOT_CREDENTIAL_REFERENCE_MISSING",
            ),
            self._check(
                "STORE_BINDING",
                config.agent.channel.store_binding is None,
                "PILOT_STORE_BINDING_AWAITS_PAGE_DISCOVERY",
                "PILOT_STORE_BINDING_PREPOPULATED",
            ),
            self._check(
                "SELECTOR_WORKFLOW",
                selector.contract_id == config.selector_contract_id
                and selector.state
                in {SelectorContractState.DRAFT, SelectorContractState.DISCOVERY}
                and not config.selector_activation_requested,
                "PILOT_SELECTOR_DISCOVERY_READY",
                "PILOT_SELECTOR_STATE_UNSAFE",
            ),
            self._check(
                "TRANSPORT_ISOLATION",
                config.inbound_transport_mode
                is PilotEnvironmentTransportMode.DISABLED
                and config.inbound_transport_name is None
                and not config.customer_message_read_enabled
                and not config.outbound_transport_enabled,
                "PILOT_TRANSPORTS_DISABLED",
                "PILOT_TRANSPORT_ISOLATION_FAILED",
            ),
            self._check(
                "SAFETY",
                config.agent.safety.dry_run
                and config.agent.safety.kill_switch
                and not config.automatic_login
                and not config.auto_reply
                and config.manual_approval,
                "PILOT_ENVIRONMENT_SAFETY_ACTIVE",
                "PILOT_ENVIRONMENT_SAFETY_INVALID",
            ),
        )
        blockers = tuple(
            check.reason_code
            for check in checks
            if check.status is PilotEnvironmentCheckStatus.BLOCKED
        )
        return PilotEnvironmentReadiness(
            final_status=(
                PilotEnvironmentFinalStatus.READY
                if not blockers
                else PilotEnvironmentFinalStatus.BLOCKED
            ),
            generated_at=generated_at,
            node_id=config.agent.node_id,
            profile_directory=config.profile_directory,
            selector_state=selector.state,
            checks=checks,
            blockers=blockers,
        )

    @staticmethod
    def _check(
        name: str,
        passed: bool,
        pass_code: str,
        fail_code: str,
    ) -> PilotEnvironmentCheck:
        return PilotEnvironmentCheck(
            name=name,
            status=(
                PilotEnvironmentCheckStatus.PASS
                if passed
                else PilotEnvironmentCheckStatus.BLOCKED
            ),
            reason_code=pass_code if passed else fail_code,
        )


def load_pilot_environment_config(path: str | Path) -> PilotEnvironmentConfig:
    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() != ".json":
        raise ValueError("Pilot Environment config must be JSON")
    raw = source.read_bytes()
    if len(raw) > _MAX_PILOT_ENV_CONFIG_BYTES:
        raise ValueError("Pilot Environment config exceeds one MiB")
    return PilotEnvironmentConfig.model_validate_json(raw)


class PDDStoreIdentityObservation(PilotModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    store_name: str = Field(min_length=1, max_length=160)
    page_context_id: str = Field(min_length=1, max_length=128)
    selector_contract_id: str = Field(min_length=1, max_length=256)
    selector_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    source_reference: str = Field(min_length=1, max_length=256)
    observed_at: AwareDatetime


@runtime_checkable
class PDDStoreIdentitySource(Protocol):
    @property
    def read_only(self) -> bool: ...

    @property
    def real_platform_source(self) -> bool: ...

    def observe(
        self,
        page: BrowserPageContext,
        selector: SelectorContract,
    ) -> PDDStoreIdentityObservation: ...


@runtime_checkable
class BrowserStoreIdentityReadPort(Protocol):
    @property
    def read_only(self) -> bool: ...

    @property
    def real_platform_source(self) -> bool: ...

    def read_values(
        self,
        page: BrowserPageContext,
        bindings: tuple[SelectorBinding, ...],
    ) -> tuple[Mapping[SelectorKey, str], str, AwareDatetime]: ...


class VerifiedSelectorStoreIdentitySource:
    """Reads only STORE_ID/STORE_NAME through a verified selector adapter port."""

    def __init__(self, reader: BrowserStoreIdentityReadPort) -> None:
        if not isinstance(reader, BrowserStoreIdentityReadPort):
            raise TypeError("reader does not implement BrowserStoreIdentityReadPort")
        self._reader = reader

    @property
    def read_only(self) -> bool:
        return self._reader.read_only

    @property
    def real_platform_source(self) -> bool:
        return self._reader.real_platform_source

    def observe(
        self,
        page: BrowserPageContext,
        selector: SelectorContract,
    ) -> PDDStoreIdentityObservation:
        identity_bindings = tuple(
            binding
            for binding in selector.bindings
            if binding.key in {SelectorKey.STORE_ID, SelectorKey.STORE_NAME}
        )
        values, source_reference, observed_at = self._reader.read_values(
            page,
            identity_bindings,
        )
        return PDDStoreIdentityObservation(
            store_id=values[SelectorKey.STORE_ID],
            store_name=values[SelectorKey.STORE_NAME],
            page_context_id=page.page_context_id,
            selector_contract_id=selector.contract_id,
            selector_fingerprint=selector.fingerprint(),
            source_reference=source_reference,
            observed_at=observed_at,
        )


class PDDStoreBindingDiscoveryError(RuntimeError):
    pass


class PDDStoreBindingDiscoveryService:
    def __init__(self, credential_reference: str) -> None:
        if not credential_reference.startswith(("credential-ref://", "secret-ref://")):
            raise ValueError("store discovery accepts credential references only")
        self._credential_reference = credential_reference

    def discover(
        self,
        session: BrowserSession,
        selector: SelectorContract,
        source: PDDStoreIdentitySource,
    ) -> StoreBinding:
        if (
            session.state is not BrowserSessionState.ACTIVE
            or session.login_state is not BrowserLoginState.AUTHENTICATED
            or session.page_context is None
        ):
            raise PDDStoreBindingDiscoveryError(
                "store identity requires an authenticated ACTIVE browser session"
            )
        if (
            selector.state is not SelectorContractState.VERIFIED
            or SelectorCapability.STORE_IDENTITY not in selector.capabilities
        ):
            raise PDDStoreBindingDiscoveryError(
                "store identity requires a VERIFIED STORE_IDENTITY selector contract"
            )
        if not source.read_only or not source.real_platform_source:
            raise PDDStoreBindingDiscoveryError(
                "store identity must come from a real read-only page/API source"
            )
        observation = source.observe(session.page_context, selector)
        if (
            observation.page_context_id != session.page_context.page_context_id
            or observation.selector_contract_id != selector.contract_id
            or observation.selector_fingerprint != selector.fingerprint()
        ):
            raise PDDStoreBindingDiscoveryError(
                "store identity evidence is not bound to the active page/selector"
            )
        lowered = observation.store_id.casefold()
        if any(
            marker in lowered
            for marker in ("placeholder", "must-be-verified", "unknown", "todo")
        ):
            raise PDDStoreBindingDiscoveryError(
                "store identity source returned a placeholder"
            )
        return StoreBinding(
            platform="pdd",
            store_id=observation.store_id,
            store_name=observation.store_name,
            credential_reference=self._credential_reference,
            status=StoreBindingStatus.BOUND,
        )


__all__ = [
    "BrowserStoreIdentityReadPort",
    "PDD_PILOT_ENV_CONTRACT_VERSION",
    "PDDStoreBindingDiscoveryError",
    "PDDStoreBindingDiscoveryService",
    "PDDStoreIdentityObservation",
    "PDDStoreIdentitySource",
    "PilotEnvironmentCheck",
    "PilotEnvironmentCheckStatus",
    "PilotEnvironmentConfig",
    "PilotEnvironmentFinalStatus",
    "PilotEnvironmentReadiness",
    "PilotEnvironmentService",
    "PilotEnvironmentTransportMode",
    "PilotGatewayVerification",
    "VerifiedSelectorStoreIdentitySource",
    "load_pilot_environment_config",
]
