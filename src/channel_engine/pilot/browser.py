from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from channel_engine.browser import (
    BrowserLoginLocationRule,
    BrowserProfileReference,
    BrowserSessionManager,
    ChromeLaunchStrategy,
    ConservativeLoginDetector,
    NamedDedicatedBrowserProfilePathProvider,
    ReadOnlyUrlLoginDetector,
    RealBrowserRuntimeDriver,
)

from .models import PilotStoreConfig
from .runtime import BrowserSessionManagerPilotPort


class PilotBrowserLaunchConfig(BaseModel):
    """Evidence-supplied browser facts; no PDD URL or selector is guessed."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    merchant_chat_url: str = Field(min_length=1, max_length=2048)
    authenticated_path_prefix: str = Field(min_length=1, max_length=512)
    login_path_prefix: str = Field(min_length=1, max_length=512)
    selector_contract_version: str = Field(min_length=1, max_length=64)

    @field_validator("merchant_chat_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Pilot merchant chat URL must be absolute HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Pilot merchant chat URL cannot contain credentials/query")
        return value

    @field_validator("authenticated_path_prefix", "login_path_prefix")
    @classmethod
    def validate_path_prefix(cls, value: str) -> str:
        if not value.startswith("/") or "?" in value or "#" in value:
            raise ValueError("Pilot login path rules must be absolute path prefixes")
        return value

    @model_validator(mode="after")
    def require_distinct_rules(self) -> PilotBrowserLaunchConfig:
        if self.authenticated_path_prefix == self.login_path_prefix:
            raise ValueError("authenticated and login paths must be distinct")
        return self

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.merchant_chat_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


class PilotBrowserDiscoveryLaunchConfig(BaseModel):
    """Pre-login launch facts; login state remains UNKNOWN until discovery evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    merchant_chat_url: str = Field(min_length=1, max_length=2048)
    node_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    profile_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    selector_contract_version: str = "pdd:merchant_chat:v1"

    @field_validator("merchant_chat_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not (
            host == "pinduoduo.com" or host.endswith(".pinduoduo.com")
        ):
            raise ValueError("discovery browser requires an official PDD HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("discovery browser URL cannot contain credentials/query")
        return value

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.merchant_chat_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def build_manual_login_browser_port(
    store: PilotStoreConfig,
    launch: PilotBrowserLaunchConfig,
    *,
    chrome_path: Path,
    profile_root: Path,
) -> BrowserSessionManagerPilotPort:
    """Build a real Chrome port that opens one page and waits for human login."""

    detector = ReadOnlyUrlLoginDetector(
        authenticated=(
            BrowserLoginLocationRule(
                launch.origin,
                launch.authenticated_path_prefix,
            ),
        ),
        login_required=(
            BrowserLoginLocationRule(
                launch.origin,
                launch.login_path_prefix,
            ),
        ),
    )
    driver = RealBrowserRuntimeDriver(
        profile_root,
        chrome_executable=chrome_path,
        initial_url=launch.merchant_chat_url,
        allowed_page_origins=(launch.origin,),
        login_detector=detector,
        profile_path_provider=NamedDedicatedBrowserProfilePathProvider(profile_root),
    )
    profile = BrowserProfileReference(
        profile_id=f"pilot-{store.store_id}",
        account_ref=store.store_id,
        storage_reference=f"profile-ref://pdd/pilot/{store.store_id}",
    )
    manager = BrowserSessionManager(
        driver,
        profile,
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version=launch.selector_contract_version,
    )
    return BrowserSessionManagerPilotPort(
        manager,
        real_browser_capable=True,
    )


def build_selector_discovery_browser_session(
    launch: PilotBrowserDiscoveryLaunchConfig,
    *,
    chrome_path: Path,
    profile_root: Path,
) -> BrowserSessionManager:
    """Prepare, but do not start, a dedicated human-login discovery session."""

    driver = RealBrowserRuntimeDriver(
        profile_root,
        chrome_executable=chrome_path,
        initial_url=launch.merchant_chat_url,
        allowed_page_origins=(launch.origin,),
        login_detector=ConservativeLoginDetector(),
        profile_path_provider=NamedDedicatedBrowserProfilePathProvider(profile_root),
    )
    profile = BrowserProfileReference(
        profile_id=launch.profile_id,
        account_ref=launch.node_id,
        storage_reference=f"profile-ref://pdd/pilot/{launch.profile_id}",
    )
    return BrowserSessionManager(
        driver,
        profile,
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version=launch.selector_contract_version,
    )


__all__ = [
    "PilotBrowserDiscoveryLaunchConfig",
    "PilotBrowserLaunchConfig",
    "build_manual_login_browser_port",
    "build_selector_discovery_browser_session",
]
