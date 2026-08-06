from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ai_cs_agent import cli
from ai_cs_agent.browser import BrowserError
from ai_cs_agent.gateway import GatewayAuthenticationFailed, GatewayUnavailable
from ai_cs_agent.models import AgentStatus, ExitCode, RuntimeState

from test_windows_agent_runtime import (
    AvailableBrowser,
    runtime_for,
    write_config,
)


class FailingGateway:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def health_check(self) -> None:
        raise self.error


class FailingBrowser(AvailableBrowser):
    def detect_chrome(self) -> Path:
        raise BrowserError("Chrome unavailable")


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (GatewayUnavailable("offline"), ExitCode.GATEWAY_UNREACHABLE),
        (
            GatewayAuthenticationFailed("invalid signature"),
            ExitCode.AUTHENTICATION_FAILED,
        ),
        (RuntimeError("unexpected runtime failure"), ExitCode.RUNTIME_ERROR),
    ],
)
def test_gateway_start_failures_have_stable_exit_codes(
    tmp_path: Path, failure: Exception, expected: ExitCode
) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config, FailingGateway(failure))

    assert runtime.run() == int(expected)
    state = runtime.status()
    assert state.agent_status is AgentStatus.FAILED
    assert state.exit_code == int(expected)


def test_invalid_configuration_returns_exit_code_1(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(
        home / "config" / "agent.json",
        safety={"kill_switch": True, "manual_approval": False, "auto_reply": False},
    )

    assert runtime_for(home, config).run() == int(ExitCode.CONFIG_ERROR)
    assert runtime_for(home, config).status().config["status"] == "INVALID"


def test_browser_environment_failure_returns_exit_code_5(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    runtime.browser_factory = lambda current_home, _config: FailingBrowser(current_home)

    assert runtime.run() == int(ExitCode.BROWSER_ERROR)
    assert runtime.status().browser["chrome_status"] == "UNAVAILABLE"


def test_normal_start_and_stop_return_exit_code_0(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    result: list[int] = []
    worker = threading.Thread(target=lambda: result.append(runtime.run()))
    worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if runtime.status().agent_status is AgentStatus.RUNNING:
            break
        time.sleep(0.01)
    runtime.request_stop()
    worker.join(timeout=2)

    assert result == [int(ExitCode.NORMAL)]
    assert runtime.status().agent_status is AgentStatus.STOPPED
    assert runtime.status().exit_code == int(ExitCode.NORMAL)


def test_start_command_propagates_child_failure_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)

    def fail_after_spawn(*_args: object, **_kwargs: object) -> object:
        state = runtime.status()
        state.agent_status = AgentStatus.FAILED
        state.exit_code = int(ExitCode.GATEWAY_UNREACHABLE)
        state.gateway = {"status": "GATEWAY_UNAVAILABLE", "reachable": False}
        state.last_error = {
            "code": "GATEWAYUNAVAILABLE",
            "message": "无法连接 AI-CS Gateway，请检查服务地址和服务状态。",
        }
        runtime.state_store.save(state)
        return object()

    monkeypatch.setattr(cli.subprocess, "Popen", fail_after_spawn)

    assert cli._start(runtime, config, 0.2) == int(ExitCode.GATEWAY_UNREACHABLE)
    assert "启动失败（退出码 2）" in capsys.readouterr().out


def test_status_reports_required_fields_and_gateway_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    runtime.state_store.save(
        RuntimeState(
            agent_status=AgentStatus.DEGRADED,
            exit_code=0,
            config={"status": "VALID"},
            gateway={
                "status": "GATEWAY_UNAVAILABLE",
                "reachable": False,
                "version": "UNKNOWN",
            },
            last_error={
                "code": "GATEWAYUNAVAILABLE",
                "message": "无法连接 AI-CS Gateway，请检查服务地址和服务状态。",
            },
        )
    )

    assert cli._status(runtime, False) == int(ExitCode.GATEWAY_UNREACHABLE)
    output = capsys.readouterr().out
    assert "版本:" in output
    assert "配置状态: VALID" in output
    assert "Agent 状态: DEGRADED" in output
    assert "Gateway 状态: GATEWAY_UNAVAILABLE" in output
    assert "Gateway 版本: UNKNOWN" in output
    assert "错误: 无法连接 AI-CS Gateway" in output


def test_status_returns_config_error_when_configuration_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "agent-home"
    runtime = runtime_for(home, home / "config" / "agent.json")

    assert cli._status(runtime, False) == int(ExitCode.CONFIG_ERROR)
    output = capsys.readouterr().out
    assert "配置状态: INVALID" in output
    assert "Agent 配置无效" in output

    write_config(home / "config" / "agent.json")
    assert cli._status(runtime, False) == int(ExitCode.NORMAL)
    assert "配置状态: VALID" in capsys.readouterr().out


def test_stop_command_returns_zero_after_safe_shutdown_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    runtime.state_store.save(RuntimeState(agent_status=AgentStatus.RUNNING, pid=12345))
    checks = iter((True, False))
    monkeypatch.setattr(cli, "_process_exists", lambda _pid: next(checks))

    assert cli._stop(runtime, 0.2) == int(ExitCode.NORMAL)
    assert runtime.stop_request.exists()
