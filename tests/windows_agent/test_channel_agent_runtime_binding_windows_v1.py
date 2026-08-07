from __future__ import annotations

import io
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.binding import AgentEnrollmentGrantRequest
from channel_agent.client import ChannelEngineClient
from channel_agent.config import ChannelAgentConfig
from channel_agent.identity import AgentIdentityStatus
from channel_agent import windows_app
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.security.rbac import (
    OperatorPrincipal,
    OperatorRole,
)


NOW = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)
CODE = "D" * 32


def test_windows_enrollment_saves_public_binding_without_code(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    data_root = tmp_path / "data"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        ChannelAgentConfig(
            server_url="https://testserver",
            agent_id="agent-windows-binding-001",
            device_id="device-windows-binding-001",
            log_directory=tmp_path / "logs",
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    admin = OperatorPrincipal(
        principal_id="admin-windows-binding",
        roles=frozenset({OperatorRole.ADMIN}),
        identity_provider="windows-binding-test",
        authenticated_at=NOW,
    )
    registry.issue_enrollment_grant(
        AgentEnrollmentGrantRequest(
            agent_id="agent-windows-binding-001",
            device_id="device-windows-binding-001",
            user_reference="user-windows-binding-001",
            store_references=("store-windows-a", "store-windows-b"),
            reason="approved Windows device enrollment",
        ),
        admin,
    )
    app = FastAPI()
    app.include_router(create_channel_agent_node_router(registry))
    transport = TestClient(app, base_url="https://testserver")

    def client_factory(config: ChannelAgentConfig) -> ChannelEngineClient:
        return ChannelEngineClient(config, http_client=transport)

    monkeypatch.setattr(windows_app, "ChannelEngineClient", client_factory)
    monkeypatch.setattr(windows_app.sys, "stdin", io.StringIO(CODE + "\n"))

    exit_code = windows_app.main(
        [
            "enroll",
            "--data-root",
            str(data_root),
            "--config",
            str(config_path),
            "--binding-code-stdin",
        ]
    )
    status_code = windows_app.main(
        ["binding-status", "--data-root", str(data_root)]
    )
    output = capsys.readouterr().out
    binding_path = data_root / "runtime" / "agent-binding.json"
    state_path = data_root / "runtime" / "channel-agent-state.json"
    binding_text = binding_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert status_code == 0
    assert '"identity_status": "BOUND"' in output
    assert '"store-windows-b"' in output
    assert CODE not in output
    assert CODE not in binding_text
    assert "binding_code" not in binding_text.casefold()
    assert state_path.is_file()
    assert registry.identity_snapshot(
        "agent-windows-binding-001"
    ).status is AgentIdentityStatus.BOUND
    transport.close()
