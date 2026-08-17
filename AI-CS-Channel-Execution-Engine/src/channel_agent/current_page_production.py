from __future__ import annotations

import json
import os
import socket
import sqlite3
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .binding import atomic_write_bytes
from .controlled_auto_runtime import (
    ControlledAutoRuntimeError,
    ControlledAutoRuntimeStateStore,
)
from .operator_control import operator_pause_requested

CURRENT_PAGE_SCOPE = "CURRENT_ACTIVE_CONVERSATION_ONLY"


class CurrentPageProductionConfig(BaseModel):
    """Credential-free references for the single-machine production owner."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["current-page-auto-production-config.v1"] = (
        "current-page-auto-production-config.v1"
    )
    ce_root: Path
    ai_cs_root: Path
    ai_cs_config_path: Path
    data_root: Path
    python_executable: Path
    agent_executable: Path
    engine_database_path: Path
    assistant_root: Path
    host_evidence_root: Path
    gateway_key_reference: Path
    send_selector_contract: Path
    catalog_store_id: str = Field(min_length=1, max_length=160)
    catalog_tenant_id: str = Field(min_length=1, max_length=160)
    host_port: int = Field(default=18443, ge=1, le=65535)
    bridge_port: int = Field(default=8430, ge=1, le=65535)
    ai_gateway_port: int = Field(default=8420, ge=1, le=65535)
    ai_platform_port: int = Field(default=8422, ge=1, le=65535)
    allowed_origin: str = "http://127.0.0.1:8421"
    observation_scope: Literal["CURRENT_ACTIVE_CONVERSATION_ONLY"] = (
        CURRENT_PAGE_SCOPE
    )
    automatic_navigation_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_ports(self) -> CurrentPageProductionConfig:
        ports = {
            self.host_port,
            self.bridge_port,
            self.ai_gateway_port,
            self.ai_platform_port,
        }
        if len(ports) != 4:
            raise ValueError("production component ports must be unique")
        return self

    @property
    def status_path(self) -> Path:
        return (
            self.data_root
            / "runtime"
            / "current-page-production-supervisor.json"
        )

    @property
    def runtime_store_path(self) -> Path:
        return self.assistant_root / "controlled-auto-runtime.sqlite3"

    @classmethod
    def load(cls, path: str | Path) -> CurrentPageProductionConfig:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


@dataclass
class _Child:
    process: subprocess.Popen[bytes]
    started_at: datetime


@dataclass
class CurrentPageProductionSupervisor:
    config: CurrentPageProductionConfig
    poll_seconds: float = 2.0
    _children: dict[str, _Child] = field(default_factory=dict, init=False)
    _last_start_attempt: dict[str, float] = field(default_factory=dict, init=False)
    _last_error: dict[str, str] = field(default_factory=dict, init=False)

    def validate_installation(self) -> None:
        required_files = {
            "python": self.config.python_executable,
            "agent": self.config.agent_executable,
            "AI-CS start script": (
                self.config.ai_cs_root
                / "scripts"
                / "windows"
                / "start_ai_customer_service.ps1"
            ),
            "AI-CS RC5 runtime config": self.config.ai_cs_config_path,
            "Host start script": (
                self.config.ce_root
                / "scripts"
                / "windows"
                / "Start-Rc5HotValidationHost.ps1"
            ),
            "bridge": (
                self.config.ce_root
                / "scripts"
                / "run_channel_agent_assistant_bridge.py"
            ),
            "AUTO runner": (
                self.config.ce_root
                / "scripts"
                / "run_controlled_pdd_reply_pilot.py"
            ),
            "engine database": self.config.engine_database_path,
            "gateway key reference": self.config.gateway_key_reference,
            "send selector contract": self.config.send_selector_contract,
        }
        missing = [name for name, path in required_files.items() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "CURRENT_PAGE_PRODUCTION_DEPENDENCY_MISSING:"
                + ",".join(sorted(missing))
            )
        agent_config_path = self.config.data_root / "config" / "agent.json"
        try:
            agent_config = json.loads(agent_config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("CURRENT_PAGE_AGENT_CONFIG_INVALID") from exc
        if agent_config.get("pdd_conversation_navigation_enabled") is not False:
            raise RuntimeError("AUTOMATIC_PDD_CONVERSATION_NAVIGATION_MUST_BE_DISABLED")
        if agent_config.get("message_observation_enabled") is not True:
            raise RuntimeError("REAL_PDD_MESSAGE_OBSERVATION_MUST_BE_ENABLED")

    def run_forever(self) -> None:
        self.validate_installation()
        self.config.status_path.parent.mkdir(parents=True, exist_ok=True)
        with self._single_instance_lock():
            try:
                while True:
                    self.run_once()
                    time.sleep(max(self.poll_seconds, 0.25))
            except KeyboardInterrupt:
                self._publish_status(
                    component_health=self._component_health(),
                    supervisor_state="STOPPED",
                )

    @contextmanager
    def _single_instance_lock(self) -> Iterator[None]:
        """Prevent two supervisors from owning the same desktop runtime."""

        lock_path = (
            self.config.data_root
            / "runtime"
            / "current-page-production-supervisor.lock"
        )
        owner_path = (
            self.config.data_root
            / "runtime"
            / "current-page-production-supervisor.owner"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                "CURRENT_PAGE_PRODUCTION_SUPERVISOR_ALREADY_RUNNING"
            ) from exc
        try:
            atomic_write_bytes(owner_path, str(os.getpid()).encode("ascii"))
            yield
        finally:
            try:
                owner_path.unlink(missing_ok=True)
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def run_once(self) -> dict[str, Any]:
        self._reap_children()
        if operator_pause_requested(self.config.data_root):
            # A human safe stop is different from a crash. Keep the
            # supervisor available for the next explicit start, but remove
            # effective AUTO ownership and never relaunch the Agent.
            self._stop_child("runner")
            self._stop_child("bridge")
            return self._publish_status(
                component_health=self._component_health(),
                supervisor_state="PAUSED_BY_OPERATOR",
            )
        health = self._component_health()

        if not health["agent"]:
            self._start_agent()
        if not (health["ai_gateway"] and health["ai_platform"]):
            self._start_ai_cs()

        health = self._component_health()
        if health["ai_gateway"] and not health["host"]:
            self._start_host()

        health = self._component_health()
        live_scope = self._live_scope_ready()
        if not live_scope or not all(
            health[name] for name in ("agent", "ai_gateway", "ai_platform", "host")
        ):
            # Desired AUTO state stays durable, but its effective owner must
            # disappear immediately when the currently opened PDD page can no
            # longer be proven.  A later healthy page starts a fresh Runner.
            self._stop_child("runner")
        if (
            health["agent"]
            and health["ai_gateway"]
            and health["ai_platform"]
            and health["host"]
            and live_scope
            and not health["bridge"]
        ):
            self._start_bridge()

        health = self._component_health()
        if health["bridge"] and live_scope and not health["runner"]:
            self._start_runner()

        health = self._component_health()
        state = self._classify_state(health, live_scope=live_scope)
        return self._publish_status(
            component_health=health,
            supervisor_state=state,
        )

    def _component_health(self) -> dict[str, bool]:
        return {
            # The desktop bootstrap is intentionally protected by a local
            # session cookie.  A loopback TCP probe verifies the Agent without
            # weakening that browser-session boundary.
            "agent": self._tcp_ok(self._agent_desktop_port()),
            "ai_gateway": self._http_ok(
                f"http://127.0.0.1:{self.config.ai_gateway_port}/api/health"
            ),
            "ai_platform": self._http_ok(
                f"http://127.0.0.1:{self.config.ai_platform_port}/health"
            ),
            "host": self._http_ok(
                f"https://127.0.0.1:{self.config.host_port}/health",
                allow_loopback_tls=True,
            ),
            "bridge": self._http_ok(
                f"http://127.0.0.1:{self.config.bridge_port}/health"
            ),
            "runner": self._runner_is_fresh(),
        }

    def _agent_desktop_port(self) -> int:
        value = json.loads(
            (self.config.data_root / "config" / "agent.json").read_text(
                encoding="utf-8"
            )
        )
        return int(value.get("desktop_ui_port") or 60801)

    @staticmethod
    def _tcp_ok(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            return False

    @staticmethod
    def _http_ok(url: str, *, allow_loopback_tls: bool = False) -> bool:
        context = None
        if allow_loopback_tls:
            context = ssl._create_unverified_context()
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1.0, context=context) as response:
                return 200 <= int(response.status) < 300
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def _live_scope_ready(self) -> bool:
        state_path = self.config.data_root / "runtime" / "channel-agent-state.json"
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return bool(
            value.get("identity_status") == "ACTIVE"
            and value.get("pdd_login_state") == "CUSTOMER_SERVICE_READY"
            and value.get("observer_status") == "OBSERVING"
            and value.get("active_store_id") == self.config.catalog_store_id
            and isinstance(value.get("pdd_store_id"), str)
            and str(value.get("pdd_store_id")).strip()
        )

    def _runner_is_fresh(self) -> bool:
        path = (
            self.config.data_root
            / "runtime"
            / "controlled-auto-public-status.json"
        )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(str(value["updated_at"]))
            age = (datetime.now(UTC) - updated_at.astimezone(UTC)).total_seconds()
        except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError):
            return False
        return bool(
            value.get("schema_version") == "controlled-auto-public-status.v1"
            and value.get("runner_active") is True
            and 0.0 <= age <= 10.0
        )

    def _start_agent(self) -> None:
        self._start_child(
            "agent",
            [str(self.config.agent_executable), "--background"],
            cwd=self.config.agent_executable.parent,
            minimum_retry_seconds=20.0,
        )

    def _start_ai_cs(self) -> None:
        self._start_child(
            "ai-cs-start",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(
                    self.config.ai_cs_root
                    / "scripts"
                    / "windows"
                    / "start_ai_customer_service.ps1"
                ),
                "-ConfigPath",
                str(self.config.ai_cs_config_path),
                "-NoBrowser",
                "-Mode",
                "Local",
            ],
            cwd=self.config.ai_cs_root,
            minimum_retry_seconds=90.0,
        )

    def _start_host(self) -> None:
        self.config.host_evidence_root.mkdir(parents=True, exist_ok=True)
        self.config.assistant_root.mkdir(parents=True, exist_ok=True)
        self._start_child(
            "host-start",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(
                    self.config.ce_root
                    / "scripts"
                    / "windows"
                    / "Start-Rc5HotValidationHost.ps1"
                ),
                "-EvidenceRoot",
                str(self.config.host_evidence_root),
                "-GatewayKeyReference",
                str(self.config.gateway_key_reference),
                "-Port",
                str(self.config.host_port),
                "-DatabasePath",
                str(self.config.engine_database_path),
                "-OfflineRuntimeRoot",
                str(self.config.assistant_root),
                "-GatewayBaseUrl",
                f"http://127.0.0.1:{self.config.ai_gateway_port}",
                "-CatalogStoreId",
                self.config.catalog_store_id,
                "-CatalogTenantId",
                self.config.catalog_tenant_id,
            ],
            cwd=self.config.ce_root,
            minimum_retry_seconds=60.0,
        )

    def _start_bridge(self) -> None:
        self._start_child(
            "bridge",
            [
                str(self.config.python_executable),
                str(
                    self.config.ce_root
                    / "scripts"
                    / "run_channel_agent_assistant_bridge.py"
                ),
                "--data-root",
                str(self.config.data_root),
                "--assistant-root",
                str(self.config.assistant_root),
                "--engine-database-path",
                str(self.config.engine_database_path),
                "--send-selector-contract",
                str(self.config.send_selector_contract),
                "--enable-controlled-send",
                "--port",
                str(self.config.bridge_port),
                "--allowed-origin",
                self.config.allowed_origin,
            ],
            cwd=self.config.ce_root,
            minimum_retry_seconds=10.0,
        )

    def _start_runner(self) -> None:
        self._start_child(
            "runner",
            [
                str(self.config.python_executable),
                str(
                    self.config.ce_root
                    / "scripts"
                    / "run_controlled_pdd_reply_pilot.py"
                ),
                "--data-root",
                str(self.config.data_root),
                "--assistant-root",
                str(self.config.assistant_root),
                "--bridge-url",
                f"http://127.0.0.1:{self.config.bridge_port}",
                "--allowed-origin",
                self.config.allowed_origin,
                "run-production-auto",
                "--operator-reference",
                "current-page-production-supervisor",
                "--poll-seconds",
                "0.5",
                "--execute-real-send",
            ],
            cwd=self.config.ce_root,
            minimum_retry_seconds=10.0,
        )

    def _start_child(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path,
        minimum_retry_seconds: float,
    ) -> None:
        current = self._children.get(name)
        if current is not None and current.process.poll() is None:
            return
        now = time.monotonic()
        if now - self._last_start_attempt.get(name, 0.0) < minimum_retry_seconds:
            return
        self._last_start_attempt[name] = now
        log_root = self.config.data_root / "runtime"
        log_root.mkdir(parents=True, exist_ok=True)
        stdout_path = log_root / f"current-page-{name}.stdout.log"
        stderr_path = log_root / f"current-page-{name}.stderr.log"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.config.ce_root / "src")
        environment["AI_CS_CHANNEL_AGENT_DATA_ROOT"] = str(self.config.data_root)
        try:
            stdout = stdout_path.open("ab")
            stderr = stderr_path.open("ab")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if os.name == "nt"
                        else 0
                    ),
                )
            finally:
                stdout.close()
                stderr.close()
            self._children[name] = _Child(process, datetime.now(UTC))
            self._last_error.pop(name, None)
        except OSError as exc:
            self._last_error[name] = type(exc).__name__

    def _reap_children(self) -> None:
        for name, child in tuple(self._children.items()):
            code = child.process.poll()
            if code is None:
                continue
            if code != 0:
                self._last_error[name] = f"EXIT_{code}"
            self._children.pop(name, None)

    def _stop_child(self, name: str) -> None:
        child = self._children.pop(name, None)
        if child is None or child.process.poll() is not None:
            return
        child.process.terminate()
        try:
            child.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            child.process.kill()
            child.process.wait(timeout=5.0)

    def _desired_auto_enabled(self) -> bool:
        try:
            state = ControlledAutoRuntimeStateStore(
                self.config.runtime_store_path
            ).load()
        except (OSError, sqlite3.Error, ValueError, ControlledAutoRuntimeError):
            return False
        return bool(
            state.runtime_mode == "PRODUCTION_AUTO"
            and state.production_real_send_enabled
            and state.controlled_store_auto_enabled
            and not state.kill_switch_enabled
        )

    @staticmethod
    def _classify_state(
        health: dict[str, bool], *, live_scope: bool
    ) -> str:
        base = (
            health["agent"]
            and health["ai_gateway"]
            and health["ai_platform"]
            and health["host"]
        )
        if not base:
            return "STARTING"
        if not live_scope:
            return "WAITING_FOR_CURRENT_PDD_CONVERSATION"
        if health["bridge"] and health["runner"]:
            return "READY"
        return "RECOVERING_AUTO_COMPONENTS"

    def _publish_status(
        self,
        *,
        component_health: dict[str, bool],
        supervisor_state: str,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": "current-page-auto-production-status.v1",
            "supervisor_active": supervisor_state != "STOPPED",
            "supervisor_pid": os.getpid(),
            "supervisor_state": supervisor_state,
            "desired_auto_reply_enabled": self._desired_auto_enabled(),
            "observation_scope": CURRENT_PAGE_SCOPE,
            "automatic_navigation_enabled": False,
            "components": component_health,
            "component_errors": dict(sorted(self._last_error.items())),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        atomic_write_bytes(
            self.config.status_path,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        return payload


__all__ = [
    "CURRENT_PAGE_SCOPE",
    "CurrentPageProductionConfig",
    "CurrentPageProductionSupervisor",
]
