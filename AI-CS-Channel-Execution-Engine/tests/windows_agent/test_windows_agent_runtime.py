from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_cs_agent.browser import BrowserError, BrowserSnapshot, WindowsBrowserManager
from ai_cs_agent.config import BrowserConfig, ConfigError, load_config
from ai_cs_agent.execution import (
    ExecutionBoundary,
    ExecutionContext,
    ExecutionDenied,
    ExecutionReceipt,
    ReceiptLedger,
    ReceiptOutcome,
)
from ai_cs_agent.gateway import GatewayHealth
from ai_cs_agent.models import AgentStatus, RuntimeState, utc_now_text
from ai_cs_agent.runtime import AgentRuntime
from ai_cs_agent.security import CredentialMaterial


class TestCredentialProvider:
    def acquire(self, reference: str) -> CredentialMaterial:
        return CredentialMaterial(reference, b"x" * 32)


class HealthyGateway:
    def health_check(self) -> GatewayHealth:
        return GatewayHealth(
            status="HEALTHY",
            service="ai-cs-gateway",
            contract_version="1.0",
            version="test",
            capabilities=("decision-v1",),
            reachable=True,
            real_ai_cs_connected=True,
            timestamp=utc_now_text(),
            details={},
        )


class AvailableBrowser:
    def __init__(self, home: Path) -> None:
        self.home = home

    def detect_chrome(self) -> Path:
        return self.home / "test-support" / "chrome.exe"

    def initialize_profile(self) -> Path:
        path = self.home / "runtime" / "browser-profile"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def snapshot(self) -> BrowserSnapshot:
        return BrowserSnapshot(
            chrome_status="AVAILABLE",
            chrome_path=None,
            profile_status="INITIALIZED",
            profile_reference="runtime/browser-profile",
            process_status="STOPPED",
            session_status="AUTH_REQUIRED",
            checked_at=utc_now_text(),
        )


def write_config(path: Path, **overrides: object) -> Path:
    value = {
        "schema_version": "1.0",
        "agent": {
            "agent_id": "agent-001",
            "device_id": "device-001",
            "customer_service_identity": "operator-001",
            "runtime_mode": "STAGING",
        },
        "server": {
            "address": "http://127.0.0.1:18021",
            "client_id": "channel-agent",
            "key_id": "key-001",
            "credential_reference": "wincred://AI-CS-Agent/Gateway/key-001",
            "timeout_seconds": 0.2,
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
    for key, item in overrides.items():
        value[key] = item
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def runtime_for(home: Path, config: Path, gateway: object | None = None) -> AgentRuntime:
    return AgentRuntime(
        home,
        config,
        credential_provider=TestCredentialProvider(),
        gateway_factory=lambda _config, _provider: gateway or HealthyGateway(),
        browser_factory=lambda current_home, _config: AvailableBrowser(current_home),
        heartbeat_seconds=0.02,
    )


def test_config_is_strict_and_secret_reference_only(tmp_path: Path) -> None:
    config = write_config(tmp_path / "agent.json")
    loaded = load_config(config)
    assert loaded.server.credential_reference.startswith("wincred://")
    value = json.loads(config.read_text(encoding="utf-8"))
    value["server"]["token"] = "plaintext-forbidden"
    config.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ConfigError, match="plaintext credential"):
        load_config(config)


def test_browser_profile_is_isolated_and_never_uses_default_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"MZ-test-support")
    home = tmp_path / "agent-home"
    manager = WindowsBrowserManager(
        home,
        BrowserConfig(
            chrome_path=str(chrome),
            profile_directory="runtime/browser-profile",
        ),
    )
    assert manager.detect_chrome() == chrome.resolve()
    profile = manager.initialize_profile()
    assert profile.is_relative_to(home.resolve())
    assert (profile / manager.MARKER_NAME).exists()

    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    default_profile = local_app_data / "Google" / "Chrome" / "User Data" / "Default"
    unsafe = WindowsBrowserManager(
        home,
        BrowserConfig(
            chrome_path=str(chrome),
            profile_directory=str(default_profile),
        ),
    )
    with pytest.raises(BrowserError, match="default Chrome profile"):
        unsafe.profile_path()


