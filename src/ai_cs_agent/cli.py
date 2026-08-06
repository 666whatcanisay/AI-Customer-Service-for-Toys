from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import ConfigError, load_config
from .models import AGENT_VERSION, AgentStatus, ExitCode, RuntimeState
from .runtime import AgentRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-cs-agent")
    parser.add_argument(
        "command",
        choices=("configure", "start", "run", "status", "stop", "kill-switch"),
    )
    parser.add_argument("action", nargs="?", choices=("enable", "disable"))
    parser.add_argument("--home", required=True)
    parser.add_argument("--config")
    parser.add_argument("--wait-seconds", type=float, default=15.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = Path(args.home).resolve()
    config = Path(args.config).resolve() if args.config else home / "config" / "agent.json"
    runtime = AgentRuntime(
        home,
        config,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    if args.command == "configure":
        return _configure(home, config)
    if args.command == "run":
        return runtime.run()
    if args.command == "start":
        return _start(runtime, config, args.wait_seconds)
    if args.command == "status":
        return _status(runtime, args.json)
    if args.command == "stop":
        return _stop(runtime, args.wait_seconds)
    if args.action is None:
        raise SystemExit("kill-switch requires enable or disable")
    state = runtime.set_kill_switch(args.action == "enable")
    print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _configure(home: Path, config_path: Path) -> int:
    print("AI-CS Channel Agent 安全配置（不会采集密码、Cookie、Token 或 Secret）")
    values = {
        "schema_version": "1.0",
        "agent": {
            "agent_id": _prompt("Agent ID", "agent-001"),
            "device_id": _prompt("Device ID", os.environ.get("COMPUTERNAME", "windows-node-001")),
            "customer_service_identity": _prompt("客服身份", os.environ.get("USERNAME", "operator")),
            "runtime_mode": _prompt("运行模式 STAGING/PILOT", "STAGING").upper(),
        },
        "server": {
            "address": _prompt("AI-CS Server", "http://127.0.0.1:18021"),
            "client_id": _prompt("Gateway Client ID", "channel-agent"),
            "key_id": _prompt("Gateway Key ID", "windows-rc-key"),
            "credential_reference": _prompt(
                "Windows 凭据引用", "wincred://AI-CS-Agent/Gateway/windows-rc-key"
            ),
            "timeout_seconds": 5.0,
        },
        "browser": {
            "chrome_path": None,
            "profile_directory": "runtime/browser-profile",
        },
        "safety": {
            "kill_switch": True,
            "manual_approval": True,
            "auto_reply": False,
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        from .config import load_config

        load_config(temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        print("配置校验失败，未保存。")
        return int(ExitCode.CONFIG_ERROR)
    os.replace(temporary, config_path)
    print(f"配置已保存：{config_path}")
    print("请在 Windows 凭据管理器中预置该引用，再运行 start。")
    return 0


def _prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _start(runtime: AgentRuntime, config: Path, wait_seconds: float) -> int:
    state = runtime.status()
    if state.pid and _process_exists(state.pid):
        print("AI-CS Agent 已在运行。")
        return int(ExitCode.NORMAL)
    runtime.prepare_start()
    runtime.home.joinpath("logs").mkdir(parents=True, exist_ok=True)
    command = _self_command() + [
        "run",
        "--home",
        str(runtime.home),
        "--config",
        str(config),
        "--heartbeat-seconds",
        str(runtime.heartbeat_seconds),
    ]
    stdout_path = runtime.home / "logs" / "agent-stdout.log"
    stderr_path = runtime.home / "logs" / "agent-stderr.log"
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
    try:
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            subprocess.Popen(
                command,
                cwd=runtime.home,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                close_fds=True,
                creationflags=creationflags,
            )
    except OSError:
        print("AI-CS Agent 启动失败：无法创建后台进程。")
        return int(ExitCode.RUNTIME_ERROR)
    deadline = time.monotonic() + max(wait_seconds, 0.1)
    while time.monotonic() < deadline:
        state = runtime.status()
        if state.agent_status in {AgentStatus.RUNNING, AgentStatus.READY}:
            print("AI-CS Agent 已启动并通过环境、配置、Gateway 与浏览器检查。")
            return int(ExitCode.NORMAL)
        if state.agent_status is AgentStatus.FAILED:
            _print_start_failure(state.exit_code, state.last_error)
            return _status_exit_code(state)
        time.sleep(0.1)
    print("AI-CS Agent 启动超时，请查看本地状态和事件日志。")
    return int(ExitCode.RUNTIME_ERROR)


def _status(runtime: AgentRuntime, as_json: bool) -> int:
    state = runtime.status()
    try:
        config = load_config(runtime.config_path)
        state.config = {
            "status": "VALID",
            "schema_version": config.schema_version,
            "runtime_mode": config.runtime_mode,
        }
        if (state.last_error or {}).get("code") == "CONFIGERROR" and (
            state.agent_status not in {AgentStatus.FAILED, AgentStatus.DEGRADED}
        ):
            state.last_error = None
            state.exit_code = int(ExitCode.NORMAL)
    except ConfigError:
        state.config = {"status": "INVALID"}
        state.exit_code = int(ExitCode.CONFIG_ERROR)
        state.last_error = {
            "code": "CONFIGERROR",
            "message": "Agent 配置无效，请检查配置页面或示例文件。",
        }
    runtime.state_store.save(state)
    if state.pid and not _process_exists(state.pid) and state.agent_status in {
        AgentStatus.RUNNING,
        AgentStatus.READY,
        AgentStatus.STARTING,
    }:
        state.agent_status = AgentStatus.DEGRADED
        state.last_error = {
            "code": "PROCESS_NOT_RUNNING",
            "message": "Agent 进程未运行，请重新启动。",
        }
        state.exit_code = int(ExitCode.RUNTIME_ERROR)
        runtime.state_store.save(state)
    exit_code = _status_exit_code(state)
    state.exit_code = exit_code
    if as_json:
        print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"版本: {state.agent_version or AGENT_VERSION}")
        print(f"配置状态: {state.config.get('status', 'UNKNOWN')}")
        print(f"Agent 状态: {state.agent_status.value}")
        print(f"Gateway 状态: {state.gateway.get('status', 'UNKNOWN')}")
        print(f"Gateway 版本: {state.gateway.get('version', 'UNKNOWN')}")
        print(f"Browser 状态: {state.browser.get('chrome_status', 'UNKNOWN')}")
        print(f"Session 状态: {state.session.get('status', 'UNKNOWN')}")
        print(
            "Kill Switch: "
            + ("ENABLED" if state.safety.get("kill_switch", True) else "DISABLED")
        )
        if state.last_error:
            print(f"错误: {state.last_error.get('message', '运行状态异常。')}")
    return exit_code


def _stop(runtime: AgentRuntime, wait_seconds: float) -> int:
    state = runtime.status()
    if not state.pid or not _process_exists(state.pid):
        print("AI-CS Agent 当前未运行。")
        return int(ExitCode.NORMAL)
    runtime.request_stop()
    deadline = time.monotonic() + max(wait_seconds, 0.1)
    while time.monotonic() < deadline:
        if not _process_exists(state.pid):
            print("AI-CS Agent 已正常停止。")
            return int(ExitCode.NORMAL)
        time.sleep(0.1)
    print("AI-CS Agent 未在安全时限内停止，请启用 Kill Switch 并联系管理员。")
    return int(ExitCode.RUNTIME_ERROR)


def _status_exit_code(state: RuntimeState) -> int:
    if state.config.get("status") == "INVALID":
        return int(ExitCode.CONFIG_ERROR)
    if state.agent_status not in {AgentStatus.FAILED, AgentStatus.DEGRADED}:
        return int(ExitCode.NORMAL)
    if state.exit_code in {int(code) for code in ExitCode if code is not ExitCode.NORMAL}:
        return int(state.exit_code)
    error_code = str((state.last_error or {}).get("code", "")).upper()
    gateway_status = str(state.gateway.get("status", "")).upper()
    if "CONFIG" in error_code:
        return int(ExitCode.CONFIG_ERROR)
    if gateway_status in {"AUTHENTICATION_FAILED", "AUTHORIZATION_DENIED"} or any(
        marker in error_code for marker in ("AUTHENTICATION", "CREDENTIAL")
    ):
        return int(ExitCode.AUTHENTICATION_FAILED)
    if gateway_status in {"GATEWAY_UNAVAILABLE", "UNAVAILABLE"} or "UNAVAILABLE" in error_code:
        return int(ExitCode.GATEWAY_UNREACHABLE)
    if state.browser.get("chrome_status") == "UNAVAILABLE" or "BROWSER" in error_code:
        return int(ExitCode.BROWSER_ERROR)
    return int(ExitCode.RUNTIME_ERROR)


def _print_start_failure(exit_code: int, last_error: dict[str, str] | None) -> None:
    message = (last_error or {}).get("message", "启动检查失败。")
    print(f"AI-CS Agent 启动失败（退出码 {exit_code}）：{message}")


def _self_command() -> list[str]:
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.suffix.casefold() == ".pyz":
        return [sys.executable, str(argv0)]
    return [sys.executable, "-m", "ai_cs_agent"]


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
