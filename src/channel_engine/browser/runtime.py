from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, Field, model_validator

from channel_engine.models.entities import new_id, utc_now

from .models import (
    BrowserHeartbeat,
    BrowserHeartbeatState,
    BrowserLoginState,
    BrowserModel,
    BrowserProfileReference,
    ChromeLaunchStrategy,
)
from .session import (
    BrowserDriverStartResult,
    BrowserProfileIsolationError,
    BrowserSessionUnavailable,
)


BROWSER_RUNTIME_CONTRACT_VERSION = "1.0"
_MAX_CDP_RESPONSE_BYTES = 1_048_576
_MAX_PAGE_LOCATION_LENGTH = 4096


class BrowserRuntimeError(RuntimeError):
    """Base error for the real browser runtime foundation."""


class BrowserRuntimeConfigurationError(BrowserRuntimeError):
    pass


class BrowserExecutableUnavailable(BrowserRuntimeError):
    pass


class BrowserInspectionUnavailable(BrowserRuntimeError):
    pass


class BrowserInspectionNotReady(BrowserInspectionUnavailable):
    pass


class BrowserProcessExited(BrowserRuntimeError):
    pass


class BrowserPageTarget(BrowserModel):
    """Minimal read-only CDP target data; the location is never serialized."""

    target_id: str = Field(min_length=1, max_length=512, exclude=True, repr=False)
    page_type: str = Field(min_length=1, max_length=64)
    location: str = Field(
        min_length=1,
        max_length=_MAX_PAGE_LOCATION_LENGTH,
        exclude=True,
        repr=False,
    )


class BrowserRuntimeObservation(BrowserModel):
    page_available: bool
    page_revision: str | None = Field(default=None, max_length=128)
    observed_at: AwareDatetime
    targets: tuple[BrowserPageTarget, ...] = Field(
        default=(), exclude=True, repr=False
    )

    @model_validator(mode="after")
    def validate_page_availability(self) -> BrowserRuntimeObservation:
        has_page = any(target.page_type == "page" for target in self.targets)
        if self.page_available != has_page:
            raise ValueError("page_available must reflect the observed page targets")
        if self.page_available and self.page_revision is None:
            raise ValueError("an available page requires a page revision")
        return self


class BrowserProcessSnapshot(BrowserModel):
    driver_session_ref: str = Field(min_length=1, max_length=128)
    pid: int = Field(gt=0)
    profile_id: str = Field(min_length=1, max_length=128)
    profile_path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$"
    )
    started_at: AwareDatetime
    alive: bool


@dataclass(frozen=True, slots=True)
class BrowserLoginLocationRule:
    """An evidence-supplied origin and path prefix; it is not PDD-specific."""

    origin: str
    path_prefix: str = "/"

    def __post_init__(self) -> None:
        normalized = _normalize_origin(self.origin)
        if normalized != self.origin:
            raise BrowserRuntimeConfigurationError(
                f"login rule origin must be normalized as {normalized}"
            )
        if not self.path_prefix.startswith("/"):
            raise BrowserRuntimeConfigurationError(
                "login rule path prefix must start with '/'"
            )
        if "?" in self.path_prefix or "#" in self.path_prefix:
            raise BrowserRuntimeConfigurationError(
                "login rule path prefix cannot contain query or fragment"
            )

    def matches(self, location: str) -> bool:
        parts = urlsplit(location)
        if not parts.hostname:
            return False
        return _origin_from_parts(parts) == self.origin and parts.path.startswith(
            self.path_prefix
        )


class ReadOnlyLoginDetector(Protocol):
    def detect(self, observation: BrowserRuntimeObservation) -> BrowserLoginState:
        """Classify already-observed page locations without mutating the browser."""


class ConservativeLoginDetector:
    """Safe default until platform-specific login evidence has been configured."""

    def detect(self, observation: BrowserRuntimeObservation) -> BrowserLoginState:
        del observation
        return BrowserLoginState.UNKNOWN


