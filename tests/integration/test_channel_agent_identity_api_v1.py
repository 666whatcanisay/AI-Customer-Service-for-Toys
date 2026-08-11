from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.legacy_client_v1 import LegacyChannelEngineClient as ChannelEngineClient
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import AgentRuntimeStatus
from channel_agent.identity import AgentIdentityStatus
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.security.rbac import (
    OperatorAccessDenied,
    OperatorPermission,
    OperatorPrincipal,
    OperatorRole,
)


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
ADMIN_HEADER = {"X-Operator-Session-Reference": "session-admin"}
OPERATOR_HEADER = {"X-Operator-Session-Reference": "session-operator"}


class StaticOperatorIdentityProvider:
    def authenticate(self, session_reference: str) -> OperatorPrincipal:
        roles = {
            "session-admin": OperatorRole.ADMIN,
            "session-operator": OperatorRole.OPERATOR,
        }
        role = roles.get(session_reference)
        if role is None:
            raise OperatorAccessDenied(OperatorPermission.AGENT_IDENTITY_READ)
        return OperatorPrincipal(
            principal_id=f"principal-{role.value.casefold()}",
            roles=frozenset({role}),
            identity_provider="integration-test",
            authenticated_at=NOW,
        )


def build_client(tmp_path: Path) -> tuple[TestClient, ChannelEngineClient]:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    app = FastAPI()
    app.include_router(
        create_channel_agent_node_router(
            registry,
            identity_provider=StaticOperatorIdentityProvider(),
        )
    )
    transport = TestClient(app)
    agent = ChannelEngineClient(
        ChannelAgentConfig(
            server_url="http://testserver",
            agent_id="agent-api-identity-001",
            device_id="device-api-identity-001",
            user_reference="user-api-ref-001",
            store_reference="store-api-ref-001",
            log_directory=tmp_path / "logs",
        ),
        http_client=transport,
        allow_legacy_control=True,
    )
    return transport, agent


def test_identity_admin_api_is_authenticated_and_read_only_queries_are_scoped(
    tmp_path: Path,
) -> None:
    transport, agent = build_client(tmp_path)
    registered = agent.register(
        hostname="service-pc-api-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )

    assert registered.identity.status is AgentIdentityStatus.UNBOUND
    assert registered.production_eligible is False
    assert transport.get("/channel-agent/v1/admin/agents").status_code == 401
    assert (
        transport.get(
            "/channel-agent/v1/admin/agents",
            headers=OPERATOR_HEADER,
        ).status_code
        == 403
    )
    listed = transport.get(
        "/channel-agent/v1/admin/agents",
        headers=ADMIN_HEADER,
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["items"][0]["identity"]["device_id"] == "device-api-identity-001"
    assert body["items"][0]["identity"]["user_id"] is None
    transport.close()


def test_admin_binding_activation_heartbeat_and_unbind_flow(tmp_path: Path) -> None:
    transport, agent = build_client(tmp_path)
    agent.register(
        hostname="service-pc-api-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )

    bound = transport.put(
        "/channel-agent/v1/admin/agents/agent-api-identity-001/binding",
        headers=ADMIN_HEADER,
        json={
            "protocol_version": "1.0",
            "user_reference": "user-api-ref-001",
            "store_reference": "store-api-ref-001",
            "reason": "approved API binding",
        },
    )
    activated = transport.post(
        "/channel-agent/v1/admin/agents/agent-api-identity-001/activate",
        headers=ADMIN_HEADER,
        json={
            "protocol_version": "1.0",
            "reason": "references verified",
        },
    )
    ack = agent.report_status(
        hostname="service-pc-api-001",
        status=AgentRuntimeStatus.ONLINE,
        timestamp=NOW,
    )
    disabled = transport.delete(
        "/channel-agent/v1/admin/agents/agent-api-identity-001/binding",
        headers=ADMIN_HEADER,
        params={"reason": "device retired"},
    )
    rejected = transport.put(
        "/channel-agent/v1/agents/agent-api-identity-001/status",
        json={
            "protocol_version": "1.0",
            "agent_id": "agent-api-identity-001",
            "device_id": "device-api-identity-001",
            "user_id": "user-api-ref-001",
            "store_id": "store-api-ref-001",
            "version": "1.0.0",
            "hostname": "service-pc-api-001",
            "status": "ONLINE",
            "timestamp": NOW.isoformat(),
        },
    )
    audit = transport.get(
        "/channel-agent/v1/admin/identity-audit",
        headers=ADMIN_HEADER,
    )

    assert bound.status_code == 200
    assert bound.json()["status"] == "BOUND"
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert ack.identity_status is AgentIdentityStatus.ACTIVE
    assert ack.production_eligible is True
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "AGENT_IDENTITY_DISABLED"
    assert [item["action"] for item in audit.json()["items"]] == [
        "BIND",
        "ACTIVATE",
        "UNBIND",
    ]
    transport.close()


def test_channel_engine_app_injects_operator_identity_provider(tmp_path: Path) -> None:
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'identity-app.sqlite3').as_posix()}"
        ),
        agent_node_registry=registry,
        agent_operator_identity_provider=StaticOperatorIdentityProvider(),
    )

    with TestClient(application) as transport:
        registered = transport.post(
            "/channel-agent/v1/agents/register",
            json={
                "protocol_version": "1.0",
                "agent_id": "agent-app-identity-001",
                "device_id": "device-app-identity-001",
                "agent_version": "1.0.0",
                "hostname": "service-pc-app-001",
                "status": "STARTING",
                "timestamp": NOW.isoformat(),
            },
        )
        listed = transport.get(
            "/channel-agent/v1/admin/agents",
            headers=ADMIN_HEADER,
        )

    assert registered.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["items"][0]["identity"]["status"] == "REGISTERED"


def test_channel_engine_app_loads_agent_service_identity_from_external_file(
    tmp_path: Path,
) -> None:
    reference = "r030-integration-reference-0123456789-abcdef"
    reference_file = tmp_path / "agent-operator.session"
    reference_file.write_text(reference, encoding="utf-8")
    registry = ChannelAgentNodeRegistry(clock=lambda: NOW)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'service-app.sqlite3').as_posix()}",
            agent_operator_session_file=str(reference_file),
            agent_operator_principal_id="ai-cs-agent-service-integration",
        ),
        agent_node_registry=registry,
    )

    with TestClient(application) as transport:
        registered = transport.post(
            "/channel-agent/v1/agents/register",
            json={
                "protocol_version": "1.0",
                "agent_id": "agent-service-identity-001",
                "device_id": "device-service-identity-001",
                "agent_version": "1.1.1",
                "hostname": "service-pc-identity-001",
                "status": "STARTING",
                "timestamp": NOW.isoformat(),
            },
        )
        allowed = transport.get(
            "/channel-agent/v1/admin/agents",
            headers={"X-Operator-Session-Reference": reference},
        )
        rejected = transport.get(
            "/channel-agent/v1/admin/agents",
            headers={"X-Operator-Session-Reference": f"{reference}-wrong"},
        )

    assert registered.status_code == 201
    assert allowed.status_code == 200
    assert allowed.json()["items"][0]["identity"]["agent_id"] == (
        "agent-service-identity-001"
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "OPERATOR_PERMISSION_DENIED"
