from __future__ import annotations

import ctypes
import hashlib
import http.client
import json
import os
import re
import subprocess
import time
import uuid
from ctypes import wintypes
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Callable, Literal, Protocol
from urllib.parse import parse_qsl, urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .logger import SafeAgentLogger


BROWSER_SESSION_SCHEMA_VERSION = "1.0"
_SAFE_FILE_PART = re.compile(r"[^A-Za-z0-9._-]+")


class BrowserControlError(RuntimeError):
    """Base error for the credential-free browser process boundary."""


class BrowserDisabledError(BrowserControlError):
    pass


class BrowserEnvironmentError(BrowserControlError):
    pass


class BrowserStateError(BrowserControlError):
    pass


class BrowserNavigationError(BrowserControlError):
    pass


class BrowserSessionStatus(StrEnum):
    STARTING = "STARTING"
    OPENED = "OPENED"
    WAITING_LOGIN = "WAITING_LOGIN"
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class BrowserSessionState(BaseModel):
    """Credential-free state for one Agent-owned browser process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = BROWSER_SESSION_SCHEMA_VERSION
    browser_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    profile_path: str = Field(min_length=1, max_length=2048)
    status: BrowserSessionStatus
    pid: int | None = Field(default=None, ge=1)
    generation: int = Field(default=1, ge=1)
    created_at: AwareDatetime
    last_seen: AwareDatetime
    human_interaction_required: bool = True
    automatic_recovery_attempted: bool = False
    last_error_code: str | None = Field(default=None, max_length=128)

    @field_validator("profile_path")
    @classmethod
    def validate_profile_path(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("browser profile path must be absolute")
        return value

    def public_view(self, data_root: str | Path) -> dict[str, object]:
        root = Path(data_root).resolve()
        profile = Path(self.profile_path).resolve()
        try:
            reference = profile.relative_to(root).as_posix()
        except ValueError:
            reference = "INVALID_PROFILE_BOUNDARY"
        return {
            "schema_version": self.schema_version,
            "browser_id": self.browser_id,
            "agent_id": self.agent_id,
            "profile_reference": reference,
            "status": self.status.value,
            "pid": self.pid,
            "generation": self.generation,
            "created_at": self.created_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "human_interaction_required": self.human_interaction_required,
            "automatic_recovery_attempted": self.automatic_recovery_attempted,
            "last_error_code": self.last_error_code,
            "contains_credentials": False,
        }


class BrowserCommandInterface(Protocol):
    def open_browser(self) -> BrowserSessionState: ...

    def close_browser(self) -> BrowserSessionState: ...

    def browser_status(self) -> BrowserSessionState: ...

    def navigate(self, url: str) -> BrowserSessionState: ...


class BrowserProcessController(Protocol):
    def start(self, executable: Path, profile_path: Path, url: str) -> int: ...

    def is_running(self, pid: int, executable: Path) -> bool: ...

    def find_running(self, executable: Path, profile_path: Path) -> int | None: ...

    def stop(self, pid: int, executable: Path, timeout_seconds: float) -> bool: ...

    def navigate(self, executable: Path, profile_path: Path, url: str) -> None: ...


class BrowserSessionStore:
    """Atomic local store. It contains state and paths, never browser credentials."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> BrowserSessionState | None:
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > 1024 * 1024:
                raise BrowserStateError("browser session state exceeds one MiB")
            return BrowserSessionState.model_validate_json(raw)
        except BrowserStateError:
            raise
        except Exception as exc:
            # A forced Windows shutdown can leave the small, non-secret state
            # file truncated even though the independent Edge profile remains
            # intact.  Quarantine that unusable state and let the runtime
            # reconstruct a STOPPED session instead of crashing on every boot.
            try:
                self._quarantine_invalid_state()
            except OSError as quarantine_exc:
                raise BrowserStateError(
                    "browser session state is invalid and cannot be quarantined"
                ) from quarantine_exc
            return None

    def save(self, state: BrowserSessionState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = state.model_dump_json(indent=2).encode("utf-8") + b"\n"
        try:
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise BrowserStateError("browser session state cannot be saved") from exc

    def _quarantine_invalid_state(self) -> Path:
        quarantine = self.path.parent / "corrupt"
        quarantine.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = quarantine / f"{self.path.stem}.{timestamp}.{uuid.uuid4().hex[:8]}.invalid"
        os.replace(self.path, target)
        return target


class BrowserProfileManager:
    """Creates one isolated Edge profile below the Agent data directory."""

    MARKER = ".ai-cs-channel-agent-profile.json"

    def __init__(self, data_root: str | Path, agent_id: str) -> None:
        self.data_root = Path(data_root).resolve()
        slug = _SAFE_FILE_PART.sub("-", agent_id).strip("-._") or "agent"
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:12]
        self.profile_path = (
            self.data_root / "browser" / "profiles" / f"{slug[:48]}-{digest}" / "edge"
        ).resolve()
        self._agent_id = agent_id
        self._validate_boundary()

    def initialize(self) -> Path:
        self._validate_boundary()
        self.profile_path.mkdir(parents=True, exist_ok=True)
        marker = self.profile_path / self.MARKER
        payload = {
            "schema_version": "1.0",
            "owner": "AI-CS Channel Agent",
            "agent_id": self._agent_id,
            "profile_isolation": True,
            "sensitive_data_export_allowed": False,
        }
        if marker.exists():
            try:
                current = json.loads(marker.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BrowserStateError("browser profile marker is invalid") from exc
            if current != payload:
                raise BrowserStateError("browser profile ownership does not match Agent")
        else:
            marker.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return self.profile_path

    def reference(self) -> str:
        return self.profile_path.relative_to(self.data_root).as_posix()

    def _validate_boundary(self) -> None:
        try:
            self.profile_path.relative_to(self.data_root)
        except ValueError as exc:
            raise BrowserEnvironmentError(
                "browser profile must stay inside the Agent data directory"
            ) from exc
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            personal_roots = (
                Path(local_app_data) / "Microsoft" / "Edge" / "User Data",
                Path(local_app_data) / "Google" / "Chrome" / "User Data",
            )
            for personal in personal_roots:
                try:
                    self.profile_path.relative_to(personal.resolve())
                except ValueError:
                    continue
                raise BrowserEnvironmentError(
                    "personal Chrome or Edge profiles cannot be used by Channel Agent"
                )


class WindowsEdgeExecutableResolver:
    """Finds system Microsoft Edge without consulting a personal browser profile."""

    def resolve(self) -> Path:
        if os.name != "nt":
            raise BrowserEnvironmentError("Edge browser control requires Windows")
        candidates: list[Path] = []
        for name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            root = os.getenv(name)
            if root:
                candidates.append(
                    Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise BrowserEnvironmentError("Microsoft Edge executable was not found")


class WindowsBrowserProcessController:
    """Windows process controller scoped to a verified Edge PID and isolated profile."""

    def start(self, executable: Path, profile_path: Path, url: str) -> int:
        self._require_windows(executable)
        try:
            process = subprocess.Popen(
                self._command(executable, profile_path, url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except OSError as exc:
            raise BrowserEnvironmentError("Microsoft Edge could not be started") from exc
        return process.pid

    def is_running(self, pid: int, executable: Path) -> bool:
        if os.name != "nt" or pid <= 0:
            return False
        actual = _windows_process_image(pid)
        if actual is None:
            return False
        return os.path.normcase(actual) == os.path.normcase(str(executable.resolve()))

    def find_running(self, executable: Path, profile_path: Path) -> int | None:
        """Find the main Edge process that owns the exact Agent profile.

        Edge can hand a new launch request to an already-running browser process and
        immediately exit the launcher PID.  The profile path is the stable ownership
        boundary; no command line or page URL is persisted or logged.
        """

        self._require_windows(executable)
        # Edge writes this file inside the exact isolated profile after binding
        # its loopback DevTools listener.  Prefer that narrow ownership signal
        # over a system-wide CIM scan: Win32_Process can fail under Windows
        # memory pressure even while the dedicated Edge window is healthy.
        devtools_pid = self._find_running_from_devtools(executable, profile_path)
        if devtools_pid is not None:
            return devtools_pid
        environment = os.environ.copy()
        environment["AI_CS_EDGE_EXECUTABLE"] = str(executable.resolve())
        environment["AI_CS_EDGE_PROFILE"] = str(profile_path.resolve())
        script = r"""
$ErrorActionPreference = 'Stop'
$expectedExecutable = [IO.Path]::GetFullPath($env:AI_CS_EDGE_EXECUTABLE)
$expectedProfile = [IO.Path]::GetFullPath($env:AI_CS_EDGE_PROFILE)
$profilePattern = [regex]::Escape($expectedProfile)
$candidates = @(
  Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object {
      $_.ExecutablePath -and
      ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $expectedExecutable) -and
      $_.CommandLine -and
      ($_.CommandLine -match $profilePattern)
    }
)
$candidateIds = @($candidates | Select-Object -ExpandProperty ProcessId)
$main = $candidates |
  Where-Object { $_.ParentProcessId -notin $candidateIds } |
  Sort-Object ProcessId |
  Select-Object -First 1
if ($null -eq $main) { $main = $candidates | Sort-Object ProcessId | Select-Object -First 1 }
if ($null -ne $main) { [Console]::Out.Write([string]$main.ProcessId) }
"""
        try:
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5.0,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        try:
            pid = int(completed.stdout.strip())
        except (TypeError, ValueError):
            return None
        return pid if completed.returncode == 0 and self.is_running(pid, executable) else None

    def _find_running_from_devtools(
        self,
        executable: Path,
        profile_path: Path,
    ) -> int | None:
        port_file = profile_path.resolve() / "DevToolsActivePort"
        try:
            raw = port_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
        if len(raw) > 4096:
            return None
        lines = raw.splitlines()
        if len(lines) < 2 or not lines[1].startswith("/devtools/browser/"):
            return None
        try:
            port = int(lines[0])
        except ValueError:
            return None
        if not 1 <= port <= 65535:
            return None
        if not self._devtools_endpoint_matches(port, lines[1]):
            return None
        try:
            completed = subprocess.run(
                ["netstat.exe", "-ano", "-p", "tcp"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        listener = re.compile(
            rf"^\s*TCP\s+127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$",
            flags=re.IGNORECASE | re.MULTILINE,
        ).search(completed.stdout)
        if listener is None:
            return None
        try:
            pid = int(listener.group(1))
        except ValueError:
            return None
        return pid if self.is_running(pid, executable) else None

    @staticmethod
    def _devtools_endpoint_matches(port: int, expected_path: str) -> bool:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        try:
            connection.request("GET", "/json/version")
            response = connection.getresponse()
            if response.status != 200:
                return False
            body = response.read(16385)
            if len(body) > 16384:
                return False
            payload = json.loads(body.decode("utf-8"))
        except (
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            http.client.HTTPException,
        ):
            return False
        finally:
            connection.close()
        websocket_url = payload.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str):
            return False
        parsed = urlsplit(websocket_url)
        return (
            parsed.scheme == "ws"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port == port
            and parsed.path == expected_path
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )

    def stop(self, pid: int, executable: Path, timeout_seconds: float) -> bool:
        if not self.is_running(pid, executable):
            return True
        commands = (
            ["taskkill.exe", "/PID", str(pid), "/T"],
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        )
        for command in commands:
            try:
                subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=max(timeout_seconds, 0.5),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            deadline = time.monotonic() + max(timeout_seconds, 0.5)
            while time.monotonic() < deadline:
                if not self.is_running(pid, executable):
                    return True
                time.sleep(0.05)
        return not self.is_running(pid, executable)

    def navigate(self, executable: Path, profile_path: Path, url: str) -> None:
        self._require_windows(executable)
        try:
            subprocess.Popen(
                self._command(executable, profile_path, url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except OSError as exc:
            raise BrowserNavigationError("Edge navigation could not be requested") from exc

    @staticmethod
    def _command(executable: Path, profile_path: Path, url: str) -> list[str]:
        return [
            str(executable),
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-sync",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            url,
        ]

    @staticmethod
    def _require_windows(executable: Path) -> None:
        if os.name != "nt":
            raise BrowserEnvironmentError("browser process control requires Windows")
        if executable.name.casefold() != "msedge.exe" or not executable.is_file():
            raise BrowserEnvironmentError("only a system Microsoft Edge executable is allowed")


class ChannelAgentBrowserManager:
    """Default-off process-only browser runtime; it has no DOM or send capability."""

    def __init__(
        self,
        *,
        agent_id: str,
        data_root: str | Path,
        enabled: bool,
        logger: SafeAgentLogger,
        executable_resolver: WindowsEdgeExecutableResolver | None = None,
        process_controller: BrowserProcessController | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        stop_timeout_seconds: float = 5.0,
    ) -> None:
        self.agent_id = agent_id
        self.data_root = Path(data_root).resolve()
        self.enabled = bool(enabled)
        self._logger = logger
        self._resolver = executable_resolver or WindowsEdgeExecutableResolver()
        self._process = process_controller or WindowsBrowserProcessController()
        self._clock = clock
        self._stop_timeout = max(stop_timeout_seconds, 0.5)
        self._profile = BrowserProfileManager(self.data_root, agent_id)
        self._store = BrowserSessionStore(
            self.data_root
            / "runtime"
            / "browser-sessions"
            / f"{self._profile.profile_path.parent.name}.json"
        )
        self._lock = RLock()

    def open_browser(self) -> BrowserSessionState:
        self._require_enabled()
        with self._lock:
            existing = self._load_checked()
            if existing and existing.pid and self._is_running(existing.pid):
                return existing
            profile = self._profile.initialize()
            if existing is not None:
                reattached = self._reattach(existing, profile, allow_stopped=True)
                if reattached is not None:
                    return reattached
            now = self._clock()
            state = BrowserSessionState(
                browser_id=f"browser:{uuid.uuid4()}",
                agent_id=self.agent_id,
                profile_path=str(profile),
                status=BrowserSessionStatus.STARTING,
                created_at=now,
                last_seen=now,
            )
            self._store.save(state)
            self._logger.event(
                "BROWSER_STARTING",
                "PENDING",
                {
                    "agent_id": self.agent_id,
                    "browser_id": state.browser_id,
                    "profile_reference": self._profile.reference(),
                },
            )
            try:
                executable = self._resolver.resolve()
                pid = self._process.start(executable, profile, "about:blank")
            except BrowserControlError as exc:
                failed = state.model_copy(
                    update={
                        "status": BrowserSessionStatus.FAILED,
                        "last_seen": self._clock(),
                        "last_error_code": type(exc).__name__.upper(),
                    }
                )
                self._store.save(failed)
                self._logger.error("BROWSER_START_FAILED", exc)
                raise
            opened = state.model_copy(
                update={
                    "status": BrowserSessionStatus.OPENED,
                    "pid": pid,
                    "last_seen": self._clock(),
                    "last_error_code": None,
                }
            )
            self._store.save(opened)
            self._logger.event(
                "BROWSER_OPENED",
                "SUCCESS",
                {
                    "agent_id": self.agent_id,
                    "browser_id": opened.browser_id,
                    "pid": pid,
                    "profile_reference": self._profile.reference(),
                },
            )
            return opened

    def close_browser(self) -> BrowserSessionState:
        with self._lock:
            state = self._load_checked() or self._initial_stopped_state()
            if state.pid is not None:
                executable = self._resolver.resolve()
                if not self._process.stop(state.pid, executable, self._stop_timeout):
                    failed = state.model_copy(
                        update={
                            "status": BrowserSessionStatus.FAILED,
                            "last_seen": self._clock(),
                            "last_error_code": "BROWSER_PROCESS_STOP_FAILED",
                        }
                    )
                    self._store.save(failed)
                    raise BrowserEnvironmentError("Edge did not stop within the safe timeout")
            stopped = state.model_copy(
                update={
                    "status": BrowserSessionStatus.STOPPED,
                    "pid": None,
                    "last_seen": self._clock(),
                    "last_error_code": None,
                }
            )
            self._store.save(stopped)
            self._logger.event(
                "BROWSER_STOPPED",
                "SUCCESS",
                {"agent_id": self.agent_id, "browser_id": stopped.browser_id},
            )
            return stopped

    def browser_status(self) -> BrowserSessionState:
        with self._lock:
            state = self._load_checked() or self._initial_stopped_state()
            active = state.status in {
                BrowserSessionStatus.STARTING,
                BrowserSessionStatus.OPENED,
                BrowserSessionStatus.WAITING_LOGIN,
                BrowserSessionStatus.READY,
                BrowserSessionStatus.RECOVERING,
            }
            # A status poll may try one profile reattachment while the session is
            # expected to be alive.  Once an operator has closed Edge and the
            # session is DEGRADED, subsequent UI polls must remain side-effect-free;
            # an explicit launch click owns the next reattachment/start attempt.
            if active:
                reattached = self._reattach(state, Path(state.profile_path))
                if reattached is not None:
                    return reattached
            if active and (state.pid is None or not self._is_running(state.pid)):
                state = state.model_copy(
                    update={
                        "status": BrowserSessionStatus.DEGRADED,
                        "pid": None,
                        "last_seen": self._clock(),
                        "last_error_code": "BROWSER_PROCESS_EXITED",
                    }
                )
                self._store.save(state)
                self._logger.event(
                    "BROWSER_PROCESS_EXITED",
                    "ERROR",
                    {"agent_id": self.agent_id, "browser_id": state.browser_id},
                )
                return state
            updated = state.model_copy(update={"last_seen": self._clock()})
            self._store.save(updated)
            return updated

    def _reattach(
        self,
        state: BrowserSessionState,
        profile_path: Path,
        *,
        allow_stopped: bool = False,
    ) -> BrowserSessionState | None:
        if state.status is BrowserSessionStatus.STOPPED and not allow_stopped:
            return None
        if state.pid is not None and self._is_running(state.pid):
            return state.model_copy(update={"last_seen": self._clock()})
        finder = getattr(self._process, "find_running", None)
        if not callable(finder):
            return None
        try:
            executable = self._resolver.resolve()
            pid = finder(executable, profile_path)
        except BrowserControlError:
            return None
        if pid is None:
            return None
        preserved = {
            BrowserSessionStatus.OPENED,
            BrowserSessionStatus.WAITING_LOGIN,
            BrowserSessionStatus.READY,
        }
        attached = state.model_copy(
            update={
                "status": state.status if state.status in preserved else BrowserSessionStatus.OPENED,
                "pid": pid,
                "last_seen": self._clock(),
                "last_error_code": None,
            }
        )
        self._store.save(attached)
        self._logger.event(
            "BROWSER_PROCESS_REATTACHED",
            "SUCCESS",
            {
                "agent_id": self.agent_id,
                "browser_id": attached.browser_id,
                "pid": pid,
                "profile_reference": self._profile.reference(),
            },
        )
        return attached

    def navigate(self, url: str) -> BrowserSessionState:
        self._require_enabled()
        target = _validate_navigation_url(url)
        with self._lock:
            state = self.browser_status()
            if state.pid is None or state.status not in {
                BrowserSessionStatus.OPENED,
                BrowserSessionStatus.WAITING_LOGIN,
                BrowserSessionStatus.READY,
            }:
                raise BrowserNavigationError("browser must be open before navigation")
            executable = self._resolver.resolve()
            try:
                self._process.navigate(executable, Path(state.profile_path), target)
            except BrowserControlError as exc:
                degraded = state.model_copy(
                    update={
                        "status": BrowserSessionStatus.DEGRADED,
                        "last_seen": self._clock(),
                        "last_error_code": type(exc).__name__.upper(),
                    }
                )
                self._store.save(degraded)
                self._logger.error("BROWSER_NAVIGATION_FAILED", exc)
                raise
            waiting = state.model_copy(
                update={
                    "status": BrowserSessionStatus.WAITING_LOGIN,
                    "last_seen": self._clock(),
                    "last_error_code": None,
                }
            )
            self._store.save(waiting)
            parsed = urlsplit(target)
            self._logger.event(
                "BROWSER_NAVIGATION_REQUESTED",
                "SUCCESS",
                {
                    "agent_id": self.agent_id,
                    "browser_id": state.browser_id,
                    "target_origin": f"{parsed.scheme}://{parsed.hostname}",
                    "human_interaction_required": True,
                },
            )
            return waiting

    def recover(self) -> BrowserSessionState:
        self._require_enabled()
        with self._lock:
            state = self.browser_status()
            if state.status not in {BrowserSessionStatus.DEGRADED, BrowserSessionStatus.FAILED}:
                return state
            if state.automatic_recovery_attempted:
                raise BrowserStateError("automatic browser recovery has already been attempted")
            recovering = state.model_copy(
                update={
                    "status": BrowserSessionStatus.RECOVERING,
                    "pid": None,
                    "generation": state.generation + 1,
                    "last_seen": self._clock(),
                    "automatic_recovery_attempted": True,
                    "last_error_code": None,
                }
            )
            self._store.save(recovering)
            self._logger.event(
                "BROWSER_RECOVERY_STARTED",
                "PENDING",
                {
                    "agent_id": self.agent_id,
                    "browser_id": state.browser_id,
                    "generation": recovering.generation,
                },
            )
            try:
                executable = self._resolver.resolve()
                pid = self._process.start(
                    executable,
                    self._profile.initialize(),
                    "about:blank",
                )
            except BrowserControlError as exc:
                failed = recovering.model_copy(
                    update={
                        "status": BrowserSessionStatus.FAILED,
                        "last_seen": self._clock(),
                        "last_error_code": type(exc).__name__.upper(),
                    }
                )
                self._store.save(failed)
                self._logger.error("BROWSER_RECOVERY_FAILED", exc)
                raise
            opened = recovering.model_copy(
                update={
                    "status": BrowserSessionStatus.OPENED,
                    "pid": pid,
                    "last_seen": self._clock(),
                    "last_error_code": None,
                }
            )
            self._store.save(opened)
            self._logger.event(
                "BROWSER_RECOVERY_COMPLETED",
                "SUCCESS",
                {
                    "agent_id": self.agent_id,
                    "browser_id": state.browser_id,
                    "generation": opened.generation,
                },
            )
            return opened

    def apply_login_observation(
        self,
        *,
        authenticated: bool,
        observation_reference: str,
    ) -> BrowserSessionState:
        """Apply a read-only observer result without exposing a login action."""

        if not re.fullmatch(r"sha256:[a-f0-9]{64}", observation_reference):
            raise BrowserStateError("login observation reference is invalid")
        with self._lock:
            state = self.browser_status()
            if state.pid is None or state.status not in {
                BrowserSessionStatus.OPENED,
                BrowserSessionStatus.WAITING_LOGIN,
                BrowserSessionStatus.READY,
            }:
                raise BrowserStateError("browser is unavailable for login observation")
            updated = state.model_copy(
                update={
                    "status": (
                        BrowserSessionStatus.READY
                        if authenticated
                        else BrowserSessionStatus.WAITING_LOGIN
                    ),
                    "last_seen": self._clock(),
                    "last_error_code": None,
                }
            )
            self._store.save(updated)
            self._logger.event(
                "BROWSER_LOGIN_OBSERVED",
                "SUCCESS",
                {
                    "agent_id": self.agent_id,
                    "browser_id": updated.browser_id,
                    "authenticated": authenticated,
                    "observation_reference": observation_reference,
                },
            )
            return updated

    def close_resources(self) -> None:
        self._logger.close()

    def _initial_stopped_state(self) -> BrowserSessionState:
        now = self._clock()
        state = BrowserSessionState(
            browser_id=f"browser:{uuid.uuid4()}",
            agent_id=self.agent_id,
            profile_path=str(self._profile.profile_path),
            status=BrowserSessionStatus.STOPPED,
            created_at=now,
            last_seen=now,
        )
        self._store.save(state)
        return state

    def _load_checked(self) -> BrowserSessionState | None:
        state = self._store.load()
        if state is None:
            return None
        if state.agent_id != self.agent_id:
            raise BrowserStateError("browser session belongs to another Agent")
        if Path(state.profile_path).resolve() != self._profile.profile_path:
            raise BrowserStateError("browser session profile escaped the Agent boundary")
        return state

    def _is_running(self, pid: int) -> bool:
        try:
            executable = self._resolver.resolve()
        except BrowserControlError:
            return False
        return self._process.is_running(pid, executable)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise BrowserDisabledError(
                "browser control is disabled; browser_enabled must be explicitly true"
            )


def _validate_navigation_url(value: str) -> str:
    target = value.strip()
    if len(target) > 2048 or any(ord(character) < 32 for character in target):
        raise BrowserNavigationError("browser navigation URL is invalid")
    parsed = urlsplit(target)
    if parsed.username or parsed.password or not parsed.hostname:
        raise BrowserNavigationError("browser navigation URL cannot contain credentials")
    if parsed.fragment:
        raise BrowserNavigationError("browser navigation URL fragments are not allowed")
    sensitive_query_parts = {
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
    if any(
        any(part in key.casefold() for part in sensitive_query_parts)
        for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        raise BrowserNavigationError("browser navigation URL contains a sensitive query")
    loopback = parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise BrowserNavigationError("browser navigation requires HTTPS or loopback HTTP")
    return target


def _windows_process_image(pid: int) -> str | None:
    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    query_image.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not query_image(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        close_handle(handle)


__all__ = [
    "BROWSER_SESSION_SCHEMA_VERSION",
    "BrowserCommandInterface",
    "BrowserControlError",
    "BrowserDisabledError",
    "BrowserEnvironmentError",
    "BrowserNavigationError",
    "BrowserProcessController",
    "BrowserProfileManager",
    "BrowserSessionState",
    "BrowserSessionStatus",
    "BrowserSessionStore",
    "BrowserStateError",
    "ChannelAgentBrowserManager",
    "WindowsBrowserProcessController",
    "WindowsEdgeExecutableResolver",
]
