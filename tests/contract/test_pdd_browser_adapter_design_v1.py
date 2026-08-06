from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from channel_engine.browser import (
    BrowserActionPhase,
    BrowserActionResult,
    BrowserExecutionDisabled,
    BrowserHeartbeatState,
    BrowserLoginState,
    BrowserObservationConflict,
    BrowserObservationMechanism,
    BrowserProfileIsolationError,
    BrowserProfileIsolationRegistry,
    BrowserProfileReference,
    BrowserSessionManager,
    BrowserSessionState,
    ChromeLaunchStrategy,
    ControlledOutboundBrowserExecutor,
    FakeBrowserActionPort,
    FakeBrowserPageObservationPort,
    FakeBrowserPageRouter,
    FakeBrowserRuntimeDriver,
    MockPDDBrowserAdapter,
    PDDMessageExtractor,
    RawBrowserMessage,
    ReceiveOnlyPageObserver,
    SelectorContractDrift,
    SelectorProbeResult,
    SelectorRegistry,
    draft_pdd_merchant_chat_v1,
    verified_mock_pdd_merchant_chat_v1,
)
from channel_engine.channel import (
    ChannelAdapter,
    LedgerExecutionAuthorizationService,
    NormalizedMessage,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import ExecutionState, ReceiptOutcome
from channel_engine.policy import ApprovalPolicy


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)


def profile(account: str = "mock-pdd-account") -> BrowserProfileReference:
    return BrowserProfileReference(
        profile_id=f"profile-{account}",
        account_ref=account,
        storage_reference=f"profile-ref://pdd/{account}",
    )


def browser_fixture():
    selector = verified_mock_pdd_merchant_chat_v1(NOW)
    registry = SelectorRegistry()
    registry.register(selector, activate=True)
    driver = FakeBrowserRuntimeDriver(clock=lambda: NOW)
    manager = BrowserSessionManager(
        driver,
        profile(),
        strategy=ChromeLaunchStrategy.MOCK,
        selector_contract_version=selector.version,
        clock=lambda: NOW,
    )
    page_port = FakeBrowserPageObservationPort()
    observer = ReceiveOnlyPageObserver(
        manager.snapshot,
        page_port,
        PDDMessageExtractor(),
        registry,
    )
    adapter = MockPDDBrowserAdapter(manager, observer)
    session = adapter.connect()
    assert session.page_context is not None
    return selector, registry, driver, manager, page_port, adapter


