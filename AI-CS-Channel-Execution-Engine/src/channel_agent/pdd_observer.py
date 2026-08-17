from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Event, Thread
from typing import Protocol

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
from .pdd_conversation_capture import (
    DurablePDDConversationCaptureStore,
    PDDConversationCaptureState,
    PDDReplyAttentionState,
)


class PDDObserverError(RuntimeError):
    """Fail-closed boundary for the production read-only observer."""


class PDDObserverFatalError(PDDObserverError):
    """Evidence or page identity failure that must stop the observer."""


class PDDConversationNotActive(PDDObserverError):
    """The conversation is listed but is not the currently visible page."""


class PDDConversationNavigationError(PDDObserverError):
    """A narrowly-scoped conversation navigation was rejected fail-closed."""

    def __init__(self, message: str, *, error_code: str, manual_review: bool) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.manual_review = manual_review


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
    latest_message_id: str | None = Field(default=None, min_length=1, max_length=255)
    page_position: int | None = Field(default=None, ge=0, le=10_000)
    attention_state: PDDReplyAttentionState = PDDReplyAttentionState.NONE
    attention_verified: bool = False
    attention_seconds: int | None = Field(default=None, ge=0, le=604_800)
    attention_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )


class PDDReadOnlyConversationDriver(Protocol):
    """Evidence-backed page driver. It deliberately exposes no write method."""

    def scan_conversations(self) -> tuple[PDDConversationSummary, ...]: ...

    def capture_conversation(
        self, summary: PDDConversationSummary
    ) -> PDDWorkspaceSnapshot: ...

    def selector_evidence(self, capability: str) -> PDDSelectorRuntimeEvidence: ...

    @property
    def navigation_enabled(self) -> bool: ...

    def navigate_to_conversation(
        self,
        summary: PDDConversationSummary,
        *,
        allow_attention_missing: bool = False,
    ) -> None: ...


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
        capture_store: DurablePDDConversationCaptureStore | None = None,
        stage: ObservationStage = ObservationStage.AI_SUGGESTIONS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._driver = driver
        self._mapper = mapper
        self._spool = spool
        self._forward = forward
        self._diagnostic = diagnostic or (lambda _code, _summary, _details: None)
        self._capture_store = capture_store
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

        # scan_once is single-flight. Any NAVIGATING record present before a
        # new scan is therefore an interrupted claim, not concurrent work.
        # Recover on every scan so a transient page/mapper/forward failure
        # does not require an Agent process restart before the task can retry.
        if self._capture_store is not None:
            self._capture_store.recover_interrupted()

        summaries = self._driver.scan_conversations()
        seen: set[tuple[str, str, str]] = set()
        captured = forwarded = baselines = manual = 0
        summaries_by_identity: dict[tuple[str, str, str], PDDConversationSummary] = {}
        for summary in summaries:
            identity = (
                summary.store_id,
                summary.platform_store_id or "",
                summary.conversation_id,
            )
            if identity in seen:
                raise PDDObserverError("conversation list contains an unstable duplicate identity")
            seen.add(identity)
            summaries_by_identity[identity] = summary
            if self._capture_store is not None:
                cursor = self._spool.conversation_cursor(*identity)
                self._capture_store.reconcile_ack(
                    summary.store_id,
                    summary.platform_store_id,
                    summary.conversation_id,
                    None if cursor is None else cursor[1],
                )
                self._capture_store.observe_attention(
                    store_id=summary.store_id,
                    platform_store_id=summary.platform_store_id,
                    conversation_id=summary.conversation_id,
                    attention_state=summary.attention_state,
                    attention_verified=summary.attention_verified,
                    attention_seconds=summary.attention_seconds,
                    attention_evidence_hash=summary.attention_evidence_hash,
                    page_position=summary.page_position,
                    latest_sequence=summary.latest_sequence,
                    latest_message_id=summary.latest_message_id,
                )

        scheduled: tuple[tuple[str, str, str], ...] = ()
        if self._capture_store is not None and getattr(
            self._driver, "navigation_enabled", False
        ):
            scheduled = tuple(
                (item.store_id, item.platform_store_id or "", item.conversation_id)
                for item in self._capture_store.pending(limit=20)
                if (item.store_id, item.platform_store_id or "", item.conversation_id)
                in summaries_by_identity
            )
        scheduled_set = set(scheduled)
        ordered = [summaries_by_identity[item] for item in scheduled]
        ordered.extend(
            summary
            for identity, summary in summaries_by_identity.items()
            if identity not in scheduled_set
        )

        for summary in ordered:
            identity = (
                summary.store_id,
                summary.platform_store_id or "",
                summary.conversation_id,
            )
            if not self._stage.allows(ObservationStage.MESSAGE_CAPTURE):
                continue
            cursor = self._spool.conversation_cursor(*identity)
            is_scheduled = identity in scheduled_set
            capture_record = (
                self._capture_store.get(
                    summary.store_id,
                    summary.platform_store_id,
                    summary.conversation_id,
                )
                if is_scheduled and self._capture_store is not None
                else None
            )

            manual_current_conversation = bool(
                cursor is None
                and summary.unread_count is None
                and not is_scheduled
                and getattr(self._driver, "navigation_enabled", None) is False
            )
            if manual_current_conversation:
                # With automatic navigation explicitly disabled, establish a
                # high-water mark only for the conversation the operator has
                # already selected.  ``capture_conversation`` rejects every
                # other list row, so this path cannot click, scroll, or import
                # another customer's history.  New messages arriving after
                # this baseline enter the normal durable Observation flow.
                try:
                    baseline = self._driver.capture_conversation(summary)
                except PDDConversationNotActive:
                    continue
                captured += 1
                self._validate_capture(summary, baseline, evidence)
                baseline = self._resolve_message_sequences(baseline)
                baseline_sequence = max(
                    (message.sequence for message in baseline.messages), default=0
                )
                if baseline_sequence:
                    self._spool.establish_high_water(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        cursor=_cursor(summary, baseline_sequence),
                        source_sequence=baseline_sequence,
                    )
                    baselines += 1
                continue
            if cursor is None and summary.unread_count is None and not is_scheduled:
                manual += 1
                self._diagnostic(
                    "STARTUP_UNREAD_STATE_UNKNOWN",
                    summary,
                    {"action": "HUMAN_CONFIRM_IMPORT", "write_operations": 0},
                )
                continue
            if cursor is not None and summary.latest_sequence is not None:
                if (
                    summary.latest_sequence <= cursor[1]
                    and not summary.unread_count
                    and not is_scheduled
                ):
                    continue
            if is_scheduled and self._capture_store is not None:
                if not self._capture_store.claim(
                    summary.store_id,
                    summary.platform_store_id,
                    summary.conversation_id,
                ):
                    continue

            try:
                snapshot = self._driver.capture_conversation(summary)
            except PDDConversationNotActive:
                if is_scheduled and getattr(self._driver, "navigation_enabled", False):
                    try:
                        self._driver.navigate_to_conversation(
                            summary,
                            allow_attention_missing=(
                                capture_record is not None
                                and (
                                    not capture_record.attention_present
                                    or capture_record.last_error_code
                                    == "RECOVERED_AFTER_NAVIGATION_INTERRUPTION"
                                )
                            ),
                        )
                        snapshot = self._driver.capture_conversation(summary)
                    except PDDConversationNotActive:
                        if self._capture_store is not None:
                            self._capture_store.mark_failure(
                                store_id=summary.store_id,
                                platform_store_id=summary.platform_store_id,
                                conversation_id=summary.conversation_id,
                                error_code="PDD_NAVIGATION_TARGET_NOT_STABLE",
                                manual_review=False,
                            )
                        self._diagnostic(
                            "PDD_NAVIGATION_TARGET_NOT_STABLE",
                            summary,
                            {
                                "action": "RETRY_VERIFIED_CONVERSATION_NAVIGATION",
                                "write_operations": 0,
                            },
                        )
                        continue
                    except PDDConversationNavigationError as exc:
                        if self._capture_store is not None:
                            self._capture_store.mark_failure(
                                store_id=summary.store_id,
                                platform_store_id=summary.platform_store_id,
                                conversation_id=summary.conversation_id,
                                error_code=exc.error_code,
                                manual_review=exc.manual_review,
                            )
                        if exc.manual_review:
                            manual += 1
                        self._diagnostic(
                            exc.error_code,
                            summary,
                            {
                                "action": (
                                    "HUMAN_REVIEW_CONVERSATION_NAVIGATION"
                                    if exc.manual_review
                                    else "PAUSE_AND_RETRY_CONVERSATION_NAVIGATION"
                                ),
                                "write_operations": 0,
                            },
                        )
                        continue
                    except PDDObserverError:
                        if self._capture_store is not None:
                            self._capture_store.mark_failure(
                                store_id=summary.store_id,
                                platform_store_id=summary.platform_store_id,
                                conversation_id=summary.conversation_id,
                                error_code="PDD_CAPTURE_RETRY_REQUIRED",
                                manual_review=False,
                            )
                        raise
                else:
                    if getattr(self._driver, "navigation_enabled", None) is False:
                        # Current-page mode intentionally never selects another
                        # conversation.  Inactive list rows are expected and
                        # must not poison the Agent health state as a failure.
                        # The already-open conversation is still captured and
                        # forwarded by its matching summary in this same scan.
                        continue
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
            snapshot = self._resolve_message_sequences(snapshot)
            latest_sequence = max(
                (message.sequence for message in snapshot.messages), default=0
            )

            if cursor is None and summary.unread_count == 0 and not is_scheduled:
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
                not_before=(
                    capture_record.first_observed_at
                    if cursor is None
                    and capture_record is not None
                    and not capture_record.attention_present
                    else None
                ),
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
            preview_only_schedule = (
                is_scheduled
                and capture_record is not None
                and not capture_record.attention_present
            )
            if is_scheduled and not any(
                item.sender == "CUSTOMER" for item in snapshot.messages
            ):
                # A privacy-safe preview hash can change because the visible row
                # switched to an operator/system tail.  That is a useful new
                # baseline, not evidence that a customer message needs review.
                if (
                    preview_only_schedule
                    and not unknown
                    and self._capture_store is not None
                ):
                    self._capture_store.mark_preview_baseline(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        latest_message_id=summary.latest_message_id,
                    )
                    continue
                if self._capture_store is not None:
                    self._capture_store.mark_failure(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        error_code="PDD_CAPTURE_NO_CUSTOMER_MESSAGE",
                        manual_review=True,
                    )
                manual += 1
                self._diagnostic(
                    "PDD_CAPTURE_NO_CUSTOMER_MESSAGE",
                    summary,
                    {
                        "action": "REVIEW_CONVERSATION_AND_SELECTOR_EVIDENCE",
                        "write_operations": 0,
                    },
                )
                continue
            if not pending:
                # No customer message newer than the preview task's first
                # observation means this row change was not an inbound message.
                # Complete it as a baseline so it cannot keep driving navigation.
                if preview_only_schedule and self._capture_store is not None:
                    self._capture_store.mark_preview_baseline(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        latest_message_id=summary.latest_message_id,
                    )
                    continue
                # Once this conversation has entered the durable flow, only a
                # Host ACK may advance its cursor. Re-reading a handled operator
                # tail is safer than inventing an acknowledgement locally.
                if is_scheduled and self._capture_store is not None:
                    latest_customer = max(
                        (
                            item
                            for item in snapshot.messages
                            if item.sender == "CUSTOMER"
                        ),
                        key=lambda item: item.sequence,
                        default=None,
                    )
                    if latest_customer is not None:
                        self._capture_store.mark_captured(
                            store_id=summary.store_id,
                            platform_store_id=summary.platform_store_id,
                            conversation_id=summary.conversation_id,
                            # Keep the privacy-safe conversation-list row
                            # watermark. The captured message sequence remains
                            # the durable customer-message high-water mark.
                            latest_message_id=summary.latest_message_id,
                            latest_sequence=latest_customer.sequence,
                            host_acked_sequence=(
                                None if cursor is None else cursor[1]
                            ),
                        )
                continue

            observations = self._mapper.map_customer_messages(
                snapshot,
                after_sequence=after_sequence,
                origin=origin.value,
                selected_message_ids=frozenset(
                    item.external_message_id for item in pending
                ),
                now=now,
            )
            for observation in observations:
                self._forward(observation)
                forwarded += 1

            if is_scheduled and self._capture_store is not None:
                latest_customer = max(
                    (item for item in snapshot.messages if item.sender == "CUSTOMER"),
                    key=lambda item: item.sequence,
                    default=None,
                )
                if latest_customer is not None:
                    cursor_after = self._spool.conversation_cursor(*identity)
                    record = self._capture_store.mark_captured(
                        store_id=summary.store_id,
                        platform_store_id=summary.platform_store_id,
                        conversation_id=summary.conversation_id,
                        latest_message_id=summary.latest_message_id,
                        latest_sequence=latest_customer.sequence,
                        host_acked_sequence=(
                            None if cursor_after is None else cursor_after[1]
                        ),
                    )
                    if record.state is PDDConversationCaptureState.COMPLETED:
                        # ACK has completed. Recheck the same active conversation
                        # once so a second customer message arriving during the
                        # first capture cannot hide behind a consumed red marker.
                        try:
                            extra = self._driver.capture_conversation(summary)
                        except PDDConversationNotActive:
                            continue
                        self._validate_capture(summary, extra, evidence)
                        extra = self._resolve_message_sequences(extra)
                        cursor_after = self._spool.conversation_cursor(*identity)
                        after = 0 if cursor_after is None else cursor_after[1]
                        extra_pending, extra_unknown = _unhandled_customer_messages(
                            extra.messages,
                            after_sequence=after,
                        )
                        if extra_unknown:
                            manual += 1
                            self._diagnostic(
                                "MESSAGE_ROLE_UNKNOWN",
                                summary,
                                {
                                    "message_count": len(extra_unknown),
                                    "action": "REVIEW_SELECTOR_EVIDENCE",
                                    "write_operations": 0,
                                },
                            )
                        if extra_pending:
                            extra_observations = self._mapper.map_customer_messages(
                                extra,
                                after_sequence=after,
                                origin=ObservationOrigin.LIVE_PDD.value,
                                selected_message_ids=frozenset(
                                    item.external_message_id for item in extra_pending
                                ),
                                now=now,
                            )
                            for observation in extra_observations:
                                self._forward(observation)
                                forwarded += 1
                            latest_extra = max(
                                extra_pending, key=lambda item: item.sequence
                            )
                            cursor_final = self._spool.conversation_cursor(*identity)
                            self._capture_store.mark_captured(
                                store_id=summary.store_id,
                                platform_store_id=summary.platform_store_id,
                                conversation_id=summary.conversation_id,
                                # The list row was not rescanned during this
                                # same-conversation ACK recheck. Preserve its
                                # last observed row watermark; a later row
                                # change will intentionally reopen the task.
                                latest_message_id=summary.latest_message_id,
                                latest_sequence=latest_extra.sequence,
                                host_acked_sequence=(
                                    None if cursor_final is None else cursor_final[1]
                                ),
                            )

        return PDDObserverScanResult(
            conversations_seen=len(summaries),
            conversations_captured=captured,
            observations_forwarded=forwarded,
            baselines_established=baselines,
            manual_review_required=manual,
        )

    def _resolve_message_sequences(
        self, snapshot: PDDWorkspaceSnapshot
    ) -> PDDWorkspaceSnapshot:
        messages = tuple(
            message.model_copy(
                update={
                    "sequence": self._spool.resolve_message_sequence(
                        store_id=snapshot.store_id,
                        platform_store_id=snapshot.platform_store_id,
                        conversation_id=snapshot.conversation_id,
                        external_message_id=message.external_message_id,
                        page_sequence=message.sequence,
                    )
                }
            )
            for message in snapshot.messages
        )
        return snapshot.model_copy(update={"messages": messages})

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
    not_before: datetime | None = None,
) -> tuple[tuple[PDDWorkspaceMessage, ...], tuple[PDDWorkspaceMessage, ...]]:
    new_messages = tuple(
        message
        for message in messages
        if message.sequence > after_sequence
        and (not_before is None or message.timestamp >= not_before)
    )
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
        recovery_sink: Callable[[], None] | None = None,
        session_event_sink: Callable[[str], None] | None = None,
        maximum_session_seconds: float = 30 * 60,
        warning_seconds: float = 25 * 60,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if maximum_session_seconds <= 0:
            raise ValueError("PDD Observer maximum session must be positive")
        if warning_seconds < 0 or warning_seconds >= maximum_session_seconds:
            raise ValueError("PDD Observer warning must precede the session limit")
        self._observer = observer
        self._interval = max(0.25, min(interval_seconds, 10.0))
        self._error_sink = error_sink or (lambda _code: None)
        self._recovery_sink = recovery_sink or (lambda: None)
        self._session_event_sink = session_event_sink or (lambda _code: None)
        self._maximum_session_seconds = maximum_session_seconds
        self._warning_seconds = warning_seconds
        self._monotonic = monotonic
        self._stop = Event()
        self._thread: Thread | None = None
        self._session_started_at: float | None = None
        self._warning_emitted = False
        self._stop_reason: str | None = None
        self._transient_error_active = False

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    @property
    def stop_reason(self) -> str | None:
        return self._stop_reason

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._session_started_at = self._monotonic()
        self._warning_emitted = False
        self._stop_reason = None
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
            session_event = self._session_event(self._monotonic())
            if session_event == "PDD_OBSERVER_SESSION_LIMIT_REACHED":
                self._stop_reason = session_event
                self._session_event_sink(session_event)
                self._stop.set()
                break
            if session_event == "PDD_OBSERVER_SESSION_WARNING":
                self._session_event_sink(session_event)
            try:
                self._observer.scan_once()
                if self._transient_error_active:
                    self._recovery_sink()
                    self._transient_error_active = False
            except PDDObserverFatalError as exc:
                code = f"PDD_OBSERVER_FATAL_{type(exc).__name__.upper()}"[:120]
                self._error_sink(code)
                self._stop.set()
                break
            except Exception as exc:
                code = f"PDD_OBSERVER_{type(exc).__name__.upper()}"[:120]
                self._error_sink(code)
                self._transient_error_active = True
            self._stop.wait(self._interval)

    def _session_event(self, now: float) -> str | None:
        started = self._session_started_at
        if started is None:
            return None
        elapsed = max(0.0, now - started)
        if elapsed >= self._maximum_session_seconds:
            return "PDD_OBSERVER_SESSION_LIMIT_REACHED"
        if elapsed >= self._warning_seconds and not self._warning_emitted:
            self._warning_emitted = True
            return "PDD_OBSERVER_SESSION_WARNING"
        return None


__all__ = [
    "ObservationOrigin",
    "PDDConversationNotActive",
    "PDDConversationSummary",
    "PDDMessageObserver",
    "PDDObserverError",
    "PDDObserverFatalError",
    "PDDObserverRunner",
    "PDDObserverScanResult",
    "PDDReadOnlyConversationDriver",
]
