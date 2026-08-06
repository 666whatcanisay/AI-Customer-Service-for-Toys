from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.browser import (
    BrowserLoginState,
    BrowserObservationBatch,
    BrowserPageObserver,
    BrowserSession,
    BrowserSessionState,
)
from channel_engine.channel import ChannelMessageV1, NormalizedMessage
from channel_engine.channel.protocol import store_scoped_conversation_ref
from channel_engine.conversation import ConversationService, IntakeResult
from channel_engine.models import DecisionState
from channel_engine.models.entities import utc_now
from channel_engine.session import (
    InboundEnvelope,
    MessageDelivery,
    MessageReliabilityService,
    PersistedMessage,
)
from channel_engine.storage import SqlAlchemyUnitOfWork


PDD_MESSAGE_OBSERVATION_VERSION = "1.0"


class PDDMessageObservationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    observation_contract_version: Literal["1.0"] = PDD_MESSAGE_OBSERVATION_VERSION


class PDDMessageObservationError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDMessageObservationSafetyViolation(PDDMessageObservationError):
    pass


class PDDMessageReaderState(StrEnum):
    CONNECTED = "CONNECTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    EXPIRED = "EXPIRED"
    DEGRADED = "DEGRADED"


class PDDPrivacyCategory(StrEnum):
    NAME = "NAME"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    PAYMENT = "PAYMENT"


class PDDObservationDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"


class PDDCapturedMessage(PDDMessageObservationModel):
    """Ephemeral capture object. It must never be written to persistence or logs."""

    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255, repr=False)
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        repr=False,
    )
    timestamp: AwareDatetime
    captured_at: AwareDatetime


class PDDPrivacyFilteredMessage(PDDMessageObservationModel):
    """Only this redacted shape may cross the persistence/Gateway boundary."""

    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["customer"] = "customer"
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        repr=False,
    )
    timestamp: AwareDatetime
    captured_at: AwareDatetime
    redaction_categories: tuple[PDDPrivacyCategory, ...] = ()
    redaction_count: int = Field(default=0, ge=0)
    redacted_content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class PDDMessageReaderHealth(PDDMessageObservationModel):
    state: PDDMessageReaderState
    read_only: Literal[True] = True
    browser_write_operations: Literal[0] = 0
    checked_at: AwareDatetime


class PDDMessageObservationPolicy(PDDMessageObservationModel):
    delay_warning_seconds: float = Field(default=30.0, ge=0)
    maximum_message_age_seconds: float = Field(default=900.0, gt=0)
    maximum_future_skew_seconds: float = Field(default=30.0, ge=0)

    @model_validator(mode="after")
    def validate_delay_thresholds(self) -> PDDMessageObservationPolicy:
        if self.maximum_message_age_seconds < self.delay_warning_seconds:
            raise ValueError("maximum message age must cover the delay warning")
        return self


class PDDMessageObservationSafetySnapshot(PDDMessageObservationModel):
    approval_created: Literal[0] = 0
    execution_created: Literal[0] = 0
    receipt_created: Literal[0] = 0
    send_operations: Literal[0] = 0
    browser_write_operations: Literal[0] = 0
    automatic_login_performed: Literal[False] = False
    auto_reply_enabled: Literal[False] = False


class PDDMessageObservationEvidence(PDDMessageObservationModel):
    message_id: str = Field(min_length=1, max_length=128)
    external_message_id: str = Field(min_length=1, max_length=255)
    conversation_id: str = Field(min_length=1, max_length=128)
    external_conversation_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    decision_state: Literal["WAITING_APPROVAL"] = "WAITING_APPROVAL"
    requires_approval: Literal[True] = True
    disposition: PDDObservationDisposition
    delayed: bool
    latency_seconds: float = Field(ge=0)
    redaction_categories: tuple[PDDPrivacyCategory, ...] = ()
    redaction_count: int = Field(default=0, ge=0)
    observed_at: AwareDatetime
    safety: PDDMessageObservationSafetySnapshot


