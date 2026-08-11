from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from channel_agent.config import ChannelAgentConfig
from channel_agent.control_v2 import (
    AgentAssistantSnapshot,
    AgentObservationSubmission,
    DeviceRequestSigner,
    DeviceRequestVerifier,
)
from channel_agent.edge_pdd_observe import PDDWorkspaceObservationMapper
from channel_agent.edge_spool import DurableEdgeSpool
from channel_agent.observation_runtime import PersistOnlyObservationForwarder
from channel_agent.observation_stages import ObservationStage
from channel_agent.pdd_observer import PDDMessageObserver
from channel_agent.pdd_page_port import ReplayPDDPageReadPort, load_pdd_replay_fixture
from channel_agent.pdd_readonly_driver import (
    EvidenceBackedPDDReadOnlyDriver,
    PDDReadOnlyDriverError,
    build_replay_observer_evidence,
)
from channel_agent.security import DeviceCredentialMaterial
from channel_engine.agent.control_store import AgentControlStore
from channel_engine.agent.control_v2 import create_channel_agent_control_v2_router
from channel_engine.agent.observation_worker import AgentObservationWorker
from channel_engine.agent.node_api import ChannelAgentNodeRegistry
from channel_engine.gateway import GatewayRiskLevel
from channel_engine.storage import create_engine_and_session, create_schema


NOW = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "simulators"
    / "pdd-customer-workspace"
    / "fixtures"
    / "pdd-readonly-page-fixture.v1.json"
)


class PlainProtector:
    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


def test_offline_replay_configuration_is_a_hard_live_pdd_lock() -> None:
    safe = ChannelAgentConfig(
        server_url="http://127.0.0.1:8000",
        agent_id="offline-agent",
        device_id="offline-device",
        runtime_mode="SIMULATOR",
        development_profile="OFFLINE_REPLAY",
        customer_assistant_enabled=True,
        message_observation_enabled=True,
        observation_stage=ObservationStage.AI_SUGGESTIONS,
        pdd_replay_fixture_path=FIXTURE,
        pdd_replay_platform_store_id="synthetic-platform-store-001",
    )
    assert safe.browser_enabled is False
    assert safe.pdd_login_url is None
    assert safe.real_send_enabled is False

    for unsafe in (
        {"browser_enabled": True},
        {"pdd_login_observation_enabled": True},
        {"pdd_login_url": "https://mms.pinduoduo.com/login/"},
        {"runtime_mode": "PRODUCTION"},
        {"real_send_enabled": True},
    ):
        with pytest.raises(ValidationError):
            ChannelAgentConfig(
                server_url="http://127.0.0.1:8000",
                agent_id="offline-agent",
                device_id="offline-device",
                development_profile="OFFLINE_REPLAY",
                pdd_replay_fixture_path=FIXTURE,
                pdd_replay_platform_store_id="synthetic-platform-store-001",
                **unsafe,
            )


def test_replay_uses_the_production_parser_and_generates_zero_pdd_requests(
    tmp_path: Path,
) -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    port = ReplayPDDPageReadPort(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="synthetic-platform-store-001",
        evidence=build_replay_observer_evidence(fixture),
        page_port=port,
        clock=lambda: NOW,
    )
    spool = DurableEdgeSpool(
        tmp_path / "offline-spool.sqlite3",
        PlainProtector(),
        clock=lambda: NOW,
    )
    observer = PDDMessageObserver(
        driver=driver,
        mapper=PDDWorkspaceObservationMapper(
            agent_id="offline-agent", device_id="offline-device"
        ),
        spool=spool,
        forward=PersistOnlyObservationForwarder(spool),
        stage=ObservationStage.MESSAGE_CAPTURE,
        clock=lambda: NOW,
    )

    result = observer.scan_once()

    assert result.conversations_seen == 1
    assert result.conversations_captured == 1
    assert result.observations_forwarded == 3
    assert len(spool.pending()) == 3
    assert {item.payload["origin"] for item in spool.pending()} == {"SYNTHETIC"}
    assert driver.source_kind == "OFFLINE_REPLAY"
    assert driver.pdd_network_requests == 0
    assert port.pdd_network_requests == 0


