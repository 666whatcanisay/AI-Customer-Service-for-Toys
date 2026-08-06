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
    ChannelAgentFirstLaunchService,
    ChannelAgentService,
    DiscoveredStoreIdentity,
    EnvironmentDoctor,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    FakeFirstLaunchBrowserPort,
    FakeFirstLaunchEnvironmentProbe,
    FakeFirstLaunchStoreIdentityProbe,
    FakeFirstLaunchWorkspacePort,
    FirstLaunchLoginStatus,
    FirstLaunchSetupConfig,
)
from channel_engine.app import create_app
from channel_engine.config import Settings


class StepClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 17, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current += timedelta(minutes=1)
        return value


def _runtime(tmp_path):
    clock = StepClock()
    config = ChannelAgentConfig(
        node_id="EDY-PC-01",
        node_name="EDY-PC-01",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/first-launch/api-token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=(tmp_path / "chrome.exe").resolve(),
            profile_root=(tmp_path / "profiles").resolve(),
        ),
        channel=AgentChannelConfig(),
        safety=AgentSafetyConfig(
            runtime_mode=AgentEnvironment.PILOT,
            dry_run=True,
        ),
    )
    agent = ChannelAgentService(
        config,
        FakeAgentServerConnector(),
        FakeAgentBrowserController(),
        FakeAgentChannelRuntimeProbe(),
        clock=clock,
    )
    browser = FakeFirstLaunchBrowserPort(clock=clock)
    store = FakeFirstLaunchStoreIdentityProbe(
        DiscoveredStoreIdentity(
            store_id="pdd-first-launch-api-store",
            store_name="玩趣乐园积木店",
            account_identity="PDD merchant operator",
        )
    )
    setup = FirstLaunchSetupConfig(
        credential_reference="credential-ref://pdd/first-launch/api-session"
    )
    first_launch = ChannelAgentFirstLaunchService(
        agent,
        setup,
        EnvironmentDoctor(FakeFirstLaunchEnvironmentProbe(), clock=clock),
        FakeFirstLaunchWorkspacePort(clock=clock),
        browser,
        store,
        clock=clock,
    )
    app = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'first-launch-api.sqlite3').as_posix()}"
        ),
        agent_service=agent,
        first_launch_service=first_launch,
    )
    return app, agent, first_launch, browser, setup


def test_first_launch_ui_and_api_complete_fake_ready_flow(tmp_path) -> None:
    app, _agent, _first_launch, browser, setup = _runtime(tmp_path)

    with TestClient(app) as client:
        home_before = client.get("/agent", follow_redirects=False)
        ui = client.get("/agent/first-launch/ui")
        initial = client.get("/agent/first-launch/status")
        doctor = client.get("/agent/first-launch/doctor")
        waiting = client.post("/agent/first-launch/start")
        still_waiting = client.post("/agent/first-launch/login/check")
        browser.set_login(FirstLaunchLoginStatus.AUTHENTICATED)
        ready = client.post("/agent/first-launch/login/check")
        home_after = client.get("/agent", follow_redirects=False)
        dashboard = client.get("/agent/dashboard")

    assert home_before.status_code == 307
    assert home_before.headers["location"] == "/agent/first-launch/ui"
    assert ui.status_code == 200
    assert ui.headers["cache-control"] == "no-store"
    for text in (
        "第一次启动",
        "一步一步来。",
        "Environment Doctor",
        "拼多多商家聊天",
        "重新打开浏览器",
        "检查登录状态",
        "人工扫码登录",
        "/agent/first-launch/start",
    ):
        assert text in ui.text
    assert "<input" not in ui.text
    assert "/send" not in ui.text
    assert "/messages" not in ui.text
    assert "/approve" not in ui.text
    assert initial.json()["state"] == "FIRST_START"
    assert initial.json()["configuration_input_required"] is False
    assert doctor.status_code == 200
    assert doctor.json()["overall"] == "WARNING"
    assert waiting.json()["state"] == "WAITING_CHANNEL_LOGIN"
    assert waiting.json()["browser"]["chrome"] == "OPEN"
    assert waiting.json()["browser"]["login"] == "WAITING"
    assert waiting.json()["browser"]["session"] == "PENDING"
    assert waiting.json()["browser"]["automatic_login_performed"] is False
    assert waiting.json()["browser"]["message_read_performed"] is False
    assert waiting.json()["browser"]["send_performed"] is False
    assert still_waiting.json()["state"] == "WAITING_CHANNEL_LOGIN"
    assert ready.status_code == 200
    assert ready.json()["state"] == "READY"
    assert ready.json()["ready"]["store"] == "玩趣乐园积木店"
    assert ready.json()["ready"]["approval"] == "REQUIRED"
    assert home_after.headers["location"] == "/agent/ui"
    assert dashboard.json()["store"]["state"] == "CONNECTED"
    serialized = "\n".join(
        [ui.text, initial.text, doctor.text, waiting.text, ready.text]
    )
    assert setup.credential_reference not in serialized
    assert "api-token" not in serialized


def test_first_launch_api_rejects_out_of_order_action_with_friendly_problem(
    tmp_path,
) -> None:
    app, _agent, _launch, _browser, _setup = _runtime(tmp_path)

    with TestClient(app) as client:
        response = client.post("/agent/first-launch/login/check")

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "FIRST_LAUNCH_ACTION_UNAVAILABLE",
            "message": "当前步骤不能执行此操作。",
        }
    }
    assert "Traceback" not in response.text
