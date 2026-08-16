from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from channel_engine.agent import (
    AgentBrowserConfig,
    AgentChannelConfig,
    AgentEnvironment,
    AgentNodeStatus,
    AgentSafetyConfig,
    AgentServerConfig,
    ChannelAgentConfig,
    ChannelAgentFirstLaunchService,
    ChannelAgentService,
    DiscoveredStoreIdentity,
    DoctorCheckStatus,
    EnvironmentDoctor,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    FakeFirstLaunchBrowserPort,
    FakeFirstLaunchEnvironmentProbe,
    FakeFirstLaunchStoreIdentityProbe,
    FakeFirstLaunchWorkspacePort,
    FirstLaunchFailureCode,
    FirstLaunchLoginStatus,
    FirstLaunchSetupConfig,
    FirstLaunchState,
    FirstLaunchTransportStatus,
    StoreBinding,
)


class StepClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current += timedelta(minutes=1)
        return value


def _identity(
    store_id: str = "pdd-discovered-store-001",
    store_name: str = "玩趣乐园积木店",
) -> DiscoveredStoreIdentity:
    return DiscoveredStoreIdentity(
        store_id=store_id,
        store_name=store_name,
        account_identity="PDD merchant operator",
    )


def _agent_config(
    tmp_path: Path,
    *,
    environment: AgentEnvironment = AgentEnvironment.PILOT,
    kill_switch: bool = False,
    binding: StoreBinding | None = None,
) -> ChannelAgentConfig:
    return ChannelAgentConfig(
        node_id="EDY-PC-01",
        node_name="EDY-PC-01",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/first-launch/token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=(tmp_path / "chrome.exe").resolve(),
            profile_root=(tmp_path / "profiles").resolve(),
        ),
        channel=AgentChannelConfig(
            credential_reference=(
                binding.credential_reference if binding is not None else None
            ),
            store_binding=binding,
        ),
        safety=AgentSafetyConfig(
            runtime_mode=environment,
            dry_run=True,
            kill_switch=kill_switch,
        ),
    )


def _first_launch(
    tmp_path: Path,
    *,
    environment_probe: FakeFirstLaunchEnvironmentProbe | None = None,
    browser: FakeFirstLaunchBrowserPort | None = None,
    identity: DiscoveredStoreIdentity | None = None,
    environment: AgentEnvironment = AgentEnvironment.PILOT,
    kill_switch: bool = False,
    binding: StoreBinding | None = None,
):
    clock = StepClock()
    agent = ChannelAgentService(
        _agent_config(
            tmp_path,
            environment=environment,
            kill_switch=kill_switch,
            binding=binding,
        ),
        FakeAgentServerConnector(),
        FakeAgentBrowserController(),
        FakeAgentChannelRuntimeProbe(),
        clock=clock,
    )
    active_browser = browser or FakeFirstLaunchBrowserPort(clock=clock)
    store_probe = FakeFirstLaunchStoreIdentityProbe(identity)
    workspace = FakeFirstLaunchWorkspacePort(clock=clock)
    service = ChannelAgentFirstLaunchService(
        agent,
        FirstLaunchSetupConfig(),
        EnvironmentDoctor(
            environment_probe or FakeFirstLaunchEnvironmentProbe(),
            clock=clock,
        ),
        workspace,
        active_browser,
        store_probe,
        clock=clock,
    )
    return service, agent, active_browser, store_probe, workspace


