from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.agent.models import StoreBinding
from channel_engine.browser import (
    BrowserLoginState,
    BrowserObservationStore,
    BrowserPageObserver,
    BrowserPageObserverState,
    BrowserSession,
    BrowserSessionManager,
    BrowserSessionState,
    PDDMessageExtractor,
    ReadOnlyBrowserPageCapturePort,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorRegistry,
)
from channel_engine.conversation import ConversationService
from channel_engine.models.entities import utc_now
from channel_engine.pilot.environment import (
    PDDStoreBindingDiscoveryService,
    VerifiedSelectorStoreIdentitySource,
)
from channel_engine.pdd_adapter.message_observation import (
    BrowserPDDMessageReader,
    PDDMessageObservationEvidence,
    PDDMessageObservationRuntime,
)
from channel_engine.storage import SqlAlchemyUnitOfWork


PDD_OBSERVE_MODE_VERSION = "1.0"


class PDDObserveModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    observe_mode_version: Literal["1.0"] = PDD_OBSERVE_MODE_VERSION


class PDDObserveState(StrEnum):
    CREATED = "CREATED"
    WAITING_LOGIN = "WAITING_LOGIN"
    VERIFYING_STORE = "VERIFYING_STORE"
    READY = "READY"
    OBSERVING = "OBSERVING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class PDDObserveError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDObserveSafetyViolation(PDDObserveError):
    pass


class PDDObserveSafetySnapshot(PDDObserveModel):
    execution_created: Literal[0] = 0
    receipt_created: Literal[0] = 0
    receipt_published: Literal[0] = 0
    customer_message_sent: Literal[0] = 0
    browser_write_operations: Literal[0] = 0
    automatic_login_performed: Literal[False] = False
    auto_reply_enabled: Literal[False] = False
    approval_execution_enabled: Literal[False] = False


class PDDObserveStatus(PDDObserveModel):
    state: PDDObserveState
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )
    browser_state: BrowserSessionState
    login_state: BrowserLoginState
    browser_generation: int = Field(ge=0)
    browser_healthy: bool
    human_login_required: bool
    profile_id: str = Field(min_length=1, max_length=128)
    selector_contract_id: str | None = Field(default=None, max_length=256)
    selector_state: SelectorContractState | None = None
    store_id: str | None = Field(default=None, max_length=128)
    store_name: str | None = Field(default=None, max_length=160)
    observed_message_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    checked_at: AwareDatetime
    safety: PDDObserveSafetySnapshot


