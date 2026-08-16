from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from channel_engine.browser import (
    BrowserInspectionUnavailable,
    BrowserLoginLocationRule,
    BrowserLoginState,
    BrowserPageTarget,
    BrowserProfileIsolationError,
    BrowserProfileReference,
    BrowserRuntimeConfigurationError,
    BrowserRuntimeObservation,
    BrowserSessionManager,
    BrowserSessionState,
    ChromeLaunchStrategy,
    DedicatedBrowserProfileLeaseManager,
    NamedDedicatedBrowserProfilePathProvider,
    ReadOnlyUrlLoginDetector,
    RealBrowserRuntimeDriver,
    SystemChromeReadOnlyInspector,
)


NOW = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)


def profile() -> BrowserProfileReference:
    return BrowserProfileReference(
        profile_id="pdd-runtime-profile",
        account_ref="synthetic-pdd-account",
        storage_reference="profile-ref://pdd/synthetic-pdd-account",
    )


def observation(location: str, revision: str) -> BrowserRuntimeObservation:
    return BrowserRuntimeObservation(
        page_available=True,
        page_revision=revision,
        observed_at=NOW,
        targets=(
            BrowserPageTarget(
                target_id=f"target-{revision}",
                page_type="page",
                location=location,
            ),
        ),
    )


class FakeExecutableResolver:
    def __init__(self, executable: Path) -> None:
        self.executable = executable
        self.resolve_count = 0

    def resolve(self) -> Path:
        self.resolve_count += 1
        return self.executable


@dataclass
class FakeManagedProcess:
    pid: int
    exit_code: int | None = None
    stop_count: int = 0

    def poll(self) -> int | None:
        return self.exit_code

    def stop(self, timeout_seconds: float) -> None:
        assert timeout_seconds > 0
        self.stop_count += 1
        if self.exit_code is None:
            self.exit_code = 0


class FakeProcessLauncher:
    def __init__(self, starting_pid: int = 4100) -> None:
        self._next_pid = starting_pid
        self.calls: list[tuple[Path, tuple[str, ...]]] = []
        self.processes: list[FakeManagedProcess] = []

    def launch(
        self, executable: Path, arguments: tuple[str, ...]
    ) -> FakeManagedProcess:
        self.calls.append((executable, arguments))
        process = FakeManagedProcess(self._next_pid)
        self._next_pid += 1
        self.processes.append(process)
        return process


class SequenceInspector:
    def __init__(self, *results: BrowserRuntimeObservation | Exception) -> None:
        self._results = list(results)
        self.paths: list[Path] = []

    def inspect(self, profile_path: Path) -> BrowserRuntimeObservation:
        self.paths.append(profile_path)
        if not self._results:
            raise AssertionError("unexpected browser inspection")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def login_detector() -> ReadOnlyUrlLoginDetector:
    return ReadOnlyUrlLoginDetector(
        authenticated=(
            BrowserLoginLocationRule("https://merchant.test", "/chat"),
        ),
        login_required=(
            BrowserLoginLocationRule("https://merchant.test", "/login"),
        ),
    )


def runtime_driver(
    profile_root: Path,
    launcher: FakeProcessLauncher,
    inspector: SequenceInspector,
) -> RealBrowserRuntimeDriver:
    return RealBrowserRuntimeDriver(
        profile_root,
        executable_resolver=FakeExecutableResolver(Path("C:/synthetic/chrome.exe")),
        process_launcher=launcher,
        inspector=inspector,
        login_detector=login_detector(),
        clock=lambda: NOW,
        sleeper=lambda _seconds: None,
    )