def test_first_launch_state_machine_reaches_ready_without_configuration_input(
    tmp_path: Path,
) -> None:
    launch, agent, browser, store_probe, workspace = _first_launch(
        tmp_path,
        identity=_identity(),
        environment=AgentEnvironment.MOCK,
    )

    initial = launch.status()
    waiting = launch.start()
    browser.set_login(FirstLaunchLoginStatus.AUTHENTICATED)
    ready = launch.check_login()

    assert initial.state is FirstLaunchState.FIRST_START
    assert waiting.state is FirstLaunchState.WAITING_CHANNEL_LOGIN
    assert ready.state is FirstLaunchState.READY
    assert ready.state_history == (
        FirstLaunchState.FIRST_START,
        FirstLaunchState.CHECKING_ENVIRONMENT,
        FirstLaunchState.CONNECTING_SERVER,
        FirstLaunchState.WAITING_CHANNEL_LOGIN,
        FirstLaunchState.VERIFYING_STORE,
        FirstLaunchState.READY,
    )
    assert ready.progress_percent == 100
    assert ready.configuration_input_required is False
    assert ready.automatic_login is False
    assert ready.message_read_enabled is False
    assert ready.send_enabled is False
    assert ready.ready is not None
    assert ready.ready.node == "EDY-PC-01"
    assert ready.ready.store == "玩趣乐园积木店"
    assert ready.ready.browser == "CONNECTED"
    assert ready.ready.session == "VALID"
    assert ready.ready.channel == "READY"
    assert ready.ready.ai == "READY"
    assert ready.ready.safety == "PILOT MODE"
    assert ready.ready.approval == "REQUIRED"
    assert agent.status().node.status.value == "ONLINE"
    assert agent.status().node.environment is AgentEnvironment.PILOT
    assert workspace.create_count == 1
    assert browser.open_count == 1
    assert store_probe.discovery_count == 1
    assert store_probe.operator_identity_input_count == 0
    assert store_probe.cookie_access_count == 0
    assert store_probe.message_read_count == 0
    assert [event.kind.value for event in ready.timeline] == [
        "STARTUP",
        "ENVIRONMENT",
        "CONNECTION",
        "BROWSER",
        "LOGIN",
        "LOGIN",
        "STORE",
        "READY",
    ]
    timeline_text = "\n".join(
        f"{event.title} {event.detail}" for event in ready.timeline
    ).casefold()
    for forbidden in ("token", "cookie", "secret", str(tmp_path).casefold()):
        assert forbidden not in timeline_text


def test_environment_doctor_reports_pass_warning_and_blocked() -> None:
    warning_report = EnvironmentDoctor(
        FakeFirstLaunchEnvironmentProbe(
            profile_directory_ready=False,
            transport_status=FirstLaunchTransportStatus.WAITING_LOGIN,
            kill_switch_enabled=True,
        ),
        clock=StepClock(),
    ).check()
    blocked_report = EnvironmentDoctor(
        FakeFirstLaunchEnvironmentProbe(
            gateway_healthy=False,
            chrome_available=False,
        ),
        clock=StepClock(),
    ).check()

    assert warning_report.overall is DoctorCheckStatus.WARNING
    warning_by_id = {item.check_id: item for item in warning_report.checks}
    assert warning_by_id["PROFILE_DIRECTORY"].status is DoctorCheckStatus.WARNING
    assert warning_by_id["TRANSPORT_STATUS"].status is DoctorCheckStatus.WARNING
    assert warning_by_id["KILL_SWITCH"].status is DoctorCheckStatus.WARNING
    assert blocked_report.overall is DoctorCheckStatus.BLOCKED
    blocked_ids = {
        item.check_id
        for item in blocked_report.checks
        if item.status is DoctorCheckStatus.BLOCKED
    }
    assert {"GATEWAY_HEALTH", "CHROME"}.issubset(blocked_ids)


def test_gateway_failure_stops_before_workspace_or_browser(tmp_path: Path) -> None:
    launch, _agent, browser, _store, workspace = _first_launch(
        tmp_path,
        environment_probe=FakeFirstLaunchEnvironmentProbe(
            gateway_healthy=False,
            server_connected=False,
        ),
    )

    failed = launch.start()

    assert failed.state is FirstLaunchState.FAILED
    assert failed.failure is not None
    assert failed.failure.code is FirstLaunchFailureCode.GATEWAY_UNAVAILABLE
    assert failed.failure.title == "AI-CS 连接失败"
    assert "AI-CS" in failed.failure.action
    assert workspace.create_count == 0
    assert browser.open_count == 0


def test_chrome_failure_has_user_facing_recovery_without_stack(tmp_path: Path) -> None:
    browser = FakeFirstLaunchBrowserPort(clock=StepClock())
    browser.fail_open()
    launch, _agent, _browser, _store, _workspace = _first_launch(
        tmp_path,
        browser=browser,
    )

    failed = launch.start()

    assert failed.state is FirstLaunchState.FAILED
    assert failed.failure is not None
    assert failed.failure.code is FirstLaunchFailureCode.CHROME_UNAVAILABLE
    assert failed.failure.title == "Chrome 启动失败"
    assert "Traceback" not in failed.model_dump_json()
    assert failed.can_reset is True