class PDDObserveDecisionResult(PDDObserveModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    conversation_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    decision_state: Literal["WAITING_APPROVAL"] = "WAITING_APPROVAL"
    requires_approval: Literal[True] = True
    observed_at: AwareDatetime


class PDDObserveModeRuntime:
    """Inbound-only PDD orchestration; it intentionally has no approval/send surface."""

    def __init__(
        self,
        browser: BrowserSessionManager,
        selector_registry: SelectorRegistry,
        page_port: ReadOnlyBrowserPageCapturePort,
        observation_store: BrowserObservationStore,
        conversation: ConversationService,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        credential_reference: str,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(page_port, ReadOnlyBrowserPageCapturePort):
            raise TypeError("page port does not implement receive-only observation")
        if not page_port.read_only or page_port.page_write_operations != 0:
            raise ValueError("PDD Observe Mode requires a zero-write page port")
        if not isinstance(observation_store, BrowserObservationStore):
            raise TypeError("observation store does not implement the contract")
        if not credential_reference.startswith(("credential-ref://", "secret-ref://")):
            raise ValueError("PDD Observe Mode accepts a credential reference only")
        self._browser = browser
        self._selectors = selector_registry
        self._page_port = page_port
        self._observation_store = observation_store
        self._conversation = conversation
        self._uow_factory = uow_factory
        self._credential_reference = credential_reference
        self._clock = clock
        self._state = PDDObserveState.CREATED
        self._reason_code = "PDD_OBSERVE_CREATED"
        self._store: StoreBinding | None = None
        self._selector: SelectorContract | None = None
        self._observer: BrowserPageObserver | None = None
        self._message_runtime: PDDMessageObservationRuntime | None = None
        self._observed_message_count = 0
        self._decision_count = 0
        self._lock = RLock()

    def start(self) -> PDDObserveStatus:
        with self._lock:
            if self._state not in {PDDObserveState.CREATED, PDDObserveState.STOPPED}:
                return self.status()
            session = self._browser.start()
            self._resolve_login_state(session)
            return self.status()

    def check_login(self) -> PDDObserveStatus:
        with self._lock:
            if self._state is PDDObserveState.STOPPED:
                raise PDDObserveError(
                    "PDD Observe Mode is stopped",
                    error_code="PDD_OBSERVE_STOPPED",
                )
            session = self._browser.heartbeat()
            self._resolve_login_state(session)
            return self.status()

    def bind_store(self) -> StoreBinding:
        with self._lock:
            session = self._browser.snapshot()
            self._require_authenticated(session)
            selector = self._active_receive_selector(session)
            self._state = PDDObserveState.VERIFYING_STORE
            source = VerifiedSelectorStoreIdentitySource(self._page_port)
            discovery = PDDStoreBindingDiscoveryService(self._credential_reference)
            try:
                binding = discovery.discover(session, selector, source)
            except Exception as exc:
                self._state = PDDObserveState.FAILED
                self._reason_code = "PDD_OBSERVE_STORE_IDENTITY_FAILED"
                raise PDDObserveError(
                    "real store identity could not be verified",
                    error_code=self._reason_code,
                ) from exc
            self._store = binding
            self._selector = selector
            self._observer = BrowserPageObserver(
                self._browser.snapshot,
                self._page_port,
                PDDMessageExtractor(),
                self._selectors,
                self._observation_store,
                stream_id=f"pdd-observe:{binding.store_id}",
                clock=self._clock,
            )
            self._observer.attach()
            self._message_runtime = PDDMessageObservationRuntime(
                BrowserPDDMessageReader(
                    self._observer,
                    self._browser.snapshot,
                    store_id=binding.store_id,
                    clock=self._clock,
                ),
                self._conversation,
                self._uow_factory,
                clock=self._clock,
            )
            self._assert_zero_write()
            self._state = PDDObserveState.READY
            self._reason_code = "PDD_OBSERVE_READY"
            return binding

    def observe_once(self) -> tuple[PDDObserveDecisionResult, ...]:
        with self._lock:
            if (
                self._state is not PDDObserveState.READY
                or self._observer is None
                or self._message_runtime is None
            ):
                raise PDDObserveError(
                    "PDD Observe Mode is not ready",
                    error_code="PDD_OBSERVE_NOT_READY",
                )
            if self._store is None:
                raise PDDObserveError(
                    "PDD store is not bound",
                    error_code="PDD_OBSERVE_STORE_UNBOUND",
                )
            self._state = PDDObserveState.OBSERVING
            try:
                evidence = self._message_runtime.observe_once()
                results = tuple(
                    PDDObserveDecisionResult(
                        external_message_id=item.external_message_id,
                        conversation_id=item.conversation_id,
                        message_id=item.message_id,
                        decision_id=item.decision_id,
                        observed_at=item.observed_at,
                    )
                    for item in evidence
                )
                self._assert_zero_write()
            except PDDObserveSafetyViolation:
                self._state = PDDObserveState.FAILED
                self._reason_code = "PDD_OBSERVE_SAFETY_VIOLATION"
                raise
            except Exception as exc:
                self._state = PDDObserveState.DEGRADED
                self._reason_code = getattr(
                    exc,
                    "error_code",
                    "PDD_OBSERVE_CAPTURE_FAILED",
                )
                raise
            self._observed_message_count += len(evidence)
            self._decision_count += len(results)
            self._state = PDDObserveState.READY
            self._reason_code = "PDD_OBSERVE_READY"
            return results

    def message_evidence(self) -> tuple[PDDMessageObservationEvidence, ...]:
        with self._lock:
            if self._message_runtime is None:
                return ()
            return self._message_runtime.evidence()

    def heartbeat(self) -> PDDObserveStatus:
        with self._lock:
            session = self._browser.heartbeat()
            if session.state is not BrowserSessionState.ACTIVE:
                self._state = (
                    PDDObserveState.WAITING_LOGIN
                    if session.login_state
                    in {BrowserLoginState.REQUIRED, BrowserLoginState.EXPIRED}
                    else PDDObserveState.DEGRADED
                )
                self._reason_code = (
                    "PDD_OBSERVE_HUMAN_LOGIN_REQUIRED"
                    if self._state is PDDObserveState.WAITING_LOGIN
                    else "PDD_OBSERVE_BROWSER_DEGRADED"
                )
            elif self._observer is not None:
                health = self._observer.heartbeat()
                if not health.healthy:
                    self._state = PDDObserveState.DEGRADED
                    self._reason_code = (
                        health.failure_code or "PDD_OBSERVE_OBSERVER_DEGRADED"
                    )
            self._assert_zero_write()
            return self.status()

    def stop(self) -> PDDObserveStatus:
        with self._lock:
            if self._observer is not None:
                self._observer.detach()
            self._browser.stop()
            self._state = PDDObserveState.STOPPED
            self._reason_code = "PDD_OBSERVE_STOPPED"
            return self.status()

    def status(self) -> PDDObserveStatus:
        with self._lock:
            session = self._browser.snapshot()
            selector = self._selector
            if selector is None and session.page_context is not None:
                try:
                    selector = self._selectors.get(
                        "pdd",
                        "merchant_chat",
                        session.page_context.selector_contract_version,
                    )
                except Exception:
                    selector = None
            return PDDObserveStatus(
                state=self._state,
                reason_code=self._reason_code,
                browser_state=session.state,
                login_state=session.login_state,
                browser_generation=session.generation,
                browser_healthy=session.state
                in {BrowserSessionState.ACTIVE, BrowserSessionState.LOGIN_REQUIRED},
                human_login_required=session.state
                in {BrowserSessionState.LOGIN_REQUIRED, BrowserSessionState.EXPIRED},
                profile_id=session.profile.profile_id,
                selector_contract_id=(selector.contract_id if selector else None),
                selector_state=(selector.state if selector else None),
                store_id=(self._store.store_id if self._store else None),
                store_name=(self._store.store_name if self._store else None),
                observed_message_count=self._observed_message_count,
                decision_count=self._decision_count,
                checked_at=self._clock(),
                safety=self.safety_snapshot(),
            )

    def safety_snapshot(self) -> PDDObserveSafetySnapshot:
        self._assert_zero_write()
        return PDDObserveSafetySnapshot()

    def _resolve_login_state(self, session: BrowserSession) -> None:
        if (
            session.state is BrowserSessionState.ACTIVE
            and session.login_state is BrowserLoginState.AUTHENTICATED
        ):
            self._state = PDDObserveState.VERIFYING_STORE
            self._reason_code = "PDD_OBSERVE_STORE_VERIFICATION_REQUIRED"
        elif session.state in {
            BrowserSessionState.LOGIN_REQUIRED,
            BrowserSessionState.EXPIRED,
        }:
            self._state = PDDObserveState.WAITING_LOGIN
            self._reason_code = "PDD_OBSERVE_HUMAN_LOGIN_REQUIRED"
        else:
            self._state = PDDObserveState.DEGRADED
            self._reason_code = "PDD_OBSERVE_BROWSER_DEGRADED"

    @staticmethod
    def _require_authenticated(session: BrowserSession) -> None:
        if (
            session.state is not BrowserSessionState.ACTIVE
            or session.login_state is not BrowserLoginState.AUTHENTICATED
            or session.page_context is None
        ):
            raise PDDObserveError(
                "human-authenticated browser session is required",
                error_code="PDD_OBSERVE_HUMAN_LOGIN_REQUIRED",
            )

    def _active_receive_selector(self, session: BrowserSession) -> SelectorContract:
        assert session.page_context is not None
        try:
            selector = self._selectors.active("pdd", "merchant_chat")
        except Exception as exc:
            raise PDDObserveError(
                "verified selector contract is not active",
                error_code="PDD_OBSERVE_SELECTOR_NOT_VERIFIED",
            ) from exc
        if (
            selector.version != session.page_context.selector_contract_version
            or selector.state is not SelectorContractState.VERIFIED
            or SelectorCapability.STORE_IDENTITY not in selector.capabilities
            or SelectorCapability.RECEIVE_MESSAGE not in selector.capabilities
            or SelectorCapability.SEND_MESSAGE in selector.capabilities
        ):
            raise PDDObserveError(
                "selector contract is not verified for receive-only store observation",
                error_code="PDD_OBSERVE_SELECTOR_NOT_RECEIVE_ONLY",
            )
        return selector

    def _assert_zero_write(self) -> None:
        if not self._page_port.read_only or self._page_port.page_write_operations != 0:
            raise PDDObserveSafetyViolation(
                "browser page write was detected",
                error_code="PDD_OBSERVE_BROWSER_WRITE_DETECTED",
            )


__all__ = [
    "PDD_OBSERVE_MODE_VERSION",
    "PDDObserveDecisionResult",
    "PDDObserveError",
    "PDDObserveModeRuntime",
    "PDDObserveSafetySnapshot",
    "PDDObserveSafetyViolation",
    "PDDObserveState",
    "PDDObserveStatus",
]