def test_conversation_list_stage_never_captures_message_content(tmp_path: Path) -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    port = ReplayPDDPageReadPort(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="synthetic-platform-store-001",
        evidence=build_replay_observer_evidence(fixture),
        page_port=port,
        clock=lambda: NOW,
    )
    spool = DurableEdgeSpool(
        tmp_path / "list-only.sqlite3", PlainProtector(), clock=lambda: NOW
    )
    result = PDDMessageObserver(
        driver=driver,
        mapper=PDDWorkspaceObservationMapper(
            agent_id="offline-agent", device_id="offline-device"
        ),
        spool=spool,
        forward=PersistOnlyObservationForwarder(spool),
        stage=ObservationStage.CONVERSATION_LIST,
        clock=lambda: NOW,
    ).scan_once()

    assert result.conversations_seen == 1
    assert result.conversations_captured == 0
    assert spool.pending() == ()
    assert port.read_calls == 1


def test_signed_assistant_snapshot_is_device_scoped_and_expires(tmp_path: Path) -> None:
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'snapshot.sqlite3').as_posix()}"
    )
    create_schema(engine)
    store = AgentControlStore(sessions, clock=lambda: NOW)
    stored = store.persist_assistant_snapshot(
        AgentAssistantSnapshot(
            agent_id="offline-agent",
            device_id="offline-device",
            store_id="store-001",
            conversation_id="offline-conversation-001",
            revision=1,
            status="WAITING_APPROVAL",
            turn_id="turn-001",
            decision_id="decision-001",
            request_id="request-001",
            customer_reference="sha256:" + "a" * 64,
            current_question="合成客户问题",
            action="SUGGEST_REPLY",
            reply_content="合成 AI 建议，必须人工审核",
            risk_level="LOW",
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=30),
        )
    )
    assert stored.revision == 1

    secret = b"offline-snapshot-device-secret-32bytes"
    verifier = DeviceRequestVerifier(
        lambda _agent, _device: DeviceCredentialMaterial(
            "wincred://offline/device", secret
        ),
        clock=lambda: NOW.timestamp(),
    )
    app = FastAPI()
    app.include_router(
        create_channel_agent_control_v2_router(
            ChannelAgentNodeRegistry(clock=lambda: NOW),
            object(),  # pairing routes are not exercised by this scoped test
            verifier,
            store,
        )
    )
    client = TestClient(app, base_url="https://testserver")
    path = "/channel-agent/v2/assistant-snapshot"
    headers = DeviceRequestSigner(
        "offline-agent", "offline-device", secret
    ).headers(
        "GET",
        path,
        timestamp=int(NOW.timestamp()),
        nonce="a" * 32,
    )

    response = client.get(path, headers=headers)

    assert response.status_code == 200
    assert response.json()["snapshot"]["decision_id"] == "decision-001"
    assert response.json()["snapshot"]["safety"]["real_send"] is False
    assert store.assistant_snapshot("other-agent", "offline-device") is None
    engine.dispose()


def test_host_worker_publishes_ai_snapshot_without_execution_or_send(tmp_path: Path) -> None:
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'worker.sqlite3').as_posix()}"
    )
    create_schema(engine)
    store = AgentControlStore(sessions, clock=lambda: NOW)
    store.persist_observation(
        AgentObservationSubmission(
            observation_id="offline-observation-001",
            agent_id="offline-agent",
            device_id="offline-device",
            store_id="store-001",
            conversation_id="offline-conversation-001",
            external_message_id="offline-message-001",
            source_cursor="store-001:synthetic:offline-conversation-001:1",
            source_sequence=1,
            payload_digest="sha256:" + "b" * 64,
            payload={
                "schema_version": "channel-agent-pdd-observation.v2.1",
                "platform": "PDD",
                "store_id": "store-001",
                "platform_store_id": "synthetic-platform-store-001",
                "store_name": "离线演练店铺",
                "conversation_id": "offline-conversation-001",
                "customer_reference": "sha256:" + "a" * 64,
                "external_message_id": "offline-message-001",
                "sender": "CUSTOMER",
                "origin": "SYNTHETIC",
                "content": "合成客户问题",
                "timestamp": NOW.isoformat(),
                "product": {},
                "order": {},
                "page_fingerprint": "sha256:" + "1" * 64,
                "selector_evidence_hash": None,
                "privacy_filtered": True,
            },
            captured_at=NOW,
        )
    )

    class SyntheticAssistant:
        def __init__(self) -> None:
            self.generated = False

        def ingest_redacted(self, _message):  # type: ignore[no-untyped-def]
            return None

        def generate_ready_reply(self, *, now, on_turn_claimed):  # type: ignore[no-untyped-def]
            del now
            if self.generated:
                return None
            self.generated = True
            on_turn_claimed(
                SimpleNamespace(
                    store_id="store-001",
                    conversation_id="offline-conversation-001",
                    turn_id="turn-001",
                    messages=(1,),
                )
            )
            return SimpleNamespace(
                store_id="store-001",
                conversation_id="offline-conversation-001",
                turn_id="turn-001",
                decision_id="decision-001",
                request_id="request-001",
                customer_reference="sha256:" + "a" * 64,
                customer_question="合成客户问题",
                action="SUGGEST_REPLY",
                reply_content="合成 AI 建议，必须人工审核",
                risk_level=GatewayRiskLevel.LOW,
                citations=(),
                state="WAITING_APPROVAL",
            )

    result = AgentObservationWorker(
        store,
        SyntheticAssistant(),  # type: ignore[arg-type]
        stage=ObservationStage.AI_SUGGESTIONS,
        clock=lambda: NOW,
    ).run_once()

    snapshot = store.assistant_snapshot("offline-agent", "offline-device")
    assert result.observations_ingested == 1
    assert result.replies_generated == 1
    assert snapshot is not None
    assert snapshot.reply_content == "合成 AI 建议，必须人工审核"
    assert snapshot.safety.execution_count == 0
    assert snapshot.safety.send_count == 0
    assert store.poll_assistant_events("offline-agent", "offline-device")[-1].status == (
        "WAITING_APPROVAL"
    )
    engine.dispose()


