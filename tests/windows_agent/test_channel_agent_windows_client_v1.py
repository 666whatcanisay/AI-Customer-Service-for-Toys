from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import pytest

import channel_agent.binding as binding_module
import channel_agent.windows as windows_module
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
    WindowsClientState,
    WindowsStateStore,
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
    recovered = False
    try:
        deadline = time.monotonic() + 2
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
    finally:
        host.request_stop()
        worker.join(timeout=2)
    assert worker.is_alive() is False
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
    assert "AI_CS_CHANNEL_AGENT_DATA_ROOT" in content
    assert "--background" in content
    for forbidden in ("cookie", "password", "secret", "token"):
        assert forbidden not in content.casefold()
    manager.disable()
    assert manager.enabled is False


def test_windows_state_store_retries_transient_replace_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WindowsStateStore(tmp_path / "runtime" / "state.json")
    original = binding_module._atomic_replace
    attempts = 0

    def transient_replace(source: str | Path, target: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("synthetic Windows sharing violation")
        original(source, target)

    monkeypatch.setattr(binding_module, "_atomic_replace", transient_replace)
    store.save(WindowsClientState(process_status=WindowsClientProcessStatus.STARTING))

    assert attempts == 3
    assert store.load().process_status is WindowsClientProcessStatus.STARTING


def test_windows_state_store_retries_transient_read_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WindowsStateStore(tmp_path / "runtime" / "state.json")
    store.save(WindowsClientState(process_status=WindowsClientProcessStatus.RUNNING))
    original = Path.read_bytes
    attempts = 0

    def transient_read(path: Path) -> bytes:
        nonlocal attempts
        if path == store.path:
            attempts += 1
            if attempts < 3:
                raise PermissionError("synthetic Windows sharing violation")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", transient_read)

    assert store.load().process_status is WindowsClientProcessStatus.RUNNING
    assert attempts == 3


def test_windows_state_store_reports_permanent_read_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WindowsStateStore(tmp_path / "runtime" / "state.json")
    store.save(WindowsClientState())
    original = Path.read_bytes

    def locked_read(path: Path) -> bytes:
        if path == store.path:
            raise PermissionError("synthetic permanent Windows sharing violation")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", locked_read)
    monkeypatch.setattr(windows_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(windows_module.WindowsStateError) as caught:
        store.load()

    assert caught.value.error_code == "LOCAL_STATE_TEMPORARILY_LOCKED"


def test_windows_state_store_invalid_and_oversized_files_fail_closed(
    tmp_path: Path,
) -> None:
    store = WindowsStateStore(tmp_path / "runtime" / "state.json")
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(windows_module.WindowsStateError) as invalid:
        store.load()
    assert invalid.value.error_code == "LOCAL_STATE_INVALID"

    store.path.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(windows_module.WindowsStateError) as oversized:
        store.load()
    assert oversized.value.error_code == "LOCAL_STATE_TOO_LARGE"


def test_windows_state_store_concurrent_reads_and_writes_are_atomic(
    tmp_path: Path,
) -> None:
    store = WindowsStateStore(tmp_path / "runtime" / "state.json")
    store.save(WindowsClientState())
    failures: list[BaseException] = []

    def writer() -> None:
        try:
            for revision in range(100):
                store.save(
                    WindowsClientState(
                        binding_revision=revision,
                        process_status=WindowsClientProcessStatus.RUNNING,
                    )
                )
        except BaseException as exc:  # pragma: no cover - assertion captures thread errors
            failures.append(exc)

    def reader() -> None:
        try:
            for _ in range(150):
                state = store.load()
                assert state.binding_revision >= 0
        except BaseException as exc:  # pragma: no cover - assertion captures thread errors
            failures.append(exc)

    threads = [Thread(target=writer), Thread(target=reader), Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(thread.is_alive() is False for thread in threads)
    assert failures == []
    assert store.load().binding_revision == 99


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell 5.1 encoding validation")
def test_shortcut_name_is_stable_under_windows_powershell_51() -> None:
    root = Path(__file__).resolve().parents[2]
    helper = (
        root
        / "packaging"
        / "windows-client-v1"
        / "ChannelAgentShortcutName.ps1"
    )
    powershell = (
        Path(os.environ["SystemRoot"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    command = (
        f". '{helper}'; "
        "$name=Get-ChannelAgentShortcutName; "
        "($name.ToCharArray() | ForEach-Object {[int]$_}) -join ','"
    )

    completed = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == ",".join(
        str(ord(character)) for character in "AI-CS 客服助手.lnk"
    )


def test_windows_release_scripts_with_non_ascii_text_have_utf8_bom() -> None:
    root = Path(__file__).resolve().parents[2]
    scripts = (
        root / "packaging" / "windows-client-v1" / "Install-AI-CS-Channel-Agent.ps1",
        root / "packaging" / "windows-client-v1" / "Uninstall-AI-CS-Channel-Agent.ps1",
        root / "scripts" / "build_channel_agent_windows_client.ps1",
        root / "scripts" / "upgrade_channel_agent_brand_only.ps1",
        root / "scripts" / "build_channel_agent_rc3.ps1",
        root / "scripts" / "upgrade_channel_agent_rc3.ps1",
    )
    for script in scripts:
        payload = script.read_bytes()
        text = payload.decode("utf-8-sig")
        if any(ord(character) > 127 for character in text):
            assert payload.startswith(b"\xef\xbb\xbf"), script


def test_upgrade_check_is_read_only_and_semantic(tmp_path: Path) -> None:
    manifest = tmp_path / "upgrade.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "package_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )

    result = check_upgrade_manifest(manifest)

    assert result.current_version == WINDOWS_CLIENT_VERSION
    assert result.available_version == "2.0.0"
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
    assert not (data_root / "config" / "agent.json").exists()
    assert (data_root / "logs").is_dir()
    assert (data_root / "runtime" / "install-state.json").is_file()
    install_state = json.loads(
        (data_root / "runtime" / "install-state.json").read_text(encoding="utf-8-sig")
    )
    assert install_state["first_launch_required"] is True
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
        (root / "packaging" / "windows-client-v2" / "production-composition.json").read_text(
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
    assert {
        "Fake",
        "Sandbox",
        "Discovery",
        "Pilot",
        "real-pdd-send",
        "auto-reply",
    }.issubset(
        composition["excluded"]
    )


def test_windows_launcher_opens_local_assistant_even_when_agent_is_degraded() -> None:
    root = Path(__file__).resolve().parents[2]
    launcher = (
        root / "packaging" / "windows-client-v1" / "ChannelAgentLauncher.cs"
    ).read_text(encoding="utf-8-sig")

    assert "openWhenReady && DesktopAssistantAvailable()" in launcher
    assert "openWhenReady && status == \"RUNNING\"" not in launcher
    assert "RequestFreshWorkspaceUrl(runtime)" in launcher
    assert 'JsonValue(runtime, "launcher_url")' in launcher
    assert 'request.Headers["X-Channel-Agent-Launcher"]' in launcher
    assert 'endpoint.AbsolutePath != "/launcher-api/v1/open"' in launcher
    assert 'new Uri(launcherEndpoint, "/launcher-api/v1/pdd/open")' in launcher
    assert 'request.Headers["X-Channel-Agent-Intent"] = "HUMAN_REQUESTED_PDD_WINDOW"' in launcher
    assert 'new[] { "pdd-login-open"' not in launcher
    assert '"preserve-assistant"' in launcher
    assert '"desktop-bootstrap-handoff-consumed.json"' in launcher
    assert '"preserve-assistant-on-launch.request"' in launcher
    assert "DateTime.UtcNow.AddSeconds(15)" in launcher
    assert "waitingForAssistantRecovery" in launcher


def test_failed_reloaded_config_rolls_back_once_without_touching_identity_data(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    config_path = write_config(data_root / "config" / "agent.json")
    previous = ChannelAgentConfig.model_validate_json(config_path.read_bytes())
    backup = data_root / "runtime" / "config-backups" / "agent.previous.json"
    backup.parent.mkdir(parents=True)
    backup.write_text(previous.model_dump_json(indent=2), encoding="utf-8")
    changed = previous.model_copy(update={"heartbeat_interval_seconds": 99.0})
    config_path.write_text(changed.model_dump_json(indent=2), encoding="utf-8")
    pending = data_root / "runtime" / "config-reload-pending.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text('{"schema_version":"channel-agent-config-reload.v1"}', encoding="utf-8")
    identity = data_root / "runtime" / "agent-binding.json"
    identity.write_text('{"preserve":true}', encoding="utf-8")
    host = WindowsAgentHost(config_path, data_root)

    assert host._rollback_pending_configuration() is True
    assert ChannelAgentConfig.model_validate_json(config_path.read_bytes()).heartbeat_interval_seconds == previous.heartbeat_interval_seconds
    assert pending.exists() is False
    restart_request = data_root / "runtime" / "restart-agent.request"
    assert restart_request.is_file()
    assert restart_request.read_text(encoding="ascii") == (
        "rollback-preserve-assistant\n"
    )
    assert identity.read_text(encoding="utf-8") == '{"preserve":true}'
    assert host._rollback_pending_configuration() is False


def test_windows_installer_supports_in_place_upgrade_without_deleting_data() -> None:
    root = Path(__file__).resolve().parents[2]
    installer = (
        root
        / "packaging"
        / "windows-client-v1"
        / "Install-AI-CS-Channel-Agent.ps1"
    ).read_text(encoding="utf-8-sig")

    assert "$existingInstall" in installer
    assert "Stop-KnownAgentLauncher $InstallRoot $DataRoot" in installer
    assert "$stopProcess.ExitCode" in installer
    assert "Assert-PackageIntegrity $stageRoot" in installer
    assert "Get-InstallOwnedProcesses $InstallDirectory" in installer
    assert ".inc-$transactionId" in installer
    assert ".bak-$transactionId" in installer
    assert "Move-Item -LiteralPath $InstallRoot -Destination $rollbackRoot" in installer
    assert installer.index("Assert-PackageIntegrity $stageRoot") < installer.index(
        "Stop-KnownAgentLauncher $InstallRoot $DataRoot"
    )
    assert "Installed version" in installer
    assert "Remove-Item -LiteralPath $DataRoot" not in installer


def test_windows_build_prunes_bytecode_without_pipeline_path_binding() -> None:
    root = Path(__file__).resolve().parents[2]
    build = (root / "scripts" / "build_channel_agent_windows_client.ps1").read_text(
        encoding="utf-8"
    )

    assert "ForEach-Object { Remove-Item -LiteralPath $_.FullName" in build
    assert "Where-Object { $_.Extension -in @('.pyc', '.pyo') }" in build
    assert "Embedded Python runtime was removed while pruning build residue." in build


@pytest.mark.skipif(os.name != "nt", reason="Windows process validation")
def test_windows_process_detection_does_not_signal_process() -> None:
    assert _process_exists(os.getpid()) is True
    assert _process_exists(2_147_483_647) is False
