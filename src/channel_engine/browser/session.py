from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, Field

from channel_engine.models.entities import new_id, utc_now

from .models import (
    BrowserHeartbeat,
    BrowserHeartbeatState,
    BrowserLoginState,
    BrowserModel,
    BrowserPageContext,
    BrowserProfileReference,
    BrowserSession,
    BrowserSessionState,
    ChromeLaunchStrategy,
)


class BrowserSessionError(RuntimeError):
    pass


class BrowserSessionUnavailable(BrowserSessionError):
    pass


class BrowserProfileIsolationError(BrowserSessionError):
    pass


class BrowserProfileIsolationRegistry:
    """Prevents a browser profile reference from being shared across accounts."""

    def __init__(self) -> None:
        self._by_profile_id: dict[str, str] = {}
        self._by_storage_reference: dict[str, str] = {}

    def register(self, profile: BrowserProfileReference) -> None:
        profile_account = self._by_profile_id.get(profile.profile_id)
        storage_account = self._by_storage_reference.get(profile.storage_reference)
        if profile_account not in {None, profile.account_ref}:
            raise BrowserProfileIsolationError(
                "browser profile id is already assigned to another account"
            )
        if storage_account not in {None, profile.account_ref}:
            raise BrowserProfileIsolationError(
                "browser profile storage is already assigned to another account"
            )
        self._by_profile_id[profile.profile_id] = profile.account_ref
        self._by_storage_reference[profile.storage_reference] = profile.account_ref


class BrowserDriverStartResult(BrowserModel):
    driver_session_ref: str = Field(min_length=1, max_length=128)
    page_revision: str | None = Field(default=None, max_length=128)
    login_state: BrowserLoginState
    page_available: bool
    observed_at: AwareDatetime


@runtime_checkable
class BrowserRuntimeDriver(Protocol):
    """Infrastructure port; implementations may use Playwright, CDP or another driver."""

    def start(
        self,
        profile: BrowserProfileReference,
        strategy: ChromeLaunchStrategy,
    ) -> BrowserDriverStartResult:
        """Start or attach without performing login."""

    def heartbeat(self, driver_session_ref: str) -> BrowserHeartbeat:
        """Probe process, page and login markers without mutating the page."""

    def stop(self, driver_session_ref: str) -> None:
        """Close driver resources without deleting the profile."""


