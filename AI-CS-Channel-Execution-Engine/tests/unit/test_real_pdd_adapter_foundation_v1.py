from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from channel_agent.binding import (
    AgentVerifiedActiveStoreSelectionRequest,
    PDDStoreBindingV1,
)
from channel_agent.controlled_send_grant import (
    ControlledSendGrantError,
    ControlledSendGrantStore,
    ControlledSendGrantV1,
)
from channel_agent.edge_pdd_observe import (
    PDDLocalReferenceTokenizer,
    PDDWorkspaceMessage,
    PDDWorkspaceObservationMapper,
    PDDWorkspaceOrder,
    PDDWorkspaceSnapshot,
)
from channel_agent.edge_spool import DurableEdgeSpool, EdgeSpoolConflict
from channel_agent.pdd_observer import PDDObserverRunner
from channel_agent.observation_runtime import ObserveOnlyRuntimeComponent
from channel_agent.pdd_page_port import build_sanitized_pdd_replay_fixture
from channel_agent.providers import ProviderUnavailable, RealPDDProvider
from channel_engine.agent.observation_pipeline import (
    AgentObservationContextProvider,
    PDDObservationPayload,
)
from channel_engine.provider import NormalizedChannelObservation

NOW = datetime(2026, 8, 12, 7, 0, tzinfo=UTC)
STORE = "c-store-pilot"
CONVERSATION = "real-conversation-001"
CUSTOMER = "sha256:" + "c" * 64
FINGERPRINT = "sha256:" + "f" * 64


class _PlainProtector:
    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


def _snapshot() -> PDDWorkspaceSnapshot:
    return PDDWorkspaceSnapshot(
        store_id=STORE,
        platform_store_id="328616090",
        store_name="只读测试店铺",
        conversation_id=CONVERSATION,
        customer_reference=CUSTOMER,
        page_fingerprint=FINGERPRINT,
        page_state="CUSTOMER_SERVICE_RUNNING",
        messages=(
            PDDWorkspaceMessage(
                external_message_id="customer-1",
                sender="CUSTOMER",
                content="这个规格适合几岁？",
                timestamp=NOW,
                sequence=1,
            ),
            PDDWorkspaceMessage(
                external_message_id="operator-1",
                sender="OPERATOR",
                content="建议五岁以上使用。",
                timestamp=NOW + timedelta(seconds=1),
                sequence=2,
            ),
            PDDWorkspaceMessage(
                external_message_id="customer-2",
                sender="CUSTOMER",
                content="那材质呢？",
                timestamp=NOW + timedelta(seconds=2),
                sequence=3,
            ),
        ),
        captured_at=NOW + timedelta(seconds=3),
    )


def test_mapper_emits_v22_real_provider_and_page_history() -> None:
    observation = PDDWorkspaceObservationMapper(
        agent_id="agent-1",
        device_id="device-1",
        provider_id="real-pdd-readonly",
    ).map_customer_messages(
        _snapshot(),
        selected_message_ids=frozenset({"customer-2"}),
    )[0]

    payload = PDDObservationPayload.model_validate_json(
        json.dumps(observation.payload, ensure_ascii=False, separators=(",", ":"))
    )
    assert payload.schema_version == "channel-agent-pdd-observation.v2.2"
    assert payload.provider_kind == "REAL_PDD"
    assert [item.sender for item in payload.visible_history] == [
        "CUSTOMER",
        "OPERATOR",
        "CUSTOMER",
    ]
    assert all(item.source == "REAL_PDD" for item in payload.visible_history)


def test_real_business_references_are_stable_tokens_and_never_cross_raw() -> None:
    tokenizer = PDDLocalReferenceTokenizer(b"privacy-token-key-32-bytes-minimum!!")
    snapshot = _snapshot().model_copy(
        update={
            "order": PDDWorkspaceOrder(
                order_reference="RAW-ORDER-A1B2C3",
                logistics_reference="RAW-TRACK-Z9Y8X7",
                order_status="PAID",
            ),
            "messages": (
                PDDWorkspaceMessage(
                    external_message_id="customer-private-1",
                    sender="CUSTOMER",
                    content=(
                        "姓名：张三，地址：上海市示例路88号；"
                        "微信号 wx_secret_88；订单号 RAW-ORDER-A1B2C3"
                    ),
                    timestamp=NOW,
                    sequence=1,
                ),
            ),
        }
    )
    payload = PDDWorkspaceObservationMapper(
        agent_id="agent-1",
        device_id="device-1",
        reference_tokenizer=tokenizer,
    ).map_customer_messages(snapshot)[0].payload

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "张三" not in serialized
    assert "上海市示例路88号" not in serialized
    assert "wx_secret_88" not in serialized
    assert "RAW-ORDER-A1B2C3" not in serialized
    assert payload["order"]["order_reference"].startswith("PDD_ORDER_")
    assert payload["order"]["logistics_reference"].startswith("PDD_LOGISTICS_")


