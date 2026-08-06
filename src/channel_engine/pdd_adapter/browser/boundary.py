from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, Field

from channel_engine.models.entities import utc_now
from channel_engine.pdd_adapter._base import PDDPrototypeModel
from channel_engine.pdd_adapter.selector import PDDVerifiedSelectorToken
from channel_engine.pdd_adapter.session import PDDSession, PDDSessionStatus


class PDDBrowserBoundaryError(RuntimeError):
    pass


class PDDLoginObservationState(StrEnum):
    AUTHENTICATED = "AUTHENTICATED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    UNKNOWN = "UNKNOWN"


class PDDBrowserHealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class PDDBrowserPageState(PDDPrototypeModel):
    session_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    browser_generation: int = Field(ge=1)
    page_revision_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    selector_contract_id: str = Field(min_length=1, max_length=160)
    selector_contract_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_available: bool
    login_state: PDDLoginObservationState
    observed_at: AwareDatetime
    synthetic_test_data: Literal[True] = True
    write_capability_enabled: Literal[False] = False
    real_platform_connected: Literal[False] = False


class PDDBrowserHealth(PDDPrototypeModel):
    status: PDDBrowserHealthState
    session_id: str | None = Field(default=None, max_length=128)
    page_available: bool
    reason_code: str = Field(min_length=3, max_length=128)
    checked_at: AwareDatetime
    real_platform_connected: Literal[False] = False
    write_capability_enabled: Literal[False] = False


@runtime_checkable
class PDDBrowserAdapter(Protocol):
    """Observation boundary. It intentionally contains no write operations."""

    def open_session(
        self,
        session: PDDSession,
        selector_token: PDDVerifiedSelectorToken,
    ) -> PDDBrowserPageState: ...

    def health_check(self) -> PDDBrowserHealth: ...

    def capture_state(self) -> PDDBrowserPageState: ...


class FakePDDBrowserAdapter:
    """Offline page-state simulator implementing the read-only browser boundary."""

    def __init__(
        self,
        *,
        page_revision_digest: str = "0" * 64,
        clock: Callable = utc_now,
    ) -> None:
        self._clock = clock
        self._page_revision_digest = page_revision_digest
        self._state: PDDBrowserPageState | None = None
        self._generation = 0
        self._lock = RLock()

    def open_session(
        self,
        session: PDDSession,
        selector_token: PDDVerifiedSelectorToken,
    ) -> PDDBrowserPageState:
        if session.status is not PDDSessionStatus.CONNECTED:
            raise PDDBrowserBoundaryError("CONNECTED PDD session is required")
        if not selector_token.synthetic_test_data:
            raise PDDBrowserBoundaryError(
                "prototype browser accepts synthetic selector evidence only"
            )
        with self._lock:
            self._generation += 1
            self._state = PDDBrowserPageState(
                session_id=session.session_id,
                store_id=session.store_id,
                browser_generation=self._generation,
                page_revision_digest=self._page_revision_digest,
                selector_contract_id=selector_token.contract_id,
                selector_contract_fingerprint=selector_token.contract_fingerprint,
                page_available=True,
                login_state=PDDLoginObservationState.AUTHENTICATED,
                observed_at=self._clock(),
            )
            return self._state

    def health_check(self) -> PDDBrowserHealth:
        with self._lock:
            state = self._state
            if state is None:
                status = PDDBrowserHealthState.UNAVAILABLE
                reason = "PDD_PROTOTYPE_SESSION_NOT_OPEN"
                page_available = False
                session_id = None
            elif state.page_available:
                status = PDDBrowserHealthState.HEALTHY
                reason = "PDD_PROTOTYPE_PAGE_AVAILABLE"
                page_available = True
                session_id = state.session_id
            else:
                status = PDDBrowserHealthState.DEGRADED
                reason = "PDD_PROTOTYPE_PAGE_UNAVAILABLE"
                page_available = False
                session_id = state.session_id
            return PDDBrowserHealth(
                status=status,
                session_id=session_id,
                page_available=page_available,
                reason_code=reason,
                checked_at=self._clock(),
            )

    def capture_state(self) -> PDDBrowserPageState:
        with self._lock:
            if self._state is None:
                raise PDDBrowserBoundaryError("PDD prototype browser session is not open")
            return self._state.model_copy(update={"observed_at": self._clock()})

    def simulate_page_unavailable(self) -> None:
        with self._lock:
            if self._state is None:
                raise PDDBrowserBoundaryError("PDD prototype browser session is not open")
            self._state = self._state.model_copy(
                update={
                    "page_available": False,
                    "login_state": PDDLoginObservationState.UNKNOWN,
                    "observed_at": self._clock(),
                }
            )

    def simulate_login_required(self) -> None:
        with self._lock:
            if self._state is None:
                raise PDDBrowserBoundaryError("PDD prototype browser session is not open")
            self._state = self._state.model_copy(
                update={
                    "login_state": PDDLoginObservationState.LOGIN_REQUIRED,
                    "observed_at": self._clock(),
                }
            )


__all__ = [
    "FakePDDBrowserAdapter",
    "PDDBrowserAdapter",
    "PDDBrowserBoundaryError",
    "PDDBrowserHealth",
    "PDDBrowserHealthState",
    "PDDBrowserPageState",
    "PDDLoginObservationState",
]