class BrowserSessionManager:
    """Session state machine. Login is always a human-owned operation."""

    def __init__(
        self,
        driver: BrowserRuntimeDriver,
        profile: BrowserProfileReference,
        *,
        strategy: ChromeLaunchStrategy,
        selector_contract_version: str,
        max_recovery_attempts: int = 3,
        clock: Callable[[], AwareDatetime] = utc_now,
        isolation_registry: BrowserProfileIsolationRegistry | None = None,
    ) -> None:
        if not isinstance(driver, BrowserRuntimeDriver):
            raise TypeError("driver does not implement BrowserRuntimeDriver")
        if not selector_contract_version.strip():
            raise ValueError("selector contract version is required")
        if max_recovery_attempts < 1:
            raise ValueError("max recovery attempts must be positive")
        self._driver = driver
        self._clock = clock
        self._selector_contract_version = selector_contract_version
        self._max_recovery_attempts = max_recovery_attempts
        self._isolation_registry = isolation_registry or BrowserProfileIsolationRegistry()
        self._isolation_registry.register(profile)
        self._driver_session_ref: str | None = None
        self._recovery_attempts = 0
        self._session = BrowserSession(
            session_id=new_id("browser-session"),
            account_ref=profile.account_ref,
            profile=profile,
            launch_strategy=strategy,
            state=BrowserSessionState.CREATED,
            login_state=BrowserLoginState.UNKNOWN,
            generation=0,
        )

    def snapshot(self) -> BrowserSession:
        return self._session

    def start(self) -> BrowserSession:
        if self._session.state not in {
            BrowserSessionState.CREATED,
            BrowserSessionState.STOPPED,
            BrowserSessionState.CRASHED,
            BrowserSessionState.DEGRADED,
            BrowserSessionState.RECOVERING,
        }:
            raise BrowserSessionError(
                f"browser session cannot start from {self._session.state}"
            )
        now = self._clock()
        self._session = self._session.model_copy(
            update={
                "state": BrowserSessionState.STARTING,
                "stopped_at": None,
                "failure_code": None,
                "human_takeover_required": False,
            }
        )
        try:
            result = self._driver.start(
                self._session.profile, self._session.launch_strategy
            )
        except Exception as exc:
            self._session = self._session.model_copy(
                update={
                    "state": BrowserSessionState.CRASHED,
                    "login_state": BrowserLoginState.UNKNOWN,
                    "failure_code": f"BROWSER_DRIVER_START_{type(exc).__name__.upper()}",
                    "last_heartbeat_at": now,
                }
            )
            raise BrowserSessionUnavailable("browser driver failed to start") from exc
        self._driver_session_ref = result.driver_session_ref
        generation = self._session.generation + 1
        page = (
            BrowserPageContext(
                page_context_id=new_id("browser-page"),
                session_id=self._session.session_id,
                generation=generation,
                selector_contract_version=self._selector_contract_version,
                page_revision=result.page_revision,
                created_at=result.observed_at,
            )
            if result.page_available
            else None
        )
        authenticated = (
            result.login_state is BrowserLoginState.AUTHENTICATED
            and page is not None
        )
        self._session = self._session.model_copy(
            update={
                "state": (
                    BrowserSessionState.ACTIVE
                    if authenticated
                    else BrowserSessionState.LOGIN_REQUIRED
                ),
                "login_state": result.login_state,
                "generation": generation,
                "page_context": page,
                "started_at": now,
                "last_heartbeat_at": result.observed_at,
                "failure_code": None if authenticated else "BROWSER_LOGIN_REQUIRED",
                "human_takeover_required": not authenticated,
            }
        )
        return BrowserSession.model_validate(self._session.model_dump())

    def heartbeat(self) -> BrowserSession:
        if self._driver_session_ref is None:
            raise BrowserSessionUnavailable("browser driver session is not started")
        try:
            heartbeat = self._driver.heartbeat(self._driver_session_ref)
        except Exception as exc:
            self._session = self._session.model_copy(
                update={
                    "state": BrowserSessionState.CRASHED,
                    "login_state": BrowserLoginState.UNKNOWN,
                    "last_heartbeat_at": self._clock(),
                    "failure_code": f"BROWSER_HEARTBEAT_{type(exc).__name__.upper()}",
                }
            )
            return BrowserSession.model_validate(self._session.model_dump())
        if heartbeat.state is BrowserHeartbeatState.CRASHED:
            target = BrowserSessionState.CRASHED
        elif heartbeat.login_state in {
            BrowserLoginState.EXPIRED,
            BrowserLoginState.REQUIRED,
        }:
            target = BrowserSessionState.EXPIRED
        elif (
            heartbeat.state is BrowserHeartbeatState.HEALTHY
            and heartbeat.page_available
            and heartbeat.login_state is BrowserLoginState.AUTHENTICATED
        ):
            target = BrowserSessionState.ACTIVE
        elif (
            self._session.state is BrowserSessionState.LOGIN_REQUIRED
            and heartbeat.state is BrowserHeartbeatState.HEALTHY
            and heartbeat.page_available
            and heartbeat.login_state is BrowserLoginState.UNKNOWN
        ):
            # An unknown read-only detector result can never prove login. Keep
            # waiting for the human/selector evidence instead of degrading it
            # into an ambiguous state.
            target = BrowserSessionState.LOGIN_REQUIRED
        else:
            target = BrowserSessionState.DEGRADED
        generation = self._session.generation
        page = self._session.page_context
        if heartbeat.page_available and heartbeat.page_revision is not None:
            if page is None or page.page_revision != heartbeat.page_revision:
                generation += 1
                page = BrowserPageContext(
                    page_context_id=new_id("browser-page"),
                    session_id=self._session.session_id,
                    generation=generation,
                    selector_contract_version=self._selector_contract_version,
                    page_revision=heartbeat.page_revision,
                    created_at=heartbeat.checked_at,
                )
        takeover = target in {
            BrowserSessionState.EXPIRED,
            BrowserSessionState.LOGIN_REQUIRED,
        }
        self._session = self._session.model_copy(
            update={
                "state": target,
                "login_state": heartbeat.login_state,
                "last_heartbeat_at": heartbeat.checked_at,
                "generation": generation,
                "page_context": page,
                "failure_code": heartbeat.failure_code,
                "human_takeover_required": takeover,
            }
        )
        return BrowserSession.model_validate(self._session.model_dump())

    def recover(self) -> BrowserSession:
        if self._session.state not in {
            BrowserSessionState.CRASHED,
            BrowserSessionState.DEGRADED,
        }:
            raise BrowserSessionError("only crashed or degraded sessions can recover")
        if self._recovery_attempts >= self._max_recovery_attempts:
            raise BrowserSessionUnavailable("browser recovery budget exhausted")
        self._recovery_attempts += 1
        if self._driver_session_ref is not None:
            self._driver.stop(self._driver_session_ref)
            self._driver_session_ref = None
        self._session = self._session.model_copy(
            update={"state": BrowserSessionState.RECOVERING}
        )
        return self.start()

    def stop(self) -> BrowserSession:
        now = self._clock()
        if self._driver_session_ref is not None:
            self._driver.stop(self._driver_session_ref)
            self._driver_session_ref = None
        self._session = self._session.model_copy(
            update={
                "state": BrowserSessionState.STOPPED,
                "page_context": None,
                "stopped_at": now,
                "failure_code": None,
            }
        )
        return BrowserSession.model_validate(self._session.model_dump())


