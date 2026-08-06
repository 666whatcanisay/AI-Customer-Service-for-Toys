from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from channel_engine.agent import (
    AgentBrowserConfig,
    AgentChannelConfig,
    AgentEnvironment,
    AgentSafetyConfig,
    AgentServerConfig,
    ChannelAgentConfig,
    ChannelAgentDashboardProjector,
    ChannelAgentService,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    StoreBinding,
)
from channel_engine.app import create_app
from channel_engine.config import Settings


class StepClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current += timedelta(seconds=1)
        return value


def _config(tmp_path, *, bound: bool = True) -> ChannelAgentConfig:
    binding = (
        StoreBinding(
            store_id="pdd-dashboard-store-001",
            store_name="Dashboard Fake Store",
            credential_reference="credential-ref://pdd/dashboard/store-001",
        )
        if bound
        else None
    )
    return ChannelAgentConfig(
        node_id="dashboard-agent-node",
        node_name="Dashboard Agent Node",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/dashboard/token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=(tmp_path / "chrome.exe").resolve(),
            profile_root=(tmp_path / "dedicated-profile").resolve(),
        ),
        channel=AgentChannelConfig(
            credential_reference=(
                binding.credential_reference if binding is not None else None
            ),
            store_binding=binding,
        ),
        safety=AgentSafetyConfig(
            runtime_mode=AgentEnvironment.PILOT,
            dry_run=True,
        ),
    )


def _service(
    tmp_path,
    *,
    bound: bool = True,
    browser_available: bool = True,
    server_available: bool = True,
) -> tuple[ChannelAgentConfig, ChannelAgentService]:
    config = _config(tmp_path, bound=bound)
    service = ChannelAgentService(
        config,
        FakeAgentServerConnector(available=server_available),
        FakeAgentBrowserController(available=browser_available),
        FakeAgentChannelRuntimeProbe(),
        clock=StepClock(),
    )
    return config, service


def test_dashboard_ui_renders_all_product_panels_without_send_controls(
    tmp_path,
) -> None:
    config, service = _service(tmp_path)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'dashboard-ui.sqlite3').as_posix()}"
        ),
        agent_service=service,
    )

    with TestClient(application) as client:
        response = client.get("/agent/ui")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "text/html" in response.headers["content-type"]
    for expected in (
        "渠道节点控制台",
        "店铺绑定",
        "Browser Runtime",
        "安全策略",
        "Runtime Timeline",
        "Pilot Mode",
        "Manual Approval",
        "Kill Switch",
        "启动节点",
        "停止节点",
        "/agent/dashboard",
    ):
        assert expected in response.text
    assert "data-testid=\"agent-status\"" in response.text
    assert "data-testid=\"store-state\"" in response.text
    assert "/send" not in response.text
    assert "/approve" not in response.text
    assert config.server.agent_token_reference not in response.text
    assert config.channel.credential_reference not in response.text


def test_dashboard_api_projects_runtime_store_browser_and_safety(tmp_path) -> None:
    config, service = _service(tmp_path)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'dashboard-api.sqlite3').as_posix()}"
        ),
        agent_service=service,
    )

    with TestClient(application) as client:
        initial = client.get("/agent/dashboard")
        client.post("/agent/start")
        running = client.get("/agent/dashboard")

    assert initial.status_code == 200
    assert initial.json()["agent"]["status"] == "STOPPED"
    assert initial.json()["browser"]["session"] == "NOT_STARTED"
    assert initial.json()["browser"]["login"] == "DISCONNECTED"
    payload = running.json()
    assert payload["dashboard_version"] == "1.0"
    assert payload["agent"] == {
        "agent_contract_version": "1.0",
        "status": "HEALTHY",
        "ready": True,
        "version": "1.0.0",
        "environment": "PILOT",
    }
    assert payload["node"]["status"] == "ONLINE"
    assert payload["ai_cs"]["connection"] == "CONNECTED"
    assert payload["browser"]["chrome_status"] == "HEALTHY"
    assert payload["browser"]["session"] == "ACTIVE"
    assert payload["browser"]["login"] == "AUTHENTICATED"
    assert payload["browser"]["profile"] == str(config.browser.profile_root)
    assert payload["channel"]["status"] == "HEALTHY"
    assert payload["store"]["state"] == "CONNECTED"
    assert payload["store"]["store_id"] == "pdd-dashboard-store-001"
    assert payload["safety"] == {
        "agent_contract_version": "1.0",
        "runtime_mode": "PILOT",
        "pilot_mode": True,
        "manual_approval": True,
        "kill_switch": False,
        "dry_run": True,
        "send_control_available": False,
    }
    assert payload["timeline"][0]["title"] == "节点就绪状态更新"
    assert payload["timeline"][0]["kind"] == "STATUS"
    serialized = running.text
    assert config.server.agent_token_reference not in serialized
    assert config.channel.credential_reference not in serialized


def test_dashboard_state_simulation_covers_waiting_login_errors_and_stop(
    tmp_path,
) -> None:
    _config_value, service = _service(tmp_path, browser_available=False)
    projector = ChannelAgentDashboardProjector(service, clock=StepClock())

    assert service.start().node.status.value == "DEGRADED"
    waiting = projector.snapshot()

    assert waiting.agent.status == "DEGRADED"
    assert waiting.store.state.value == "WAITING_LOGIN"
    assert waiting.browser.session.value == "DEGRADED"
    assert waiting.browser.login.value == "WAITING_LOGIN"
    assert any(item.kind.value == "ERROR" for item in waiting.timeline)
    assert any(
        item.reason_code == "AGENT_BROWSER_UNAVAILABLE"
        for item in waiting.timeline
    )

    service.stop()
    stopped = projector.snapshot()
    assert stopped.agent.status == "STOPPED"
    assert stopped.store.state.value == "DISCONNECTED"
    assert stopped.browser.session.value == "STOPPED"
    assert stopped.timeline[0].kind.value == "STOP"


def test_dashboard_unbound_and_server_offline_states_are_fail_closed(tmp_path) -> None:
    _config_value, service = _service(
        tmp_path,
        bound=False,
        server_available=False,
    )
    projector = ChannelAgentDashboardProjector(service, clock=StepClock())

    service.start()
    dashboard = projector.snapshot()

    assert dashboard.agent.status == "OFFLINE"
    assert dashboard.ai_cs.connection.value == "DISCONNECTED"
    assert dashboard.store.state.value == "DISCONNECTED"
    assert dashboard.channel.status.value == "BLOCKED"
    assert dashboard.safety.manual_approval is True
    assert dashboard.safety.send_control_available is False
