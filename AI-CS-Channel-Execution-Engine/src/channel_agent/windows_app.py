from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from .binding import AgentBindingStore
from .browser import (
    BrowserControlError,
    BrowserDisabledError,
    BrowserSessionStatus,
    ChannelAgentBrowserManager,
)
from .client import (
    AgentClientError,
    AgentConnectionError,
    AgentProtocolError,
    AgentRejectedError,
    ChannelEngineClient,
)
from .config import AgentConfigError, load_agent_config
from .contract import AgentRuntimeStatus
from .logger import SafeAgentLogger
from .pdd_login import (
    PDDLoginObservationAdapter,
    PDDLoginObservationError,
    PDDLoginState,
)
from .onboarding import ChannelAgentOnboardingService, OnboardingWebServer
from .windows import (
    WINDOWS_CLIENT_VERSION,
    WindowsAgentHost,
    WindowsAutoStartManager,
    WindowsClientError,
    WindowsClientProcessStatus,
    WindowsClientState,
    WindowsStateError,
    WindowsStateStore,
    check_upgrade_manifest,
    default_data_root,
    default_startup_directory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ChannelAgent.exe")
    parser.add_argument(
        "command",
        choices=(
            "start",
            "setup",
            "run",
            "stop",
            "status",
            "version",
            "check-config",
            "autostart",
            "upgrade-check",
            "enroll",
            "binding-status",
            "browser-open",
            "browser-close",
            "browser-status",
            "browser-navigate",
            "pdd-login-open",
            "pdd-login-status",
        ),
    )
    parser.add_argument("action", nargs="?", choices=("enable", "disable", "status"))
    parser.add_argument("--data-root")
    parser.add_argument("--config")
    parser.add_argument("--startup-directory")
    parser.add_argument("--manifest")
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--binding-code-stdin", action="store_true")
    parser.add_argument("--url")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_root = Path(args.data_root).resolve() if args.data_root else default_data_root()
    config_path = (
        Path(args.config).resolve()
        if args.config
        else data_root / "config" / "agent.json"
    )
    host = WindowsAgentHost(config_path, data_root)
    if args.command == "version":
        print(WINDOWS_CLIENT_VERSION)
        return 0
    if args.command == "setup":
        return _setup(config_path, data_root)
    if args.command == "check-config":
        return _check_config(config_path)
    if args.command == "run":
        return _run(host)
    if args.command == "start":
        return _start(host, args.wait_seconds)
    if args.command == "stop":
        return _stop(host, args.wait_seconds)
    if args.command == "status":
        return _status(host.state_store, args.json)
    if args.command == "autostart":
        return _autostart(args, data_root)
    if args.command == "enroll":
        return _enroll(config_path, data_root, args.binding_code_stdin)
    if args.command == "binding-status":
        return _binding_status(data_root)
    if args.command.startswith("browser-"):
        return _browser_command(args.command, config_path, data_root, args.url)
    if args.command.startswith("pdd-login-"):
        return _pdd_login_command(args.command, config_path, data_root)
    return _upgrade_check(args.manifest)


def _check_config(config_path: Path) -> int:
    try:
        config = load_agent_config(config_path)
    except AgentConfigError:
        print("Channel Agent 配置无效，请检查配置文件。", file=sys.stderr)
        return 1
    print(json.dumps(config.public_view(), ensure_ascii=False, indent=2))
    return 0


def _setup(config_path: Path, data_root: Path) -> int:
    if config_path.is_file():
        print("Channel Agent 已完成首次连接配置。")
        return 0
    server: OnboardingWebServer | None = None
    try:
        service = ChannelAgentOnboardingService(
            data_root=data_root,
            config_path=config_path,
        )
        server = OnboardingWebServer(service)
        url = server.start(open_browser=True)
        print(f"首次连接向导已打开：{url}")
        print("发现主机后仍需输入连接码并人工确认，系统不会自动绑定。")
        while not config_path.is_file():
            time.sleep(0.25)
        time.sleep(0.5)
        print("首次连接配置完成。")
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("首次连接向导启动失败，请检查本机网络环境。", file=sys.stderr)
        return 4
    finally:
        if server is not None:
            server.stop()


def _run(host: WindowsAgentHost) -> int:
    stop_event = Event()

    def request_stop(_signum=None, _frame=None) -> None:  # type: ignore[no-untyped-def]
        stop_event.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        value = getattr(signal, name, None)
        if value is not None:
            signal.signal(value, request_stop)
    return host.run(stop_event)


def _start(host: WindowsAgentHost, wait_seconds: float) -> int:
    try:
        previous = host.state_store.load()
    except WindowsStateError:
        previous = WindowsClientState()
    if previous.pid and _process_exists(previous.pid):
        print("Channel Agent 已在运行。")
        return 0
    try:
        load_agent_config(host.config_path)
    except AgentConfigError:
        print("启动失败：Channel Agent 配置无效。", file=sys.stderr)
        return 1
    host.stop_request.unlink(missing_ok=True)
    command = _self_command() + [
        "run",
        "--data-root",
        str(host.data_root),
        "--config",
        str(host.config_path),
    ]
    logs = host.data_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
    try:
        with (logs / "client-stdout.log").open("ab") as stdout, (
            logs / "client-stderr.log"
        ).open("ab") as stderr:
            subprocess.Popen(
                command,
                cwd=host.data_root,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                close_fds=True,
                creationflags=flags,
            )
    except OSError:
        print("启动失败：无法创建 Channel Agent 后台进程。", file=sys.stderr)
        return 4
    deadline = time.monotonic() + max(wait_seconds, 0.1)
    while time.monotonic() < deadline:
        try:
            state = host.state_store.load()
        except WindowsStateError:
            time.sleep(0.1)
            continue
        if state.process_status is WindowsClientProcessStatus.RUNNING:
            print("Channel Agent 已启动。")
            return 0
        if state.process_status is WindowsClientProcessStatus.DEGRADED:
            if state.browser_enabled and state.browser_status in {
                BrowserSessionStatus.DEGRADED,
                BrowserSessionStatus.FAILED,
            }:
                print(
                    "Channel Agent 已启动，但浏览器运行环境不可用。",
                    file=sys.stderr,
                )
                return 5
            print(
                "Channel Agent 已启动，但 Channel Engine 暂不可用。",
                file=sys.stderr,
            )
            return 2
        if state.process_status is WindowsClientProcessStatus.FAILED:
            print("Channel Agent 启动失败。", file=sys.stderr)
            return 1 if state.config_status == "INVALID" else 4
        time.sleep(0.1)
    print("Channel Agent 启动超时。", file=sys.stderr)
    return 4


def _stop(host: WindowsAgentHost, wait_seconds: float) -> int:
    try:
        state = host.state_store.load()
    except WindowsStateError:
        print("Channel Agent 状态文件无效。", file=sys.stderr)
        return 4
    if not state.pid or not _process_exists(state.pid):
        _close_orphaned_browser(host.config_path, host.data_root)
        _save_stopped(host.state_store, state)
        print("Channel Agent 当前未运行。")
        return 0
    host.request_stop()
    deadline = time.monotonic() + max(wait_seconds, 0.1)
    while time.monotonic() < deadline:
        if not _process_exists(state.pid):
            latest = host.state_store.load()
            _save_stopped(host.state_store, latest)
            print("Channel Agent 已停止。")
            return 0
        time.sleep(0.1)
    print("Channel Agent 未在安全时限内停止。", file=sys.stderr)
    return 4


def _status(store: WindowsStateStore, as_json: bool) -> int:
    try:
        state = store.load()
    except WindowsStateError:
        print("Channel Agent 状态文件无效。", file=sys.stderr)
        return 4
    running = bool(state.pid and _process_exists(state.pid))
    if state.pid and not running and state.process_status in {
        WindowsClientProcessStatus.STARTING,
        WindowsClientProcessStatus.RUNNING,
        WindowsClientProcessStatus.DEGRADED,
    }:
        state = state.model_copy(
            update={
                "pid": None,
                "process_status": WindowsClientProcessStatus.FAILED,
                "last_error_code": "PROCESS_NOT_RUNNING",
                "updated_at": datetime.now(UTC),
            }
        )
        store.save(state)
    if as_json:
        print(state.model_dump_json(indent=2))
    else:
        print(f"客户端版本: {state.client_version}")
        print(f"Agent 状态: {state.process_status.value}")
        print(f"Runtime 状态: {state.runtime_status.value}")
        print(f"身份状态: {state.identity_status.value}")
        print(f"生产资格: {'是' if state.production_eligible else '否'}")
        print(f"Agent ID: {state.agent_id or '未配置'}")
        print(f"Device ID: {state.device_id or '未配置'}")
        print(f"客服端就绪状态: {state.experience_status.value}")
        print(
            "授权店铺: "
            + (", ".join(state.authorized_store_ids) or "尚未绑定")
        )
        print(f"当前工作店铺: {state.active_store_id or '尚未选择'}")
        print(f"Browser enabled: {'YES' if state.browser_enabled else 'NO'}")
        print(f"Browser status: {state.browser_status.value}")
        print(f"Browser ID: {state.browser_id or 'NOT_CREATED'}")
        print(
            "PDD login observation: "
            f"{'ENABLED' if state.pdd_login_observation_enabled else 'DISABLED'}"
        )
        print(
            "PDD login state: "
            f"{state.pdd_login_state.value if state.pdd_login_state else 'NOT_OBSERVED'}"
        )
        print(f"PDD store reference: {state.pdd_store_reference or 'NOT_CONFIRMED'}")
        print(f"Desktop UI: {state.desktop_ui_status}")
        print(f"Desktop UI URL: {state.desktop_ui_url or 'NOT_RUNNING'}")
    if state.config_status == "INVALID":
        return 1
    if state.process_status is WindowsClientProcessStatus.DEGRADED:
        if state.browser_enabled and state.browser_status in {
            BrowserSessionStatus.DEGRADED,
            BrowserSessionStatus.FAILED,
        }:
            return 5
        return 2
    if state.process_status is WindowsClientProcessStatus.FAILED:
        return 4
    return 0


def _autostart(args: argparse.Namespace, data_root: Path) -> int:
    if args.action is None:
        print("autostart 需要 enable、disable 或 status。", file=sys.stderr)
        return 1
    directory = (
        Path(args.startup_directory).resolve()
        if args.startup_directory
        else default_startup_directory()
    )
    manager = WindowsAutoStartManager(directory)
    if args.action == "enable":
        manager.enable(_launcher_executable(), data_root)
        print("Channel Agent Windows 自启动已启用。")
    elif args.action == "disable":
        manager.disable()
        print("Channel Agent Windows 自启动已关闭。")
    else:
        print("ENABLED" if manager.enabled else "DISABLED")
    return 0


def _upgrade_check(manifest: str | None) -> int:
    if manifest is None:
        print("upgrade-check 需要 --manifest。", file=sys.stderr)
        return 1
    try:
        result = check_upgrade_manifest(manifest)
    except WindowsClientError:
        print("升级清单无效。", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    return 0


def _enroll(config_path: Path, data_root: Path, code_from_stdin: bool) -> int:
    try:
        config = load_agent_config(config_path)
    except AgentConfigError:
        print("绑定失败：Channel Agent 配置无效。", file=sys.stderr)
        return 1
    binding_code = (
        _read_binding_code_from_stdin()
        if code_from_stdin
        else getpass.getpass("请输入一次性绑定码: ").strip()
    )
    if not binding_code:
        print("绑定失败：绑定码不能为空。", file=sys.stderr)
        return 3
    client = ChannelEngineClient(config)
    try:
        client.register(
            hostname=socket.gethostname().strip() or "unknown-host",
            status=AgentRuntimeStatus.STARTING,
            timestamp=datetime.now(UTC),
        )
        response = client.enroll(binding_code)
        binding = response.binding
        AgentBindingStore(
            data_root / "runtime" / "agent-binding.json"
        ).save(binding)
        state_store = WindowsStateStore(
            data_root / "runtime" / "channel-agent-state.json"
        )
        try:
            previous = state_store.load()
        except WindowsStateError:
            previous = WindowsClientState()
        state_store.save(
            previous.model_copy(
                update={
                    "identity_status": binding.identity_status,
                    "production_eligible": binding.production_eligible,
                    "agent_id": binding.agent_id,
                    "device_id": binding.device_id,
                    "user_id": binding.user_id,
                    "store_id": binding.store_ids[0] if binding.store_ids else None,
                    "store_ids": binding.store_ids,
                    "binding_revision": binding.binding_revision,
                    "config_status": "VALID",
                    "config_path": str(config_path),
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        print(binding.model_dump_json(indent=2))
        return 0
    except AgentConnectionError:
        print("绑定失败：无法连接 Channel Engine。", file=sys.stderr)
        return 2
    except AgentRejectedError:
        print("绑定失败：绑定码无效、过期或未获授权。", file=sys.stderr)
        return 3
    except (AgentProtocolError, AgentClientError, ValueError):
        print("绑定失败：Channel Engine 返回无效绑定结果。", file=sys.stderr)
        return 4
    finally:
        client.close()


def _read_binding_code_from_stdin() -> str:
    """Normalize Windows PowerShell 5.1 native-pipeline text safely."""
    return sys.stdin.readline().replace("\x00", "").lstrip("\ufeff").strip()


def _binding_status(data_root: Path) -> int:
    try:
        binding = AgentBindingStore(
            data_root / "runtime" / "agent-binding.json"
        ).load()
    except (OSError, ValueError):
        print("本地绑定状态无效。", file=sys.stderr)
        return 4
    if binding is None:
        print(json.dumps({"identity_status": "UNBOUND"}, ensure_ascii=False))
        return 0
    print(binding.model_dump_json(indent=2))
    return 0


def _browser_command(
    command: str,
    config_path: Path,
    data_root: Path,
    url: str | None,
) -> int:
    try:
        config = load_agent_config(config_path)
    except AgentConfigError:
        print("浏览器命令失败：Channel Agent 配置无效。", file=sys.stderr)
        return 1
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "browser-runtime.jsonl"),
    )
    try:
        if command == "browser-open":
            state = manager.open_browser()
        elif command == "browser-close":
            state = manager.close_browser()
        elif command == "browser-status":
            state = manager.browser_status()
        else:
            if not url:
                print("浏览器导航失败：必须提供 --url。", file=sys.stderr)
                return 1
            state = manager.navigate(url)
        print(json.dumps(state.public_view(data_root), ensure_ascii=False, indent=2))
        return 0
    except BrowserDisabledError:
        print(
            "浏览器控制未启用；请先将 browser_enabled 显式设置为 true。",
            file=sys.stderr,
        )
        return 5
    except BrowserControlError:
        print(
            "浏览器命令失败；未执行页面读取、登录或发送操作。",
            file=sys.stderr,
        )
        return 5
    finally:
        manager.close_resources()


def _pdd_login_command(command: str, config_path: Path, data_root: Path) -> int:
    try:
        config = load_agent_config(config_path)
    except AgentConfigError:
        print("PDD 登录观察失败：Channel Agent 配置无效。", file=sys.stderr)
        return 1
    if (
        not config.pdd_login_observation_enabled
        or config.pdd_login_url is None
        or config.pdd_customer_service_url is None
    ):
        print(
            "PDD 登录观察未启用；请显式启用 browser_enabled 和 "
            "pdd_login_observation_enabled。",
            file=sys.stderr,
        )
        return 5
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "browser-runtime.jsonl"),
    )
    observer = PDDLoginObservationAdapter(
        agent_id=config.agent_id,
        data_root=data_root,
        login_url=config.pdd_login_url,
        customer_service_url=config.pdd_customer_service_url,
        browser=manager,
        logger=SafeAgentLogger(data_root / "logs" / "pdd-login-observer.jsonl"),
    )
    try:
        observation = (
            observer.launch() if command == "pdd-login-open" else observer.observe()
        )
        print(json.dumps(observation.public_view(), ensure_ascii=False, indent=2))
        return 5 if observation.login_state is PDDLoginState.LOGIN_FAILED else 0
    except (BrowserControlError, PDDLoginObservationError):
        print(
            "PDD 登录观察失败；未执行自动登录、消息读取或页面写操作。",
            file=sys.stderr,
        )
        return 5
    finally:
        observer.close_resources()
        manager.close_resources()


def _close_orphaned_browser(config_path: Path, data_root: Path) -> None:
    try:
        config = load_agent_config(config_path)
    except AgentConfigError:
        return
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "browser-runtime.jsonl"),
    )
    try:
        manager.close_browser()
    except BrowserControlError:
        pass
    finally:
        manager.close_resources()


def _save_stopped(store: WindowsStateStore, state: WindowsClientState) -> None:
    store.save(
        state.model_copy(
            update={
                "pid": None,
                "process_status": WindowsClientProcessStatus.STOPPED,
                "runtime_status": AgentRuntimeStatus.STOPPED,
                "last_error_code": None,
                "updated_at": datetime.now(UTC),
            }
        )
    )


def _self_command() -> list[str]:
    return [sys.executable, str(Path(sys.argv[0]).resolve())]


def _launcher_executable() -> Path:
    candidate = Path(sys.argv[0]).resolve()
    if candidate.suffix.casefold() == ".exe":
        return candidate
    packaged = candidate.parent.parent / "ChannelAgent.exe"
    return packaged if packaged.exists() else candidate


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_exists(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _windows_process_exists(pid: int) -> bool:
    """Check a Windows PID without sending a signal to the process."""
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(synchronize, False, pid)
    if not handle:
        return False
    try:
        return wait_for_single_object(handle, 0) == wait_timeout
    finally:
        close_handle(handle)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