class FakeBrowserRuntimeDriver:
    """Offline driver; it never starts Chrome or opens a network connection."""

    def __init__(
        self,
        *,
        login_state: BrowserLoginState = BrowserLoginState.AUTHENTICATED,
        page_available: bool = True,
        page_revision: str = "mock-page-revision-1",
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self.login_state = login_state
        self.page_available = page_available
        self.page_revision = page_revision
        self.heartbeat_state = BrowserHeartbeatState.HEALTHY
        self.failure_code: str | None = None
        self._clock = clock
        self.start_count = 0
        self.stop_count = 0
        self.real_browser_started = False
        self._active_refs: set[str] = set()

    def start(
        self,
        profile: BrowserProfileReference,
        strategy: ChromeLaunchStrategy,
    ) -> BrowserDriverStartResult:
        del profile, strategy
        self.start_count += 1
        reference = new_id("fake-browser-driver")
        self._active_refs.add(reference)
        return BrowserDriverStartResult(
            driver_session_ref=reference,
            page_revision=self.page_revision,
            login_state=self.login_state,
            page_available=self.page_available,
            observed_at=self._clock(),
        )

    def heartbeat(self, driver_session_ref: str) -> BrowserHeartbeat:
        if driver_session_ref not in self._active_refs:
            raise BrowserSessionUnavailable("fake driver session is unavailable")
        return BrowserHeartbeat(
            session_id=driver_session_ref,
            state=self.heartbeat_state,
            login_state=self.login_state,
            page_available=self.page_available,
            page_revision=self.page_revision if self.page_available else None,
            checked_at=self._clock(),
            failure_code=self.failure_code,
        )

    def stop(self, driver_session_ref: str) -> None:
        self.stop_count += 1
        self._active_refs.discard(driver_session_ref)


__all__ = [
    "BrowserDriverStartResult",
    "BrowserRuntimeDriver",
    "BrowserProfileIsolationError",
    "BrowserProfileIsolationRegistry",
    "BrowserSessionError",
    "BrowserSessionManager",
    "BrowserSessionUnavailable",
    "FakeBrowserRuntimeDriver",
]
