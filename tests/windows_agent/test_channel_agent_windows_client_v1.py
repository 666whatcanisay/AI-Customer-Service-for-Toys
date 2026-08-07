from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import pytest

from channel_agent.client import AgentConnectionError
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import (
    AgentHeartbeatAck,
    AgentRegistrationResponse,
    AgentRuntimeStatus,
    ManagedAgentConfig,
)
from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_agent.logger import SafeAgentLogger
from channel_agent.runtime import ChannelAgentRuntime
from channel_agent.windows import (
    WINDOWS_CLIENT_VERSION,
    WindowsAgentHost,
    WindowsAutoStartManager,
    WindowsClientError,
    WindowsClientProcessStatus,
    check_upgrade_manifest,
)
from channel_agent.windows_app import _process_exists


NOW = datetime(2026, 8, 6, 14, 0, tzinfo=UTC)


class RecoveringChannelEngineClient:
    def __init__(self) -> None:
        self.register_count = 0
        self.heartbeat_count = 0
        self.closed = False
        self.config = ManagedAgentConfig(
            revision="windows-client-test-v1",
            heartbeat_interval_seconds=0.05,
        )

    def register(self, **_kwargs: object) -> AgentRegistrationResponse:
        self.register_count += 1
        return AgentRegistrationResponse(
            registration_id="agent-registration:windows-test",
            identity=AgentIdentity(
                agent_id="agent-windows-001",
                device_id="device-windows-001",
                status=AgentIdentityStatus.UNBOUND,
                created_at=NOW,
                updated_at=NOW,
            ),
            production_eligible=False,
            config=self.config,
            server_time=NOW,
        )

    def report_status(self, **_kwargs: object) -> AgentHeartbeatAck:
        self.heartbeat_count += 1
        if self.heartbeat_count == 1:
            raise AgentConnectionError("synthetic heartbeat outage")
        return AgentHeartbeatAck(
            identity_status=AgentIdentityStatus.UNBOUND,
            production_eligible=False,
            config_revision=self.config.revision,
            server_time=NOW,
        )

    def fetch_config(self) -> ManagedAgentConfig:
        return self.config

    def close(self) -> None:
        self.closed = True