class PDDCapturedMessageBatch(PDDMessageObservationModel):
    """Ephemeral browser batch; acknowledgement is intentionally separate."""

    browser_batch: BrowserObservationBatch = Field(repr=False)
    messages: tuple[PDDCapturedMessage, ...] = Field(repr=False)

    @model_validator(mode="after")
    def validate_alignment(self) -> PDDCapturedMessageBatch:
        if len(self.browser_batch.messages) != len(self.messages):
            raise ValueError("browser and PDD capture batches must remain aligned")
        return self


class PDDDurableIngestResult(PDDMessageObservationModel):
    batch_id: str = Field(min_length=1, max_length=128)
    instance_id: str = Field(min_length=1, max_length=128)
    persisted_message_ids: tuple[str, ...]
    duplicate_message_ids: tuple[str, ...]
    transaction_committed: Literal[True] = True
    browser_cursor_acknowledged: Literal[True] = True
    persistence_preceded_cursor_ack: Literal[True] = True
    observed_at: AwareDatetime


@runtime_checkable
class PDDMessageReader(Protocol):
    """Capture-only PDD boundary. There is intentionally no send/execute method."""

    @property
    def store_id(self) -> str: ...

    @property
    def read_only(self) -> bool: ...

    @property
    def browser_write_operations(self) -> int: ...

    def capture(self) -> tuple[PDDCapturedMessage, ...]: ...

    def health_check(self) -> PDDMessageReaderHealth: ...


@runtime_checkable
class PDDTransactionalMessageReader(PDDMessageReader, Protocol):
    """Two-phase receive boundary: stage, durable persist, then acknowledge."""

    def stage_capture(self) -> PDDCapturedMessageBatch: ...

    def acknowledge(self, batch: PDDCapturedMessageBatch) -> None: ...