def test_real_driver_lifecycle_uses_dedicated_profile_and_tracks_process(
    tmp_path: Path,
) -> None:
    launcher = FakeProcessLauncher()
    inspector = SequenceInspector(
        observation("https://merchant.test/chat", "revision-1"),
        observation("https://merchant.test/chat", "revision-2"),
    )
    driver = runtime_driver(tmp_path / "dedicated-profiles", launcher, inspector)

    started = driver.start(
        profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT
    )
    assert started.login_state is BrowserLoginState.AUTHENTICATED
    assert started.page_available is True
    executable, arguments = launcher.calls[0]
    assert executable == Path("C:/synthetic/chrome.exe")
    user_data_arguments = [
        argument for argument in arguments if argument.startswith("--user-data-dir=")
    ]
    assert len(user_data_arguments) == 1
    dedicated_path = Path(user_data_arguments[0].split("=", 1)[1])
    assert dedicated_path.parent == (tmp_path / "dedicated-profiles").resolve()
    assert profile().account_ref not in str(dedicated_path)
    assert profile().storage_reference not in " ".join(arguments)
    assert "--remote-debugging-address=127.0.0.1" in arguments
    assert "--remote-debugging-port=0" in arguments
    assert "about:blank" == arguments[-1]
    assert not any(argument.startswith("--profile-directory=") for argument in arguments)

    tracked = driver.process_snapshot(started.driver_session_ref)
    assert tracked.pid == 4100
    assert tracked.alive is True
    assert len(tracked.profile_path_fingerprint) == 64
    heartbeat = driver.heartbeat(started.driver_session_ref)
    assert heartbeat.login_state is BrowserLoginState.AUTHENTICATED
    assert heartbeat.page_available is True

    driver.stop(started.driver_session_ref)
    assert launcher.processes[0].stop_count == 1
    assert not (dedicated_path / DedicatedBrowserProfileLeaseManager.LOCK_NAME).exists()
    assert dedicated_path.exists(), "stopping must preserve the dedicated profile"
    driver.stop(started.driver_session_ref)  # idempotent cleanup


def test_session_manager_recovers_crashed_chrome_with_new_page_generation(
    tmp_path: Path,
) -> None:
    launcher = FakeProcessLauncher()
    inspector = SequenceInspector(
        observation("https://merchant.test/chat", "revision-1"),
        observation("https://merchant.test/chat", "revision-2"),
    )
    driver = runtime_driver(tmp_path / "profiles", launcher, inspector)
    manager = BrowserSessionManager(
        driver,
        profile(),
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version="pdd:merchant_chat:v1",
        clock=lambda: NOW,
    )

    first = manager.start()
    assert first.state is BrowserSessionState.ACTIVE
    assert first.generation == 1
    assert first.page_context is not None
    assert first.page_context.page_revision == "revision-1"
    launcher.processes[0].exit_code = 37

    crashed = manager.heartbeat()
    assert crashed.state is BrowserSessionState.CRASHED
    assert crashed.failure_code == "CHROME_PROCESS_EXITED"
    recovered = manager.recover()
    assert recovered.state is BrowserSessionState.ACTIVE
    assert recovered.generation == 2
    assert recovered.page_context is not None
    assert recovered.page_context.page_revision == "revision-2"
    assert len(launcher.processes) == 2
    assert launcher.processes[0].stop_count == 1
    manager.stop()


def test_authenticated_session_becomes_expired_on_read_only_login_detection(
    tmp_path: Path,
) -> None:
    launcher = FakeProcessLauncher()
    inspector = SequenceInspector(
        observation("https://merchant.test/chat", "revision-1"),
        observation("https://merchant.test/login", "revision-2"),
    )
    driver = runtime_driver(tmp_path / "profiles", launcher, inspector)
    manager = BrowserSessionManager(
        driver,
        profile(),
        strategy=ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT,
        selector_contract_version="pdd:merchant_chat:v1",
        clock=lambda: NOW,
    )

    assert manager.start().state is BrowserSessionState.ACTIVE
    expired = manager.heartbeat()
    assert expired.state is BrowserSessionState.EXPIRED
    assert expired.login_state is BrowserLoginState.EXPIRED
    assert expired.human_takeover_required is True
    assert launcher.processes[0].stop_count == 0, "login detection must not act"
    manager.stop()


def test_profile_file_lease_prevents_duplicate_runtime_and_releases_on_stop(
    tmp_path: Path,
) -> None:
    profile_root = tmp_path / "profiles"
    first_launcher = FakeProcessLauncher(5100)
    second_launcher = FakeProcessLauncher(6100)
    first = runtime_driver(
        profile_root,
        first_launcher,
        SequenceInspector(observation("https://merchant.test/chat", "revision-1")),
    )
    second = runtime_driver(
        profile_root,
        second_launcher,
        SequenceInspector(observation("https://merchant.test/chat", "revision-2")),
    )

    first_started = first.start(
        profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT
    )
    with pytest.raises(BrowserProfileIsolationError, match="already leased"):
        second.start(profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT)
    assert second_launcher.calls == []

    first.stop(first_started.driver_session_ref)
    second_started = second.start(
        profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT
    )
    assert second.process_snapshot(second_started.driver_session_ref).pid == 6100
    second.stop(second_started.driver_session_ref)


