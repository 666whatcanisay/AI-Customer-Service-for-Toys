from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from channel_agent.contract import AgentRegistrationRequest, AgentRuntimeStatus
from channel_agent.identity import (
    AgentIdentityActivationRequest,
    AgentIdentityBindingRequest,
)
from channel_engine.agent.node_api import ChannelAgentNodeRegistry
from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole


def test_observability_api_and_read_only_console(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{(tmp_path / 'observability.sqlite3').as_posix()}"
        )
    )
    with TestClient(app) as client:
        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "ops-api-conversation",
                "external_message_id": "ops-api-message",
                "text": "confidential customer phrase must not appear",
                "sender": "private-customer-id",
            },
        )
        assert intake.status_code == 200
        message_id = intake.json()["message_id"]

        runtime = client.get("/ops/runtime/status")
        events = client.get("/ops/events", params={"trace_id": message_id})
        trace = client.get(f"/ops/traces/{message_id}")
        approvals = client.get(
            "/ops/approvals", params={"waiting_only": "true"}
        )
        review = client.get(
            f"/ops/approvals/{intake.json()['decision_id']}/review"
        )
        executions = client.get("/ops/executions")
        snapshot = client.get("/ops/console/snapshot")
        console = client.get("/ops/console")

        assert runtime.status_code == 200
        assert runtime.json()["event_count"] >= 6
        assert events.status_code == 200
        assert events.json()["count"] >= 5
        assert trace.status_code == 200
        assert trace.json()["why_stopped"] == "WAITING_APPROVAL"
        assert trace.json()["next_step"] == "等待人工批准或拒绝"
        assert approvals.status_code == 200
        assert len(approvals.json()) == 1
        assert review.status_code == 200
        assert review.json()["customer_question"] == (
            "confidential customer phrase must not appear"
        )
        assert review.json()["knowledge_sources"] == []
        assert review.json()["knowledge_source_status"] == "NOT_PROVIDED"
        assert review.json()["risk_level"] == "UNSPECIFIED"
        assert executions.json() == []
        assert snapshot.status_code == 200
        assert console.status_code == 200
        assert "AI-CS 智能客服运营控制中心" in console.text
        assert "必须人工审核" in console.text
        assert "自动执行已关闭" in console.text
        assert "click send" not in console.text.casefold()

        serialized = events.text.casefold()
        assert "confidential customer phrase" not in serialized
        assert "private-customer-id" not in serialized
        assert "cookie" not in serialized
        assert "password" not in serialized
        assert "bearer " not in serialized


def test_trace_lookup_returns_404_for_unknown_identifier(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        response = client.get("/ops/traces/not-a-real-id")
    assert response.status_code == 404


def test_local_operations_console_has_distinct_device_management_center(
    tmp_path,
) -> None:
    now = datetime(2026, 8, 8, 16, 0, tzinfo=UTC)
    registry = ChannelAgentNodeRegistry(clock=lambda: now)
    registry.register(
        AgentRegistrationRequest(
            agent_id="agent-device-center-001",
            device_id="device-device-center-001",
            agent_version="2.0.0rc1",
            hostname="customer-service-pc-001",
            status=AgentRuntimeStatus.ONLINE,
            timestamp=now,
        )
    )
    admin = OperatorPrincipal(
        principal_id="device-center-test-admin",
        roles=frozenset({OperatorRole.ADMIN}),
        identity_provider="test",
        authenticated_at=now,
    )
    registry.bind_identity(
        "agent-device-center-001",
        AgentIdentityBindingRequest(
            user_reference="user-service-001",
            store_reference="store-001",
            reason="approved test device binding",
        ),
        admin,
    )
    registry.activate_identity(
        "agent-device-center-001",
        AgentIdentityActivationRequest(reason="approved active device"),
        admin,
    )
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'devices.sqlite3').as_posix()}"),
        agent_node_registry=registry,
    )
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 51000),
    ) as client:
        listing = client.get("/ops/devices")
        assert listing.status_code == 200
        device = next(
            item
            for item in listing.json()["items"]
            if item["agent_id"] == "agent-device-center-001"
        )
        assert device["identity_status"] == "ACTIVE"
        assert device["connectivity_status"] == "ONLINE"
        assert device["user_reference"] == "user-service-001"
        assert device["authorized_store_ids"] == ["store-001"]
        assert device["authoritative_source"] == "CHANNEL_ENGINE_HOST_CONTROL"
        assert device["last_heartbeat"] == now.isoformat().replace("+00:00", "Z")

        missing_intent = client.post(
            "/ops/devices/agent-device-center-001/disable",
            headers={"Origin": "http://127.0.0.1"},
            json={
                "reason": "管理员确认停用测试设备",
                "confirmation_text": "确认禁用设备",
            },
        )
        assert missing_intent.status_code == 403
        assert registry.identity_snapshot("agent-device-center-001").status.value == "ACTIVE"

        disabled = client.post(
            "/ops/devices/agent-device-center-001/disable",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Operator-Intent": "HUMAN_CONFIRMED_AGENT_DISABLE",
            },
            json={
                "reason": "管理员确认停用测试设备",
                "confirmation_text": "确认禁用设备",
            },
        )
        assert disabled.status_code == 200
        assert disabled.json()["items"][0]["identity_status"] == "DISABLED"
        assert disabled.json()["items"][0]["user_reference"] is None

        restored = client.post(
            "/ops/devices/agent-device-center-001/restore-to-registered",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Operator-Intent": "HUMAN_CONFIRMED_AGENT_RESTORE",
            },
            json={
                "reason": "管理员确认恢复测试设备为待绑定",
                "confirmation_text": "确认恢复为待绑定",
            },
        )
        assert restored.status_code == 200
        assert restored.json()["items"][0]["identity_status"] == "REGISTERED"
        assert restored.json()["items"][0]["connectivity_status"] == "ONLINE"
        assert restored.json()["items"][0]["user_reference"] is None


def test_channel_connection_and_bounded_runtime_recovery_are_logged(tmp_path) -> None:
    app = create_app(
        Settings(database_url=f"sqlite:///{(tmp_path / 'recovery.sqlite3').as_posix()}")
    )
    with TestClient(app) as client:
        assert client.post("/runtime/v1/start").status_code == 200
        app.state.runtime_browser.simulate_failure("SYNTHETIC_PAGE_CRASH")
        pulse = client.post("/runtime/v1/heartbeat")
        assert pulse.json()["overall"] == "UNHEALTHY"
        recovered = client.post(
            "/runtime/v1/recover", json={"component": "BROWSER"}
        )
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "RECOVERED"

        assert client.get(
            "/ops/events", params={"event_type": "CHANNEL_CONNECTED"}
        ).json()["count"] == 1
        assert client.get(
            "/ops/events", params={"event_type": "RECOVERY_STARTED"}
        ).json()["count"] == 1
        assert client.get(
            "/ops/events", params={"event_type": "RECOVERY_COMPLETED"}
        ).json()["count"] == 1