class BrowserPDDMessageReader:
    """Adapts the verified BrowserPageObserver into a capture-only PDD reader."""

    read_only = True

    def __init__(
        self,
        observer: BrowserPageObserver,
        session_provider: Callable[[], BrowserSession],
        *,
        store_id: str,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not store_id.strip():
            raise ValueError("PDD message reader requires a store binding")
        self._observer = observer
        self._session_provider = session_provider
        self._store_id = store_id
        self._clock = clock
        self._browser_write_operations = 0

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def browser_write_operations(self) -> int:
        return self._browser_write_operations

    def stage_capture(self) -> PDDCapturedMessageBatch:
        self._require_active_authenticated_session()
        browser_batch = self._observer.stage_capture()
        health = self._observer.heartbeat()
        self._browser_write_operations = health.page_write_operations
        if not health.healthy:
            raise PDDMessageObservationError(
                "PDD browser observer is unhealthy",
                error_code=(
                    health.failure_code or "PDD_MESSAGE_READER_OBSERVER_UNHEALTHY"
                ),
            )
        self._assert_read_only()
        captured_at = self._clock()
        messages = tuple(
            PDDCapturedMessage(
                store_id=self._store_id,
                conversation_id=message.conversation_id,
                external_message_id=message.external_message_id,
                sender=message.sender,
                content=message.content,
                timestamp=message.timestamp,
                captured_at=captured_at,
            )
            for message in browser_batch.messages
        )
        return PDDCapturedMessageBatch(
            browser_batch=browser_batch,
            messages=messages,
        )

    def acknowledge(self, batch: PDDCapturedMessageBatch) -> None:
        self._observer.commit_batch(batch.browser_batch)
        self._assert_read_only()

    def capture(self) -> tuple[PDDCapturedMessage, ...]:
        """Compatibility path for callers that do not own a durable inbox."""

        batch = self.stage_capture()
        self.acknowledge(batch)
        return batch.messages

    def health_check(self) -> PDDMessageReaderHealth:
        session = self._session_provider()
        state = self._project_state(session)
        if state is PDDMessageReaderState.CONNECTED:
            heartbeat = self._observer.heartbeat()
            self._browser_write_operations = heartbeat.page_write_operations
            if not heartbeat.healthy:
                state = PDDMessageReaderState.DEGRADED
        self._assert_read_only()
        return PDDMessageReaderHealth(
            state=state,
            checked_at=self._clock(),
        )

    def _require_active_authenticated_session(self) -> BrowserSession:
        session = self._session_provider()
        state = self._project_state(session)
        if state is PDDMessageReaderState.EXPIRED:
            raise PDDMessageObservationError(
                "PDD browser session expired",
                error_code="PDD_MESSAGE_READER_SESSION_EXPIRED",
            )
        if state is not PDDMessageReaderState.CONNECTED:
            raise PDDMessageObservationError(
                "PDD browser session is not ready for observation",
                error_code="PDD_MESSAGE_READER_SESSION_NOT_READY",
            )
        return session

    @staticmethod
    def _project_state(session: BrowserSession) -> PDDMessageReaderState:
        if (
            session.state is BrowserSessionState.ACTIVE
            and session.login_state is BrowserLoginState.AUTHENTICATED
            and session.page_context is not None
        ):
            return PDDMessageReaderState.CONNECTED
        if (
            session.state is BrowserSessionState.EXPIRED
            or session.login_state is BrowserLoginState.EXPIRED
        ):
            return PDDMessageReaderState.EXPIRED
        if (
            session.state is BrowserSessionState.LOGIN_REQUIRED
            or session.login_state is BrowserLoginState.REQUIRED
        ):
            return PDDMessageReaderState.AUTH_REQUIRED
        return PDDMessageReaderState.DEGRADED

    def _assert_read_only(self) -> None:
        if not self.read_only or self._browser_write_operations != 0:
            raise PDDMessageObservationSafetyViolation(
                "PDD message reader performed a browser write",
                error_code="PDD_MESSAGE_READER_WRITE_DETECTED",
            )


class FakePDDMessageReader:
    """Synthetic capture-only reader used to test the production boundary."""

    read_only = True

    def __init__(
        self,
        *,
        store_id: str,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self._store_id = store_id
        self._clock = clock
        self._state = PDDMessageReaderState.CONNECTED
        self._queue: deque[PDDCapturedMessage] = deque()
        self._browser_write_operations = 0

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def browser_write_operations(self) -> int:
        return self._browser_write_operations

    def enqueue(self, *messages: PDDCapturedMessage) -> None:
        self._queue.extend(messages)

    def set_state(self, state: PDDMessageReaderState) -> None:
        self._state = state

    def capture(self) -> tuple[PDDCapturedMessage, ...]:
        if self._state is PDDMessageReaderState.EXPIRED:
            raise PDDMessageObservationError(
                "PDD browser session expired",
                error_code="PDD_MESSAGE_READER_SESSION_EXPIRED",
            )
        if self._state is not PDDMessageReaderState.CONNECTED:
            raise PDDMessageObservationError(
                "PDD message reader is not connected",
                error_code="PDD_MESSAGE_READER_SESSION_NOT_READY",
            )
        items = tuple(self._queue)
        self._queue.clear()
        return items

    def health_check(self) -> PDDMessageReaderHealth:
        return PDDMessageReaderHealth(
            state=self._state,
            checked_at=self._clock(),
        )


class PDDPrivacyFilter:
    """Redacts supported direct identifiers before persistence or Gateway use."""

    _patterns: tuple[tuple[PDDPrivacyCategory, re.Pattern[str], str], ...] = (
        (
            PDDPrivacyCategory.NAME,
            re.compile(
                r"(?:(?:我叫|姓名|收件人)\s*[:：]?\s*)"
                r"(?:[\u4e00-\u9fff·]{2,8}|[A-Za-z][A-Za-z .'-]{1,40})",
                re.IGNORECASE,
            ),
            "[姓名已脱敏]",
        ),
        (
            PDDPrivacyCategory.NAME,
            re.compile(
                r"\bmy\s+name\s+is\s+[A-Za-z][A-Za-z .'-]{1,40}",
                re.IGNORECASE,
            ),
            "[姓名已脱敏]",
        ),
        (
            PDDPrivacyCategory.PHONE,
            re.compile(r"(?<!\d)(?:\+?86[\s-]?)?1[3-9](?:[\s-]?\d){9}(?!\d)"),
            "[手机号已脱敏]",
        ),
        (
            PDDPrivacyCategory.PAYMENT,
            re.compile(r"(?<!\d)(?:\d[\s-]?){12,18}\d(?!\d)"),
            "[支付信息已脱敏]",
        ),
        (
            PDDPrivacyCategory.PAYMENT,
            re.compile(
                r"(?:银行卡号|卡号|支付账号|支付宝账号|微信支付账号|付款码)"
                r"\s*[:：]?\s*[A-Za-z0-9@._-]{4,64}",
                re.IGNORECASE,
            ),
            "[支付信息已脱敏]",
        ),
        (
            PDDPrivacyCategory.ADDRESS,
            re.compile(r"(?:收货地址|地址)\s*[:：]?\s*[^。；;\n]{2,160}"),
            "[地址已脱敏]",
        ),
    )

    def apply(self, message: PDDCapturedMessage) -> PDDPrivacyFilteredMessage:
        content = message.content
        categories: list[PDDPrivacyCategory] = []
        redaction_count = 0
        for category, pattern, replacement in self._patterns:
            content, count = pattern.subn(replacement, content)
            if count:
                redaction_count += count
                if category not in categories:
                    categories.append(category)
        content = content.strip()
        if not content:
            content = "[敏感内容已脱敏]"
        return PDDPrivacyFilteredMessage(
            store_id=message.store_id,
            conversation_id=message.conversation_id,
            external_message_id=message.external_message_id,
            content=content,
            timestamp=message.timestamp,
            captured_at=message.captured_at,
            redaction_categories=tuple(categories),
            redaction_count=redaction_count,
            redacted_content_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )


class PDDObservationMessageMapper:
    def __init__(self, *, store_id: str) -> None:
        if not store_id.strip():
            raise ValueError("PDD observation mapper requires a store binding")
        self._store_id = store_id

    def map(self, message: PDDPrivacyFilteredMessage) -> ChannelMessageV1:
        if message.store_id != self._store_id:
            raise PDDMessageObservationSafetyViolation(
                "captured PDD message belongs to another store",
                error_code="PDD_MESSAGE_STORE_MISMATCH",
            )
        return ChannelMessageV1(
            message_id=message.external_message_id,
            channel="pdd",
            store_id=message.store_id,
            conversation_id=message.conversation_id,
            sender="customer",
            content=message.content,
            timestamp=message.timestamp,
        )


class PDDMessageObservationRuntime:
    """Read-only PDD message pipeline that terminates at WAITING_APPROVAL."""

    def __init__(
        self,
        reader: PDDMessageReader,
        conversation: ConversationService,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        privacy_filter: PDDPrivacyFilter | None = None,
        mapper: PDDObservationMessageMapper | None = None,
        policy: PDDMessageObservationPolicy | None = None,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(reader, PDDMessageReader):
            raise TypeError("PDD message reader does not implement the capture contract")
        if not reader.read_only or reader.browser_write_operations != 0:
            raise ValueError("PDD message observation requires a zero-write reader")
        self._reader = reader
        self._conversation = conversation
        self._uow_factory = uow_factory
        self._privacy_filter = privacy_filter or PDDPrivacyFilter()
        self._mapper = mapper or PDDObservationMessageMapper(store_id=reader.store_id)
        self._policy = policy or PDDMessageObservationPolicy()
        self._clock = clock
        self._evidence: list[PDDMessageObservationEvidence] = []
        self._lock = RLock()

    def observe_once(self) -> tuple[PDDMessageObservationEvidence, ...]:
        with self._lock:
            self._assert_zero_side_effect_reader()
            captures = self._reader.capture()
            results: list[PDDMessageObservationEvidence] = []
            for captured in captures:
                latency, delayed = self._validate_message_age(captured)
                filtered = self._privacy_filter.apply(captured)
                mapped = self._mapper.map(filtered)
                evidence = self._decide(mapped, filtered, latency, delayed)
                self._evidence.append(evidence)
                results.append(evidence)
            self._assert_zero_side_effect_reader()
            return tuple(results)

    def evidence(self) -> tuple[PDDMessageObservationEvidence, ...]:
        with self._lock:
            return tuple(self._evidence)

    def safety_snapshot(self) -> PDDMessageObservationSafetySnapshot:
        self._assert_zero_side_effect_reader()
        return PDDMessageObservationSafetySnapshot()

    def _decide(
        self,
        mapped: ChannelMessageV1,
        filtered: PDDPrivacyFilteredMessage,
        latency: float,
        delayed: bool,
    ) -> PDDMessageObservationEvidence:
        duplicate = self._message_exists(mapped)
        intake: IntakeResult = self._conversation.receive(mapped.to_runtime_message())
        if (
            intake.decision_state is not DecisionState.WAITING_APPROVAL
            or not intake.requires_approval
        ):
            raise PDDMessageObservationSafetyViolation(
                "AI-CS Decision escaped WAITING_APPROVAL",
                error_code="PDD_MESSAGE_DECISION_NOT_WAITING_APPROVAL",
            )
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            approval = repo.get_approval_for_decision(intake.decision_id)
            execution = repo.get_execution_for_decision(intake.decision_id)
            receipt = (
                repo.get_receipt_for_execution(execution.execution_id)
                if execution is not None
                else None
            )
        if approval is not None or execution is not None or receipt is not None:
            raise PDDMessageObservationSafetyViolation(
                "message observation created approval, execution, or receipt",
                error_code="PDD_MESSAGE_EXECUTION_BOUNDARY_BREACHED",
            )
        return PDDMessageObservationEvidence(
            message_id=intake.message_id,
            external_message_id=mapped.message_id,
            conversation_id=intake.conversation_id,
            external_conversation_id=mapped.conversation_id,
            decision_id=intake.decision_id,
            trace_id=intake.message_id,
            disposition=(
                PDDObservationDisposition.DUPLICATE
                if duplicate
                else PDDObservationDisposition.ACCEPTED
            ),
            delayed=delayed,
            latency_seconds=latency,
            redaction_categories=filtered.redaction_categories,
            redaction_count=filtered.redaction_count,
            observed_at=self._clock(),
            safety=PDDMessageObservationSafetySnapshot(),
        )

    def _message_exists(self, message: ChannelMessageV1) -> bool:
        conversation_ref = store_scoped_conversation_ref(
            message.store_id,
            message.conversation_id,
        )
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            conversation = repo.find_conversation(message.channel, conversation_ref)
            if conversation is None:
                return False
            return (
                repo.find_message(conversation.conversation_id, message.message_id)
                is not None
            )

    def _validate_message_age(
        self, message: PDDCapturedMessage
    ) -> tuple[float, bool]:
        age = (message.captured_at - message.timestamp).total_seconds()
        if age < -self._policy.maximum_future_skew_seconds:
            raise PDDMessageObservationError(
                "PDD message timestamp is too far in the future",
                error_code="PDD_MESSAGE_TIMESTAMP_IN_FUTURE",
            )
        latency = max(age, 0.0)
        if latency > self._policy.maximum_message_age_seconds:
            raise PDDMessageObservationError(
                "PDD message exceeded the observation age limit",
                error_code="PDD_MESSAGE_STALE",
            )
        return latency, latency >= self._policy.delay_warning_seconds

    def _assert_zero_side_effect_reader(self) -> None:
        if not self._reader.read_only or self._reader.browser_write_operations != 0:
            raise PDDMessageObservationSafetyViolation(
                "PDD message reader crossed the write boundary",
                error_code="PDD_MESSAGE_READER_WRITE_DETECTED",
            )


class PDDDurableMessageObservationRuntime:
    """Crash-safe PDD inbox pipeline terminating at WAITING_APPROVAL.

    Ordering is fixed by construction:

    1. stage the browser capture without cursor mutation;
    2. redact and commit messages to the SQLite inbox;
    3. acknowledge the browser cursor;
    4. drain the durable inbox into Conversation / AI-CS Decision;
    5. acknowledge inbox delivery only after WAITING_APPROVAL is verified.
    """

    def __init__(
        self,
        reader: PDDTransactionalMessageReader,
        reliability: MessageReliabilityService,
        conversation: ConversationService,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        instance_id: str,
        privacy_filter: PDDPrivacyFilter | None = None,
        mapper: PDDObservationMessageMapper | None = None,
        policy: PDDMessageObservationPolicy | None = None,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(reader, PDDTransactionalMessageReader):
            raise TypeError("PDD reader must implement staged cursor acknowledgement")
        if not instance_id.strip():
            raise ValueError("durable PDD observation requires an instance id")
        if not reader.read_only or reader.browser_write_operations != 0:
            raise ValueError("durable PDD observation requires a zero-write reader")
        self._reader = reader
        self._reliability = reliability
        self._conversation = conversation
        self._uow_factory = uow_factory
        self._instance_id = instance_id
        self._privacy_filter = privacy_filter or PDDPrivacyFilter()
        self._mapper = mapper or PDDObservationMessageMapper(store_id=reader.store_id)
        self._policy = policy or PDDMessageObservationPolicy()
        self._clock = clock
        self._redaction_metadata: dict[
            str, tuple[tuple[PDDPrivacyCategory, ...], int]
        ] = {}
        self._lock = RLock()

    def ingest_once(
        self,
        *,
        after_transaction_commit: Callable[[], None] | None = None,
    ) -> PDDDurableIngestResult:
        """Commit redacted messages, then ACK the external browser cursor.

        ``after_transaction_commit`` is an explicit crash-injection seam used by
        recovery tests.  If it raises, the inbox remains durable and the browser
        cursor remains unchanged.
        """

        with self._lock:
            self._assert_zero_side_effect_reader()
            batch = self._reader.stage_capture()
            envelopes: list[InboundEnvelope] = []
            for index, (captured, identity) in enumerate(
                zip(batch.messages, batch.browser_batch.identities),
                start=1,
            ):
                self._validate_message_age(captured)
                filtered = self._privacy_filter.apply(captured)
                mapped = self._mapper.map(filtered)
                self._redaction_metadata[mapped.message_id] = (
                    filtered.redaction_categories,
                    filtered.redaction_count,
                )
                envelopes.append(
                    InboundEnvelope(
                        message=mapped,
                        source_cursor=(
                            f"browser:{batch.browser_batch.stream_id}:"
                            f"{identity.source_sequence}:"
                            f"{identity.identity_digest[:24]}"
                        ),
                        source_sequence=(
                            batch.browser_batch.checkpoint.accepted_count + index
                        ),
                    )
                )
            persisted: tuple[PersistedMessage, ...] = self._reliability.persist(
                self._instance_id,
                tuple(envelopes),
            )
            if after_transaction_commit is not None:
                after_transaction_commit()
            self._reader.acknowledge(batch)
            self._assert_zero_side_effect_reader()
            return PDDDurableIngestResult(
                batch_id=batch.browser_batch.batch_id,
                instance_id=self._instance_id,
                persisted_message_ids=tuple(
                    item.message.message_id for item in persisted if not item.duplicate
                ),
                duplicate_message_ids=tuple(
                    item.message.message_id for item in persisted if item.duplicate
                ),
                observed_at=self._clock(),
            )

    def drain_pending(self, *, limit: int = 100) -> tuple[PDDMessageObservationEvidence, ...]:
        """Recover and process committed inbox messages without creating Execution."""

        with self._lock:
            results: list[PDDMessageObservationEvidence] = []
            for delivery in self._reliability.receive_pending(
                self._instance_id,
                limit=limit,
            ):
                try:
                    results.append(self._decide_delivery(delivery))
                    self._reliability.ack(
                        self._instance_id,
                        delivery.delivery_id,
                    )
                except Exception:
                    self._reliability.mark_retry(
                        self._instance_id,
                        delivery.delivery_id,
                        reason_code="PDD_DECISION_DELIVERY_FAILED",
                    )
                    raise
            return tuple(results)

    def run_once(self) -> tuple[PDDMessageObservationEvidence, ...]:
        self.ingest_once()
        return self.drain_pending()

    def _decide_delivery(
        self, delivery: MessageDelivery
    ) -> PDDMessageObservationEvidence:
        mapped = delivery.message
        duplicate = self._message_exists(mapped)
        intake = self._conversation.receive(mapped.to_runtime_message())
        if (
            intake.decision_state is not DecisionState.WAITING_APPROVAL
            or not intake.requires_approval
        ):
            raise PDDMessageObservationSafetyViolation(
                "AI-CS Decision escaped WAITING_APPROVAL",
                error_code="PDD_MESSAGE_DECISION_NOT_WAITING_APPROVAL",
            )
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            approval = repo.get_approval_for_decision(intake.decision_id)
            execution = repo.get_execution_for_decision(intake.decision_id)
            receipt = (
                repo.get_receipt_for_execution(execution.execution_id)
                if execution is not None
                else None
            )
        if approval is not None or execution is not None or receipt is not None:
            raise PDDMessageObservationSafetyViolation(
                "durable message observation crossed the execution boundary",
                error_code="PDD_MESSAGE_EXECUTION_BOUNDARY_BREACHED",
            )
        now = self._clock()
        latency = max((now - mapped.timestamp).total_seconds(), 0.0)
        categories, redaction_count = self._redaction_metadata.get(
            mapped.message_id,
            ((), 0),
        )
        return PDDMessageObservationEvidence(
            message_id=intake.message_id,
            external_message_id=mapped.message_id,
            conversation_id=intake.conversation_id,
            external_conversation_id=mapped.conversation_id,
            decision_id=intake.decision_id,
            trace_id=intake.message_id,
            disposition=(
                PDDObservationDisposition.DUPLICATE
                if duplicate
                else PDDObservationDisposition.ACCEPTED
            ),
            delayed=latency >= self._policy.delay_warning_seconds,
            latency_seconds=latency,
            redaction_categories=categories,
            redaction_count=redaction_count,
            observed_at=now,
            safety=PDDMessageObservationSafetySnapshot(),
        )

    def _message_exists(self, message: ChannelMessageV1) -> bool:
        conversation_ref = store_scoped_conversation_ref(
            message.store_id,
            message.conversation_id,
        )
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            conversation = repo.find_conversation(message.channel, conversation_ref)
            if conversation is None:
                return False
            return repo.find_message(conversation.conversation_id, message.message_id) is not None

    def _validate_message_age(self, message: PDDCapturedMessage) -> None:
        age = (message.captured_at - message.timestamp).total_seconds()
        if age < -self._policy.maximum_future_skew_seconds:
            raise PDDMessageObservationError(
                "PDD message timestamp is too far in the future",
                error_code="PDD_MESSAGE_TIMESTAMP_IN_FUTURE",
            )
        if max(age, 0.0) > self._policy.maximum_message_age_seconds:
            raise PDDMessageObservationError(
                "PDD message exceeded the observation age limit",
                error_code="PDD_MESSAGE_STALE",
            )

    def _assert_zero_side_effect_reader(self) -> None:
        if not self._reader.read_only or self._reader.browser_write_operations != 0:
            raise PDDMessageObservationSafetyViolation(
                "PDD message reader crossed the write boundary",
                error_code="PDD_MESSAGE_READER_WRITE_DETECTED",
            )


__all__ = [
    "PDD_MESSAGE_OBSERVATION_VERSION",
    "BrowserPDDMessageReader",
    "FakePDDMessageReader",
    "PDDCapturedMessageBatch",
    "PDDCapturedMessage",
    "PDDDurableIngestResult",
    "PDDDurableMessageObservationRuntime",
    "PDDMessageObservationError",
    "PDDMessageObservationEvidence",
    "PDDMessageObservationPolicy",
    "PDDMessageObservationRuntime",
    "PDDMessageObservationSafetySnapshot",
    "PDDMessageObservationSafetyViolation",
    "PDDMessageReader",
    "PDDMessageReaderHealth",
    "PDDMessageReaderState",
    "PDDTransactionalMessageReader",
    "PDDObservationDisposition",
    "PDDObservationMessageMapper",
    "PDDPrivacyCategory",
    "PDDPrivacyFilter",
    "PDDPrivacyFilteredMessage",
]