def enqueue_browser_execution(foundation, suffix: str):
    conversation_ref = f"browser-conversation-{suffix}"
    intake = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    ).receive(
        NormalizedMessage(
            channel="pdd",
            conversation_id=conversation_ref,
            external_message_id=f"browser-message-{suffix}",
            sender="synthetic-buyer",
            content="synthetic browser adapter question",
            timestamp=NOW,
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(intake.decision_id, "browser-human-operator")
    return conversation_ref, enqueued


def test_pdd_selector_v1_is_draft_until_real_page_evidence_exists() -> None:
    draft = draft_pdd_merchant_chat_v1()
    assert draft.contract_id == "pdd:merchant_chat:v1"
    assert draft.bindings == ()
    assert draft.verified_at is None
    registry = SelectorRegistry()
    with pytest.raises(ValueError, match="only verified"):
        registry.register(draft, activate=True)

    verified_mock = verified_mock_pdd_merchant_chat_v1(NOW)
    registry.register(verified_mock, activate=True)
    assert registry.active("pdd", "merchant_chat") == verified_mock
    assert len(verified_mock.fingerprint()) == 64
    assert all(binding.engine.value == "MOCK" for binding in verified_mock.bindings)

    drift = SelectorProbeResult(
        contract_id=verified_mock.contract_id,
        contract_fingerprint=verified_mock.fingerprint(),
        page_context_id="mock-page",
        passed=False,
        missing_keys=(verified_mock.bindings[0].key,),
        checked_at=NOW,
    )
    with pytest.raises(SelectorContractDrift):
        registry.assert_probe(drift)


def test_session_lifecycle_login_expiry_crash_recovery_and_profile_isolation() -> None:
    selector, _registry, driver, manager, _page_port, adapter = browser_fixture()
    active = manager.snapshot()
    assert active.state is BrowserSessionState.ACTIVE
    assert active.login_state is BrowserLoginState.AUTHENTICATED
    assert active.generation == 1
    assert active.page_context is not None
    assert active.page_context.selector_contract_version == selector.version
    assert driver.real_browser_started is False

    driver.heartbeat_state = BrowserHeartbeatState.CRASHED
    driver.failure_code = "MOCK_CHROME_CRASHED"
    crashed = adapter.heartbeat()
    assert crashed.state is BrowserSessionState.CRASHED
    driver.heartbeat_state = BrowserHeartbeatState.HEALTHY
    driver.failure_code = None
    recovered = manager.recover()
    assert recovered.state is BrowserSessionState.ACTIVE
    assert recovered.generation == 2
    assert recovered.profile == active.profile
    assert driver.start_count == 2

    driver.login_state = BrowserLoginState.EXPIRED
    expired = adapter.heartbeat()
    assert expired.state is BrowserSessionState.EXPIRED
    assert expired.human_takeover_required is True

    isolation = BrowserProfileIsolationRegistry()
    isolation.register(profile("account-a"))
    with pytest.raises(BrowserProfileIsolationError):
        isolation.register(
            BrowserProfileReference(
                profile_id="profile-account-b",
                account_ref="account-b",
                storage_reference="profile-ref://pdd/account-a",
            )
        )


def test_login_is_never_automated_and_requires_human_takeover() -> None:
    selector = verified_mock_pdd_merchant_chat_v1(NOW)
    driver = FakeBrowserRuntimeDriver(
        login_state=BrowserLoginState.REQUIRED,
        clock=lambda: NOW,
    )
    manager = BrowserSessionManager(
        driver,
        profile(),
        strategy=ChromeLaunchStrategy.MOCK,
        selector_contract_version=selector.version,
        clock=lambda: NOW,
    )
    session = manager.start()
    assert session.state is BrowserSessionState.LOGIN_REQUIRED
    assert session.human_takeover_required is True
    assert driver.start_count == 1
    assert driver.real_browser_started is False


def test_receive_only_observer_normalizes_orders_and_deduplicates_messages() -> None:
    _selector, _registry, _driver, _manager, page_port, adapter = browser_fixture()
    assert isinstance(adapter, ChannelAdapter)
    later = RawBrowserMessage(
        conversation_id="mock-conversation",
        external_message_id="message-2",
        sender="buyer-1",
        content="second",
        timestamp=NOW.replace(second=2),
        observation_mechanism=BrowserObservationMechanism.MOCK_FEED,
    )
    earlier = later.model_copy(
        update={
            "external_message_id": "message-1",
            "content": "first",
            "timestamp": NOW.replace(second=1),
        }
    )
    page_port.enqueue(later, earlier)

    first = adapter.receive_message()
    second = adapter.receive_message()
    assert first is not None and first.external_message_id == "message-1"
    assert second is not None and second.external_message_id == "message-2"
    assert first.channel == "pdd"
    assert adapter.get_conversation("mock-conversation").message_count == 2
    page_port.enqueue(earlier)
    assert adapter.receive_message() is None
    assert page_port.real_page_accessed is False

    page_port.enqueue(earlier.model_copy(update={"content": "changed"}))
    with pytest.raises(BrowserObservationConflict):
        adapter.receive_message()
    with pytest.raises(BrowserExecutionDisabled):
        adapter.send_message(None)
    assert adapter.send_call_count == 1


@pytest.mark.parametrize(
    ("outcome", "expected_state", "expected_retry"),
    [
        (ReceiptOutcome.SUCCESS, ExecutionState.SUCCESS, False),
        (ReceiptOutcome.FAILED, ExecutionState.FAILED, True),
        (ReceiptOutcome.UNKNOWN, ExecutionState.UNKNOWN, False),
    ],
)
def test_outbound_executor_requires_live_ledger_and_maps_receipt_safely(
    foundation,
    outcome: ReceiptOutcome,
    expected_state: ExecutionState,
    expected_retry: bool,
) -> None:
    suffix = outcome.value.casefold()
    conversation_ref, enqueued = enqueue_browser_execution(foundation, suffix)
    _selector, registry, driver, manager, _page_port, _adapter = browser_fixture()
    page = manager.snapshot().page_context
    assert page is not None
    router = FakeBrowserPageRouter()
    router.bind(conversation_ref, page)
    action_port = FakeBrowserActionPort(outcome)
    executor = ControlledOutboundBrowserExecutor(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        router,
        registry,
        action_port,
    )
    worker = ExecutionWorker(
        foundation["uow_factory"],
        executor,
        f"browser-worker-{suffix}",
    )

    result = worker.run_once()
    assert result is not None
    assert result.execution_id == enqueued.execution_id
    assert result.execution_state is expected_state
    assert action_port.call_count == 1
    assert action_port.real_browser_called is False
    assert driver.real_browser_started is False
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None
    assert receipt.outcome is outcome
    assert receipt.details["human_approval_verified"] is True
    assert receipt.details["execution_lease_verified"] is True
    assert receipt.details["automatic_reply"] is False
    assert receipt.details["automatic_retry_allowed"] is expected_retry
    assert receipt.details["real_browser_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert receipt.details["simulation_only"] is True
    if outcome is ReceiptOutcome.UNKNOWN:
        assert receipt.details["human_takeover_required"] is True
        assert worker.run_once() is None


def test_browser_result_cannot_label_pretrigger_failure_unknown() -> None:
    with pytest.raises(ValidationError, match="post-trigger"):
        BrowserActionResult(
            outcome=ReceiptOutcome.UNKNOWN,
            phase=BrowserActionPhase.VALIDATED,
            error_code="INVALID_UNKNOWN",
            real_browser_called=False,
            customer_message_sent=False,
        )
    with pytest.raises(ValidationError, match="post-trigger failure"):
        BrowserActionResult(
            outcome=ReceiptOutcome.FAILED,
            phase=BrowserActionPhase.SEND_TRIGGERED,
            error_code="INVALID_FAILED",
            real_browser_called=False,
            customer_message_sent=False,
        )
