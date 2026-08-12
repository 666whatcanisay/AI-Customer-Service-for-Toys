from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Literal

from channel_agent.observation_stages import ObservationStage
from channel_engine.customer_assistant import (
    CustomerAssistantRuntime,
    OfflineReplyControlStore,
    PipelineStage,
    PipelineStageState,
)
from channel_engine.customer_assistant.buffer import ConversationBufferError
from channel_engine.customer_assistant.models import (
    BufferedMessageDisposition,
    ConversationTurn,
)
from channel_engine.pdd_adapter import PDDPrivacyFilteredMessage

from .assistant_projection import build_assistant_snapshot
from .control_store import AgentControlStore
from .observation_pipeline import PDDObservationPayload


class AgentObservationWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AgentObservationWorkerResult:
    observations_ingested: int
    observations_rejected: int
    replies_generated: int


class AgentObservationWorker:
    """Consumes the committed Agent inbox and drives the authoritative Host buffer.

    The worker intentionally owns no platform transport.  In ``OBSERVE_ONLY`` it
    can create CustomerContext and AI suggestions, but it cannot create an
    Execution, invoke PDD, or write a send Receipt.
    """

    def __init__(
        self,
        store: AgentControlStore,
        assistant: CustomerAssistantRuntime | None,
        *,
        observer_mode: Literal["OBSERVE_ONLY"] = "OBSERVE_ONLY",
        stage: ObservationStage = ObservationStage.AI_SUGGESTIONS,
        offline_control: OfflineReplyControlStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if observer_mode != "OBSERVE_ONLY":
            raise AgentObservationWorkerError(
                "controlled send requires a separate safety-gated release"
            )
        self._store = store
        self._assistant = assistant
        self._stage = stage
        self._offline_control = offline_control
        self._clock = clock
        self._fault_injector = fault_injector or (lambda _checkpoint: None)

    def run_once(self, *, limit: int = 100) -> AgentObservationWorkerResult:
        self._store.purge_expired()
        if self._assistant is not None:
            purge_content = getattr(self._assistant, "purge_expired_content", None)
            if callable(purge_content):
                purge_content()
        if self._offline_control is not None:
            self._offline_control.purge_expired_content()
        ingested = rejected = generated = 0
        for submission in self._store.pending_observations(limit=limit):
            try:
                payload = PDDObservationPayload.model_validate_json(
                    json.dumps(
                        submission.payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                if (
                    payload.store_id != submission.store_id
                    or payload.conversation_id != submission.conversation_id
                    or payload.external_message_id != submission.external_message_id
                ):
                    raise ValueError("observation envelope scope mismatch")
                filtered = PDDPrivacyFilteredMessage(
                    store_id=payload.store_id,
                    conversation_id=payload.conversation_id,
                    external_message_id=payload.external_message_id,
                    content=payload.content,
                    timestamp=payload.timestamp,
                    captured_at=submission.captured_at,
                    redacted_content_digest=hashlib.sha256(
                        payload.content.encode("utf-8")
                    ).hexdigest(),
                )
                if self._assistant is None:
                    raise AgentObservationWorkerError(
                        "HOST_INGEST requires a durable assistant buffer"
                    )
                disposition = self._assistant.ingest_redacted(filtered)
                trace_id = _trace_id(payload, submission.observation_id)
                if self._offline_control is not None:
                    self._offline_control.record_trace(
                        trace_id,
                        PipelineStage.HOST_PERSIST,
                        PipelineStageState.SUCCEEDED,
                        "HOST_ACK_COMMITTED",
                    )
                    self._offline_control.register_observation(
                        observation_id=submission.observation_id,
                        store_id=payload.store_id,
                        conversation_id=payload.conversation_id,
                        trace_id=trace_id,
                    )
                    self._offline_control.record_trace(
                        trace_id,
                        PipelineStage.BUFFERING,
                        PipelineStageState.SUCCEEDED,
                        (
                            "BUFFER_DUPLICATE"
                            if disposition is BufferedMessageDisposition.DUPLICATE
                            else "BUFFER_COMMITTED"
                        ),
                    )
                self._store.mark_observation_forwarded(submission.observation_id)
                ingested += 1
            except Exception as exc:
                rejected += 1
                permanent = _permanent_observation_error(exc)
                if self._offline_control is not None:
                    self._offline_control.record_trace(
                        _submission_trace_id(submission.payload, submission.observation_id),
                        PipelineStage.HOST_PERSIST,
                        (
                            PipelineStageState.FAILED
                            if permanent
                            else PipelineStageState.RUNNING
                        ),
                        (
                            f"HOST_REJECTED_{_error_code(exc)}"
                            if permanent
                            else f"HOST_RETRY_{_error_code(exc)}"
                        ),
                    )
                if not permanent:
                    # Buffer/database/service outages remain pending.  Host ACK
                    # durability is preserved and the worker retries after recovery.
                    continue
                self._store.append_assistant_event(
                    event_id=_event_id("OBSERVATION_FAILED", submission.observation_id),
                    event_type="OBSERVATION_FAILED",
                    agent_id=submission.agent_id,
                    device_id=submission.device_id,
                    store_id=submission.store_id,
                    conversation_id=submission.conversation_id,
                    status="MANUAL_REVIEW_REQUIRED",
                    metadata={
                        "observation_id": submission.observation_id,
                        "error_code": _error_code(exc),
                        "contains_customer_content": False,
                    },
                )
                # Invalid input cannot become valid by retrying.  It is retained
                # durably for audit, but removed from the automatic AI queue.
                self._store.mark_observation_forwarded(submission.observation_id)

        if not self._stage.allows(ObservationStage.AI_SUGGESTIONS):
            return AgentObservationWorkerResult(ingested, rejected, generated)
        if self._assistant is None:
            raise AgentObservationWorkerError(
                "AI_SUGGESTIONS stage requires an assistant runtime"
            )

        while True:
            claimed: list[ConversationTurn] = []

            def on_claim(turn: ConversationTurn) -> None:
                claimed.append(turn)
                scope = self._scope(turn.store_id, turn.conversation_id)
                if scope is None:
                    raise AgentObservationWorkerError("assistant event route is unavailable")
                agent_id, device_id = scope
                trace_id = self._trace_id(turn.store_id, turn.conversation_id)
                if self._offline_control is not None:
                    self._offline_control.record_trace(
                        trace_id,
                        PipelineStage.CUSTOMER_CONTEXT,
                        PipelineStageState.RUNNING,
                        "CONTEXT_ASSEMBLY_STARTED",
                    )
                    self._offline_control.record_trace(
                        trace_id,
                        PipelineStage.AI_GENERATING,
                        PipelineStageState.RUNNING,
                        "AI_REQUEST_STARTED",
                    )
                metadata = {
                    "message_count": len(turn.messages),
                    "contains_customer_content": False,
                }
                self._store.append_assistant_event(
                    event_id=_event_id("QUESTION_GROUP_FORMED", turn.turn_id),
                    event_type="QUESTION_GROUP_FORMED",
                    agent_id=agent_id,
                    device_id=device_id,
                    store_id=turn.store_id,
                    conversation_id=turn.conversation_id,
                    turn_id=turn.turn_id,
                    status="READY",
                    metadata=metadata,
                )
                self._store.append_assistant_event(
                    event_id=_event_id("AI_GENERATING", turn.turn_id),
                    event_type="AI_GENERATING",
                    agent_id=agent_id,
                    device_id=device_id,
                    store_id=turn.store_id,
                    conversation_id=turn.conversation_id,
                    turn_id=turn.turn_id,
                    status="RUNNING",
                    metadata={"contains_customer_content": False},
                )

            try:
                package = self._assistant.generate_ready_reply(
                    now=self._clock(),
                    on_turn_claimed=on_claim,
                )
            except Exception as exc:
                if claimed:
                    turn = claimed[0]
                    scope = self._scope(turn.store_id, turn.conversation_id)
                    trace_id = self._trace_id(turn.store_id, turn.conversation_id)
                    if self._offline_control is not None:
                        self._offline_control.record_trace(
                            trace_id,
                            PipelineStage.AI_GENERATING,
                            PipelineStageState.FAILED,
                            f"AI_FAILED_{_error_code(exc)}",
                        )
                    if scope is not None:
                        self._store.append_assistant_event(
                            event_id=_event_id("OBSERVATION_FAILED", turn.turn_id),
                            event_type="OBSERVATION_FAILED",
                            agent_id=scope[0],
                            device_id=scope[1],
                            store_id=turn.store_id,
                            conversation_id=turn.conversation_id,
                            turn_id=turn.turn_id,
                            status="AI_FAILED",
                            metadata={
                                "error_code": _error_code(exc),
                                "contains_customer_content": False,
                            },
                        )
                break
            if package is None:
                break
            self._fault_injector("AFTER_BUFFER_REPLY_COMMIT")
            scope = self._scope(package.store_id, package.conversation_id)
            if scope is None:
                raise AgentObservationWorkerError("assistant event route is unavailable")
            common = dict(
                agent_id=scope[0],
                device_id=scope[1],
                store_id=package.store_id,
                conversation_id=package.conversation_id,
                turn_id=package.turn_id,
                decision_id=package.decision_id,
            )
            now = self._clock().astimezone(UTC)
            trace_id = self._trace_id(package.store_id, package.conversation_id)
            control_outcome = None
            if self._offline_control is not None:
                stored = self._assistant.stored_reply(package.decision_id)
                if stored is None:
                    raise AgentObservationWorkerError(
                        "durable reply context is unavailable for quality gate"
                    )
                context, _stored_package = stored
                self._offline_control.record_trace(
                    trace_id,
                    PipelineStage.CUSTOMER_CONTEXT,
                    PipelineStageState.SUCCEEDED,
                    "CONTEXT_ASSEMBLED",
                )
                self._offline_control.record_trace(
                    trace_id,
                    PipelineStage.AI_GENERATING,
                    PipelineStageState.SUCCEEDED,
                    "AI_REPLY_CREATED",
                )
                control_outcome = self._offline_control.register_reply(
                    context,
                    package,
                    trace_id=trace_id,
                )
            self._fault_injector("AFTER_CONTROL_DECISION_COMMIT")
            status = package.state
            if control_outcome is not None:
                if (
                    control_outcome.preparation is not None
                    and control_outcome.preparation.state.value == "READY"
                ):
                    status = "EXECUTION_PREPARED"
                elif control_outcome.quality.status.value == "BLOCKED":
                    status = "MANUAL_INTERVENTION"
            self._store.persist_assistant_snapshot(
                build_assistant_snapshot(
                    package,
                    control_outcome,
                    agent_id=scope[0],
                    device_id=scope[1],
                    trace_id=trace_id,
                    now=now,
                )
            )
            self._fault_injector("AFTER_ASSISTANT_SNAPSHOT_COMMIT")
            self._store.append_assistant_event(
                event_id=_event_id("AI_SUGGESTION_READY", package.decision_id),
                event_type="AI_SUGGESTION_READY",
                status="READY",
                metadata={
                    "action": package.action,
                    "risk_level": package.risk_level.value,
                    "contains_customer_content": False,
                },
                **common,
            )
            if control_outcome is not None:
                self._store.append_assistant_event(
                    event_id=_event_id("QUALITY_GATE", package.decision_id),
                    event_type="QUALITY_GATE",
                    status=control_outcome.quality.status.value,
                    metadata={
                        "trace_id": trace_id,
                        "reason_code": control_outcome.quality.reason_codes[0],
                        "contains_customer_content": False,
                    },
                    **common,
                )
                if control_outcome.preparation is not None:
                    self._store.append_assistant_event(
                        event_id=_event_id("EXECUTION_PREPARED", package.decision_id),
                        event_type="EXECUTION_PREPARED",
                        status="EXECUTION_PREPARED",
                        metadata={
                            "trace_id": trace_id,
                            "preparation_id": control_outcome.preparation.preparation_id,
                            "authorization_kind": control_outcome.preparation.authorization_kind.value,
                            "real_send_enabled": False,
                            "contains_customer_content": False,
                        },
                        **common,
                    )
            self._store.append_assistant_event(
                event_id=_event_id("WAITING_APPROVAL", package.decision_id),
                event_type="WAITING_APPROVAL",
                status=(
                    status
                ),
                metadata={
                    "manual_approval_required": status != "EXECUTION_PREPARED",
                    "execution_prepared": status == "EXECUTION_PREPARED",
                    "execution_created": 0,
                    "transport_calls": 0,
                    "send_receipts": 0,
                    "contains_customer_content": False,
                },
                **common,
            )
            generated += 1

        return AgentObservationWorkerResult(ingested, rejected, generated)

    def _scope(self, store_id: str, conversation_id: str) -> tuple[str, str] | None:
        return self._store.assistant_scope_for_conversation(store_id, conversation_id)

    def _trace_id(self, store_id: str, conversation_id: str) -> str:
        raw = self._store.latest_observation_payload(store_id, conversation_id) or {}
        value = raw.get("trace_id")
        if isinstance(value, str) and value.startswith("trace:"):
            return value
        return _derived_trace_id(store_id, conversation_id)


class AgentObservationWorkerRunner:
    """Bounded background lifecycle for the durable Host inbox consumer."""

    def __init__(
        self,
        worker: AgentObservationWorker,
        *,
        interval_seconds: float = 0.5,
        error_sink: Callable[[str], None] | None = None,
    ) -> None:
        self._worker = worker
        self._interval = max(0.1, min(interval_seconds, 10.0))
        self._error_sink = error_sink or (lambda _code: None)
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread is not None and self._thread.is_alive())

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(
                target=self._run,
                name="channel-agent-observation-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, timeout))
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._worker.run_once()
            except Exception as exc:
                code = f"OBSERVATION_WORKER_{type(exc).__name__.upper()}"[:120]
                self._error_sink(code)
            self._stop.wait(self._interval)


def _event_id(event_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{event_type}:{source_id}".encode("utf-8")).hexdigest()
    return f"assistant-event:{digest}"


def _error_code(exc: Exception) -> str:
    value = "".join(character if character.isalnum() else "_" for character in type(exc).__name__)
    return (value.upper() or "OBSERVATION_WORKER_FAILURE")[:80]


def _trace_id(payload: PDDObservationPayload, observation_id: str) -> str:
    return payload.trace_id or _derived_trace_id(
        payload.store_id, payload.conversation_id, observation_id
    )


def _derived_trace_id(*parts: str) -> str:
    return "trace:" + hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _permanent_observation_error(exc: Exception) -> bool:
    from pydantic import ValidationError

    if isinstance(exc, ConversationBufferError):
        return exc.error_code in {
            "CUSTOMER_MESSAGE_IDEMPOTENCY_CONFLICT",
            "CUSTOMER_MESSAGE_NOT_PRIVACY_FILTERED",
        }
    return isinstance(exc, (ValidationError, ValueError)) and not isinstance(
        exc, AgentObservationWorkerError
    )


def _submission_trace_id(payload: object, observation_id: str) -> str:
    if isinstance(payload, dict):
        value = payload.get("trace_id")
        if isinstance(value, str) and value.startswith("trace:"):
            return value
    return _derived_trace_id(observation_id)


__all__ = [
    "AgentObservationWorker",
    "AgentObservationWorkerError",
    "AgentObservationWorkerResult",
    "AgentObservationWorkerRunner",
]
