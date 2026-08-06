from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from itertools import count

import pytest
from sqlalchemy import select

from channel_engine.browser import (
    BrowserLoginState,
    BrowserProfileReference,
    BrowserSessionManager,
    CDPPageTarget,
    ChromeDevToolsReadOnlyPagePort,
    ChromeLaunchStrategy,
    FakeBrowserRuntimeDriver,
    InMemoryBrowserObservationStore,
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorKey,
    SelectorRegistry,
)
from channel_engine.conversation import ConversationService
from channel_engine.gateway import CONTRACT_VERSION
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayClient,
    GatewayServiceIdentity,
    MockAICSGateway,
    MockAICSGatewayTransport,
)
from channel_engine.models import DecisionState
from channel_engine.pdd_adapter import (
    PDDObserveError,
    PDDObserveModeRuntime,
    PDDObserveState,
    PDDPrivacyCategory,
)
from channel_engine.storage.orm import MessageRow


NOW = datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc)
SECRET = b"pdd-observe-gateway-test-secret-32b"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="pdd-observe-key",
    credential_ref="vault://ai-cs/pdd-observe/key",
)


class Resolver:
    def resolve(self) -> CDPPageTarget:
        return CDPPageTarget(
            target_id="observe-runtime-target",
            websocket_url="ws://127.0.0.1:9222/devtools/page/observe-runtime-target",
            location_origin="https://mms.pinduoduo.com",
        )


class Evaluator:
    def __init__(self) -> None:
        self.results = deque(
            (
                {
                    "STORE_ID": {"count": 1, "value": "observed-store-001"},
                    "STORE_NAME": {"count": 1, "value": "Observed Test Store"},
                },
                [self.message("existing")],
                [self.message("existing"), self.message("new")],
            )
        )

    @staticmethod
    def message(suffix: str) -> dict[str, str]:
        content = (
            "我叫张三；手机号13800138000；地址：上海浦东新区；"
            "卡号6222020202020202；什么时候发货？"
            if suffix == "new"
            else f"Synthetic customer question {suffix}"
        )
        return {
            "conversation_id": "observed-conversation-001",
            "external_message_id": f"observed-message-{suffix}",
            "sender": "customer",
            "content": content,
            "timestamp": "2026-08-05T11:00:00+00:00",
        }

    def evaluate(self, target: CDPPageTarget, expression: str) -> object:
        del target, expression
        return self.results.popleft()


def selector_contract() -> SelectorContract:
    def css(
        key: SelectorKey,
        locator: str,
        attribute: str | None = None,
        maximum: int | None = None,
    ) -> SelectorBinding:
        return SelectorBinding(
            key=key,
            engine=LocatorEngine.CSS,
            locator=locator,
            value_attribute=attribute,
            expected_count_max=maximum,
        )

    return SelectorContract(
        platform="pdd",
        page="merchant_chat",
        version="observe-v1",
        state=SelectorContractState.VERIFIED,
        capabilities=frozenset(
            {SelectorCapability.STORE_IDENTITY, SelectorCapability.RECEIVE_MESSAGE}
        ),
        bindings=(
            css(SelectorKey.STORE_ID, "[data-store-id]", "data-store-id", 1),
            css(SelectorKey.STORE_NAME, "[data-store-name]", "data-store-name", 1),
            css(SelectorKey.CONVERSATION_ITEM, "[data-conversation]"),
            css(
                SelectorKey.CONVERSATION_ID,
                "[data-conversation-id]",
                "data-conversation-id",
            ),
            css(SelectorKey.MESSAGE_ITEM, "[data-message-id]"),
            css(
                SelectorKey.EXTERNAL_MESSAGE_ID,
                "[data-message-id]",
                "data-message-id",
            ),
            css(SelectorKey.MESSAGE_SENDER, "[data-sender]", "data-sender"),
            css(SelectorKey.MESSAGE_CONTENT, ".message-content"),
            css(SelectorKey.MESSAGE_TIMESTAMP, "time[datetime]", "datetime"),
        ),
        evidence_reference="evidence-ref://pdd/observe/integration-selector",
        verified_at=NOW,
    )


