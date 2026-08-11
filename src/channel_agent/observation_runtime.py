from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable, Protocol

from .assistant_events import AssistantEventPoller
from .client import ChannelEngineClient
from .control_v2 import AgentObservationSubmission
from .edge_spool import DurableEdgeSpool, EdgeObservation
from .observation_stages import ObservationStage
from .pdd_observer import PDDObserverRunner


class ObservationRuntimeError(RuntimeError):
    """Fail-closed error raised by the packaged OBSERVE_ONLY runtime."""


class ObservationForwardingRuntime(Protocol):
    def __call__(self, observation: EdgeObservation) -> object: ...

    def recover_pending(self) -> int: ...


class AssistantEventRuntime(Protocol):
    def start(self) -> None: ...

    def stop(self, timeout: float = 5.0) -> None: ...


class NoopAssistantEventRuntime:
    """Lower observation stages have no Host assistant-feed dependency."""

    def start(self) -> None:
        return None

    def stop(self, timeout: float = 5.0) -> None:
        del timeout


class PersistOnlyObservationForwarder:
    """MESSAGE_CAPTURE stage: durable local capture with zero Host requests."""

    def __init__(self, spool: DurableEdgeSpool) -> None:
        self._spool = spool

    def __call__(self, observation: EdgeObservation) -> bool:
        return self._spool.persist(observation)

    def recover_pending(self) -> int:
        # Pending rows intentionally remain unacknowledged until HOST_INGEST.
        return 0


class PersistAckObservationForwarder:
    """Persist locally, submit to Host, then advance the conversation cursor.

    The ordering in this class is intentional.  A crash before Host ACK leaves
    an encrypted pending row that is safe to redeliver; no local cursor can move
    before the Host transaction is known to have committed.
    """

    def __init__(self, client: ChannelEngineClient, spool: DurableEdgeSpool) -> None:
        self._client = client
        self._spool = spool
        self._lock = RLock()

    def __call__(self, observation: EdgeObservation) -> object:
        with self._lock:
            self._spool.persist(observation)
            return self._submit_and_ack(observation)

    def recover_pending(self) -> int:
        recovered = 0
        with self._lock:
            self._spool.purge_expired()
            for observation in self._spool.pending():
                self._submit_and_ack(observation)
                recovered += 1
        return recovered

    def _submit_and_ack(self, observation: EdgeObservation) -> object:
        if observation.source_cursor is None:
            raise ObservationRuntimeError(
                "PDD observation does not contain a source cursor"
            )
        submission = AgentObservationSubmission(
            observation_id=observation.observation_id,
            agent_id=observation.agent_id,
            device_id=observation.device_id,
            store_id=observation.store_id,
            conversation_id=observation.conversation_id,
            external_message_id=observation.external_message_id,
            source_cursor=observation.source_cursor,
            source_sequence=observation.source_sequence,
            payload_digest=observation.payload_digest,
            payload=observation.payload,
            captured_at=observation.captured_at,
        )
        acknowledgement = self._client.submit_observation(submission)
        if acknowledgement.observation_id != observation.observation_id:
            raise ObservationRuntimeError("Host acknowledged a different observation")
        if acknowledgement.acknowledged_cursor != observation.source_cursor:
            raise ObservationRuntimeError("Host acknowledged a different source cursor")
        self._spool.acknowledge(
            observation_id=observation.observation_id,
            payload_digest=observation.payload_digest,
            cursor=acknowledgement.acknowledged_cursor,
        )
        return acknowledgement


@dataclass(slots=True)
class ObserveOnlyRuntimeComponent:
    """Lifecycle composition containing no execution or transport dependency."""

    forwarder: ObservationForwardingRuntime
    observer: PDDObserverRunner
    assistant_events: AssistantEventRuntime
    stage: ObservationStage = ObservationStage.AI_SUGGESTIONS
    error_sink: Callable[[str], None] = lambda _code: None
    close_resources: Callable[[], None] = lambda: None
    _started: bool = False
    _observing: bool = False

    def start(self, *, page_ready: bool) -> None:
        if self._started:
            self.set_page_ready(page_ready)
            return
        if self.stage.allows(ObservationStage.HOST_INGEST):
            try:
                self.forwarder.recover_pending()
            except Exception as exc:
                self.error_sink(
                    ("OBSERVATION_RECOVERY_" + type(exc).__name__.upper())[:120]
                )
        if self.stage.allows(ObservationStage.ASSISTANT_FEED):
            self.assistant_events.start()
        self._started = True
        self.set_page_ready(page_ready)

    def set_page_ready(self, ready: bool) -> None:
        if not self._started:
            return
        if (
            ready
            and self.stage.allows(ObservationStage.CONVERSATION_LIST)
            and not self._observing
        ):
            self.observer.start()
            self._observing = True
        elif not ready and self._observing:
            self.observer.stop()
            self._observing = False

    def stop(self) -> None:
        self.observer.stop()
        self._observing = False
        self.assistant_events.stop()
        self._started = False

    def close(self) -> None:
        self.stop()
        self.close_resources()

    @property
    def observing(self) -> bool:
        return self._observing and self.observer.running


__all__ = [
    "ObservationRuntimeError",
    "ObserveOnlyRuntimeComponent",
    "NoopAssistantEventRuntime",
    "PersistOnlyObservationForwarder",
    "PersistAckObservationForwarder",
]
