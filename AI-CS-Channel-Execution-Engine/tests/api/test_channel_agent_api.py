from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.agent import (
    AgentBrowserConfig,
    AgentChannelConfig,
    AgentEnvironment,
    AgentSafetyConfig,
    AgentServerConfig,
    ChannelAgentConfig,
    ChannelAgentService,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    StoreBinding,
)
from channel_engine.app import create_app
from channel_engine.config import Settings


def _config(tmp_path, *, bound: bool = True) -> ChannelAgentConfig:
    binding = (
        StoreBinding(
            store_id="pdd-api-agent-store",
            store_name="PDD API Fake Store",
            credential_reference="secret-ref://pdd/agent/api-store",
        )
        if bound
        else None
    )
    return ChannelAgentConfig(
        node_id="channel-agent-api-node",
        node_name="Channel Agent API Node",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/agent/api-token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=(tmp_path / "fake-chrome.exe").resolve(),
            profile_root=(tmp_path / "agent-profile").resolve(),
        ),
        channel=AgentChannelConfig(store_binding=binding),
        safety=AgentSafetyConfig(
            runtime_mode=AgentEnvironment.MOCK,
            dry_run=True,
        ),
    )


def _service(config: ChannelAgentConfig) -> ChannelAgentService:
    return ChannelAgentService(
        config,
        FakeAgentServerConnector(),
        FakeAgentBrowserController(),
        FakeAgentChannelRuntimeProbe(),
    )


def test_local_management_api_start_check_stop_and_ui(tmp_path) -> None:
    config = _config(tmp_path)
    service = _service(config)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'agent-api.sqlite3').as_posix()}"
        ),
        agent_service=service,
    )

    with TestClient(application) as client:
        initial = client.get("/agent/status")
        health = client.get("/agent/health")
        ui = client.get("/agent/ui")
        started = client.post("/agent/start")
        checked = client.post("/agent/check")
        stopped = client.post("/agent/stop")

    assert initial.status_code == 200
    assert initial.json()["node"]["status"] == "INIT"
    assert health.status_code == 200
    assert health.json()["ready"] is False
    assert ui.status_code == 200
    assert "AI-CS Channel Agent" in ui.text
    assert "启动" in ui.text
    assert "停止" in ui.text
    assert "检查" in ui.text
    assert started.status_code == 200
    assert started.json()["node"]["status"] == "ONLINE"
    assert checked.json()["node"]["status"] == "ONLINE"
    assert stopped.json()["node"]["status"] == "STOPPED"
    serialized = "\n".join(
        [initial.text, health.text, started.text, checked.text, stopped.text, ui.text]
    )
    assert config.server.agent_token_reference not in serialized
    assert config.channel.store_binding is not None
    assert config.channel.store_binding.credential_reference not in serialized


def test_local_store_bind_and_unbind_api_supports_only_one_store(tmp_path) -> None:
    config = _config(tmp_path, bound=False)
    service = _service(config)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'agent-store-api.sqlite3').as_posix()}"
        ),
        agent_service=service,
    )
    payload = {
        "platform": "pdd",
        "store_id": "pdd-api-bound-store",
        "store_name": "PDD API Bound Fake Store",
        "credential_reference": "secret-ref://pdd/agent/api-bound-store",
        "status": "BOUND",
    }

    with TestClient(application) as client:
        initial = client.get("/agent/status")
        bound = client.put("/agent/store", json=payload)
        started = client.post("/agent/start")
        cannot_replace = client.put(
            "/agent/store",
            json={**payload, "store_id": "pdd-api-other-store"},
        )
        client.post("/agent/stop")
        unbound = client.delete("/agent/store")
        final = client.get("/agent/status")

    assert initial.json()["store_status"] == "UNBOUND"
    assert bound.status_code == 200
    assert bound.json()["store_status"] == "BOUND"
    assert started.json()["node"]["status"] == "ONLINE"
    assert cannot_replace.status_code == 409
    assert unbound.status_code == 204
    assert final.json()["store_status"] == "UNBOUND"


def test_agent_api_reads_authoritative_pdd_kill_switch(tmp_path) -> None:
    config = _config(tmp_path)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'agent-kill-api.sqlite3').as_posix()}"
        ),
        agent_config=config,
    )

    with TestClient(application) as client:
        application.state.pdd_safety.enable_kill_switch(
            operator="agent-api-operator",
            reason="AGENT_API_KILL_SWITCH_TEST",
        )
        started = client.post("/agent/start")
        health = client.get("/agent/health")

    assert started.status_code == 200
    assert started.json()["node"]["status"] == "DEGRADED"
    assert started.json()["kill_switch"] is True
    assert started.json()["channel_status"]["status"] == "BLOCKED"
    assert started.json()["channel_status"]["reason_code"] == (
        "AGENT_KILL_SWITCH_ENABLED"
    )
    assert health.json()["ready"] is False