class ReadOnlyUrlLoginDetector:
    """Detect login state from explicitly configured, read-only URL rules."""

    def __init__(
        self,
        *,
        authenticated: Sequence[BrowserLoginLocationRule] = (),
        login_required: Sequence[BrowserLoginLocationRule] = (),
    ) -> None:
        self._authenticated = tuple(authenticated)
        self._login_required = tuple(login_required)

    def detect(self, observation: BrowserRuntimeObservation) -> BrowserLoginState:
        page_locations = tuple(
            target.location
            for target in observation.targets
            if target.page_type == "page"
        )
        if any(
            rule.matches(location)
            for rule in self._login_required
            for location in page_locations
        ):
            return BrowserLoginState.REQUIRED
        if any(
            rule.matches(location)
            for rule in self._authenticated
            for location in page_locations
        ):
            return BrowserLoginState.AUTHENTICATED
        return BrowserLoginState.UNKNOWN


class ManagedBrowserProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def stop(self, timeout_seconds: float) -> None: ...


class BrowserProcessLauncher(Protocol):
    def launch(
        self, executable: Path, arguments: tuple[str, ...]
    ) -> ManagedBrowserProcess: ...


class BrowserExecutableResolver(Protocol):
    def resolve(self) -> Path: ...


class BrowserRuntimeInspector(Protocol):
    def inspect(self, profile_path: Path) -> BrowserRuntimeObservation: ...


class BrowserProfilePathProvider(Protocol):
    def resolve(self, profile: BrowserProfileReference) -> Path: ...