def test_waiting_login_is_stable_and_does_not_discover_store(tmp_path: Path) -> None:
    launch, _agent, browser, store_probe, _workspace = _first_launch(
        tmp_path,
        identity=_identity(),
    )

    launch.start()
    waiting = launch.check_login()
    reopened = launch.reopen_browser()

    assert waiting.state is FirstLaunchState.WAITING_CHANNEL_LOGIN
    assert waiting.browser.chrome.value == "OPEN"
    assert waiting.browser.login.value == "WAITING"
    assert waiting.browser.automatic_login_performed is False
    assert waiting.browser.message_read_performed is False
    assert waiting.browser.send_performed is False
    assert reopened.state is FirstLaunchState.WAITING_CHANNEL_LOGIN
    assert browser.open_count == 2
    assert store_probe.discovery_count == 0


def test_store_mismatch_preserves_existing_binding_and_stops(tmp_path: Path) -> None:
    existing = StoreBinding(
        store_id="pdd-expected-store",
        store_name="Expected Store",
        credential_reference="credential-ref://pdd/expected-store",
    )
    launch, agent, browser, _store, _workspace = _first_launch(
        tmp_path,
        binding=existing,
        identity=_identity("pdd-other-store", "Other Store"),
    )

    launch.start()
    browser.set_login(FirstLaunchLoginStatus.AUTHENTICATED)
    failed = launch.check_login()

    assert failed.state is FirstLaunchState.FAILED
    assert failed.failure is not None
    assert failed.failure.code is FirstLaunchFailureCode.STORE_MISMATCH
    assert agent.status().store_id == "pdd-expected-store"
    assert agent.status().node.status in {
        AgentNodeStatus.INIT,
        AgentNodeStatus.STOPPED,
    }


def test_login_failure_requests_new_manual_scan(tmp_path: Path) -> None:
    launch, _agent, browser, store_probe, _workspace = _first_launch(tmp_path)
    launch.start()
    browser.set_login(FirstLaunchLoginStatus.FAILED)

    failed = launch.check_login()

    assert failed.failure is not None
    assert failed.failure.code is FirstLaunchFailureCode.LOGIN_FAILED
    assert "人工扫码" in failed.failure.action
    assert store_probe.discovery_count == 0


def test_kill_switch_allows_diagnosis_but_blocks_ready(tmp_path: Path) -> None:
    launch, agent, browser, _store, _workspace = _first_launch(
        tmp_path,
        environment_probe=FakeFirstLaunchEnvironmentProbe(
            kill_switch_enabled=True,
        ),
        identity=_identity(),
        kill_switch=True,
    )

    waiting = launch.start()
    browser.set_login(FirstLaunchLoginStatus.AUTHENTICATED)
    failed = launch.check_login()

    assert waiting.doctor is not None
    assert waiting.doctor.overall is DoctorCheckStatus.WARNING
    assert failed.state is FirstLaunchState.FAILED
    assert failed.failure is not None
    assert failed.failure.code is FirstLaunchFailureCode.KILL_SWITCH_ENABLED
    assert agent.status().node.status is AgentNodeStatus.INIT
    assert failed.send_enabled is False


def test_ready_reset_stops_agent_and_removes_only_wizard_binding(
    tmp_path: Path,
) -> None:
    launch, agent, browser, _store, _workspace = _first_launch(
        tmp_path,
        identity=_identity(),
    )
    launch.start()
    browser.set_login(FirstLaunchLoginStatus.AUTHENTICATED)
    assert launch.check_login().state is FirstLaunchState.READY

    reset = launch.reset()

    assert reset.state is FirstLaunchState.FIRST_START
    assert reset.state_history == (FirstLaunchState.FIRST_START,)
    assert reset.timeline[-1].kind.value == "RESET"
    assert agent.status().node.status is AgentNodeStatus.STOPPED
    assert agent.status().store_id is None
    assert browser.close_count == 1