def write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = ChannelAgentConfig(
        server_url="http://127.0.0.1:18080",
        agent_id="agent-windows-001",
        device_id="device-windows-001",
        heartbeat_interval_seconds=0.05,
        log_directory=Path("logs"),
    )
    path.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def test_windows_host_starts_heartbeats_recovers_and_stops(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    config_path = write_config(data_root / "config" / "agent.json")
    client = RecoveringChannelEngineClient()

    def factory(config: ChannelAgentConfig, *, log_path: str) -> ChannelAgentRuntime:
        return ChannelAgentRuntime(
            config,
            client,
            SafeAgentLogger(log_path),
            hostname="windows-service-pc",
            clock=lambda: NOW,
        )

    host = WindowsAgentHost(
        config_path,
        data_root,
        runtime_factory=factory,
        clock=lambda: NOW,
        poll_interval_seconds=0.02,
    )
    stop = Event()
    result: list[int] = []
    worker = Thread(target=lambda: result.append(host.run(stop)))
    worker.start()
    deadline = time.monotonic() + 2
    recovered = False
    while time.monotonic() < deadline:
        state = host.state_store.load()
        if (
            client.heartbeat_count >= 2
            and state.process_status is WindowsClientProcessStatus.RUNNING
            and state.last_heartbeat == NOW
        ):
            recovered = True
            break
        time.sleep(0.02)

    host.request_stop()
    worker.join(timeout=2)
    final = host.state_store.load()

    assert recovered is True
    assert client.register_count == 1
    assert client.heartbeat_count >= 2
    assert result == [0]
    assert final.process_status is WindowsClientProcessStatus.STOPPED
    assert final.runtime_status is AgentRuntimeStatus.STOPPED
    assert final.pid is None
    assert final.identity_status is AgentIdentityStatus.UNBOUND
    assert final.production_eligible is False
    assert client.closed is True


def test_autostart_enable_status_disable_is_credential_free(tmp_path: Path) -> None:
    manager = WindowsAutoStartManager(tmp_path / "startup")
    executable = tmp_path / "program" / "ChannelAgent.exe"
    data_root = tmp_path / "data"

    path = manager.enable(executable, data_root)
    content = path.read_text(encoding="utf-8-sig")

    assert manager.enabled is True
    assert "ChannelAgent.exe" in content
    assert "--data-root" in content
    for forbidden in ("cookie", "password", "secret", "token"):
        assert forbidden not in content.casefold()
    manager.disable()
    assert manager.enabled is False


def test_upgrade_check_is_read_only_and_semantic(tmp_path: Path) -> None:
    manifest = tmp_path / "upgrade.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1.2.0",
                "package_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )

    result = check_upgrade_manifest(manifest)

    assert result.current_version == WINDOWS_CLIENT_VERSION
    assert result.available_version == "1.2.0"
    assert result.update_available is True
    assert result.package_sha256 == "a" * 64
    manifest.write_text('{"version":"latest"}', encoding="utf-8")
    with pytest.raises(WindowsClientError):
        check_upgrade_manifest(manifest)


@pytest.mark.skipif(os.name != "nt", reason="Windows installer validation")
def test_installer_and_uninstaller_manage_program_and_data_layout(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    package = tmp_path / "package"
    (package / "app").mkdir(parents=True)
    (package / "config").mkdir()
    (package / "ChannelAgent.exe").write_bytes(b"synthetic-test-launcher")
    (package / "app" / "channel-agent.pyz").write_bytes(b"synthetic-test-app")
    (package / "config" / "agent.example.json").write_text(
        ChannelAgentConfig(
            server_url="http://127.0.0.1:18080",
            agent_id="agent-install-001",
            device_id="device-install-001",
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (package / "release-manifest.json").write_text(
        json.dumps({"version": WINDOWS_CLIENT_VERSION}),
        encoding="utf-8",
    )
    install_root = tmp_path / "installed" / "program"
    data_root = tmp_path / "installed" / "data"
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    install_script = root / "packaging" / "windows-client-v1" / "Install-AI-CS-Channel-Agent.ps1"
    uninstall_script = root / "packaging" / "windows-client-v1" / "Uninstall-AI-CS-Channel-Agent.ps1"

    installed = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(install_script),
            "-PackageRoot",
            str(package),
            "-InstallRoot",
            str(install_root),
            "-DataRoot",
            str(data_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert installed.returncode == 0, installed.stderr
    assert (install_root / "ChannelAgent.exe").is_file()
    assert (data_root / "config" / "agent.json").is_file()
    assert (data_root / "logs").is_dir()
    assert (data_root / "runtime" / "install-state.json").is_file()
    (install_root / "ChannelAgent.exe").unlink()
    uninstalled = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(uninstall_script),
            "-InstallRoot",
            str(install_root),
            "-DataRoot",
            str(data_root),
            "-RemoveData",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert uninstalled.returncode == 0, uninstalled.stderr
    assert install_root.exists() is False
    assert data_root.exists() is False


def test_windows_composition_contains_only_channel_agent_foundation() -> None:
    root = Path(__file__).resolve().parents[2]
    composition = json.loads(
        (root / "packaging" / "windows-client-v1" / "production-composition.json").read_text(
            encoding="utf-8"
        )
    )

    assert composition["release"].endswith(WINDOWS_CLIENT_VERSION)
    assert all(
        path.startswith("src/channel_agent/")
        for path in composition["source_allowlist"]
    )
    serialized = json.dumps(composition).casefold()
    assert "src/channel_engine/" not in serialized
    assert "src/ai_cs_agent/" not in serialized
    assert {"pdd", "browser-automation", "message-read", "message-send"}.issubset(
        composition["excluded"]
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows process validation")
def test_windows_process_detection_does_not_signal_process() -> None:
    assert _process_exists(os.getpid()) is True
    assert _process_exists(2_147_483_647) is False