def test_real_order_reference_without_local_tokenizer_fails_closed() -> None:
    snapshot = _snapshot().model_copy(
        update={"order": PDDWorkspaceOrder(order_reference="RAW-ORDER-A1B2C3")}
    )
    with pytest.raises(Exception, match="local tokenizer"):
        PDDWorkspaceObservationMapper(
            agent_id="agent-1", device_id="device-1"
        ).map_customer_messages(snapshot)


def test_v21_remains_accepted_but_cannot_carry_visible_history() -> None:
    payload = PDDWorkspaceObservationMapper(
        agent_id="agent-1", device_id="device-1"
    ).map_customer_messages(_snapshot())[0].payload
    payload["schema_version"] = "channel-agent-pdd-observation.v2.1"
    payload.pop("visible_history")
    parse = lambda value: PDDObservationPayload.model_validate_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )
    assert parse(payload).schema_version.endswith("v2.1")
    payload["visible_history"] = []
    assert parse(payload).visible_history == ()


def test_real_page_operator_history_enters_context_without_synthetic_fallback() -> None:
    observation = PDDWorkspaceObservationMapper(
        agent_id="agent-1", device_id="device-1"
    ).map_customer_messages(
        _snapshot(), selected_message_ids=frozenset({"customer-2"})
    )[0]
    latest = SimpleNamespace(
        payload=observation.payload,
        observation_id=observation.observation_id,
        external_message_id=observation.external_message_id,
        source_cursor=observation.source_cursor,
        source_sequence=observation.source_sequence,
    )
    store = SimpleNamespace(
        latest_observation=lambda *_args: latest,
        observation_provider_kinds=lambda *_args: {},
    )
    history = SimpleNamespace(load_history=lambda **_kwargs: ())
    entries = AgentObservationContextProvider(store, history).load_visible_history_for_turn(
        store_id=STORE,
        conversation_id=CONVERSATION,
        limit=20,
        excluded_external_message_ids=("customer-2",),
    )
    assert [(item.sender, item.external_message_id) for item in entries] == [
        ("customer", "customer-1"),
        ("operator", "operator-1"),
    ]


def test_host_owned_store_binding_overrides_agent_catalog_tenant() -> None:
    observation = PDDWorkspaceObservationMapper(
        agent_id="agent-1", device_id="device-1"
    ).map_customer_messages(_snapshot())[0]
    store = SimpleNamespace(
        latest_observation_payload=lambda *_args: observation.payload,
    )
    history = SimpleNamespace(load_history=lambda **_kwargs: ())
    provider = AgentObservationContextProvider(
        store,
        history,
        catalog_tenant_bindings={STORE: "c-tenant-production"},
    )

    page = provider.capture_page_context(
        store_id=STORE,
        conversation_id=CONVERSATION,
    )

    assert (
        PDDObservationPayload.model_validate_json(
            json.dumps(observation.payload, ensure_ascii=False, separators=(",", ":"))
        ).catalog_tenant_id
        == "CHANNEL-AGENT-PILOT"
    )
    assert page.catalog_tenant_id == "c-tenant-production"


def test_real_provider_is_bounded_and_rejects_non_real_items() -> None:
    real = NormalizedChannelObservation.synthetic(
        provider_id="seed",
        store_id=STORE,
        conversation_id=CONVERSATION,
        external_message_id="message-1",
        source_sequence=1,
        content="只读消息",
        timestamp=NOW,
    ).model_copy(update={"provider_kind": "REAL_PDD"})
    provider = RealPDDProvider(lambda limit: (real,), provider_id="pilot-real")
    item = provider.poll(limit=1)[0]
    assert item.provider_kind == "REAL_PDD"
    assert item.provider_id == "pilot-real"
    with pytest.raises(ProviderUnavailable):
        RealPDDProvider(lambda limit: (real, real)).poll(limit=1)


