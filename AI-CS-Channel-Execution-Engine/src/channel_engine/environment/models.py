from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ENVIRONMENT_PROFILE_VERSION = "1.0"
PRODUCTION_CONFIRMATION = "ENABLE_CHANNEL_ENGINE_PRODUCTION"

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
_SENSITIVE_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "COOKIE",
    "PRIVATE_KEY",
)


class EnvironmentProfileError(ValueError):
    pass


class ProductionProfileDisabled(EnvironmentProfileError):
    pass


class EnvironmentProfile(StrEnum):
    MOCK = "mock"
    STAGING = "staging"
    PRODUCTION = "production"


class AdapterMode(StrEnum):
    FAKE = "FAKE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    PRODUCTION_PREPARATION = "PRODUCTION_PREPARATION"


class StagingAction(StrEnum):
    OBSERVE_MESSAGE = "OBSERVE_MESSAGE"
    REQUEST_DECISION = "REQUEST_DECISION"
    SIMULATE_SEND_MESSAGE = "SIMULATE_SEND_MESSAGE"
    SEND_MESSAGE = "SEND_MESSAGE"
    AUTOMATIC_REPLY = "AUTOMATIC_REPLY"
    REFUND = "REFUND"
    MODIFY_ORDER = "MODIFY_ORDER"
    PAYMENT = "PAYMENT"


MANDATORY_BLOCKED_ACTIONS = frozenset(
    {
        StagingAction.SEND_MESSAGE,
        StagingAction.AUTOMATIC_REPLY,
        StagingAction.REFUND,
        StagingAction.MODIFY_ORDER,
        StagingAction.PAYMENT,
    }
)
SAFE_STAGING_ACTIONS = frozenset(
    {
        StagingAction.OBSERVE_MESSAGE,
        StagingAction.REQUEST_DECISION,
        StagingAction.SIMULATE_SEND_MESSAGE,
    }
)


class EnvironmentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class CredentialReference(EnvironmentModel):
    """Log-safe locator only; this model has no secret-value field."""

    provider: Literal["secret-manager", "vault"]
    credential_id: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)
    version: str = Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)
    account_ref: str = Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)


class StagingAllowlist(EnvironmentModel):
    account_refs: frozenset[str] = Field(min_length=1)
    conversation_ids: frozenset[str] = Field(min_length=1)
    allowed_actions: frozenset[StagingAction] = Field(min_length=1)
    blocked_actions: frozenset[StagingAction] = MANDATORY_BLOCKED_ACTIONS

    @field_validator("account_refs", "conversation_ids")
    @classmethod
    def validate_identifiers(cls, values: frozenset[str]) -> frozenset[str]:
        for value in values:
            if not value or len(value) > 255 or "\r" in value or "\n" in value:
                raise ValueError("allowlist identifiers must be nonblank single lines")
        return values

    @model_validator(mode="after")
    def validate_actions(self) -> StagingAllowlist:
        if not MANDATORY_BLOCKED_ACTIONS.issubset(self.blocked_actions):
            raise ValueError("mandatory high-impact actions must remain blocked")
        if not self.allowed_actions.issubset(SAFE_STAGING_ACTIONS):
            raise ValueError("staging allowlist contains a prohibited action")
        if self.allowed_actions & self.blocked_actions:
            raise ValueError("an action cannot be both allowed and blocked")
        return self


