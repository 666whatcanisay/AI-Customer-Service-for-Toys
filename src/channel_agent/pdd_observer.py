from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event, Thread
from typing import Callable, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .edge_pdd_observe import (
    PDDSelectorRuntimeEvidence,
    PDDWorkspaceBoundaryError,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceSnapshot,
)
from .edge_spool import DurableEdgeSpool, EdgeObservation
from .observation_stages import ObservationStage


class PDDObserverError(RuntimeError):
    """Fail-closed boundary for the production read-only observer."""


class PDDObserverFatalError(PDDObserverError):
    """Evidence or page identity failure that must stop the observer."""


class PDDConversationNotActive(PDDObserverError):
    """The conversation is listed but is not the currently visible page."""


class ObservationOrigin(StrEnum):
    LIVE_PDD = "LIVE_PDD"
    STARTUP_UNREAD = "STARTUP_UNREAD"
    SYNTHETIC = "SYNTHETIC"


class PDDConversationSummary(BaseModel):
    """Minimal, privacy-safe row read from the PDD conversation list."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    unread_count: int | None = Field(default=None, ge=0, le=9999)
    last_activity_at: AwareDatetime
    latest_sequence: int | None = Field(default=None, ge=1)


class PDDReadOnlyConversationDriver(Protocol):
    """Evidence-backed page driver. It deliberately exposes no write method."""

    def scan_conversations(self) -> tuple[PDDConversationSummary, ...]: ...

    def capture_conversation(
        self, summary: PDDConversationSummary
    ) -> PDDWorkspaceSnapshot: ...

    def selector_evidence(self, capability: str) -> PDDSelectorRuntimeEvidence: ...


class ObservationForwarder(Protocol):
    def __call__(self, observation: EdgeObservation) -> object: ...


class ObserverDiagnosticSink(Protocol):
    def __call__(
        self,
        code: str,
        summary: PDDConversationSummary,
        details: dict[str, object],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PDDObserverScanResult:
    conversations_seen: int
    conversations_captured: int
    observations_forwarded: int
    baselines_established: int
    manual_review_required: int


class PDDMessageObserver:
    """Formal OBSERVE_ONLY coordinator used by ChannelAgent 2.0 runtime.

    The coordinator never touches a reply box and has no transport dependency.
    Host acknowledgement remains the only way its per-conversation cursor advances.
    """

    def __init__(
        self,
        *,
        driver: PDDReadOnlyConversationDriver,
        mapper: PDDWorkspaceObservationMapper,
        spool: DurableEdgeSpool,
        forward: ObservationForwarder,
        diagnostic: ObserverDiagnosticSink | None = None,
        stage: ObservationStage = ObservationStage.AI_SUGGESTIONS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._driver = driver
        self._mapper = mapper
        self._spool = spool
        self._forward = forward
        self._diagnostic = diagnostic or (lambda _code, _summary, _details: None)
        self._stage = stage
        self._clock = clock

    def scan_once(self) -> PDDObserverScanResult:
        now = self._clock().astimezone(UTC)
        evidence = self._driver.selector_evidence("OBSERVE")
        try:
            evidence.assert_active(now=now, expected_capability="OBSERVE")
        except PDDWorkspaceBoundaryError as exc:
            raise PDDObserverFatalError(
                "OBSERVE selector evidence is unavailable"
            ) from exc

        summaries = self._driver.scan_conversations()
        seen: set[tuple[str, str, str]] = set()
        captured = forwarded = baselines = manual = 0
        for summary in summaries:
            identity = (
                summary.store_id,
                summary.platform_store_id or "",
                summary.conversation_id,
            )
            if identity in seen:
                raise PDDObserverError("conversation list contains an unstable duplicate identity")
            seen.add(identity)
            if not self._stage.allows(ObservationStage.MESSAGE_CAPTURE):
                continue
            cursor = self._spool.conversation_cursor(*identity)

            if cursor is None and summary.unread_count is None:
                manual += 1
                self._diagnostic(
                    "STARTUP_UNREAD_STATE_UNKNOWN",
                    summary,
                    {"action": "HUMAN_CONFIRM_IMPORT", "write_operations": 0},
                )
                continue
            if cursor is not None and summary.latest_sequence is not None:
                if summary.latest_sequence <= cursor[1] and not summary.unread_count:
                    continue

            try:
                snapshot = self._driver.capture_conversation(summary)
            except PDDConversationNotActive:
                manual += 1
                self._diagnostic(
                    "CONVERSATION_REQUIRES_HUMAN_SELECTION",
                    summary,
                    {
                        "action": "HUMAN_SELECT_CONVERSATION",
                        "write_operations": 0,
                    },
                )
                continue
            captured += 1
            self._validate_capture(summary, snapshot, evidence)
            latest_sequence = max(
                (message.sequence for message in snapshot.messages), default=0
            )

            if cursor is None and summary.unread_count == 0:
                if latest_sequence:
                    self._spool.establish_high_water(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        cursor=_cursor(summary, latest_sequence),
                        source_sequence=latest_sequence,
                    )
                    baselines += 1
                continue

            after_sequence = cursor[1] if cursor is not None else 0
            if getattr(self._driver, "source_kind", "LIVE_PDD") == "OFFLINE_REPLAY":
                origin = ObservationOrigin.SYNTHETIC
            else:
                origin = (
                    ObservationOrigin.STARTUP_UNREAD
                    if cursor is None
                    else ObservationOrigin.LIVE_PDD
                )
            pending, unknown = _unhandled_customer_messages(
                snapshot.messages,
                after_sequence=after_sequence,
            )
            if unknown:
                manual += 1
                self._diagnostic(
                    "MESSAGE_ROLE_UNKNOWN",
                    summary,
                    {
                        "message_count": len(unknown),
                        "action": "REVIEW_SELECTOR_EVIDENCE",
                        "write_operations": 0,
                    },
                )
            if not pending:
                # Once this conversation has entered the durable flow, only a
                # Host ACK may advance its cursor. Re-reading a handled operator
                # tail is safer than inventing an acknowledgement locally.
                continue

            customer_snapshot = snapshot.model_copy(update={"messages": pending})
            observations = self._mapper.map_customer_messages(
                customer_snapshot,
                after_sequence=after_sequence,
                origin=origin.value,
                now=now,
            )
            for observation in observations:
                self._forward(observation)
                forwarded += 1

        return PDDObserverScanResult(
            conversations_seen=len(summaries),
            conversations_captured=captured,
            observations_forwarded=forwarded,
            baselines_established=baselines,
            manual_review_required=manual,
        )

    @staticmethod
    def _validate_capture(
        summary: PDDConversationSummary,
        snapshot: PDDWorkspaceSnapshot,
        evidence: PDDSelectorRuntimeEvidence,
    ) -> None:
        if snapshot.page_state not in {
            "CUSTOMER_SERVICE_READY",
            "CUSTOMER_SERVICE_RUNNING",
        }:
            raise PDDObserverFatalError("customer service page is not ready")
        if snapshot.page_fingerprint != evidence.page_fingerprint:
            raise PDDObserverFatalError(
                "PDD page fingerprint changed during observation"
            )
        if snapshot.selector_evidence_hash not in {None, evidence.evidence_hash}:
            raise PDDObserverFatalError(
                "PDD selector evidence changed during observation"
            )
        if (
            snapshot.store_id != summary.store_id
            or snapshot.platform_store_id != summary.platform_store_id
            or snapshot.conversation_id != summary.conversation_id
            or snapshot.customer_reference != summary.customer_reference
        ):
            raise PDDObserverFatalError(
                "conversation identity changed during read-only capture"
            )


def _unhandled_customer_messages(
    messages: tuple[PDDWorkspaceMessage, ...],
    *,
    after_sequence: int,
) -> tuple[tuple[PDDWorkspaceMessage, ...], tuple[PDDWorkspaceMessage, ...]]:
    new_messages = tuple(message for message in messages if message.sequence > after_sequence)
    last_operator_sequence = max(
        (message.sequence for message in new_messages if message.sender == "OPERATOR"),
        default=after_sequence,
    )
    customers = tuple(
        message
        for message in new_messages
        if message.sender == "CUSTOMER" and message.sequence > last_operator_sequence
    )
    unknown = tuple(message for message in new_messages if message.sender == "UNKNOWN")
    return customers, unknown


def _cursor(summary: PDDConversationSummary, sequence: int) -> str:
    platform_store = summary.platform_store_id or "unknown"
    return f"{summary.store_id}:{platform_store}:{summary.conversation_id}:{sequence}"


class PDDObserverRunner:
    """Lifecycle wrapper used by the formal Windows Agent composition."""

    def __init__(
        self,
        observer: PDDMessageObserver,
        *,
        interval_seconds: float = 1.0,
        error_sink: Callable[[str], None] | None = None,
    ) -> None:
        self._observer = observer
        self._interval = max(0.25, min(interval_seconds, 10.0))
        self._error_sink = error_sink or (lambda _code: None)
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="channel-agent-pdd-observer",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, timeout))
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._observer.scan_once()
            except PDDObserverFatalError as exc:
                code = f"PDD_OBSERVER_FATAL_{type(exc).__name__.upper()}"[:120]
                self._error_sink(code)
                self._stop.set()
                break
            except Exception as exc:
                code = f"PDD_OBSERVER_{type(exc).__name__.upper()}"[:120]
                self._error_sink(code)
            self._stop.wait(self._interval)


__all__ = [
    "ObservationOrigin",
    "PDDConversationSummary",
    "PDDConversationNotActive",
    "PDDMessageObserver",
    "PDDObserverError",
    "PDDObserverFatalError",
    "PDDObserverScanResult",
    "PDDObserverRunner",
    "PDDReadOnlyConversationDriver",
]