def test_offline_replay_is_bounded_at_one_hundred_messages(tmp_path: Path) -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    messages = [
        {
            "message_id": f"stress-message-{sequence:03d}",
            "role": "customer",
            "content": f"合成压力消息 {sequence}",
            "timestamp": (NOW + timedelta(milliseconds=sequence)).isoformat(),
            "sequence": str(sequence),
        }
        for sequence in range(1, 101)
    ]
    capture = {**fixture.capture, "messages": messages}
    scan = {
        **fixture.scan,
        "conversations": [
            {
                **fixture.scan["conversations"][0],
                "unread_count": "100",
                "latest_sequence": "100",
            }
        ],
    }
    bounded = fixture.model_copy(update={"scan": scan, "capture": capture})
    port = ReplayPDDPageReadPort(bounded)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="synthetic-platform-store-001",
        evidence=build_replay_observer_evidence(bounded),
        page_port=port,
        clock=lambda: NOW,
    )
    spool = DurableEdgeSpool(
        tmp_path / "stress.sqlite3", PlainProtector(), clock=lambda: NOW
    )

    result = PDDMessageObserver(
        driver=driver,
        mapper=PDDWorkspaceObservationMapper(
            agent_id="offline-agent", device_id="offline-device"
        ),
        spool=spool,
        forward=PersistOnlyObservationForwarder(spool),
        stage=ObservationStage.MESSAGE_CAPTURE,
        clock=lambda: NOW,
    ).scan_once()

    assert result.observations_forwarded == 100
    assert len(spool.pending()) == 100
    assert port.pdd_network_requests == 0

    overflow = bounded.model_copy(
        update={"capture": {**capture, "messages": messages + [messages[-1]]}}
    )
    overflow_driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="synthetic-platform-store-001",
        evidence=build_replay_observer_evidence(overflow),
        page_port=ReplayPDDPageReadPort(overflow),
        clock=lambda: NOW,
    )
    with pytest.raises(PDDReadOnlyDriverError, match="safety limit"):
        overflow_driver.capture_conversation(overflow_driver.scan_conversations()[0])


def test_host_snapshot_retention_is_deterministic(tmp_path: Path) -> None:
    current = [NOW]
    engine, sessions = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'retention.sqlite3').as_posix()}"
    )
    create_schema(engine)
    store = AgentControlStore(sessions, clock=lambda: current[0])
    store.persist_assistant_snapshot(
        AgentAssistantSnapshot(
            agent_id="offline-agent",
            device_id="offline-device",
            store_id="store-001",
            conversation_id="offline-conversation-001",
            revision=1,
            status="WAITING_APPROVAL",
            turn_id="turn-001",
            decision_id="decision-001",
            request_id="request-001",
            customer_reference="sha256:" + "a" * 64,
            current_question="合成客户问题",
            action="SUGGEST_REPLY",
            reply_content="合成 AI 建议",
            risk_level="LOW",
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=30),
        )
    )
    current[0] = NOW + timedelta(minutes=31)

    assert store.assistant_snapshot("offline-agent", "offline-device") is None
    assert store.purge_expired()["snapshots"] == 1
    engine.dispose()