def test_observe_mode_reaches_decision_and_stops_at_waiting_approval(
    foundation,
) -> None:
    driver = FakeBrowserRuntimeDriver(
        login_state=BrowserLoginState.AUTHENTICATED,
        clock=lambda: NOW,
    )
    manager = BrowserSessionManager(
        driver,
        BrowserProfileReference(
            profile_id="pdd-observe-profile",
            account_ref="pdd-observe-account",
            storage_reference="profile-ref://pdd/observe/single-store",
        ),
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version="observe-v1",
        clock=lambda: NOW,
    )
    registry = SelectorRegistry()
    registry.register(selector_contract(), activate=True)
    page_port = ChromeDevToolsReadOnlyPagePort(
        Resolver(), Evaluator(), clock=lambda: NOW
    )
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    nonce = count(1)
    gateway = GatewayClient(
        MockAICSGatewayTransport(server),
        IDENTITY,
        FakeGatewayTokenProvider(
            {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        nonce_factory=lambda: f"pddobserve{next(nonce):016d}",
        sleeper=lambda _delay: None,
    )
    conversation = ConversationService(foundation["uow_factory"], gateway)
    runtime = PDDObserveModeRuntime(
        manager,
        registry,
        page_port,
        InMemoryBrowserObservationStore(),
        conversation,
        foundation["uow_factory"],
        credential_reference="credential-ref://pdd/observe/manual-session",
        clock=lambda: NOW,
    )

    started = runtime.start()
    binding = runtime.bind_store()
    baseline = runtime.observe_once()
    decisions = runtime.observe_once()

    assert started.state is PDDObserveState.VERIFYING_STORE
    assert binding.store_id == "observed-store-001"
    assert baseline == ()
    assert len(decisions) == 1
    assert decisions[0].decision_state == DecisionState.WAITING_APPROVAL.value
    assert decisions[0].requires_approval is True
    assert runtime.status().state is PDDObserveState.READY
    assert runtime.status().observed_message_count == 1
    assert runtime.status().decision_count == 1
    assert runtime.safety_snapshot().execution_created == 0
    assert runtime.safety_snapshot().receipt_published == 0
    assert page_port.page_write_operations == 0
    assert server.decision_server.decision_compute_count == 1
    assert server.artifact_server.accept_count == 0
    assert foundation["executor"].call_count == 0
    assert not hasattr(runtime, "approve")
    assert not hasattr(runtime, "execute")
    assert not hasattr(runtime, "send_message")

    observation_evidence = runtime.message_evidence()
    assert len(observation_evidence) == 1
    assert set(observation_evidence[0].redaction_categories) == {
        PDDPrivacyCategory.NAME,
        PDDPrivacyCategory.PHONE,
        PDDPrivacyCategory.ADDRESS,
        PDDPrivacyCategory.PAYMENT,
    }
    with foundation["session_factory"]() as session:
        persisted_content = session.scalar(select(MessageRow.content))
    assert persisted_content is not None
    assert "张三" not in persisted_content
    assert "13800138000" not in persisted_content
    assert "上海浦东新区" not in persisted_content
    assert "6222020202020202" not in persisted_content

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.get_approval_for_decision(decisions[0].decision_id) is None
        assert repo.get_execution_for_decision(decisions[0].decision_id) is None

    assert gateway.contract_version == CONTRACT_VERSION


def test_observe_mode_waits_for_human_login_and_cannot_bind_early(
    foundation,
) -> None:
    driver = FakeBrowserRuntimeDriver(
        login_state=BrowserLoginState.REQUIRED,
        clock=lambda: NOW,
    )
    manager = BrowserSessionManager(
        driver,
        BrowserProfileReference(
            profile_id="pdd-observe-waiting-profile",
            account_ref="pdd-observe-waiting-account",
            storage_reference="profile-ref://pdd/observe/waiting-login",
        ),
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version="observe-v1",
        clock=lambda: NOW,
    )
    page_port = ChromeDevToolsReadOnlyPagePort(
        Resolver(), Evaluator(), clock=lambda: NOW
    )
    runtime = PDDObserveModeRuntime(
        manager,
        SelectorRegistry(),
        page_port,
        InMemoryBrowserObservationStore(),
        ConversationService(foundation["uow_factory"], foundation["gateway"]),
        foundation["uow_factory"],
        credential_reference="credential-ref://pdd/observe/manual-session",
        clock=lambda: NOW,
    )

    status = runtime.start()

    assert status.state is PDDObserveState.WAITING_LOGIN
    assert status.human_login_required is True
    assert status.login_state is BrowserLoginState.REQUIRED
    assert runtime.safety_snapshot().automatic_login_performed is False
    assert runtime.safety_snapshot().customer_message_sent == 0
    with pytest.raises(PDDObserveError) as raised:
        runtime.bind_store()
    assert raised.value.error_code == "PDD_OBSERVE_HUMAN_LOGIN_REQUIRED"
    assert foundation["gateway"].call_count == 0
    assert foundation["executor"].call_count == 0
