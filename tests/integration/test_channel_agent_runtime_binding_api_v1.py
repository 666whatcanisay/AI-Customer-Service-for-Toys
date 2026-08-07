from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.client import (
    AgentConnectionError,
    AgentRejectedError,
    ChannelEngineClient,
)
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import AgentRuntimeStatus
from channel_agent.identity import AgentIdentityStatus
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.security.rbac import (
    OperatorAccessDenied,
    OperatorPermission,
    OperatorPrincipal,
    OperatorRole,
)


NOW = datetime(2026, 8, 6, 17, 0, tzinfo=UTC)
CODE = "B" * 32
ADMIN = {"X-Operator-Session-Reference": "admin-session"}
OPERATOR = {"X-Operator-Session-Reference": "operator-session"}


class IdentityProvider:
    def authenticate(self, session_reference: str) -> OperatorPrincipal:
        role = {
            "admin-session": OperatorRole.ADMIN,
            "operator-session": OperatorRole.OPERATOR,
        }.get(session_reference)
        if role is None:
            raise OperatorAccessDenied(OperatorPermission.AGENT_IDENTITY_READ)
        return OperatorPrincipal(
            principal_id=f"principal-{role.value.casefold()}",
            roles=frozenset({role}),
            identity_provider="runtime-binding-api-test",
            authenticated_at=NOW,
        )


def build_clients(tmp_path):
    registry = ChannelAgentNodeRegistry(
        clock=lambda: NOW,
        binding_code_factory=lambda: CODE,
    )
    app = FastAPI()
    app.include_router(
        create_channel_agent_node_router(
            registry,
            identity_provider=IdentityProvider(),
        )
    )
    transport = TestClient(app, base_url="https://testserver")
    agent = ChannelEngineClient(
        ChannelAgentConfig(
            server_url="https://testserver",
            agent_id="agent-runtime-api-001",
            device_id="device-runtime-api-001",
            log_directory=tmp_path / "logs",
        ),
        http_client=transport,
    )
    return transport, agent


def test_enrollment_user_multi_store_activation_and_status_sync(tmp_path) -> None:
    transport, agent = build_clients(tmp_path)
    registered = agent.register(
        hostname="service-pc-runtime-api-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )
    denied = transport.post(
        "/channel-agent/v1/admin/enrollment-grants",
        headers=OPERATOR,
        json={
            "protocol_version": "1.0",
            "agent_id": "agent-runtime-api-001",
            "device_id": "device-runtime-api-001",
            "user_reference": "user-runtime-api-001",
            "store_references": ["store-api-a", "store-api-b"],
            "reason": "unauthorized issuance",
        },
    )
    grant = transport.post(
        "/channel-agent/v1/admin/enrollment-grants",
        headers=ADMIN,
        json={
            "protocol_version": "1.0",
            "agent_id": "agent-runtime-api-001",
            "device_id": "device-runtime-api-001",
            "user_reference": "user-runtime-api-001",
            "store_references": ["store-api-a", "store-api-b"],
            "reason": "approved workstation enrollment",
        },
    )
    enrolled = agent.enroll(grant.json()["binding_code"])
    reused = transport.post(
        "/channel-agent/v1/agents/enroll",
        json={
            "protocol_version": "1.0",
            "agent_id": "agent-runtime-api-001",
            "device_id": "device-runtime-api-001",
            "binding_code": CODE,
        },
    )
    activated = transport.post(
        "/channel-agent/v1/admin/agents/agent-runtime-api-001/activate",
        headers=ADMIN,
        json={
            "protocol_version": "1.0",
            "reason": "binding references verified",
        },
    )
    before_update = agent.report_status(
        hostname="service-pc-runtime-api-001",
        status=AgentRuntimeStatus.ONLINE,
        timestamp=NOW,
    )
    stores = transport.put(
        "/channel-agent/v1/admin/agents/agent-runtime-api-001/stores",
        headers=ADMIN,
        json={
            "protocol_version": "1.0",
            "store_references": ["store-api-a", "store-api-c", "store-api-d"],
            "reason": "authorized multi-store assignment",
        },
    )
    synchronized = agent.report_status(
        hostname="service-pc-runtime-api-001",
        status=AgentRuntimeStatus.ONLINE,
        timestamp=NOW,
    )
    admin_view = transport.get(
        "/channel-agent/v1/admin/agents/agent-runtime-api-001",
        headers=ADMIN,
    )

    assert registered.identity.status is AgentIdentityStatus.UNBOUND
    assert denied.status_code == 403
    assert grant.status_code == 201
    assert enrolled.binding.store_ids == ("store-api-a", "store-api-b")
    assert reused.status_code == 403
    assert activated.json()["status"] == "ACTIVE"
    assert before_update.identity is not None
    assert before_update.identity.binding_revision == 2
    assert stores.json()["store_ids"] == [
        "store-api-a",
        "store-api-c",
        "store-api-d",
    ]
    assert synchronized.identity is not None
    assert synchronized.identity.binding_revision == 3
    assert synchronized.identity.effective_store_ids == (
        "store-api-a",
        "store-api-c",
        "store-api-d",
    )
    assert admin_view.json()["online_status"] == "ONLINE"
    assert admin_view.json()["identity"]["user_id"] == "user-runtime-api-001"
    transport.close()


def test_invalid_enrollment_code_and_insecure_remote_transport_fail_closed(
    tmp_path,
) -> None:
    transport, agent = build_clients(tmp_path)
    agent.register(
        hostname="service-pc-runtime-api-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=NOW,
    )

    with pytest.raises(AgentRejectedError):
        agent.enroll("C" * 32)

    insecure = ChannelEngineClient(
        ChannelAgentConfig(
            server_url="http://channel-engine.example",
            agent_id="agent-insecure-001",
            device_id="device-insecure-001",
        ),
        http_client=transport,
    )
    with pytest.raises(AgentConnectionError, match="requires HTTPS"):
        insecure.enroll(CODE)
    transport.close()