def test_real_provider_revalidates_copied_business_references() -> None:
    real = NormalizedChannelObservation.synthetic(
        provider_id="seed",
        store_id=STORE,
        conversation_id=CONVERSATION,
        external_message_id="message-unsafe",
        source_sequence=1,
        content="只读消息",
        timestamp=NOW,
    ).model_copy(
        update={
            "provider_kind": "REAL_PDD",
            "order": {"order_reference": "RAW-ORDER-A1B2C3"},
        }
    )
    with pytest.raises(ProviderUnavailable):
        RealPDDProvider(lambda _limit: (real,)).poll(limit=1)


def test_pdd_store_binding_projects_verified_server_mapping() -> None:
    request = AgentVerifiedActiveStoreSelectionRequest(
        device_id="device-1",
        user_reference="user-1",
        store_reference=STORE,
        platform="pdd",
        observed_platform_store_id="328616090",
        platform_binding_id="binding-1",
        platform_binding_verified_at=NOW,
        binding_revision=3,
        human_confirmed=True,
        reason="pilot verification",
    )
    binding = PDDStoreBindingV1.from_verified_selection(request)
    binding.assert_current_page(
        observed_pdd_store_id="328616090", ai_cs_store_reference=STORE
    )
    with pytest.raises(ValueError):
        binding.assert_current_page(
            observed_pdd_store_id="different", ai_cs_store_reference=STORE
        )


def test_replay_builder_requires_allowlist_and_removes_real_identifiers() -> None:
    scan = {
        "fingerprint": FINGERPRINT,
        "conversations": [
            {
                "conversation_id": "real-secret-conversation",
                "customer_reference": "real-secret-customer",
                "unread_count": 1,
                "last_activity": NOW.isoformat(),
                "latest_sequence": 1,
            }
        ],
    }
    capture = {
        "fingerprint": FINGERPRINT,
        "active_conversation_id": "real-secret-conversation",
        "customer_reference": "real-secret-customer",
        "store_name": "真实店铺名称",
        "product": {
            "product_id": "real-product-id",
            "product_name": "测试积木",
            "sku_id": "real-sku-id",
            "sku_name": "蓝色款",
        },
        "messages": [
            {
                "message_id": "real-message-id",
                "role": "buyer",
                "content": "我的手机是13800138000",
                "timestamp": NOW.isoformat(),
                "sequence": 1,
            }
        ],
    }
    fixture = build_sanitized_pdd_replay_fixture(
        scan=scan,
        capture=capture,
        role_map={"buyer": "CUSTOMER"},
        target_conversation_id="real-secret-conversation",
        allowed_message_ids=("real-message-id",),
        captured_at=NOW,
    )
    serialized = fixture.model_dump_json()
    assert "real-secret" not in serialized
    assert "real-product-id" not in serialized
    assert "13800138000" not in serialized
    assert "[手机号已脱敏]" in serialized


def test_observer_session_warns_then_stops_before_another_scan() -> None:
    runner = PDDObserverRunner(
        SimpleNamespace(scan_once=lambda: None),
        maximum_session_seconds=30,
        warning_seconds=25,
        monotonic=lambda: 0.0,
    )
    runner._session_started_at = 0.0
    assert runner._session_event(24.0) is None
    assert runner._session_event(25.0) == "PDD_OBSERVER_SESSION_WARNING"
    assert runner._session_event(26.0) is None
    assert runner._session_event(30.0) == "PDD_OBSERVER_SESSION_LIMIT_REACHED"


def test_observer_clears_transient_error_after_next_successful_scan() -> None:
    errors: list[str] = []
    recoveries: list[str] = []

    class FlakyObserver:
        calls = 0
        runner: PDDObserverRunner

        def scan_once(self) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary PDD redraw")
            self.runner._stop.set()

    observer = FlakyObserver()
    runner = PDDObserverRunner(
        observer,
        error_sink=errors.append,
        recovery_sink=lambda: recoveries.append("RECOVERED"),
    )
    observer.runner = runner

    runner._run()

    assert errors == ["PDD_OBSERVER_RUNTIMEERROR"]
    assert recoveries == ["RECOVERED"]


