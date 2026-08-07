from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.client import ChannelEngineClient
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import AgentRuntimeStatus, ManagedAgentConfig
from channel_agent.logger import SafeAgentLogger
from channel_agent.runtime import ChannelAgentRuntime
from channel_engine.app import create_app
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.config import Settings


NOW = datetime(2026, 8, 6, 9, 30, tzinfo=UTC)


def test_channel_engine_application_exposes_agent_v1_router(tmp_path: Path) -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'channel-engine.sqlite3').as_posix()}"
        ),
        agent_node_registry=registry,
    )

    with TestClient(application) as client:
        response = client.get(
            "/channel-agent/v1/agents/unregistered-agent/config",
            params={"device_id": "unregistered-device"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "AGENT_NOT_REGISTERED"
    assert application.state.channel_agent_node_registry is registry


def test_agent_connects_to_versioned_channel_engine_api_and_receives_config(
    tmp_path: Path,
) -> None:
    managed = ManagedAgentConfig(
        revision="server-config-v1",
        heartbeat_interval_seconds=15.0,
    )
    registry = ChannelAgentNodeRegistry(managed_config=managed, clock=lambda: NOW)
    app = FastAPI()
    app.include_router(create_channel_agent_node_router(registry))
    transport = TestClient(app)
    config = ChannelAgentConfig(
        server_url="http://testserver",
        agent_id="agent-integration-001",
        device_id="device-integration-001",
        heartbeat_interval_seconds=0.05,
        log_directory=tmp_path / "logs",
    )
    client = ChannelEngineClient(config, http_client=transport)
    runtime = ChannelAgentRuntime(
        config,
        client,
        SafeAgentLogger(tmp_path / "logs" / "agent.jsonl"),
        hostname="service-desk-pc-01",
        clock=lambda: NOW,
    )

    online = runtime.start(background_heartbeat=False)
    heartbeat = runtime.heartbeat_once()

    assert online.status is AgentRuntimeStatus.ONLINE
    assert online.config_revision == "server-config-v1"
    assert heartbeat.last_heartbeat == NOW
    assert runtime.remote_config == managed
    assert runtime.remote_config.message_read_enabled is False
    assert runtime.remote_config.send_enabled is False
    assert runtime.remote_config.browser_automation_enabled is False
    record = registry.snapshot(config.agent_id)
    assert record is not None
    assert record.agent_id == config.agent_id
    assert record.device_id == config.device_id
    assert record.version == "1.1.1"
    assert record.hostname == "service-desk-pc-01"
    assert record.status == "ONLINE"
    assert record.last_heartbeat == NOW
    runtime.close()
    transport.close()


def test_registration_is_idempotent_and_device_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    app = FastAPI()
    app.include_router(create_channel_agent_node_router(registry))
    transport = TestClient(app)
    first_config = ChannelAgentConfig(
        server_url="http://testserver",
        agent_id="agent-idempotent-001",
        device_id="device-a",
        log_directory=tmp_path / "logs-a",
    )
    first = ChannelEngineClient(first_config, http_client=transport)

    one = first.register(
        hostname="pc-a",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )
    two = first.register(
        hostname="pc-a",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )

    assert one.registration_id == two.registration_id
    conflicting = transport.post(
        "/channel-agent/v1/agents/register",
        json={
            "protocol_version": "1.0",
            "agent_id": "agent-idempotent-001",
            "device_id": "device-b",
            "version": "1.0.0",
            "hostname": "pc-b",
            "status": "STARTING",
            "timestamp": NOW.isoformat(),
        },
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["code"] == "AGENT_DEVICE_BINDING_CONFLICT"
    transport.close()


def test_windows_entry_and_example_config_remain_foundation_only() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/windows/start_channel_agent_foundation.bat"
    example = root / "deploy/channel-agent-foundation/agent.example.json"
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    payload = json.loads(example.read_text(encoding="utf-8"))

    assert script.is_file()
    assert "python.exe\" -m channel_agent" in script.read_text(encoding="utf-8")
    assert "channel-agent-foundation = \"channel_agent.app:main\"" in pyproject
    assert set(payload) == {
        "config_version",
        "server_url",
        "agent_id",
        "device_id",
        "user_reference",
            "store_reference",
            "store_references",
        "connect_timeout_seconds",
        "heartbeat_interval_seconds",
        "log_directory",
    }
    serialized = json.dumps(payload).casefold()
    for forbidden in ("cookie", "password", "token", "pdd", "send_message"):
        assert forbidden not in serialized
