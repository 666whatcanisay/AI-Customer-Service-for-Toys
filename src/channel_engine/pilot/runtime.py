from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol, runtime_checkable

from pydantic import JsonValue

from channel_engine.browser import (
    BrowserLoginState,
    BrowserSessionManager,
    BrowserSessionState,
)
from channel_engine.channel import (
    NormalizedMessage,
    PDDApprovedExecutionContext,
    PDDProductionSafetyService,
    PDDSendGateDecision,
    PDDSendSafetyError,
    PDDSendSession,
    PDDSendSessionState,
)
from channel_engine.control.models import KillSwitchState
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionWorker
from channel_engine.gateway import AICSGateway, DecisionRequest, DecisionResponse
from channel_engine.models.entities import utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork

from .approval import PilotApprovalService
from .models import (
    PilotBrowserObservation,
    PilotBrowserStatus,
    PilotComponentStatus,
    PilotDashboard,
    PilotDecisionTrace,
    PilotEvidence,
    PilotEvidenceType,
    PilotExecutionResult,
    PilotIntakeResult,
    PilotObservedStore,
    PilotRuntimeState,
    PilotSafetyStatus,
    PilotStoreConfig,
    PilotStoreStatus,
)
from .persistence import PilotPersistenceService


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PilotRuntimeError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@runtime_checkable
class PilotBrowserPort(Protocol):
    @property
    def real_browser_capable(self) -> bool: ...

    def open_for_manual_login(self) -> PilotBrowserObservation: ...

    def check(self) -> PilotBrowserObservation: ...

    def stop(self) -> PilotBrowserObservation: ...


@runtime_checkable
class PilotStoreIdentityProbe(Protocol):
    @property
    def read_only(self) -> bool: ...

    def detect(self) -> PilotObservedStore | None: ...


@runtime_checkable
class PilotInboundPort(Protocol):
    @property
    def real_platform_transport(self) -> bool: ...

    def health_check(self) -> bool: ...

    def receive(self) -> NormalizedMessage | None: ...

    def ack(self, message: NormalizedMessage) -> None: ...


class PilotKillSwitchPort(Protocol):
    def enabled(self) -> bool: ...

    def enable(self, *, operator: str, reason: str) -> None: ...

    def disable(self, *, operator: str, reason: str) -> None: ...


class PilotGatewayCapture:
    """Captures contract response evidence without changing Gateway Contract V1."""

    def __init__(self, gateway: AICSGateway) -> None:
        self._gateway = gateway
        self._traces: dict[str, PilotDecisionTrace] = {}
        self._lock = RLock()

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        response = self._gateway.decide(request)
        raw_citations = response.metadata.get("citations", [])
        citations: tuple[JsonValue, ...]
        if isinstance(raw_citations, list):
            citations = tuple(raw_citations)
        elif raw_citations is None:
            citations = ()
        else:
            citations = (raw_citations,)
        raw_risk = response.metadata.get("risk_level")
        trace = PilotDecisionTrace(
            decision_id=response.decision_id,
            message_id=request.message_id,
            context=request.context,
            answer=response.proposed_content,
            citations=citations,
            risk_level=raw_risk if isinstance(raw_risk, str) else None,
            action=response.action.value,
            gateway_version=response.gateway_version,
            decided_at=response.decided_at,
        )
        with self._lock:
            self._traces[response.decision_id] = trace
        return response

    def trace(self, decision_id: str) -> PilotDecisionTrace | None:
        with self._lock:
            return self._traces.get(decision_id)

    def health_check(self) -> bool:
        check = getattr(self._gateway, "health_check", None)
        if check is None:
            return True
        try:
            health = check()
        except Exception:
            return False
        return bool(getattr(health, "reachable", False))