class EnvironmentProfileV1(EnvironmentModel):
    profile_version: Literal["1.0"] = ENVIRONMENT_PROFILE_VERSION
    profile: EnvironmentProfile
    gateway_endpoint: str = Field(min_length=1, max_length=512)
    adapter_mode: AdapterMode
    credential_reference: CredentialReference | None = None
    policy_profile: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    allowlist: StagingAllowlist | None = None
    production_enabled: bool = False
    production_confirmation: str | None = Field(default=None, exclude=True, repr=False)
    automatic_send_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_profile(self) -> EnvironmentProfileV1:
        self._validate_gateway_endpoint()
        if self.profile is EnvironmentProfile.MOCK:
            if self.production_enabled or self.production_confirmation is not None:
                raise ValueError("mock profile cannot carry production enablement")
            if self.adapter_mode is not AdapterMode.FAKE:
                raise ValueError("mock profile requires FAKE adapter mode")
            if self.credential_reference is not None:
                raise ValueError("mock profile cannot resolve credentials")
            if self.allowlist is not None:
                raise ValueError("mock profile does not use a staging allowlist")
        elif self.profile is EnvironmentProfile.STAGING:
            if self.production_enabled or self.production_confirmation is not None:
                raise ValueError("staging profile cannot carry production enablement")
            if self.adapter_mode not in {
                AdapterMode.FAKE,
                AdapterMode.OBSERVATION_ONLY,
            }:
                raise ValueError("staging permits only fake or observation adapters")
            if self.credential_reference is None or self.allowlist is None:
                raise ValueError(
                    "staging requires credential reference and explicit allowlist"
                )
            if (
                self.credential_reference.account_ref
                not in self.allowlist.account_refs
            ):
                raise ValueError("credential account must be staging-allowlisted")
        else:
            if not self.production_enabled:
                raise ProductionProfileDisabled(
                    "production profile is disabled by default"
                )
            if self.production_confirmation != PRODUCTION_CONFIRMATION:
                raise ProductionProfileDisabled(
                    "production profile requires explicit confirmation"
                )
            if self.adapter_mode is not AdapterMode.PRODUCTION_PREPARATION:
                raise ValueError(
                    "production profile V1 is limited to preparation adapter mode"
                )
            if self.credential_reference is None or self.allowlist is None:
                raise ValueError(
                    "production preparation requires reference and allowlist"
                )
        return self

    def _validate_gateway_endpoint(self) -> None:
        parsed = urlsplit(self.gateway_endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("gateway endpoint must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("gateway endpoint cannot contain credentials")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("gateway endpoint cannot contain path, query or fragment")
        if self.profile is EnvironmentProfile.MOCK:
            if parsed.hostname.casefold() not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("mock gateway endpoint must use loopback")
        elif parsed.scheme != "https":
            raise ValueError("staging and production gateway endpoints require HTTPS")


def default_mock_profile() -> EnvironmentProfileV1:
    return EnvironmentProfileV1(
        profile=EnvironmentProfile.MOCK,
        gateway_endpoint="http://127.0.0.1:18021",
        adapter_mode=AdapterMode.FAKE,
        policy_profile="mock-human-approval.v1",
    )


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise EnvironmentProfileError(f"{name} must be an explicit boolean")


def _csv(source: Mapping[str, str], key: str) -> frozenset[str]:
    values = frozenset(
        part.strip() for part in source.get(key, "").split(",") if part.strip()
    )
    return values


def load_environment_profile(
    environ: Mapping[str, str] | None = None,
) -> EnvironmentProfileV1:
    source = os.environ if environ is None else environ
    for key in source:
        if key.startswith("CHANNEL_ENGINE_") and any(
            marker in key.upper() for marker in _SENSITIVE_ENV_MARKERS
        ):
            raise EnvironmentProfileError(
                f"secret values are prohibited in environment profile: {key}"
            )

    try:
        profile = EnvironmentProfile(
            source.get("CHANNEL_ENGINE_PROFILE", "mock").strip().casefold()
        )
    except ValueError as exc:
        raise EnvironmentProfileError(
            "CHANNEL_ENGINE_PROFILE must be mock, staging or production"
        ) from exc
    production_enabled = _parse_bool(
        source.get("CHANNEL_ENGINE_PRODUCTION_ENABLED", "false"),
        "CHANNEL_ENGINE_PRODUCTION_ENABLED",
    )
    if profile is EnvironmentProfile.PRODUCTION:
        if not production_enabled:
            raise ProductionProfileDisabled(
                "production profile is disabled by default"
            )
        if (
            source.get("CHANNEL_ENGINE_PRODUCTION_CONFIRMATION")
            != PRODUCTION_CONFIRMATION
        ):
            raise ProductionProfileDisabled(
                "production profile requires explicit confirmation"
            )
    if profile is EnvironmentProfile.MOCK:
        try:
            adapter_mode = AdapterMode(
                source.get("CHANNEL_ENGINE_ADAPTER_MODE", AdapterMode.FAKE.value)
            )
        except ValueError as exc:
            raise EnvironmentProfileError(
                "CHANNEL_ENGINE_ADAPTER_MODE is invalid"
            ) from exc
        has_credential_metadata = any(
            source.get(key)
            for key in (
                "CHANNEL_ENGINE_CREDENTIAL_PROVIDER",
                "CHANNEL_ENGINE_CREDENTIAL_ID",
                "CHANNEL_ENGINE_CREDENTIAL_VERSION",
                "CHANNEL_ENGINE_ACCOUNT_REF",
            )
        )
        if has_credential_metadata:
            raise EnvironmentProfileError(
                "mock profile cannot carry credential metadata"
            )
        if any(
            _csv(source, key)
            for key in (
                "CHANNEL_ENGINE_ALLOWED_ACCOUNTS",
                "CHANNEL_ENGINE_ALLOWED_CONVERSATIONS",
                "CHANNEL_ENGINE_ALLOWED_ACTIONS",
            )
        ):
            raise EnvironmentProfileError("mock profile cannot carry an allowlist")
        return EnvironmentProfileV1(
            profile=profile,
            gateway_endpoint=source.get(
                "CHANNEL_ENGINE_GATEWAY_ENDPOINT", "http://127.0.0.1:18021"
            ),
            adapter_mode=adapter_mode,
            policy_profile=source.get(
                "CHANNEL_ENGINE_POLICY_PROFILE", "mock-human-approval.v1"
            ),
            production_enabled=production_enabled,
            production_confirmation=source.get(
                "CHANNEL_ENGINE_PRODUCTION_CONFIRMATION"
            ),
        )

    credential = CredentialReference(
        provider=source.get("CHANNEL_ENGINE_CREDENTIAL_PROVIDER", ""),
        credential_id=source.get("CHANNEL_ENGINE_CREDENTIAL_ID", ""),
        version=source.get("CHANNEL_ENGINE_CREDENTIAL_VERSION", ""),
        account_ref=source.get("CHANNEL_ENGINE_ACCOUNT_REF", ""),
    )
    try:
        allowed_actions = frozenset(
            StagingAction(value)
            for value in _csv(source, "CHANNEL_ENGINE_ALLOWED_ACTIONS")
        )
    except ValueError as exc:
        raise EnvironmentProfileError("allowed action is unknown") from exc
    allowlist = StagingAllowlist(
        account_refs=_csv(source, "CHANNEL_ENGINE_ALLOWED_ACCOUNTS"),
        conversation_ids=_csv(source, "CHANNEL_ENGINE_ALLOWED_CONVERSATIONS"),
        allowed_actions=allowed_actions,
    )
    default_adapter = (
        AdapterMode.OBSERVATION_ONLY.value
        if profile is EnvironmentProfile.STAGING
        else AdapterMode.PRODUCTION_PREPARATION.value
    )
    try:
        adapter_mode = AdapterMode(
            source.get("CHANNEL_ENGINE_ADAPTER_MODE", default_adapter)
        )
    except ValueError as exc:
        raise EnvironmentProfileError("CHANNEL_ENGINE_ADAPTER_MODE is invalid") from exc
    return EnvironmentProfileV1(
        profile=profile,
        gateway_endpoint=source.get("CHANNEL_ENGINE_GATEWAY_ENDPOINT", ""),
        adapter_mode=adapter_mode,
        credential_reference=credential,
        policy_profile=source.get("CHANNEL_ENGINE_POLICY_PROFILE", ""),
        allowlist=allowlist,
        production_enabled=production_enabled,
        production_confirmation=source.get(
            "CHANNEL_ENGINE_PRODUCTION_CONFIRMATION"
        ),
    )


__all__ = [
    "AdapterMode",
    "CredentialReference",
    "ENVIRONMENT_PROFILE_VERSION",
    "EnvironmentProfile",
    "EnvironmentProfileError",
    "EnvironmentProfileV1",
    "MANDATORY_BLOCKED_ACTIONS",
    "PRODUCTION_CONFIRMATION",
    "ProductionProfileDisabled",
    "SAFE_STAGING_ACTIONS",
    "StagingAction",
    "StagingAllowlist",
    "default_mock_profile",
    "load_environment_profile",
]