def test_session_limit_requires_explicit_restart_and_recovers_pending() -> None:
    class Runner:
        running = False
        stop_reason = "PDD_OBSERVER_SESSION_LIMIT_REACHED"
        starts = 0

        def start(self) -> None:
            self.running = True
            self.stop_reason = None
            self.starts += 1

        def stop(self, timeout: float = 5.0) -> None:
            del timeout
            self.running = False

    class Forwarder:
        recovered = 0

        def recover_pending(self) -> int:
            self.recovered += 1
            return self.recovered

    runner = Runner()
    forwarder = Forwarder()
    component = ObserveOnlyRuntimeComponent(
        forwarder=forwarder,
        observer=runner,
        assistant_events=SimpleNamespace(start=lambda: None, stop=lambda timeout=5: None),
    )
    component._started = True
    component._observing = True

    component.set_page_ready(True)
    assert component.observing is False
    assert runner.starts == 0

    assert component.restart_observer(page_ready=True) is True
    assert component.observing is True
    assert runner.starts == 1
    assert forwarder.recovered == 1


def test_session_restart_does_not_block_on_stale_pending_recovery() -> None:
    class Runner:
        running = False
        stop_reason = "PDD_OBSERVER_SESSION_LIMIT_REACHED"
        starts = 0

        def start(self) -> None:
            self.running = True
            self.stop_reason = None
            self.starts += 1

        def stop(self, timeout: float = 5.0) -> None:
            del timeout
            self.running = False

    class Forwarder:
        def recover_pending(self) -> int:
            raise RuntimeError("already accepted by Host")

    errors: list[str] = []
    runner = Runner()
    component = ObserveOnlyRuntimeComponent(
        forwarder=Forwarder(),
        observer=runner,
        assistant_events=SimpleNamespace(start=lambda: None, stop=lambda timeout=5: None),
        error_sink=errors.append,
    )
    component._started = True

    assert component.restart_observer(page_ready=True) is True
    assert component.observing is True
    assert runner.starts == 1
    assert errors == ["OBSERVATION_RECOVERY_RUNTIMEERROR"]


def test_missing_page_sequence_uses_durable_message_id_monotonic_mapping(tmp_path) -> None:
    spool = DurableEdgeSpool(
        tmp_path / "edge-spool.sqlite3", _PlainProtector(), clock=lambda: NOW
    )
    first = spool.resolve_message_sequence(
        store_id=STORE,
        platform_store_id="328616090",
        conversation_id=CONVERSATION,
        external_message_id="stable-message-a",
        page_sequence=0,
    )
    repeated = spool.resolve_message_sequence(
        store_id=STORE,
        platform_store_id="328616090",
        conversation_id=CONVERSATION,
        external_message_id="stable-message-a",
        page_sequence=0,
    )
    second = spool.resolve_message_sequence(
        store_id=STORE,
        platform_store_id="328616090",
        conversation_id=CONVERSATION,
        external_message_id="stable-message-b",
        page_sequence=0,
    )
    assert (first, repeated, second) == (1, 1, 2)
    with pytest.raises(EdgeSpoolConflict):
        spool.resolve_message_sequence(
            store_id=STORE,
            platform_store_id="328616090",
            conversation_id=CONVERSATION,
            external_message_id="stable-message-c",
            page_sequence=2,
        )


def test_controlled_send_grant_is_five_minute_target_bound_and_single_use(tmp_path) -> None:
    content = "这是指定测试会话的单条人工确认回复。"
    grant = ControlledSendGrantV1.issue(
        store_id=STORE,
        test_buyer_hash=CUSTOMER,
        conversation_id=CONVERSATION,
        customer_message_id="customer-2",
        decision_id="decision-1",
        reply_content=content,
        operator_reference="operator-1",
        issued_at=NOW,
    )
    ledger = ControlledSendGrantStore(tmp_path / "controlled-send.sqlite3")
    kwargs = dict(
        store_id=STORE,
        test_buyer_hash=CUSTOMER,
        conversation_id=CONVERSATION,
        customer_message_id="customer-2",
        decision_id="decision-1",
        reply_content=content,
        now=NOW + timedelta(seconds=1),
    )
    ledger.consume_once(grant, **kwargs)
    with pytest.raises(ControlledSendGrantError):
        ledger.consume_once(grant, **kwargs)
    with pytest.raises(ControlledSendGrantError):
        grant.assert_target(**(kwargs | {"reply_content": "被篡改的回复"}))
    with pytest.raises(ControlledSendGrantError):
        grant.assert_target(**(kwargs | {"now": NOW + timedelta(minutes=5)}))


def test_visible_history_hashes_are_exact_content_hashes() -> None:
    observation = PDDWorkspaceObservationMapper(
        agent_id="agent-1", device_id="device-1"
    ).map_customer_messages(_snapshot())[0]
    for item in observation.payload["visible_history"]:
        assert item["content_sha256"] == hashlib.sha256(
            item["content"].encode("utf-8")
        ).hexdigest()