class SystemChromeExecutableResolver:
    """Resolve a Chrome executable without starting or attaching to a browser."""

    def __init__(self, explicit_path: Path | None = None) -> None:
        self._explicit_path = explicit_path

    def resolve(self) -> Path:
        if self._explicit_path is not None:
            return self._validate(self._explicit_path)

        command = shutil.which("chrome") or shutil.which("google-chrome")
        if command:
            return self._validate(Path(command))

        candidates: list[Path] = []
        if os.name == "nt":
            for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
                base = os.environ.get(variable)
                if base:
                    candidates.append(
                        Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
                    )
        elif sys_platform() == "darwin":
            candidates.append(
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            )
        else:
            candidates.extend(
                (Path("/usr/bin/google-chrome"), Path("/usr/bin/google-chrome-stable"))
            )

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise BrowserExecutableUnavailable("system Chrome executable was not found")

    @staticmethod
    def _validate(path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise BrowserExecutableUnavailable("configured Chrome executable is unavailable")
        return resolved


class SystemChromeProcess:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> int | None:
        return self._process.poll()

    def stop(self, timeout_seconds: float) -> None:
        if self.poll() is not None:
            return
        if os.name == "nt":
            self._stop_windows_tree(timeout_seconds)
            return
        self._stop_posix_group(timeout_seconds)

    def _stop_windows_tree(self, timeout_seconds: float) -> None:
        subprocess.run(
            ("taskkill", "/PID", str(self.pid), "/T"),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(timeout_seconds, 0.1),
        )
        try:
            self._process.wait(timeout=timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            subprocess.run(
                ("taskkill", "/PID", str(self.pid), "/T", "/F"),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(timeout_seconds, 0.1),
            )
        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise BrowserRuntimeError("Chrome process tree did not stop") from exc

    def _stop_posix_group(self, timeout_seconds: float) -> None:
        try:
            os.killpg(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self._process.wait(timeout=timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise BrowserRuntimeError("Chrome process group did not stop") from exc


class SystemChromeProcessLauncher:
    """Launch Chrome directly (never through a shell) in its own process group."""

    def launch(
        self, executable: Path, arguments: tuple[str, ...]
    ) -> ManagedBrowserProcess:
        kwargs: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "shell": False,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(
            (str(executable), *arguments),
            **kwargs,  # type: ignore[arg-type]
        )
        return SystemChromeProcess(process)


class SystemChromeReadOnlyInspector:
    """Read Chrome's loopback DevTools target list; never executes page scripts."""

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 1.0,
        max_response_bytes: int = _MAX_CDP_RESPONSE_BYTES,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive")
        if max_response_bytes < 1:
            raise ValueError("max response size must be positive")
        self._request_timeout_seconds = request_timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._clock = clock
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def inspect(self, profile_path: Path) -> BrowserRuntimeObservation:
        port_file = profile_path / "DevToolsActivePort"
        try:
            lines = port_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise BrowserInspectionNotReady(
                "Chrome debugging endpoint is not ready"
            ) from exc
        except OSError as exc:
            raise BrowserInspectionUnavailable(
                "Chrome debugging endpoint metadata is unreadable"
            ) from exc
        if not lines:
            raise BrowserInspectionNotReady("Chrome debugging endpoint has no port")
        try:
            port = int(lines[0])
        except ValueError as exc:
            raise BrowserInspectionUnavailable(
                "Chrome debugging endpoint port is invalid"
            ) from exc
        if not 1 <= port <= 65535:
            raise BrowserInspectionUnavailable(
                "Chrome debugging endpoint port is out of range"
            )

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/list",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(
                request, timeout=self._request_timeout_seconds
            ) as response:
                payload = response.read(self._max_response_bytes + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise BrowserInspectionNotReady(
                "Chrome debugging endpoint is not responding"
            ) from exc
        if len(payload) > self._max_response_bytes:
            raise BrowserInspectionUnavailable(
                "Chrome debugging target response exceeds the safety limit"
            )
        try:
            raw_targets = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrowserInspectionUnavailable(
                "Chrome debugging target response is invalid"
            ) from exc
        if not isinstance(raw_targets, list):
            raise BrowserInspectionUnavailable(
                "Chrome debugging target response must be a list"
            )

        targets: list[BrowserPageTarget] = []
        revision_parts: list[str] = []
        for raw in raw_targets:
            if not isinstance(raw, dict):
                continue
            target_id = raw.get("id")
            page_type = raw.get("type")
            location = raw.get("url")
            if not all(isinstance(value, str) for value in (target_id, page_type, location)):
                continue
            assert isinstance(target_id, str)
            assert isinstance(page_type, str)
            assert isinstance(location, str)
            safe_location = _strip_query_and_fragment(location)
            if (
                not target_id
                or len(target_id) > 512
                or not page_type
                or len(page_type) > 64
                or not safe_location
                or len(safe_location) > _MAX_PAGE_LOCATION_LENGTH
            ):
                continue
            targets.append(
                BrowserPageTarget(
                    target_id=target_id,
                    page_type=page_type,
                    location=safe_location,
                )
            )
            revision_parts.append(f"{target_id}\0{page_type}\0{safe_location}")
        page_available = any(target.page_type == "page" for target in targets)
        revision = (
            "sha256:"
            + hashlib.sha256("\n".join(sorted(revision_parts)).encode()).hexdigest()
            if page_available
            else None
        )
        return BrowserRuntimeObservation(
            page_available=page_available,
            page_revision=revision,
            observed_at=self._clock(),
            targets=tuple(targets),
        )


class DedicatedBrowserProfilePathProvider:
    """Map opaque profile references into a controlled, non-default profile root."""

    def __init__(self, profile_root: Path) -> None:
        self._root = profile_root.expanduser().resolve()
        self._assert_not_default_chrome_storage(self._root)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, profile: BrowserProfileReference) -> Path:
        digest = hashlib.sha256(profile.storage_reference.encode()).hexdigest()
        path = (self._root / digest).resolve()
        if not _is_relative_to(path, self._root) or path == self._root:
            raise BrowserProfileIsolationError(
                "resolved browser profile escaped its dedicated root"
            )
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _assert_not_default_chrome_storage(root: Path) -> None:
        default_roots: list[Path] = []
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                default_roots.append(Path(local) / "Google" / "Chrome" / "User Data")
        elif sys_platform() == "darwin":
            default_roots.append(
                Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
            )
        else:
            default_roots.append(Path.home() / ".config" / "google-chrome")
        for candidate in default_roots:
            default = candidate.expanduser().resolve()
            if root == default or _is_relative_to(root, default):
                raise BrowserProfileIsolationError(
                    "the user default Chrome profile tree is forbidden"
                )


class NamedDedicatedBrowserProfilePathProvider(DedicatedBrowserProfilePathProvider):
    """Use the validated profile_id as the dedicated directory name."""

    def resolve(self, profile: BrowserProfileReference) -> Path:
        path = (self.root / profile.profile_id).resolve()
        if not _is_relative_to(path, self.root) or path == self.root:
            raise BrowserProfileIsolationError(
                "named browser profile escaped its dedicated root"
            )
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass(slots=True)
class DedicatedBrowserProfileLease:
    lock_path: Path
    owner: str
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        try:
            payload = self.lock_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._released = True
            return
        if payload != self.owner:
            raise BrowserProfileIsolationError(
                "browser profile lease ownership changed unexpectedly"
            )
        self.lock_path.unlink()
        self._released = True


class DedicatedBrowserProfileLeaseManager:
    LOCK_NAME = ".channel-engine-browser.lock"

    def acquire(
        self, profile_path: Path, driver_session_ref: str
    ) -> DedicatedBrowserProfileLease:
        lock_path = (profile_path / self.LOCK_NAME).resolve()
        if lock_path.parent != profile_path.resolve():
            raise BrowserProfileIsolationError("browser profile lock path is invalid")
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise BrowserProfileIsolationError(
                "browser profile is already leased by another runtime"
            ) from exc
        try:
            os.write(descriptor, driver_session_ref.encode("utf-8"))
        finally:
            os.close(descriptor)
        return DedicatedBrowserProfileLease(lock_path, driver_session_ref)


@dataclass(slots=True)
class _RuntimeSession:
    driver_session_ref: str
    profile: BrowserProfileReference
    profile_path: Path
    process: ManagedBrowserProcess
    profile_lease: DedicatedBrowserProfileLease
    started_at: datetime
    login_state: BrowserLoginState


class RealBrowserRuntimeDriver:
    """System-Chrome runtime with a dedicated profile and read-only inspection."""

    def __init__(
        self,
        profile_root: Path,
        *,
        chrome_executable: Path | None = None,
        initial_url: str = "about:blank",
        allowed_page_origins: Sequence[str] = (),
        startup_timeout_seconds: float = 10.0,
        shutdown_timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.1,
        executable_resolver: BrowserExecutableResolver | None = None,
        process_launcher: BrowserProcessLauncher | None = None,
        inspector: BrowserRuntimeInspector | None = None,
        login_detector: ReadOnlyLoginDetector | None = None,
        lease_manager: DedicatedBrowserProfileLeaseManager | None = None,
        profile_path_provider: BrowserProfilePathProvider | None = None,
        clock: Callable[[], AwareDatetime] = utc_now,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if startup_timeout_seconds <= 0 or shutdown_timeout_seconds <= 0:
            raise ValueError("browser lifecycle timeouts must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("browser poll interval must be positive")
        self._profile_paths = profile_path_provider or DedicatedBrowserProfilePathProvider(
            profile_root
        )
        self._executable_resolver = executable_resolver or SystemChromeExecutableResolver(
            chrome_executable
        )
        self._process_launcher = process_launcher or SystemChromeProcessLauncher()
        self._inspector = inspector or SystemChromeReadOnlyInspector(clock=clock)
        self._login_detector = login_detector or ConservativeLoginDetector()
        self._lease_manager = lease_manager or DedicatedBrowserProfileLeaseManager()
        self._startup_timeout_seconds = startup_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._initial_url = _validate_initial_url(
            initial_url, tuple(_normalize_origin(item) for item in allowed_page_origins)
        )
        self._sessions: dict[str, _RuntimeSession] = {}
        self._mutex = threading.RLock()

    def start(
        self,
        profile: BrowserProfileReference,
        strategy: ChromeLaunchStrategy,
    ) -> BrowserDriverStartResult:
        if strategy is not ChromeLaunchStrategy.SYSTEM_CHROME_PERSISTENT_CONTEXT:
            raise BrowserRuntimeConfigurationError(
                "RealBrowserRuntimeDriver only supports system Chrome persistent context"
            )
        executable = self._executable_resolver.resolve()
        profile_path = self._profile_paths.resolve(profile)
        driver_session_ref = new_id("chrome-runtime")
        lease = self._lease_manager.acquire(profile_path, driver_session_ref)
        process: ManagedBrowserProcess | None = None
        try:
            process = self._process_launcher.launch(
                executable,
                self._launch_arguments(profile_path),
            )
            observation = self._await_initial_observation(process, profile_path)
            login_state = self._safe_detect_login(observation)
            started_at = self._clock()
            runtime = _RuntimeSession(
                driver_session_ref=driver_session_ref,
                profile=profile,
                profile_path=profile_path,
                process=process,
                profile_lease=lease,
                started_at=started_at,
                login_state=login_state,
            )
            with self._mutex:
                self._sessions[driver_session_ref] = runtime
            return BrowserDriverStartResult(
                driver_session_ref=driver_session_ref,
                page_revision=observation.page_revision,
                login_state=login_state,
                page_available=observation.page_available,
                observed_at=observation.observed_at,
            )
        except Exception:
            try:
                if process is not None:
                    process.stop(self._shutdown_timeout_seconds)
            finally:
                lease.release()
            raise

    def heartbeat(self, driver_session_ref: str) -> BrowserHeartbeat:
        runtime = self._require_session(driver_session_ref)
        if runtime.process.poll() is not None:
            return BrowserHeartbeat(
                session_id=driver_session_ref,
                state=BrowserHeartbeatState.CRASHED,
                login_state=BrowserLoginState.UNKNOWN,
                page_available=False,
                page_revision=None,
                checked_at=self._clock(),
                failure_code="CHROME_PROCESS_EXITED",
            )
        try:
            observation = self._inspector.inspect(runtime.profile_path)
        except BrowserInspectionUnavailable:
            return BrowserHeartbeat(
                session_id=driver_session_ref,
                state=BrowserHeartbeatState.DEGRADED,
                login_state=BrowserLoginState.UNKNOWN,
                page_available=False,
                page_revision=None,
                checked_at=self._clock(),
                failure_code="CHROME_PAGE_INSPECTION_UNAVAILABLE",
            )
        detected = self._safe_detect_login(observation)
        if (
            runtime.login_state is BrowserLoginState.AUTHENTICATED
            and detected is BrowserLoginState.REQUIRED
        ):
            detected = BrowserLoginState.EXPIRED
        runtime.login_state = detected
        state = (
            BrowserHeartbeatState.HEALTHY
            if observation.page_available
            else BrowserHeartbeatState.DEGRADED
        )
        return BrowserHeartbeat(
            session_id=driver_session_ref,
            state=state,
            login_state=detected,
            page_available=observation.page_available,
            page_revision=observation.page_revision,
            checked_at=observation.observed_at,
            failure_code=None if observation.page_available else "CHROME_PAGE_UNAVAILABLE",
        )

    def stop(self, driver_session_ref: str) -> None:
        with self._mutex:
            runtime = self._sessions.pop(driver_session_ref, None)
        if runtime is None:
            return
        process_error: Exception | None = None
        try:
            runtime.process.stop(self._shutdown_timeout_seconds)
        except Exception as exc:  # cleanup continues so a lock cannot leak silently
            process_error = exc
        try:
            runtime.profile_lease.release()
        except Exception:
            if process_error is None:
                raise
        if process_error is not None:
            raise BrowserRuntimeError("Chrome process cleanup failed") from process_error

    def process_snapshot(self, driver_session_ref: str) -> BrowserProcessSnapshot:
        runtime = self._require_session(driver_session_ref)
        return BrowserProcessSnapshot(
            driver_session_ref=driver_session_ref,
            pid=runtime.process.pid,
            profile_id=runtime.profile.profile_id,
            profile_path_fingerprint=hashlib.sha256(
                str(runtime.profile_path).encode()
            ).hexdigest(),
            started_at=runtime.started_at,
            alive=runtime.process.poll() is None,
        )

    def _require_session(self, driver_session_ref: str) -> _RuntimeSession:
        with self._mutex:
            runtime = self._sessions.get(driver_session_ref)
        if runtime is None:
            raise BrowserSessionUnavailable("browser driver session is unavailable")
        return runtime

    def _launch_arguments(self, profile_path: Path) -> tuple[str, ...]:
        return (
            f"--user-data-dir={profile_path}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            self._initial_url,
        )

    def _await_initial_observation(
        self, process: ManagedBrowserProcess, profile_path: Path
    ) -> BrowserRuntimeObservation:
        deadline = self._monotonic() + self._startup_timeout_seconds
        while True:
            if process.poll() is not None:
                raise BrowserProcessExited("Chrome exited before its page became available")
            try:
                return self._inspector.inspect(profile_path)
            except BrowserInspectionNotReady:
                if self._monotonic() >= deadline:
                    raise BrowserInspectionUnavailable(
                        "Chrome page inspection did not become ready before timeout"
                    )
                self._sleeper(self._poll_interval_seconds)

    def _safe_detect_login(
        self, observation: BrowserRuntimeObservation
    ) -> BrowserLoginState:
        try:
            return self._login_detector.detect(observation)
        except Exception:
            return BrowserLoginState.UNKNOWN


def _strip_query_and_fragment(location: str) -> str:
    parts = urlsplit(location)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _normalize_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise BrowserRuntimeConfigurationError(
            "allowed origins must be HTTP(S) origins without credentials, path, query or fragment"
        )
    return _origin_from_parts(parts)


def _origin_from_parts(parts) -> str:
    hostname = parts.hostname
    if hostname is None:
        raise BrowserRuntimeConfigurationError("origin hostname is required")
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{host}{port}"


def _validate_initial_url(initial_url: str, allowed_origins: tuple[str, ...]) -> str:
    if initial_url == "about:blank":
        return initial_url
    parts = urlsplit(initial_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise BrowserRuntimeConfigurationError(
            "initial browser URL must be about:blank or an allowed HTTP(S) URL "
            "without credentials, query or fragment"
        )
    if _origin_from_parts(parts) not in allowed_origins:
        raise BrowserRuntimeConfigurationError(
            "initial browser URL origin is not explicitly allowed"
        )
    return initial_url


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def sys_platform() -> str:
    # Isolated for deterministic unit testing without mutating global platform state.
    import sys

    return sys.platform


__all__ = [
    "BROWSER_RUNTIME_CONTRACT_VERSION",
    "BrowserExecutableResolver",
    "BrowserExecutableUnavailable",
    "BrowserInspectionNotReady",
    "BrowserInspectionUnavailable",
    "BrowserLoginLocationRule",
    "BrowserPageTarget",
    "BrowserProcessLauncher",
    "BrowserProcessSnapshot",
    "BrowserProfilePathProvider",
    "BrowserProcessExited",
    "BrowserRuntimeConfigurationError",
    "BrowserRuntimeError",
    "BrowserRuntimeInspector",
    "BrowserRuntimeObservation",
    "ConservativeLoginDetector",
    "DedicatedBrowserProfileLeaseManager",
    "DedicatedBrowserProfilePathProvider",
    "ManagedBrowserProcess",
    "NamedDedicatedBrowserProfilePathProvider",
    "ReadOnlyLoginDetector",
    "ReadOnlyUrlLoginDetector",
    "RealBrowserRuntimeDriver",
    "SystemChromeExecutableResolver",
    "SystemChromeProcessLauncher",
    "SystemChromeReadOnlyInspector",
]