def test_named_profile_provider_uses_existing_dedicated_profile_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "channel-agent-profiles"
    provider = NamedDedicatedBrowserProfilePathProvider(root)

    resolved = provider.resolve(profile())

    assert resolved == (root / profile().profile_id).resolve()
    assert resolved.is_dir()
    assert resolved.parent == root.resolve()


def test_failed_start_cleans_process_and_profile_lease(tmp_path: Path) -> None:
    profile_root = tmp_path / "profiles"
    launcher = FakeProcessLauncher()
    driver = runtime_driver(
        profile_root,
        launcher,
        SequenceInspector(BrowserInspectionUnavailable("synthetic failure")),
    )

    with pytest.raises(BrowserInspectionUnavailable, match="synthetic failure"):
        driver.start(profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT)
    assert launcher.processes[0].stop_count == 1
    lock_files = list(profile_root.rglob(DedicatedBrowserProfileLeaseManager.LOCK_NAME))
    assert lock_files == []


def test_external_initial_page_requires_explicit_origin_allowlist(
    tmp_path: Path,
) -> None:
    with pytest.raises(BrowserRuntimeConfigurationError, match="explicitly allowed"):
        RealBrowserRuntimeDriver(
            tmp_path / "profiles",
            initial_url="https://merchant.test/chat",
        )

    driver = RealBrowserRuntimeDriver(
        tmp_path / "allowed-profiles",
        initial_url="https://merchant.test/chat",
        allowed_page_origins=("https://merchant.test",),
        executable_resolver=FakeExecutableResolver(Path("C:/synthetic/chrome.exe")),
        process_launcher=FakeProcessLauncher(),
        inspector=SequenceInspector(
            observation("https://merchant.test/chat", "revision-1")
        ),
        login_detector=login_detector(),
        clock=lambda: NOW,
    )
    started = driver.start(
        profile(), ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT
    )
    driver.stop(started.driver_session_ref)

    with pytest.raises(BrowserRuntimeConfigurationError, match="query or fragment"):
        RealBrowserRuntimeDriver(
            tmp_path / "query-profiles",
            initial_url="https://merchant.test/chat?token=forbidden",
            allowed_page_origins=("https://merchant.test",),
        )


def test_runtime_observations_do_not_serialize_page_location() -> None:
    observed = observation(
        "https://merchant.test/chat/synthetic-conversation?token=forbidden",
        "revision-1",
    )
    serialized = observed.model_dump_json()
    assert "synthetic-conversation" not in serialized
    assert "forbidden" not in serialized
    assert "target-revision" not in serialized


def test_system_chrome_inspector_reads_only_loopback_target_metadata(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "dedicated-profile"
    profile_path.mkdir()
    (profile_path / "DevToolsActivePort").write_text(
        "43123\n/devtools/browser/synthetic\n", encoding="utf-8"
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return (
                b'[{"id":"target-1","type":"page",'
                b'"url":"https://merchant.test/chat?secret=forbidden"}]'
            )

    class LoopbackOnlyOpener:
        def __init__(self) -> None:
            self.calls: list[tuple[str, float]] = []

        def open(self, request, timeout: float):
            self.calls.append((request.full_url, timeout))
            return FakeResponse()

    opener = LoopbackOnlyOpener()
    inspector = SystemChromeReadOnlyInspector(clock=lambda: NOW)
    inspector._opener = opener  # type: ignore[attr-defined]

    result = inspector.inspect(profile_path)
    assert opener.calls == [("http://127.0.0.1:43123/json/list", 1.0)]
    assert result.page_available is True
    assert result.page_revision is not None
    assert result.targets[0].location == "https://merchant.test/chat"
    assert "forbidden" not in result.model_dump_json()
