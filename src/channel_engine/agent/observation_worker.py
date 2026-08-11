from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from typing import Callable, Literal

from channel_engine.customer_assistant import CustomerAssistantRuntime
from channel_engine.customer_assistant.models import ConversationTurn
from channel_engine.pdd_adapter import PDDPrivacyFilteredMessage
from channel_agent.control_v2 import AgentAssistantSnapshot
from channel_agent.observation_stages import ObservationStage

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
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if observer_mode != "OBSERVE_ONLY":
            raise AgentObservationWorkerError(
                "controlled send requires a separate safety-gated release"
            )
        self._store = store
        self._assistant = assistant
        self._stage = stage
        self._clock = clock

    def run_once(self, *, limit: int = 100) -> AgentObservationWorkerResult:
        self._store.purge_expired()
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
                if self._assistant is not None:
                    self._assistant.ingest_redacted(filtered)
                self._store.mark_observation_forwarded(submission.observation_id)
                ingested += 1
            except Exception as exc:
                rejected += 1
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
            self._store.persist_assistant_snapshot(
                AgentAssistantSnapshot(
                    agent_id=scope[0],
                    device_id=scope[1],
                    store_id=package.store_id,
                    conversation_id=package.conversation_id,
                    revision=1,
                    status=package.state,
                    turn_id=package.turn_id,
                    decision_id=package.decision_id,
                    request_id=package.request_id,
                    customer_reference=package.customer_reference,
                    current_question=package.customer_question,
                    action=package.action,
                    reply_content=package.reply_content,
                    risk_level=package.risk_level.value,
                    citations=tuple(
                        citation.model_dump(mode="json")
                        for citation in package.citations
                    ),
                    updated_at=now,
                    expires_at=now + timedelta(minutes=30),
                )
            )
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
            self._store.append_assistant_event(
                event_id=_event_id("WAITING_APPROVAL", package.decision_id),
                event_type="WAITING_APPROVAL",
                status=(
                    "WAITING_APPROVAL"
                    if package.state == "WAITING_APPROVAL"
                    else "MANUAL_INTERVENTION"
                ),
                metadata={
                    "manual_approval_required": True,
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


__all__ = [
    "AgentObservationWorker",
    "AgentObservationWorkerError",
    "AgentObservationWorkerResult",
    "AgentObservationWorkerRunner",
]
