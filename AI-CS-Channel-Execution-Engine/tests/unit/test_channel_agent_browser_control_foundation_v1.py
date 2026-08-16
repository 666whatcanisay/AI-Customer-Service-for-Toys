from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

import pytest

import channel_agent.browser as browser_module

from channel_agent.browser import (
    BrowserDisabledError,
    BrowserNavigationError,
    BrowserSessionState,
    BrowserSessionStore,
    BrowserSessionStatus,
    BrowserStateError,
    ChannelAgentBrowserManager,
    WindowsBrowserProcessController,
    WindowsEdgeExecutableResolver,
)
from channel_agent.config import ChannelAgentConfig, load_agent_config
from channel_agent.contract import AgentRuntimeStatus
from channel_agent.identity import AgentIdentityStatus
from channel_agent.logger import SafeAgentLogger
from channel_agent.runtime import AgentRuntimeSnapshot
from channel_agent.windows import WindowsAgentHost, WindowsClientProcessStatus


NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def test_corrupt_browser_state_is_quarantined_without_touching_profile(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime" / "browser-sessions" / "agent.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(b"\x00" * 523)
    profile_marker = tmp_path / "browser" / "profiles" / "agent" / "edge" / "marker"
    profile_marker.parent.mkdir(parents=True)
    profile_marker.write_text("preserve", encoding="utf-8")

    assert BrowserSessionStore(state_path).load() is None
    assert not state_path.exists()
    quarantined = list((state_path.parent / "corrupt").glob("*.invalid"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"\x00" * 523
    assert profile_marker.read_text(encoding="utf-8") == "preserve"


class FakeResolver:
    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def resolve(self) -> Path:
        return self.executable


class FakeProcessController:
    def __init__(self) -> None:
        self.next_pid = 1100
        self.running: dict[int, bool] = {}
        self.starts: list[tuple[Path, Path, str]] = []
        self.navigations: list[str] = []
        self.stops: list[int] = []
        self.profile_pid: int | None = None
        self.finds = 0

    def start(self, executable: Path, profile_path: Path, url: str) -> int:
        self.next_pid += 1
        self.running[self.next_pid] = True
        self.starts.append((executable, profile_path, url))
        return self.next_pid

    def is_running(self, pid: int, executable: Path) -> bool:
        return self.running.get(pid, False)

    def find_running(self, executable: Path, profile_path: Path) -> int | None:
        self.finds += 1
        if self.profile_pid is None or not self.running.get(self.profile_pid, False):
            return None
        return self.profile_pid

    def stop(self, pid: int, executable: Path, timeout_seconds: float) -> bool:
        self.stops.append(pid)
        self.running[pid] = False
        return True

    def navigate(self, executable: Path, profile_path: Path, url: str) -> None:
        self.navigations.append(url)


class AdvancingClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        self.value += timedelta(seconds=1)
        return self.value


def make_manager(
    tmp_path: Path, *, enabled: bool = True
) -> tuple[ChannelAgentBrowserManager, FakeProcessController, SafeAgentLogger]:
    executable = tmp_path / "program" / "msedge.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"synthetic-edge")
    process = FakeProcessController()
    logger = SafeAgentLogger(tmp_path / "data" / "logs" / "browser.jsonl")
    manager = ChannelAgentBrowserManager(
        agent_id="agent-browser-001",
        data_root=tmp_path / "data",
        enabled=enabled,
        logger=logger,
        executable_resolver=FakeResolver(executable),  # type: ignore[arg-type]
        process_controller=process,
        clock=AdvancingClock(),
    )
    return manager, process, logger


def test_browser_config_is_default_off_and_requires_explicit_enable(tmp_path: Path) -> None:
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        json.dumps(
            {
                "config_version": "1.0",
                "server_url": "https://channel-engine.example",
                "agent_id": "agent-browser-001",
                "device_id": "device-browser-001",
            }
        ),
        encoding="utf-8",
    )

    assert load_agent_config(config_path).browser_enabled is False
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["browser_enabled"] = True
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_agent_config(config_path).browser_enabled is True


def test_disabled_browser_cannot_start_or_navigate(tmp_path: Path) -> None:
    manager, process, _logger = make_manager(tmp_path, enabled=False)
    try:
        with pytest.raises(BrowserDisabledError):
            manager.open_browser()
        with pytest.raises(BrowserDisabledError):
            manager.navigate("https://merchant.example/login")
        assert process.starts == []
        assert process.navigations == []
        assert (tmp_path / "data" / "browser" / "profiles").exists() is False
    finally:
        manager.close_resources()


def test_browser_lifecycle_uses_isolated_profile_and_waits_for_human_login(
    tmp_path: Path,
) -> None:
    manager, process, _logger = make_manager(tmp_path)
    try:
        opened = manager.open_browser()
        waiting = manager.navigate("https://merchant.example/login/customer-flow")
        status = manager.browser_status()
        stopped = manager.close_browser()

        assert opened.status is BrowserSessionStatus.OPENED
        assert waiting.status is BrowserSessionStatus.WAITING_LOGIN
        assert status.status is BrowserSessionStatus.WAITING_LOGIN
        assert stopped.status is BrowserSessionStatus.STOPPED
        assert stopped.pid is None
        assert process.starts[0][2] == "about:blank"
        assert process.navigations == ["https://merchant.example/login/customer-flow"]
        profile = Path(opened.profile_path)
        assert profile.is_relative_to((tmp_path / "data").resolve())
        assert (profile / ".ai-cs-channel-agent-profile.json").is_file()
        assert process.stops == [opened.pid]
    finally:
        manager.close_resources()


def test_agent_profiles_are_isolated_by_agent_identity(tmp_path: Path) -> None:
    logger_a = SafeAgentLogger(tmp_path / "logs" / "a.jsonl")
    logger_b = SafeAgentLogger(tmp_path / "logs" / "b.jsonl")
    executable = tmp_path / "msedge.exe"
    executable.write_bytes(b"edge")
    process = FakeProcessController()
    first = ChannelAgentBrowserManager(
        agent_id="agent-a",
        data_root=tmp_path / "data",
        enabled=True,
        logger=logger_a,
        executable_resolver=FakeResolver(executable),  # type: ignore[arg-type]
        process_controller=process,
        clock=AdvancingClock(),
    )
    second = ChannelAgentBrowserManager(
        agent_id="agent-b",
        data_root=tmp_path / "data",
        enabled=True,
        logger=logger_b,
        executable_resolver=FakeResolver(executable),  # type: ignore[arg-type]
        process_controller=process,
        clock=AdvancingClock(),
    )
    try:
        a = first.open_browser()
        b = second.open_browser()
        assert a.profile_path != b.profile_path
        assert Path(a.profile_path).is_relative_to((tmp_path / "data").resolve())
        assert Path(b.profile_path).is_relative_to((tmp_path / "data").resolve())
    finally:
        first.close_browser()
        second.close_browser()
        first.close_resources()
        second.close_resources()


def test_abnormal_exit_is_detected_and_recovered_once(tmp_path: Path) -> None:
    manager, process, _logger = make_manager(tmp_path)
    try:
        opened = manager.open_browser()
        assert opened.pid is not None
        process.running[opened.pid] = False

        degraded = manager.browser_status()
        recovered = manager.recover()
        assert degraded.status is BrowserSessionStatus.DEGRADED
        assert degraded.last_error_code == "BROWSER_PROCESS_EXITED"
        assert recovered.status is BrowserSessionStatus.OPENED
        assert recovered.browser_id == opened.browser_id
        assert recovered.generation == 2
        assert recovered.automatic_recovery_attempted is True
        assert recovered.pid != opened.pid

        assert recovered.pid is not None
        process.running[recovered.pid] = False
        assert manager.browser_status().status is BrowserSessionStatus.DEGRADED
        with pytest.raises(BrowserStateError):
            manager.recover()
    finally:
        manager.close_resources()


def test_degraded_status_poll_does_not_repeat_profile_process_discovery(
    tmp_path: Path,
) -> None:
    manager, process, _logger = make_manager(tmp_path)
    try:
        opened = manager.open_browser()
        assert opened.pid is not None
        process.running[opened.pid] = False

        degraded = manager.browser_status()
        finds_after_exit = process.finds
        polled_again = manager.browser_status()

        assert degraded.status is BrowserSessionStatus.DEGRADED
        assert polled_again.status is BrowserSessionStatus.DEGRADED
        assert process.finds == finds_after_exit
    finally:
        manager.close_resources()


def test_explicit_open_restarts_a_degraded_dedicated_browser(tmp_path: Path) -> None:
    manager, process, _logger = make_manager(tmp_path)
    try:
        opened = manager.open_browser()
        assert opened.pid is not None
        process.running[opened.pid] = False
        assert manager.browser_status().status is BrowserSessionStatus.DEGRADED

        restarted = manager.open_browser()

        assert restarted.status is BrowserSessionStatus.OPENED
        assert restarted.pid is not None
        assert restarted.pid != opened.pid
        assert len(process.starts) == 2
    finally:
        manager.close_resources()


def test_windows_profile_discovery_runs_without_a_visible_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "msedge.exe"
    executable.write_bytes(b"edge")
    profile = tmp_path / "profile"
    profile.mkdir()
    controller = WindowsBrowserProcessController()
    captured: dict[str, object] = {}

    monkeypatch.setattr(controller, "_require_windows", lambda _executable: None)

    def fake_run(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return type("Completed", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(browser_module.subprocess, "run", fake_run)

    assert controller.find_running(executable, profile) is None
    assert captured["creationflags"] == getattr(
        browser_module.subprocess, "CREATE_NO_WINDOW", 0
    )


def test_windows_edge_command_bypasses_system_proxy_once_and_keeps_url_last(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "msedge.exe"
    profile = tmp_path / "profile"
    url = "https://merchant.example/customer-service"

    command = WindowsBrowserProcessController._command(executable, profile, url)

    assert command[0] == str(executable)
    assert command[1] == f"--user-data-dir={profile}"
    assert command.count("--no-proxy-server") == 1
    assert "--remote-debugging-address=127.0.0.1" in command
    assert "--remote-debugging-port=0" in command
    assert command[-1] == url


def test_windows_start_and_navigate_share_proxy_bypass_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "msedge.exe"
    executable.write_bytes(b"edge")
    profile = tmp_path / "profile"
    profile.mkdir()
    controller = WindowsBrowserProcessController()
    commands: list[list[str]] = []

    monkeypatch.setattr(controller, "_require_windows", lambda _executable: None)

    class FakeProcess:
        pid = 40152

    def fake_popen(command: list[str], **_kwargs: object) -> FakeProcess:
        commands.append(command)
        return FakeProcess()

    monkeypatch.setattr(browser_module.subprocess, "Popen", fake_popen)

    assert controller.start(executable, profile, "https://merchant.example/login") == 40152
    controller.navigate(executable, profile, "https://merchant.example/chat")

    assert len(commands) == 2
    assert all(command.count("--no-proxy-server") == 1 for command in commands)
    assert commands[0][-1] == "https://merchant.example/login"
    assert commands[1][-1] == "https://merchant.example/chat"


def test_windows_profile_discovery_uses_devtools_listener_when_cim_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "msedge.exe"
    executable.write_bytes(b"edge")
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(
        "57744\n/devtools/browser/synthetic-id\n",
        encoding="utf-8",
    )
    controller = WindowsBrowserProcessController()
    calls: list[list[str]] = []

    monkeypatch.setattr(controller, "_require_windows", lambda _executable: None)
    monkeypatch.setattr(
        browser_module,
        "_windows_process_image",
        lambda pid: str(executable.resolve()) if pid == 40152 else None,
    )
    monkeypatch.setattr(
        controller,
        "_devtools_endpoint_matches",
        lambda port, path: port == 57744 and path == "/devtools/browser/synthetic-id",
    )

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        assert command[0] == "netstat.exe"
        return type(
            "Completed",
            (),
            {
                "stdout": (
                    "  TCP    127.0.0.1:57744    0.0.0.0:0    "
                    "LISTENING    40152\n"
                ),
                "returncode": 0,
            },
        )()

    monkeypatch.setattr(browser_module.subprocess, "run", fake_run)

    assert controller.find_running(executable, profile) == 40152
    assert len(calls) == 1


def test_windows_profile_discovery_rejects_stale_devtools_listener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "msedge.exe"
    executable.write_bytes(b"edge")
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(
        "57744\n/devtools/browser/stale-id\n",
        encoding="utf-8",
    )
    controller = WindowsBrowserProcessController()
    calls = 0

    monkeypatch.setattr(controller, "_require_windows", lambda _executable: None)
    monkeypatch.setattr(browser_module, "_windows_process_image", lambda _pid: None)
    monkeypatch.setattr(controller, "_devtools_endpoint_matches", lambda _port, _path: True)

    def fake_run(command: list[str], **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if command[0] == "netstat.exe":
            return type(
                "Completed",
                (),
                {
                    "stdout": (
                        "  TCP    127.0.0.1:57744    0.0.0.0:0    "
                        "LISTENING    40152\n"
                    ),
                    "returncode": 0,
                },
            )()
        return type("Completed", (), {"stdout": "", "returncode": 1})()

    monkeypatch.setattr(browser_module.subprocess, "run", fake_run)

    assert controller.find_running(executable, profile) is None
    assert calls == 2


def test_browser_status_reattaches_to_existing_agent_profile_process(
    tmp_path: Path,
) -> None:
    manager, process, logger = make_manager(tmp_path)
    log_path = logger.path
    try:
        opened = manager.open_browser()
        assert opened.pid is not None
        process.running[opened.pid] = False
        process.profile_pid = 2200
        process.running[2200] = True

        attached = manager.browser_status()

        assert attached.status is BrowserSessionStatus.OPENED
        assert attached.pid == 2200
        assert attached.last_error_code is None
        assert len(process.starts) == 1
        assert "BROWSER_PROCESS_REATTACHED" in log_path.read_text(encoding="utf-8")
    finally:
        manager.close_resources()


@pytest.mark.parametrize(
    "url",
    (
        "javascript:alert(1)",
        "http://merchant.example/login",
        "https://user:password@merchant.example/login",
        "https://merchant.example/login#token",
        "https://merchant.example/login?access_token=sensitive",
    ),
)
def test_navigation_fails_closed_for_unsafe_urls(tmp_path: Path, url: str) -> None:
    manager, process, _logger = make_manager(tmp_path)
    try:
        manager.open_browser()
        with pytest.raises(BrowserNavigationError):
            manager.navigate(url)
        assert process.navigations == []
    finally:
        manager.close_browser()
        manager.close_resources()


def test_browser_state_and_logs_do_not_persist_navigation_or_credentials(
    tmp_path: Path,
) -> None:
    manager, _process, logger = make_manager(tmp_path)
    log_path = logger.path
    try:
        opened = manager.open_browser()
        manager.navigate("https://merchant.example/private-customer-path")
        state_path = next(
            (tmp_path / "data" / "runtime" / "browser-sessions").glob("*.json")
        )
        state = BrowserSessionState.model_validate_json(state_path.read_bytes())
        public = state.public_view(tmp_path / "data")
        assert public["profile_reference"].startswith("browser/profiles/")
        assert public["contains_credentials"] is False
        serialized_state = state_path.read_text(encoding="utf-8").casefold()
        assert "private-customer-path" not in serialized_state
        assert state.browser_id == opened.browser_id
    finally:
        manager.close_browser()
        manager.close_resources()
    serialized_log = log_path.read_text(encoding="utf-8").casefold()
    assert "private-customer-path" not in serialized_log
    assert "password=" not in serialized_log
    assert "cookie=" not in serialized_log
    assert "token=" not in serialized_log


def test_browser_boundary_exposes_no_page_read_or_send_methods(tmp_path: Path) -> None:
    manager, _process, _logger = make_manager(tmp_path)
    try:
        for forbidden in (
            "read_messages",
            "capture_dom",
            "click_send",
            "send_message",
            "auto_login",
        ):
            assert hasattr(manager, forbidden) is False
    finally:
        manager.close_resources()


class FakeRuntime:
    def __init__(self, config: ChannelAgentConfig) -> None:
        self.config = config
        self.status = AgentRuntimeStatus.STOPPED

    def start(self, *, background_heartbeat: bool = True) -> AgentRuntimeSnapshot:
        self.status = AgentRuntimeStatus.ONLINE
        return self.snapshot()

    def stop(self) -> AgentRuntimeSnapshot:
        self.status = AgentRuntimeStatus.STOPPED
        return self.snapshot()

    def close(self) -> None:
        self.status = AgentRuntimeStatus.STOPPED

    def snapshot(self) -> AgentRuntimeSnapshot:
        return AgentRuntimeSnapshot(
            agent_id=self.config.agent_id,
            device_id=self.config.device_id,
            user_id=None,
            store_id=None,
            store_ids=(),
            binding_revision=0,
            identity=None,
            identity_status=AgentIdentityStatus.UNBOUND,
            production_eligible=False,
            version="1.2.0",
            hostname="customer-service-pc",
            status=self.status,
            registered=self.status is AgentRuntimeStatus.ONLINE,
            registration_id=None,
            config_revision=None,
            last_heartbeat=NOW if self.status is AgentRuntimeStatus.ONLINE else None,
            consecutive_failures=0,
            last_error_code=None,
        )


class FakeHostBrowser:
    def __init__(self, tmp_path: Path) -> None:
        self.opened = False
        self.closed = False
        self.resources_closed = False
        self.state = BrowserSessionState(
            browser_id="browser:host-test",
            agent_id="agent-browser-host",
            profile_path=str((tmp_path / "data" / "browser" / "profile").resolve()),
            status=BrowserSessionStatus.STOPPED,
            created_at=NOW,
            last_seen=NOW,
        )

    def open_browser(self) -> BrowserSessionState:
        self.opened = True
        self.state = self.state.model_copy(
            update={"status": BrowserSessionStatus.OPENED, "pid": 4242}
        )
        return self.state

    def close_browser(self) -> BrowserSessionState:
        self.closed = True
        self.state = self.state.model_copy(
            update={"status": BrowserSessionStatus.STOPPED, "pid": None}
        )
        return self.state

    def browser_status(self) -> BrowserSessionState:
        return self.state

    def recover(self) -> BrowserSessionState:
        return self.state

    def close_resources(self) -> None:
        self.resources_closed = True


def test_windows_host_syncs_browser_state_and_closes_with_agent(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config = ChannelAgentConfig(
        server_url="https://channel-engine.example",
        agent_id="agent-browser-host",
        device_id="device-browser-host",
        browser_enabled=True,
        heartbeat_interval_seconds=0.05,
    )
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    browser = FakeHostBrowser(tmp_path)
    host = WindowsAgentHost(
        config_path,
        data_root,
        runtime_factory=lambda value, **_kwargs: FakeRuntime(value),  # type: ignore[arg-type]
        browser_factory=lambda _value, _root: browser,  # type: ignore[arg-type]
        clock=lambda: NOW,
        poll_interval_seconds=0.02,
    )
    stop = Event()
    result: list[int] = []
    worker = Thread(target=lambda: result.append(host.run(stop)))
    worker.start()
    deadline = time.monotonic() + 2
    running = False
    while time.monotonic() < deadline:
        state = host.state_store.load()
        if (
            state.process_status is WindowsClientProcessStatus.RUNNING
            and state.browser_status is BrowserSessionStatus.OPENED
        ):
            running = True
            break
        time.sleep(0.02)
    host.request_stop()
    worker.join(timeout=2)
    final = host.state_store.load()

    assert running is True
    assert result == [0]
    assert browser.opened is True
    assert browser.closed is True
    assert browser.resources_closed is True
    assert final.process_status is WindowsClientProcessStatus.STOPPED
    assert final.browser_enabled is True
    assert final.browser_status is BrowserSessionStatus.STOPPED


def test_configuration_reload_preserves_running_browser_and_profile(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config = ChannelAgentConfig(
        server_url="https://channel-engine.example",
        agent_id="agent-browser-host",
        device_id="device-browser-host",
        browser_enabled=True,
        heartbeat_interval_seconds=0.05,
    )
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    browser = FakeHostBrowser(tmp_path)
    host = WindowsAgentHost(
        config_path,
        data_root,
        runtime_factory=lambda value, **_kwargs: FakeRuntime(value),  # type: ignore[arg-type]
        browser_factory=lambda _value, _root: browser,  # type: ignore[arg-type]
        clock=lambda: NOW,
        poll_interval_seconds=0.02,
    )
    stop = Event()
    result: list[int] = []
    worker = Thread(target=lambda: result.append(host.run(stop)))
    worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if browser.opened:
            break
        time.sleep(0.02)
    host.reload_request.parent.mkdir(parents=True, exist_ok=True)
    host.reload_request.write_text(
        json.dumps({"preserve_browser": True}), encoding="utf-8"
    )
    worker.join(timeout=2)
    final = host.state_store.load()

    assert result == [0]
    assert browser.opened is True
    assert browser.closed is False
    assert browser.resources_closed is True
    assert browser.state.status is BrowserSessionStatus.OPENED
    assert final.process_status is WindowsClientProcessStatus.STOPPED
    assert final.browser_enabled is True
    assert final.browser_status is BrowserSessionStatus.OPENED


@pytest.mark.skipif(
    os.name != "nt" or os.getenv("AI_CS_RUN_EDGE_SMOKE") != "1",
    reason="explicit isolated Edge smoke validation",
)
def test_real_windows_edge_start_status_and_close_with_isolated_profile(
    tmp_path: Path,
) -> None:
    logger = SafeAgentLogger(tmp_path / "data" / "logs" / "browser.jsonl")
    manager = ChannelAgentBrowserManager(
        agent_id="agent-edge-smoke",
        data_root=tmp_path / "data",
        enabled=True,
        logger=logger,
        executable_resolver=WindowsEdgeExecutableResolver(),
        process_controller=WindowsBrowserProcessController(),
    )
    try:
        opened = manager.open_browser()
        assert opened.status is BrowserSessionStatus.OPENED
        assert opened.pid is not None
        assert manager.browser_status().status is BrowserSessionStatus.OPENED
        stopped = manager.close_browser()
        assert stopped.status is BrowserSessionStatus.STOPPED
        assert stopped.pid is None
    finally:
        try:
            manager.close_browser()
        finally:
            manager.close_resources()
