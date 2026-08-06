from __future__ import annotations

from fastapi.testclient import TestClient

from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.execution import FakeExecutor
from channel_engine.control.models import KillSwitchState


def test_foundation_api_full_fake_flow(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'api.sqlite3').as_posix()}"
    )
    executor = FakeExecutor()
    application = create_app(settings=settings, executor=executor)

    with TestClient(application) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "service": "ai-cs-channel-execution-engine",
            "environment": "mock",
            "environment_profile_version": "1.0",
            "adapter_mode": "FAKE",
            "production_enabled": False,
            "real_channel_enabled": False,
            "real_gateway_enabled": False,
            "browser_execution_enabled": False,
            "human_approval_required": True,
            "unknown_auto_retry_enabled": False,
            "automatic_send_enabled": False,
        }

        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "api-conversation-1",
                "external_message_id": "api-message-1",
                "text": "hello from the fake channel",
            },
        )
        assert intake.status_code == 200
        body = intake.json()
        assert body["decision_state"] == "WAITING_APPROVAL"
        assert executor.call_count == 0
        assert application.state.adapter_registry.discover() == ("fake-pdd",)
        assert application.state.fake_pdd_adapter.receive_call_count == 1
        assert application.state.fake_pdd_adapter.send_call_count == 0
        assert application.state.gateway_client is not None
        assert application.state.mock_ai_cs_server.request_count == 1
        assert application.state.mock_ai_cs_server.decision_compute_count == 1

        decision = client.get(f"/v1/decisions/{body['decision_id']}")
        assert decision.status_code == 200
        assert decision.json()["requires_approval"] is True

        execution = client.post(
            f"/v1/decisions/{body['decision_id']}/approve",
            json={"operator": "api-human-operator"},
        )
        assert execution.status_code == 202
        assert execution.json()["execution_state"] == "PENDING"
        assert executor.call_count == 0

        worker_result = application.state.execution_worker.run_once()
        assert worker_result is not None
        assert worker_result.execution_state.value == "SUCCESS"
        assert executor.call_count == 1
        assert application.state.fake_pdd_adapter.send_call_count == 0


def test_unknown_decision_returns_404(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'api-404.sqlite3').as_posix()}"
        )
    )
    with TestClient(application) as client:
        response = client.get("/v1/decisions/decision-missing")
    assert response.status_code == 404


def test_control_plane_read_views_and_kill_switch_gate_are_wired(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'api-control.sqlite3').as_posix()}"
        )
    )
    with TestClient(application) as client:
        status = client.get("/control/v1/status")
        health = client.get("/control/v1/health")
        assert status.status_code == 200
        assert status.json()["control_plane_version"] == "1.0"
        assert status.json()["kill_switch"]["state"] == "DISABLED"
        assert health.status_code == 200
        assert health.json()["worker"]["state"] == "STOPPED"

        intake = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "api-control-conversation",
                "external_message_id": "api-control-message",
                "text": "synthetic control-plane API message",
            },
        )
        assert intake.status_code == 200
        application.state.control_plane.enable_kill_switch(
            operator="api.control.operator",
            reason="API_CONTROL_SAFETY_STOP",
        )
        blocked = client.post(
            f"/v1/decisions/{intake.json()['decision_id']}/approve",
            json={"operator": "api-human-operator"},
        )

        assert blocked.status_code == 409
        assert application.state.control_plane.kill_switch_status().state is (
            KillSwitchState.ENABLED
        )
        assert application.state.execution_worker.run_once() is None