class BrowserSessionManagerPilotPort:
    """Manual-login adapter; it never enters credentials or scans a QR code."""

    def __init__(
        self,
        manager: BrowserSessionManager,
        *,
        real_browser_capable: bool,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._manager = manager
        self._real_browser_capable = real_browser_capable
        self._clock = clock

    @property
    def real_browser_capable(self) -> bool:
        return self._real_browser_capable

    def open_for_manual_login(self) -> PilotBrowserObservation:
        return self._map(self._manager.start())

    def check(self) -> PilotBrowserObservation:
        return self._map(self._manager.heartbeat())

    def stop(self) -> PilotBrowserObservation:
        return self._map(self._manager.stop())

    def _map(self, session) -> PilotBrowserObservation:  # type: ignore[no-untyped-def]
        status = {
            BrowserSessionState.ACTIVE: PilotBrowserStatus.CONNECTED,
            BrowserSessionState.LOGIN_REQUIRED: PilotBrowserStatus.LOGIN_REQUIRED,
            BrowserSessionState.EXPIRED: PilotBrowserStatus.EXPIRED,
            BrowserSessionState.STOPPED: PilotBrowserStatus.DISCONNECTED,
        }.get(session.state, PilotBrowserStatus.DEGRADED)
        return PilotBrowserObservation(
            status=status,
            session_id=(
                session.session_id
                if status is PilotBrowserStatus.CONNECTED
                else None
            ),
            checked_at=session.last_heartbeat_at or self._clock(),
            human_login_required=session.login_state
            in {BrowserLoginState.REQUIRED, BrowserLoginState.EXPIRED},
            real_browser_started=self._real_browser_capable,
            generation=session.generation if session.generation > 0 else None,
            page_revision=(
                session.page_context.page_revision
                if session.page_context is not None
                else None
            ),
            selector_version=(
                session.page_context.selector_contract_version
                if session.page_context is not None
                else None
            ),
            failure_code=session.failure_code,
        )


class FakePilotBrowserPort:
    real_browser_capable = False

    def __init__(
        self,
        status: PilotBrowserStatus = PilotBrowserStatus.LOGIN_REQUIRED,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.status = status
        self._clock = clock
        self.start_count = 0
        self.check_count = 0
        self.stop_count = 0
        self.automatic_login_count = 0

    def open_for_manual_login(self) -> PilotBrowserObservation:
        self.start_count += 1
        return self._snapshot()

    def check(self) -> PilotBrowserObservation:
        self.check_count += 1
        return self._snapshot()

    def stop(self) -> PilotBrowserObservation:
        self.stop_count += 1
        self.status = PilotBrowserStatus.DISCONNECTED
        return self._snapshot()

    def set_status(self, status: PilotBrowserStatus) -> None:
        self.status = status

    def _snapshot(self) -> PilotBrowserObservation:
        connected = self.status is PilotBrowserStatus.CONNECTED
        return PilotBrowserObservation(
            status=self.status,
            session_id="fake-pilot-browser-session" if connected else None,
            checked_at=self._clock(),
            human_login_required=self.status
            in {PilotBrowserStatus.LOGIN_REQUIRED, PilotBrowserStatus.EXPIRED},
            real_browser_started=False,
            generation=1 if connected else None,
            page_revision="fake-pilot-page-revision" if connected else None,
            selector_version="verified-mock:pdd:merchant_chat:v1" if connected else None,
            failure_code=None if connected else f"PILOT_BROWSER_{self.status.value}",
        )


class FakePilotStoreIdentityProbe:
    read_only = True

    def __init__(self, observed: PilotObservedStore | None = None) -> None:
        self.observed = observed
        self.detect_count = 0
        self.page_write_count = 0

    def detect(self) -> PilotObservedStore | None:
        self.detect_count += 1
        return self.observed

    def set_observed(self, observed: PilotObservedStore | None) -> None:
        self.observed = observed


class FakePilotInboundPort:
    real_platform_transport = False

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self._messages: deque[NormalizedMessage] = deque()
        self.acked: list[tuple[str, str]] = []
        self.real_receive_count = 0

    def enqueue(self, message: NormalizedMessage) -> None:
        self._messages.append(message)

    def health_check(self) -> bool:
        return self.healthy

    def receive(self) -> NormalizedMessage | None:
        return self._messages.popleft() if self._messages else None

    def ack(self, message: NormalizedMessage) -> None:
        self.acked.append((message.conversation_id, message.external_message_id))


class FakePilotKillSwitch:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def enabled(self) -> bool:
        return self._enabled

    def enable(self, *, operator: str, reason: str) -> None:
        del operator, reason
        self._enabled = True

    def disable(self, *, operator: str, reason: str) -> None:
        del operator, reason
        self._enabled = False


class PDDPilotKillSwitchAdapter:
    def __init__(
        self,
        pdd_safety: PDDProductionSafetyService,
        *,
        global_control_plane=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self._pdd = pdd_safety
        self._global = global_control_plane

    def enabled(self) -> bool:
        pdd_enabled = self._pdd.status().kill_switch is KillSwitchState.ENABLED
        global_enabled = bool(
            self._global is not None
            and self._global.kill_switch_status().state is KillSwitchState.ENABLED
        )
        return pdd_enabled or global_enabled

    def enable(self, *, operator: str, reason: str) -> None:
        self._pdd.enable_kill_switch(operator=operator, reason=reason)

    def disable(self, *, operator: str, reason: str) -> None:
        self._pdd.disable_kill_switch(operator=operator, reason=reason)


class PilotReadinessLatch:
    def __init__(self) -> None:
        self._ready = False
        self._lock = RLock()

    def set(self, ready: bool) -> None:
        with self._lock:
            self._ready = ready

    def ready(self) -> bool:
        with self._lock:
            return self._ready


class PilotPDDSendSessionProvider:
    """Reference-only session view derived from manual Browser readiness."""

    def __init__(
        self,
        config: PilotStoreConfig,
        browser_snapshot: Callable[[], PilotBrowserObservation],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._config = config
        self._browser_snapshot = browser_snapshot
        self._clock = clock

    def current_session(self) -> PDDSendSession:
        browser = self._browser_snapshot()
        now = _as_utc(self._clock())
        if browser.status is PilotBrowserStatus.CONNECTED:
            state = PDDSendSessionState.HEALTHY
            expires = now + timedelta(minutes=5)
        elif browser.status is PilotBrowserStatus.EXPIRED:
            state = PDDSendSessionState.EXPIRED
            expires = now - timedelta(microseconds=1)
        else:
            state = PDDSendSessionState.DEGRADED
            expires = now + timedelta(minutes=1)
        return PDDSendSession(
            session_id=browser.session_id or "pilot-browser-session-unavailable",
            session_reference=f"session-ref://pdd/pilot/{self._config.store_id}",
            cookie_reference=self._config.credential_reference,
            state=state,
            generation=1,
            heartbeat_at=browser.checked_at,
            expires_at=expires,
        )


class PDDPilotSendPreflightGate:
    gate_name = "pdd-single-store-pilot-gate.v1"

    def __init__(
        self,
        config: PilotStoreConfig,
        persistence: PilotPersistenceService,
        kill_switch: PilotKillSwitchPort,
        readiness: PilotReadinessLatch,
        *,
        dry_run: bool = True,
        allow_real_platform_transport: bool = False,
    ) -> None:
        if allow_real_platform_transport and dry_run:
            raise ValueError("real Pilot transport cannot be enabled in dry-run mode")
        self._config = config
        self._persistence = persistence
        self._kill_switch = kill_switch
        self._readiness = readiness
        self._dry_run = dry_run
        self.allow_real_platform_transport = allow_real_platform_transport

    def authorize_send(
        self,
        context: PDDApprovedExecutionContext,
        command,
        session: PDDSendSession,
    ) -> PDDSendGateDecision:  # type: ignore[no-untyped-def]
        if self._kill_switch.enabled():
            raise PDDSendSafetyError(
                "Pilot kill switch is enabled",
                error_code="PILOT_KILL_SWITCH_ENABLED",
            )
        if not self._readiness.ready():
            raise PDDSendSafetyError(
                "Pilot runtime is not ready",
                error_code="PILOT_RUNTIME_NOT_READY",
            )
        if not self._config.approval_required or self._config.auto_reply:
            raise PDDSendSafetyError(
                "Pilot approval policy is invalid",
                error_code="PILOT_MANUAL_APPROVAL_REQUIRED",
            )
        if session.cookie_reference != self._config.credential_reference:
            raise PDDSendSafetyError(
                "Pilot session belongs to another credential reference",
                error_code="PILOT_CREDENTIAL_REFERENCE_MISMATCH",
            )
        reservation = self._persistence.get_reservation(context.execution_id)
        if reservation is None:
            raise PDDSendSafetyError(
                "Pilot Execution has no send reservation",
                error_code="PILOT_EXECUTION_RESERVATION_MISSING",
            )
        if (
            reservation.store_id != self._config.store_id
            or reservation.conversation_id != command.message.conversation_id
        ):
            raise PDDSendSafetyError(
                "Pilot Execution store or conversation does not match",
                error_code="PILOT_EXECUTION_BINDING_MISMATCH",
            )
        return PDDSendGateDecision(
            gate_name=self.gate_name,
            environment="PILOT",
            store_id=self._config.store_id,
            dry_run=self._dry_run,
        )


class PDDPilotRuntime:
    def __init__(
        self,
        config: PilotStoreConfig,
        browser: PilotBrowserPort,
        store_probe: PilotStoreIdentityProbe,
        inbound: PilotInboundPort,
        gateway: PilotGatewayCapture,
        conversation: ConversationService,
        approval: PilotApprovalService,
        persistence: PilotPersistenceService,
        kill_switch: PilotKillSwitchPort,
        readiness: PilotReadinessLatch,
        *,
        worker: ExecutionWorker | None = None,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not isinstance(browser, PilotBrowserPort):
            raise TypeError("browser does not implement PilotBrowserPort")
        if not isinstance(store_probe, PilotStoreIdentityProbe):
            raise TypeError("store probe does not implement PilotStoreIdentityProbe")
        if not store_probe.read_only:
            raise ValueError("Pilot store identity probe must be read-only")
        if not isinstance(inbound, PilotInboundPort):
            raise TypeError("inbound does not implement PilotInboundPort")
        self.config = config
        self.browser = browser
        self.store_probe = store_probe
        self.inbound = inbound
        self.gateway = gateway
        self.conversation = conversation
        self.approval = approval
        self.persistence = persistence
        self.kill_switch = kill_switch
        self.readiness = readiness
        self.worker = worker
        self._uow_factory = uow_factory or persistence.uow_factory
        self._clock = clock
        self._lock = RLock()
        now = _as_utc(clock())
        self._browser = PilotBrowserObservation(
            status=PilotBrowserStatus.DISCONNECTED,
            checked_at=now,
            human_login_required=False,
            real_browser_started=False,
        )
        self._store_status = PilotStoreStatus.UNVERIFIED
        self._message_status = PilotComponentStatus.BLOCKED
        self._ai_status = PilotComponentStatus.UNAVAILABLE
        self._state = PilotRuntimeState.INIT
        self._reason_code = "PILOT_NOT_STARTED"
        self._last_heartbeat: datetime | None = None

    def start(self) -> PilotDashboard:
        with self._lock:
            if self._state is PilotRuntimeState.READY:
                return self.status()
            self.readiness.set(False)
            self._evidence(
                PilotEvidenceType.STARTUP,
                correlation_id=self.config.store_id,
                idempotency_key=f"pilot:startup:{self.config.store_id}",
                payload={
                    "environment": "PILOT",
                    "auto_reply": False,
                    "approval_required": True,
                    "send_limit": self.config.send_limit,
                },
            )
            if self.kill_switch.enabled():
                self._block("PILOT_KILL_SWITCH_ENABLED")
                return self.status()
            try:
                self._browser = self.browser.open_for_manual_login()
            except Exception as exc:
                self._browser = PilotBrowserObservation(
                    status=PilotBrowserStatus.DEGRADED,
                    checked_at=_as_utc(self._clock()),
                    human_login_required=False,
                    real_browser_started=False,
                    failure_code=f"PILOT_BROWSER_START_{type(exc).__name__.upper()}",
                )
            self._record_browser_evidence()
            return self._resolve_after_browser()

    def check(self) -> PilotDashboard:
        with self._lock:
            if self._state in {PilotRuntimeState.INIT, PilotRuntimeState.STOPPED}:
                return self.status()
            if self.kill_switch.enabled():
                self._block("PILOT_KILL_SWITCH_ENABLED")
                return self.status()
            try:
                self._browser = self.browser.check()
            except Exception as exc:
                self._browser = PilotBrowserObservation(
                    status=PilotBrowserStatus.DEGRADED,
                    checked_at=_as_utc(self._clock()),
                    human_login_required=False,
                    real_browser_started=False,
                    failure_code=f"PILOT_BROWSER_CHECK_{type(exc).__name__.upper()}",
                )
            self._record_browser_evidence()
            dashboard = self._resolve_after_browser()
            self._sync_all_receipts()
            return dashboard

    def stop(self) -> PilotDashboard:
        with self._lock:
            self._browser = self.browser.stop()
            self.readiness.set(False)
            self._state = PilotRuntimeState.STOPPED
            self._reason_code = "PILOT_STOPPED"
            self._message_status = PilotComponentStatus.BLOCKED
            self._last_heartbeat = _as_utc(self._clock())
            return self.status()

    def poll_message(self) -> PilotIntakeResult | None:
        with self._lock:
            self._assert_ready()
            message = self.inbound.receive()
            if message is None:
                return None
            if message.channel != "pdd":
                raise PilotRuntimeError(
                    "Pilot received a non-PDD message",
                    error_code="PILOT_MESSAGE_CHANNEL_MISMATCH",
                )
            intake = self.conversation.receive(message)
            message_key = f"pilot:message:{message.conversation_id}:{message.external_message_id}"
            if self.persistence.get_evidence(message_key) is None:
                self._evidence(
                    PilotEvidenceType.MESSAGE_RECEIVED,
                    correlation_id=intake.message_id,
                    idempotency_key=message_key,
                    payload={
                        "message_id": intake.message_id,
                        "external_message_id": message.external_message_id,
                        "conversation_id": message.conversation_id,
                        "timestamp": message.timestamp.isoformat(),
                        "store_id": self.config.store_id,
                        "payload_summary": {
                            "channel": message.channel,
                            "content_length": len(message.content),
                            "sender_present": bool(message.sender.strip()),
                        },
                    },
                )
            trace = self.gateway.trace(intake.decision_id)
            if trace is None:
                trace = self._fallback_trace(intake.decision_id, intake.message_id)
            decision_key = f"pilot:decision:{intake.decision_id}"
            if self.persistence.get_evidence(decision_key) is None:
                self._evidence(
                    PilotEvidenceType.DECISION_CREATED,
                    correlation_id=intake.decision_id,
                    idempotency_key=decision_key,
                    payload={
                        "decision_id": trace.decision_id,
                        "message_id": trace.message_id,
                        "context": trace.context,
                        "answer": trace.answer,
                        "citations": list(trace.citations),
                        "risk_level": trace.risk_level,
                        "action": trace.action,
                        "state": "WAITING_APPROVAL",
                        "gateway_version": trace.gateway_version,
                    },
                )
            self.inbound.ack(message)
            return PilotIntakeResult(
                conversation_id=intake.conversation_id,
                message_id=intake.message_id,
                external_message_id=message.external_message_id,
                decision_id=intake.decision_id,
                answer=trace.answer,
                citations=trace.citations,
                risk_level=trace.risk_level,
            )

    def approve_and_execute(
        self,
        decision_id: str,
        approved_by: str,
    ) -> PilotExecutionResult:
        with self._lock:
            self._assert_ready()
            enqueued = self.approval.approve_and_reserve(decision_id, approved_by)
            with self._uow_factory() as uow:
                durable_approval = uow.require_repository().get_approval_for_decision(
                    decision_id
                )
            if durable_approval is None or durable_approval.decided_by is None:
                raise PilotRuntimeError(
                    "Pilot Approval evidence is unavailable",
                    error_code="PILOT_APPROVAL_EVIDENCE_MISSING",
                )
            self._evidence(
                PilotEvidenceType.APPROVAL_GRANTED,
                correlation_id=decision_id,
                idempotency_key=f"pilot:approval:{enqueued.approval_id}",
                payload={
                    "decision_id": decision_id,
                    "approval_id": enqueued.approval_id,
                    "execution_id": enqueued.execution_id,
                    "approved_by": durable_approval.decided_by,
                    "manual_approval": True,
                },
            )
            if self.worker is not None:
                self.worker.run_execution(enqueued.execution_id)
            return self.sync_execution(enqueued.execution_id)

    def sync_execution(self, execution_id: str) -> PilotExecutionResult:
        with self._lock:
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                execution = repo.get_execution(execution_id)
                receipt = repo.get_receipt_for_execution(execution_id)
            self._evidence(
                PilotEvidenceType.EXECUTION_STARTED,
                correlation_id=execution_id,
                idempotency_key=(
                    f"pilot:execution:{execution_id}:{execution.state.value}"
                ),
                payload={
                    "execution_id": execution_id,
                    "decision_id": execution.decision_id,
                    "state": execution.state.value,
                    "attempt": execution.attempt,
                },
            )
            if receipt is not None:
                self._evidence(
                    PilotEvidenceType.RECEIPT_RECORDED,
                    correlation_id=execution_id,
                    idempotency_key=f"pilot:receipt:{receipt.receipt_id}",
                    payload={
                        "receipt_id": receipt.receipt_id,
                        "execution_id": execution_id,
                        "outcome": receipt.outcome.value,
                        "recorded_at": receipt.recorded_at.isoformat(),
                        "customer_message_sent": bool(
                            receipt.details.get("customer_message_sent", False)
                        ),
                        "real_platform_called": bool(
                            receipt.details.get("real_platform_called", False)
                        ),
                        "mode": receipt.details.get("mode", "UNKNOWN"),
                    },
                )
            return PilotExecutionResult(
                decision_id=execution.decision_id,
                approval_id=execution.approval_id,
                execution_id=execution.execution_id,
                execution_state=execution.state.value,
                receipt_id=receipt.receipt_id if receipt else None,
                receipt_outcome=receipt.outcome.value if receipt else None,
                customer_message_sent=bool(
                    receipt and receipt.details.get("customer_message_sent", False)
                ),
            )

    def enable_kill_switch(self, *, operator: str, reason: str) -> PilotDashboard:
        with self._lock:
            self.kill_switch.enable(operator=operator, reason=reason)
            self.readiness.set(False)
            self._block("PILOT_KILL_SWITCH_ENABLED")
            self._evidence(
                PilotEvidenceType.KILL_SWITCH_CHANGED,
                correlation_id=self.config.store_id,
                idempotency_key=f"pilot:kill-switch:enabled:{self._clock().isoformat()}",
                payload={"enabled": True, "operator": operator, "reason": reason},
            )
            return self.status()

    def disable_kill_switch(self, *, operator: str, reason: str) -> PilotDashboard:
        with self._lock:
            self.kill_switch.disable(operator=operator, reason=reason)
            self._state = PilotRuntimeState.DEGRADED
            self._reason_code = "PILOT_RECHECK_REQUIRED"
            self._evidence(
                PilotEvidenceType.KILL_SWITCH_CHANGED,
                correlation_id=self.config.store_id,
                idempotency_key=f"pilot:kill-switch:disabled:{self._clock().isoformat()}",
                payload={"enabled": False, "operator": operator, "reason": reason},
            )
            return self.status()

    def evidence(self, limit: int = 200) -> list[PilotEvidence]:
        return self.persistence.list_evidence(self.config.store_id, limit)

    def browser_snapshot(self) -> PilotBrowserObservation:
        with self._lock:
            return self._browser

    def status(self) -> PilotDashboard:
        with self._lock:
            kill_enabled = self.kill_switch.enabled()
            today = _as_utc(self._clock()).date()
            sent = self.persistence.today_count(self.config.store_id, today)
            ready = self._state is PilotRuntimeState.READY and not kill_enabled
            node = (
                "ONLINE"
                if ready
                else "STOPPED"
                if self._state in {PilotRuntimeState.INIT, PilotRuntimeState.STOPPED}
                else "BLOCKED"
                if self._state is PilotRuntimeState.BLOCKED or kill_enabled
                else "DEGRADED"
            )
            channel = (
                PilotComponentStatus.READY
                if ready
                else PilotComponentStatus.BLOCKED
            )
            return PilotDashboard(
                node=node,  # type: ignore[arg-type]
                runtime_state=self._state,
                store_id=self.config.store_id,
                store_name=self.config.store_name,
                store_status=self._store_status,
                browser=self._browser.status,
                message=self._message_status,
                ai=self._ai_status,
                channel=channel,
                safety=(
                    PilotSafetyStatus.KILL_SWITCH
                    if kill_enabled
                    else PilotSafetyStatus.PILOT_MODE
                ),
                today_send=sent,
                send_limit=self.config.send_limit,
                last_heartbeat=self._last_heartbeat,
                reason_code=(
                    "PILOT_KILL_SWITCH_ENABLED" if kill_enabled else self._reason_code
                ),
            )

    def _resolve_after_browser(self) -> PilotDashboard:
        self._last_heartbeat = _as_utc(self._clock())
        if self._browser.status in {
            PilotBrowserStatus.LOGIN_REQUIRED,
            PilotBrowserStatus.EXPIRED,
        }:
            self.readiness.set(False)
            self._state = PilotRuntimeState.WAITING_FOR_LOGIN
            self._reason_code = "PILOT_MANUAL_LOGIN_REQUIRED"
            self._store_status = PilotStoreStatus.UNVERIFIED
            self._message_status = PilotComponentStatus.BLOCKED
            return self.status()
        if self._browser.status is not PilotBrowserStatus.CONNECTED:
            self._block("PILOT_BROWSER_NOT_CONNECTED")
            return self.status()

        self._state = PilotRuntimeState.VALIDATING
        observed = self.store_probe.detect()
        if observed is None:
            self._store_status = PilotStoreStatus.UNVERIFIED
            self._block("PILOT_STORE_IDENTITY_UNVERIFIED")
            return self.status()
        if (
            observed.platform != self.config.platform
            or observed.store_id != self.config.store_id
            or observed.store_name != self.config.store_name
        ):
            self._store_status = PilotStoreStatus.MISMATCH
            self._block("PILOT_STORE_MISMATCH")
            self._evidence(
                PilotEvidenceType.SEND_BLOCKED,
                correlation_id=self.config.store_id,
                idempotency_key=(
                    f"pilot:store-mismatch:{observed.store_id}:{observed.observed_at.isoformat()}"
                ),
                payload={
                    "reason_code": "PILOT_STORE_MISMATCH",
                    "expected_store_id": self.config.store_id,
                    "observed_store_id": observed.store_id,
                },
            )
            return self.status()
        self._store_status = PilotStoreStatus.MATCHED
        self._evidence(
            PilotEvidenceType.STORE_BINDING,
            correlation_id=self.config.store_id,
            idempotency_key=f"pilot:store-matched:{self.config.store_id}",
            payload={
                "platform": observed.platform,
                "store_id": observed.store_id,
                "store_name": observed.store_name,
                "source": observed.source,
            },
        )

        self._ai_status = (
            PilotComponentStatus.READY
            if self.gateway.health_check()
            else PilotComponentStatus.UNAVAILABLE
        )
        self._message_status = (
            PilotComponentStatus.READY
            if self.inbound.health_check()
            else PilotComponentStatus.UNAVAILABLE
        )
        if (
            self._ai_status is not PilotComponentStatus.READY
            or self._message_status is not PilotComponentStatus.READY
        ):
            self._state = PilotRuntimeState.DEGRADED
            self._reason_code = (
                "PILOT_AI_UNAVAILABLE"
                if self._ai_status is not PilotComponentStatus.READY
                else "PILOT_MESSAGE_TRANSPORT_UNAVAILABLE"
            )
            self.readiness.set(False)
            return self.status()
        self._state = PilotRuntimeState.READY
        self._reason_code = "PILOT_READY"
        self.readiness.set(True)
        return self.status()

    def _assert_ready(self) -> None:
        if self.kill_switch.enabled():
            raise PilotRuntimeError(
                "Pilot kill switch is enabled",
                error_code="PILOT_KILL_SWITCH_ENABLED",
            )
        if self._state is not PilotRuntimeState.READY or not self.readiness.ready():
            raise PilotRuntimeError(
                "Pilot runtime is not ready",
                error_code=self._reason_code,
            )

    def _block(self, reason_code: str) -> None:
        self.readiness.set(False)
        self._state = PilotRuntimeState.BLOCKED
        self._reason_code = reason_code
        self._message_status = PilotComponentStatus.BLOCKED

    def _record_browser_evidence(self) -> None:
        session_key = self._browser.session_id or "no-session"
        self._evidence(
            PilotEvidenceType.BROWSER_SESSION,
            correlation_id=self.config.store_id,
            idempotency_key=f"pilot:browser:{session_key}:{self._browser.status.value}",
            payload={
                "status": self._browser.status.value,
                "human_login_required": self._browser.human_login_required,
                "real_browser_started": self._browser.real_browser_started,
                "generation": self._browser.generation,
                "page_revision": self._browser.page_revision,
                "selector_version": self._browser.selector_version,
                "failure_code": self._browser.failure_code,
            },
        )

    def _fallback_trace(self, decision_id: str, message_id: str) -> PilotDecisionTrace:
        with self._uow_factory() as uow:
            decision = uow.require_repository().get_decision(decision_id)
        return PilotDecisionTrace(
            decision_id=decision_id,
            message_id=message_id,
            context={"evidence_replayed": True},
            answer=decision.proposed_content,
            citations=(),
            action=decision.action.value,
            gateway_version=decision.gateway_version,
            decided_at=decision.created_at,
        )

    def _sync_all_receipts(self) -> None:
        for reservation in self.persistence.list_reservations(self.config.store_id):
            self.sync_execution(reservation.execution_id)

    def _evidence(
        self,
        evidence_type: PilotEvidenceType,
        *,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> PilotEvidence:
        return self.persistence.evidence(
            evidence_type=evidence_type,
            store_id=self.config.store_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload=payload,
            recorded_at=_as_utc(self._clock()),
        )


__all__ = [
    "BrowserSessionManagerPilotPort",
    "FakePilotBrowserPort",
    "FakePilotInboundPort",
    "FakePilotKillSwitch",
    "FakePilotStoreIdentityProbe",
    "PDDPilotKillSwitchAdapter",
    "PDDPilotRuntime",
    "PDDPilotSendPreflightGate",
    "PilotBrowserPort",
    "PilotGatewayCapture",
    "PilotInboundPort",
    "PilotKillSwitchPort",
    "PilotPDDSendSessionProvider",
    "PilotReadinessLatch",
    "PilotRuntimeError",
    "PilotStoreIdentityProbe",
]