def test_lifecycle_start_status_stop_and_persisted_kill_switch(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    worker = threading.Thread(target=runtime.run)
    worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if runtime.status().agent_status is AgentStatus.RUNNING:
            break
        time.sleep(0.01)
    assert runtime.status().agent_status is AgentStatus.RUNNING
    assert runtime.status().safety["kill_switch"] is True
    runtime.request_stop()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert runtime.status().agent_status is AgentStatus.STOPPED
    runtime.set_kill_switch(False, operator="test-operator")
    assert runtime.status().safety["kill_switch"] is False
    recovered = runtime_for(home, config).preflight()
    assert recovered.safety["kill_switch"] is False


def test_invalid_config_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(
        home / "config" / "agent.json",
        safety={"kill_switch": True, "manual_approval": False, "auto_reply": False},
    )
    state = runtime_for(home, config).preflight()
    assert state.agent_status is AgentStatus.FAILED
    assert state.last_error and state.last_error["code"] == "CONFIGERROR"


def test_server_unreachable_stops_before_browser_ready(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    value = json.loads(config.read_text(encoding="utf-8"))
    value["server"]["address"] = "http://127.0.0.1:1"
    value["server"]["timeout_seconds"] = 0.1
    config.write_text(json.dumps(value), encoding="utf-8")
    runtime = AgentRuntime(
        home,
        config,
        credential_provider=TestCredentialProvider(),
        browser_factory=lambda current_home, _config: AvailableBrowser(current_home),
        heartbeat_seconds=0.02,
    )
    state = runtime.preflight()
    assert state.agent_status is AgentStatus.FAILED
    assert state.first_launch_state.value == "FAILED"
    assert state.browser == {}


def test_session_recovery_requires_login_revalidation(tmp_path: Path) -> None:
    home = tmp_path / "agent-home"
    config = write_config(home / "config" / "agent.json")
    runtime = runtime_for(home, config)
    previous = RuntimeState(
        agent_status=AgentStatus.STOPPED,
        session={
            "session_id": "session-previous",
            "status": "CONNECTED",
            "credential_reference": "wincred://AI-CS-Agent/Gateway/key-001",
        },
    )
    runtime.state_store.save(previous)
    recovered = runtime.preflight()
    assert recovered.session["status"] == "AUTH_REQUIRED"
    assert recovered.session["recovery_reason"] == "LOGIN_REVALIDATION_REQUIRED"
    assert recovered.recovery_count == 1


def test_execution_boundary_and_unknown_receipt_are_fail_closed(tmp_path: Path) -> None:
    context = ExecutionContext(
        execution_id="execution-1",
        decision_id="decision-1",
        approval_id="approval-1",
        decision_status="APPROVED",
        approval_status="APPROVED",
        execution_status="RUNNING",
        lease_owner="worker-1",
        lease_token="lease-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        idempotency_key="send-1",
    )
    with pytest.raises(ExecutionDenied, match="kill switch"):
        ExecutionBoundary.authorize(
            context,
            kill_switch=True,
            worker_id="worker-1",
            lease_token="lease-1",
        )
    missing_approval = replace(context, approval_status="PENDING")
    with pytest.raises(ExecutionDenied, match="Approval"):
        ExecutionBoundary.authorize(
            missing_approval,
            kill_switch=False,
            worker_id="worker-1",
            lease_token="lease-1",
        )
    ExecutionBoundary.authorize(
        context,
        kill_switch=False,
        worker_id="worker-1",
        lease_token="lease-1",
    )
    receipt = ExecutionReceipt(
        receipt_id="receipt-1",
        execution_id="execution-1",
        decision_id="decision-1",
        approval_id="approval-1",
        outcome=ReceiptOutcome.UNKNOWN,
        idempotency_key="send-1",
        recorded_at=utc_now_text(),
        error_code="TRANSPORT_OUTCOME_UNKNOWN",
        reconciliation_required=True,
        automatic_retry_allowed=False,
    )
    ledger = ReceiptLedger(tmp_path / "receipts.jsonl")
    assert ledger.append(receipt) == receipt
    assert ledger.append(receipt) == receipt
    assert len((tmp_path / "receipts.jsonl").read_text().splitlines()) == 1
