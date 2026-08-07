from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from channel_agent.client import (
    AgentConnectionError,
    AgentRejectedError,
    ChannelEngineClient,
)
from channel_agent.config import AgentConfigError, ChannelAgentConfig, load_agent_config
from channel_agent.contract import (
    AgentHeartbeatAck,
    AgentRegistrationResponse,
    AgentRuntimeStatus,
    ManagedAgentConfig,
)
from channel_agent.heartbeat import HeartbeatManager
from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_agent.logger import SafeAgentLogger, sanitize
from channel_agent.runtime import ChannelAgentRuntime


NOW = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)


def config(tmp_path: Path) -> ChannelAgentConfig:
    return ChannelAgentConfig(
        server_url="http://127.0.0.1:18080",
        agent_id="agent-foundation-001",
        device_id="device-foundation-001",
        heartbeat_interval_seconds=0.05,
        log_directory=tmp_path / "logs",
    )


class FakeChannelEngineClient:
    def __init__(self) -> None:
        self.register_calls: list[dict[str, object]] = []
        self.heartbeat_calls: list[dict[str, object]] = []
        self.fetch_count = 0
        self.fail_register = False
        self.fail_heartbeat = False
        self.closed = False
        self.managed = ManagedAgentConfig(
            revision="foundation-test-v1",
            heartbeat_interval_seconds=0.05,
        )

    def register(self, **kwargs: object) -> AgentRegistrationResponse:
        self.register_calls.append(kwargs)
        if self.fail_register:
            raise AgentConnectionError("synthetic connection failure")
        return AgentRegistrationResponse(
            registration_id="agent-registration:test",
            identity=AgentIdentity(
                agent_id="agent-foundation-001",
                device_id="device-foundation-001",
                status=AgentIdentityStatus.UNBOUND,
                created_at=NOW,
                updated_at=NOW,
            ),
            production_eligible=False,
            config=self.managed,
            server_time=NOW,
        )

    def report_status(self, **kwargs: object) -> AgentHeartbeatAck:
        self.heartbeat_calls.append(kwargs)
        if self.fail_heartbeat:
            raise AgentConnectionError("synthetic heartbeat failure")
        return AgentHeartbeatAck(
            identity_status=AgentIdentityStatus.UNBOUND,
            production_eligible=False,
            config_revision=self.managed.revision,
            server_time=NOW,
        )

    def fetch_config(self) -> ManagedAgentConfig:
        self.fetch_count += 1
        return self.managed

    def close(self) -> None:
        self.closed = True


def runtime(tmp_path: Path, client: FakeChannelEngineClient) -> ChannelAgentRuntime:
    logger = SafeAgentLogger(tmp_path / "logs" / "agent.jsonl")
    return ChannelAgentRuntime(
        config(tmp_path),
        client,
        logger,
        hostname="customer-service-pc",
        clock=lambda: NOW,
    )


def test_config_loads_required_fields_and_rejects_plaintext_credentials(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps(config(tmp_path).model_dump(mode="json")),
        encoding="utf-8",
    )

    loaded = load_agent_config(path)

    assert loaded.agent_id == "agent-foundation-001"
    assert loaded.device_id == "device-foundation-001"
    assert loaded.server_url == "http://127.0.0.1:18080"
    unsafe = json.loads(path.read_text(encoding="utf-8"))
    unsafe["token"] = "plaintext-must-never-be-stored"
    path.write_text(json.dumps(unsafe), encoding="utf-8")
    with pytest.raises(AgentConfigError, match="sensitive field"):
        load_agent_config(path)


def test_agent_start_connects_and_reaches_online(tmp_path: Path) -> None:
    client = FakeChannelEngineClient()
    agent = runtime(tmp_path, client)

    snapshot = agent.start(background_heartbeat=False)

    assert snapshot.status is AgentRuntimeStatus.ONLINE
    assert snapshot.registered is True
    assert snapshot.registration_id == "agent-registration:test"
    assert snapshot.config_revision == "foundation-test-v1"
    assert client.register_calls[0]["status"] is AgentRuntimeStatus.STARTING
    agent.close()


def test_heartbeat_reports_required_state_and_stop_is_clean(tmp_path: Path) -> None:
    client = FakeChannelEngineClient()
    agent = runtime(tmp_path, client)
    agent.start(background_heartbeat=False)

    heartbeat = agent.heartbeat_once()
    stopped = agent.stop()

    assert heartbeat.status is AgentRuntimeStatus.ONLINE
    assert heartbeat.last_heartbeat == NOW
    assert client.heartbeat_calls[0] == {
        "hostname": "customer-service-pc",
        "status": AgentRuntimeStatus.ONLINE,
        "timestamp": NOW,
    }
    assert client.heartbeat_calls[-1]["status"] is AgentRuntimeStatus.STOPPED
    assert stopped.status is AgentRuntimeStatus.STOPPED
    agent.close()


def test_connection_failure_degrades_then_next_heartbeat_recovers(
    tmp_path: Path,
) -> None:
    client = FakeChannelEngineClient()
    agent = runtime(tmp_path, client)
    assert agent.start(background_heartbeat=False).status is AgentRuntimeStatus.ONLINE
    client.fail_heartbeat = True

    degraded = agent.heartbeat_once()

    assert degraded.status is AgentRuntimeStatus.DEGRADED
    assert degraded.consecutive_failures == 1
    assert degraded.last_error_code == "AGENTCONNECTIONERROR"
    client.fail_heartbeat = False
    recovered = agent.heartbeat_once()
    assert recovered.status is AgentRuntimeStatus.ONLINE
    assert recovered.consecutive_failures == 0
    assert recovered.last_error_code is None
    agent.close()


def test_initial_connection_failure_is_recovered_by_heartbeat(tmp_path: Path) -> None:
    client = FakeChannelEngineClient()
    client.fail_register = True
    agent = runtime(tmp_path, client)

    degraded = agent.start(background_heartbeat=False)

    assert degraded.status is AgentRuntimeStatus.DEGRADED
    assert degraded.registered is False
    client.fail_register = False
    recovered = agent.heartbeat_once()
    assert recovered.status is AgentRuntimeStatus.ONLINE
    assert recovered.registered is True
    agent.close()


def test_engine_restart_triggers_one_registration_recovery(tmp_path: Path) -> None:
    client = FakeChannelEngineClient()
    agent = runtime(tmp_path, client)
    agent.start(background_heartbeat=False)
    original_report = client.report_status
    attempts = 0

    def restarted_report(**kwargs: object) -> AgentHeartbeatAck:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AgentRejectedError(
                "registration was lost during Engine restart",
                status_code=404,
                error_code="AGENT_NOT_REGISTERED",
            )
        return original_report(**kwargs)

    client.report_status = restarted_report  # type: ignore[method-assign]

    recovered = agent.heartbeat_once()

    assert recovered.status is AgentRuntimeStatus.ONLINE
    assert recovered.registered is True
    assert len(client.register_calls) == 2
    assert attempts == 2
    agent.close()


def test_authorization_rejection_does_not_retry_registration(tmp_path: Path) -> None:
    client = FakeChannelEngineClient()
    agent = runtime(tmp_path, client)
    agent.start(background_heartbeat=False)

    def rejected_report(**_kwargs: object) -> AgentHeartbeatAck:
        raise AgentRejectedError(
            "identity is disabled",
            status_code=403,
            error_code="AGENT_IDENTITY_DISABLED",
        )

    client.report_status = rejected_report  # type: ignore[method-assign]

    degraded = agent.heartbeat_once()

    assert degraded.status is AgentRuntimeStatus.DEGRADED
    assert len(client.register_calls) == 1
    agent.close()


def test_windows_powershell_binding_code_pipeline_is_normalized(monkeypatch) -> None:
    monkeypatch.setattr(
        "channel_agent.windows_app.sys.stdin",
        io.StringIO("\ufeffE\x00E\x00E\x00E\x00\r\x00\n\x00"),
    )

    from channel_agent import windows_app

    assert windows_app._read_binding_code_from_stdin() == "EEEE"


def test_heartbeat_manager_is_restartable_and_run_once_is_deterministic() -> None:
    calls: list[str] = []
    manager = HeartbeatManager(lambda: calls.append("tick"), 0.05)

    manager.run_once()
    manager.start()
    manager.stop()
    manager.start()
    manager.stop()

    assert calls == ["tick"]
    assert manager.is_running is False


def test_local_log_redacts_sensitive_keys_and_values(tmp_path: Path) -> None:
    logger = SafeAgentLogger(tmp_path / "agent.jsonl")
    logger.event(
        "AGENT_TEST",
        "ERROR",
        {
            "token": "top-secret-value",
            "detail": "password=hidden-value",
            "url": "https://user:pass@example.invalid/path",
        },
    )
    logger.close()
    content = (tmp_path / "agent.jsonl").read_text(encoding="utf-8")

    assert "top-secret-value" not in content
    assert "hidden-value" not in content
    assert "user:pass" not in content
    assert "[REDACTED]" in content
    assert sanitize({"cookie": "private"}) == {"cookie": "[REDACTED]"}


def test_agent_client_exposes_control_plane_operations_only() -> None:
    public = {
        name
        for name in dir(ChannelEngineClient)
        if not name.startswith("_")
    }

    assert {"register", "report_status", "fetch_config", "close"} <= public
    assert "send_message" not in public
    assert "receive_messages" not in public
    assert "execute" not in public
    assert "login" not in public
